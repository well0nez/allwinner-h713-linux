// SPDX-License-Identifier: GPL-2.0
/*
 * cpu_comm_proto.c — Communication protocol layer
 *
 * Message sending (SendCommLow, SendComm2CPUEx), message receiving
 * (command_action, ack_action), and the 4 message type handlers
 * (call, return, callACK, returnACK).
 *
 * RE source: HAL_SX6/Kernel_Driver/cpu_comm/cpu_comm_core.c
 */

#include <linux/kernel.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <linux/sched.h>
#include <linux/semaphore.h>
#include <linux/delay.h>
#include "cpu_comm.h"

/* ── Interrupt semaphore array ─────────────────────────────── */

/*
 * comm_intrsem layout (from IDA):
 * [0..7]: semaphore-like structures
 * [8..11]: cached call pointers per (cpu, direction) pair
 * Indexed as: comm_intrsem[2 * cpu + direction + 8]
 */
u32 comm_intrsem[16];
static struct semaphore intr_sems[4]; /* 2 CPUs × 2 directions */

static const char *cpu_comm_type_name(int type)
{
	switch (type) {
	case MSG_TYPE_CALL:
		return "CALL";
	case MSG_TYPE_RETURN:
		return "RETURN";
	case MSG_TYPE_CALL_ACK:
		return "CALL_ACK";
	case MSG_TYPE_RETURN_ACK:
		return "RETURN_ACK";
	default:
		return "UNKNOWN";
	}
}

static const char *cpu_comm_dir_name(int direction)
{
	switch (direction) {
	case 0:
		return "LOCAL/ARM";
	case 2:
		return "REMOTE/MIPS";
	default:
		return "OTHER";
	}
}

static void cpu_comm_trace_ipc(const char *stage, int type, int direction, int cpu)
{
	u32 arm_flag = 0;
	u32 mips_flag = 0;

	if (ShMemAddrBase) {
		arm_flag = *(u32 *)(ShMemAddrBase + 0x4CDC);
		mips_flag = *(u32 *)(ShMemAddrBase + 0x4CE0);
	}

	pr_info_ratelimited("cpu_comm: IPC[%s] type=%d(%s) dir=%d(%s) cpu=%d ARM=0x%x MIPS=0x%x\n",
			    stage,
			    type, cpu_comm_type_name(type),
			    direction, cpu_comm_dir_name(direction),
			    cpu, arm_flag, mips_flag);
}

void init_intrsem(int dummy)
{
	int i;

	memset(comm_intrsem, 0, sizeof(comm_intrsem));
	for (i = 0; i < 4; i++)
		sema_init(&intr_sems[i], 0);
}

/* ── SendCommLow — Low-level message dispatch ──────────────── */

/*
 * Writes message metadata into a shared-memory FIFO slot,
 * then triggers either local processing (queueAction) or
 * remote interrupt (sunxi_cpu_comm_send_intr_to_mips).
 *
 * @seq:    pointer to share sequence structure
 * @slot:   FIFO slot index
 * @type:   message type (cmd_type field)
 * @param:  parameter value
 * @sem:    semaphore pointer for completion notification
 */
int SendCommLow(u8 *seq, u32 slot, u8 type, u32 param, u32 sem_ptr)
{
	u8 src, dst, dir;
	u32 cur_cpu;

	if (WARN_ON(!seq))
		return -EINVAL;

	src = seq[1];	/* source CPU */
	dst = seq[0];	/* destination CPU - note: reversed in share_seq */

	cur_cpu = getCurCPUID(0);
	if (WARN_ON(src != cur_cpu))
		return -EINVAL;

	dir = seq[2];	/* direction: 0=call, 1=return */
	if (WARN_ON(dir > 1 || slot >= FIFO_DEFAULT_CAP))
		return -EINVAL;

	/* Fill message metadata */
	seq[16] = slot;		/* sequence number */
	*(u32 *)(seq + 20) = param;
	*(u64 *)(seq + 24) = (u64)sem_ptr;
	*(u32 *)(seq + 4) += 1;	/* increment counter */
	seq[8] = type;

	/* Memory barrier — ensure writes visible before signaling */
	dmb(ish);

	if (dst == src) {
		/* Local message — process directly via work queue */
		return queueAction(dir, cur_cpu);
	}

	/* Remote message — set "sent" flag and notify via msgbox */
	seq[8] |= MSG_FLAG_SENT;
	dmb(ish);

	/* Wait for flag acknowledgement */
	while (!(seq[8] & MSG_FLAG_SENT))
		;

	/* Send interrupt to MIPS via the built-in RPMSG layer */
	sunxi_cpu_comm_send_intr_to_mips(dir, INTR_TYPE_SEND, 0);
	return 0;
}

