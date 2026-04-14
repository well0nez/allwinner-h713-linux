// SPDX-License-Identifier: GPL-2.0
/*
 * cpu_comm_rpc.c — High-level RPC API
 *
 * CPUComm_Call (synchronous call to MIPS), CPUComm_Notify (async),
 * routine management (InstallRoutine, UnInstallRoutine, FindRoutine).
 *
 * RE source: HAL_SX6/Kernel_Driver/cpu_comm/cpu_comm_core.c
 */

#include <linux/kernel.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <linux/workqueue.h>
#include <linux/list.h>
#include <linux/string.h>
#include <linux/io.h>

/* Stock uses mmiocpy() for shared-memory copies; mainline equivalent */
#define mmiocpy(dst, src, len) memcpy_toio((void __iomem *)(dst), (src), (len))
#include "cpu_comm.h"

/* ── Routine registry ──────────────────────────────────────── */

/* Routine table uses shared memory hash table — see AddInRoutine/FindRoutineEx */

/*
 * ═══════════════════════════════════════════════════════════════
 * Shared Memory Routine Table
 *
 * From IDA: Routines are stored in shared memory (not kernel lists).
 * This allows both ARM and MIPS to register and look up handlers.
 *
 * Layout in shared memory (at ShMemAddrBase + 0x7000 = SHMEM_OFF_COMP_POOL):
 *   Pool + 1472 (= ShMemAddrBase + 30144): version counter (u32)
 *   Pool + 1476 (= ShMemAddrBase + 30148): entry count (u32)
 *   Pool + 1480 (= ShMemAddrBase + 30152): routine entry table
 *
 * The table uses open-address hashing with chaining:
 *   1024 primary hash buckets (index 0..1023)
 *   200 overflow slots (index 1024..1223)
 *   Hash function: index = comp_id & 0x3FF
 *
 * Each entry is 96 bytes:
 *   +0:  header/name (first 2 bytes = comp name u16)
 *   +2:  cpu_id (u16)
 *   +4:  flags (u32)
 *   +8:  comp_id (u32)  — the component search key
 *   +12: routine data (callback info, name string, etc.)
 *   +92: next_index (i32, -1 = end of chain)
 * ═══════════════════════════════════════════════════════════════
 */

/* Offsets from ShMemAddrBase */
#define RT_VERSION_OFF		30144	/* u32 version counter */
#define RT_COUNT_OFF		30148	/* u32 entry count (checked <= 1223) */
#define RT_TABLE_OFF		30152	/* start of 96-byte entries */

/* Entry field offsets */
#define RT_ENTRY_SIZE		96
#define RT_COMP_ID_OFF		8	/* u32 at entry + 8 */
#define RT_CPU_OFF		2	/* u16 at entry + 2 */
#define RT_NEXT_OFF		92	/* i32 at entry + 92 (chain link) */

/* Table limits */
#define RT_PRIMARY_SLOTS	1024
#define RT_OVERFLOW_START	1024
#define RT_MAX_INDEX		1223

/* Get pointer to entry at given index */
static inline u8 *rt_entry(int idx)
{
	return (u8 *)(ShMemAddrBase + RT_TABLE_OFF + RT_ENTRY_SIZE * idx);
}

/* Get comp_id at entry index */
static inline u32 rt_comp_id(int idx)
{
	return *(u32 *)(rt_entry(idx) + RT_COMP_ID_OFF);
}

/* Get/set next chain index at entry */
static inline int rt_next(int idx)
{
	return *(int *)(rt_entry(idx) + RT_NEXT_OFF);
}

static inline void rt_set_next(int idx, int next)
{
	*(int *)(rt_entry(idx) + RT_NEXT_OFF) = next;
}

/* Version counter */
static inline u32 *rt_version_ptr(void)
{
	return (u32 *)(ShMemAddrBase + RT_VERSION_OFF);
}

/* Entry count */
static inline u32 *rt_count_ptr(void)
{
	return (u32 *)(ShMemAddrBase + RT_COUNT_OFF);
}

/*
 * AddInRoutine — Register a routine in the shared memory hash table.
 *
 * From IDA @ 0x60f8. Validates magic, checks for duplicates via
 * FindRoutineEx, then inserts into the hash table under spinlock 2.
 *
 * @data: pointer to 96-byte routine descriptor to register.
 *        comp_id is at data+8, used as hash key.
 *
 * Returns 0 on success, -2 if table full.
 */
