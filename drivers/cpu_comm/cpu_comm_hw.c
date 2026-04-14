// SPDX-License-Identifier: GPL-2.0
/*
 * cpu_comm_hw.c — Hardware abstraction for CPU_COMM
 *
 * Register access via io_accessor (MMIO read/write with whitelist),
 * hardware spinlocks via sunxi hwspinlock controller,
 * shared registers mapped to MIPS control MMIO (0x03061024/28),
 * software spinlocks in shared memory.
 *
 * RE source: HAL_SX6/Kernel_Driver/cpu_comm/
 *   - cpu_comm_core.c (io_accessor, known_regs)
 *   - tridsharereg.c (getShareRegbyID)
 *   - tridspinlock.c (hwspinlock, sw spinlock)
 */

#include <linux/kernel.h>
#include <linux/io.h>
#include <linux/hwspinlock.h>
#include <linux/delay.h>
#include <linux/workqueue.h>
#include <linux/interrupt.h>
#include "cpu_comm.h"

/* ── Globals ───────────────────────────────────────────────── */

void *hwlocks[HW_SPINLOCK_COUNT * 2];	/* [0..13]=lock handles, [14..27]=counters */

/*
 * Known register addresses — the only registers io_accessor will touch.
 * From IDA: known_regs @ 0x16350 in cpu_comm_dev.ko
 */
static const u32 known_regs[] = {
	0x03061024,	/* MIPS ShareReg14 — SharedMemAddr */
	0x03061028,	/* MIPS ShareReg13 — SharedMemSize */
	0x03003000,	/* Msgbox channel register */
	0x03003010,	/* Msgbox channel register */
};

static void __iomem *mips_ctrl_base;	/* ioremap of 0x03061000 */
static void __iomem *msgbox_ctrl_base;	/* ioremap of 0x03003000 */

/*
 * ── H713 Msgbox Register Layout ─────────────────────────────
 *
 * The H713 uses a custom Allwinner msgbox with per-user regions
 * (0x400 bytes each). ARM = User 0 @ 0x03003000.
 *
 * Register offsets within ARM user region (verified from stock
 * vmlinux IDA RE + live hardware register dump):
 *
 *   +0x010: MSG_DATA   — FIFO read/write (MIPS→ARM messages)
 *   +0x024: IRQ_EN     — RX IRQ enable (bit pattern 0x55 = all RX)
 *   +0x034: IRQ_EN2    — TX IRQ enable (bit pattern 0xAA = all TX)
 *   +0x050: IRQ_STATUS — RX pending (write-1-to-clear)
 *   +0x060: FIFO_STAT  — Number of messages in FIFO
 *
 * TX to MIPS: write message to msgbox_ctrl_base + 0x20
 * (ARM→MIPS FIFO data register, confirmed working).
 *
 * GIC IRQ: SPI 21 (verified: permanently asserted when FIFO
 * has unread messages; SPI 46 was wrong — never asserts).
 */
/*
 * Verified from stock vmlinux IDA (sunxi_msgbox_irq):
 *   RX: sx_base(mdev, ARM=0) + port*4 + offset
 *   TX: sx_base(mdev, MIPS=1) + port*4 + offset
 * With port=0, ARM_base=0x03003000, MIPS_base=0x03003400:
 */
#define H713_MSGBOX_RX_FIFO	0x60	/* ARM base+0x60: RX FIFO count */
#define H713_MSGBOX_RX_DATA	0x70	/* ARM base+0x70: RX auto-pop read */
#define H713_MSGBOX_RX_IRQ_EN	0x20	/* ARM base+0x20: RX IRQ enable */
#define H713_MSGBOX_RX_IRQ_CLR	0x24	/* ARM base+0x24: RX IRQ clear (W1C) */
#define H713_MSGBOX_TX_DATA	0x474	/* MIPS User1 Port1 FIFO write */
#define H713_MSGBOX_TX_FIFO	0x464	/* MIPS User1 Port1 FIFO status */

#define H713_MSGBOX_RX_IRQ_BIT	BIT(0)	/* RX IRQ bit for port 0 */

static int msgbox_irq_num = -1;
static void (*msgbox_rx_callback)(int type, int direction);
static struct delayed_work msgbox_poll_work;
static bool msgbox_poll_active;

