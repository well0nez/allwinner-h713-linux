// SPDX-License-Identifier: GPL-2.0
/*
 * cpu_comm_dev.c — Kernel interface for CPU_COMM
 *
 * Platform driver, /dev/cpu_comm chardev, ioctl handler,
 * mmap for shared memory access, procfs debug interface,
 * suspend/resume, and module init/cleanup.
 *
 * RE source: HAL_SX6/Kernel_Driver/cpu_comm/cpu_comm.c
 */

#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/of.h>
#include <linux/of_reserved_mem.h>
#include <linux/slab.h>
#include <linux/vmalloc.h>
#include <linux/mm.h>
#include <linux/uaccess.h>
#include <linux/proc_fs.h>
#include <linux/seq_file.h>
#include <linux/io.h>
#include <linux/delay.h>
#include <linux/of_irq.h>
#include "cpu_comm.h"

#define DEVICE_NAME	"cpu_comm"

/* ── Module globals ────────────────────────────────────────── */

static int cpu_comm_major;
static int cpu_comm_fd_major;
static struct class *cpucommclass;
static struct proc_dir_entry *proc_dir;
int cpu_comm_suspend_flag;

static struct device *cpu_comm_mbox_dev;

/* Global waitqueue for custom counting semaphore (BUG-19 fix) */
DECLARE_WAIT_QUEUE_HEAD(cpu_comm_sem_wq);

/* ── File operations ───────────────────────────────────────── */

int cpu_comm_open(struct inode *inode, struct file *file)
{
	pr_debug("cpu_comm: open by pid %d\n", current->pid);
	return 0;
}

static int cpu_comm_release(struct inode *inode, struct file *file)
{
	pr_debug("cpu_comm: close by pid %d\n", current->pid);
	/* Clean up routines for this PID */
	RemovePidRoutines(current->pid);
	return 0;
}

int cpu_comm_mmap(struct file *file, struct vm_area_struct *vma)
{
	unsigned long size = vma->vm_end - vma->vm_start;
	unsigned long pfn;

	if (!ShMemAddr || !ShMemSize)
		return -ENODEV;

	if (size > ShMemSize)
		return -EINVAL;

	pfn = ShMemAddr >> PAGE_SHIFT;
	vma->vm_page_prot = pgprot_noncached(vma->vm_page_prot);

	if (remap_pfn_range(vma, vma->vm_start, pfn, size, vma->vm_page_prot))
		return -EAGAIN;

	pr_debug("cpu_comm: mmap 0x%lx bytes at phys 0x%x\n", size, ShMemAddr);
	return 0;
}

/* ── ioctl handler ─────────────────────────────────────────── */

/*
 * Stock ioctl command codes (from IDA):
 *   0xBFFE7F01: SendComm2CPU (kernel buffer)
 *   0x40087F02: SendComm2CPU (user buffer, call)
 *   0xC0087F26: CPUComm_Call
 *   0xC0087F27: CPUComm_Notify
 *   0x40047F22: setCPUReset
 *   0x7F05:     ShowCPUComm
 *   0x7F12:     Trid_SMM_Show
 *   0x7F39:     Stop MIPS display
 *   0xC0087F21: Shmem info query
 *   0xC0087F20: Shmem addr translation
 *   0xC0087F10: Shmem malloc
 *   0x40047F11: Shmem free
 *   0xBFFE7F30: resume
 *   0xBFFE7F19: suspend
 */

#define IOCTL_SEND_KERN		0xBFFE7F01
#define IOCTL_SEND_USER		0x40087F02
#define IOCTL_CALL		0xC0087F26
#define IOCTL_NOTIFY		0xC0087F27
#define IOCTL_SET_RESET		0x40047F22
#define IOCTL_SHOW		0x7F05
#define IOCTL_SMM_SHOW		0x7F12
#define IOCTL_STOP_DISP		0x7F39
#define IOCTL_SHMEM_INFO	0xC0087F21
#define IOCTL_ADDR_TRANS	0xC0087F20
#define IOCTL_MALLOC		0xC0087F10
#define IOCTL_FREE		0x40047F11
#define IOCTL_RESUME		0xBFFE7F30
#define IOCTL_SUSPEND		0xBFFE7F19
#define IOCTL_GET_CPUID		0x80087F34
#define IOCTL_INSTALL_RT	0xC0087F30
#define IOCTL_UNINSTALL_RT	0xC0087F31
#define IOCTL_CPU_STATUS	0xC0087F21
#define IOCTL_SPINLOCK		0xC0087F36
#define IOCTL_NOTICE_CHECK	0x7F25

long cpu_comm_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	int ret = 0;
	u32 buf[26]; /* max 104 bytes */

	if (cmd == IOCTL_RESUME) {
		cpu_comm_resume(0);
		return 0;
	}

	if (cpu_comm_suspend_flag > 0) {
		pr_warn("cpu_comm: ioctl 0x%x while suspended\n", cmd);
		return -EFAULT;
	}

	switch (cmd) {
	case IOCTL_SEND_KERN:
		ret = SendComm2CPU(arg, 0);
		if (ret)
			pr_warn("cpu_comm: SendComm2CPU failed: %d\n", ret);
		break;

	case IOCTL_SEND_USER:
		ret = SendComm2CPU(arg, 1);
		if (ret)
			pr_warn("cpu_comm: SendComm2CPU(user) failed: %d\n", ret);
		break;

	case IOCTL_CALL: {
		u8 call_buf[168];

		if (copy_from_user(call_buf, (void __user *)arg, 168))
			return -EFAULT;
		ret = CPUComm_Call(call_buf, &call_buf[64],
				   (void *)&call_buf[120]);
		if (ret)
			return -EFAULT;
		if (copy_to_user((void __user *)arg, call_buf, 168))
			return -EFAULT;
		break;
	}

	case IOCTL_NOTIFY: {
		u8 notify_buf[124];

		if (copy_from_user(notify_buf, (void __user *)arg, 124))
			return -EFAULT;
		ret = CPUComm_Notify(notify_buf, (void *)&notify_buf[64]);
		if (ret)
			return -EFAULT;
		break;
	}

	case IOCTL_SET_RESET: {
		u32 val;
		if (copy_from_user(&val, (void __user *)arg, 4))
			return -EFAULT;
		setCPUReset(val & 0xFFFF, val >> 16);
		break;
	}

	case IOCTL_GET_CPUID: {
		u32 cpu = getCurCPUID(0);
		if (copy_to_user((void __user *)arg, &cpu, 4))
			return -EFAULT;
		break;
	}

	case IOCTL_MALLOC: {
		u32 params[2];
		u32 mid;
		if (copy_from_user(params, (void __user *)arg, 8))
			return -EFAULT;
		mid = Trid_SMM_MallocAttr(params[1]);
		params[0] = Mid2Vir(getCurCPUID(0), mid);
		pr_debug("cpu_comm: IOCTL_MALLOC: size=%u mid=0x%x vir=0x%x\n",
			params[1], mid, params[0]);
		if (copy_to_user((void __user *)arg, params, 8))
			return -EFAULT;
		break;
	}

	case IOCTL_FREE: {
		u32 vir = (u32)arg;
		u32 cpu = getCurCPUID(0);
		u32 mid = Vir2Mid(cpu, vir);
		pr_debug("cpu_comm: IOCTL_FREE: arg=0x%x vir=0x%x cpu=%u mid=0x%x\n",
			 (u32)arg, vir, cpu, mid);
		Trid_SMM_Free(mid);
		break;
	}

	case IOCTL_INSTALL_RT:
		if (copy_from_user(buf, (void __user *)arg, 96))
			return -EFAULT;
		ret = AddInRoutine(buf);
		if (ret)
			return -EFAULT;
		if (copy_to_user((void __user *)arg, buf, 96))
			return -EFAULT;
		break;

	case IOCTL_UNINSTALL_RT:
		if (copy_from_user(buf, (void __user *)arg, 96))
			return -EFAULT;
		ret = RemoveRoutine(buf);
		if (ret < 0)
			return -EFAULT;
		break;

	case IOCTL_STOP_DISP: {
		u32 reg = comm_ReadRegWord(0x03061024);
		if (!(reg & 2))
			pr_info("cpu_comm: MIPS display already stopped\n");
		comm_WriteRegWord(0x03061024, reg & ~2);
		pr_info("cpu_comm: MIPS display stopped\n");
		break;
	}

	case IOCTL_SUSPEND:
		cpu_comm_suspend(0);
		break;

	case IOCTL_NOTICE_CHECK:
		checkNoticeReqedJob();
		break;

	case IOCTL_SHOW:
		/* Debug dump — pr_info all state */
		pr_info("cpu_comm: ShMem=0x%x Size=0x%x Base=0x%x Vir=0x%x\n",
			ShMemAddr, ShMemSize, ShMemAddrBase, ShMemAddrVir);
		pr_info("cpu_comm: ARM ready=%d MIPS ready=%d\n",
			isCPUReady(CPU_ID_ARM), isCPUReady(CPU_ID_MIPS));
		break;

	default:
		pr_debug("cpu_comm: unknown ioctl 0x%x\n", cmd);
		return -ENOTTY;
	}

	return ret;
}

