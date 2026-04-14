// SPDX-License-Identifier: GPL-2.0
/*
 * cpu_comm_mem.c — Shared memory initialization and management
 *
 * Manages the 5MB shared memory region at 0x4E300000 that both
 * ARM and MIPS access for IPC. Handles:
 *  - Memory layout initialization (InitCommMem)
 *  - CPU status flags (ready/reset/app-ready)
 *  - Shared memory allocator (Trid_SMM — heap in shared memory)
 *  - Address translation (Physical ↔ Virtual ↔ MID)
 *
 * RE source: HAL_SX6/Kernel_Driver/cpu_comm/
 *   - comm_request.c (InitCommMem, InitCommSeqMem, CPU status)
 *   - trid_smm.c (SMM allocator)
 */

#include <linux/kernel.h>
#include <linux/io.h>
#include <linux/vmalloc.h>
#include <linux/mm.h>
#include <linux/slab.h>
#include <linux/delay.h>
#include <linux/sched.h>
#include "cpu_comm.h"

/* ── Globals ───────────────────────────────────────────────── */

u32 ShMemAddr;		/* physical base address */
u32 ShMemSize;		/* total size (5MB) */
u32 ShMemAddrVir;	/* kernel virtual (after vmap) */
u32 ShMemAddrBase;	/* uncacheable mapping base */
u32 ShMemAddr1;		/* secondary region physical (optional) */
u32 ShMemSize1;		/* secondary region size */

struct cpu_comm_dev *pcpu_comm_dev;

/* CommSocket array — 2 sockets × 1248 DWORDs */
u32 s_CommSockt[2 * (COMM_SOCKET_SIZE / 4)];

/* Call session ID counter */
u32 s_CallSessionId;

/* Memory init flag */
static int iniMemflag;

/*
 * MIPS APP_READY assumption.
 *
 * MIPS writes its flags through KSEG0 (L1 write-back cache) with no
 * coherency with ARM.  ARM reads physical memory via ioremap (uncached).
 * After init, MIPS READY (BIT(0)) IS visible in physical memory (written
 * during spinlock-protected init, sync'd by the HW spinlock release).
 * MIPS APP_READY (BIT(2)) is set by setCPUAppReady immediately after
 * READY in the same thread (thread_entry_sys_monitor), but without a
 * sync barrier, so it stays in MIPS L1 cache and never reaches physical.
 *
 * Once we see MIPS READY during init, we KNOW the MIPS will set
 * APP_READY within milliseconds (setCPUAppReady in display.bin).
 * This flag lets isCPUAppReady return true for MIPS without
 * reading the stale physical memory value.
 */
int mips_app_ready_assumed;

/* ── CPU status flags ──────────────────────────────────────── */

/*
 * CPU status flags live at ShMemAddrBase + 0x4CDC + 4*cpu_id
 * (= offset 19676 - 16 = 19660 decimal).
 *
 * Verified from MIPS display.bin IDA analysis:
 *   isCPUReady():  (cpu_id + 0x1336) * 4 + 4 = 0x4CDC + cpu_id*4
 *   IsCPUReset():  same offset, BIT(1)
 *
 * All flags share the same 32-bit word per CPU.
 *   Bit 0: ready (base comm layer initialized)
 *   Bit 1: not-ready / reset
 *   Bit 2: app-ready (full framework initialized)
 *   Bit 3: notice-requested
 */
#define CPU_FLAG_OFFSET(cpu)	(0x4CDC + 4 * (cpu))
#define CPU_FLAG_READY		BIT(0)
#define CPU_FLAG_NOT_READY	BIT(1)
#define CPU_FLAG_APP_READY	BIT(2)
#define CPU_FLAG_RESET		BIT(3)
#define CPU_FLAG_NOTICE_REQ	BIT(3)	/* same bit as RESET */

/*
 * setCPUReset — Put a CPU into reset state.
 *
 * From IDA @ 0x9e8. Two-phase reset:
 *
 * Phase 0 (phase == 0):
 *   Under spinlock 3, modifies the CPU flag word:
 *     - Clear READY (bit 0) and APP_READY (bit 2)
 *     - Set NOT_READY (bit 1)
 *     - Set NOTICE_REQ (bit 3) on BOTH CPU 0 and CPU 1 flag words
 *
 * Phase 1 (phase == 1):
 *   Runs the full cleanup chain:
 *     1. checkNoticeReqedJob() — drain pending notices
 *     2. comm_SpinLockCleanUpInCPUReset() — release stuck spinlocks
 *     3. Trid_SMMCleanUpInCPUReset() — reset SMM heaps
 *     4. RoutineCleanupInCPUReset() — unregister routines
 *     5. cleanupFDCPUReset() — cleanup FusionDale state
 *     6. InitCommShareSeqMem(0, cpu), InitCommShareSeqMem(cpu, 0)
 *        InitCommShareSeqMem(1, cpu), InitCommShareSeqMem(cpu, 1)
 *        — re-initialize all 4 share sequence directions
 *
 * Usage via IOCTL_SET_RESET (0x40047F22):
 *   val & 0xFFFF = cpu_id
 *   val >> 16 = phase (0 or 1)
 */
void setCPUReset(u32 cpu_id, unsigned int phase)
{
	u32 *flag;

	if (WARN_ON(!ShMemAddrBase || cpu_id > 1))
		return;
	if (*(u32 *)(ShMemAddrBase + SHMEM_OFF_MAGIC1) != CPU_COMM_MAGIC) {
		pr_err("cpu_comm: setCPUReset: magic1 not set!\n");
		return;
	}
	if (*(u32 *)(ShMemAddrBase + SHMEM_OFF_MAGIC2) != CPU_COMM_MAGIC) {
		pr_err("cpu_comm: setCPUReset: magic2 not set!\n");
		return;
	}

	if (phase == 0) {
		/* Phase 0: Set reset flags — stops the target CPU */
		comm_SpinLock(3);

		flag = (u32 *)(ShMemAddrBase + CPU_FLAG_OFFSET(cpu_id));

		/* Clear READY and APP_READY */
		*flag &= ~CPU_FLAG_READY;
		*flag &= ~CPU_FLAG_APP_READY;

		/* Set NOT_READY */
		*flag |= CPU_FLAG_NOT_READY;

		/* Set NOTICE_REQ on BOTH CPUs so each side knows a reset happened */
		*(u32 *)(ShMemAddrBase + CPU_FLAG_OFFSET(CPU_ID_ARM)) |=
			CPU_FLAG_NOTICE_REQ;
		*(u32 *)(ShMemAddrBase + CPU_FLAG_OFFSET(CPU_ID_MIPS)) |=
			CPU_FLAG_NOTICE_REQ;

		comm_SpinUnLock(3, 0);

		pr_info("cpu_comm: setCPUReset(%u) phase 0 — MIPS stopped, flags set\n", cpu_id);

	} else if (phase == 1) {
		/* Phase 1: Full cleanup chain — restarts the target CPU */
		pr_info("cpu_comm: setCPUReset(%u) phase 1 — cleanup chain, restarting MIPS\n",
			cpu_id);

		checkNoticeReqedJob();
		comm_SpinLockCleanUpInCPUReset(cpu_id);
		Trid_SMMCleanUpInCPUReset();
		RoutineCleanupInCPUReset((void *)(unsigned long)cpu_id);
		cleanupFDCPUReset(cpu_id);

		/* Re-initialize all 4 share sequence directions */
		InitCommShareSeqMem(CPU_ID_ARM, cpu_id);
		InitCommShareSeqMem(cpu_id, CPU_ID_ARM);
		InitCommShareSeqMem(CPU_ID_MIPS, cpu_id);
		InitCommShareSeqMem(cpu_id, CPU_ID_MIPS);

		pr_info("cpu_comm: setCPUReset(%u) phase 1 — done\n", cpu_id);
	}
}

void setCPUReady(u32 cpu_id)
{
	pr_debug("cpu_comm: setCPUReady(%u) enter\n", cpu_id);
	u32 *flag;

	if (WARN_ON(!ShMemAddrBase || cpu_id > 1))
		return;

	/* Verify magic markers */
	if (*(u32 *)(ShMemAddrBase + SHMEM_OFF_MAGIC1) != CPU_COMM_MAGIC ||
	    *(u32 *)(ShMemAddrBase + SHMEM_OFF_MAGIC2) != CPU_COMM_MAGIC) {
		pr_err("cpu_comm: setCPUReady but magic not set! Skipping.\n");
		return;
	}

	comm_SpinLock(3);
	flag = (u32 *)(ShMemAddrBase + CPU_FLAG_OFFSET(cpu_id));
	*flag |= CPU_FLAG_READY;
	*flag &= ~CPU_FLAG_NOT_READY;
	*flag &= ~CPU_FLAG_RESET;
	*flag &= ~CPU_FLAG_NOTICE_REQ;
	comm_SpinUnLock(3, 0);
}

void setCPUnotReady(u32 cpu_id)
{
	u32 *flag;

	if (WARN_ON(!ShMemAddrBase || cpu_id > 1))
		return;

	comm_SpinLock(3);
	flag = (u32 *)(ShMemAddrBase + CPU_FLAG_OFFSET(cpu_id));
	*flag |= CPU_FLAG_NOT_READY;
	*flag &= ~CPU_FLAG_READY;
	comm_SpinUnLock(3, 0);
}

int isCPUReady(u32 cpu_id)
{
	u32 *flag;

	if (cpu_id > 1 || !ShMemAddrBase)
		return 0;

	if (*(u32 *)(ShMemAddrBase + SHMEM_OFF_MAGIC1) != CPU_COMM_MAGIC ||
	    *(u32 *)(ShMemAddrBase + SHMEM_OFF_MAGIC2) != CPU_COMM_MAGIC)
		return 0;

	flag = (u32 *)(ShMemAddrBase + CPU_FLAG_OFFSET(cpu_id));
	return (*flag & CPU_FLAG_READY) ? 1 : 0;
}

int IsCPUReset(u32 cpu_id)
{
	u32 *flag;

	if (cpu_id > 1 || !ShMemAddrBase)
		return 0;

	flag = (u32 *)(ShMemAddrBase + CPU_FLAG_OFFSET(cpu_id));
	return (*flag & CPU_FLAG_RESET) ? 1 : 0;
}

int IsCurCPURest(void)
{
	return IsCPUReset(getCurCPUID(0));
}

/* ── setCPUAppReady / isCPUAppReady ────────────────────────── */

/*
 * App-ready indicates the full IPC framework is initialized (not just
 * base shared memory). Stored as BIT(2) in the SAME flag word as
 * ready/not-ready/reset at CPU_FLAG_OFFSET(cpu).
 *
 * From IDA @ 0x4f28: sets BIT(2), then waits for the OTHER CPU's
 * BIT(2) to also be set. On ARM side (cpu=0), the wait checks offset
 * 19676 which is our own flag — exits immediately since we just set it.
 * The MIPS side would wait for ARM's flag. So for ARM this is effectively
 * just "set our flag and return".
 */