/*
 * Polling work function — processes msgbox FIFO messages.
 *
 * The H713 msgbox IRQ is level-triggered and stays asserted as long
 * as the FIFO contains data. Since the MIPS sends messages faster
 * than we can process+reply, a pure IRQ handler triggers the kernel's
 * IRQ storm detector (100k limit). Instead we use a polling approach:
 * drain the FIFO periodically, dispatch messages, reschedule.
 */
static void cpu_comm_msgbox_poll_fn(struct work_struct *work)
{
	u32 raw;
	int type, direction;
	int count = 0;

	if (!msgbox_poll_active || !msgbox_ctrl_base)
		return;

	while (readl(msgbox_ctrl_base + H713_MSGBOX_RX_FIFO) & 0xF) {
		raw = readl(msgbox_ctrl_base + H713_MSGBOX_RX_DATA);
		type = (raw >> 16) & 0xFFFF;
		direction = raw & 0xFFFF;

		pr_info_ratelimited("cpu_comm: msgbox rx raw=0x%08x type=%d dir=%d\n",
				    raw, type, direction);

		if (msgbox_rx_callback)
			msgbox_rx_callback(type, direction);

		if (++count > 32)
			break;
	}

	if (msgbox_poll_active)
		schedule_delayed_work(&msgbox_poll_work, msecs_to_jiffies(1));
}

int cpu_comm_msgbox_request_irq(int irq, void *callback)
{
	u32 raw;

	msgbox_rx_callback = callback;

	/* Drain stale messages before starting the poll */
	while (readl(msgbox_ctrl_base + H713_MSGBOX_RX_FIFO) & 0xF) {
		raw = readl(msgbox_ctrl_base + H713_MSGBOX_RX_DATA);
		pr_info("cpu_comm: drained stale msgbox message: 0x%08x\n", raw);
	}

	INIT_DELAYED_WORK(&msgbox_poll_work, cpu_comm_msgbox_poll_fn);
	msgbox_poll_active = true;
	schedule_delayed_work(&msgbox_poll_work, msecs_to_jiffies(10));

	pr_info("cpu_comm: msgbox RX poll started (1ms interval, IRQ %d reserved)\n", irq);
	return 0;
}

void cpu_comm_msgbox_free_irq(void)
{
	if (msgbox_poll_active) {
		msgbox_poll_active = false;
		/*
		 * Use cancel_delayed_work (non-sync) to avoid blocking
		 * during shutdown. The poll_fn checks msgbox_poll_active
		 * at entry and returns immediately when false.
		 * _sync variant hangs if MMIO is already dead during reboot.
		 */
		cancel_delayed_work(&msgbox_poll_work);
		msgbox_rx_callback = NULL;
		pr_info("cpu_comm: msgbox RX poll stopped\n");
	}
}

/* Legacy stubs — no longer needed but keep exports for now */
void cpu_comm_msgbox_probe_start(void) { }
void cpu_comm_msgbox_probe_stop(void) { }

/* ── Register access ───────────────────────────────────────── */

static int is_known_reg(u32 addr)
{
	int i;

	for (i = 0; i < ARRAY_SIZE(known_regs); i++) {
		if (known_regs[i] == addr)
			return 1;
	}
	return 0;
}

/*
 * Map a physical register address to its ioremapped virtual address.
 * We maintain two mappings: MIPS control (0x03061xxx) and msgbox (0x03004xxx).
 */
static void __iomem *reg_to_iomem(u32 phys_addr)
{
	if (phys_addr >= 0x03061000 && phys_addr < 0x03062000) {
		if (!mips_ctrl_base)
			return NULL;
		return mips_ctrl_base + (phys_addr - 0x03061000);
	}
	if (phys_addr >= 0x03003000 && phys_addr < 0x03004000) {
		if (!msgbox_ctrl_base)
			return NULL;
		return msgbox_ctrl_base + (phys_addr - 0x03003000);
	}
	return NULL;
}

int comm_ReadRegWord(u32 reg_addr)
{
	void __iomem *vaddr;

	if (!is_known_reg(reg_addr)) {
		pr_err("cpu_comm: read from unknown reg 0x%08x\n", reg_addr);
		WARN_ON(1);
		return 0;
	}

	vaddr = reg_to_iomem(reg_addr);
	if (!vaddr) {
		pr_err("cpu_comm: reg 0x%08x not mapped\n", reg_addr);
		return 0;
	}

	return readl(vaddr);
}

