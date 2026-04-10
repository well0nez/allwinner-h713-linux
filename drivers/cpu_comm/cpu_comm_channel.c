// SPDX-License-Identifier: GPL-2.0
/*
 * cpu_comm_channel.c — Channel pool, session, and wait-queue management
 *
 * Channels map component_id + cpu pairs to FIFO endpoints.
 * Wait objects track pending RPC calls awaiting responses.
 * Sessions provide unique IDs for matching calls to returns.
 *
 * RE source: HAL_SX6/Kernel_Driver/cpu_comm/comm_request.c
 */

#include <linux/kernel.h>
#include <linux/slab.h>
#include <linux/list.h>
#include <linux/semaphore.h>
#include "cpu_comm.h"

/* ── Channel Pool ──────────────────────────────────────────── */

void ChannelPoolInit(void *pool_ptr)
{
	u32 *pool = pool_ptr;
	int i;

	if (WARN_ON(!pool))
		return;

	pool[0] = 0;			/* count */
	pool[1] = 0;
	pool[2] = 1;			/* sem */
	pool[3] = (u32)&pool[3];	/* active list head (self-ref) */
	pool[4] = (u32)&pool[3];	/* active list tail */
	pool[5] = 0;			/* free count */
	pool[6] = 1;			/* free sem */
	pool[7] = (u32)&pool[7];	/* free list head */
	pool[8] = (u32)&pool[7];	/* free list tail */

	/* Initialize channel slots — 32 slots × 11 DWORDs */
	for (i = 0; i < CHANNEL_SLOT_COUNT; i++) {
		u32 *slot = &pool[9 + i * CHANNEL_SLOT_DWORDS];
		/* Set sentinel session IDs */
		slot[8] = SESSION_ID_INVALID;  /* +44 from pool[9] base */
		slot[4] = SESSION_ID_INVALID;  /* +40 */
	}
}

/*
 * Comm_QueryChannel — Find a channel by channel_id
 * channel_id = component_id | (cpu << 4)
 * Returns 0 if found (result points to channel), negative on error.
 */
int Comm_QueryChannel(void *pool_ptr, u32 channel_id, u32 *result)
{
	u32 *pool = pool_ptr;
	int i;

	if (!pool || !result)
		return -EINVAL;

	*result = 0;

	for (i = 0; i < CHANNEL_SLOT_COUNT; i++) {
		u32 *slot = &pool[9 + i * CHANNEL_SLOT_DWORDS];
		if (slot[0] == channel_id) {
			*result = (u32)slot;
			return 0;
		}
	}
	return 0; /* not found, result stays 0 */
}

/*
 * Comm_AddNewChannel — Create a new channel for component + cpu pair
 */
int Comm_AddNewChannel(void *pool_ptr, u16 comp_id, u32 cpu)
{
	u32 *pool = pool_ptr;
	u32 channel_id;
	int i;

	if (!pool)
		return -EINVAL;

	channel_id = comp_id | (cpu << 4);

	/* Find a free slot */
	for (i = 0; i < CHANNEL_SLOT_COUNT; i++) {
		u32 *slot = &pool[9 + i * CHANNEL_SLOT_DWORDS];
		if (slot[0] == 0) {
			slot[0] = channel_id;
			slot[1] = 0; /* session count */
			pool[0]++;   /* increment active count */
			pr_debug("cpu_comm: channel added: comp=%u cpu=%u id=0x%x\n",
				 comp_id, cpu, channel_id);
			return 0;
		}
	}

	pr_err("cpu_comm: channel pool full\n");
	return -ENOMEM;
}

/*
 * Comm_RemoveChannel — Remove a channel
 */
int Comm_RemoveChannel(void *pool_ptr, u16 comp_id, u32 cpu)
{
	u32 *pool = pool_ptr;
	u32 channel_id;
	int i;

	if (!pool)
		return -EINVAL;

	channel_id = comp_id | (cpu << 4);

	for (i = 0; i < CHANNEL_SLOT_COUNT; i++) {
		u32 *slot = &pool[9 + i * CHANNEL_SLOT_DWORDS];
		if (slot[0] == channel_id) {
			memset(slot, 0, CHANNEL_SLOT_DWORDS * 4);
			pool[0]--;
			return 0;
		}
	}
	return -ENOENT;
}