void setCPUAppReady(u32 cpu_id)
{
	u32 *flag;
	u32 *other_flag;

	if (WARN_ON(!ShMemAddrBase || cpu_id > 1))
		return;

	/* Verify magic markers — graceful error handling */
	if (*(u32 *)(ShMemAddrBase + SHMEM_OFF_MAGIC1) != CPU_COMM_MAGIC) {
		pr_err("cpu_comm: setCPUAppReady: magic1 not set! Skipping APP_READY.\n");
		return;
	}
	if (*(u32 *)(ShMemAddrBase + SHMEM_OFF_MAGIC2) != CPU_COMM_MAGIC) {
		pr_err("cpu_comm: setCPUAppReady: magic2 not set! Skipping APP_READY.\n");
		return;
	}
	if (!isCPUReady(cpu_id)) {
		pr_err("cpu_comm: setCPUAppReady: CPU %s not ready! Skipping APP_READY.\n",
		       getCPUIDName(cpu_id));
		return;
	}
	if (IsCPUReset(cpu_id)) {
		pr_err("cpu_comm: setCPUAppReady: CPU %s in reset! Skipping APP_READY.\n",
		       getCPUIDName(cpu_id));
		return;
	}

	pr_debug("cpu_comm: setCPUAppReady(%u) — acquiring spinlock 3\n", cpu_id);

	/* Set BIT(2) = APP_READY on our CPU's flag word */
	comm_SpinLock(3);

	pr_debug("cpu_comm: setCPUAppReady(%u) — spinlock 3 acquired, setting flag\n", cpu_id);

	flag = (u32 *)(ShMemAddrBase + CPU_FLAG_OFFSET(cpu_id));
	*flag |= CPU_FLAG_APP_READY;
	comm_SpinUnLock(3, 0);

	pr_debug("cpu_comm: setCPUAppReady(%u) — flag set to 0x%x, checking other CPU\n",
		cpu_id, *flag);

	/*
	 * Wait for the other CPU to also become app-ready — with TIMEOUT.
	 * Stock had an infinite loop here. MIPS firmware may never set APP_READY
	 * (known issue: MIPS setCPUAppReady fails on magic checks after memset_io).
	 * ARM must not block forever waiting for MIPS.
	 */
	other_flag = (u32 *)(ShMemAddrBase + CPU_FLAG_OFFSET(cpu_id ^ 1));

	pr_debug("cpu_comm: setCPUAppReady(%u) — other_flag @ %px = 0x%x\n",
		cpu_id, other_flag, *other_flag);

	{
		int timeout_ms = 2000;  /* 2 second timeout */
		while (!(*other_flag & CPU_FLAG_APP_READY) && timeout_ms > 0) {
			msleep(10);
			timeout_ms -= 10;
		}
		if (!(*other_flag & CPU_FLAG_APP_READY)) {
			/*
			 * MIPS firmware never sets APP_READY on its own flag (0x4CE0).
			 * Stock display.bin writes READY/NOT_READY to 0x4CDC (ARM flag!)
			 * but never sets BIT(2) on 0x4CE0. This is stock behavior.
			 * Set it from ARM side so IPC paths that check isCPUAppReady work.
			 */
			pr_warn("cpu_comm: setCPUAppReady(%u) — MIPS APP_READY timeout (flag=0x%x). "
				"Setting MIPS APP_READY from ARM side.\n",
				cpu_id, *other_flag);
			comm_SpinLock(3);
			*other_flag |= CPU_FLAG_APP_READY;
			comm_SpinUnLock(3, 0);
			pr_info("cpu_comm: MIPS APP_READY force-set from ARM (flag now=0x%x)\n",
				*other_flag);
		}
	}

	pr_info("cpu_comm: CPU %s app ready\n", getCPUIDName(cpu_id));
}

/*
 * isCPUAppReady — Check if a CPU's application layer is ready.
 *
 * From IDA @ 0x4ae0:
 *   cpu_id 0 or 1: checks magic + BIT(2) at CPU_FLAG_OFFSET(cpu_id)
 *   cpu_id 2: checks if ALL CPUs are app-ready (recursive)
 */
int isCPUAppReady(u32 cpu_id)
{
	u32 *flag;

	if (cpu_id > 2) {
		pr_err("cpu_comm: isCPUAppReady: invalid cpu %u\n", cpu_id);
		return 0;
	}

	/* cpu_id == 2: check all CPUs */
	if (cpu_id == 2) {
		u32 max_cpu = *(u32 *)(ShMemAddrBase + SHMEM_OFF_MAX_CPU);
		int result = 1;

		if ((max_cpu & 1) && !isCPUAppReady(CPU_ID_ARM))
			result = 0;
		if ((max_cpu & 2) && !isCPUAppReady(CPU_ID_MIPS))
			result = 0;
		return result;
	}

	/* Normal check for cpu 0 or 1 */
	if (!ShMemAddrBase)
		return 0;
	if (*(u32 *)(ShMemAddrBase + SHMEM_OFF_MAGIC1) != CPU_COMM_MAGIC)
		return 0;
	if (*(u32 *)(ShMemAddrBase + SHMEM_OFF_MAGIC2) != CPU_COMM_MAGIC)
		return 0;

	flag = (u32 *)(ShMemAddrBase + CPU_FLAG_OFFSET(cpu_id));
	if (!(*flag & CPU_FLAG_APP_READY)) {
		/*
		 * MIPS cache workaround: MIPS sets APP_READY in L1 cache
		 * but it never flushes to physical memory.  If we've seen
		 * MIPS READY during init, trust that APP_READY is set.
		 */
		if (cpu_id == CPU_ID_MIPS && mips_app_ready_assumed) {
			pr_debug("cpu_comm: MIPS app-ready assumed (phys flags=0x%x)\n",
				 *flag);
			return 1;
		}
		pr_debug("cpu_comm: CPU %s app not ready (flags=0x%x)\n",
			 getCPUIDName(cpu_id), *flag);
		return 0;
	}

	return 1;
}

/* ── Notice/Request flags ──────────────────────────────────── */

/*
 * isCPUNoticeReqed — Check if a CPU has a pending notice request.
 *
 * From IDA @ 0x4a4c: reads BIT(3) at CPU_FLAG_OFFSET(cpu_id).
 * BIT(3) is shared with RESET — a reset IS a notice request.
 * When ShMemAddrBase is not set, returns 1 (conservatively assume notice needed).
 */
int isCPUNoticeReqed(u32 cpu_id)
{
	u32 *flag;

	if (WARN_ON(cpu_id > 1))
		return 1;

	if (!ShMemAddrBase)
		return 1;

	flag = (u32 *)(ShMemAddrBase + CPU_FLAG_OFFSET(cpu_id));
	return (*flag & CPU_FLAG_NOTICE_REQ) ? 1 : 0;
}

/*
 * clearCPUNoticeReqed — Clear the notice-requested flag for current CPU.
 *
 * From IDA @ 0x4690: clears BIT(3) at CPU_FLAG_OFFSET(getCurCPUID())
 * with spinlock 3 held. Validates magic markers.
 */
void clearCPUNoticeReqed(u32 cpu_id)
{
	u32 cur_cpu;

	if (WARN_ON(!ShMemAddrBase))
		return;

	if (*(u32 *)(ShMemAddrBase + SHMEM_OFF_MAGIC1) != CPU_COMM_MAGIC ||
	    *(u32 *)(ShMemAddrBase + SHMEM_OFF_MAGIC2) != CPU_COMM_MAGIC) {
		pr_err("cpu_comm: clearCPUNoticeReqed: magic not set! Skipping.\n");
		return;
	}

	comm_SpinLock(3);
	cur_cpu = getCurCPUID(0);
	*(u32 *)(ShMemAddrBase + CPU_FLAG_OFFSET(cur_cpu)) &= ~CPU_FLAG_NOTICE_REQ;
	comm_SpinUnLock(3, 0);
}

/*
 * checkNoticeReqedJob — Handle pending notice requests from reset CPUs.
 *
 * From IDA @ 0x4d8c: For each remote CPU, if that CPU is in reset state,
 * signal pending waiters and clean up. This is called during init to
 * synchronize after one CPU resets while the other was waiting.
 *
 * The stock implementation is quite complex (semaphore polling with
 * jiffies timeout). For our use case (ARM-only, MIPS runs independently),
 * we simplify to just checking and clearing the flags.
 */
void checkNoticeReqedJob(void)
{
	u32 cur_cpu;
	u32 other_cpu;

	if (WARN_ON(!ShMemAddrBase))
		return;

	comm_SpinLock(3);
	cur_cpu = getCurCPUID(0);

	/* Check each remote CPU */
	for (other_cpu = 0; other_cpu < CPU_ID_MAX; other_cpu++) {
		if (other_cpu == cur_cpu)
			continue;

		if (IsCPUReset(other_cpu)) {
			pr_info("cpu_comm: CPU %s is in reset, handling notice\n",
				getCPUIDName(other_cpu));
			/*
			 * Stock does complex semaphore polling with 500-jiffies
			 * timeout to drain pending waiters. For initial bring-up,
			 * we just note the state. Full cleanup will be added when
			 * MIPS reset handling is needed.
			 */
		}
	}

	comm_SpinUnLock(3, 0);
	clearCPUNoticeReqed(0);
}

/* ── Address translation ───────────────────────────────────── */

/*
 * Three address spaces:
 *   Physical (Phy): Hardware bus address (e.g., 0x4E300000)
 *   Virtual (Vir):  Kernel VA (after vmap, uncacheable)
 *   MID:            MIPS Internal — on H713, same as physical
 *
 * Conversion: Vir = Phy + (ShMemAddrVir - ShMemAddr)
 *             Phy = Vir - (ShMemAddrVir - ShMemAddr)
 *             MID = Phy (on H713)
 */

u32 Mid2Phy(u32 cpu, u32 mid)
{
	return mid; /* identity on H713 */
}

u32 Phy2Mid(u32 phy)
{
	return phy;
}

u32 Mid2Vir(u32 cpu, u32 mid)
{
	u32 phy = Mid2Phy(cpu, mid);

	if (!phy || !ShMemAddrBase || !ShMemAddr)
		return 0;

	return phy + (ShMemAddrBase - ShMemAddr);
}

u32 Vir2Mid(u32 cpu, u32 vir)
{
	u32 phy;

	if (!vir || !ShMemAddrBase || !ShMemAddr)
		return 0;

	phy = vir - (ShMemAddrBase - ShMemAddr);
	return Phy2Mid(phy);
}

/* ── Sequence helpers ──────────────────────────────────────── */