void comm_WriteRegWord(u32 reg_addr, u32 value)
{
	void __iomem *vaddr;

	if (!is_known_reg(reg_addr)) {
		pr_err("cpu_comm: write to unknown reg 0x%08x\n", reg_addr);
		WARN_ON(1);
		return;
	}

	vaddr = reg_to_iomem(reg_addr);
	if (!vaddr) {
		pr_err("cpu_comm: reg 0x%08x not mapped\n", reg_addr);
		return;
	}

	writel(value, vaddr);
}

/* ── Shared Registers (MIPS MMIO) ─────────────────────────── */

/*
 * Shared registers are MIPS control MMIO registers used to exchange
 * configuration between ARM and MIPS at init time.
 *
 * Reg 14 → 0x03061024 → SharedMemAddr (physical)
 * Reg 13 → 0x03061028 → SharedMemSize
 */
int getShareRegbyID(int reg_id)
{
	switch (reg_id) {
	case SHARE_REG_ADDR:
		return 0x03061024;
	case SHARE_REG_SIZE:
		return 0x03061028;
	default:
		pr_err("cpu_comm: unknown share reg %d\n", reg_id);
		return 0;
	}
}

int comm_ReadShareReg(int reg_id)
{
	return comm_ReadRegWord(getShareRegbyID(reg_id));
}

void comm_WriteShareReg(int reg_id, u32 value)
{
	comm_WriteRegWord(getShareRegbyID(reg_id), value);
}

/* ── Hardware Spinlocks ────────────────────────────────────── */

/*
 * The H713 has a hardware spinlock controller (sunxi-hwspinlock).
 * cpu_comm uses 14 locks. The hardware spinlock ID = logical_id + 8.
 * These locks synchronize shared-memory access between ARM and MIPS.
 */

static int getRegbySpinID(int id)
{
	if (id < 0 || id > 13) {
		pr_err("cpu_comm: invalid spinlock ID %d\n", id);
		return -1;
	}
	return id + 8;	/* hardware spinlock offset */
}

int comm_InitHwSpinLock(void)
{
	int i, j, hw_id;

	for (i = 0; i < HW_SPINLOCK_COUNT; i++) {
		if (!hwlocks[i]) {
			hw_id = getRegbySpinID(i);
			hwlocks[i] = hwspin_lock_request_specific(hw_id);
			if (!hwlocks[i]) {
				pr_err("cpu_comm: failed to get hwspinlock %d (hw=%d)\n",
				       i, hw_id);
				for (j = 0; j < i; j++) {
					if (hwlocks[j]) {
						hwspin_lock_free(hwlocks[j]);
						hwlocks[j] = NULL;
					}
				}
				return -EBUSY;
			}
		}
	}
	return 0;
}

/*
 * spinlockhwReg — Acquire hardware spinlock (busy-wait)
 */
int spinlockhwReg(int lock_id)
{
	int ret;

	if (!hwlocks[lock_id]) {
		pr_err("cpu_comm: spinlockhwReg(%d): hwlocks[%d] is NULL!\n",
		       lock_id, lock_id);
		return -EINVAL;
	}

	ret = __hwspin_lock_timeout(hwlocks[lock_id], 100, HWLOCK_RAW, NULL);
	if (ret) {
		pr_warn("cpu_comm: spinlockhwReg(%d): timeout (ret=%d) hwlock=%px\n",
			lock_id, ret, hwlocks[lock_id]);
		return ret;
	}

	/* Increment lock counter (stored at hwlocks[lock_id + 14]) */
	((u32 *)hwlocks)[lock_id + HW_SPINLOCK_COUNT]++;
	return 0;
}

/*
 * tryspinlockhwReg — Try to acquire hardware spinlock (non-blocking)
 * Returns 1 on success, 0 on failure.
 */
int tryspinlockhwReg(int lock_id)
{
	int ret;

	ret = __hwspin_trylock(hwlocks[lock_id], HWLOCK_RAW, NULL);
	if (ret == 0) {
		((u32 *)hwlocks)[lock_id + HW_SPINLOCK_COUNT]++;
		return 1; /* acquired */
	}
	return 0; /* failed */
}