int AddInRoutine(void *data)
{
	u32 comp_id;
	int hash_idx;
	int cur_idx;
	int prev_idx;
	u8 find_buf[96];
	u8 find_name[4];
	u8 *entry;

	if (WARN_ON(!ShMemAddrBase || !data))
		return -EINVAL;
	if (*(u32 *)(ShMemAddrBase + SHMEM_OFF_MAGIC1) != CPU_COMM_MAGIC)
		return -EINVAL;
	if (*(u32 *)(ShMemAddrBase + SHMEM_OFF_MAGIC2) != CPU_COMM_MAGIC)
		return -EINVAL;

	/* Keep cpu_id from user buffer (allows registering routes to MIPS) */
	/* Was: *(u16 *)((u8 *)data + RT_CPU_OFF) = (u16)getCurCPUID(0); */

	comp_id = *(u32 *)((u8 *)data + RT_COMP_ID_OFF);
	if (*(int *)rt_count_ptr() > RT_MAX_INDEX) {
		pr_err("cpu_comm: AddInRoutine: table count > %d\n", RT_MAX_INDEX);
		return -EINVAL;
	}

	/* Check for duplicate */
	if (!FindRoutineEx(comp_id, find_buf, (u32 *)find_name))
		return 0;	/* already registered */

	comm_SpinLock(2);
	(*rt_version_ptr())++;

	hash_idx = comp_id & (RT_PRIMARY_SLOTS - 1);

	/* Check if primary slot is occupied */
	if (rt_comp_id(hash_idx) == 0 && rt_next(hash_idx) == -1) {
		/* Primary slot is free — insert directly */
		entry = rt_entry(hash_idx);
		mmiocpy(entry, data, RT_ENTRY_SIZE);
		rt_set_next(hash_idx, -1);
		(*rt_count_ptr())++;
	} else {
		/* Walk the chain to find the end */
		cur_idx = hash_idx;
		prev_idx = -1;

		while (rt_comp_id(cur_idx) != 0) {
			if (*(u16 *)(rt_entry(cur_idx) + RT_CPU_OFF) > 1) {
				pr_err("cpu_comm: AddInRoutine: corrupt entry at %d\n",
				       cur_idx);
				return -EINVAL;
			}
			prev_idx = cur_idx;
			cur_idx = rt_next(cur_idx);
			if (cur_idx < 0)
				break;
			if (cur_idx > RT_MAX_INDEX) {
				pr_err("cpu_comm: AddInRoutine: chain index %d > max\n",
				       cur_idx);
				return -EINVAL;
			}
		}

		if (cur_idx >= 0 && rt_next(cur_idx) == -1) {
			/* Found empty slot in chain — use it directly */
			entry = rt_entry(cur_idx);
			mmiocpy(entry, data, RT_ENTRY_SIZE);
			rt_set_next(cur_idx, -1);
			(*rt_count_ptr())++;
		} else {
			/* Need overflow slot — find free one */
			int overflow_idx;
			int ret = -2;

			for (overflow_idx = RT_OVERFLOW_START;
			     overflow_idx <= RT_MAX_INDEX;
			     overflow_idx++) {
				if (rt_comp_id(overflow_idx) == 0) {
					/* Found free overflow slot */
					if (rt_next(overflow_idx) != -1) {
						pr_err("cpu_comm: AddInRoutine: "
						       "overflow %d has next!=%d\n",
						       overflow_idx,
						       rt_next(overflow_idx));
						return -EINVAL;
					}
					entry = rt_entry(overflow_idx);
					mmiocpy(entry, data, RT_ENTRY_SIZE);
					rt_set_next(overflow_idx, -1);

					/* Link from previous entry */
					if (prev_idx >= 0)
						rt_set_next(prev_idx,
							    overflow_idx);

					ret = 0;
					(*rt_count_ptr())++;
					break;
				}
			}

			if (ret != 0) {
				pr_err("cpu_comm: AddInRoutine: table full\n");
				(*rt_version_ptr())++;
				comm_SpinUnLock(2, 0);
				return -2;
			}
		}
	}

	(*rt_version_ptr())++;
	comm_SpinUnLock(2, 0);
	return 0;
}

/*
 * RemoveRoutine — Remove a routine from the shared memory hash table.
 *
 * From IDA @ 0x68f4. Walks the hash chain to find the matching entry,
 * then removes it and re-links the chain.
 *
 * @data: pointer to routine descriptor. comp_id at data+8 is the key.
 *
 * Returns 0 on success (found matching CPU), 1 if not found for our CPU,
 *        -1 if not in table at all.
 */
