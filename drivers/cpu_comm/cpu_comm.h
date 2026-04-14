/* SPDX-License-Identifier: GPL-2.0 */
/*
 * HY310 CPU_COMM — ARM ↔ MIPS Inter-Processor Communication
 *
 * Port of Allwinner HAL_SX6 cpu_comm framework.
 * Reverse-engineered from stock cpu_comm_dev.ko (H713 SDK V1.3)
 * Source: HAL_SX6/Kernel_Driver/cpu_comm/
 *
 * Architecture:
 *   ARM Kernel ←→ Shared Memory (5MB @ 0x4E300000) ←→ MIPS Display Engine
 *   Notifications via msgbox hardware doorbell
 *   Synchronization via sunxi hardware spinlocks
 */

#ifndef _CPU_COMM_H_
#define _CPU_COMM_H_

#include <linux/types.h>
#include <linux/list.h>
#include <linux/semaphore.h>
#include <linux/workqueue.h>
#include <linux/cdev.h>
#include <linux/wait.h>
#include <linux/atomic.h>
#include <linux/sched.h>

/*
 * ══════════════════════════════════════════════════════════════
 * Custom counting semaphore compatible with stock 4-byte layout
 *
 * The stock kernel uses 4-byte semaphore counters at packed offsets.
 * Mainline struct semaphore is 16 bytes (spinlock+count+wait_list)
 * and would overlap adjacent fields. These helpers operate on a raw
 * u32 counter + a global waitqueue, matching the stock layout.
 *
 * BUG-19 fix: replaces all (struct semaphore *) casts throughout.
 * ══════════════════════════════════════════════════════════════
 */

extern wait_queue_head_t cpu_comm_sem_wq;

static inline void cpu_comm_sem_down(void *addr)
{
	u32 *count = (u32 *)addr;

	wait_event_interruptible(cpu_comm_sem_wq, *count > 0);
	(*count)--;
}

static inline int cpu_comm_sem_down_interruptible(void *addr)
{
	u32 *count = (u32 *)addr;
	int ret;

	ret = wait_event_interruptible(cpu_comm_sem_wq, *count > 0);
	if (ret)
		return ret;
	(*count)--;
	return 0;
}

static inline int cpu_comm_sem_down_timeout(void *addr, long jiffies)
{
	u32 *count = (u32 *)addr;
	long ret;

	ret = wait_event_interruptible_timeout(cpu_comm_sem_wq,
					       *count > 0, jiffies);
	if (ret == 0)
		return -ETIME;	/* timeout */
	if (ret < 0)
		return (int)ret; /* interrupted */
	(*count)--;
	return 0;
}

static inline void cpu_comm_sem_up(void *addr)
{
	u32 *count = (u32 *)addr;

	if (!count)
		return;

	(*count)++;
	wake_up_all(&cpu_comm_sem_wq);
}

/* ══════════════════════════════════════════════════════════════
 * Constants (from IDA RE)
 * ══════════════════════════════════════════════════════════════ */

#define CPU_COMM_MAGIC		0xDEADBEEF

/* CPU IDs */
#define CPU_ID_ARM		0
#define CPU_ID_MIPS		1
#define CPU_ID_MAX		2	/* only 0 and 1 used, though max_cpu=3 in init */

/* MIPS control register base (ioremapped separately by mipsloader) */
#define MIPS_CTRL_BASE		0x03061000
#define MIPS_REG_STATUS		0x1C
#define MIPS_REG_SHARE14	0x24	/* SharedMemAddr written here */
#define MIPS_REG_SHARE13	0x28	/* SharedMemSize written here */
#define MIPS_REG_BOOTADDR	0x30

/* Msgbox base (hardware doorbell for ARM ↔ MIPS) */
#define MSGBOX_BASE		0x03003000

/* Hardware spinlock IDs */
#define HW_SPINLOCK_COUNT	14
#define HW_SPINLOCK_APP_START	5	/* app-usable locks start at 5 */
#define HW_SPINLOCK_APP_END	11

/* Shared Register IDs (mapped to MIPS MMIO at MIPS_CTRL_BASE) */
#define SHARE_REG_SIZE		13	/* → MIPS_REG_SHARE13 (0x03061028) */
#define SHARE_REG_ADDR		14	/* → MIPS_REG_SHARE14 (0x03061024) */
#define SHARE_REG_MAX		39