/*
 * spinUnlockhwReg — Release hardware spinlock
 */
void spinUnlockhwReg(int lock_id)
{
	__hwspin_unlock(hwlocks[lock_id], HWLOCK_RAW, NULL);
}

/* ── Software Spinlocks (in shared memory) ─────────────────── */

/*
 * 2-Level spinlock system from IDA:
 *
 * Level 1: HW spinlock — held BRIEFLY for atomic SharedMem update.
 *          Mapping: SW lock N → HW lock N+2 (hwlocks[N+2])
 *
 * Level 2: SharedMem owner field — held for the ENTIRE critical section.
 *          12 entries at ShMemAddrBase + 0, each 12 bytes:
 *            +0: type (u8) — lock type, initialized to 2
 *            +1: owner_cpu (u8) — 2=free, 0=ARM, 1=MIPS
 *            +2: mutex_flag (u8) — 0 for normal, set for nested
 *            +3: (u8) — initialized to 2
 *            +4: ref_count (u32) — nesting depth
 *            +8: thread_id (u32) — 255=unassigned, else current->tgid
 *
 * enterCritical: acquires HW lock → sets owner in SharedMem → releases HW lock
 * leaveCritical: sets owner back to 2 (free) in SharedMem (no HW lock needed)
 * spinLock: uses enterCritical/leaveCritical + ref_count management
 */

/*
 * SharedMem spinlock entry layout (12 bytes, from IDA comm_InitSpinLock):
 *   [0]: type (init: 2)
 *   [1]: status (init: 2)
 *   [2]: mutex_flag (init: 0)
 *   [3]: owner_cpu (SPINLOCK_FREE=2, ARM=0, MIPS=1)
 *   [4..7]: ref_count (u32, init: 0)
 *   [8..11]: thread_id (u32, init: 255=NONE)
 */
#define SPINLOCK_FREE		2	/* owner_cpu value for "free" */
#define SPINLOCK_HWID_NONE	255	/* unassigned hw lock id */
#define SPINLOCK_MAX_ID		11	/* max SW lock id */
#define SPINLOCK_HW_OFFSET	2	/* SW lock N → hwlocks[N+2] */
#define SPINLOCK_ENTRY_SIZE	12	/* bytes per entry in SharedMem */
#define SPINLOCK_OFF_TYPE	0
#define SPINLOCK_OFF_STATUS	1
#define SPINLOCK_OFF_MUTEX	2
#define SPINLOCK_OFF_OWNER	3	/* THE critical offset — was wrongly 1 */

static u8 *getSpinLockMemArea(void)
{
	if (WARN_ON(!ShMemAddrBase))
		return NULL;
	return (u8 *)(unsigned long)ShMemAddrBase;
}

/*
 * comm_InitSpinLock — Initialize 12 spinlock entries in shared memory.
 * From IDA @ 0x92e4.
 */
int comm_InitSpinLock(int dummy)
{
	u8 *base;
	int i;
	int ret;

	base = getSpinLockMemArea();
	if (!base)
		return -1;

	ret = comm_InitHwSpinLock();
	if (ret)
		return ret;

	/* Release all HW locks 1..13 (clear stale state from previous boot) */
	for (i = 1; i < HW_SPINLOCK_COUNT; i++)
		spinUnlockhwReg(i);

	/* Initialize 12 SW spinlock entries in shared memory */
	for (i = 0; i < 12; i++) {
		u8 *entry = base + SPINLOCK_ENTRY_SIZE * i;

		entry[0] = SPINLOCK_FREE;	/* type */
		entry[1] = SPINLOCK_FREE;	/* status */
		entry[2] = 0;			/* mutex_flag */
		entry[3] = SPINLOCK_FREE;	/* owner_cpu = free */
		*(u32 *)(entry + 4) = 0;	/* ref_count */
		*(u32 *)(entry + 8) = SPINLOCK_HWID_NONE; /* thread_id */
	}

	return 0;
}

/*
 * enterCritical — Atomically claim ownership via HW lock + SharedMem.
 * From IDA @ 0x97c4.
 *
 * 1. Spin until SharedMem entry shows "free" (owner==2)
 * 2. Acquire HW lock (lock_id + 2)
 * 3. Verify still free → set owner = our CPU
 * 4. Release HW lock
 *
 * After this, the calling CPU "owns" the lock in SharedMem.
 */