u32 getSeq(u32 cpu_id)
{
	if (WARN_ON(cpu_id > 1))
		return 0;
	return (u32)&s_CommSockt[cpu_id * (COMM_SOCKET_SIZE / 4)];
}

/*
 * getShareSeq — Get a shared sequence structure for a CPU pair + direction
 *
 * From IDA (0x3e3c): return ShMemAddrBase + 9760*a1 + 4880*a2 + 2440*a3 + 152
 *
 * Layout in shared memory:
 *   Offset 152 + 9760*local + 4880*remote + 2440*dir
 *   Each entry is 2440 bytes (share sequence with embedded FIFOs + call slots)
 *   2 CPUs × 2 remotes × 2 directions = 8 entries
 */
u32 getShareSeq(u32 cpu, u32 remote, u32 dir)
{
	if (WARN_ON(!ShMemAddrBase || cpu > 1 || remote > 1 || dir > 1))
		return 0;

	return ShMemAddrBase + 9760 * cpu + 4880 * remote + 2440 * dir + 152;
}

/*
 * getShareSeqR — Get read sequence (messages FROM remote TO us)
 * "R" = we Read what remote sent. Local = getCurCPUID(), remote = cpu arg.
 */
u32 getShareSeqR(u32 cpu, u32 dir)
{
	return getShareSeq(getCurCPUID(0), cpu, dir);
}

/*
 * getShareSeqW — Get write sequence (messages FROM us TO remote)
 * "W" = we Write to remote. Local = cpu arg, remote = getCurCPUID().
 */
u32 getShareSeqW(u32 cpu, u32 dir)
{
	return getShareSeq(cpu, getCurCPUID(0), dir);
}

/* ── InitCommSeqMem — Per-CPU socket initialization ────────── */

/*
 * interSeq2Name — Generate a name string for this socket.
 *
 * From IDA: generates "CPU0" or "CPU1" based on the cpu_id stored
 * at sock[0].  Returns a pointer to a static buffer (single-CPU
 * use only; callers pass it immediately to InitMsgFIFO).
 */
static const char *interSeq2Name(u32 *sock)
{
	static char buf[16];

	snprintf(buf, sizeof(buf), "CPU%u", sock[0]);
	return buf;
}

/*
 * InitCommSeqMem — Initialize the per-CPU CommSocket in s_CommSockt[].
 *
 * Faithful port of IDA decompilation @ 0x51cc.
 *
 * CommSocket layout (s_CommSockt[1248 * cpu_id], each 1248 DWORDs = 4992 bytes):
 *
 *   [0]         cpu_id
 *   [1]         pad
 *   [2]         status = 0
 *   [3]         sem_count = 1
 *   [4..5]      self-ref list pair  (head = tail = &sock[4])
 *   [6..7]      0
 *   [8..9]      self-ref list pair  (head = tail = &sock[8])
 *   [10..29]    (gap — covered by subsequent writes at sock[30..])
 *   [30]        0
 *   [31]        1
 *   [32..33]    self-ref list pair  (head = tail = &sock[32])
 *   [34..41]    FreeWait comm_fifo  (rd, wr, peak, sem=1, cap=21, item=4, base, rsv)
 *   [42..49]    FreeWait name: "FreeWait" padded to 32 bytes
 *   [50]        0
 *   [51]        pad
 *   [52..71]    FreeWait ring buffer (21 × 4 bytes, mmioset to 0)
 *   [72..231]   20 wait entries, 8 DWORDs each (32 bytes), stride 8:
 *                     entry[0]   = type/pad
 *                     entry[1]   = SESSION_ID_INVALID (session_id)
 *                     entry[2]   = 0 (status)
 *                     entry[3..4] = 0 (v11-4, v11-3)
 *                     entry[5..6] = self-ref pair (v11-2, v11-1)
 *                     entry[7]   = self-ref (v11, list_head.next)
 *                     (+next entry[0] = list_head.prev, v11+1)
 *                   FreeWait FIFO pre-filled with &entry[1] per entry
 *   [37]        0  (clear sem after FIFO fill)
 *
 *   [234]       0
 *   [235]       1
 *   [236..237]  self-ref pair (&sock[236])
 *   [238..]     CallCmd ring buffer (mmioset to 0)
 *   [259]       0
 *   [260]       1
 *   [261..262]  self-ref pair (&sock[261])
 *   [263..264]  0
 *   [265..266]  self-ref pair (&sock[265])
 *   [267..286]  InitMsgFIFO → " ReturnList"
 *   [287]       0
 *   [288]       1
 *   [289..290]  self-ref pair (&sock[289])
 *
 *   SendCmdWaitList MsgFIFO at &sock[40]:
 *     [40..59]  msg_fifo struct (name=interSeq2Name+" SendCmdWaitList", mode=1)
 */
void InitCommSeqMem(u32 cpu_id)
{
	u32 *sock;
	u32 v2;		/* sock base index in s_CommSockt */
	int i;
	u32 *share_seq_r;

	if (WARN_ON(cpu_id > 1))
		return;

	v2 = cpu_id * (COMM_SOCKET_SIZE / 4);	/* 1248 * cpu_id */
	sock = &s_CommSockt[v2];

	/* ── Basic socket fields ── */
	sock[0] = cpu_id;
	/*
	 * sem at offset 8 (sock[2]): local send semaphore.
	 * MIPS binary uses seq_base+8 for local sem_ptr.
	 * Must be 1 to allow first sem_down to succeed.
	 */
	sock[2] = 1;		/* local send sem count = 1 */
	sock[3] = 1;		/* sem_count */

	/* Self-referencing linked list 0 at sock[4] */
	sock[4] = (u32)&sock[4];
	sock[5] = (u32)&sock[4];
	sock[6] = 0;
	sock[7] = 0;

	/* Self-referencing linked list 1 at sock[8] */
	sock[8] = (u32)&sock[8];
	sock[9] = (u32)&sock[8];

	/* ── SendCmdWaitList MsgFIFO at &sock[10] (= byte offset 40) ── */
	InitMsgFIFO(&sock[10], interSeq2Name(sock), " SendCmdWaitList", 1);

	/* ── Fields around the send FIFO ── */
	sock[30] = 0;
	sock[31] = 1;		/* sem = 1 */

	/* Self-referencing list at sock[32] */
	sock[32] = (u32)&sock[32];
	sock[33] = (u32)&sock[32];

	/* ── FreeWait FIFO at sock[34] ──
	 *
	 * Layout of the 8-DWORD comm_fifo (compact form):
	 *   [34] rd_idx   = 0
	 *   [35] wr_idx   = 0
	 *   [36] peak     = 0
	 *   [37] sem/track= 1  (set to 0 after pre-filling)
	 *   [38] capacity = 21
	 *   [39] item_size= 4
	 *   [40] base_addr= (u32)&sock[52]  (FreeWait ring buffer)
	 *   [41] reserved = 0
	 *
	 * Name at sock[42] (= byte offset 168): "FreeWait", 32 bytes
	 * sock[50] = 0
	 * Ring buffer at sock[52] (= byte offset 208): mmioset to 0, 21×4=84 bytes
	 */
	sock[34] = 0;		/* rd_idx */
	sock[35] = 0;		/* wr_idx */
	sock[36] = 0;		/* peak_count */
	sock[37] = 1;		/* track_stats/sem = 1 during init */
	sock[38] = 21;		/* capacity */
	sock[39] = 4;		/* item_size */
	sock[40] = (u32)&sock[52];	/* base_addr = ring buffer start */
	sock[41] = 0;

	strncpy((char *)&sock[42], "FreeWait", 32);
	sock[50] = 0;

	/* Zero-fill the ring buffer (21 slots × 4 bytes = 84 bytes) */
	memset_io(&sock[52], 0, 21 * 4);

	/* ── Pre-fill FreeWait FIFO with pointers to wait entries ──
	 *
	 * 20 wait entries, each 8 DWORDs (32 bytes), starting at sock[72].
	 * Entry i layout (base = &sock[72 + 8*i]):
	 *   [+0]  type/pad
	 *   [+1]  session_id = SESSION_ID_INVALID  ← "wait object" pointer
	 *   [+2]  status = 0
	 *   [+3]  = 0  (v11-4)
	 *   [+4]  = 0  (v11-3)
	 *   [+5]  self-ref (v11-2)
	 *   [+6]  self-ref (v11-1)
	 *   [+7]  v11 = list_head.next (self-ref)
	 *
	 * v11 = &sock[79 + 8*i]  (7 DWORDs into entry = entry[7])
	 * Item pushed into FIFO = v11 - 6 = &sock[73 + 8*i] = &entry[1]
	 *   (This is the "wait object" = pointer to session_id field)
	 */
	for (i = 0; i < MAX_WAIT_ENTRIES; i++) {
		u32 *entry = &sock[72 + 8 * i];	/* 8 DWORDs per entry (32 bytes) */
		u32 *v11 = &sock[79 + 8 * i];		/* list_head anchor (entry[7]) */
		u32 *item_wr;

		/* Wait entry fields */
		entry[1] = (u32)SESSION_ID_INVALID;	/* session_id = -1 */
		entry[2] = 0;				/* status */
		entry[3] = 0;
		entry[4] = 0;

		/* List nodes: v11-4, v11-3 = 0; v11-2, v11-1 = self-ref; */
		/* v11, v11+1 = self-ref */
		*(v11 - 4) = 0;
		*(v11 - 3) = 0;
		*(v11 - 2) = (u32)(v11 - 2);	/* self-ref */
		*(v11 - 1) = (u32)(v11 - 2);	/* self-ref */
		*v11       = (u32)v11;		/* self-ref */
		*(v11 + 1) = (u32)v11;		/* self-ref */

		/* Write "wait object pointer" into the FreeWait FIFO.
		 * The wait object starts 6 DWORDs before v11 = entry[1].
		 */
		item_wr = (u32 *)fifo_getItemWr(&sock[34]);
		if (!item_wr) {
			pr_err("cpu_comm: InitCommSeqMem: FreeWait FIFO full at entry %d\n",
			       i);
			break;
		}
		*item_wr = (u32)(v11 - 6);	/* = &entry[1] */
		fifo_requestItemWr(&sock[34]);
	}

	/* Clear sem — FIFO pre-fill complete */
	sock[37] = 0;

	/* ── Additional list/semaphore fields ── */
	sock[234] = 0;
	sock[235] = 1;		/* sem = 1 */

	/* Self-referencing list at sock[236] (= byte offset 944) */
	sock[236] = (u32)&sock[236];
	sock[237] = (u32)&sock[236];

	/* ── CallCmd ring buffer at sock[238] (= byte offset 952) ──
	 * Capacity = 21 slots × 4 bytes; mmioset to 0.
	 * The share_seq FIFO for direction 0 will point its base here.
	 */
	memset_io(&sock[238], 0, 21 * 4);

	/*
	 * Remote send semaphore at offset 0x3E0 (992) = sock[248].
	 * MIPS binary (0x8B11FEEC): sem_ptr = seq_base + 0x3E0 for remote.
	 * MIPS getSeq stride is 1168 bytes (not 4992).
	 * This falls in the ring buffer area, but must be 1 for IPC to work.
	 */
	sock[248] = 1;		/* remote send sem count = 1 */
	pr_info("cpu_comm: InitCommSeqMem(%u): sock[248]=0x%x (remote sem @ offset 0x3E0)\n",
		cpu_id, sock[248]);

	sock[259] = 0;
	sock[260] = 1;		/* sem = 1 */

	/* Self-referencing pair at sock[261] */
	sock[261] = (u32)&sock[261];
	sock[262] = (u32)&sock[261];

	sock[263] = 0;
	sock[264] = 0;

	/* Self-referencing pair at sock[265] */
	sock[265] = (u32)&sock[265];
	sock[266] = (u32)&sock[265];

	/* ── ReturnList MsgFIFO at &sock[267] ── */
	InitMsgFIFO(&sock[267], interSeq2Name(sock), " ReturnList", 1);

	sock[287] = 0;
	sock[288] = 1;		/* sem = 1 */

	/* Self-referencing pair at sock[289] */
	sock[289] = (u32)&sock[289];
	sock[290] = (u32)&sock[289];

	/* ── Share sequence R CallCmd/ReturnCmd FIFO setup ──
	 *
	 * IDA @ 0x51cc: The CallCmd staging FIFO lives at ShareSeqR + 32
	 * (byte offset from the share_seq structure in shared memory).
	 * Its ring buffer is in the LOCAL socket at sock[238] (virtual).
	 * This is SEPARATE from the FreeCall FIFO at +120 (set up by
	 * InitCommShareSeqMem with physical addresses).
	 *
	 * FIFO header at ShareSeqR + 32:
	 *   +32: rd_idx=0, +36: wr_idx=0, +40: peak=0, +44: sem=1,
	 *   +48: capacity=21, +52: item_size=4,
	 *   +56: base_addr = VIRTUAL addr of sock ring buffer,
	 *   +60: reserved=0
	 * Name at +64: "CallCmd" (32 bytes)
	 * Reserved at +96: 0
	 */
	share_seq_r = (u32 *)getShareSeqR(cpu_id, 0);
	if (share_seq_r) {
		u32 *fifo = (u32 *)((u8 *)share_seq_r + 32);

		memset_io(&sock[238], 0, 21 * 4);

		fifo[0] = 0;		/* rd_idx */
		fifo[1] = 0;		/* wr_idx */
		fifo[2] = 0;		/* peak_count */
		fifo[3] = 1;		/* sem/track = 1 */
		fifo[4] = 21;		/* capacity */
		fifo[5] = 4;		/* item_size */
		fifo[6] = (u32)&sock[238];	/* base_addr = VIRTUAL */
		fifo[7] = 0;

		strncpy((char *)share_seq_r + 64, "CallCmd", 32);
		*(u32 *)((u8 *)share_seq_r + 96) = 0;
	}

	/*
	 * ShareSeqR direction 1 (return): same layout at +32.
	 * Ring buffer at sock[291], name "ReturnCmd".
	 */
	{
		u32 *share_seq_r1 = (u32 *)getShareSeqR(cpu_id, 1);

		if (share_seq_r1) {
			u32 *fifo1 = (u32 *)((u8 *)share_seq_r1 + 32);

			memset_io(&sock[291], 0, 21 * 4);

			fifo1[0] = 0;
			fifo1[1] = 0;
			fifo1[2] = 0;
			fifo1[3] = 1;
			fifo1[4] = 21;
			fifo1[5] = 4;
			fifo1[6] = (u32)&sock[291];	/* VIRTUAL */
			fifo1[7] = 0;

			strncpy((char *)share_seq_r1 + 64, "ReturnCmd", 32);
			*(u32 *)((u8 *)share_seq_r1 + 96) = 0;
		}
	}

	pr_debug("cpu_comm: InitCommSeqMem(%u) done\n", cpu_id);
}