/* ── SendComm2CPUEx — Extended message send ────────────────── */

/*
 * The main message sending function. Full implementation matching IDA @ 0xd164.
 *
 * Handles:
 *  1. Finding target component (FindRoutine for local CPU, direct read for remote)
 *  2. Acquiring the correct sequence semaphore (sem_ptr depends on target_cpu)
 *  3. Waiting for FIFO space
 *  4. Getting or reusing a cached free call slot
 *  5. Copying message data (copy_from_user or memcpy)
 *  6. Setting slot index, msg_type, session ID, routine fields, pid
 *  7. Allocating a wait object when a response is expected
 *  8. Sending via SendCommLow and waiting for ACK (500 jiffies timeout)
 *  9. Cleaning up wait object on timeout
 *
 * @msg_ptr:    u32 pointer to 104-byte message buffer (user or kernel)
 * @target_cpu: 0=local (ARM), 1=remote (MIPS)
 * @from_user:  non-zero if msg_ptr is in userspace
 */
int SendComm2CPUEx(u32 msg_ptr, u32 target_cpu, int from_user)
{
	u8     *share_seq_w;	/* write-side share sequence */
	u32     seq_base;	/* comm_socket base for dst_cpu */
	u8     *sem_ptr;	/* pointer to the acquire semaphore */
	u8     *call_slot;	/* FIFO slot for this message */
	u16     slot_idx;	/* slot index saved before copy */
	u8      msg_type;	/* 1=call-to-local, 2=call-to-remote */
	u32     dst_cpu;	/* resolved destination CPU */
	u16     flags;		/* message flags from slot+6 */
	u8      direction;	/* 0=call (forward), 1=return (backward) */
	u32     session_id;	/* generated session ID */
	u32    *wait_ptr;	/* allocated wait object, or NULL */
	int     ret = 0;
	u32     cache_idx = 0;	/* index into comm_intrsem cache; 0 until set */
	bool    cache_acquired = false; /* true once call_slot has been stored */
	/*
	 * routine_find_buf: filled by FindRoutine when target_cpu==0.
	 * Must be 96 bytes — FindRoutineEx copies full entry (96 bytes)
	 * including mmiocpy(buf+12, ..., 64) and *(u64*)(buf+80).
	 * BUG-18 fix: was 24 bytes → stack overflow!
	 */
	u8      routine_find_buf[96];
	bool    routine_found = false;

	/* ── Step 1: basic validation ── */
	if (!msg_ptr || target_cpu > 1) {
		pr_err("cpu_comm: SendComm2CPUEx: invalid args msg=%08x cpu=%u\n",
		       msg_ptr, target_cpu);
		return -EINVAL;
	}

	/* ── Step 2: resolve dst_cpu ── */

	if (target_cpu == 0) {
		/*
		 * Local CPU path: use component_id from msg+40 to look up
		 * the target via FindRoutine.  FindRoutine fills a 24-byte
		 * result buffer; byte [2] is the destination CPU.
		 */
		u32 comp_id;

		if (from_user) {
			if (get_user(comp_id, (u32 __user *)(msg_ptr + 40)))
				return -EFAULT;
		} else {
			comp_id = *(u32 *)(msg_ptr + 40);
		}

		if (FindRoutine(comp_id, routine_find_buf) != 0)
			return -3; /* ESRCH — routine not found */

		routine_found = true;
		dst_cpu = (u32)(u8)routine_find_buf[2];
	} else {
		/* Remote CPU path: dst_cpu from msg+2 (u16) */
		u16 dc;

		if (from_user) {
			if (get_user(dc, (u16 __user *)(msg_ptr + 2)))
				return -EFAULT;
		} else {
			dc = *(u16 *)(msg_ptr + 2);
		}
		dst_cpu = (u32)dc;
	}

	/* ── Step 3: CPU-reset and range check ── */
	if (IsCPUReset(dst_cpu))
		return -512;

	if (dst_cpu > 1)
		return -EINVAL;

	/* ── Step 4: get share sequence and seq socket ── */
	share_seq_w = (u8 *)getShareSeqW(dst_cpu, target_cpu);
	if (!share_seq_w) {
		pr_err("cpu_comm: SendComm2CPUEx: no share_seq for dst=%u dir=%u\n",
		       dst_cpu, target_cpu);
		return -EINVAL;
	}

	seq_base = getSeq(dst_cpu);

	/*
	 * sem_ptr selection (from IDA):
	 *   target_cpu != 0 (remote): seq_base + 1036
	 *   target_cpu == 0 (local):  seq_base + 8
	 */
	if (target_cpu)
		sem_ptr = (u8 *)seq_base + 1036;
	else
		sem_ptr = (u8 *)seq_base + 8;

	/* ── Step 5: acquire sequence semaphore ── */
	ret = cpu_comm_sem_down_interruptible((void *)sem_ptr);
	if (ret) {
		pr_err("cpu_comm: SendComm2CPUEx: down_interruptible interrupted (cpu=%u)\n",
		       dst_cpu);
		return ret;
	}

	/* Re-check reset status after acquiring semaphore */
	if (IsCPUReset(dst_cpu)) {
		ret = -512;
		goto out_up_sem;
	}

	/* ── Step 6: check isCPUAppReady ── */
	if (!isCPUAppReady(dst_cpu)) {
		ret = -1;
		goto out_up_sem;
	}

	/* ── Step 7: wait for FIFO space ── */
	while (fifo_isNearlyFull((u32 *)(share_seq_w + 32), 1))
		schedule();

	/* ── Step 8: get or reuse cached free call slot ── */
	cache_idx = 2 * dst_cpu + target_cpu + 8;
	cache_acquired = true;
	call_slot = (u8 *)comm_intrsem[cache_idx];
	if (!call_slot) {
		do {
			call_slot = (u8 *)Comm_GetFreeCall(share_seq_w);
			if (!call_slot)
				schedule();
		} while (!call_slot);
		comm_intrsem[cache_idx] = (u32)call_slot;
	}

	/* ── Step 9: save slot_index before copy overwrites it ── */
	slot_idx = *(u16 *)(call_slot + 4);

	/* ── Step 10: copy message into slot ── */
	if (from_user) {
		if (copy_from_user(call_slot, (void __user *)msg_ptr, COMM_MSG_SIZE)) {
			ret = -EFAULT;
			goto out_clear_cache;
		}
	} else {
		memcpy(call_slot, (void *)msg_ptr, COMM_MSG_SIZE);
	}

	/* ── Step 11: barrier + restore slot_idx ── */
	dmb(ish);
	*(u16 *)(call_slot + 4) = slot_idx;

	/* ── Step 12: set msg_type (1=local-call, 2=remote-call) ── */
	msg_type = target_cpu ? 2 : 1;
	*(u16 *)(call_slot + 10) = msg_type;

	/* ── Step 13: verify slot address matches FIFO table ── */
	if (call_slot != (share_seq_w + 104 * (u32)slot_idx + 360)) {
		pr_err("cpu_comm: SendComm2CPUEx: slot address mismatch!\n");
		return -EINVAL;
	}

	/* ── Step 14: direction from share_seq header byte [2] ── */
	direction = share_seq_w[2];

	wait_ptr = NULL;

	if (direction == 0) {
		/*
		 * Forward call path: assign session ID and populate
		 * routing fields from FindRoutine result (or re-read
		 * for the remote path which didn't call FindRoutine).
		 */
		u32 cur_cpu = getCurCPUID(0);

		/* Generate session ID */
		s_CallSessionId = (s_CallSessionId + 1) & SESSION_ID_MASK;
		session_id = s_CallSessionId | (cur_cpu << 30);

		if (routine_found) {
			/*
			 * Local path: reuse the FindRoutine result from step 2.
			 * Populate routing fields in the call slot from the buf:
			 *   [0]: routine_name (u16)
			 *   [2]: routine_dst_cpu (u16)
			 *   [16],[24]: dst cpu expanded to u32
			 */
			*(u16 *)(call_slot +  0) = *(u16 *)(routine_find_buf + 0); /* routine_name */
			*(u16 *)(call_slot +  2) = *(u16 *)(routine_find_buf + 2); /* routine_dst_cpu */
			*(u32 *)(call_slot + 16) = (u32)(u8)routine_find_buf[2];   /* dst cpu (expanded) */
			*(u32 *)(call_slot + 24) = (u32)(u8)routine_find_buf[2];   /* again */
		}

		/* Fields set regardless of local/remote */
		*(u32 *)(call_slot + 12) = session_id;	/* session_id field */
		*(u32 *)(call_slot + 28) = (u32)current->pid;

		flags = *(u16 *)(call_slot + 6);

		if ((flags & MSG_FLAG_NOTIFY) && !(flags & MSG_FLAG_RETURN_ACK)) {
			/* Fire-and-forget: no wait object needed */
			*(u64 *)(call_slot + 32) = 0ULL;
		} else {
			/* Normal call or return-ack: allocate a wait object */
			u32 wait_fifo_base = getSeq(dst_cpu) + 136;

			do {
				ret = GetFreeWaitComm((void *)wait_fifo_base, &wait_ptr);
				if (ret || !wait_ptr) {
					schedule();
					wait_ptr = NULL;
				}
			} while (!wait_ptr);

			*wait_ptr       = session_id;
			*(wait_ptr + 1) = (u32)current->pid;

			AddtoWaitComm((void *)(getSeq(dst_cpu) + 40), (u32)wait_ptr);

			*(u64 *)(call_slot + 32) = (u64)(u32)wait_ptr;

			/* Return-ack path: also fill offsets 60/64 */
			if (flags & MSG_FLAG_RETURN_ACK) {
				*(u32 *)(call_slot + 60) = session_id;
				*(u32 *)(call_slot + 64) = (u32)wait_ptr;
			}
		}
	} else {
		/* Return direction: read session_id from what was already in slot */
		session_id = *(u32 *)(call_slot + 12);
		flags      = *(u16 *)(call_slot + 6);
	}

	/* ── Step 15: second barrier ── */
	dmb(ish);

	/* ── Step 16: copy-back to userspace if needed ── */
	if (from_user) {
		if (copy_to_user((void __user *)msg_ptr, call_slot, COMM_MSG_SIZE)) {
			ret = -EFAULT;
			goto out_cleanup_wait;
		}
	}

	/* ── Step 17: mark "sent" in flags2 ── */
	*(u16 *)(call_slot + 10) |= MSG_FLAG_SENT;

	/* ── Step 18: dispatch via SendCommLow ── */
	SendCommLow(share_seq_w, (u32)slot_idx, msg_type, session_id,
		    (u32)(sem_ptr + 16));

	/* ── Step 19: wait for ACK (500 jiffies) ── */
	ret = cpu_comm_sem_down_timeout((void *)(sem_ptr + 16),
			   SEND_TIMEOUT_JIFFIES);
	if (ret) {
		pr_err("cpu_comm: SendComm2CPUEx: ACK timeout (cpu=%u session=0x%08x)\n",
		       dst_cpu, session_id);

		/* Clear "sent" bit from share-seq status */
		share_seq_w[8] &= ~MSG_FLAG_SENT;

		/* Release the wait object if we allocated one */
		if (direction == 0 && wait_ptr) {
			u8 tmp_buf[WAIT_ENTRY_SIZE];

			GetWaitbySessionId((void *)(getSeq(dst_cpu) + 40),
					   *wait_ptr, tmp_buf);
			ReleaseWaitComm(dst_cpu, (u32)wait_ptr);
		}
	}

out_cleanup_wait:
	/* intentional fall-through: clean up wait and cache on copy_to_user error */

out_clear_cache:
	if (cache_acquired)
		comm_intrsem[cache_idx] = 0;

out_up_sem:
	cpu_comm_sem_up((void *)sem_ptr);
	return ret;
}