static const struct file_operations cpu_comm_fops = {
	.owner		= THIS_MODULE,
	.open		= cpu_comm_open,
	.release	= cpu_comm_release,
	.unlocked_ioctl	= cpu_comm_ioctl,
	.mmap		= cpu_comm_mmap,
};

/* ══════════════════════════════════════════════════════════════
 * comm_fd_ioctl — FusionDale ioctl handler for /dev/cpu_comm_fd
 *
 * From IDA @ 0xf0fc (0x11cc bytes). Handles component management,
 * event subscription, and listener registration used by tvtop/decd.
 *
 * Source in stock: comm_fusiondale.c
 *
 * Ioctl command mapping (verified from ARM32 assembly disassembly):
 *   0xC0047F40: CreateComponent / AttachComponent / DetachComponent (36 bytes)
 *   0xC0047F41: Lock/Unlock spinlock (12 bytes)
 *   0xC0047F42: Pool pointer + Mid2Vir translation (12 bytes)
 *   0xC0047F43: addListener (64 bytes)
 *   0xC0047F44: removeListener (16 bytes)
 *   0xC0047F45: SharedMem buffer alloc/free (12 bytes)
 *   0xC0047F46: msgAddEvent / msgRemoveEvent / msgGetEventIndex (40 bytes)
 *   0xC0047F47: msgAddListener (24 bytes)
 *   0xC0087F48: msgRemoveListener (4 bytes via get/put_user)
 * ══════════════════════════════════════════════════════════════
 */

/*
 * Ioctl command numbers — EXACT values from ARM32 assembly.
 * DO NOT change these; they are verified against the stock binary.
 */
#define IOCTL_FD_COMPONENT	0xC0047F40  /* Create/Attach/Detach component (36 bytes) */
#define IOCTL_FD_LOCK		0xC0047F41  /* Lock/Unlock spinlock (12 bytes) */
#define IOCTL_FD_MID2VIR	0xC0047F42  /* Pool pointer + Mid2Vir (12 bytes) */
#define IOCTL_FD_ADDLISTENER	0xC0047F43  /* Add event listener (64 bytes) */
#define IOCTL_FD_REMOVELISTENER	0xC0047F44  /* Remove event listener (16 bytes) */
#define IOCTL_FD_SHMEM_BUF	0xC0047F45  /* SharedMem buffer alloc/free (12 bytes) */
#define IOCTL_FD_EVENT		0xC0047F46  /* Event add/remove/getindex (40 bytes) */
#define IOCTL_FD_MSGADDLISTENER	0xC0047F47  /* msgAddListener (24 bytes) */
#define IOCTL_FD_MSGRMLISTENER	0xC0087F48  /* msgRemoveListener (4 bytes via get/put_user) */

/*
 * Component pool layout (from IDA analysis):
 *
 * Pool base = getComponentPool() = ShMemAddrBase + SHMEM_OFF_COMP_POOL
 *
 * Pool header:
 *   pool[0] (u32): pool-wide spinlock ID
 *
 * Per-entry (stride = 816 bytes, 40 entries max):
 *   Entry base = pool + 816 * index
 *   +8  (u8):  attach_count
 *   +9  (u8):  registered_flag (non-zero = component registered)
 *   +10 (u8):  component_index (self-index, same as slot number)
 *   +11 (char[15]): name string (null-terminated)
 *   +28 (u16): home_cpu
 *   +32 (u32): per-component spinlock_id (0-11, or 255=not allocated)
 *   +40 (u32): callback_ptr
 *   +44 (u32): flags
 *   +48 (u32): listener_count
 *   +52 (u32): change_counter
 *   +56: listener entries (16 × 48 bytes = 768 bytes)
 *     Per listener (48 bytes = 12 DWORDs):
 *       +0  (u32): flags
 *       +4  (u32): type
 *       +8  (u64): callback_id (8 bytes) — zero means slot free
 *       +16 (u32): event_mask
 *       +24..40: extra data
 *       +40 (u32): owner_tgid
 *
 * Pool trailer (after 40 entries = pool + 32640):
 *   pool+32648 (pool32[8162]): free_slot_count
 *   pool+32656 (pool32[8164..8165]): shmem_buf_mid (u64)
 *   pool+32664 (pool32[8166]): shmem_buf_size
 */
#define COMP_POOL_ENTRY_SIZE	816	/* bytes */
#define COMP_POOL_MAX_SLOTS	40
#define COMP_POOL_MAX_LISTENERS	16