/*
 * Comm_Add2NewCallFifo — Add a call entry to a staging FIFO and signal channel.
 *
 * From IDA @ 0x7e48.  Three arguments:
 *   1. Write call_entry pointer into cmd_fifo
 *   2. Set "dispatched" flag (0x10) on the call entry
 *   3. Look up channel by component_id and signal it via up()
 *
 * @pool_ptr:    pointer to channel_pool (pcpu_comm_dev + 0x30)
 * @cmd_fifo:    pointer to the staging FIFO (CallCmd FIFO at share_seq + 32)
 * @call_entry:  virtual address of the call entry (comm_msg) to enqueue
 */
void Comm_Add2NewCallFifo(void *pool_ptr, u32 *cmd_fifo, u32 call_entry)
{
	u32 *wr_slot;
	u16 comp_id;
	u32 channel_id;
	u32 channel_ptr = 0;

	/* Write call entry pointer to cmd FIFO */
	wr_slot = (u32 *)fifo_getItemWr(cmd_fifo);
	if (!wr_slot) {
		pr_err("cpu_comm: Comm_Add2NewCallFifo: cmd_fifo full!\n");
		BUG();
	}
	*wr_slot = call_entry;
	if (!fifo_requestItemWr(cmd_fifo)) {
		pr_err("cpu_comm: Comm_Add2NewCallFifo: requestItemWr failed!\n");
		BUG();
	}

	/* Set "dispatched" flag at entry + 10 (u16 flags2) */
	*(u16 *)(call_entry + 10) |= 0x10;

	/* Look up channel by component_id from the call entry */
	comp_id = *(u16 *)(call_entry + 2);
	channel_id = (comp_id & 0xF) | (*(u32 *)(call_entry + 16) << 4);

	channel_ptr = 0;
	Comm_QueryChannel(pool_ptr, channel_id, &channel_ptr);
	if (!channel_ptr) {
		pr_warn("cpu_comm: Comm_Add2NewCallFifo: no channel for id 0x%x\n",
			channel_id);
		return;
	}

	/* Validate channel fields match the call entry */
	if (*(u16 *)(channel_ptr + 2) != *(u16 *)call_entry) {
		pr_err("cpu_comm: Comm_Add2NewCallFifo: channel comp mismatch!\n");
		BUG();
	}
	if (*(u32 *)(channel_ptr + 8) != *(u32 *)(call_entry + 16)) {
		pr_err("cpu_comm: Comm_Add2NewCallFifo: channel cpu mismatch!\n");
		BUG();
	}
	if (*(u32 *)(channel_ptr + 12) != channel_id) {
		pr_err("cpu_comm: Comm_Add2NewCallFifo: channel id mismatch!\n");
		BUG();
	}

	/* Signal the channel's semaphore to wake processing thread */
	cpu_comm_sem_up((void *)(channel_ptr + 16));
}

/*
 * Comm_GetCallbyChannel — Dequeue a call from a channel's cmd FIFO.
 *
 * Looks up the channel by channel_id, then reads and removes the oldest
 * call entry from its embedded FIFO.
 *
 * @pool_ptr:   pointer to channel_pool
 * @channel_id: channel identifier (comp_id | (cpu << 4))
 * @result:     output — receives virtual address of the call entry
 *
 * Returns 0 on success (result set), 0 with result=0 if FIFO empty,
 * negative on error.
 */
int Comm_GetCallbyChannel(void *pool_ptr, u32 channel_id, u32 *result)
{
	u32 channel_ptr = 0;
	u32 *cmd_fifo;
	u32 *item;

	if (!result)
		return -EINVAL;

	*result = 0;

	if (!pool_ptr)
		return -EINVAL;

	Comm_QueryChannel(pool_ptr, channel_id, &channel_ptr);
	if (!channel_ptr)
		return 0;	/* channel not found, result stays 0 */

	/* cmd_fifo embedded in channel at byte offset 32 */
	cmd_fifo = (u32 *)(channel_ptr + 32);

	item = (u32 *)fifo_getItemRd(cmd_fifo);
	if (!item)
		return 0;	/* FIFO empty */

	*result = *item;
	fifo_ItemRdNext(cmd_fifo);
	return 0;
}

/* ── Wait/Session Management ───────────────────────────────── */