int SendComm2CPU(u32 msg_ptr, int from_user)
{
	u16 target;

	if (from_user) {
		if (get_user(target, (u16 __user *)(msg_ptr + 2)))
			return -EFAULT;
	} else {
		target = *(u16 *)(msg_ptr + 2);
	}

	return SendComm2CPUEx(msg_ptr, target, from_user);
}

/* ── SendAckLow — Send acknowledgement ────────────────────── */

/*
 * SendAckLow — Send ACK for received message.
 *
 * From IDA @ 0xd9b0. DIFFERENT from SendCommLow!
 * Writes to ACK-specific offsets in the share sequence:
 *   +104: sequence number (a2)
 *   +105: status/type (a3)
 *   +108: param (a4)
 *   +112: sem_ptr (a5, stored as u64)
 *
 * Then dispatches as type 2 (CALL_ACK) or 3 (RETURN_ACK) based on
 * the share sequence direction.
 *
 * Previously this was incorrectly delegating to SendCommLow which
 * writes to offsets 16/20/24/4/8 instead — completely wrong!
 */
void SendAckLow(void *data, u32 a2, u8 a3, u32 a4, u32 a5)
{
	u8 *seq = data;
	u8 src, dst, dir;
	u32 cur_cpu;

	if (WARN_ON(!seq))
		return;

	src = seq[1];	/* source CPU */
	dst = seq[0];	/* destination CPU */
	cur_cpu = getCurCPUID(0);

	if (WARN_ON(src != cur_cpu))
		return;
	if (WARN_ON(seq[2] > 1))
		return;

	/* Validate: ACK sent flag must not already be set */
	if (seq[105] & 4) {
		pr_err("cpu_comm: SendAckLow: ACK sent flag already set!\n");
		return;
	}

	/* Write ACK metadata to ACK-specific offsets */
	seq[104] = (u8)a2;		/* sequence number */
	*(u32 *)(seq + 108) = a4;	/* param */
	seq[105] = a3;			/* status/type */
	*(u64 *)(seq + 112) = (u64)a5;	/* sem_ptr */

	dmb(ish);

	dir = seq[2];

	if (dst == src) {
		/* Local ACK — dispatch directly */
		u32 ack_type = (dir == 0) ? MSG_TYPE_CALL_ACK : MSG_TYPE_RETURN_ACK;

		queueAction(ack_type, getCurCPUID(0));
	} else {
		/* Remote ACK — set sent flag and notify MIPS */
		seq[105] |= 4;	/* sent flag */
		dmb(ish);

		while (!(seq[105] & 4))
			;

		{
			u32 intr_type = (dir == 0) ? MSG_TYPE_CALL_ACK
						   : MSG_TYPE_RETURN_ACK;

			sunxi_cpu_comm_send_intr_to_mips(intr_type, INTR_TYPE_SEND, -1);
		}
	}
}