int RemoveRoutine(void *data)
{
	u32 comp_id;
	int cur_idx;
	int prev_idx;
	int next_idx;
	u8 *cur_entry;
	int result;
	u32 our_cpu;

	if (WARN_ON(!ShMemAddrBase || !data))
		return -EINVAL;
	if (*(u32 *)(ShMemAddrBase + SHMEM_OFF_MAGIC1) != CPU_COMM_MAGIC)
		return -EINVAL;
	if (*(u32 *)(ShMemAddrBase + SHMEM_OFF_MAGIC2) != CPU_COMM_MAGIC)
		return -EINVAL;

	comp_id = *(u32 *)((u8 *)data + RT_COMP_ID_OFF);
	if (*(int *)rt_count_ptr() > RT_MAX_INDEX)
		return -EINVAL;

	comm_SpinLock(2);
	(*rt_version_ptr())++;

	/* Walk the hash chain */
	cur_idx = comp_id & (RT_PRIMARY_SLOTS - 1);
	prev_idx = -1;

	while (1) {
		if (rt_comp_id(cur_idx) == comp_id)
			break;

		next_idx = rt_next(cur_idx);
		if (next_idx < 0) {
			result = -1;
			goto out;
		}
		if (next_idx > RT_MAX_INDEX)
			return -EFAULT;

		prev_idx = cur_idx;
		cur_idx = next_idx;
	}

	cur_entry = rt_entry(cur_idx);

	if (*(u16 *)(cur_entry + RT_CPU_OFF) > 1)
		return -EFAULT;

	/* Clear the entry */
	*(u32 *)(cur_entry + RT_COMP_ID_OFF) = 0;

	/* Re-link chain: if next entry exists, copy it into this slot */
	next_idx = rt_next(cur_idx);
	if (next_idx >= 0 && next_idx <= RT_MAX_INDEX) {
		u8 *next_entry = rt_entry(next_idx);

		mmiocpy(cur_entry, next_entry, RT_ENTRY_SIZE);
		rt_set_next(cur_idx, rt_next(next_idx));

		/* Clear the moved slot */
		*(u32 *)(next_entry + RT_COMP_ID_OFF) = 0;
		rt_set_next(next_idx, -1);
	}

	(*rt_count_ptr())--;

	/* Check if the matching entry was for our CPU */
	our_cpu = getCurCPUID(0);
	result = (*(u16 *)((u8 *)data + 0) == *(u16 *)(cur_entry + 0) &&
		  *(u32 *)((u8 *)data + 4) == *(u32 *)(cur_entry + 4) &&
		  *(u16 *)(cur_entry + RT_CPU_OFF) == our_cpu) ? 0 : 1;

out:
	(*rt_version_ptr())++;
	comm_SpinUnLock(2, 0);
	return result;
}

/*
 * FindRoutineEx — Look up a routine in the shared memory hash table.
 *
 * From IDA @ 0x5cfc. Walks the hash chain for the given comp_id.
 * On success, copies the 96-byte entry into msg_buf and optionally
 * sets *result to the entry's data pointer.
 *
 * The stock version caches the table in pcpu_comm_dev and syncs on
 * version mismatch. We read directly from shared memory (simpler,
 * still correct, slightly slower).
 *
 * @comp_search: component ID to find
 * @msg_buf:     output buffer (96 bytes) — receives the entry copy
 * @result:      optional — receives pointer to the entry's data (+12)
 *
 * Returns 0 on success, 1 if not found.
 */
int FindRoutineEx(u32 comp_search, void *msg_buf, u32 *result)
{
	int cur_idx;
	u8 *entry;

	if (WARN_ON(!ShMemAddrBase || !msg_buf))
		return 1;
	if (*(u32 *)(ShMemAddrBase + SHMEM_OFF_MAGIC1) != CPU_COMM_MAGIC)
		return 1;
	if (*(u32 *)(ShMemAddrBase + SHMEM_OFF_MAGIC2) != CPU_COMM_MAGIC)
		return 1;
	if (*(int *)rt_count_ptr() > RT_MAX_INDEX)
		return 1;

	cur_idx = comp_search & (RT_PRIMARY_SLOTS - 1);

	while (1) {
		if (cur_idx > RT_MAX_INDEX) {
			pr_err("cpu_comm: FindRoutineEx: index %d > max\n", cur_idx);
			return 1;
		}

		entry = rt_entry(cur_idx);

		if (*(u32 *)(entry + RT_COMP_ID_OFF) == comp_search) {
			/* Found — copy entry to output */
			*(u16 *)msg_buf = *(u16 *)entry;
			*(u32 *)((u8 *)msg_buf + 8) = *(u32 *)(entry + 8);
			*(u16 *)((u8 *)msg_buf + 2) = *(u16 *)(entry + 2);

			/* Copy callback pointers at +80 (8 bytes) */
			*(u64 *)((u8 *)msg_buf + 80) = *(u64 *)(entry + 80);

			*(u32 *)((u8 *)msg_buf + 4) = *(u32 *)(entry + 4);

			/* Copy routine data at +12 (64 bytes) */
			mmiocpy((u8 *)msg_buf + 12, entry + 12, 64);

			if (result)
				*result = (u32)(entry + 12);

			if (*(u16 *)(entry + RT_CPU_OFF) > 1) {
				pr_warn("cpu_comm: FindRoutineEx: cpu %u > 1\n",
					*(u16 *)(entry + RT_CPU_OFF));
			}

			return 0; /* found */
		}

		/* Follow chain link */
		cur_idx = rt_next(cur_idx);
		if (cur_idx < 0)
			return 1; /* not found */
	}
}