static void enterCritical(int lock_id)
{
	u8 *base = getSpinLockMemArea();
	u8 *entry = base + SPINLOCK_ENTRY_SIZE * lock_id;
	int hw_id = lock_id + SPINLOCK_HW_OFFSET;
	int spins = 0;
	u8 cur_cpu;

	pr_debug("cpu_comm: enterCritical(%d) hw_id=%d entry=[%02x %02x %02x %02x]\n",
		 lock_id, hw_id, entry[0], entry[1], entry[2], entry[3]);

	/*
	 * Use hwspin_lock_timeout instead of trylock loop.
	 * MIPS may already hold HW locks — trylock would spin forever.
	 * Timeout of 50ms: if we can't get the HW lock, force-proceed
	 * because ARM needs to initialize regardless of MIPS state.
	 */
	{
		int ret = __hwspin_lock_timeout(hwlocks[hw_id], 50, HWLOCK_RAW, NULL);

		if (ret) {
			/* HW lock timeout — MIPS probably holds it */
			pr_warn("cpu_comm: enterCritical(%d): HW lock %d timeout "
				"(ret=%d), force-claiming SharedMem entry\n",
				lock_id, hw_id, ret);
			/* Force-claim without HW lock protection */
			cur_cpu = (u8)getCurCPUID(0);
			entry[SPINLOCK_OFF_OWNER] = cur_cpu;
			dmb(ish);
			return;
		}

		/* Got HW lock — claim SharedMem entry */
		cur_cpu = (u8)getCurCPUID(0);
		entry[SPINLOCK_OFF_OWNER] = cur_cpu;
		dmb(ish);

		/* Release HW lock — we now own via SharedMem */
		__hwspin_unlock(hwlocks[hw_id], HWLOCK_RAW, NULL);

		pr_debug("cpu_comm: enterCritical(%d) acquired OK\n", lock_id);
	}
}

/*
 * leaveCritical — Release ownership in SharedMem.
 * From IDA @ 0x9914.
 * Just sets owner back to 2 (free). No HW lock needed.
 */
static void leaveCritical(int lock_id)
{
	u8 *base = getSpinLockMemArea();
	u8 *entry = base + SPINLOCK_ENTRY_SIZE * lock_id;

	entry[SPINLOCK_OFF_OWNER] = SPINLOCK_FREE;	/* set owner = free */
}

/*
 * spinLock — Full lock with ref_count tracking.
 * From IDA @ 0x9a68.
 *
 * @lock_id: 0..11
 * @mode: 0=try (non-blocking), 1=mutex (recursive), 2=exclusive (blocking)
 *
 * Returns: 0=failed (mode 0 only), 1=recursive re-lock, 2=new lock acquired
 */
static int spinLock(int lock_id, int mode)
{
	u8 *base = getSpinLockMemArea();
	u8 *entry = base + SPINLOCK_ENTRY_SIZE * lock_id;
	u8 cur_cpu;

	if (lock_id > SPINLOCK_MAX_ID) {
		pr_err("cpu_comm: spinLock: invalid lock_id %d\n", lock_id);
		return -EINVAL;
	}
	if (*(int *)(entry + 4) < 0) { /* ref_count sanity */
		pr_err("cpu_comm: spinLock: negative ref_count on lock %d\n", lock_id);
		return -EIO;
	}

	while (1) {
		enterCritical(lock_id);
		cur_cpu = (u8)getCurCPUID(0);

		if (entry[SPINLOCK_OFF_OWNER] == cur_cpu) {
			/*
			 * We own this lock (entry[3] set by enterCritical).
			 * Two sub-cases:
			 *   a) First acquisition: thread_id == NONE (255)
			 *      → enterCritical claimed it but thread_id not set yet
			 *   b) Recursive lock: thread_id == our tgid
			 */
			if (*(u32 *)(entry + 8) == SPINLOCK_HWID_NONE) {
				/* First acquisition — set thread_id + ref_count */
				*(u32 *)(entry + 8) = (u32)current->tgid;
				(*(u32 *)(entry + 4))++;
				leaveCritical(lock_id);
				return 2;	/* new lock acquired */
			}
			if (!entry[2] && /* mutex_flag clear */
			    *(u32 *)(entry + 8) == (u32)current->tgid) {
				/* Same thread — recursive lock */
				(*(u32 *)(entry + 4))++;
				leaveCritical(lock_id);
				return 1;	/* recursive */
			}
			/* Different thread holds it — release and retry */
			leaveCritical(lock_id);
			if (!mode)
				return 0;	/* non-blocking: fail */
			schedule();
			continue;
		}

		if (entry[SPINLOCK_OFF_OWNER] == SPINLOCK_FREE) {
			/* Lock is free but enterCritical didn't claim it
			 * (shouldn't happen — enterCritical always claims).
			 * Handle defensively: claim it now.
			 */
			entry[SPINLOCK_OFF_OWNER] = cur_cpu;
			*(u32 *)(entry + 8) = (u32)current->tgid;
			(*(u32 *)(entry + 4))++;
			dmb(ish);
			leaveCritical(lock_id);
			return 2;	/* new lock acquired */
		}

		/* Someone else owns it */
		leaveCritical(lock_id);
		if (!mode)
			return 0;	/* non-blocking: fail */
		if (mode >= 2)
			schedule();	/* blocking: yield and retry */
	}
}