/* FIFO parameters */
#define FIFO_NAME_LEN		48
#define FIFO_DEFAULT_CAP	21	/* capacity (1 slot wasted → 20 usable) */
#define FIFO_ITEM_SIZE		4	/* default: 4 bytes per item (pointer) */

/* CommSocket parameters */
#define MAX_WAIT_ENTRIES	20
#define WAIT_ENTRY_SIZE		32	/* bytes per wait entry */
#define COMM_SOCKET_SIZE	4992	/* 1248 DWORDs per socket — s_CommSockt[1248*cpu+off] stride */

/* Call entries */
#define CALL_ENTRY_SIZE		96	/* bytes */
#define CALL_ENTRY_COUNT	1224	/* 117504 / 96 */
#define CALL_ENTRIES_TOTAL	117504

/* Message size */
#define COMM_MSG_SIZE		104	/* 0x68 bytes — the IPC message unit */

/* Channel pool */
#define CHANNEL_SLOT_COUNT	32
#define CHANNEL_SLOT_DWORDS	11

/* Component pool */
#define COMPONENT_COUNT		40
#define COMPONENT_SIZE_DWORDS	204	/* DWORDs per component (816 bytes) */

/* Session ID */
#define SESSION_ID_MASK		0x3FFFFFFF
#define SESSION_ID_INVALID	(-1)

/* Timeouts */
#define SEND_TIMEOUT_JIFFIES	500	/* ~5 seconds at HZ=100 */

/* Message types (cpu_comm_msg_cb switch) */
#define MSG_TYPE_CALL		0
#define MSG_TYPE_RETURN		1
#define MSG_TYPE_CALL_ACK	2
#define MSG_TYPE_RETURN_ACK	3

/* Message flags (offset 0x06 in comm_msg, u16) */
#define MSG_FLAG_NOTIFY		BIT(0)	/* async, no wait for response */
#define MSG_FLAG_RETURN_ACK	BIT(1)	/* expects return acknowledgement */
#define MSG_FLAG_SENT		BIT(2)	/* message has been dispatched */

/* SendCommLow interrupt type */
#define INTR_TYPE_SEND		2

/* pcpu_comm_dev allocation */
#define CPU_COMM_DEV_SIZE	119648	/* 0x1D360 bytes */

/* ══════════════════════════════════════════════════════════════
 * Shared Memory Layout Offsets (from ShMemAddrBase)
 * Base physical: 0x4E300000, Size: 5MB (0x500000)
 * ══════════════════════════════════════════════════════════════ */

#define SHMEM_OFF_MAGIC1	144	/* 0x0090 */
#define SHMEM_OFF_MAX_CPU	19672	/* 0x4CD8 */
#define SHMEM_OFF_VA_OFFSET	19688	/* 0x4CE8 */
#define SHMEM_OFF_LIST_BASE	19724	/* 0x4D0C — first linked list */
#define SHMEM_OFF_REC_ENTRIES	19888	/* 0x4DB0 — addRec() entries */
#define SHMEM_OFF_MAGIC2	30136	/* 0x75B8 */
#define SHMEM_OFF_CALL_ENTRIES	30144	/* 0x75C0 */
#define SHMEM_OFF_COMP_POOL	147656	/* 0x240E8 */
#define SHMEM_OFF_MSG_POOL	180328	/* 0x2C068 */
#define SHMEM_OFF_SMM_HEAP	183536	/* 0x2CCF0 */

/* ══════════════════════════════════════════════════════════════
 * FIFO — Ring buffer for shared-memory message passing
 * Single-producer single-consumer (ARM writes, MIPS reads or vice versa)
 * ══════════════════════════════════════════════════════════════ */

struct comm_fifo {
	u32 rd_idx;		/* [0] read position */
	u32 wr_idx;		/* [1] write position */
	u32 peak_count;		/* [2] stats: max occupancy seen */
	u32 track_stats;	/* [3] 1 = track peak, 0 = track min */
	u32 capacity;		/* [4] max items (one wasted for full detect) */
	u32 item_size;		/* [5] bytes per item */
	u32 base_addr;		/* [6] pointer to item array (may be phys or virt) */
	u32 reserved[9];	/* [7-15] */
	u32 debug_flags;	/* [16] bit0 = verbose logging */
};