/*
 * FindRoutine — Simple wrapper for FindRoutineEx.
 *
 * From IDA @ 0x60e8: `return FindRoutineEx(a1, a2, 0);`
 */
int FindRoutine(u32 comp_search, void *msg_buf)
{
	return FindRoutineEx(comp_search, msg_buf, NULL);
}

/*
 * RemovePidRoutines — Remove all routines registered by a given PID.
 *
 * From IDA @ 0x65d4. Walks the entire routine table and removes entries
 * matching the PID (stored at entry + 28 = process info field).
 */
void RemovePidRoutines(pid_t pid)
{
	int i;
	u32 pid_val = (u32)pid;

	if (!ShMemAddrBase)
		return;

	comm_SpinLock(2);
	(*rt_version_ptr())++;

	for (i = 0; i <= RT_MAX_INDEX; i++) {
		u8 *entry = rt_entry(i);

		if (*(u32 *)(entry + RT_COMP_ID_OFF) == 0)
			continue;

		/* PID is stored at entry + 28 (from IDA: *(entry + 7*4)) */
		if (*(u32 *)(entry + 28) == pid_val) {
			*(u32 *)(entry + RT_COMP_ID_OFF) = 0;
			(*rt_count_ptr())--;
		}
	}

	(*rt_version_ptr())++;
	comm_SpinUnLock(2, 0);
}

/*
 * RoutineCleanupInCPUReset — Remove all routines for a given CPU.
 *
 * From IDA @ 0x6cb4. Walks the routine table and removes entries
 * owned by the specified CPU.
 */
void RoutineCleanupInCPUReset(void *data)
{
	u32 cpu_id = (u32)(unsigned long)data;
	int i;

	if (!ShMemAddrBase)
		return;

	comm_SpinLock(2);
	(*rt_version_ptr())++;

	for (i = 0; i <= RT_MAX_INDEX; i++) {
		u8 *entry = rt_entry(i);

		if (*(u32 *)(entry + RT_COMP_ID_OFF) == 0)
			continue;

		if (*(u16 *)(entry + RT_CPU_OFF) == cpu_id) {
			*(u32 *)(entry + RT_COMP_ID_OFF) = 0;
			(*rt_count_ptr())--;
		}
	}

	(*rt_version_ptr())++;
	comm_SpinUnLock(2, 0);
}

void RoutineCleanupExpKernel(void *data)
{
	RoutineCleanupInCPUReset(data);
}

/* ── CPUComm_Call — Synchronous RPC call to another CPU ────── */

/*
 * From IDA @ 0x10b3c:
 *   CPUComm_Call(msg_buf, params, result)
 *     → CPUComm_CallEx(*(u32*)(msg_buf+40), params, result)
 *
 * msg_buf+40 = component_id from the comm_msg payload[0].
 */
int CPUComm_Call(void *msg_buf, void *params, void *result)
{
	if (!msg_buf)
		return -EINVAL;
	return CPUComm_CallEx(*(u32 *)((u8 *)msg_buf + 40),
			      (int *)params, (u32 *)result);
}

int CPUComm_Call_Ex(void *msg_buf, void *params, void *result)
{
	return CPUComm_Call(msg_buf, params, result);
}

/*
 * CPUComm_CallEx — Full synchronous RPC: send, wait, receive, return.
 *
 * From IDA @ 0x10614. This is NOT just a wrapper for SendComm2CPUEx.
 * It builds a comm_msg from the component_id + params, sends it,
 * waits for the MIPS response, copies the result, and cleans up.
 *
 * @comp_id:  component identifier (determines routing to MIPS handler)
 * @params:   int array: params[0]=count (max 10), params[1..n]=values
 * @result:   u32 array: result[0]=count on return, result[1..n]=values
 *
 * Returns 0 on success, negative on error.
 */