/*
 * comm_SpinLock — Acquire lock (exclusive, blocking).
 * From IDA @ 0x9e2c: calls spinLock(id, 2).
 */
void comm_SpinLock(int lock_id)
{
	pr_debug("cpu_comm: comm_SpinLock(%d) enter\n", lock_id);
	spinLock(lock_id, 2);
	pr_debug("cpu_comm: comm_SpinLock(%d) acquired\n", lock_id);
}

/*
 * comm_SpinUnLock — Release lock with ref_count management.
 * From IDA @ 0x9e74.
 */
void comm_SpinUnLock(int lock_id, int dummy)
{
	u8 *base = getSpinLockMemArea();
	u8 *entry = base + SPINLOCK_ENTRY_SIZE * lock_id;

	if (lock_id > SPINLOCK_MAX_ID) {
		pr_err("cpu_comm: SpinUnLock: invalid lock_id %d\n", lock_id);
		return;
	}

	enterCritical(lock_id);

	if (*(int *)(entry + 4) <= 0) {
		/* ref_count already 0 — double unlock */
		leaveCritical(lock_id);
		return;
	}

	if (entry[SPINLOCK_OFF_OWNER] == SPINLOCK_FREE) {
		pr_warn("cpu_comm: SpinUnLock(%d): unlocking a free lock, skipping\n", lock_id);
		leaveCritical(lock_id);
		return;
	}
	if (*(u32 *)(entry + 8) == SPINLOCK_HWID_NONE) {
		pr_warn("cpu_comm: SpinUnLock(%d): no thread_id, skipping\n", lock_id);
		leaveCritical(lock_id);
		return;
	}

	/* Decrement ref_count */
	if (--(*(u32 *)(entry + 4)) == 0) {
		/* Last unlock — release fully */
		entry[SPINLOCK_OFF_OWNER] = SPINLOCK_FREE;
		*(u32 *)(entry + 8) = SPINLOCK_HWID_NONE;
	}

	leaveCritical(lock_id);
}

/*
 * comm_TrySpinLock — Non-blocking lock attempt.
 * Returns 1 on success, 0 on failure.
 */
int comm_TrySpinLock(int lock_id)
{
	return spinLock(lock_id, 0) ? 1 : 0;
}

/*
 * comm_SpinLockMutex — Recursive-safe lock (mutex mode).
 * From IDA @ 0x9e48: calls spinLock(id, 1).
 */
void comm_SpinLockMutex(int lock_id)
{
	spinLock(lock_id, 1);
}

void comm_SpinLocksetType(int lock_id, int type)
{
	u8 *base = getSpinLockMemArea();

	if (!base)
		return;
	base[SPINLOCK_ENTRY_SIZE * lock_id] = type;
}

/*
 * comm_ReqestSpinLock — Allocate a free software spinlock from the pool.
 * Scans slots 5..11 for a free one (owner == SPINLOCK_FREE).
 * Returns slot ID (5..11) or 255 if none available.
 */