/*
 * GetFreeWaitComm — Get a free wait object from the FreeWait FIFO.
 *
 * From IDA @ 0x344c.
 *
 * @fifo:   pointer to the FreeWait comm_fifo (sock + 136 bytes = &sock[34])
 * @result: output — receives virtual address of the wait entry
 *
 * Returns 0 on success, 1 if FIFO is empty.
 *
 * The FIFO items are virtual addresses pointing to wait entry[1]
 * (the session_id field), pre-filled by InitCommSeqMem.
 */
int GetFreeWaitComm(void *fifo, u32 **result)
{
	u32 *f = fifo;
	u32 *item;

	if (!result)
		BUG();

	item = (u32 *)fifo_getItemRd(f);
	if (item) {
		/* Item contains the virtual address of the wait object */
		*result = (u32 *)*item;
		fifo_ItemRdNext(f);
		return 0;
	}

	*result = NULL;
	return 1;	/* empty */
}

/*
 * AddtoWaitComm — Insert a wait entry into the active wait list.
 *
 * From IDA @ 0x2aa0.
 *
 * @list_base:  byte address of the MsgFIFO/list anchor (sock + 40 bytes)
 *              Fields at byte offsets from list_base:
 *                +48 = peak_count (u8)
 *                +52 = count (u32)
 *                +56 = head (u32, next ptr of sentinel)
 *                +60 = tail (u32, prev ptr of sentinel = last entry's node)
 *                +64 = sem (struct semaphore)
 * @wait_entry: byte address of the wait entry to insert.
 *              The linked-list node lives at wait_entry + 24 (6 DWORDs in):
 *                +24 = node.next
 *                +28 = node.prev
 *
 * Inserts at tail (before sentinel head).
 */
int AddtoWaitComm(void *list_base, u32 wait_entry)
{
	u8 *lb = list_base;
	u32 new_node;
	u32 *prev;

	if (WARN_ON(!list_base || !wait_entry))
		return -EINVAL;

	cpu_comm_sem_down((void *)(lb + 64));

	/* tail pointer = previous last entry's node (or sentinel head if empty) */
	prev = *(u32 **)(lb + 60);

	/* The new node is 24 bytes into the wait entry */
	new_node = wait_entry + 24;

	/* Insert new node as new tail (before sentinel):
	 *   old_tail->next = new_node
	 *   new_node->next = sentinel head (&lb[56])
	 *   new_node->prev = old_tail
	 *   sentinel->prev (lb+60) = new_node
	 */
	*(u32 *)(lb + 60) = new_node;
	*(u32 *)(wait_entry + 24) = (u32)(lb + 56);	/* next → sentinel */
	*(u32 *)(wait_entry + 28) = (u32)prev;		/* prev → old tail */
	*prev = new_node;				/* old_tail->next = new */

	/* Update peak count */
	{
		u32 count = ++*(u32 *)(lb + 52);

		if (count > *(u8 *)(lb + 48))
			*(u8 *)(lb + 48) = (u8)count;
	}

	cpu_comm_sem_up((void *)(lb + 64));
	return 0;
}

/*
 * GetWaitbySessionId — Remove and return a wait entry by session_id.
 *
 * From IDA @ 0x34e8.
 *
 * @list_base:  byte address of the MsgFIFO/list anchor
 * @session_id: session_id to match (at wait_entry + 0)
 * @result:     output byte pointer — receives the wait entry base address
 *
 * Walks the linked list starting at list_base+56 (head.next).
 * Wait entry base = node_address - 24.
 * On find: list_del (remove from list), decrement count, return 0.
 * Returns 1 if not found.
 */
int GetWaitbySessionId(void *list_base, u32 session_id, u8 *result)
{
	u8 *lb = list_base;
	u32 sentinel = (u32)(lb + 56);
	u32 cur_node;
	u32 entry_base;

	if (WARN_ON(!list_base || !result))
		return 1;

	cpu_comm_sem_down((void *)(lb + 64));

	cur_node = *(u32 *)(lb + 56);	/* head.next */

	while (cur_node != sentinel) {
		/* Wait entry base is 24 bytes before the node */
		entry_base = cur_node - 24;

		if (*(u32 *)entry_base == session_id) {
			/* Found — unlink: prev->next = next, next->prev = prev */
			u32 node_next = *(u32 *)(cur_node);
			u32 node_prev = *(u32 *)(cur_node + 4);

			*(u32 *)node_prev = node_next;
			*(u32 *)(node_next + 4) = node_prev;

			/* Decrement count */
			--*(u32 *)(lb + 52);

			cpu_comm_sem_up((void *)(lb + 64));

			*(u8 **)result = (u8 *)entry_base;
			return 0;
		}

		cur_node = *(u32 *)cur_node;	/* follow ->next */
	}

	cpu_comm_sem_up((void *)(lb + 64));
	return 1;	/* not found */
}