int CPUComm_CallEx(int comp_id, int *params, u32 *result)
{
	u8 local_msg[COMM_MSG_SIZE];
	int ret;
	int param_count;
	int i;
	u16 dst_cpu;
	u32 seq_base;
	u32 wait_obj = 0;
	u32 session_ptr;
	u16 *return_entry = NULL;

	if (!params)
		return -EINVAL;
	if (!result)
		return -EINTR;

	param_count = params[0];
	if (param_count > 10) {
		pr_err("cpu_comm: CPUComm_CallEx: param_count %d > 10\n",
		       param_count);
		return -EINVAL;
	}

	/* Build local comm_msg on stack */
	memset(local_msg, 0, COMM_MSG_SIZE);

	/* Store component_id in payload area (offset 40 = 0x28) */
	*(u32 *)(local_msg + 40) = (u32)comp_id;

	/* Store caller's PID (offset 52 = 0x34) */
	*(u32 *)(local_msg + 52) = (u32)current->tgid;

	/* Store param count in cmd_type field (offset 8) */
	*(u16 *)(local_msg + 8) = (u16)param_count;

	/* Copy params into payload (offset 44..84 = 0x2C..0x54) */
	for (i = 0; i < param_count; i++)
		*(u32 *)(local_msg + 44 + 4 * i) = (u32)params[i + 1];

	/* Clear notify flag — this is a synchronous call */
	*(u16 *)(local_msg + 6) &= ~MSG_FLAG_NOTIFY;

	/* Send via SendComm2CPUEx (target_cpu=0 = auto-detect via FindRoutine) */
	ret = SendComm2CPUEx((u32)local_msg, 0, 0);
	if (ret) {
		pr_err("cpu_comm: CPUComm_CallEx: SendComm2CPUEx failed (%d)\n",
		       ret);
		return ret;
	}

	/*
	 * Now wait for the MIPS response.
	 * SendComm2CPUEx allocated a wait object and stored the session_id.
	 * We need to find it, wait on it, then get the return data.
	 */
	session_ptr = *(u32 *)(local_msg + 12);  /* session_id field */
	dst_cpu = *(u16 *)(local_msg + 2);       /* resolved destination CPU */
	seq_base = getSeq(dst_cpu);

	/* Find our wait object */
	FindWaitBySessionId((void *)(seq_base + 40),
			    session_ptr, (u32 **)&wait_obj);
	if (!wait_obj) {
		pr_err("cpu_comm: CPUComm_CallEx: wait obj not found (session=0x%x)\n",
		       session_ptr);
		return -EINVAL;
	}

	/* Wait for MIPS to respond (blocks until up() is called) */
	ret = cpu_comm_sem_down_interruptible((void *)(wait_obj + 8));
	if (ret) {
		pr_err("cpu_comm: CPUComm_CallEx: interrupted waiting (session=0x%x)\n",
		       session_ptr);
		return -EINVAL;
	}

	/* Get the return message from the return FIFO */
	ret = GetReturnbySessionId(session_ptr, dst_cpu, (u32 *)&return_entry);
	if (ret) {
		pr_err("cpu_comm: CPUComm_CallEx: return not found (session=0x%x)\n",
		       session_ptr);
		return -EFAULT;
	}

	/* Copy results from return entry to caller's result buffer */
	if (return_entry) {
		/* Increment return counter in pcpu_comm_dev */
		if (pcpu_comm_dev)
			*(u32 *)((u8 *)pcpu_comm_dev + 1632) += 1;

		/* Set "result received" flag */
		return_entry[5] |= 0x80;

		/* Copy result values (IDA: return_entry[4] = result count) */
		if (return_entry[4] != 15 && return_entry[4] <= 10) {
			*result = return_entry[4]; /* result count */
			for (i = 0; i < (int)return_entry[4]; i++)
				result[i + 1] = *(u32 *)&return_entry[2 * i + 22];
		}

		/* Release the call slot back to the share sequence */
		Comm_ReleaseFreeCall(
			(void *)getShareSeqR(return_entry[1], 1),
			(void *)return_entry);
	} else if (!IsCPUReset(dst_cpu)) {
		pr_warn("cpu_comm: CPUComm_CallEx: null return (cpu=%u session=0x%x)\n",
			dst_cpu, session_ptr);
	}

	/* Clean up wait object */
	{
		u32 wait_cleanup = 0;

		GetWaitbySessionId((void *)(seq_base + 40),
				   session_ptr, (u8 *)&wait_cleanup);
		if (!wait_cleanup)
			return -EINVAL;
		ReleaseWaitComm(dst_cpu, wait_cleanup);
	}

	return ret;
}

/* ── CPUComm_Notify — Asynchronous notification ────────────── */

/*
 * CPUComm_Notify — Send async notification to MIPS (no response wait).
 *
 * From IDA @ 0x10bd8:
 *   1. Format name: sprintf(s, "%s_%1lx_%3.3lx", name, params[11], params[12] & 0xFFF)
 *   2. Resolve: comp_id = Comm_Name2ID(s)
 *   3. Validate: params[0] (count) <= 10
 *   4. Build local msg on stack: copy params[1..count] into payload
 *   5. Set NOTIFY flag (bit 0)
 *   6. Store comp_id, PID, param_count
 *   7. SendComm2CPUEx(&msg, 0, 0)
 *
 * @name:   component name string (e.g. "VideoDecoder")
 * @params: int array: params[0]=count, params[1..n]=values,
 *          params[11]=cpu_hint, params[12]=sub_id
 */