/* ══════════════════════════════════════════════════════════════
 * IPC Message — 104 bytes (0x68), the fundamental unit of communication
 * Sits in shared memory FIFO slots
 * ══════════════════════════════════════════════════════════════ */

struct comm_msg {
	u8  src_cpu;		/* [0x00] source CPU (0=ARM, 1=MIPS) */
	u8  dst_cpu;		/* [0x01] destination CPU */
	u16 component_id;	/* [0x02] target component on destination */
	u16 slot_index;		/* [0x04] FIFO slot index */
	u16 flags;		/* [0x06] MSG_FLAG_* */
	u16 cmd_type;		/* [0x08] command/message type */
	u16 flags2;		/* [0x0A] additional flags */
	u32 session_id;		/* [0x0C] 30-bit counter | (cpu_id << 30) */
	u8  sequence;		/* [0x10] sequence number (max 19) */
	u8  reserved1[3];	/* [0x11] */
	u32 param;		/* [0x14] parameter */
	u32 wait_ptr_lo;	/* [0x18] wait object pointer (low) */
	u32 wait_ptr_hi;	/* [0x1C] wait object pointer (high) */
	u32 payload[18];	/* [0x20-0x67] command-specific payload */
};

static_assert(sizeof(struct comm_msg) == COMM_MSG_SIZE,
	      "comm_msg must be exactly 104 bytes");

/* ══════════════════════════════════════════════════════════════
 * MsgFIFO — Named FIFO wrapper used throughout cpu_comm
 * ══════════════════════════════════════════════════════════════ */

struct msg_fifo {
	char name[FIFO_NAME_LEN];	/* [0x00] display name */
	u8  mode;			/* [0x30] */
	u8  pad1[3];
	u32 count;			/* [0x34] */
	u32 head;			/* [0x38] linked list head (self-ref init) */
	u32 tail;			/* [0x3C] linked list tail */
	u32 reserved1;			/* [0x40] */
	u32 owner;			/* [0x44] = mode param from InitMsgFIFO */
	u32 wait_head;			/* [0x48] secondary list head */
	u32 wait_tail;			/* [0x4C] secondary list tail */
};

/* ══════════════════════════════════════════════════════════════
 * Wait entry — tracks pending RPC calls awaiting response
 * ══════════════════════════════════════════════════════════════ */

struct comm_wait {
	u32 session_id;		/* matching session for response */
	u32 pid;		/* requesting process PID */
	struct semaphore sem;	/* signaled when response arrives */
	/* ... additional fields TBD from deeper RE */
};

/* ══════════════════════════════════════════════════════════════
 * CommShareSeq — per CPU-pair, per direction shared sequence
 * Manages FIFO slots for call/return messages
 * ══════════════════════════════════════════════════════════════ */

struct comm_share_seq {
	u8  local_cpu;		/* [0x00] */
	u8  remote_cpu;		/* [0x01] */
	u8  direction;		/* [0x02] 0=call, 1=return */
	u8  pad[5];
	u8  status;		/* [0x08] */
	u8  pad2[7];
	u8  max_items;		/* [0x10] = 20 */
	u8  pad3[3];
	u32 session_id;		/* [0x14] = -1 initially */
	u8  pad4[0x54];
	u8  max_items2;		/* [0x68] = 20 */
	u8  status2;		/* [0x69] */
	u8  pad5[2];
	u32 session_id2;	/* [0x6C] = -1 */
	u8  pad6[8];
	u32 field_78;		/* [0x78] */
	u32 field_7c;		/* [0x7C] */
	u32 field_80;		/* [0x80] */
	u32 sem;		/* [0x84] = 1 (semaphore count) */
	u32 max_entries;	/* [0x88] = 21 */
	u32 capacity;		/* [0x8C] = 4 */
	u32 phy_addr;		/* [0x90] physical addr of FIFO buffer */
	u32 field_94;		/* [0x94] = 0 */
	char name[32];		/* [0x98] "FreeCall" or "FreeReturn" */
	u32 field_b8;		/* [0xB8] = 0 */
	u8  pad7[4];
	/* [0xC0] FIFO ring buffer: 20 entries × 104 bytes each */
	u8  fifo_data[20 * COMM_MSG_SIZE];
	/* [0x168..] call entry table: 20 × 104 bytes */
};