static long comm_fd_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	void __user *uarg = (void __user *)arg;
	u8 *comp_pool;
	int ret = 0;

	if (!ShMemAddrBase)
		return -ENODEV;

	comp_pool = (u8 *)getComponentPool();
	if (!comp_pool)
		return -ENODEV;

	switch (cmd) {

	/* ── 0xC0047F40 — CreateComponent / AttachComponent / DetachComponent ── */
	case IOCTL_FD_COMPONENT: {
		u8 buf[36];
		u32 sub_cmd;
		u8 name[16];

		if (copy_from_user(buf, uarg, 36))
			return -EFAULT;

		/* Sub-command at buf+16: 0=Create, 1=Attach, 2=Detach */
		sub_cmd = *(u32 *)(buf + 16);
		memcpy(name, buf, 16);
		name[15] = '\0';

		if (sub_cmd == 0) {
			/* ── Create: find free slot, register component ── */
			u32 *pool32 = (u32 *)comp_pool;
			u32 pool_spin = pool32[0];
			u32 comp_flags = *(u32 *)(buf + 24);
			int slot = -1;
			int i;

			comm_SpinLockMutex(pool_spin);

			/* Scan for duplicate name */
			for (i = 0; i < COMP_POOL_MAX_SLOTS; i++) {
				u8 *entry = comp_pool + COMP_POOL_ENTRY_SIZE * i;

				if (!entry[9]) /* not registered */
					continue;
				if (!strncmp((char *)(entry + 11), (char *)name, 15)) {
					/* Component already exists */
					comm_SpinUnLock(pool_spin, 0);
					*(u32 *)(buf + 20) = (u32)-1;
					goto fd_comp_copyout;
				}
			}

			/* Find a free slot (attach_count == 0, not registered) */
			for (i = 0; i < COMP_POOL_MAX_SLOTS; i++) {
				u8 *entry = comp_pool + COMP_POOL_ENTRY_SIZE * i;

				if (!entry[8] && !entry[9]) {
					slot = i;
					break;
				}
			}

			if (slot < 0) {
				comm_SpinUnLock(pool_spin, 0);
				*(u32 *)(buf + 20) = (u32)-1;
				goto fd_comp_copyout;
			}

			{
				u8 *entry   = comp_pool + COMP_POOL_ENTRY_SIZE * slot;
				u32 *entry32 = (u32 *)entry;

				strncpy((char *)(entry + 11), (char *)name, 15);
				entry[8]  = 1;        /* attach_count = 1 */
				entry[9]  = 1;        /* registered_flag */
				entry[10] = (u8)slot; /* component_index */
				*(u16 *)(entry + 28) = (u16)getCurCPUID(0);
				entry32[11] = entry[10]; /* copy index to dword field */
				entry32[10] = comp_flags;

				/* Allocate spinlock if not yet assigned */
				if (entry32[8] == 255)
					entry32[8] = comm_ReqestSpinLock();

				pool32[8162]--; /* decrement free_slot_count */
			}

			*(u32 *)(buf + 20) = (u32)slot;
			comm_SpinUnLock(pool_spin, 0);

		} else if (sub_cmd == 1) {
			/* ── Attach: find by name with timeout, increment attach_count ── */
			u32 timeout_ms = *(u32 *)(buf + 28);
			unsigned long timeout_j = jiffies + msecs_to_jiffies(timeout_ms);
			u32 *pool32 = (u32 *)comp_pool;
			int found = -1;
			int i;

			do {
				comm_SpinLockMutex(pool32[0]);
				for (i = 0; i < COMP_POOL_MAX_SLOTS; i++) {
					u8 *entry = comp_pool + COMP_POOL_ENTRY_SIZE * i;

					if (!entry[9]) /* not registered */
						continue;
					if (!strncmp((char *)(entry + 11), (char *)name, 15)) {
						found = i;
						break;
					}
				}

				if (found >= 0) {
					u8 *base      = comp_pool + COMP_POOL_ENTRY_SIZE * found;
					u32 comp_spin = *(u32 *)(base + 32);

					comm_SpinLockMutex(comp_spin);
					base[8]++; /* attach_count++ */
					comm_SpinUnLock(comp_spin, 0);
				}
				comm_SpinUnLock(pool32[0], 0);

				if (found >= 0)
					break;

				msleep(2);
			} while (!timeout_ms || time_before(jiffies, timeout_j));

			*(u32 *)(buf + 20) = (u32)found; /* slot index, or -1 on timeout */

		} else if (sub_cmd == 2) {
			/* ── Detach: decrement attach_count, clear slot if last ── */
			u32 comp_idx = *(u32 *)(buf + 20);
			u32 *pool32  = (u32 *)comp_pool;
			u8  *base;
			u32  comp_spin;

			if (comp_idx >= COMP_POOL_MAX_SLOTS)
				return -EINVAL;

			base = comp_pool + COMP_POOL_ENTRY_SIZE * comp_idx;
			if (!base[8])
				return -EINVAL;

			comp_spin = *(u32 *)(base + 32);
			if (comp_spin == 255)
				return -EINVAL;

			comm_SpinLockMutex(pool32[0]);
			comm_SpinLockMutex(comp_spin);

			if (--base[8] == 0) {
				if (!*(u32 *)(base + 48)) { /* listener_count == 0 */
					/* Fully detached — clear the slot */
					*(u16 *)(base + 28) = 2; /* home_cpu = unused marker */
					base[11] = '\0';         /* clear name */
					base[9]  = 0;            /* registered_flag = 0 */
					*(u64 *)(base + 40) = 0; /* callback_ptr + flags */
					pool32[8162]++;          /* increment free_slot_count */

					/* Release shmem buffer if pool is now empty */
					if (pool32[8162] == COMP_POOL_MAX_SLOTS) {
						u64 mid = *(u64 *)&pool32[8164];

						if (mid && pool32[8166]) {
							Trid_SMM_Free((u32)mid);
							*(u64 *)&pool32[8164] = 0;
							pool32[8166] = 0;
						}
					}
				}
				ret = 1; /* fully detached */
			} else {
				ret = 0; /* still held by others */
			}

			comm_SpinUnLock(comp_spin, 0);
			comm_SpinUnLock(pool32[0], 0);

			*(u32 *)(buf + 24) = ret;
			ret = 0;
		} else {
			return -EINVAL;
		}

fd_comp_copyout:
		if (copy_to_user(uarg, buf, 36))
			return -EFAULT;
		return 0;
	}

	/* ── 0xC0047F41 — Lock/Unlock spinlock ── */
	case IOCTL_FD_LOCK: {
		/*
		 * buf[0] = pool_type (0=component, 1=message)
		 * buf[1] = index (component slot, ignored for message pool)
		 * buf[2] = operation (non-zero=lock, zero=unlock)
		 */
		u32 buf[3]; /* 12 bytes */
		u32 spinlock_id;

		if (copy_from_user(buf, uarg, 12))
			return -EFAULT;

		if (buf[0] == 0) {
			/* Component pool: per-entry spinlock */
			if (buf[1] >= COMP_POOL_MAX_SLOTS)
				return -EINVAL;

			spinlock_id = *(u32 *)(comp_pool + COMP_POOL_ENTRY_SIZE * buf[1] + 32);
			if (spinlock_id > 11)
				return -EINVAL;
		} else if (buf[0] == 1) {
			/* Message pool: pool-level spinlock at msg_pool+4 */
			spinlock_id = *(u32 *)((u8 *)getMsgPool() + 4);
		} else {
			return -EINVAL;
		}

		if (buf[2])
			comm_SpinLockMutex(spinlock_id);
		else
			comm_SpinUnLock(spinlock_id, 0);

		return 0;
	}

	/* ── 0xC0047F42 — Pool pointer + Mid2Vir translation ── */
	case IOCTL_FD_MID2VIR: {
		/*
		 * buf[0] = pool_type (0=component, 1=message)
		 * buf[1] = comp_idx (used only when pool_type=0)
		 * buf[2] = out: Mid2Vir(getCurCPUID(0), ptr)
		 */
		u32 buf[3]; /* 12 bytes */
		u8 *ptr;

		if (copy_from_user(buf, uarg, 12))
			return -EFAULT;

		if (buf[0] == 0) {
			/* Component pool: return pointer to entry data start (+8) */
			if (buf[1] >= COMP_POOL_MAX_SLOTS)
				return -EINVAL;

			ptr = comp_pool + COMP_POOL_ENTRY_SIZE * buf[1] + 8;
		} else if (buf[0] == 1) {
			/* Message pool: return pool base */
			ptr = (u8 *)getMsgPool();
		} else {
			return -EINVAL;
		}

		buf[2] = Mid2Vir(getCurCPUID(0), (u32)(unsigned long)ptr);

		if (copy_to_user(uarg, buf, 12))
			return -EFAULT;
		return 0;
	}

	/* ── 0xC0047F43 — addListener ── */
	case IOCTL_FD_ADDLISTENER: {
		/*
		 * User buffer (64 bytes):
		 *   buf[0]  (u32): comp_idx
		 *   buf+4   (u32): listener.flags
		 *   buf+8   (u64): listener.callback_id
		 *   buf+16  (u32): listener.event_mask
		 *   buf+24..40:    listener extra data
		 *   buf+60  (u32): out result (0=ok, -14=error)
		 */
		u8 buf[64];
		u32 comp_idx;
		u8 *base;
		u32 comp_spin;
		u32 *listener;
		int i;

		if (copy_from_user(buf, uarg, 64))
			return -EFAULT;

		comp_idx = *(u32 *)buf;
		if (comp_idx >= COMP_POOL_MAX_SLOTS)
			return -EINVAL;

		base      = comp_pool + COMP_POOL_ENTRY_SIZE * comp_idx;
		comp_spin = *(u32 *)(base + 32);

		/* Guard against full listener table before taking lock */
		if (*(u32 *)(base + 48) >= COMP_POOL_MAX_LISTENERS) {
			ret = -ENOSPC;
			goto addlistener_out;
		}

		comm_SpinLockMutex(comp_spin);

		/* Check for duplicate: same callback_id + event_mask + tgid */
		listener = (u32 *)(base + 56);
		for (i = 0; i < COMP_POOL_MAX_LISTENERS; i++) {
			if (*(u64 *)(listener + 2) == *(u64 *)(buf + 8) &&
			    listener[4]  == *(u32 *)(buf + 16) &&
			    listener[10] == (u32)current->tgid) {
				ret = -EEXIST;
				goto addlistener_unlock;
			}
			listener += 12; /* advance 48 bytes */
		}

		/* Find free slot: callback_id == 0 means free */
		listener = (u32 *)(base + 56);
		for (i = 0; i < COMP_POOL_MAX_LISTENERS; i++) {
			if (!*(u64 *)(listener + 2))
				break;
			listener += 12;
		}

		if (i >= COMP_POOL_MAX_LISTENERS) {
			ret = -ENOSPC;
			goto addlistener_unlock;
		}

		/* Fill the listener entry */
		listener[0]              = *(u32 *)(buf + 4);   /* flags */
		listener[1]              = *(u32 *)(buf + 0);   /* type (comp_idx) */
		*(u64 *)(listener + 2)   = *(u64 *)(buf + 8);   /* callback_id */
		listener[4]              = *(u32 *)(buf + 16);  /* event_mask */
		*(u64 *)(listener + 6)   = *(u64 *)(buf + 24);  /* extra[0..1] */
		*(u64 *)(listener + 8)   = *(u64 *)(buf + 32);  /* extra[2..3] */
		listener[10]             = (u32)current->tgid;  /* owner_tgid */

		*(u32 *)(base + 48) += 1; /* listener_count++ */
		*(u32 *)(base + 52) += 1; /* change_counter++ */
		ret = 0;

addlistener_unlock:
		comm_SpinUnLock(comp_spin, 0);
addlistener_out:
		*(u32 *)(buf + 60) = ret;
		if (copy_to_user(uarg, buf, 64))
			return -EFAULT;
		return 0;
	}

	/* ── 0xC0047F44 — removeListener ── */
	case IOCTL_FD_REMOVELISTENER: {
		/*
		 * User buffer (16 bytes):
		 *   buf[0] (u32): comp_idx
		 *   buf[1..2] (u64 at offset 4): callback_id to match
		 *   buf[2] (u32 at offset 8): ... (part of callback_id u64)
		 *   buf[2] (u32 at offset 8): event_mask to match
		 *   buf[3] (u32): out result
		 *
		 * Match criteria: callback_id (buf+4 as u64) + event_mask (buf+8) + tgid
		 */
		u32 buf[4]; /* 16 bytes */
		u32 comp_idx;
		u8 *base;
		u32 comp_spin;
		u32 *listener;
		int i;
		int found = 0;

		if (copy_from_user(buf, uarg, 16))
			return -EFAULT;

		comp_idx = buf[0];
		if (comp_idx >= COMP_POOL_MAX_SLOTS)
			return -EINVAL;

		base      = comp_pool + COMP_POOL_ENTRY_SIZE * comp_idx;
		comp_spin = *(u32 *)(base + 32);

		comm_SpinLockMutex(comp_spin);

		listener = (u32 *)(base + 56);
		for (i = 0; i < COMP_POOL_MAX_LISTENERS; i++) {
			if (*(u64 *)(listener + 2) == *(u64 *)&buf[1] &&
			    listener[4]  == buf[2] &&
			    listener[10] == (u32)current->tgid) {
				/* Match — clear the entry */
				*(u32 *)(base + 52) += 1; /* change_counter++ */
				listener[0]            = 0;
				*(u64 *)(listener + 2) = 0; /* callback_id = 0 (marks free) */
				listener[4]            = 0;
				*(u64 *)(listener + 6) = 0;
				*(u64 *)(listener + 8) = 0;
				listener[10]           = 0;
				*(u32 *)(base + 48) -= 1; /* listener_count-- */
				*(u32 *)(base + 52) += 1; /* change_counter++ */
				found = 1;
				break;
			}
			listener += 12;
		}

		ret = found ? 0 : -ENOENT;
		comm_SpinUnLock(comp_spin, 0);

		buf[3] = ret;
		if (copy_to_user(uarg, buf, 16))
			return -EFAULT;
		return 0;
	}

	/* ── 0xC0047F45 — SharedMem buffer alloc/free ── */
	case IOCTL_FD_SHMEM_BUF: {
		/*
		 * buf[0] = out: physical address of buffer
		 * buf[1] = in:  requested size
		 * buf[2] = in:  non-zero=allocate, zero=free
		 */
		u32 buf[3]; /* 12 bytes */
		u32 *pool32 = (u32 *)comp_pool;

		if (copy_from_user(buf, uarg, 12))
			return -EFAULT;

		comm_SpinLockMutex(pool32[0]);

		if (buf[2]) {
			/* Allocate */
			u64 existing_mid = *(u64 *)&pool32[8164];

			if (existing_mid) {
				/* Buffer already exists */
				if (pool32[8166] >= buf[1]) {
					/* Existing buffer is large enough — return it */
					buf[0] = (u32)existing_mid;
				} else {
					/* Too small — free and reallocate */
					Trid_SMM_Free((u32)existing_mid);
					*(u64 *)&pool32[8164] = 0;
					pool32[8166] = 0;
					existing_mid = 0;
				}
			}

			if (!*(u64 *)&pool32[8164]) {
				u32 mid = Trid_SMM_Malloc(buf[1]);

				*(u64 *)&pool32[8164] = (u64)mid;
				pool32[8166]          = mid ? buf[1] : 0;
				buf[0]                = mid;
			}
		} else {
			/* Free */
			u64 mid = *(u64 *)&pool32[8164];

			if (mid)
				Trid_SMM_Free((u32)mid);
			*(u64 *)&pool32[8164] = 0;
			pool32[8166] = 0;
		}

		comm_SpinUnLock(pool32[0], 0);

		if (copy_to_user(uarg, buf, 12))
			return -EFAULT;
		return 0;
	}

	/* ── 0xC0047F46 — Event management (add/remove/getIndex) ── */
	case IOCTL_FD_EVENT: {
		/*
		 * User buffer (40 bytes):
		 *   buf[0..31]: event name string
		 *   buf+32 (u32): sub_cmd (0=add, 1=remove, 2=getIndex)
		 *   buf+36 (u32): in/out index
		 */
		u8  buf[40];
		u32 sub_cmd;
		u32 *msg_pool;
		u32  msg_spin;

		if (copy_from_user(buf, uarg, 40))
			return -EFAULT;

		sub_cmd  = *(u32 *)(buf + 32);
		msg_pool = (u32 *)getMsgPool();
		msg_spin = msg_pool[1]; /* msg_pool+4 */

		if (sub_cmd == 0) {
			/* msgAddEvent — register new event name */
			int idx;

			comm_SpinLockMutex(msg_spin);
			msg_pool[0]++; /* change_counter++ */

			/* Reject if name already registered */
			if (msgEventName2Index((char *)buf) >= 0) {
				ret = -1;
			} else {
				ret = -1;
				/* msg_pool+8: 32 event name strings of 32 bytes each */
				/* msg_pool+1032 = pool32[258]: registered flags */
				for (idx = 0; idx < 32; idx++) {
					if (!msg_pool[idx + 258]) {
						msg_pool[idx + 258] = 1; /* mark registered */
						/* event name at msg_pool+8 + idx*32 */
						strncpy((char *)((u8 *)msg_pool + 8 + idx * 32),
							(char *)buf, 32);
						ret = idx;
						break;
					}
				}
			}

			msg_pool[0]++; /* change_counter++ */
			comm_SpinUnLock(msg_spin, 0);
			*(u32 *)(buf + 36) = (u32)ret;

		} else if (sub_cmd == 1) {
			/* msgRemoveEvent — remove event by index */
			u32 event_idx = *(u32 *)(buf + 36);

			comm_SpinLockMutex(msg_spin);

			if (event_idx < 32 && msg_pool[event_idx + 258]) {
				msg_pool[event_idx + 258] = 0;
				msg_pool[0]++; /* change_counter++ */
				ret = 0;
			} else {
				ret = -1;
			}

			comm_SpinUnLock(msg_spin, 0);
			*(u32 *)(buf + 36) = (u32)ret;

		} else if (sub_cmd == 2) {
			/* msgGetEventIndex — look up index by name */
			*(u32 *)(buf + 36) = (u32)msgEventName2Index((char *)buf);

		} else {
			return -EINVAL;
		}

		if (copy_to_user(uarg, buf, 40))
			return -EFAULT;
		return 0;
	}

	/* ── 0xC0047F47 — msgAddListener ── */
	case IOCTL_FD_MSGADDLISTENER: {
		u32 buf[6]; /* 24 bytes */
		u16 result;

		if (copy_from_user(buf, uarg, 24))
			return -EFAULT;

		result = (u16)msgAddListener(getMsgPool(), buf);
		*(u16 *)buf = result;

		if (copy_to_user(uarg, buf, 24))
			return -EFAULT;
		return 0;
	}

	/* ── 0xC0087F48 — msgRemoveListener (4 bytes via get/put_user) ── */
	case IOCTL_FD_MSGRMLISTENER: {
		u32 val;

		if (get_user(val, (u32 __user *)arg))
			return -EFAULT;

		ret = msgRemoveListener(getMsgPool(), (void *)(unsigned long)val);

		if (put_user((u32)ret, (u32 __user *)arg))
			return -EFAULT;
		return 0;
	}

	default:
		pr_warn("cpu_comm: comm_fd_ioctl: unknown cmd 0x%08x\n", cmd);
		return -ENOTTY;
	}

	return ret;
}