int comm_ReqestSpinLock(void)
{
	int id;
	u8 *base, *entry;

	spinlockhwReg(1);

	base = getSpinLockMemArea();
	if (!base) {
		spinUnlockhwReg(1);
		return 255;
	}

	for (id = HW_SPINLOCK_APP_START; id <= HW_SPINLOCK_APP_END; id++) {
		entry = base + SPINLOCK_ENTRY_SIZE * id;
		if (entry[SPINLOCK_OFF_OWNER] == SPINLOCK_FREE) {
			if (*(u32 *)(entry + 4) != 0) {
				pr_warn("cpu_comm: AssignSpinLock(%d): free lock has non-zero ref_count\n", id);
				continue;
			}
			if (entry[0] != SPINLOCK_FREE) {
				pr_warn("cpu_comm: AssignSpinLock(%d): inconsistent mutex state\n", id);
				continue;
			}
			if (*(u32 *)(entry + 8) != SPINLOCK_HWID_NONE) {
				pr_warn("cpu_comm: AssignSpinLock(%d): free lock has thread_id set\n", id);
				continue;
			}
			entry[SPINLOCK_OFF_MUTEX] = 0;
			entry[SPINLOCK_OFF_OWNER] = getCurCPUID(0);
			spinUnlockhwReg(1);
			return id;
		}
	}

	spinUnlockhwReg(1);
	return 255;
}

/*
 * comm_ReleaseSpinLock — Return a spinlock to the pool.
 */
int comm_ReleaseSpinLock(int lock_id)
{
	u8 *base, *entry;

	if (lock_id < HW_SPINLOCK_APP_START || lock_id > HW_SPINLOCK_APP_END) {
		pr_err("cpu_comm: release invalid spinlock %d\n", lock_id);
		return -EINVAL;
	}

	base = getSpinLockMemArea();
	entry = base + SPINLOCK_ENTRY_SIZE * lock_id;

	spinlockhwReg(1);

	if (*(u32 *)(entry + 4) != 0 || *(u32 *)(entry + 8) != SPINLOCK_HWID_NONE) {
		pr_err("cpu_comm: spinlock %d still in use\n", lock_id);
		spinUnlockhwReg(1);
		return -1;
	}

	entry[SPINLOCK_OFF_OWNER] = SPINLOCK_FREE;
	spinUnlockhwReg(1);
	return 0;
}

/* ── Interrupt management ──────────────────────────────────── */

/*
 * getInterruptRegChannel — Get interrupt register set for a CPU pair
 * cpu: 0=ARM, 1=MIPS. channel: 0 or 1.
 * Returns pointer to interrupt register struct (5 DWORDs).
 * Stock returns 0 (simplified — actual registers are in the built-in
 * sunxi_cpu_comm RPMSG layer which handles the msgbox hardware).
 */
int getInterruptRegChannel(u32 cpu, u32 channel)
{
	if (cpu > 1 || channel > 1) {
		pr_err("cpu_comm: invalid IRQ channel cpu=%u ch=%u\n",
		       cpu, channel);
		return -EINVAL;
	}
	return 0; /* stub — actual interrupt routing is in sunxi_cpu_comm */
}

/*
 * ResetCommInterrupt — Clear interrupt registers for all channels
 */
void ResetCommInterrupt(int dummy)
{
	/* In the stock module, this writes 0 to four interrupt registers
	 * per channel. Since our interrupt handling goes through the
	 * built-in sunxi_cpu_comm RPMSG layer, this is a no-op.
	 * The RPMSG layer manages msgbox interrupts directly.
	 */
}

/*
 * comm_SpinLockCleanUpInCPUReset — Release spinlocks held by reset CPU.
 *
 * From IDA @ 0xa008. Walks all spinlock slots and releases any that
 * were held by the specified CPU. This prevents deadlocks when a CPU
 * resets while holding spinlocks.
 */
/*
 * comm_SpinLockCleanUpInCPUReset — Release locks held by reset CPU.
 * From IDA @ 0xa008. Walks SharedMem entries and force-releases any
 * owned by the specified CPU.
 */