/* ── InitCommShareSeqMem — Shared sequence structures ──────── */

/*
 * InitCommShareSeqMem — Initialize shared sequence structures.
 *
 * From IDA @ 0x4120. For each sub-direction (i=0: FreeCall, i=1: FreeReturn):
 *  - Initializes the comm_share_seq header
 *  - Sets up an embedded comm_fifo at offset 120 (capacity=21, item_size=4)
 *  - Pre-fills the FIFO with physical pointers to 20 call entries (104 bytes each)
 *  - Call entries start at share_seq + 360 (0x168)
 *
 * Layout within each share_seq (2440 bytes):
 *   +0x00:  header (local_cpu, remote_cpu, direction, status, max_items, session_id)
 *   +0x68:  second header block (max_items2, status2, session_id2)
 *   +0x78:  FIFO struct (rd, wr, peak, sem, capacity=21, item_size=4, base_addr)
 *   +0x98:  name string (32 bytes: "FreeCall" or "FreeReturn")
 *   +0xB8:  reserved
 *   +0xC0:  FIFO buffer (21 × 4 bytes = 84 bytes of physical pointers)
 *   +0x168: call entries (20 × 104 bytes, each with session_id=-1 at +12)
 */
void InitCommShareSeqMem(u32 cpu_id, u32 direction)
{
	int i;
	const char *name;

	if (WARN_ON(!ShMemAddrBase)) {
		pr_err("cpu_comm: InitCommShareSeqMem: ShMemAddrBase not set!\n");
		return;
	}
	if (WARN_ON(cpu_id > 1 || direction > 1))
		return;

	for (i = 0; i < 2; i++) {
		u32 seq = getShareSeq(cpu_id, direction, i);
		u8 *s = (u8 *)seq;
		u32 *fifo;
		u32 buf_vir;	/* virtual address of FIFO buffer */
		u32 buf_phy;	/* physical address of FIFO buffer */
		u32 entry_base;	/* virtual address of first call entry */
		int j;

		if (!seq)
			continue;

		/* Initialize header fields */
		s[0] = (u8)cpu_id;	/* local_cpu */
		s[1] = (u8)direction;	/* remote_cpu */
		s[2] = (u8)i;		/* direction: 0=call, 1=return */
		s[8] = 0;		/* status */
		s[16] = 20;		/* max_items */
		*(u32 *)(s + 20) = SESSION_ID_INVALID;	/* session_id = -1 */
		s[104] = 20;		/* max_items2 */
		s[105] = 0;		/* status2 */
		*(u32 *)(s + 108) = SESSION_ID_INVALID;	/* session_id2 = -1 */

		/* Zero the FIFO buffer area at offset 0xC0 */
		buf_vir = seq + 192;
		if (buf_vir) {
			buf_phy = buf_vir - ShMemAddrBase + ShMemAddr;
			if (buf_phy) {
				u32 tmp_vir = buf_phy + ShMemAddrBase - ShMemAddr;
				if (tmp_vir)
					memset_io((void *)tmp_vir, 0,
						  21 * 4); /* 21 slots × 4 bytes */
			}
		}

		/* Set up embedded FIFO struct at offset 120 (0x78) */
		fifo = (u32 *)(seq + 120);
		fifo[0] = 0;		/* rd_idx */
		fifo[1] = 0;		/* wr_idx */
		fifo[2] = 0;		/* peak_count */
		fifo[3] = 1;		/* sem / track_stats — cleared to 0 after init */
		fifo[4] = 21;		/* capacity (1 wasted → 20 usable) */
		fifo[5] = 4;		/* item_size (4 bytes per slot = physical pointer) */

		/* base_addr = physical address of buffer at offset 0xC0 */
		buf_phy = (buf_vir) ? buf_vir - ShMemAddrBase + ShMemAddr : 0;
		fifo[6] = buf_phy;

		fifo[7] = 0;		/* reserved */

		/* Name at offset 152 (0x98) from share_seq */
		name = (i == 0) ? "FreeCall" : "FreeReturn";
		strncpy((char *)(seq + 152), name, 32);

		/* Clear field_b8 */
		*(u32 *)(seq + 184) = 0;

		/*
		 * Verify that FIFO has a valid write slot before filling.
		 * fifo_getItemWr returns the physical address of the first slot.
		 */
		if (!fifo_getItemWr(fifo)) {
			pr_err("cpu_comm: InitCommShareSeqMem: FIFO not ready!\n");
			return;
		}

		/*
		 * Pre-fill the FIFO with physical pointers to 20 call entries.
		 * Each call entry is 104 bytes starting at share_seq + 360 (0x168).
		 */
		entry_base = seq + 360;

		for (j = 0; j < 20; j++) {
			u32 entry_vir = entry_base + j * COMM_MSG_SIZE;
			u32 entry_phy;
			u32 wr_slot_phy;
			u32 *wr_slot_vir;

			/* Set slot index (u16 at call_entry + 4) */
			*(u16 *)(entry_vir + 4) = (u16)j;

			/* Set session_id = -1 (u32 at call_entry + 12) */
			*(u32 *)(entry_vir + 12) = SESSION_ID_INVALID;

			/* Get current write slot from FIFO */
			wr_slot_phy = fifo_getItemWr(fifo);
			if (!wr_slot_phy) {
				pr_err("cpu_comm: InitCommShareSeqMem: FIFO full at entry %d!\n", j);
				break;
			}

			/* Convert write slot to virtual, write entry's physical addr */
			wr_slot_vir = (u32 *)(wr_slot_phy + ShMemAddrBase - ShMemAddr);
			entry_phy = entry_vir ? entry_vir - ShMemAddrBase + ShMemAddr : 0;
			*wr_slot_vir = entry_phy;

			/* Commit the write */
			fifo_requestItemWr(fifo);
		}

		/* Clear sem (track_stats) — init is complete */
		fifo[3] = 0;
	}

	pr_debug("cpu_comm: InitCommShareSeqMem(%u, %u) done\n",
		 cpu_id, direction);
}

/* ── Component/Messager pools ──────────────────────────────── */

void InitComponentPool(void *pool_ptr)
{
	u32 *pool = pool_ptr;
	int i, j;

	if (WARN_ON(!pool))
		return;

	memset_io(pool, 0, COMPONENT_COUNT * 816 + 16);

	/* Max components */
	pool[8162 / 4] = COMPONENT_COUNT;

	/* Request a spinlock for the pool */
	pool[0] = comm_ReqestSpinLock();
	if (pool[0] == 255) {
		pr_err("cpu_comm: failed to get spinlock for component pool\n");
		return;
	}

	/* Initialize each component */
	for (i = 0; i < COMPONENT_COUNT; i++) {
		u32 *comp = &pool[i * (816 / 4) + 4]; /* skip header */
		u8 *comp_bytes = (u8 *)comp;

		comp_bytes[10 - 16] = i;	/* index */
		comp[8 / 4] = 255;		/* spinlock_id = unassigned */
		*((u16 *)(comp_bytes + 0x1C - 16)) = 2; /* state = 2 */

		/* Sub-entries: set sentinel values */
		for (j = 0; j < 192; j += 12) {
			comp[(j + 18) * 4 / 4] = SESSION_ID_INVALID;
		}
	}
}