/* FusionDale device file operations */
static const struct file_operations cpu_comm_fd_fops = {
	.owner		= THIS_MODULE,
	.open		= cpu_comm_open,
	.release	= cpu_comm_release,
	.unlocked_ioctl	= comm_fd_ioctl,
	.mmap		= cpu_comm_mmap,
};

/* ── Suspend / Resume ──────────────────────────────────────── */

int cpu_comm_suspend(int flags)
{
	cpu_comm_suspend_flag++;
	pr_info("cpu_comm: suspended (count=%d)\n", cpu_comm_suspend_flag);
	return 0;
}

int cpu_comm_resume(int flags)
{
	if (cpu_comm_suspend_flag > 0)
		cpu_comm_suspend_flag--;
	pr_info("cpu_comm: resumed (count=%d)\n", cpu_comm_suspend_flag);
	return 0;
}

/* ── Proc filesystem ───────────────────────────────────────── */

static int cpu_comm_proc_show(struct seq_file *m, void *v)
{
	seq_printf(m, "ShMemAddr: 0x%08x\n", ShMemAddr);
	seq_printf(m, "ShMemSize: 0x%08x\n", ShMemSize);
	seq_printf(m, "ShMemAddrVir: 0x%08x\n", ShMemAddrVir);
	seq_printf(m, "ShMemAddrBase: 0x%08x\n", ShMemAddrBase);
	seq_printf(m, "ARM Ready: %d\n", isCPUReady(CPU_ID_ARM));
	seq_printf(m, "MIPS Ready: %d\n", isCPUReady(CPU_ID_MIPS));
	seq_printf(m, "ARM App Ready: %d\n", isCPUAppReady(CPU_ID_ARM));
	seq_printf(m, "MIPS App Ready: %d\n", isCPUAppReady(CPU_ID_MIPS));
	seq_printf(m, "Suspend: %d\n", cpu_comm_suspend_flag);
	return 0;
}