/* ══════════════════════════════════════════════════════════════
 * CommSocket — per-CPU communication state
 * Global array s_CommSockt[2], 4992 bytes each
 * ══════════════════════════════════════════════════════════════ */

struct comm_socket {
	u32 cpu_id;			/* [0x00] */
	u32 pad1;
	u32 status;			/* [0x08] */
	u32 sem_count;			/* [0x0C] = 1 */
	u32 list0_head;			/* [0x10] */
	u32 list0_tail;			/* [0x14] */
	u32 pad2[2];
	u32 list1_head;			/* [0x20] */
	u32 list1_tail;			/* [0x24] */
	struct msg_fifo send_cmd_fifo;	/* [0x28] "SendCmdWaitList" */
	/* ... rest TBD: wait entries, return list, additional FIFOs */
	u8  _rest[COMM_SOCKET_SIZE - 0x78];
};

/* ══════════════════════════════════════════════════════════════
 * Channel — maps component_id + cpu pair to a FIFO
 * ══════════════════════════════════════════════════════════════ */

struct comm_channel {
	u32 channel_id;		/* component_id | (cpu << 4) */
	u32 session_id;
	u32 pad[CHANNEL_SLOT_DWORDS - 2];
};

struct channel_pool {
	u32 count;			/* [0] active channels */
	u32 pad1;
	u32 sem;			/* [2] = 1 */
	u32 active_head;		/* [3] */
	u32 active_tail;		/* [4] */
	u32 free_count;			/* [5] */
	u32 free_sem;			/* [6] = 1 */
	u32 free_head;			/* [7] */
	u32 free_tail;			/* [8] */
	struct comm_channel slots[CHANNEL_SLOT_COUNT];
};

/* ══════════════════════════════════════════════════════════════
 * Component — registered handler for a specific component ID
 * ══════════════════════════════════════════════════════════════ */

struct comm_component {
	u8  pad[10];
	u8  index;			/* [0x0A] component index */
	u8  pad2[17];
	u16 state;			/* [0x1C] = 2 initially */
	u8  pad3[2];
	u32 spinlock_id;		/* [0x20] = 255 (unassigned) */
	u8  pad4[8];
	u32 field_30;			/* [0x30] = 0 */
	u32 field_34;			/* [0x34] = 0 */
	/* ... sub-entries with 12-DWORD stride */
	u8  _rest[816 - 0x38];
};

struct component_pool {
	u32 spinlock_id;		/* from comm_ReqestSpinLock */
	u8  pad[4];
	u32 max_components;		/* = 40 */
	u8  pad2[4];
	struct comm_component components[COMPONENT_COUNT];
};

/* ══════════════════════════════════════════════════════════════
 * MessagerPool — event message routing
 * ══════════════════════════════════════════════════════════════ */

struct messager_pool {
	u32 count;
	u32 spinlock_id;		/* from comm_ReqestSpinLock */
	/* ... TBD from deeper RE */
};

/* ══════════════════════════════════════════════════════════════
 * HW Spinlock entry (in shared memory)
 * ══════════════════════════════════════════════════════════════ */

struct comm_spinlock {
	u8  type;		/* [0] lock type */
	u8  pad1;
	u8  status;		/* [2] 0 = acquired */
	u8  owner_cpu;		/* [3] 2 = free, 0 = ARM, 1 = MIPS */
	u32 ref_count;		/* [4] should be 0 when free */
	u32 hwlock_id;		/* [8] 255 = unassigned */
};

/* ══════════════════════════════════════════════════════════════
 * SMM — Shared Memory Manager (heap in shared memory)
 * ══════════════════════════════════════════════════════════════ */

struct smm_heap_header {
	u32 free_list_head;	/* physical addr of free list */
	u32 free_list_cur;	/* current position */
	u32 page_count;		/* total pages */
	u8  pad[0xA8];
	u32 total_capacity;	/* [0xB4] byte size */
	u32 raw_size;		/* [0xB8] */
	u32 phy_base;		/* [0xBC] physical address */
};