void InitMessagerPool(void *pool_ptr)
{
	u32 *pool = pool_ptr;

	if (WARN_ON(!pool))
		return;

	memset_io(pool, 0, 3208);
	pool[0] = 0;	/* count */
	pool[1] = comm_ReqestSpinLock();
	if (pool[1] == 255) {
		pr_err("cpu_comm: failed to get spinlock for messager pool\n");
		return;
	}
}

/* ── Shared Memory Manager (Trid_SMM) ─────────────────────── */

/*
 * Address translation helpers for SMM.
 * All pointers stored in the heap (page table, free lists) are physical
 * addresses.  Access requires conversion to kernel virtual.
 */
static inline u32 smm_phy2vir(u32 phy)
{
	if (!phy)
		return 0;
	return phy + ShMemAddrBase - ShMemAddr;
}

static inline u32 smm_vir2phy(u32 vir)
{
	if (!vir)
		return 0;
	return vir - ShMemAddrBase + ShMemAddr;
}

/*
 * __shmalloc_brk — sbrk-like break extension for the SMM heap.
 *
 * @heap: pointer to heap header (virtual address)
 * @a2:   bytes to extend (0 = query current break)
 *
 * Returns virtual address of the old break position, or 0 if a2 == 0
 * and the break equals the physical base.
 *
 * IDA RE @ 0xa184.
 */
static int __shmalloc_brk(u32 *heap, int a2)
{
	int new_break;
	int cur_break_phys;

	if (a2) {
		new_break = a2 + (int)heap[45];
		if (new_break > (int)heap[46]) {
			pr_err("cpu_comm: SMM out of memory (brk)\n");
			return 0;
		}
		heap[45] = (u32)new_break;
	}

	cur_break_phys = (int)(heap[47] + heap[45]);
	if (cur_break_phys != a2)
		return (int)(ShMemAddrBase - ShMemAddr) + cur_break_phys - a2;
	return 0;
}

/*
 * morecore — Allocate page-aligned memory from the heap break.
 *
 * @heap: heap header (virtual)
 * @a2:   bytes needed (must be a multiple of 4096 for large allocs)
 *
 * Returns virtual address of the newly allocated region, or 0 on failure.
 *
 * IDA RE @ 0xa280.
 */
static int morecore(u32 *heap, int a2)
{
	int ptr;
	int waste;
	int page_table_vir;
	int end;
	int needed_pages;

	ptr = __shmalloc_brk(heap, a2);
	if (ptr & 0xFFF) {
		waste = 4096 - (ptr & 0xFFF);
		ptr += waste;
		__shmalloc_brk(heap, waste);
	}

	if (ptr) {
		/* page_table_vir = virtual address of page table base */
		if (heap[0])
			page_table_vir = (int)heap[0] + (int)ShMemAddrBase - (int)ShMemAddr;
		else
			page_table_vir = 0;

		end = ptr + a2;
		needed_pages = (end - page_table_vir) / 4096 + 1;
		if (needed_pages > (int)heap[2]) {
			pr_err("cpu_comm: SMM page table overflow\n");
			return 0;
		}

		/* Update page_table_vir after potential null-correction */
		if (heap[0])
			page_table_vir = (int)heap[0] + (int)ShMemAddrBase - (int)ShMemAddr;
		else
			page_table_vir = 0;

		heap[4] = (u32)((end - page_table_vir) / 4096 + 1);
	}

	return ptr;
}

/*
 * __shmalloc — Core SMM buddy allocator.
 *
 * @heap: heap header (virtual address)
 * @size: requested allocation size in bytes
 *
 * Returns virtual address of the allocated block, or 0 on failure.
 *
 * Size <= 7:   rounded up to 8
 * Size 8..2048: power-of-2 free lists (buddy system)
 * Size > 2048:  page-granularity allocation
 *
 * Each free block header: [next_free_phys, prev_free_phys] (2 × u32)
 * Page table entries: 12 bytes each = [field0, field1, field2]
 *
 * IDA RE @ 0xa3b8.
 */
static int __shmalloc(u32 *heap, unsigned int size)
{
	int page_table_vir;	/* virtual address of page table base */
	unsigned int i;
	u32 *free_list_slot;
	int free_head_phy;
	u32 *free_head_vir;
	unsigned int v_tmp;
	int page_alloc;

	if (!size)
		return 0;

	/* page_table_vir = virt(heap[1]) */
	page_table_vir = (int)heap[1];
	if (page_table_vir)
		page_table_vir = page_table_vir + (int)ShMemAddrBase - (int)ShMemAddr;

	/* Round up small sizes */
	if (size <= 7)
		size = 8;

	/* ── Large allocation path (> 2048 bytes) ── */
	if (size > 0x800) {
		unsigned int pages_needed = (size + 4095) >> 12;
		int search_page = (int)heap[3];	/* current free-page search start */
		int cur_page;
		u32 *pte;
		unsigned int free_count;
		int result;
		int data_base_vir;
		int brk_vir;
		int last_free_page;
		int last_free_count;
		int extra_pages;
		int extra_bytes;

		cur_page = search_page;

		/* Walk the free page list looking for a run of pages_needed pages */
		while (1) {
			do {
				pte = (u32 *)(page_table_vir + 12 * cur_page);
				free_count = pte[0];
				if (pages_needed <= free_count) {
					/* Found a block big enough */
					data_base_vir = (int)heap[0];
					if (data_base_vir)
						data_base_vir = data_base_vir +
							(int)ShMemAddrBase - (int)ShMemAddr;

					/*
					 * PTE index → virtual address:
					 * IDA: data_base + ((pte_idx + 0xFFFFF) << 12)
					 * In 32-bit: 0xFFFFF << 12 = -4096, so = (pte_idx - 1) * 4096
					 * PTE index 1 = first data page at data_base + 0.
					 */
					result = data_base_vir + (cur_page - 1) * 4096;

					if (pages_needed >= free_count) {
						/* Consume the whole free block */
						*(u32 *)(page_table_vir + 12 * pte[1] + 8) = pte[2];
						*(u32 *)(page_table_vir + 12 * pte[2] + 4) = pte[1];
						heap[3] = pte[1];
						--heap[43];
					} else {
						/* Split: leave the tail as a smaller free block */
						int split_page = cur_page + pages_needed;
						u32 *split_pte = (u32 *)(page_table_vir + 12 * split_page);

						split_pte[0] = free_count - pages_needed;
						split_pte[1] = pte[1];
						split_pte[2] = pte[2];
						heap[3] = split_page;
						*(u32 *)(page_table_vir + 12 * pte[1] + 8) = split_page;
						*(u32 *)(page_table_vir + 12 * pte[2] + 4) = split_page;
					}

					/* Mark page table entry as allocated */
					pte[0] = 0;
					pte[1] = pages_needed;
					heap[41]++;
					heap[42] += pages_needed << 12;
					heap[44] -= pages_needed << 12;
					return result;
				}
				cur_page = (int)pte[1];
			} while (search_page != cur_page);

			/*
			 * No suitable free block found — try extending the last
			 * free block if it is adjacent to the current break.
			 */
			last_free_page = *(u32 *)(page_table_vir + 8);	/* sentinel next */
			last_free_count = *(u32 *)(page_table_vir + 12 * last_free_page);

			if (!heap[4])
				break;

			if (heap[4] != last_free_page + last_free_count)
				break;

			brk_vir = __shmalloc_brk(heap, 0);
			data_base_vir = (int)heap[0];
			if (data_base_vir)
				data_base_vir = data_base_vir +
					(int)ShMemAddrBase - (int)ShMemAddr;

			if (brk_vir != data_base_vir +
			    (last_free_page - 1) * 4096)
				break;

			extra_pages = (int)pages_needed - last_free_count;
			extra_bytes = extra_pages << 12;
			if (!morecore(heap, extra_bytes))
				break;

			/* Update the last free block's page count */
			cur_page = *(u32 *)(page_table_vir + 8);
			*(u32 *)(page_table_vir + 12 * cur_page) += extra_pages;
			heap[44] += extra_bytes;
		}

		/* Fall back to pure morecore */
		page_alloc = morecore(heap, pages_needed << 12);
		if (!page_alloc) {
			pr_err("cpu_comm: SMM large alloc failed (pages=%u)\n", pages_needed);
			return 0;
		}

		/* Find page index of the new allocation */
		{
			int data_base_v = (int)heap[0];

			if (data_base_v)
				data_base_v = data_base_v +
					(int)ShMemAddrBase - (int)ShMemAddr;

			pte = (u32 *)(page_table_vir + 12 *
				((page_alloc - data_base_v) / 4096) + 12);
			pte[0] = 0;
			pte[1] = pages_needed;
		}
		heap[41]++;
		heap[42] += pages_needed << 12;
		return page_alloc;
	}

	/* ── Small allocation path (8..2048 bytes) ── */

	/* Compute size class: i = ceil(log2(size)) */
	v_tmp = size - 1;
	for (i = 1; v_tmp; ++i)
		v_tmp >>= 1;

	/* free_list_slot = &heap[2*i] — points at the per-class header */
	free_list_slot = &heap[2 * i];

	/* free_head_phy = heap[2*i + 17] = free list head physical address */
	free_head_phy = (int)free_list_slot[17];

	if (free_head_phy &&
	    (free_head_vir = (u32 *)(free_head_phy +
				     (int)ShMemAddrBase - (int)ShMemAddr)) != 0) {
		/*
		 * Validate pointer: must be 4-byte aligned and within heap bounds.
		 * If invalid, raise SIGSEGV (stock behaviour) — we use WARN+return.
		 */
		u32 heap_data_base = heap[47];
		u32 heap_data_base_vir = heap_data_base ?
			heap_data_base + ShMemAddrBase - ShMemAddr : 0;

		if ((u32)free_head_vir <= heap_data_base_vir ||
		    (u32)free_head_vir >= heap_data_base_vir + heap[46]) {
			/* Out of bounds */
			WARN(1, "cpu_comm: SMM free list head out of bounds (class=%u ptr=0x%x)\n",
			     i, (u32)free_head_vir);
			return 0;
		}
		if ((u32)free_head_vir & 3) {
			WARN(1, "cpu_comm: SMM free list head misaligned (class=%u ptr=0x%x)\n",
			     i, (u32)free_head_vir);
			return 0;
		}

		/* Validate prev pointer (free_head_vir[1]) */
		{
			u32 prev_phy = free_head_vir[1];
			u32 prev_vir;

			if (heap_data_base >= prev_phy ||
			    prev_phy >= heap_data_base + heap[46]) {
				WARN(1, "cpu_comm: SMM free list prev out of bounds\n");
				return 0;
			}
			if (prev_phy & 3) {
				WARN(1, "cpu_comm: SMM free list prev misaligned\n");
				return 0;
			}

			/* Unlink from free list: next->prev = prev */
			prev_vir = prev_phy + ShMemAddrBase - ShMemAddr;
			{
				u32 next_phy = free_head_vir[0];
				u32 *next_vir = next_phy ?
					(u32 *)(next_phy + ShMemAddrBase - ShMemAddr) : NULL;

				if (next_vir) {
					/* Validate next pointer too */
					if ((u32)next_vir <= heap_data_base_vir ||
					    (u32)next_vir >= heap_data_base_vir + heap[46] ||
					    ((u32)next_vir & 3)) {
						WARN(1, "cpu_comm: SMM free list next invalid\n");
						return 0;
					}
					next_vir[1] = prev_phy;
				}

				/* prev->next = next */
				if (prev_vir) {
					u32 *pv = (u32 *)prev_vir;

					pv[0] = next_phy;
				}
			}

			/* Update page table entry: decrement alloc_count for this page */
			{
				int data_base_v = (int)heap[0];

				if (data_base_v)
					data_base_v = data_base_v +
						(int)ShMemAddrBase - (int)ShMemAddr;

				{
					u32 page_idx = ((u32)free_head_vir - data_base_v +
							4095) >> 12;
					u32 *page_pte = (u32 *)(page_table_vir +
								12 * page_idx + 12);

					if (--page_pte[1] == 0) {
						/* Last block in page freed back to sub-index */
						page_pte[2] = (free_head_vir[0] & 0xFFF) >> i;
					}
				}
			}

			heap[41]++;
			heap[42] += 1u << i;
			--heap[43];
			heap[44] -= 1u << i;
		}
	} else {
		/* Free list empty — allocate a whole page and carve it up */
		u32 page_vir = (u32)__shmalloc(heap, 4096);

		if (page_vir) {
			unsigned int sub_count = 4096 >> i;
			u32 j;
			u32 *pte;
			u32 data_base_v;

			++heap[i + 5];	/* pages split for this class */

			/* Chain sub-blocks j=1..sub_count-1 into the free list */
			for (j = 1; j < sub_count; ++j) {
				u32 block_vir = page_vir + (j << i);
				u32 *block = (u32 *)block_vir;
				int list_head_phys;

				/* next = current list head */
				block[0] = free_list_slot[17];

				/*
				 * prev = physical address of &free_list_slot[17]
				 * (the free list head pointer itself, so old head
				 * can update the list head via prev->next)
				 */
				list_head_phys = (int)&free_list_slot[17] +
					(int)ShMemAddr - (int)ShMemAddrBase;

				block[1] = list_head_phys;

				/* list head = physical(block) */
				free_list_slot[17] = block_vir ?
					block_vir + ShMemAddr - ShMemAddrBase : 0;

				/* Update old head's prev */
				{
					u32 old_head_phy = block[0];

					if (old_head_phy) {
						u32 *old_head_vir = (u32 *)(old_head_phy +
							ShMemAddrBase - ShMemAddr);
						u32 block_phys = block_vir ?
							block_vir + ShMemAddr - ShMemAddrBase : 0;

						old_head_vir[1] = block_phys;
					}
				}
			}

			/* Fill in page table entry for this page */
			{
				data_base_v = (int)heap[0];
				if (data_base_v)
					data_base_v = data_base_v +
						(int)ShMemAddrBase - (int)ShMemAddr;

				pte = (u32 *)(page_table_vir +
					12 * ((int)(page_vir - data_base_v) / 4096) + 12);
				pte[0] = i;		/* size class */
				pte[1] = sub_count - 1;	/* alloc_count */
				pte[2] = sub_count - 1;	/* sub_block_offset */
			}

			/* Correct heap stats: __shmalloc above consumed 4096 bytes;
			 * we're actually giving one block to the caller
			 */
			{
				u32 block_bytes = 1u << i;

				heap[43] = heap[43] - 1 + sub_count;
				heap[42] = heap[42] - 4096 + block_bytes;
				heap[44] = heap[44] + 4096 - block_bytes;
			}
		} else {
			pr_err("cpu_comm: SMM small alloc failed (class=%u)\n", i);
		}
		return (int)page_vir;
	}

	return (int)free_head_vir;
}