static int cpu_comm_proc_open(struct inode *inode, struct file *file)
{
	return single_open(file, cpu_comm_proc_show, NULL);
}

static const struct proc_ops cpu_comm_proc_ops = {
	.proc_open	= cpu_comm_proc_open,
	.proc_read	= seq_read,
	.proc_lseek	= seq_lseek,
	.proc_release	= single_release,
};

void cpu_comm_proc_init(void)
{
	proc_dir = proc_mkdir("cpu_comm", NULL);
	if (proc_dir)
		proc_create("status", 0444, proc_dir, &cpu_comm_proc_ops);
}

void cpu_comm_proc_term(void)
{
	if (proc_dir) {
		remove_proc_entry("status", proc_dir);
		remove_proc_entry("cpu_comm", NULL);
		proc_dir = NULL;
	}
}

/* ── Module init — the big one ─────────────────────────────── */

int cpu_comm_init(int mode)
{
	struct page **pages;
	int page_count, i;
	void *vaddr;
	int ret;

	/*
	 * MIPS CCU Clock + Reset Initialization.
	 *
	 * Before accessing any MIPS-related hardware or shared memory,
	 * ensure the MIPS clock domain is properly enabled. This is the
	 * first step in the MIPS boot sequence (Phase 2 of the 6-phase
	 * boot chain).
	 *
	 * CCU registers (from ccu-sun50i-h713.c):
	 *   0x02001600: mips_clk — osc24M/pll-periph0-2x, M-Divider, Gate
	 *   0x02001604: bus_mips_clk — AHB gate
	 *   0x0200160c: bus_mips_reset — bits 16-18 (RST_MIPS, RST_MIPS_DBG, RST_MIPS_CFG)
	 *   0x0200171c: msgbox_reset — bit 16
	 *
	 * We ensure clocks are enabled and resets are deasserted so the
	 * MIPS can boot properly when loaded by U-Boot.
	 */
	{
		void __iomem *ccu = ioremap(0x02001000, 0x800);

		if (ccu) {
			u32 val;

			/* Ensure MIPS clock is enabled (0x600 offset from CCU base) */
			val = readl(ccu + 0x600);
			pr_info("cpu_comm: MIPS CLK before: 0x%08x\n", val);
			if (!(val & 0x80000000)) {
				val |= 0x80000000; /* Set gate enable bit */
				writel(val, ccu + 0x600);
				pr_info("cpu_comm: MIPS CLK enabled\n");
			}

			/* Ensure bus MIPS clock is enabled (0x604 offset) */
			val = readl(ccu + 0x604);
			pr_info("cpu_comm: BUS MIPS CLK before: 0x%08x\n", val);
			if (!(val & 0x1)) {
				val |= 0x1; /* Set AHB gate enable */
				writel(val, ccu + 0x604);
				pr_info("cpu_comm: BUS MIPS CLK enabled\n");
			}

			/* Deassert MIPS reset bits (0x60c offset, bits 16-18) */
			val = readl(ccu + 0x60c);
			pr_info("cpu_comm: BUS MIPS RESET before: 0x%08x\n", val);
			if (val & 0x00070000) {
				val &= ~0x00070000; /* Clear RST_MIPS, RST_MIPS_DBG, RST_MIPS_CFG */
				writel(val, ccu + 0x60c);
				pr_info("cpu_comm: MIPS resets deasserted\n");
			}

			/* Deassert msgbox reset (0x71c offset, bit 16) */
			val = readl(ccu + 0x71c);
			pr_info("cpu_comm: MSGBOX RESET before: 0x%08x\n", val);
			if (val & 0x00010000) {
				val &= ~0x00010000;
				writel(val, ccu + 0x71c);
				pr_info("cpu_comm: MSGBOX reset deasserted\n");
			}

			iounmap(ccu);
		} else {
			pr_warn("cpu_comm: failed to ioremap CCU for MIPS clock init\n");
		}
	}

	/*
	 * Stock has NO startup delay here. The MIPS boots independently
	 * and polls SharedMem address at 0x03061024. Any delay risks
	 * the MIPS timing out on its side.
	 */

	if (!ShMemAddr || !ShMemSize) {
		pr_err("cpu_comm: ShMemAddr/Size not set\n");
		return -EINVAL;
	}

	/* Map shared memory into kernel VA (uncacheable) */
	page_count = (ShMemSize + PAGE_SIZE - 1) >> PAGE_SHIFT;
	pages = vmalloc(page_count * sizeof(struct page *));
	if (!pages)
		return -ENOMEM;

	for (i = 0; i < page_count; i++)
		pages[i] = pfn_to_page((ShMemAddr >> PAGE_SHIFT) + i);

	/*
	 * SharedMem MUST be uncached — both ARM and MIPS access it.
	 * pgprot_writecombine buffers reads → ARM never sees MIPS writes.
	 * Stock uses pgprot_kernel & 0xFFFFFDC3 | 0x204 (strongly ordered).
	 * pgprot_noncached is the mainline equivalent.
	 */
	vaddr = vmap(pages, page_count, VM_MAP,
		     pgprot_noncached(PAGE_KERNEL));
	vfree(pages);

	if (!vaddr) {
		pr_err("cpu_comm: failed to vmap shared memory\n");
		return -ENOMEM;
	}

	ShMemAddrBase = (u32)(unsigned long)vaddr;
	ShMemAddrVir = ShMemAddrBase;

	pr_info("cpu_comm: shared memory mapped: phys=0x%x virt=0x%x size=0x%x\n",
		ShMemAddr, ShMemAddrBase, ShMemSize);

	pr_info("cpu_comm: PRE-WIPE: ARM=0x%x MIPS=0x%x magic1=0x%x magic2=0x%x\n",
		readl(vaddr + 0x4CDC), readl(vaddr + 0x4CE0),
		readl(vaddr + 0x90), readl(vaddr + 0x75B8));

	/*
	 * FIX: Conditional wipe — only memset_io if magics are NOT already set.
	 *
	 * Root cause of MIPS APP_READY=0: memset_io wipes the entire shared
	 * memory region including magic markers and MIPS flags BEFORE the MIPS
	 * has a chance to call setCPUAppReady. Since MIPS only calls
	 * setCPUAppReady once during its init, a wipe after MIPS has already
	 * set its flags permanently destroys MIPS APP_READY.
	 *
	 * Stock firmware checks magic1+magic2 in InitCommMem master path
	 * and takes a lightweight reinit if both are DEADBEEF.
	 * We replicate this: if magics are already set, skip the full wipe.
	 */
	{
		u32 magic1 = readl(vaddr + SHMEM_OFF_MAGIC1);
		u32 magic2 = readl(vaddr + SHMEM_OFF_MAGIC2);

		if (magic1 == CPU_COMM_MAGIC && magic2 == CPU_COMM_MAGIC) {
			pr_info("cpu_comm: magics already set (0x%x/0x%x) — skipping memset_io wipe to preserve MIPS flags\n",
				magic1, magic2);
		} else {
			pr_info("cpu_comm: magics not set (0x%x/0x%x) — performing full memset_io wipe\n",
				magic1, magic2);
			memset_io(vaddr, 0, SHMEM_OFF_SMM_HEAP + 8);
		}
	}

	ret = cpu_comm_hw_init();
	if (ret)
		goto err_unmap;

	if (getCurCPUID(0) == CPU_ID_ARM) {
		comm_WriteShareReg(SHARE_REG_ADDR, ShMemAddr);
		comm_WriteShareReg(SHARE_REG_SIZE, ShMemSize);
		pr_info("cpu_comm: wrote ShMemAddr=0x%x to MIPS share regs\n",
			ShMemAddr);
	}

	/* Register /dev/cpu_comm character device */
	cpu_comm_major = register_chrdev(0, "/dev/" DEVICE_NAME, &cpu_comm_fops);
	if (cpu_comm_major <= 0) {
		pr_err("cpu_comm: failed to register chrdev\n");
		ret = -ENODEV;
		goto err_hw;
	}

	cpucommclass = class_create(DEVICE_NAME);
	if (IS_ERR(cpucommclass)) {
		pr_err("cpu_comm: failed to create class\n");
		ret = PTR_ERR(cpucommclass);
		goto err_chrdev;
	}

	if (IS_ERR(device_create(cpucommclass, NULL,
				 MKDEV(cpu_comm_major, 0), NULL,
				 DEVICE_NAME))) {
		pr_err("cpu_comm: failed to create device\n");
		ret = -ENODEV;
		goto err_class;
	}

	/* Register /dev/cpu_comm_fd — FusionDale device for tvtop/decd */
	{
		cpu_comm_fd_major = register_chrdev(0, "/dev/cpu_comm_fd",
						   &cpu_comm_fd_fops);
		if (cpu_comm_fd_major > 0) {
			device_create(cpucommclass, NULL,
				      MKDEV(cpu_comm_fd_major, 0), NULL,
				      "cpu_comm_fd");
			pr_info("cpu_comm: /dev/cpu_comm_fd registered (major=%d)\n",
				cpu_comm_fd_major);
		} else {
			pr_warn("cpu_comm: /dev/cpu_comm_fd failed — FusionDale unavailable\n");
		}
	}

	/* Allocate per-device state */
	pcpu_comm_dev = kzalloc(CPU_COMM_DEV_SIZE, GFP_KERNEL);
	if (!pcpu_comm_dev) {
		ret = -ENOMEM;
		goto err_device;
	}

	/* Initialize pcpu_comm_dev fields (from IDA @ 0x2234).
	 * kzalloc zeros everything, but semaphore counts and self-ref
	 * lists need non-zero initialization.
	 */
	{
		u32 *d = (u32 *)pcpu_comm_dev;

		/* Self-ref list at offset 24/28 (call list head/tail) */
		d[6] = (u32)&d[6];
		d[7] = (u32)&d[6];

		/* Self-ref list at offset 40/44 (return list head/tail) */
		d[10] = (u32)&d[10];
		d[11] = (u32)&d[10];

		/* Semaphore counts — just u32 counters used by cpu_comm_sem_*()
		 * helpers (BUG-19 fix: no struct semaphore, just atomic u32).
		 */
		d[5] = 1;	/* call sem at offset 20 */
		d[9] = 1;	/* return sem at offset 36 */
		d[507] = 1;	/* sem at offset 2028 */

		/* Self-ref list at offset 2032/2036 */
		d[508] = (u32)&d[508];
		d[509] = (u32)&d[508];

		/* Marker */
		d[510] = (u32)-1;	/* offset 2040 = -1 */
		d[506] = 0;		/* offset 2024 */
	}

	/* Initialize channel pool inside pcpu_comm_dev */
	ChannelPoolInit((void *)((u8 *)pcpu_comm_dev + 0x30));

	/* Initialize work queues (8 total: 2 CPUs × 4 priorities) */
	/* Stock creates 8 dedicated work queues (2 CPUs × 4 priorities).
	 * We use the default kernel workqueue via schedule_work() in
	 * Comm_Add2Call2WQ instead, which is simpler and sufficient
	 * for initial bring-up. Dedicated WQs can be added later if
	 * needed for priority-based scheduling.
	 */

	/*
	 * Stock sequence: ISR registration BEFORE InitCommMem.
	 * This ensures MIPS interrupts arriving during shmem init
	 * are caught rather than lost.
	 */

	/* Initialize interrupt semaphores */
	init_intrsem(0);

	/*
	 * MIPS elog intercept — switch MIPS firmware logging to Mode 2
	 * (2MB linear buffer) BEFORE we trigger MIPS to continue.
	 * This captures all MIPS logs from the moment it sees ARM READY.
	 *
	 * MIPS virtual → ARM physical: subtract 0x40000000
	 *   Mode flag:       MIPS 0x8B48BE9B → phys 0x4B48BE9B
	 *   Mode2 enable:    MIPS 0x8B48C2AD → phys 0x4B48C2AD
	 *   Mode2 write ptr: MIPS 0x8B48C2B8 → phys 0x4B48C2B8
	 *   Mode2 buffer:    MIPS 0x8B28BD9C → phys 0x4B28BD9C (2MB)
	 */
	{
		void __iomem *elog_ctl;

		/* Map MIPS elog control region (flags + pointers) */
		elog_ctl = ioremap(0x4B48BE00, 0x500);
		if (elog_ctl) {
			u8 old_mode = readb(elog_ctl + 0x9B);  /* 0x4B48BE9B */
			u8 old_en2  = readb(elog_ctl + 0x4AD);  /* 0x4B48C2AD */
			u32 old_wp2 = readl(elog_ctl + 0x4B8); /* 0x4B48C2B8 */

			pr_info("cpu_comm: MIPS elog BEFORE: mode=%u en2=%u wp2=%u\n",
				old_mode, old_en2, old_wp2);

			/* Switch to Mode 2 (2MB linear buffer) */
			/* writeb(2, elog_ctl + 0x9B); -- keep Mode 1 ring buffer */   /* mode = 2 */
			/* writeb(1, elog_ctl + 0x4AD); */  /* mode2 enable = 1 */
			/* writel(0, elog_ctl + 0x4B8); */  /* mode2 write ptr = 0 */

			pr_info("cpu_comm: MIPS elog staying on Mode 1 (ring buffer) (2MB buffer)\n");
			iounmap(elog_ctl);
		} else {
			pr_warn("cpu_comm: failed to ioremap MIPS elog control\n");
		}
	}

	/* Initialize shared memory structures FIRST — before enabling
	 * message reception. The MIPS will send messages as soon as it
	 * sees ARM READY, and command_action/ack_action need initialized
	 * SharedMem structures to process them correctly.
	 */
	pr_debug("cpu_comm: calling InitCommMem(%d)...\n", mode);
	ret = InitCommMem(mode);
	if (ret) {
		pr_err("cpu_comm: InitCommMem failed: %d\n", ret);
		goto err_device;
	}
	pr_debug("cpu_comm: InitCommMem done\n");

	/* NOW start message reception — SharedMem is ready */
	{
		int irq = platform_get_irq(to_platform_device(cpu_comm_mbox_dev), 0);

		if (irq > 0) {
			ret = cpu_comm_msgbox_request_irq(irq, (void *)cpu_comm_msg_cb);
			if (ret)
				pr_err("cpu_comm: msgbox IRQ registration failed: %d\n", ret);
		} else {
			pr_warn("cpu_comm: no msgbox IRQ in DTS (err=%d)\n", irq);
		}
	}

	/*
	 * Stock ARM never waits for MIPS READY or MIPS APP_READY.
	 * The protocol is: ARM sets its flags, MIPS polls them.
	 * Blocking here risks timeout if MIPS hasn't started yet,
	 * and the stock driver simply proceeds without waiting.
	 */
	{
		u32 *mips_flag = (u32 *)(ShMemAddrBase + 0x4CE0);
		u32 *arm_flag = (u32 *)(ShMemAddrBase + 0x4CDC);

		/*
		 * FIX: ARM sets only its READY flag (BIT(0)), NOT APP_READY (BIT(2)).
		 * Only MIPS sets its own APP_READY flag via setCPUAppReady.
		 * ARM was previously calling setCPUAppReady(getCurCPUID(0)) which
		 * set ARM's own APP_READY flag and then waited for MIPS — but ARM
		 * should not participate in the APP_READY handshake.
		 *
		 * ARM still needs to set READY (BIT(0)) so MIPS knows the ARM
		 * side of the shared memory is initialized.
		 * Flag bits: BIT(0)=READY, BIT(1)=NOT_READY, BIT(2)=APP_READY, BIT(3)=RESET/NOTICE_REQ
		 */
		{
			u32 tmp;
			comm_SpinLock(3);
			tmp = *arm_flag;
			tmp |= BIT(0);   /* READY */
			tmp &= ~BIT(1);  /* clear NOT_READY */
			tmp &= ~BIT(3);  /* clear RESET/NOTICE_REQ */
			*arm_flag = tmp;
			comm_SpinUnLock(3, 0);
			pr_info("cpu_comm: ARM READY set (no APP_READY — MIPS sets its own)\n");
		}

		pr_info("cpu_comm: POST-INIT: magic1=0x%x magic2=0x%x ARM=0x%x MIPS=0x%x\n",
			*(u32 *)(ShMemAddrBase + 0x90),
			*(u32 *)(ShMemAddrBase + 0x75B8),
			*arm_flag, *mips_flag);

		/* If MIPS has set READY (BIT(0)), assume APP_READY follows.
		 * MIPS sets APP_READY in L1 cache (invisible to ARM). */
		if (*mips_flag & 0x1) {
			mips_app_ready_assumed = 1;
			pr_info("cpu_comm: MIPS app-ready assumed (MIPS READY seen)\n");
		}

		/*
		 * Wait for MIPS to process and log, then dump elog buffer.
		 * The MIPS should see ARM READY+APP_READY and continue its
		 * init, logging through Mode 2 (2MB buffer).
		 */
		msleep(500);

		pr_info("cpu_comm: POST-WAIT: ARM=0x%x MIPS=0x%x\n",
			*arm_flag, *mips_flag);

		/* Re-check MIPS READY after wait */
		if (!mips_app_ready_assumed && (*mips_flag & 0x1)) {
			mips_app_ready_assumed = 1;
			pr_info("cpu_comm: MIPS app-ready assumed (MIPS READY seen after wait)\n");
		}

		/*
		 * Force-set MIPS READY + APP_READY from ARM side.
		 *
		 * Background: In the stock Allwinner H713 firmware, the MIPS
		 * coprocessor (running display.bin) NEVER sets APP_READY (BIT2)
		 * on its own CPU flag word at SharedMem + 0x4CE0.
		 *
		 * Evidence from stock binary analysis (display.bin, 1.2MB MIPS32-LE):
		 *
		 *   1. display.bin setCPUAppReady equivalent (file offset 0x1a440):
		 *      - LW/ORI/SW at offset 0x4CDC (= CPU_FLAG_OFFSET(0) = ARM flag)
		 *      - Sets BIT(0) READY, clears BIT(1) NOT_READY, clears BIT(3) NOTICE_REQ
		 *      - All writes go to 0x4CDC (ARM flag), NOT 0x4CE0 (MIPS flag)
		 *      - BIT(2) APP_READY is NEVER set anywhere in display.bin
		 *
		 *   2. display.bin only reads 0x4CE0 (MIPS flag) ONCE (offset 0x1af04):
		 *      - LW + ANDI 0x8 = checks NOTICE_REQ (BIT3) only
		 *      - No writes to 0x4CE0 exist in the entire 1.2MB binary
		 *
		 *   3. Stock ARM driver setCPUAppReady (cpu_comm_dev.ko @ 0x4f28):
		 *      - Sets BIT(2) on own flag, then waits on other CPU's BIT(2)
		 *      - BUG: wait loop reads [r5+0xcdc] = hardcoded ARM flag (0x4CDC)
		 *        regardless of cpu_id. ARM waits on ITS OWN flag, not MIPS.
		 *      - For ARM (cpu_id=0): sets APP_READY, waits on self = returns
		 *        immediately. MIPS APP_READY is never actually checked.
		 *      - Stock error paths: 6x while(1) infinite loops (not BUG())
		 *      - Stock APP_READY wait: while(!flag) msleep(1) with NO timeout
		 *
		 * Conclusion: MIPS APP_READY was never functional in stock firmware.
		 * The stock system worked because ARM never checked MIPS APP_READY
		 * (due to the hardcoded 0x4CDC bug in the wait loop). Our mainline
		 * driver correctly checks the other CPU's flag (cpu_id ^ 1), which
		 * means isCPUAppReady(MIPS) would always return false without this
		 * force-set. Setting both READY and APP_READY here matches the
		 * effective stock behavior where MIPS readiness was always assumed.
		 *
		 * See also: cpu_comm_mem.c setCPUAppReady() 2s timeout on the
		 * other-CPU wait (replacing the stock infinite msleep loop).
		 */
		if (!(*mips_flag & 0x5)) {
			comm_SpinLock(3);
			*mips_flag |= 0x5;  /* CPU_FLAG_READY | CPU_FLAG_APP_READY */
			comm_SpinUnLock(3, 0);
			pr_info("cpu_comm: MIPS READY+APP_READY force-set from ARM (stock never sets it). flag=0x%x\n",
				*mips_flag);
		}

		/* Auto-register known MIPS VP routes */
		{
			static const u32 mips_vp_ids[] = {
				0x8B109F04, 0x8B10A0E0, 0x8B10A0E8, 0x8B10A110,
				0x8B10A138, 0x8B10A160, 0x8B10A188, 0x8B10A1EC,
				0x8B10A218, 0x8B10A244, 0x8B109D20, 0x8B109D54,
				0x8B109DC0, 0x8B109CD0, 0x8B109CF8, 0x8B109B48,
				0x8B109B40, 0x8B109F7C,
			};
			int j, ok = 0;
			for (j = 0; j < ARRAY_SIZE(mips_vp_ids); j++) {
				u8 rt[96];
				memset(rt, 0, 96);
				*(u16 *)(rt + 2) = 1;
				*(u32 *)(rt + 8) = mips_vp_ids[j];
				*(int *)(rt + 92) = -1;
				if (AddInRoutine(rt) == 0)
					ok++;
			}
			pr_info("cpu_comm: auto-registered %d/%d MIPS VP routes\n",
				ok, (int)ARRAY_SIZE(mips_vp_ids));
		}
	}

	/* Dump MIPS elog Mode 2 buffer */
	{
		void __iomem *elog_ctl, *elog_buf;
		u32 wp2;

		elog_ctl = ioremap(0x4B48BE00, 0x500);
		elog_buf = ioremap(0x4B28BD9C, 0x200000);

		if (elog_ctl && elog_buf) {
			u8 cur_mode = readb(elog_ctl + 0x9B);
			wp2 = readl(elog_ctl + 0x4B8);

			pr_info("cpu_comm: MIPS elog AFTER: mode=%u wp2=%u\n",
				cur_mode, wp2);

			if (wp2 > 0 && wp2 <= 0x200000) {
				/* Dump in chunks to dmesg (max ~800 bytes per pr_info) */
				char line[256];
				u32 pos = 0;
				u32 len = min_t(u32, wp2, 0x10000); /* cap at 64KB for dmesg */
				int lpos = 0;

				pr_info("cpu_comm: === MIPS ELOG DUMP (%u bytes) ===\n", wp2);
				while (pos < len) {
					u8 c = readb(elog_buf + pos);
					pos++;
					if (c == '\n' || lpos >= 250) {
						line[lpos] = '\0';
						pr_info("MIPS: %s\n", line);
						lpos = 0;
					} else if (c >= 0x20 && c < 0x7F) {
						line[lpos++] = c;
					} else if (c == '\x1B') {
						/* Skip ANSI escape sequences */
						while (pos < len) {
							c = readb(elog_buf + pos);
							pos++;
							if ((c >= 'A' && c <= 'Z') ||
							    (c >= 'a' && c <= 'z'))
								break;
						}
					}
				}
				if (lpos > 0) {
					line[lpos] = '\0';
					pr_info("MIPS: %s\n", line);
				}
				pr_info("cpu_comm: === END MIPS ELOG ===\n");
			} else {
				pr_info("cpu_comm: MIPS elog Mode 2 buffer empty (wp2=%u)\n", wp2);
			}
		}

		if (elog_buf)
			iounmap(elog_buf);
		if (elog_ctl)
			iounmap(elog_ctl);
	}

	/* Create proc entries */
	cpu_comm_proc_init();

	pr_info("cpu_comm: initialized (ShMem=0x%x, %u bytes)\n",
		ShMemAddr, ShMemSize);
	return 0;

err_device:
	if (cpucommclass) {
		if (cpu_comm_fd_major > 0)
			device_destroy(cpucommclass, MKDEV(cpu_comm_fd_major, 0));
		if (cpu_comm_major > 0)
			device_destroy(cpucommclass, MKDEV(cpu_comm_major, 0));
	}
err_class:
	if (cpucommclass) {
		class_destroy(cpucommclass);
		cpucommclass = NULL;
	}
err_chrdev:
	if (cpu_comm_fd_major > 0) {
		unregister_chrdev(cpu_comm_fd_major, "/dev/cpu_comm_fd");
		cpu_comm_fd_major = 0;
	}
	if (cpu_comm_major > 0) {
		unregister_chrdev(cpu_comm_major, "/dev/" DEVICE_NAME);
		cpu_comm_major = 0;
	}
err_hw:
	cpu_comm_msgbox_probe_stop();
	cpu_comm_msgbox_free_irq();
	cpu_comm_hw_cleanup();
err_unmap:
	if (vaddr)
		vunmap(vaddr);
	ShMemAddrBase = 0;
	ShMemAddrVir = 0;
	return ret;
}

