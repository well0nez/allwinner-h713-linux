// SPDX-License-Identifier: GPL-2.0
/*
 * cpu_comm_fifo.c — Ring-buffer FIFO for shared-memory IPC
 *
 * Single-producer single-consumer ring buffer.
 * Used for all message passing between ARM and MIPS.
 * Resides in shared memory — both CPUs access the same FIFO.
 *
 * The FIFO wastes one slot for full detection:
 *   empty: rd_idx == wr_idx
 *   full:  rd_idx == (wr_idx + 1) % capacity
 *
 * Write pattern: ptr = getItemWr(); write(ptr); requestItemWr();
 * Read pattern:  ptr = getItemRd(); read(ptr);  ItemRdNext();
 *
 * RE source: HAL_SX6/Kernel_Driver/cpu_comm/comm_request.c
 */

#include <linux/kernel.h>
#include <linux/string.h>
#include <linux/io.h>
#include "cpu_comm.h"

/*
 * InitMsgFIFO — Initialize a named message FIFO
 *
 * @fifo:   pointer to msg_fifo in shared memory
 * @prefix: name prefix (e.g., seq name)
 * @suffix: name suffix (e.g., " SendCmdWaitList")
 * @mode:   owner mode (>= 0 enables secondary wait list)
 */
void InitMsgFIFO(void *fifo_ptr, const char *prefix, const char *suffix,
		 int mode)
{
	u32 *f = fifo_ptr;
	char *name = (char *)f;

	/* Build name: prefix + suffix, max 48 chars */
	strncpy(name, prefix, FIFO_NAME_LEN);
	strlcat(name, suffix, FIFO_NAME_LEN);

	/* f[12] = mode (offset 0x30) */
	*((u8 *)f + 48) = 0;
	f[13] = 0;			/* count */

	/* Primary linked list (self-referencing init) */
	f[14] = (u32)&f[14];		/* head = &head */
	f[15] = (u32)&f[14];		/* tail = &head */

	if (mode >= 0) {
		f[16] = 1;		/* sem count = 1 (protects list ops) */
		f[17] = mode;		/* owner */
		/* Secondary wait list */
		f[18] = (u32)&f[18];	/* wait_head = &wait_head */
		f[19] = (u32)&f[18];	/* wait_tail = &wait_head */
	}
}

/*
 * fifo_getItemWr — Get pointer to current write slot (without advancing)
 *
 * Returns: virtual address of write slot, or 0 if FIFO is full
 *
 * FIFO layout: f[0]=rd, f[1]=wr, f[4]=cap, f[5]=item_size, f[6]=base
 */
u32 fifo_getItemWr(u32 *f)
{
	u32 rd, wr, cap;

	if (WARN_ON(!f))
		return 0;

	rd = f[0];
	wr = f[1];
	cap = f[4];

	WARN_ON(rd >= cap);
	WARN_ON(wr >= cap);

	/* Full check: if rd == (wr + 1) % cap → full */
	if (rd == (wr + 1) % cap) {
		pr_warn("cpu_comm: FIFO full (rd=%u wr=%u cap=%u)\n",
			rd, wr, cap);
		return 0;
	}

	/* Return address of current write slot */
	return f[6] + f[5] * wr;
}

/*
 * fifo_requestItemWr — Commit write and advance write index
 *
 * Call AFTER writing data to the slot returned by fifo_getItemWr.
 * Returns: address of NEW write slot, or 0 if now full.
 */
u32 fifo_requestItemWr(u32 *f)
{
	u32 rd, wr, cap, next_wr;
	int count;

	if (WARN_ON(!f))
		return 0;

	rd = f[0];
	wr = f[1];
	cap = f[4];

	WARN_ON(rd >= cap);
	WARN_ON(wr >= cap);

	next_wr = (wr + 1) % cap;

	/* Full after advance? */
	if (rd == next_wr)
		return 0;

	/* Advance write index */
	f[1] = next_wr;

	/* Track peak occupancy */
	if (f[3]) {
		count = fifo_getCount(f);
		if (count > (int)f[2])
			f[2] = count;
	}

	/* Return address of new write slot */
	return f[6] + f[5] * next_wr;
}

/*
 * fifo_getItemRd — Get pointer to current read slot (without advancing)
 *
 * Returns: virtual address of read slot, or 0 if FIFO is empty
 */
u32 fifo_getItemRd(u32 *f)
{
	u32 rd, wr, cap;

	if (WARN_ON(!f))
		return 0;

	rd = f[0];
	wr = f[1];
	cap = f[4];

	WARN_ON(rd >= cap);
	WARN_ON(wr >= cap);

	/* Empty check */
	if (rd == wr)
		return 0;

	return f[6] + f[5] * rd;
}

/*
 * fifo_ItemRdNext — Advance read index after consuming data
 *
 * Returns: address of new read slot, or 0 if now empty
 */
u32 fifo_ItemRdNext(u32 *f)
{
	u32 rd, wr, cap, next_rd;
	int count;

	if (WARN_ON(!f))
		return 0;

	rd = f[0];
	wr = f[1];
	cap = f[4];

	WARN_ON(rd >= cap);
	WARN_ON(wr >= cap);

	/* Already empty? */
	if (rd == wr)
		return 0;

	next_rd = (rd + 1) % cap;
	f[0] = next_rd;

	/* Track minimum occupancy */
	if (!f[3]) {
		count = fifo_getCount(f);
		if (count < (int)f[2])
			f[2] = count;
	}

	/* Empty after advance? */
	if (wr == next_rd)
		return 0;

	return f[6] + f[5] * next_rd;
}

/*
 * fifo_getCount — Number of items currently in FIFO
 */
int fifo_getCount(u32 *f)
{
	u32 rd, wr, cap;

	if (!f)
		return 0;

	rd = f[0];
	wr = f[1];
	cap = f[4];

	if (wr >= rd)
		return wr - rd;
	else
		return cap - rd + wr;
}

/*
 * fifo_isNearlyFull — Check if FIFO is within 'margin' of full
 */
int fifo_isNearlyFull(u32 *f, int margin)
{
	int count, cap;

	if (!f)
		return 1;

	count = fifo_getCount(f);
	cap = f[4];

	/* Full = cap - 1 items (one slot wasted) */
	return count >= (cap - 1 - margin);
}

/*
 * fifo_setmode — Set FIFO tracking mode
 */
void fifo_setmode(u32 *f, int mode)
{
	if (f)
		f[3] = mode;
}

/*
 * fifo_show — Debug: print FIFO state
 */
void fifo_show(u32 *f)
{
	if (!f)
		return;

	pr_info("cpu_comm FIFO [%.48s]: rd=%u wr=%u cap=%u count=%d peak=%u "
		"item_size=%u base=0x%x\n",
		(char *)f, f[0], f[1], f[4], fifo_getCount(f), f[2],
		f[5], f[6]);
}