/*
 * smmMalloc — Entry point for SMM allocations.
 *
 * @slot: heap slot index (0 or 1), or -1 for auto-select via @attr flags
 * @size: requested size in bytes
 * @attr: attribute flags when slot == -1
 *        bit 0: use slot 1 (MID memory)
 *        bit 2 + bit 1: must both be set for valid auto-select
 *
 * Returns virtual address of the allocated block, or 0 on failure.
 *
 * IDA RE @ 0xab2c.
 */
static int smmMalloc(int slot, unsigned int size, unsigned char attr)
{
	int effective_slot;
	u64 *slot_entry;
	u32 *heap;
	unsigned int alloc_size;
	int result;

	effective_slot = slot;

	if (slot < 0) {
		/* Auto-select slot from attr flags */
		if (attr & 1) {
			effective_slot = 1;
		} else {
			if (!(attr & 4)) {
				pr_err("cpu_comm: smmMalloc: invalid attr 0x%x (missing bit2)\n",
				       attr);
				return 0;
			}
			if (!(attr & 2)) {
				pr_err("cpu_comm: smmMalloc: invalid attr 0x%x (missing bit1)\n",
				       attr);
				return 0;
			}
			effective_slot = 0;
		}
	} else if (slot > 1) {
		pr_err("cpu_comm: smmMalloc: invalid slot %d\n", slot);
		return 0;
	}

	comm_SpinLock(1);

	result = 0;
	slot_entry = (u64 *)(ShMemAddrBase + 72 * effective_slot + 19696);

	if (*slot_entry) {
		/*
		 * Slot 1 (MID memory) always uses page-granularity allocation:
		 * if size <= 2048 and slot is odd, pass 2049 so __shmalloc
		 * takes the large (page-aligned) path.
		 */
		if (size <= 0x800 && (effective_slot & 1))
			alloc_size = 2049;
		else
			alloc_size = size;

		heap = (u32 *)((u32)*slot_entry - ShMemAddr + ShMemAddrBase);
		result = __shmalloc(heap, alloc_size);

		if (result) {
			/* Update per-CPU stats at offset 28672 + 4*cpu */
			u32 cpu_id = getCurCPUID(0);
			u32 *stats = (u32 *)(ShMemAddrBase + 4 * cpu_id + 28672);

			stats[1432 / 4] += size;
			++*(u32 *)(ShMemAddrBase + 4 * cpu_id + 30112);
		}
	} else {
		pr_warn("cpu_comm: smmMalloc: heap slot %d not initialized\n",
			effective_slot);
	}

	comm_SpinUnLock(1, 0);

	/*
	 * __shmalloc returns a kernel-virtual address (ShMemAddrBase-based).
	 * Convert to physical/mid before returning — callers expect mid.
	 */
	if (result)
		result = result - ShMemAddrBase + ShMemAddr;

	return result;
}

int Trid_SMM_Init(u32 base, u32 size)
{
	u32 *heap;
	u32 page_count;

	comm_SpinLock(1);

	/* Page-align base */
	base = (base + 4095) & ~4095UL;
	heap = (u32 *)base;
	page_count = (size + 4095) >> 12;

	/* Initialize heap header */
	memset_io(heap, 0, 4096);

	/*
	 * heap[0] and heap[1] store the PHYSICAL address of the page table.
	 * The page table starts 4096 bytes (1024 u32s) after the heap header.
	 * All pointers in the heap header are PHYSICAL for SharedMem compat.
	 * __shmalloc later converts phy→vir when accessing them.
	 *
	 * BUG-17 fix: previously stored virtual address → double-conversion
	 * in __shmalloc → crash on any allocation attempt.
	 */
	{
		u32 pt_vir = (u32)(heap + 1024);  /* page table virtual */
		u32 pt_phy = pt_vir - ShMemAddrBase + ShMemAddr; /* to physical */

		heap[0] = pt_phy;	/* free_list_head = page_table physical */
		heap[1] = pt_phy;	/* free_list_cur */
	}
	heap[2] = page_count;

	/*
	 * From IDA @ 0xb220:
	 *   heap[0xB4/4] = ((12 * page_count + 4095) & ~0xFFF) + 4096
	 *     → data_start_offset: size of header(4096) + page_table(page-aligned)
	 *     This is the fixed offset from heap base to where allocatable data begins.
	 *     __shmalloc_brk uses this as the initial break position.
	 *
	 *   heap[0xB8/4] = size (raw capacity passed to Trid_SMM_Init)
	 *
	 *   heap[0xBC/4] = heap_phy (physical address of the heap header itself)
	 *     __shmalloc_brk computes: data_addr = phy_base + brk_offset
	 */
	{
		u32 pt_size_aligned = (12 * page_count + 4095) & ~4095UL;
		u32 data_start = pt_size_aligned + 4096; /* header(4096) + page_table */
		u32 heap_phy = (u32)heap - ShMemAddrBase + ShMemAddr;

		heap[0xB4 / 4] = data_start;	/* data_start_offset (NOT brk, NOT capacity) */
		heap[0xB8 / 4] = size;		/* raw capacity */
		heap[0xBC / 4] = heap_phy;	/* physical base of heap header */
	}

	/* Mark the region in shared memory header.
	 * The slot area at ShMemAddrBase + 19712 stores the PHYSICAL
	 * address of the heap, not the virtual. MIPS also reads this.
	 */
	{
		u32 *shmem = (u32 *)ShMemAddrBase;
		u32 slot = 0; /* first heap slot */
		u32 heap_phy = (u32)heap - ShMemAddrBase + ShMemAddr;

		/*
		 * IDA: v17[2462] = heap_phy where v17 = &ShMemAddrBase[9*slot]
		 * = ShMemAddrBase + 9*8*slot = +72*slot (as u64 array)
		 * v17[2462] = ShMemAddrBase + 72*slot + 2462*8 = +72*slot + 19696
		 * NOT 19712! Previous code was off by 16 bytes.
		 */
		/*
		 * IDA: v17[2462] = heap_phy → offset 2462*8 = 19696 (as _QWORD*)
		 *      *((_DWORD*)v17 + 4926) = size → offset 4926*4 = 19704
		 * Base is at 19696 (8 bytes: u64), Size at 19704 (4 bytes: u32)
		 */
		*(u64 *)(((u8 *)shmem) + 19696 + 72 * slot) = (u64)heap_phy;
		*(u32 *)(((u8 *)shmem) + 19704 + 72 * slot) = size;
	}

	comm_SpinUnLock(1, 0);

	pr_info("cpu_comm: SMM heap initialized: base=0x%x size=%u pages=%u\n",
		base, size, page_count);
	return 0;
}