/* ══════════════════════════════════════════════════════════════
 * Top-level shared memory layout
 * ══════════════════════════════════════════════════════════════ */

struct cpu_comm_shmem {
	u8  _header[144];				/* [0x0000] */
	u32 magic1;					/* [0x0090] = 0xDEADBEEF */
	u8  _pad1[19524];				/* to 0x4CD8 */
	u32 max_cpu_count;				/* [0x4CD8] = 3 */
	u8  _pad2[12];
	u32 va_offset;					/* [0x4CE8] ShMemAddrVir - ShMemAddr */
	u32 _pad3;					/* [0x4CEC] */
	u8  _pad4[28];					/* to 0x4D0C */
	/* [0x4D0C..0x4DB0] linked lists (5 pairs × 8 bytes) */
	u32 lists[40];
	/* [0x4DB0..0x75B8] rec entries + wait/share seq structures */
	u8  _seq_area[30136 - 19888];
	u32 magic2;					/* [0x75B8] = 0xDEADBEEF */
	/* [0x75C0] call entries: 1224 × 96 bytes */
	u8  call_entries[CALL_ENTRIES_TOTAL];
	/* [0x240E8] component pool */
	u8  _comp_pool_raw[SHMEM_OFF_MSG_POOL - SHMEM_OFF_COMP_POOL];
	/* [0x2C068] messager pool */
	u8  _msg_pool_raw[SHMEM_OFF_SMM_HEAP - SHMEM_OFF_MSG_POOL];
	/* [0x2CCF0] SMM heap (extends to end of 5MB) */
	/* u8 smm_heap[]; — variable size */
};

/* ══════════════════════════════════════════════════════════════
 * Per-device kernel state (NOT in shared memory)
 * Allocated by cpu_comm_init: 119648 bytes (0x1D360)
 * ══════════════════════════════════════════════════════════════ */

struct cpu_comm_dev {
	u32 field_00;
	u32 field_04;
	u32 sem1;			/* [0x08] = 1 */
	u32 pad1;
	u32 sem2;			/* [0x10] semaphore (down_interruptible) */
	u8  pad2[8];
	u32 list_call_head;		/* [0x18] linked list */
	u32 list_call_tail;		/* [0x1C] */
	u32 field_20;
	u32 sem3;			/* [0x24] = 1 */
	u32 list_return_head;		/* [0x28] linked list */
	u32 list_return_tail;		/* [0x2C] */
	struct channel_pool channels;	/* [0x30] channel pool */
	/* ... work queues, counters, etc. */
	u8  _work_queues[CPU_COMM_DEV_SIZE - 0x30 - sizeof(struct channel_pool)];
};

/* ══════════════════════════════════════════════════════════════
 * Global state (module-level)
 * ══════════════════════════════════════════════════════════════ */

/* These mirror the globals from the stock module */
extern u32 ShMemAddr;		/* physical base of shared memory */
extern u32 ShMemSize;		/* size (5MB) */
extern u32 ShMemAddrVir;	/* kernel virtual after vmap */
extern u32 ShMemAddrBase;	/* uncacheable mapping base (= ShMemAddrVir) */
extern struct cpu_comm_dev *pcpu_comm_dev;

/* Secondary shared memory (optional, for extended SMM) */
extern u32 ShMemAddr1;
extern u32 ShMemSize1;

/* HW spinlock handles */
extern void *hwlocks[HW_SPINLOCK_COUNT * 2]; /* [0..13]=handles, [14..27]=counters */

/* MIPS app-ready assumption flag (cache coherency workaround) */
extern int mips_app_ready_assumed;

/* CommSocket array */
extern u32 s_CommSockt[];	/* [2 * COMM_SOCKET_SIZE/4] */

/* Call session ID counter */
extern u32 s_CallSessionId;

/* Interrupt semaphore array */
extern u32 comm_intrsem[];

/* Suspend flag */
extern int cpu_comm_suspend_flag;

/* ══════════════════════════════════════════════════════════════
 * Function declarations — grouped by source file
 * ══════════════════════════════════════════════════════════════ */