/*
 * FindWaitBySessionId — Find (but do NOT remove) a wait entry by session_id.
 *
 * From IDA @ 0x5c1c.  Same as GetWaitbySessionId but leaves the entry in
 * the list.
 *
 * @list_base:  byte address of the MsgFIFO/list anchor
 * @session_id: session_id to match (at wait_entry + 0)
 * @result:     output — receives virtual address of the wait entry
 *
 * Returns 0 on success, 1 if not found.
 */
int FindWaitBySessionId(void *list_base, u32 session_id, u32 **result)
{
	u8 *lb = list_base;
	u32 sentinel = (u32)(lb + 56);
	u32 cur_node;
	u32 entry_base;

	if (WARN_ON(!list_base || !result))
		return 1;

	cpu_comm_sem_down((void *)(lb + 64));

	cur_node = *(u32 *)(lb + 56);	/* head.next */

	while (cur_node != sentinel) {
		entry_base = cur_node - 24;

		if (*(u32 *)entry_base == session_id) {
			*result = (u32 *)entry_base;
			cpu_comm_sem_up((void *)(lb + 64));
			return 0;
		}

		cur_node = *(u32 *)cur_node;
	}

	cpu_comm_sem_up((void *)(lb + 64));
	*result = NULL;
	return 1;
}

/*
 * ReleaseWaitComm — Return a wait entry back to the FreeWait FIFO.
 *
 * From IDA @ 0x3b28.
 *
 * @cpu_id:    CPU socket index (0 = ARM, 1 = MIPS)
 * @wait_entry: virtual address of the wait entry to release
 *
 * The FreeWait FIFO lives at sock[34] (= s_CommSockt[1248*cpu_id + 34]).
 * The semaphore protecting writes is at sock[30] (byte offset 120 = 30*4).
 * The FIFO items are virtual addresses of wait entries.
 */
void ReleaseWaitComm(u32 cpu_id, u32 wait_entry)
{
	u32 *fifo;
	u32 *sem;
	u32 *wr_slot;

	if (WARN_ON(cpu_id > 1))
		return;

	/* FreeWait FIFO at sock[34], sem at sock[30] */
	fifo = &s_CommSockt[1248 * cpu_id + 34];
	sem  = &s_CommSockt[1248 * cpu_id + 30];

	cpu_comm_sem_down((void *)sem);

	wr_slot = (u32 *)fifo_getItemWr(fifo);
	if (!wr_slot) {
		pr_err("cpu_comm: ReleaseWaitComm: FreeWait FIFO full!\n");
		BUG();
	}

	*wr_slot = wait_entry;
	fifo_requestItemWr(fifo);

	cpu_comm_sem_up((void *)sem);
}

/*
 * HasInList — Check if a node is present in a doubly-linked list.
 *
 * @list: pointer to the sentinel head (list_head style: [next, prev])
 * @item: pointer to the node to search for
 *
 * Returns 1 if found, 0 if not.
 */
int HasInList(void *list, void *item)
{
	u32 sentinel;
	u32 cur;

	if (!list || !item)
		return 0;

	sentinel = (u32)list;
	cur = *(u32 *)list;	/* head.next */

	while (cur != sentinel) {
		if (cur == (u32)item)
			return 1;
		cur = *(u32 *)cur;	/* follow ->next */
	}

	return 0;
}

/* ── Free Call management ──────────────────────────────────── */