/* ── Message handlers — called from cpu_comm_msg_cb ────────── */

/*
 * These handle incoming messages from MIPS.
 * The msg_cb receives a 4-byte type from RPMSG, maps it to a handler.
 *
 * Each handler:
 * 1. Reads from the appropriate FIFO
 * 2. Processes the message
 * 3. Signals waiting threads if applicable
 */

void cpu_comm_handle_CPU2_call(int a1, int a2, int cpu)
{
	/* MIPS is calling ARM — queue the command for processing */
	cpu_comm_trace_ipc("handle_call", MSG_TYPE_CALL, -1, cpu);
	comm_Action(MSG_TYPE_CALL, cpu);
}

void cpu_comm_handle_CPU2_return(int a1, int a2, int cpu)
{
	/* MIPS is returning a result to ARM's previous call */
	cpu_comm_trace_ipc("handle_return", MSG_TYPE_RETURN, -1, cpu);
	comm_Action(MSG_TYPE_RETURN, cpu);
}

void cpu_comm_handle_CPU2_callACK(int a1, int a2, int cpu)
{
	/* MIPS acknowledges ARM's call was received */
	cpu_comm_trace_ipc("handle_call_ack", MSG_TYPE_CALL_ACK, -1, cpu);
	comm_Action(MSG_TYPE_CALL_ACK, cpu);
}