/* cpu_comm_hw.c — hardware abstraction */
int  cpu_comm_hw_init(void);
void cpu_comm_hw_cleanup(void);
int  comm_ReadRegWord(u32 reg_addr);
void comm_WriteRegWord(u32 reg_addr, u32 value);
int  comm_ReadShareReg(int reg_id);
void comm_WriteShareReg(int reg_id, u32 value);
int  comm_InitHwSpinLock(void);
int  comm_InitSpinLock(int dummy);
int  comm_ReqestSpinLock(void);
int  comm_ReleaseSpinLock(int lock_id);
void comm_SpinLock(int lock_id);
void comm_SpinUnLock(int lock_id, int dummy);
int  comm_TrySpinLock(int lock_id);
void comm_SpinLockMutex(int lock_id);
void comm_SpinLocksetType(int lock_id, int type);
int  spinlockhwReg(int lock_id);
int  tryspinlockhwReg(int lock_id);
void spinUnlockhwReg(int lock_id);
int  getShareRegbyID(int reg_id);
int  getInterruptRegChannel(u32 cpu, u32 channel);
void ResetCommInterrupt(int dummy);

/* cpu_comm_fifo.c — ring buffer FIFO */
void InitMsgFIFO(void *fifo, const char *prefix, const char *suffix, int mode);
u32  fifo_getItemWr(u32 *fifo);
u32  fifo_requestItemWr(u32 *fifo);
u32  fifo_getItemRd(u32 *fifo);
u32  fifo_ItemRdNext(u32 *fifo);
int  fifo_getCount(u32 *fifo);
int  fifo_isNearlyFull(u32 *fifo, int margin);
void fifo_setmode(u32 *fifo, int mode);
void fifo_show(u32 *fifo);

/* cpu_comm_mem.c — shared memory init + SMM allocator */
int  InitCommMem(int mode);
void InitCommSeqMem(u32 cpu_id);
void InitCommShareSeqMem(u32 cpu_id, u32 direction);
void InitComponentPool(void *pool);
void InitMessagerPool(void *pool);
int  Trid_SMM_Init(u32 base, u32 size);
u32  Trid_SMM_Malloc(u32 size);
u32  Trid_SMM_MallocAttr(u32 size);
int  Trid_SMM_Free(u32 mid_addr);
void Trid_SMMCleanUpInCPUReset(void);
void comm_SpinLockCleanUpInCPUReset(u32 cpu_id);
void cleanupFDCPUReset(u32 cpu_id);
u32  Mid2Phy(u32 cpu, u32 mid);
u32  Phy2Mid(u32 phy);
u32  Mid2Vir(u32 cpu, u32 mid);
u32  Vir2Mid(u32 cpu, u32 vir);

/* cpu_comm_proto.c — communication protocol */
void init_intrsem(int dummy);
int  SendCommLow(u8 *share_seq, u32 slot, u8 msg_type, u32 param, u32 sem_ptr);
int  SendComm2CPUEx(u32 msg, u32 target_cpu, int from_user);
int  SendComm2CPU(u32 msg, int from_user);
void SendAckLow(void *data, u32 a2, u8 a3, u32 a4, u32 a5);
void command_action(u32 remote_cpu, u32 direction);
void comm_Action(int type, int cpu);
void ack_action(u32 cpu, u32 direction);
int  queueAction(u32 direction, u32 cpu);  /* BUG-6 fix: direction first */

/* cpu_comm_proto.c — message handlers */
void cpu_comm_handle_CPU2_call(int a1, int a2, int cpu);
void cpu_comm_handle_CPU2_return(int a1, int a2, int cpu);
void cpu_comm_handle_CPU2_callACK(int a1, int a2, int cpu);
void cpu_comm_handle_CPU2_returnACK(int a1, int a2, int cpu);

/* cpu_comm_channel.c — channel management */
void ChannelPoolInit(void *pool);
int  Comm_AddNewChannel(void *pool, u16 comp_id, u32 cpu);
int  Comm_RemoveChannel(void *pool, u16 comp_id, u32 cpu);
int  Comm_QueryChannel(void *pool, u32 channel_id, u32 *result);
void Comm_Add2NewCallFifo(void *pool, u32 *cmd_fifo, u32 call_entry);
int  Comm_GetCallbyChannel(void *pool, u32 channel_id, u32 *result);