int CPUComm_Notify(void *name, void *params)
{
	int *p = (int *)params;
	u8 local_msg[COMM_MSG_SIZE];
	char comp_name[64];
	int param_count;
	int comp_id;
	int i;

	if (!params)
		return -EINVAL;

	param_count = p[0];
	if (param_count > 10) {
		pr_err("cpu_comm: CPUComm_Notify: param_count %d > 10\n",
		       param_count);
		return -EINVAL;
	}

	/* Format component name: name_cpuhint_subid */
	snprintf(comp_name, sizeof(comp_name), "%s_%1lx_%3.3lx",
		 (const char *)name, (unsigned long)p[11],
		 (unsigned long)(p[12] & 0xFFF));

	/* Resolve component ID via shared memory lookup */
	comp_id = Comm_Name2ID(comp_name);

	/* Build local comm_msg on stack */
	memset(local_msg, 0, COMM_MSG_SIZE);

	/* Store component ID in payload (offset 0x28 = 40) */
	*(u32 *)(local_msg + 40) = (u32)comp_id;

	/* Store caller PID (offset 0x20 = 32) */
	*(u32 *)(local_msg + 32) = (u32)current->tgid;

	/* Store param count in cmd_type (offset 0x08) */
	*(u16 *)(local_msg + 8) = (u16)param_count;

	/* Store zero in reserved field (offset 0x06 = flags) */
	*(u16 *)(local_msg + 6) = 0;

	/* Copy params into payload (offset 0x2C = 44) */
	for (i = 0; i < param_count; i++)
		*(u32 *)(local_msg + 44 + 4 * i) = (u32)p[i + 1];

	/* Set NOTIFY flag — no wait for response */
	*(u16 *)(local_msg + 6) |= MSG_FLAG_NOTIFY;

	/* Send via auto-detect target (target_cpu=0) */
	return SendComm2CPUEx((u32)local_msg, 0, 0);
}

int CPUComm_Notify_Ex(void *name, void *params)
{
	return CPUComm_Notify(name, params);
}

/* ── CPUComm_InstallRoutine — Register handler from userspace ─ */

/*
 * From IDA @ 0x10d7c:
 *   CPUComm_InstallRoutine(const char *name, int callback, int a3, int priority)
 *
 * Steps:
 *   1. Validate priority <= 4, a3 == 0
 *   2. Format name: sprintf(s, "%s_%1x_%3.3x", name, getCurCPUID(), a3)
 *   3. Build 96-byte routine descriptor on stack:
 *      - descriptor[0] (u16) = priority + 5 (component_id offset)
 *      - descriptor[2] (u16) = thread_id (from current)
 *      - descriptor[4] (u32) = Comm_Name2ID(s)
 *      - descriptor[8] (u32) = callback
 *      - descriptor[12] (u32) = a3
 *   4. AddInRoutine(&descriptor) — insert into shared memory hash table
 *   5. If new: Comm_AddNewChannel(pcpu_comm_dev+48, comp_id, thread_id)
 *   6. If new channel: alloc_workqueue("CommCallWQ%d", ...) for this channel
 *
 * Our ioctl passes a 96-byte buffer from userspace containing all the
 * fields pre-formatted. We extract the relevant fields for channel mgmt.
 */
int CPUComm_InstallRoutine(void *data)
{
	u16 *desc = (u16 *)data;
	u32 comp_id;
	u32 channel_id;
	u32 thread_id;
	u32 existing_channel = 0;
	int ret;

	if (!data)
		return -EINVAL;

	/* Extract fields from the 96-byte descriptor */
	comp_id = *(u32 *)((u8 *)data + 8);	/* component_id at +8 */
	thread_id = *(u32 *)((u8 *)data + 4);	/* thread_id/flags at +4 */

	/* Step 1: Register in shared memory hash table */
	ret = AddInRoutine(data);
	if (ret)
		return -1;

	/* Step 2: Ensure a channel exists for this component */
	channel_id = (comp_id & 0xF) | (thread_id << 4);

	Comm_QueryChannel((void *)((u8 *)pcpu_comm_dev + 0x30),
			  channel_id, &existing_channel);

	if (!existing_channel) {
		/* No channel yet — create one */
		ret = Comm_AddNewChannel((void *)((u8 *)pcpu_comm_dev + 0x30),
					comp_id, thread_id);
		if (ret) {
			pr_err("cpu_comm: CPUComm_InstallRoutine: "
			       "AddNewChannel failed (%d)\n", ret);
		}

		/*
		 * Stock also creates a dedicated workqueue here:
		 *   alloc_workqueue("CommCallWQ%d", WQ_UNBOUND, ...)
		 * We use the default kernel workqueue via schedule_work()
		 * instead, which is simpler for initial bring-up.
		 * Dedicated WQs can be added later for priority scheduling.
		 */
	}

	return ret;
}