u32 Trid_SMM_Malloc(u32 size)
{
	return (u32)smmMalloc(0, size, 0);
}

u32 Trid_SMM_MallocAttr(u32 size)
{
	/*
	 * Stock calls smmMalloc(-1, size, attr) with attr = the attribute byte.
	 * For MallocAttr we don't have a separate attr argument in this wrapper,
	 * so use slot 0 like Trid_SMM_Malloc.  If a caller needs MID/slot-1
	 * memory it should call smmMalloc(-1, size, attr) directly.
	 */
	return (u32)smmMalloc(0, size, 0);
}

/*
 * Trid_SMM_Free — Free a block previously allocated by Trid_SMM_Malloc.
 *
 * @mid_addr: physical (MID) address of the block to free
 *
 * Determines which heap slot owns the address, then:
 *  - For small blocks (size_class > 0): re-inserts into the per-class free
 *    list and coalesces if the whole page is now free.
 *  - For large blocks (size_class == 0): merges adjacent free page spans.
 *
 * IDA RE @ 0xb3b8.
 */
int Trid_SMM_Free(u32 mid_addr)
{
	u32 phy_addr;
	int slot;
	u64 slot_base;
	u32 slot_size;
	u64 *slot_entry;
	u32 *heap;
	int page_table_vir;
	int data_base_vir;
	u32 page_idx;
	u32 *pte;		/* page table entry for addr's page */
	u32 size_class;
	u32 alloc_count_or_pages;
	u32 vaddr;		/* virtual address of the block */

	phy_addr = Mid2Phy(0, mid_addr);
	if (!phy_addr)
		return 0;

	/* ── Find which heap slot owns this address ── */
	slot_base = *(u64 *)(ShMemAddrBase + 19696);	/* slot 0: [base, base+size] */
	slot_size = *(u32 *)(ShMemAddrBase + 19704);
	if (phy_addr >= (u32)slot_base && phy_addr < (u32)slot_base + slot_size) {
		slot = 0;
	} else {
		u64 slot1_base = *(u64 *)(ShMemAddrBase + 19768);
		u32 slot1_size = *(u32 *)(ShMemAddrBase + 19776);

		if (phy_addr < (u32)slot1_base ||
		    phy_addr >= (u32)slot1_base + slot1_size) {
			pr_err("cpu_comm: Trid_SMM_Free(0x%x): address not in any heap\n",
			       mid_addr);
			return -EINVAL;
		}
		slot = 1;
	}

	comm_SpinLock(1);

	slot_entry = (u64 *)(ShMemAddrBase + 72 * slot + 19696);
	if (!*slot_entry) {
		pr_warn("cpu_comm: Trid_SMM_Free: heap slot %d not initialized\n", slot);
		goto out_unlock;
	}

	heap = (u32 *)((u32)*slot_entry - ShMemAddr + ShMemAddrBase);

	page_table_vir = (int)heap[1];
	if (page_table_vir)
		page_table_vir = page_table_vir + (int)ShMemAddrBase - (int)ShMemAddr;

	data_base_vir = (int)heap[0];
	if (data_base_vir)
		data_base_vir = data_base_vir + (int)ShMemAddrBase - (int)ShMemAddr;

	vaddr = phy_addr + ShMemAddrBase - ShMemAddr;

	--heap[41];	/* decrement allocation counter */

	/*
	 * Compute page index.  The page table starts at index 0 = sentinel;
	 * real pages start at index 1.  So page_idx = (addr - data_base) / 4096
	 * and pte = &page_table[(page_idx + 1) * 3].
	 */
	page_idx = (vaddr - (u32)data_base_vir) / 4096;
	pte = (u32 *)(page_table_vir + 12 * (page_idx + 1));

	size_class = pte[0];
	alloc_count_or_pages = pte[1];

restart_free:
	if (size_class == 0) {
		/*
		 * Large page allocation.
		 * pte[1] = page count of this allocation.
		 * We find the right position in the free-page doubly-linked
		 * list (sorted by page index) and insert/merge.
		 */
		u32 pages = alloc_count_or_pages;
		u32 cur_search = heap[3];	/* search start (current hint) */
		u32 prev_page, next_page;
		u32 prev_pte_count, next_pte_count;
		u32 merged_page;

		/* Update stats */
		heap[42] -= pages << 12;
		heap[44] += pages << 12;

		/*
		 * Walk the free list to find insertion point.
		 * The list is sorted by ascending page index.
		 */
		if (page_idx + 1 >= cur_search) {
			/* Walk forward to find where page_idx+1 fits */
			do {
				cur_search = *(u32 *)(page_table_vir + 12 * cur_search + 4);
				if (!cur_search)
					break;
			} while (page_idx + 1 > cur_search);
			prev_page = *(u32 *)(page_table_vir + 12 * cur_search + 8);
		} else {
			/* Walk backward */
			do {
				cur_search = *(u32 *)(page_table_vir + 12 * cur_search + 8);
			} while (page_idx + 1 < cur_search);
			prev_page = *(u32 *)(page_table_vir + 12 * cur_search + 8);
			cur_search = *(u32 *)(page_table_vir + 12 * prev_page + 4);
			/* re-derive */
			prev_page = cur_search;
			cur_search = prev_page;
		}

		/*
		 * At this point cur_search is the first free page with index
		 * >= page_idx+1, and the previous free page is just before it.
		 * Try to merge backwards with prev.
		 */
		prev_page = *(u32 *)(page_table_vir + 12 * cur_search + 4);
		prev_pte_count = *(u32 *)(page_table_vir + 12 * prev_page);

		if (page_idx + 1 == prev_page + prev_pte_count) {
			/* Merge with previous free block */
			merged_page = prev_page;
			*(u32 *)(page_table_vir + 12 * prev_page) =
				prev_pte_count + pages;
		} else {
			/* Insert as new free block after prev */
			pte[0] = pages;
			pte[1] = *(u32 *)(page_table_vir + 12 * prev_page + 4);
			pte[2] = prev_page;
			*(u32 *)(page_table_vir + 12 * prev_page + 4) = page_idx + 1;
			*(u32 *)(page_table_vir + 12 *
				 *(u32 *)(page_table_vir + 12 * prev_page + 4 + 4) + 8) =
					page_idx + 1;
			++heap[43];
			merged_page = page_idx + 1;
		}

		/* Try to merge forward with cur_search */
		{
			u32 *mp = (u32 *)(page_table_vir + 12 * merged_page);

			if (merged_page + mp[0] == cur_search) {
				next_pte_count = *(u32 *)(page_table_vir + 12 * cur_search);
				mp[0] += next_pte_count;
				next_page = *(u32 *)(page_table_vir + 12 * cur_search + 4);
				mp[1] = next_page;
				*(u32 *)(page_table_vir + 12 * next_page + 8) = merged_page;
				--heap[43];
			}
		}

		/* Shrink break if tail pages are free */
		{
			u32 *mp = (u32 *)(page_table_vir + 12 * merged_page);

			if (mp[0] > 7 && merged_page + mp[0] == heap[4]) {
				int brk_vir = __shmalloc_brk(heap, 0);
				int db = (int)heap[0];

				if (db)
					db = db + (int)ShMemAddrBase - (int)ShMemAddr;

				if (brk_vir == db + (merged_page - 1) * 4096 +
				    (int)(mp[0] << 12)) {
					heap[4] -= mp[0];
					__shmalloc_brk(heap, -(int)(mp[0] << 12));
					/* Unlink from free list */
					*(u32 *)(page_table_vir + 12 * mp[2] + 4) = mp[1];
					*(u32 *)(page_table_vir + 12 * mp[1] + 8) = mp[2];
					--heap[43];
					heap[44] -= mp[0] << 12;
				}
			}
		}

		heap[3] = merged_page;

	} else {
		/*
		 * Small block (size_class > 0).
		 * pte[1] = alloc_count (number of allocated blocks in this page)
		 * pte[2] = sub_block_index hint
		 *
		 * The block header at vaddr[0] = next_free_phy, vaddr[1] = prev_free_phy.
		 * We insert at the head of the per-class free list.
		 */
		u32 *free_list_slot = &heap[2 * size_class];
		u32 heap_data_base = heap[47];
		u32 heap_data_base_vir = heap_data_base ?
			heap_data_base + ShMemAddrBase - ShMemAddr : 0;

		/* Validate vaddr */
		if (vaddr <= heap_data_base_vir ||
		    vaddr >= heap_data_base_vir + heap[46] ||
		    (vaddr & 3)) {
			WARN(1, "cpu_comm: SMM_Free: bad vaddr 0x%x\n", vaddr);
			goto out_unlock;
		}

		/* Update stats */
		heap[42] -= 1u << size_class;
		heap[44] += 1u << size_class;
		++heap[43];

		if (alloc_count_or_pages == (4096u >> size_class) - 1) {
			/*
			 * This is the LAST allocated block being freed — the whole
			 * page is now free.  Walk the free list to remove all
			 * sub-blocks of this page, then release the page back to
			 * the large allocator.
			 */
			u32 sub_count = 4096u >> size_class;
			u32 i;
			u32 page_base_vir = vaddr & ~0xFFFu;
			u32 cur_block;

			if (free_list_slot[5] > 1) {
				--free_list_slot[5];	/* pages split for this class */

				/* Walk free list removing all blocks from this page */
				for (i = 1, cur_block = (u32)free_list_slot[17];
				     i < sub_count && cur_block;
				     ++i) {
					u32 cur_vir;

					if (!cur_block)
						break;
					cur_vir = cur_block + ShMemAddrBase - ShMemAddr;

					/* Bounds/alignment check */
					if (cur_vir <= heap_data_base_vir ||
					    cur_vir >= heap_data_base_vir + heap[46] ||
					    (cur_vir & 3)) {
						WARN(1, "cpu_comm: SMM_Free: corrupt free list\n");
						goto out_unlock;
					}

					if ((cur_vir & ~0xFFFu) == page_base_vir) {
						/* This block is in our page — unlink it */
						u32 *blk = (u32 *)cur_vir;
						u32 next_phy = blk[0];
						u32 prev_phy = blk[1];
						u32 next_vir2 = next_phy ?
							next_phy + ShMemAddrBase - ShMemAddr : 0;
						u32 prev_vir2 = prev_phy ?
							prev_phy + ShMemAddrBase - ShMemAddr : 0;

						if (next_vir2)
							*(u32 *)(next_vir2 + 4) = prev_phy;
						if (prev_vir2)
							*(u32 *)prev_vir2 = next_phy;
						else
							free_list_slot[17] = next_phy;

						cur_block = next_phy;
					} else {
						cur_block = *(u32 *)(cur_vir);
					}
				}

				/* Also remove the block being freed itself if still in list */
				/* Now free the page */
				--heap[43];
				heap[43] -= sub_count - 1;
				heap[42] += 4096 - (1u << size_class);
				heap[44] -= 4096 - (1u << size_class);

				/* Convert page to a "1-page large allocation" and free it */
				page_idx = (page_base_vir - (u32)data_base_vir) / 4096;
				pte = (u32 *)(page_table_vir + 12 * (page_idx + 1));
				pte[0] = 0;
				pte[1] = 1;
				size_class = 0;
				alloc_count_or_pages = 1;
				vaddr = page_base_vir;
				++heap[41];		/* undo the -- at top */
				goto restart_free;
			}
			/* only 1 page of this class: just add to free list normally */
		}

		/* Normal case: insert block at head of free list */
		{
			u32 *blk = (u32 *)vaddr;
			u32 old_head_phy = free_list_slot[17];	/* physical */
			u32 list_head_phys;

			/* prev = physical address of &free_list_slot[17] */
			list_head_phys = (u32)&free_list_slot[17] +
				ShMemAddr - ShMemAddrBase;

			blk[0] = old_head_phy;
			blk[1] = list_head_phys;

			/* Update old head's prev to point to us */
			if (old_head_phy) {
				u32 old_head_vir = old_head_phy + ShMemAddrBase - ShMemAddr;

				if (old_head_vir > heap_data_base_vir &&
				    old_head_vir < heap_data_base_vir + heap[46] &&
				    !(old_head_vir & 3)) {
					*(u32 *)(old_head_vir + 4) =
						vaddr + ShMemAddr - ShMemAddrBase;
				}
			}

			/* list head = physical(vaddr) */
			free_list_slot[17] = vaddr ? vaddr + ShMemAddr - ShMemAddrBase : 0;

			/* Update alloc_count in page table */
			++pte[1];
			pte[2] = (u32)(*(u32 *)vaddr & 0xFFF) >> size_class;
		}
	}

out_unlock:
	comm_SpinUnLock(1, 0);
	return 0;
}