/* cpu_comm_channel.c — wait/session management */
int  AddtoWaitComm(void *list, u32 wait_entry);
int  GetFreeWaitComm(void *list, u32 **result);
int  GetWaitbySessionId(void *list, u32 session_id, u8 *result);
int  FindWaitBySessionId(void *list, u32 session_id, u32 **result);
void ReleaseWaitComm(u32 cpu_id, u32 wait_entry);
int  HasInList(void *list, void *item);
int  Comm_GetFreeCall(void *share_seq);
void Comm_ReleaseFreeCall(void *share_seq, void *call);
int  AddReturn2Fifo(u32 *fifo, void *data);
void returnPipeLine(void *data);
int  GetReturnbySessionId(u32 session_id, u32 cpu, u32 *result);

/* cpu_comm_rpc.c — high-level RPC API */
void *getComponentPool(void);
void *getMsgPool(void);
int  msgAddListener(void *pool, void *listener);
int  msgRemoveListener(void *pool, void *listener);
int  msgEventName2Index(const char *name);
int  CPUComm_Call(void *msg_buf, void *params, void *result);
int  CPUComm_CallEx(int comp_id, int *params, u32 *result);
int  CPUComm_Notify(void *name, void *params);
int  CPUComm_InstallRoutine(void *data);
int  CPUComm_UnInstallRoutine(void *data);
int  Comm_Name2ID(const char *name);
int  FindRoutine(u32 comp_search, void *msg_buf);
int  FindRoutineEx(u32 comp_search, void *msg_buf, u32 *result);
int  AddInRoutine(void *data);
int  RemoveRoutine(void *data);
void RemovePidRoutines(pid_t pid);
void RoutineCleanupInCPUReset(void *data);
void Comm_Add2Call2WQ(void *data);
void comm_CallWorkAction(void *data);
void comm_WorkAction(struct work_struct *work);

/* cpu_comm_dev.c — kernel interface */
int  cpu_comm_init(int mode);
void cpu_comm_cleanup(void);
int  cpu_comm_open(struct inode *inode, struct file *file);
long cpu_comm_ioctl(struct file *file, unsigned int cmd, unsigned long arg);
int  cpu_comm_mmap(struct file *file, struct vm_area_struct *vma);
int  cpu_comm_suspend(int flags);
int  cpu_comm_resume(int flags);
void cpu_comm_msg_cb(int type, int direction);
void cpu_comm_proc_init(void);
void cpu_comm_proc_term(void);

/* cpu_comm_dev.c — CPU status */
void setCPUReady(u32 cpu_id);
void setCPUnotReady(u32 cpu_id);
void setCPUAppReady(u32 cpu_id);
void setCPUReset(u32 cpu_id, unsigned int phase);  /* phase: NULL=flags, (char*)1=cleanup */
int  isCPUReady(u32 cpu_id);
int  isCPUAppReady(u32 cpu_id);
int  IsCPUReset(u32 cpu_id);
int  IsCurCPURest(void);
int  isCPUNoticeReqed(u32 cpu_id);
void clearCPUNoticeReqed(u32 cpu_id);
void checkNoticeReqedJob(void);

/* helpers */
u32  getCurCPUID(int dummy);
const char *getCurCPUName(int dummy);
const char *getCPUIDName(u32 cpu_id);
u32  CPUId2Index(u32 cpu_id);
u32  getSeq(u32 cpu_id);
u32  getShareSeq(u32 cpu, u32 remote, u32 dir);
u32  getShareSeqR(u32 cpu, u32 dir);
u32  getShareSeqW(u32 cpu, u32 dir);

/* export for other modules (tvtop, decd, etc.) */
void sunxi_cpu_comm_send_intr_to_mips(u32 cpu, u32 type, u32 value);

/* H713 direct msgbox IRQ handler (replaces mailbox framework) */
int  cpu_comm_msgbox_request_irq(int irq, void *callback);
void cpu_comm_msgbox_free_irq(void);
void cpu_comm_msgbox_probe_start(void);	/* legacy stub */
void cpu_comm_msgbox_probe_stop(void);	/* legacy stub */

#endif /* _CPU_COMM_H_ */