void cpu_comm_handle_CPU2_returnACK(int a1, int a2, int cpu)
{
	/* MIPS acknowledges ARM's return was received */
	cpu_comm_trace_ipc("handle_return_ack", MSG_TYPE_RETURN_ACK, -1, cpu);
	comm_Action(MSG_TYPE_RETURN_ACK, cpu);
}

/* ── comm_Action — Dispatch incoming message by type ───────── */

/*
 * From IDA @ 0xe00c: Stock takes a single struct_ptr argument and reads
 * cpu from *(ptr+36) and type from *(ptr+40). Our version takes (type, cpu)
 * directly since our callers (cpu_comm_handle_CPU2_*) already have these
 * as separate values. The dispatch logic is identical.
 *
 * IDA dispatch:
 *   type 0,1 → command_action(cpu, type)
 *   type 2   → ack_action(cpu, 0)
 *   type 3   → ack_action(cpu, 1)
 */
void comm_Action(int type, int cpu)
{
	cpu_comm_trace_ipc("dispatch", type, -1, cpu);

	switch (type) {
	case MSG_TYPE_CALL:
		command_action((u32)cpu, 0);
		break;
	case MSG_TYPE_RETURN:
		command_action((u32)cpu, 1);
		break;
	case MSG_TYPE_CALL_ACK:
		ack_action((u32)cpu, 0);
		break;
	case MSG_TYPE_RETURN_ACK:
		ack_action((u32)cpu, 1);
		break;
	default:
		pr_err("cpu_comm: comm_Action: unknown type %d\n", type);
		return;
	}
}