/*
 * Comm_GetFreeCall — Get a free call entry from a share sequence's FIFO.
 *
 * From IDA @ 0x3790.
 *
 * @share_seq: virtual address of a comm_share_seq structure (in shared memory).
 *             The free-call FIFO lives at share_seq + 120 (byte offset).
 *             FIFO items are PHYSICAL addresses of call-slot pointers.
 *
 * Returns virtual address of the call entry, or 0 if FIFO is empty.
 *
 * Translation chain:
 *   slot_phy = FIFO item (physical addr of u32 holding entry_phy)
 *   slot_vir = slot_phy + ShMemAddrBase - ShMemAddr
 *   entry_phy = *slot_vir
 *   entry_vir = entry_phy + ShMemAddrBase - ShMemAddr  (or 0 if entry_phy == 0)
 */
int Comm_GetFreeCall(void *share_seq)
{
	u32 *fifo;
	u32 slot_phy;
	u32 *slot_vir;
	u32 entry_phy;
	u32 entry_vir;

	if (WARN_ON(!share_seq || !ShMemAddrBase || !ShMemAddr))
		return 0;

	fifo = (u32 *)((u8 *)share_seq + 120);

	slot_phy = fifo_getItemRd(fifo);
	if (!slot_phy)
		return 0;

	/* Convert physical slot address to virtual */
	slot_vir = (u32 *)(slot_phy + ShMemAddrBase - ShMemAddr);

	/* Read the physical address of the call entry from the slot */
	entry_phy = *slot_vir;
	entry_vir = entry_phy ? entry_phy + ShMemAddrBase - ShMemAddr : 0;

	if (!entry_vir) {
		pr_err("cpu_comm: Comm_GetFreeCall: null entry_phy in slot!\n");
		BUG();
	}

	/* Validate slot index (u16 at entry + 4) */
	if (*(u16 *)(entry_vir + 4) > 19) {
		pr_err("cpu_comm: Comm_GetFreeCall: slot index %u out of range!\n",
		       *(u16 *)(entry_vir + 4));
		BUG();
	}

	/* Clear the call entry flags (u16 at entry + 10) */
	*(u16 *)(entry_vir + 10) = 0;

	fifo_ItemRdNext(fifo);
	return (int)entry_vir;
}

/*
 * Comm_ReleaseFreeCall — Return a call entry back to the share sequence FIFO.
 *
 * From IDA @ 0x3c40.
 *
 * @share_seq: virtual address of the comm_share_seq
 * @call:      virtual address of the call entry to release
 *
 * The FreeCall FIFO lives at share_seq + 120 with PHYSICAL base address.
 * fifo_getItemWr returns a PHYSICAL slot address — must convert to virtual.
 * Uses semaphore from the remote CPU's socket at sock[234] (byte offset 936).
 * share_seq[0] = local_cpu, share_seq[1] = remote_cpu (byte fields).
 */
void Comm_ReleaseFreeCall(void *share_seq, void *call)
{
	u8 *seq = (u8 *)share_seq;
	u32 *fifo;
	u32 wr_slot_phy;
	u32 *wr_slot_vir;
	u32 entry_vir;
	u32 entry_phy;
	u8 remote_cpu;
	u32 *sem;

	if (!share_seq) {
		pr_err("cpu_comm: Comm_ReleaseFreeCall: null share_seq!\n");
		BUG();
	}

	/* Validate local_cpu matches current CPU */
	if (seq[0] != getCurCPUID(0)) {
		pr_err("cpu_comm: Comm_ReleaseFreeCall: cpu mismatch!\n");
		BUG();
	}

	remote_cpu = seq[1];
	if (remote_cpu > 1) {
		pr_err("cpu_comm: Comm_ReleaseFreeCall: invalid remote cpu %u\n",
		       remote_cpu);
		BUG();
	}

	fifo = (u32 *)(seq + 120);
	sem = &s_CommSockt[1248 * remote_cpu + 234]; /* byte 936 from sock */

	cpu_comm_sem_down((void *)sem);

	wr_slot_phy = fifo_getItemWr(fifo);
	if (!wr_slot_phy) {
		pr_err("cpu_comm: Comm_ReleaseFreeCall: FIFO full!\n");
		BUG();
	}

	/* Convert physical write slot to virtual for writing */
	wr_slot_vir = (u32 *)(wr_slot_phy + ShMemAddrBase - ShMemAddr);
	if (!wr_slot_vir) {
		pr_err("cpu_comm: Comm_ReleaseFreeCall: null wr_slot_vir!\n");
		BUG();
	}

	/* Clear flags on the call entry before returning to pool */
	*(u16 *)((u8 *)call + 10) = 0;

	/* Convert call entry virtual → physical, write to FIFO slot */
	entry_vir = (u32)call;
	entry_phy = entry_vir ? entry_vir - ShMemAddrBase + ShMemAddr : 0;
	*wr_slot_vir = entry_phy;

	if (!fifo_requestItemWr(fifo)) {
		pr_err("cpu_comm: Comm_ReleaseFreeCall: requestItemWr failed!\n");
		BUG();
	}

	cpu_comm_sem_up((void *)sem);
}