/*
 * Trid_SMMCleanUpInCPUReset — Reset the SMM heaps after a CPU reset.
 *
 * From IDA setCPUReset @ 0x9e8: called as part of the CPU reset sequence
 * (a2 == 1). Resets the heap state so the other CPU can re-initialize.
 *
 * For our use case (ARM never resets while MIPS runs), this is a no-op
 * during normal operation. During development it may be called if MIPS
 * is rebooted while ARM is running.
 */
void Trid_SMMCleanUpInCPUReset(void)
{
	/* Reset not needed for initial bring-up.
	 * Full implementation would re-initialize the SMM heaps
	 * via Trid_SMM_Init() for the reset CPU's heap slot.
	 */
	pr_info("cpu_comm: Trid_SMMCleanUpInCPUReset called (no-op)\n");
}

/* ── InitCommMem — Main shared memory initialization ───────── */

int InitCommMem(int mode)
{
	u32 base = ShMemAddrBase;
	u32 *shmem;
	int i;

	if (WARN_ON(!base))
		return -EINVAL;

	shmem = (u32 *)base;

	/* ARM is CPU 0 — we initialize the shared memory.
	 * Stock: ALWAYS full init on every boot (mmioset + InitCommMem).
	 * MIPS display.bin re-initializes after seeing ARM READY + Magic.
	 */
	if (getCurCPUID(0) == CPU_ID_ARM) {
		int hwret;

		/* Initialize HW spinlock handles FIRST — before any lock access */
		hwret = comm_InitHwSpinLock();
		if (hwret) {
			pr_err("cpu_comm: InitCommMem: comm_InitHwSpinLock failed: %d\n", hwret);
			return hwret;
		}

		/* Acquire HW lock 0 for init exclusion */
		shmem[SHMEM_OFF_MAGIC1 / 4] = CPU_COMM_MAGIC;
		tryspinlockhwReg(0);

		/* Initialize software spinlock layer in SharedMem */
		comm_InitSpinLock(0);

		if (mode != 2) {
			/* Full init: clear call entries area */
			memset_io((void *)(base + SHMEM_OFF_CALL_ENTRIES), 0,
				  CALL_ENTRIES_TOTAL);

			/* Set all session IDs to -1 */
			for (i = 0; i < CALL_ENTRIES_TOTAL; i += CALL_ENTRY_SIZE)
				*(u32 *)(base + SHMEM_OFF_CALL_ENTRIES + i + 100) =
					SESSION_ID_INVALID;
		}

		/* Clear magic temporarily during setup */
		memset_io((void *)(base + SHMEM_OFF_MAGIC1), 0, 4);

		/* Set max CPU count */
		shmem[SHMEM_OFF_MAX_CPU / 4] = 3;

		/* Initialize ALL sockets */
		InitCommSeqMem(CPU_ID_ARM);
		InitCommShareSeqMem(CPU_ID_ARM, 0);
		InitCommShareSeqMem(CPU_ID_ARM, 1);
		InitCommSeqMem(CPU_ID_MIPS);
		InitCommShareSeqMem(CPU_ID_MIPS, 0);
		InitCommShareSeqMem(CPU_ID_MIPS, 1);

		/* Clear SMM heap marker */
		*(u64 *)(base + SHMEM_OFF_SMM_HEAP) = 0;

		/* Initialize pools */
		InitComponentPool((void *)(base + SHMEM_OFF_COMP_POOL));
		InitMessagerPool((void *)(base + SHMEM_OFF_MSG_POOL));

		/* Set VA offset for address translation */
		shmem[SHMEM_OFF_VA_OFFSET / 4] = ShMemAddrVir - ShMemAddr;
		shmem[(SHMEM_OFF_VA_OFFSET + 4) / 4] = 0;

		/* Initialize linked lists (self-referencing) */
		for (i = SHMEM_OFF_LIST_BASE; i < SHMEM_OFF_LIST_BASE + 160;
		     i += 8) {
			shmem[i / 4] = base + i;
			shmem[i / 4 + 1] = base + i;
		}

		/* Init routing table before setting magics */
		{
			int ri;
			u32 *ver = (u32 *)(ShMemAddrBase + 30144);
			u32 *cnt = (u32 *)(ShMemAddrBase + 30148);
			u8  *tbl = (u8 *)(ShMemAddrBase + 30152);
			*ver = 0;
			*cnt = 0;
			for (ri = 0; ri < 1224; ri++) {
				*(u32 *)(tbl + 96 * ri + 8) = 0;
				*(int *)(tbl + 96 * ri + 92) = -1;
			}
			pr_info("cpu_comm: routine table initialized (1224 slots)\n");
		}

		/* Set magic markers — shared memory is now valid */
		shmem[SHMEM_OFF_MAGIC1 / 4] = CPU_COMM_MAGIC;
		shmem[SHMEM_OFF_MAGIC2 / 4] = CPU_COMM_MAGIC;

		/* Initialize SMM heap in remaining space */
		Trid_SMM_Init(base + SHMEM_OFF_SMM_HEAP,
			      base + ShMemSize - 1 -
			      (base + SHMEM_OFF_SMM_HEAP));

		/* Optional: secondary memory region */
		if (ShMemSize1) {
			if (!ShMemAddr1)
				ShMemAddr1 = ShMemAddr + ShMemSize;
			if (ShMemAddr1)
				Trid_SMM_Init(
					ShMemAddr1 + ShMemAddrBase -
					ShMemAddr, ShMemSize1);
		}

		/* Set spinlock type and mark ARM as ready + app-ready */
		comm_SpinLocksetType(2, 1);
		setCPUReady(CPU_ID_ARM);

		/*
		 * CRITICAL: Set APP_READY BEFORE releasing HW spinlock 0.
		 * MIPS (slave) acquires this spinlock and reads ARM flag
		 * into its L1 cache. MIPS KSEG0 cache has no coherency
		 * with ARM — later ARM writes are invisible to MIPS.
		 * If ARM flag is only 0x1 (READY) when MIPS first caches it,
		 * MIPS will loop forever in setCPUAppReady waiting for BIT(2).
		 * Setting APP_READY here ensures MIPS caches 0x5 on first read.
		 */
		{
			u32 *arm_flag = (u32 *)(ShMemAddrBase +
						CPU_FLAG_OFFSET(CPU_ID_ARM));
			*arm_flag |= CPU_FLAG_APP_READY;
			pr_info("cpu_comm: ARM flag pre-set to 0x%x before spinlock release\n",
				*arm_flag);
		}

		spinUnlockhwReg(0);
	} else {
			/* MIPS side — wait for ARM to initialize, then init own socket */
			u32 wait_loops = 0;

			while (1) {
				if (tryspinlockhwReg(0)) {
					u32 magic1 = shmem[SHMEM_OFF_MAGIC1 / 4];
					u32 magic2 = shmem[SHMEM_OFF_MAGIC2 / 4];
					int arm_ready = isCPUReady(CPU_ID_ARM);
					int arm_reset = IsCPUReset(CPU_ID_ARM);

					if (magic1 == CPU_COMM_MAGIC &&
					    magic2 == CPU_COMM_MAGIC &&
					    arm_ready &&
					    !arm_reset) {
						u32 my_cpu = getCurCPUID(0);

						if (!isCPUReady(my_cpu)) {
							InitCommSeqMem(my_cpu);
							InitCommSeqMem(CPU_ID_MIPS);
							ResetCommInterrupt(0);
							setCPUReady(my_cpu);
						}
						spinUnlockhwReg(0);
						break;
					}

					if ((++wait_loops % 200) == 0) {
						pr_info("cpu_comm: MIPS wait ARM init: magic1=0x%x magic2=0x%x arm_ready=%d arm_reset=%d ARM=0x%x MIPS=0x%x\n",
							magic1, magic2, arm_ready, arm_reset,
							*(u32 *)(ShMemAddrBase + CPU_FLAG_OFFSET(CPU_ID_ARM)),
							*(u32 *)(ShMemAddrBase + CPU_FLAG_OFFSET(CPU_ID_MIPS)));
					}
					spinUnlockhwReg(0);
				}
				schedule();
			}
		}

		/* Wait for all CPUs to clear their notice requests */
	while (isCPUNoticeReqed(0) || isCPUNoticeReqed(1))
		msleep(10);

	pr_info("cpu_comm: shared memory initialized (base=0x%x size=0x%x)\n",
		ShMemAddr, ShMemSize);
	return 0;
}