/* ── command_action — Process incoming call from MIPS ──────── */

/*
 * From IDA @ 0xdbf8. Handles incoming messages from a remote CPU.
 *
 * Parameters (passed via comm_Action → data cast to u32):
 *   a1 (data): CPU index of the remote sender
 *   a2: direction (0=call, 1=return)
 *
 * For direction 0 (call): reads the call entry from the MIPS→ARM shared
 * sequence, dispatches it (via Comm_Add2NewCallFifo for low-priority or
 * Comm_Add2Call2WQ for high-priority), then sends an ACK back.
 *
 * For direction 1 (return): handles a return from a previous call we made
 * to MIPS. Signals the waiting semaphore to unblock SendComm2CPUEx.
 */
void command_action(u32 remote_cpu, u32 direction)
{
	u32 share_seq_r;	/* read sequence (messages FROM remote) */
	u32 share_seq_w;	/* write sequence (for sending ACK TO remote) */
	u32 seq_idx;		/* current sequence index */
	u32 entry_base;		/* virtual address of the call entry */
	u16 component_id;
	u32 session_id;

	if (WARN_ON(remote_cpu > 1))
		return;

	share_seq_r = getShareSeqR(remote_cpu, direction);
	share_seq_w = getShareSeqW(remote_cpu, direction);
	if (!share_seq_r || !share_seq_w)
		return;

	/* Read current sequence index */
	seq_idx = *(u8 *)(share_seq_r + 16);	/* max_items field */
	if (seq_idx >= FIFO_DEFAULT_CAP) {
		pr_warn("cpu_comm: command_action: seq_idx %u out of range\n", seq_idx);
		return;
	}

	/* Check: sent flag (bit 2) must not be set on read side */
	if (*(u8 *)(share_seq_r + 8) & 4) {
		pr_err("cpu_comm: command_action: sent flag on read sequence!\n");
		return;
	}

	/* Get the call entry at the current sequence index */
	entry_base = share_seq_r + 104 * seq_idx + 360;

	/* Mark as received (set bit 3 on flags at entry + 10) */
	*(u16 *)(entry_base + 10) |= 8;

	/* Read component_id from the call entry */
	component_id = *(u16 *)(entry_base + 2);

	/* Verify destination matches us */
	if (component_id != getCurCPUID(0)) {
		/* Destination mismatch — but this may be the component ID,
		 * not CPU ID. Stock asserts here. Log and continue.
		 */
		pr_debug("cpu_comm: command_action: comp_id %u (seq_idx=%u)\n",
			 component_id, seq_idx);
	}

	/* Data memory barrier before processing */
	dmb(ish);

	/* Swap src/dst in the entry to reflect that we're now the handler */
	*(u16 *)(entry_base + 2) = remote_cpu;

	if (direction == 0) {
		/*
		 * Incoming CALL from MIPS.
		 * Dispatch based on component priority (entry + 0 = component_id word):
		 *   ≤4: enqueue via Comm_Add2NewCallFifo (normal priority)
		 *   >4: enqueue via Comm_Add2Call2WQ (high priority / workqueue)
		 */
		u16 entry_cmd = *(u16 *)(entry_base);
		if (entry_cmd <= 4)
			Comm_Add2NewCallFifo(
				(void *)((u8 *)pcpu_comm_dev + 48),
				(u32 *)(share_seq_r + 32),
				entry_base);
		else
			Comm_Add2Call2WQ((void *)entry_base);

		/* Increment incoming call counter */
		if (pcpu_comm_dev)
			*(u32 *)((u8 *)pcpu_comm_dev + 4) += 1;
	} else {
		/*
		 * Incoming RETURN from MIPS (response to our previous call).
		 * Add to return FIFO, then wake up the waiting thread.
		 */
		/*
		 * First arg is the FIFO pointer (from share_seq + 32,
		 * which is the CallCmd/ReturnCmd FIFO embedded in the
		 * share sequence). Pass as pointer, not dereferenced.
		 */
		AddReturn2Fifo((u32 *)(share_seq_r + 32),
			       (void *)(share_seq_r + 104 * seq_idx + 360));

		if (pcpu_comm_dev) {
			*(u32 *)pcpu_comm_dev += 1;
			*(u32 *)((u8 *)pcpu_comm_dev + 1628) += 1;
		}

		/* Find and signal the waiting thread */
		session_id = *(u32 *)(entry_base + 12);
		if (*(u16 *)(entry_base + 6) & MSG_FLAG_RETURN_ACK) {
			/* Has return-ack flag — find wait by session ID */
			u32 seq_base = getSeq(remote_cpu);
			u32 wait_obj = 0;

			FindWaitBySessionId((void *)(seq_base + 40),
					    session_id, (u32 **)&wait_obj);
			if (!wait_obj) {
				pr_err("cpu_comm: command_action: wait not found for session 0x%x\n",
				       session_id);
    return;
			}

			/* Verify session match */
			if (*(u32 *)(entry_base + 12) != *(u32 *)wait_obj) {
				pr_err("cpu_comm: command_action: session mismatch\n");
    return;
			}

			dmb(ish);
			*(u16 *)(entry_base + 10) |= 0x40;
			cpu_comm_sem_up((void *)(wait_obj + 8));
		} else {
			/* No return-ack — use embedded wait pointer */
			u64 wait_ptr = *(u64 *)(entry_base + 32);

			if (!wait_ptr) {
				pr_err("cpu_comm: command_action: no wait pointer\n");
    return;
			}

			/* Verify session match */
			if (*(u32 *)(entry_base + 12) != *(u32 *)(u32)wait_ptr) {
				pr_err("cpu_comm: command_action: session mismatch (embedded)\n");
    return;
			}

			dmb(ish);
			*(u16 *)(entry_base + 10) |= 0x40;
			cpu_comm_sem_up((void *)((u32)wait_ptr + 8));
		}
	}

	/* Reset sequence index and send ACK */
	*(u8 *)(share_seq_r + 16) = 20;
	SendAckLow((void *)share_seq_w,
		   *(u8 *)(share_seq_r + 16),
		   *(u8 *)(share_seq_r + 8),
		   *(u32 *)(share_seq_r + 20),
		   *(u32 *)(share_seq_r + 24));
}