/*
 * CPUComm_UnInstallRoutine — Unregister handler.
 *
 * From IDA @ 0x1111c: Calls RemoveRoutine, then if the routine was
 * ours (return == 0), removes the channel too.
 */
int CPUComm_UnInstallRoutine(void *data)
{
	int ret;
	u32 comp_id;
	u32 thread_id;

	if (!data)
		return -EINVAL;

	comp_id = *(u32 *)((u8 *)data + 8);
	thread_id = *(u32 *)((u8 *)data + 4);

	ret = RemoveRoutine(data);

	if (ret == 0) {
		/* Routine was ours — also remove the channel */
		u32 channel_id = (comp_id & 0xF) | (thread_id << 4);

		Comm_RemoveChannel((void *)((u8 *)pcpu_comm_dev + 0x30),
				   comp_id, thread_id);
	}

	return (ret < 0) ? ret : 0;
}

/* ── Work queue action for async call processing ───────────── */

/* Work item for deferred call processing (Comm_Add2Call2WQ → comm_CallWorkAction) */
struct comm_work_item {
	struct work_struct work;
	void *call_entry;	/* pointer to comm_msg in shared memory */
};

/*
 * comm_CallWorkAction — Process a queued incoming call from MIPS.
 *
 * From IDA @ 0x102c8. This is the work_struct->func callback enqueued
 * by Comm_Add2Call2WQ. It:
 *   1. Reads the call entry pointer from work_struct + 32
 *   2. Copies the 104-byte comm_msg locally
 *   3. Releases the call slot back to the share sequence FIFO
 *   4. Looks up the registered routine via FindRoutine
 *   5. Calls the routine's callback with extracted parameters
 *   6. Sends the response back via SendComm2CPUEx(msg, 1, 0) if needed
 *   7. Frees the work allocation
 *
 * @data: pointer to work_struct (allocated by Comm_Add2Call2WQ)
 */
void comm_CallWorkAction(void *data)
{
	u8 *work = data;
	u16 *call_entry;
	u8 local_msg[COMM_MSG_SIZE];
	u8 routine_info[96];
	u8 routine_name[4];
	u8 *share_seq;

	if (!data)
		return;

	/* The call entry pointer is stored in our comm_work_item struct */
	call_entry = ((struct comm_work_item *)data)->call_entry;
	if (!call_entry)
		return;

	/* Validate: component_id > 4 (high-priority calls only) */
	if (*call_entry <= 4) {
		pr_err("cpu_comm: comm_CallWorkAction: comp_id %u <= 4!\n",
		       *call_entry);
		return;
	}

	/* Validate: source CPU */
	if (call_entry[1] > 1) {
		pr_err("cpu_comm: comm_CallWorkAction: invalid src CPU %u\n",
		       call_entry[1]);
		return;
	}

	/* Copy the 104-byte message locally before releasing the slot */
	memcpy(local_msg, call_entry, COMM_MSG_SIZE);

	/* Release the call slot back to the share sequence FIFO */
	share_seq = (u8 *)getShareSeqR(call_entry[1], 0);
	Comm_ReleaseFreeCall(share_seq, call_entry);

	/* Find the registered routine for this component */
	if (FindRoutine(*(u32 *)(local_msg + 40), routine_info)) {
		/* No routine found — log and discard */
		pr_warn("cpu_comm: comm_CallWorkAction: no routine for comp 0x%x\n",
			*(u32 *)(local_msg + 40));
		goto out_free;
	}

	/* Verify destination matches current CPU */
	{
		u16 dst_cpu = *(u16 *)(routine_info + 2);
		u32 cur_cpu = getCurCPUID(0);

		if (dst_cpu != cur_cpu) {
			pr_err("cpu_comm: comm_CallWorkAction: dst %u != cur %u\n",
			       dst_cpu, cur_cpu);
			return;
		}
	}

	/* Call the registered routine callback.
	 *
	 * The routine_info structure contains the callback function pointer.
	 * From IDA: callback is at routine_info + 0x58 (offset 88 in the
	 * 96-byte routine structure). It receives (params, result).
	 *
	 * For now, we just extract the callback and call it.
	 * The full parameter marshalling is complex — we simplify by
	 * passing the raw message payload.
	 */
	{
		void (*callback)(u32 *, u32 *) =
			*(void (**)(u32 *, u32 *))(routine_info + 88);

		if (callback) {
			u32 params[11];
			u32 result[11];

			/* Extract params from local_msg payload (offset 44..84) */
			memcpy(params, local_msg + 44, 10 * sizeof(u32));
			params[0] = *(u16 *)(local_msg + 4); /* slot index */
			memset(result, 0, sizeof(result));
			result[0] = 15; /* max result count */

			callback(params, result);

			/* If response needed (not notify-only), send back */
			if (!(local_msg[6] & 1) || (local_msg[6] & 2)) {
				/* Copy result back into local_msg */
				*(u16 *)(local_msg + 4) = (u16)result[0];

				if (result[0] != 15) {
					int i;

					for (i = 0; i < (int)result[0] && i < 10; i++)
						*(u32 *)(local_msg + 44 + i * 4) =
							result[i + 1];
				}

				/* Send response back to caller */
				if (SendComm2CPUEx((u32)local_msg, 1, 0))
					pr_warn("cpu_comm: comm_CallWorkAction: "
						"SendComm2CPUEx failed\n");
			}
		}
	}

out_free:
	/* Free the work allocation (40 bytes from Comm_Add2Call2WQ) */
	kfree(data);
}