/*
 * cleanupFDCPUReset — Cleanup FusionDale state during CPU reset.
 *
 * From IDA @ 0xe7f0. Called as part of setCPUReset phase 1.
 * Resets the component pool's FD-specific state for the reset CPU.
 *
 * The stock implementation resets listener reference counts and
 * component attachment states. For initial bring-up, we just
 * log the event since FD-based services (tvtop/decd) aren't running yet.
 */
void cleanupFDCPUReset(u32 cpu_id)
{
	pr_info("cpu_comm: cleanupFDCPUReset(%u)\n", cpu_id);
	/* Full implementation clears component listener entries
	 * and resets attachment counts in the component pool.
	 * Not needed until FusionDale services are running.
	 */
}

void cpu_comm_cleanup(void)
{
	cpu_comm_proc_term();

	if (pcpu_comm_dev) {
		kfree(pcpu_comm_dev);
		pcpu_comm_dev = NULL;
	}

	if (cpucommclass) {
		/* Destroy both devices before destroying the class */
		if (cpu_comm_fd_major > 0)
			device_destroy(cpucommclass, MKDEV(cpu_comm_fd_major, 0));
		device_destroy(cpucommclass, MKDEV(cpu_comm_major, 0));
		class_destroy(cpucommclass);
		cpucommclass = NULL;
	}

	if (cpu_comm_fd_major > 0) {
		unregister_chrdev(cpu_comm_fd_major, "/dev/cpu_comm_fd");
		cpu_comm_fd_major = 0;
	}

	if (cpu_comm_major > 0) {
		unregister_chrdev(cpu_comm_major, "/dev/" DEVICE_NAME);
		cpu_comm_major = 0;
	}

	cpu_comm_msgbox_probe_stop();
	cpu_comm_msgbox_free_irq();
	cpu_comm_hw_cleanup();

	if (ShMemAddrBase) {
		vunmap((void *)(unsigned long)ShMemAddrBase);
		ShMemAddrBase = 0;
		ShMemAddrVir = 0;
	}

	pr_info("cpu_comm: cleaned up\n");
}