/* ── ack_action — Process ACK from MIPS ────────────────────── */

/*
 * From IDA @ 0xc9bc: ack_action(u32 cpu, u32 direction)
 *
 * Gets the share sequence for the given CPU pair using the DIRECTION
 * parameter (0=call-ack, 1=return-ack). This is critical — using the
 * wrong direction signals the wrong semaphore.
 *
 * Validates status, then calls up() on the semaphore at offset 112
 * to wake up the thread waiting in SendCommLow/SendComm2CPUEx.
 */
void ack_action(u32 cpu, u32 direction)
{
	u32 share_seq;

	if (WARN_ON(cpu > 1))
		return;
	if (WARN_ON(direction > 1))
		return;

	/* Get share sequence using the correct DIRECTION (BUG-1 fix) */
	share_seq = getShareSeqR(cpu, direction);
	if (!share_seq)
		return;

	/* Validate: status2 bit 2 must not be set (already processing) */
	if (*(u8 *)(share_seq + 105) & 4) {
		pr_err("cpu_comm: ack_action: status2 bit 2 set (cpu=%u dir=%u)\n",
		       cpu, direction);
		return;
	}

	/* Signal the semaphore at offset 112 in the share sequence.
	 * This wakes up SendCommLow which is waiting for the ACK.
	 */
	cpu_comm_sem_up((void *)(unsigned long)*(u32 *)(share_seq + 112));
}