void comm_SpinLockCleanUpInCPUReset(u32 cpu_id)
{
	u8 *base;
	int i;

	pr_info("cpu_comm: SpinLockCleanUpInCPUReset(%u)\n", cpu_id);

	base = getSpinLockMemArea();
	if (!base)
		return;

	for (i = 0; i <= SPINLOCK_MAX_ID; i++) {
		u8 *entry = base + SPINLOCK_ENTRY_SIZE * i;

		if (entry[SPINLOCK_OFF_OWNER] == (u8)cpu_id) {
			/* This lock was held by the resetting CPU — force release */
			pr_info("cpu_comm: force-releasing lock %d (held by CPU %u)\n",
				i, cpu_id);
			entry[SPINLOCK_OFF_OWNER] = SPINLOCK_FREE;
			*(u32 *)(entry + 4) = 0;		/* ref_count = 0 */
			*(u32 *)(entry + 8) = SPINLOCK_HWID_NONE; /* thread_id = none */
		}
	}
}

/*
 * sunxi_cpu_comm_send_intr_to_mips — Trigger msgbox interrupt to MIPS.
 *
 * The stock module writes directly to the msgbox MMIO registers.
 * On our mainline kernel, we write to the msgbox channel 2 register
 * at 0x03003000 + offset. The write value encodes the message type.
 *
 * @cpu: message type in stock HAL path (0=CALL,1=RETURN,2=CALL_ACK,3=RETURN_ACK)
 * @type: interrupt route/type (stock uses constant 2)
 * @value: payload value (unused in current path)
 */
void sunxi_cpu_comm_send_intr_to_mips(u32 cpu, u32 type, u32 value)
{
	u32 raw;

	if (!msgbox_ctrl_base) {
		pr_err("cpu_comm: msgbox not mapped, can't send intr!\n");
		return;
	}

	/*
	 * Stock HAL semantics recovered from IDA:
	 *   sunxi_cpu_comm_send_intr_to_mips(msg_type, intr_type, payload)
	 * Message format:
	 *   raw[31:16] = msg_type (0..3)
	 *   raw[15:0]  = direction/intr_type (stock: 2)
	 */
	raw = cpu & 0x3;	/* MIPS expects plain 0-3 comm_type */

	/* TX goes to MIPS base (0x400 offset) + 0x70 */
	writel(raw, msgbox_ctrl_base + H713_MSGBOX_TX_DATA);
	pr_info_ratelimited("cpu_comm: msgbox tx raw=0x%08x\n", raw);
}

/* ── Register mapping init/cleanup ─────────────────────────── */

int cpu_comm_hw_init(void)
{
	mips_ctrl_base = ioremap(MIPS_CTRL_BASE, 0x100);
	if (!mips_ctrl_base) {
		pr_err("cpu_comm: failed to map MIPS ctrl @ 0x%08x\n",
		       MIPS_CTRL_BASE);
		return -ENOMEM;
	}

	msgbox_ctrl_base = ioremap(0x03003000, 0x800);
	if (!msgbox_ctrl_base) {
		pr_err("cpu_comm: failed to map msgbox ctrl\n");
		iounmap(mips_ctrl_base);
		mips_ctrl_base = NULL;
		return -ENOMEM;
	}

	pr_info("cpu_comm: HW mapped — MIPS ctrl @ %p, msgbox @ %p\n",
		mips_ctrl_base, msgbox_ctrl_base);
	return 0;
}

void cpu_comm_hw_cleanup(void)
{
	int i;

	cpu_comm_msgbox_free_irq();

	for (i = 0; i < HW_SPINLOCK_COUNT; i++) {
		if (hwlocks[i]) {
			hwspin_lock_free(hwlocks[i]);
			hwlocks[i] = NULL;
		}
	}

	if (msgbox_ctrl_base) {
		iounmap(msgbox_ctrl_base);
		msgbox_ctrl_base = NULL;
	}
	if (mips_ctrl_base) {
		iounmap(mips_ctrl_base);
		mips_ctrl_base = NULL;
	}
}

/* ── CPU ID helpers ────────────────────────────────────────── */

u32 getCurCPUID(int dummy)
{
	return CPU_ID_ARM; /* we are always the ARM CPU */
}

const char *getCurCPUName(int dummy)
{
	return "ARM";
}

const char *getCPUIDName(u32 cpu_id)
{
	switch (cpu_id) {
	case CPU_ID_ARM:  return "ARM";
	case CPU_ID_MIPS: return "MIPS";
	default:          return "UNKNOWN";
	}
}

u32 CPUId2Index(u32 cpu_id)
{
	return cpu_id; /* identity mapping on H713 */
}