/* ── Platform driver ───────────────────────────────────────── */

static int cpu_comm_drv_probe(struct platform_device *pdev)
{
	struct device_node *np = pdev->dev.of_node;
	struct device_node *mem_node;
	struct reserved_mem *rmem;
	int ret;

	/* Get shared memory region from DTS */
	mem_node = of_parse_phandle(np, "shared-memory", 0);
	if (!mem_node)
		mem_node = of_parse_phandle(np, "memory-region", 0);
	if (!mem_node) {
		dev_err(&pdev->dev, "no shared-memory/memory-region in DTS\n");
		return -ENODEV;
	}

	rmem = of_reserved_mem_lookup(mem_node);
	of_node_put(mem_node);
	if (!rmem) {
		dev_err(&pdev->dev, "reserved mem lookup failed\n");
		return -ENODEV;
	}

	ShMemAddr = rmem->base;
	ShMemSize = rmem->size;

	dev_info(&pdev->dev, "shared memory: 0x%x size 0x%x\n",
		 ShMemAddr, ShMemSize);

	/* Initialize CPU_COMM */
	cpu_comm_mbox_dev = &pdev->dev;
	ret = cpu_comm_init(0);
	if (ret) {
		dev_err(&pdev->dev, "init failed: %d\n", ret);
		return ret;
	}

	dev_info(&pdev->dev, "probed successfully\n");
	return 0;
}

static void cpu_comm_drv_remove(struct platform_device *pdev)
{
	cpu_comm_cleanup();
}

static const struct of_device_id cpu_comm_of_match[] = {
	{ .compatible = "trix,cpu_comm" },
	{ .compatible = "allwinner,hy310-cpu-comm" },
	{ .compatible = "allwinner,sunxi-cpu-comm" },
	{ /* sentinel */ }
};
MODULE_DEVICE_TABLE(of, cpu_comm_of_match);

static struct platform_driver cpu_comm_driver = {
	.probe	= cpu_comm_drv_probe,
	.remove	= cpu_comm_drv_remove,
	.driver	= {
		.name		= "hy310-cpu-comm",
		.of_match_table	= cpu_comm_of_match,
	},
};
module_platform_driver(cpu_comm_driver);

MODULE_DESCRIPTION("HY310 CPU_COMM — ARM/MIPS IPC Framework");
MODULE_AUTHOR("HY310 Mainline Port (RE from Allwinner HAL_SX6)");
MODULE_LICENSE("GPL");