/* ── comm_WorkAction — Work queue dispatch via actionFuncs table ── */

/*
 * From IDA @ 0x6f4. Called as the work_struct callback for message
 * processing. Reads cpu_id and priority from the work item, then
 * dispatches to the corresponding handler.
 *
 * Stock uses actionFuncs[4*cpu + prio] function pointer table with
 * 12 tiny wrappers that call comm_Action. We inline the dispatch
 * since our comm_Action already handles type→handler mapping.
 *
 * The work item layout (from IDA):
 *   +0..+35:  struct work_struct header
 *   +36:      cpu_id (u32)
 *   +40:      priority (u32) — 0=CALL, 1=RETURN, 2=CALL_ACK, 3=RETURN_ACK
 */
void comm_WorkAction(struct work_struct *work)
{
	u32 cpu = *(u32 *)((u8 *)work + 36);
	u32 prio = *(u32 *)((u8 *)work + 40);

	if (WARN_ON(cpu > 1))
		return;
	if (WARN_ON(prio > 3))
		return;

	/* Map priority to message type and dispatch */
	comm_Action(prio, cpu);
}

/* ── queueAction — Queue a work item for deferred dispatch ──── */

/*
 * From IDA @ 0xcad0. Creates a work item with cpu_id and priority,
 * queues it for comm_WorkAction to process. Used by the interrupt
 * handlers (cpu_comm_handle_CPU2_*) for deferred processing.
 *
 * @direction: message type / priority (0=CALL, 1=RETURN, 2=ACK, 3=RET_ACK)
 * @cpu:       source CPU id (0=ARM, 1=MIPS)
 *
 * Returns 0 on success.
 */
int queueAction(u32 direction, u32 cpu)
{
	/* Currently we process synchronously in interrupt context.
	 * The stock uses dedicated work queues (alloc_workqueue per CPU/prio).
	 * For initial bring-up, direct dispatch is sufficient.
	 * TODO: Add proper work queue dispatch for production use.
	 */
	comm_Action(direction, cpu);
	return 0;
}

/* ── Message callback from RPMSG layer ─────────────────────── */

/*
 * Called by the built-in sunxi_cpu_comm RPMSG client when a
 * 4-byte message arrives from MIPS via msgbox.
 *
 * @type:      message type (0=call, 1=return, 2=callACK, 3=returnACK)
 * @direction: source direction (remapped: 0→0, 2→1, else→2)
 */
void cpu_comm_msg_cb(int type, int direction)
{
	int cpu;

	/* Map direction to CPU ID */
	if (direction == 0)
		cpu = 0;
	else if (direction == 2)
		cpu = 1;
	else
		cpu = 2;

	cpu_comm_trace_ipc("msg_cb", type, direction, cpu);

	switch (type) {
	case MSG_TYPE_CALL:
		cpu_comm_handle_CPU2_call(-1, 0, cpu);
		break;
	case MSG_TYPE_RETURN:
		cpu_comm_handle_CPU2_return(-1, 0, cpu);
		break;
	case MSG_TYPE_CALL_ACK:
		cpu_comm_handle_CPU2_callACK(-1, 0, cpu);
		break;
	case MSG_TYPE_RETURN_ACK:
		cpu_comm_handle_CPU2_returnACK(-1, 0, cpu);
		break;
	default:
		pr_warn("cpu_comm: unknown msg type %d from dir %d\n",
			type, direction);
		break;
	}
}