/*
 * Comm_Add2Call2WQ — Enqueue a high-priority incoming call to work queue.
 *
 * From IDA @ 0x11344. Called from command_action when component_id > 4.
 * Allocates a work_struct, stores the call entry pointer, and queues it
 * for deferred processing by comm_CallWorkAction.
 *
 * @data: virtual address of the call entry (comm_msg, 104 bytes)
 */
void Comm_Add2Call2WQ(void *data)
{
	u16 *call_entry = data;
	struct work_struct *work;

	if (!call_entry || *call_entry <= 4) {
		pr_err("cpu_comm: Comm_Add2Call2WQ: invalid call entry\n");
		return;
	}

	/* Allocate comm_work_item (work_struct + call_entry pointer).
	 * Stock uses Comm_malloc(40, 2592) from SMM; we use kmalloc.
	 */
	{
		struct comm_work_item *item;

		item = kmalloc(sizeof(*item), GFP_ATOMIC);
		if (!item) {
			pr_err("cpu_comm: Comm_Add2Call2WQ: OOM!\n");
			return;
		}

		item->call_entry = data;

		/* Set flag at call_entry + 10 (flags2 |= 0x20 = "in work queue") */
		call_entry[5] |= 0x20;

		/* Initialize and schedule the work */
		INIT_WORK(&item->work, (work_func_t)comm_CallWorkAction);
		schedule_work(&item->work);
	}
}

/* ── Message/Component system ──────────────────────────────── */

/*
 * msgAddListener / msgRemoveListener — Register/unregister message
 * event listeners. Used by the tvtop/decd userspace daemons.
 *
 * These interact with the message pool at ShMemAddrBase + SHMEM_OFF_MSG_POOL.
 * The pool stores listener entries with component IDs and callback pointers.
 * Not critical for ARM↔MIPS base communication — only for the event
 * subscription system used by higher-level services.
 *
 * Returning 0 (success) allows the ioctl to succeed without side effects.
 */
int msgAddListener(void *pool, void *listener)
{
	/* Non-critical for base comm — event subscription system */
	return 0;
}

int msgRemoveListener(void *pool, void *listener)
{
	/* Non-critical for base comm — event subscription system */
	return 0;
}

void *getComponentPool(void)
{
	if (!ShMemAddrBase)
		return NULL;
	return (void *)(ShMemAddrBase + SHMEM_OFF_COMP_POOL);
}

void *getMsgPool(void)
{
	if (!ShMemAddrBase)
		return NULL;
	return (void *)(ShMemAddrBase + SHMEM_OFF_MSG_POOL);
}

/*
 * Comm_Name2ID — Map a component name string to its numeric ID.
 *
 * From IDA: walks the component pool (1224 entries × 96 bytes each)
 * at ShMemAddrBase + 28672 (SHMEM_OFF_COMP_POOL), comparing names.
 * Each entry has: [component_id, name_u16, dst_cpu, ...].
 *
 * Used by CPUComm_InstallRoutine to resolve names to IDs.
 * Not critical for init — userspace sets up routines later.
 */
int Comm_Name2ID(const char *name)
{
	u8 *pool;
	int i;

	if (!ShMemAddrBase || !name)
		return -1;

	pool = (u8 *)(ShMemAddrBase + SHMEM_OFF_COMP_POOL);

	/* Walk the component pool (up to 1224 entries, 96 bytes each) */
	for (i = 0; i < 1224; i++) {
		u8 *entry = pool + 8 + i * 96;  /* skip 8-byte pool header */
		u32 comp_id = *(u32 *)(entry + 8);

		if (!comp_id)
			continue;

		/* Name starts at entry + 12, max 32 chars */
		if (strncmp((char *)(entry + 12), name, 32) == 0)
			return (int)comp_id;
	}

	return -1;
}

int msgEventName2Index(const char *name)
{
	/* Event name → index mapping for the message subscription system.
	 * Non-critical — returns -1 (not found) until event system is ported.
	 */
	return -1;
}