/* ── Return FIFO ───────────────────────────────────────────── */

/*
 * AddReturn2Fifo — Write a return entry into a FIFO.
 *
 * From IDA @ 0x35cc. SIMPLE function — just a FIFO ring-buffer write.
 * NOT a linked-list operation (the agent version was wrong).
 *
 * @fifo:  pointer to a comm_fifo (ring buffer) that stores return entries.
 *         Caller passes the appropriate FIFO from the share sequence.
 * @data:  virtual address of the call entry (comm_msg) to add.
 *
 * IDA pseudocode:
 *   ItemWr = fifo_getItemWr(a1);
 *   if (!ItemWr) BUG();
 *   *ItemWr = a2;
 *   *(u16 *)(a2 + 10) |= 0x10;   // set "return queued" flag
 *   fifo_requestItemWr(a1);
 *
 * Returns the result of fifo_requestItemWr (non-zero on success).
 */
int AddReturn2Fifo(u32 *fifo, void *data)
{
	u32 *wr_slot;

	if (WARN_ON(!fifo || !data))
		return 0;

	wr_slot = (u32 *)fifo_getItemWr(fifo);
	if (!wr_slot) {
		pr_err("cpu_comm: AddReturn2Fifo: FIFO full!\n");
		BUG();
	}

	*wr_slot = (u32)data;

	/* Set "return queued" flag at entry + 10 (u16 flags2) */
	*(u16 *)((u8 *)data + 10) |= 0x10;

	if (!fifo_requestItemWr(fifo)) {
		pr_err("cpu_comm: AddReturn2Fifo: requestItemWr failed!\n");
		BUG();
	}

	return 1;
}

/*
 * GetReturnbySessionId — Remove and return a return entry by session_id.
 *
 * From IDA @ 0x59cc.
 *
 * @session_id: session ID to match (comm_msg.session_id at entry + 12)
 * @cpu:        CPU whose return list to search (0=ARM, 1=MIPS)
 * @result:     output — receives virtual address of the matched comm_msg entry
 *
 * First calls returnPipeLine(cpu) to drain the staging FIFO into the
 * ReturnList linked list. Then walks the list.
 *
 * The ReturnList MsgFIFO is at sock[267]. The linked list nodes are
 * embedded in the comm_msg at byte offset 84 (payload[13..14]).
 * The semaphore is at sock[283] (= MsgFIFO f[16], byte 1132 from sock).
 *
 * On match: list_del, decrement count (sock[280]), store entry base.
 *
 * Returns 0 always (result=NULL if not found, per IDA).
 */
int GetReturnbySessionId(u32 session_id, u32 cpu, u32 *result)
{
	u32 *sock;
	u32 *fifo_hdr;
	u32 sentinel;
	u32 cur_node;
	u32 next_node;
	u32 *sem;
	u32 entry_base;

	if (cpu > 1) {
		pr_err("cpu_comm: GetReturnbySessionId: invalid cpu %u\n", cpu);
		BUG();
	}

	/* Drain the staging FIFO into the linked list first */
	returnPipeLine((void *)(unsigned long)cpu);

	sock = &s_CommSockt[1248 * cpu];
	fifo_hdr = &sock[267];	/* ReturnList MsgFIFO */

	/* Semaphore at MsgFIFO f[16] = sock[267+16] = sock[283] */
	sem = &sock[283];

	sentinel = (u32)&fifo_hdr[14];	/* sentinel head address */

	cpu_comm_sem_down((void *)sem);

	cur_node = fifo_hdr[14];	/* head.next */

	while (cur_node != sentinel) {
		next_node = *(u32 *)cur_node;

		/*
		 * Return entry (comm_msg) node is at entry + 84 bytes.
		 * session_id is at entry + 12 bytes.
		 * So session_id = *(u32 *)(cur_node - 84 + 12) = *(cur_node - 72).
		 */
		if (*(u32 *)(cur_node - 72) == session_id) {
			/* Found — entry base is 84 bytes before node */
			entry_base = cur_node - 84;

			/* list_del: unlink node from list */
			{
				u32 node_next = *(u32 *)(cur_node);
				u32 node_prev = *(u32 *)(cur_node + 4);

				*(u32 *)node_prev = node_next;
				*(u32 *)(node_next + 4) = node_prev;
			}

			/* Decrement count, BUG if it goes negative */
			if ((int)--fifo_hdr[13] < 0) {
				pr_err("cpu_comm: GetReturnbySessionId: count underflow!\n");
				BUG();
			}

			if (result)
				*result = entry_base;

			cpu_comm_sem_up((void *)sem);
			return 0;
		}

		cur_node = next_node;
	}

	/* Not found */
	if (result)
		*result = 0;

	cpu_comm_sem_up((void *)sem);
	return 0;
}

/*
 * returnPipeLine — Drain the ReturnCmd staging FIFO into the ReturnList.
 *
 * From IDA @ 0x57f8.
 *
 * @data: CPU id (passed as void * for compatibility, cast to u32)
 *
 * Reads return entries from the ReturnCmd FIFO (at ShareSeqR(cpu,1) + 32)
 * and inserts each into the ReturnList linked list (at sock[267]).
 * The linked list node in each comm_msg entry is at byte offset 84.
 *
 * Semaphore: sock[283] (= MsgFIFO f[16], byte 1132 from sock base).
 * List head: sock[281] (= MsgFIFO f[14], byte 1124).
 * List tail: sock[282] (= MsgFIFO f[15], byte 1128).
 * Count:     sock[280] (= MsgFIFO f[13], byte 1120).
 * Peak:      sock byte 1116 (= MsgFIFO name[48] area, u8).
 */
void returnPipeLine(void *data)
{
	u32 cpu = (u32)(unsigned long)data;
	u32 share_seq_r;
	u32 *fifo;
	u32 *sock;
	u32 *sem;
	u32 item_addr;
	u32 entry_vir;

	if (cpu > 1) {
		pr_err("cpu_comm: returnPipeLine: invalid cpu %u\n", cpu);
		BUG();
	}

	share_seq_r = getShareSeqR(cpu, 1);	/* return direction */
	if (!share_seq_r)
		return;

	fifo = (u32 *)(share_seq_r + 32);	/* ReturnCmd staging FIFO */
	sock = &s_CommSockt[1248 * cpu];
	sem = &sock[283];			/* MsgFIFO semaphore */

	cpu_comm_sem_down((void *)sem);

	item_addr = fifo_getItemRd(fifo);

	while (item_addr) {
		/* Read the entry pointer from the FIFO slot */
		entry_vir = *(u32 *)item_addr;

		/* Validate slot index */
		if (*(u16 *)(entry_vir + 4) > 19) {
			pr_err("cpu_comm: returnPipeLine: slot index %u out of range!\n",
			       *(u16 *)(entry_vir + 4));
			BUG();
		}

		/* Set "in return list" flag at entry + 10 */
		*(u16 *)(entry_vir + 10) |= 0x20;

		/* Insert node (at entry + 84) at tail of ReturnList.
		 * List head sentinel: &sock[281] (f[14])
		 * List tail pointer:  sock[282] (f[15])
		 */
		{
			u32 new_node = entry_vir + 84;
			u32 *prev = (u32 *)sock[282];	/* current tail */
			u32 head_sentinel = (u32)&sock[281];

			*(u32 *)(new_node)     = head_sentinel;	/* next → sentinel */
			*(u32 *)(new_node + 4) = (u32)prev;	/* prev → old tail */
			*prev                  = new_node;	/* old_tail->next */
			sock[282]              = new_node;	/* sentinel->prev */
		}

		/* Increment count, update peak */
		{
			u32 count = ++sock[280];
			u8 *peak = (u8 *)&sock[279];

			if (count > *peak)
				*peak = (u8)count;
		}

		item_addr = fifo_ItemRdNext(fifo);
	}

	cpu_comm_sem_up((void *)sem);
}
