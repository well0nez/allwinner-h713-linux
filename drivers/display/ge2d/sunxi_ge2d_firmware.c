// SPDX-License-Identifier: GPL-2.0-only
/*
 * sunxi_ge2d_firmware.c — Firmware loader for ge2d display driver
 *
 * Loads LogoRegData.bin, parses binary header/project/logo tables,
 * patches panel timing into the register stream, then writes all
 * register entries to hardware via per-register ioremap/readl/writel/iounmap.
 *
 * Matches stock ge2d_dev.ko behavior 1:1 based on IDA decompilations of:
 *   __is_header_valid  @ 0xec94
 *   __is_project_valid @ 0xe634
 *   __get_project_info @ 0xe5d4
 *   __get_logo_table_info @ 0xeb18
 *   __get_reg          @ 0xeb98
 *   __write_reg        @ 0xf0a8
 *   __update_panel_set_member @ 0xe920
 *   __update_panel_setting    @ 0xf2b8
 *   __update_osd_buf_addr     @ 0xe824
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/firmware.h>
#include <linux/io.h>
#include <linux/delay.h>
#include <linux/slab.h>
#include <linux/err.h>
#include <asm/barrier.h>

#include "sunxi_ge2d.h"
#include "sunxi_ge2d_firmware.h"

/* Forward declarations for internal helpers */
extern int sunxi_tvtop_clk_get(int enable);

/* -----------------------------------------------------------------------
 * Helper: build flat panel_set[29] from ge2d_panel_config
 *
 * Stock driver maintains a separate g_panel_set[29] u32 array filled from
 * DTS. It does NOT include pwm/backlight/delay fields. We reconstruct the
 * same layout from our ge2d_panel_config struct.
 *
 * Stock g_panel_set index mapping (verified from __update_panel_setting IDA):
 *  [0]  protocol          [1]  bitwidth       [2]  data_swap
 *  [3]  ssc_span          [4]  ssc_step       [5]  ssc_en
 *  [6]  dclk_freq         [7]  de_current     [8]  even_data_current
 *  [9]  odd_data_current  [10] vs_invert      [11] hs_invert
 *  [12] de_invert         [13] dclk_invert    [14] mirror_mode
 *  [15] dual_port         [16] debug_en       [17] htotal
 *  [18] vtotal            [19] hsync          [20] vsync
 *  [21] hsync_pol         [22] vsync_pol      [23] width
 *  [24] height            [25] hbp            [26] vbp
 *  [27] lvds0_pol         [28] lvds1_pol
 * ----------------------------------------------------------------------- */
static void build_panel_set(const struct ge2d_panel_config *cfg,
			     struct ge2d_panel_set *ps)
{
	ps->v[0]  = cfg->protocol;
	ps->v[1]  = cfg->bitwidth;
	ps->v[2]  = cfg->data_swap;
	ps->v[3]  = cfg->ssc_span;
	ps->v[4]  = cfg->ssc_step;
	ps->v[5]  = cfg->ssc_en;
	ps->v[6]  = cfg->dclk_freq;
	ps->v[7]  = cfg->de_current;
	ps->v[8]  = cfg->even_data_current;
	ps->v[9]  = cfg->odd_data_current;
	ps->v[10] = cfg->vs_invert;
	ps->v[11] = cfg->hs_invert;
	ps->v[12] = cfg->de_invert;
	ps->v[13] = cfg->dclk_invert;
	ps->v[14] = cfg->mirror_mode;
	ps->v[15] = cfg->dual_port;
	ps->v[16] = cfg->debug_en;
	ps->v[17] = cfg->htotal;
	ps->v[18] = cfg->vtotal;
	ps->v[19] = cfg->hsync;
	ps->v[20] = cfg->vsync;
	ps->v[21] = cfg->hsync_pol;
	ps->v[22] = cfg->vsync_pol;
	ps->v[23] = cfg->width;
	ps->v[24] = cfg->height;
	ps->v[25] = cfg->hbp;
	ps->v[26] = cfg->vbp;
	ps->v[27] = cfg->lvds0_pol;
	ps->v[28] = cfg->lvds1_pol;
}

/* -----------------------------------------------------------------------
 * Firmware context helpers — equivalent to IDA __get_* functions
 * ----------------------------------------------------------------------- */

/*
 * ge2d_fw_parse() — Validate header and set up ctx pointers.
 * Equivalent to __is_header_valid + boundary checks from create_parse_reg_t.
 *
 * IDA create_parse_reg_t @ 0xfbd8:
 *   parse_reg[15] (0x3C) = fw_data pointer
 *   parse_reg[17] (0x44) = fw_data + 16 (project_table start)
 *   *(u16*)(parse_reg + 0x40) = header.project_table_size / 24 (num_projects)
 *   parse_reg[48] (0xC0) = fw_data + 16 + project_table_size (logo_table start)
 *   *(u16*)(parse_reg + 0xBC) = header.logo_table_size / 12 (num_logos)
 *
 * KEY INSIGHT: parse_reg[48] = logo_table_start, and logo_entry->offset
 * values are relative to this base (NOT to reg_data after the logo_table).
 *
 * Returns 0 on success, -EINVAL on bad firmware.
 */
static int ge2d_fw_parse(struct ge2d_fw_ctx *ctx,
			  const u8 *data, size_t size)
{
	const struct ge2d_fw_header *hdr;
	u32 project_table_size, logo_table_size, reg_data_size;
	size_t expected;

	if (size < sizeof(*hdr)) {
		pr_err("ge2d: firmware too small (%zu bytes)\n", size);
		return -EINVAL;
	}

	hdr = (const struct ge2d_fw_header *)data;

	/* __is_header_valid @ 0xec94: check magic == "logo" */
	if (le32_to_cpu(hdr->magic) != GE2D_FW_MAGIC) {
		pr_err("ge2d: bad firmware magic 0x%08X (expected 0x%08X)\n",
		       le32_to_cpu(hdr->magic), GE2D_FW_MAGIC);
		return -EINVAL;
	}

	project_table_size = le16_to_cpu(hdr->project_table_size);
	logo_table_size    = le16_to_cpu(hdr->logo_table_size);
	reg_data_size      = le32_to_cpu(hdr->reg_data_size);

	/* Sanity: project and logo table sizes must be multiples of entry size */
	if (project_table_size % sizeof(struct ge2d_fw_project_entry) != 0 ||
	    logo_table_size    % sizeof(struct ge2d_fw_logo_entry)    != 0) {
		pr_err("ge2d: firmware table sizes misaligned (proj=%u logo=%u)\n",
		       project_table_size, logo_table_size);
		return -EINVAL;
	}

	/* reg_data_size is NOT required to be a multiple of 16 because it
	 * contains sub-blocks with 8-byte headers + 16-byte entries */

	expected = sizeof(*hdr) + project_table_size +
		   logo_table_size + reg_data_size;
	if (size < expected) {
		pr_err("ge2d: firmware too small: need %zu have %zu\n",
		       expected, size);
		return -EINVAL;
	}

	ctx->hdr              = hdr;
	ctx->project_table    = (const struct ge2d_fw_project_entry *)
				 (data + sizeof(*hdr));
	ctx->num_projects     = project_table_size /
				 sizeof(struct ge2d_fw_project_entry);

	/* logo_table starts immediately after project_table */
	ctx->logo_table       = (const struct ge2d_fw_logo_entry *)
				 (data + sizeof(*hdr) + project_table_size);
	ctx->num_logos        = logo_table_size /
				 sizeof(struct ge2d_fw_logo_entry);

	/*
	 * logo_section_base = logo_table start = parse_reg[48] in IDA.
	 * Logo entry offsets are relative to THIS pointer, not to reg_data.
	 * The logo_table itself occupies the first logo_table_size bytes,
	 * then the register sub-blocks follow.
	 */
	ctx->logo_section_base = data + sizeof(*hdr) + project_table_size;
	ctx->logo_section_total = logo_table_size + reg_data_size;

	return 0;
}

/*
 * ge2d_fw_find_project() — __get_project_info @ 0xe5d4
 * Iterates project table at stride 24 bytes, matches on project_id field.
 * Returns pointer to matching entry, or NULL.
 */
static const struct ge2d_fw_project_entry *
ge2d_fw_find_project(const struct ge2d_fw_ctx *ctx, u32 project_id)
{
	u16 i;

	for (i = 0; i < ctx->num_projects; i++) {
		if (le32_to_cpu(ctx->project_table[i].project_id) == project_id)
			return &ctx->project_table[i];
	}
	return NULL;
}

/*
 * ge2d_fw_find_logo() — __get_logo_table_info @ 0xeb18
 * Iterates logo table at stride 12 bytes, matches on index field.
 * Returns pointer to matching entry, or NULL.
 */
static const struct ge2d_fw_logo_entry *
ge2d_fw_find_logo(const struct ge2d_fw_ctx *ctx, u32 logo_index)
{
	u16 i;

	for (i = 0; i < ctx->num_logos; i++) {
		if (le32_to_cpu(ctx->logo_table[i].index) == logo_index)
			return &ctx->logo_table[i];
	}
	return NULL;
}

/*
 * ge2d_fw_get_stream() — port of __get_reg @ 0xeb98
 *
 * Two-level lookup:
 *   1. Find logo_section via logo_table[stream_type] (logo entry with index==stream_type)
 *   2. Within that section, iterate sub-blocks to find the one where
 *      sub_block.stream_id == project_entry.stream_ids[stream_type]
 *
 * IDA ARM assembly (verified from disasm @ 0xeb98):
 *   R2 = parse_reg[0xC0] + logo_entry->offset  (byte pointer into fw data)
 *   R12 = logo_entry->size
 *   R0 = *(u16*)(project_entry + 8 + 2*stream_type)  (target sub-block id)
 *
 *   loop:
 *     LDR R3, [R2]           ; sub_block->stream_id
 *     CMP R3, R0             ; match?
 *     LDR R3, [R2, #4]       ; sub_block->data_size
 *     BEQ found
 *     ADD R3, R3, #8         ; skip_size = data_size + 8 (header)
 *     ADD R1, R1, R3         ; accumulate consumed bytes
 *     ADD R2, R2, R3         ; advance byte pointer
 *     CMP R12, R1            ; past end?
 *     BHI loop
 *
 *   found:
 *     entries_ptr = R2 + 8   ; skip 8-byte sub-block header
 *     num_entries = R3 >> 4  ; data_size / 16
 *
 * Returns 0 on success, -ENOENT if project/stream/sub-block not found.
 */
static int ge2d_fw_get_stream(const struct ge2d_fw_ctx *ctx,
			       u32 project_id, u32 stream_type,
			       struct ge2d_fw_stream *stream)
{
	const struct ge2d_fw_project_entry *proj;
	const struct ge2d_fw_logo_entry *logo;
	const u8 *section_base;
	u32 section_size;
	u16 target_sub_id;
	u32 pos;

	/* Step 1: find project entry */
	proj = ge2d_fw_find_project(ctx, project_id);
	if (!proj) {
		pr_err("ge2d: project 0x%04X not found in firmware\n",
		       project_id);
		return -ENOENT;
	}

	/* Step 2: find logo section for this stream_type */
	logo = ge2d_fw_find_logo(ctx, stream_type);
	if (!logo) {
		pr_err("ge2d: logo section %u not found\n", stream_type);
		return -ENOENT;
	}

	/*
	 * Step 3: get target sub-block stream_id from project entry.
	 * IDA: target = *(u16*)(project_entry + 8 + 2 * stream_type)
	 * In our struct: stream_ids[stream_type] (array starts at byte 8)
	 */
	if (stream_type >= ARRAY_SIZE(proj->stream_ids)) {
		pr_err("ge2d: stream_type %u exceeds max %zu\n",
		       stream_type,  ARRAY_SIZE(proj->stream_ids));
		return -EINVAL;
	}
	target_sub_id = le16_to_cpu(proj->stream_ids[stream_type]);

	/*
	 * Step 4: locate the section data.
	 * Logo entry offset is relative to logo_section_base (= logo_table start).
	 */
	section_base = ctx->logo_section_base + le32_to_cpu(logo->offset);
	section_size = le32_to_cpu(logo->size);

	/* Bounds check */
	if (section_base + section_size > ctx->logo_section_base + ctx->logo_section_total) {
		pr_err("ge2d: logo section %u overflows firmware data\n",
		       stream_type);
		return -ERANGE;
	}

	/*
	 * Step 5: iterate sub-blocks within this section.
	 * Each sub-block: { u32 stream_id, u32 data_size, u8 entries[data_size] }
	 * Matching IDA __get_reg loop @ 0xec00..0xec20.
	 */
	pos = 0;
	while (pos + sizeof(struct ge2d_fw_sub_block_hdr) <= section_size) {
		const struct ge2d_fw_sub_block_hdr *blk =
			(const struct ge2d_fw_sub_block_hdr *)(section_base + pos);
		u32 blk_stream_id = le32_to_cpu(blk->stream_id);
		u32 blk_data_size = le32_to_cpu(blk->data_size);

		if (blk_stream_id == target_sub_id) {
			/* Found! Entries start after 8-byte header */
			const u8 *entries_ptr = section_base + pos +
						sizeof(struct ge2d_fw_sub_block_hdr);
			u32 num_entries = blk_data_size / sizeof(struct ge2d_fw_reg_entry);

			/* Sanity check */
			if (pos + sizeof(struct ge2d_fw_sub_block_hdr) + blk_data_size > section_size) {
				pr_err("ge2d: sub-block %u overflows section\n",
				       blk_stream_id);
				return -ERANGE;
			}

			stream->entries = (const struct ge2d_fw_reg_entry *)entries_ptr;
			stream->num_entries = num_entries;
			stream->stream_type = stream_type;
			return 0;
		}

		/* Advance past this sub-block: 8-byte header + data_size bytes */
		pos += sizeof(struct ge2d_fw_sub_block_hdr) + blk_data_size;
	}

	pr_err("ge2d: sub-block id %u not found in logo section %u\n",
	       target_sub_id, stream_type);
	return -ENOENT;
}

/* -----------------------------------------------------------------------
 * Panel bitfield update — __update_panel_set_member @ 0xe920
 *
 * Reads or writes a bitfield within reg_entry->value.
 *
 *   dest   != NULL: *dest = (entry->value >> shift) & mask
 *   source >= 0:    entry->value = (entry->value & ~(mask << shift))
 *                                | ((source & mask) << shift)
 *
 * Note: entry is a mutable copy — entries are copied from firmware before
 * patching (see ge2d_stream_alloc_copy()).
 * ----------------------------------------------------------------------- */
static void update_panel_set_member(u32 *dest, int source,
				     struct ge2d_fw_reg_entry *entry,
				     u32 shift, u32 mask)
{
	u32 val = le32_to_cpu(entry->value);

	if (dest)
		*dest = (val >> shift) & mask;

	if (source >= 0) {
		val = (val & ~(mask << shift)) | (((u32)source & mask) << shift);
		entry->value = cpu_to_le32(val);
	}
}

/* -----------------------------------------------------------------------
 * Mutable copy of a stream's register entries for patching
 * ----------------------------------------------------------------------- */
static struct ge2d_fw_reg_entry *
ge2d_stream_alloc_copy(const struct ge2d_fw_stream *stream, gfp_t gfp)
{
	size_t bytes = stream->num_entries * sizeof(struct ge2d_fw_reg_entry);
	struct ge2d_fw_reg_entry *copy;

	copy = kmalloc(bytes, gfp);
	if (!copy)
		return NULL;
	memcpy(copy, stream->entries, bytes);
	return copy;
}

/* -----------------------------------------------------------------------
 * Panel setting update — __update_panel_setting @ 0xf2b8
 *
 * Patches the mutable copy of each stream's register entries with current
 * panel settings before they are written to hardware.
 *
 * Two passes:
 *  Stream 1 (LVDS entries): patch LVDS config, SSC, polarity
 *  Stream 2 (OSD entries):  patch OSD dimensions, timing, AFBD dual_port
 * ----------------------------------------------------------------------- */

/*
 * patch_stream1_lvds() — patch the LVDS/timing stream entries.
 *
 * Port of __update_panel_setting stream 1 pass (IDA @ 0xf2b8..0xf614).
 * Addresses verified from actual firmware project 0x0030 sub-block stream_id=2.
 *
 * IDA maps panel_set indices to these fields:
 *   ps[0]=protocol, ps[1]=bitwidth, ps[2]=data_swap, ps[3]=ssc_span,
 *   ps[4]=ssc_step, ps[5]=ssc_en, ps[7]=de_current, ps[8]=even_data_current,
 *   ps[9]=odd_data_current, ps[10]=vs_invert, ps[11]=hs_invert,
 *   ps[12]=de_invert, ps[13]=dclk_invert, ps[27]=lvds0_pol, ps[28]=lvds1_pol
 */
static void patch_stream1_lvds(struct ge2d_fw_reg_entry *entries, u32 n,
				const struct ge2d_panel_set *ps)
{
	u32 i;
	u32 addr;

	for (i = 0; i < n; i++) {
		addr = le32_to_cpu(entries[i].phys_addr);

		switch (addr) {
		case GE2D_PHYS_LVDS_CFG:
			/*
			 * 0x05800000: LVDS main config register.
			 * IDA _update_panel_set_member calls for addr==0x057E0000
			 * (92274688 decimal = 0x05800000 — IDA decompiler mislabel):
			 *   protocol[5:3], bitwidth[2:0], data_swap[14:14],
			 *   vs_invert[24:24], hs_invert[18:18],
			 *   de_invert[16:16], dclk_invert[17:17]
			 */
			update_panel_set_member(NULL, (int)ps->v[0],
						&entries[i], 6, 0x3U);  /* protocol */
			update_panel_set_member(NULL, (int)ps->v[1],
						&entries[i], 3, 0x3U);  /* bitwidth */
			update_panel_set_member(NULL, (int)ps->v[2],
						&entries[i], 14, 0x1U); /* data_swap */
			update_panel_set_member(NULL, (int)ps->v[10],
						&entries[i], 24, 0x1U); /* vs_invert */
			update_panel_set_member(NULL, (int)ps->v[11],
						&entries[i], 18, 0x1U); /* hs_invert */
			update_panel_set_member(NULL, (int)ps->v[12],
						&entries[i], 16, 0x1U); /* de_invert */
			update_panel_set_member(NULL, (int)ps->v[13],
						&entries[i], 17, 0x1U); /* dclk_invert */
			break;

		case GE2D_PHYS_LVDS_SSC_A:
			/*
			 * 0x058C0020: LVDS SSC/current register A.
			 * IDA: ssc_span[24:24] -> bit 24 mask 63,
			 *       ssc_step[0:0] -> bit 0 mask 7,
			 *       mirror[16:16] -> bit 16 mask 63
			 */
			update_panel_set_member(NULL, (int)ps->v[3],
						&entries[i], 24, 0x3FU); /* ssc_span */
			update_panel_set_member(NULL, (int)ps->v[4],
						&entries[i], 0, 0x7U);   /* ssc_step */
			update_panel_set_member(NULL, (int)ps->v[14],
						&entries[i], 16, 0x3FU); /* mirror */
			break;

		case GE2D_PHYS_LVDS_SSC_B:
			/*
			 * 0x058C0024: LVDS SSC/current register B.
			 * Same layout as A for second LVDS port.
			 */
			update_panel_set_member(NULL, (int)ps->v[3],
						&entries[i], 24, 0x3FU);
			update_panel_set_member(NULL, (int)ps->v[4],
						&entries[i], 0, 0x7U);
			update_panel_set_member(NULL, (int)ps->v[14],
						&entries[i], 16, 0x3FU);
			break;

		case GE2D_PHYS_LVDS_POL:
			/*
			 * 0x0588000C: LVDS polarity register.
			 * IDA: data_swap[12:12] -> bits [14:12] mask 3
			 */
			update_panel_set_member(NULL, (int)ps->v[2],
						&entries[i], 12, 0x3U);
			break;

		case GE2D_PHYS_LVDS_PLL_CFG:
			/*
			 * 0x058C0014: LVDS PLL config — SSC enable bit.
			 * IDA: dclk_invert[24:24] -> bit 24 mask 1
			 * This address appears multiple times (PLL init sequence),
			 * only the last occurrence matters for the panel setting.
			 */
			update_panel_set_member(NULL, (int)ps->v[13],
						&entries[i], 24, 0x1U);
			break;

		default:
			break;
		}
	}
}

/*
 * patch_stream2_osd() — patch the OSD/display stream entries.
 *
 * Port of __update_panel_setting stream 2 pass (IDA @ 0xf634..0xfaf0).
 * Addresses verified from actual firmware project 0x0030 sub-block stream_id=0.
 *
 * panel_set index mapping for stream 2:
 *   ps[4]=dual_port check, ps[15]=dual_port,
 *   ps[17]=htotal, ps[18]=vtotal, ps[19]=hsync, ps[20]=vsync,
 *   ps[21]=hsync_pol, ps[22]=vsync_pol, ps[23]=width, ps[24]=height,
 *   ps[25]=hbp, ps[26]=vbp
 */
static void patch_stream2_osd(struct ge2d_fw_reg_entry *entries, u32 n,
			       const struct ge2d_panel_set *ps)
{
	u32 i;
	u32 addr;
	u32 htotal, vtotal, hsync, vsync, width, height, hbp, vbp;
	u32 dual_port;

	htotal    = ps->v[17];
	vtotal    = ps->v[18];
	hsync     = ps->v[19];
	vsync     = ps->v[20];
	width     = ps->v[23];
	height    = ps->v[24];
	hbp       = ps->v[25];
	vbp       = ps->v[26];
	dual_port = ps->v[15];

	for (i = 0; i < n; i++) {
		addr = le32_to_cpu(entries[i].phys_addr);

		switch (addr) {
		case GE2D_PHYS_AFBD_CFG:
			/*
			 * 0x05600140: AFBD config — dual_port bit.
			 * IDA: _update_panel_set_member(a1+88, a3+4, entry, 2, 3)
			 * → ps[4] used for read, dual_port bit at [3:2]
			 */
			update_panel_set_member(NULL, (int)(dual_port & 0x3U),
						&entries[i], 2, 0x3U);
			break;

		case GE2D_PHYS_MIXER_BASE:
		case GE2D_PHYS_OSD_BASE_ALT:
			/*
			 * 0x0525C000 / 0x0524C010: htotal+hsync packed.
			 * IDA: _update_panel_set_member(NULL, ps[17]+ps[19], entry, 16, 0xFFFF)
			 *      _update_panel_set_member(NULL, ps[18]+ps[20], entry, 0, 0xFFFF)
			 * → [31:16] = htotal+hsync, [15:0] = vtotal+vsync
			 */
			update_panel_set_member(NULL, (int)(vtotal + vsync),
						&entries[i], 0, 0xFFFFU);
			update_panel_set_member(NULL, (int)(htotal + hsync),
						&entries[i], 16, 0xFFFFU);
			break;

		case GE2D_PHYS_MIXER_HACT:
			/*
			 * 0x0525C01C: h_active start.
			 * IDA: _update_panel_set_member(NULL, ps[17]+ps[19], entry, 0, 0xFFFF)
			 *      _update_panel_set_member(NULL, ps[21], entry, 16, 0xFFFF)
			 */
			update_panel_set_member(NULL, (int)(htotal + hsync),
						&entries[i], 0, 0xFFFFU);
			update_panel_set_member(NULL, (int)ps->v[21],
						&entries[i], 16, 0xFFFFU);
			break;

		case GE2D_PHYS_MIXER_HSEND:
			/*
			 * 0x0525C034: h_sync end.
			 * IDA: _update_panel_set_member(NULL, ps[17]+ps[19], entry, 0, 0xFFFF)
			 *      _update_panel_set_member(NULL, ps[21], entry, 16, 0xFFFF)
			 */
			update_panel_set_member(NULL, (int)(htotal + hsync),
						&entries[i], 0, 0xFFFFU);
			update_panel_set_member(NULL, (int)ps->v[21],
						&entries[i], 16, 0xFFFFU);
			break;

		case GE2D_PHYS_MIXER_VTOT:
			/*
			 * 0x0525C020: v_total.
			 * IDA: _update_panel_set_member(NULL, ps[18]+ps[20], entry, 0, 0xFFFF)
			 */
			update_panel_set_member(NULL, (int)(vtotal + vsync),
						&entries[i], 0, 0xFFFFU);
			break;

		case GE2D_PHYS_MIXER_VSEND:
			/*
			 * 0x0525C030: v_sync end.
			 * IDA: _update_panel_set_member(NULL, ps[18]+ps[20], entry, 0, 0xFFFF)
			 *      _update_panel_set_member(NULL, ps[21], entry, 16, 0xFFFF)
			 */
			update_panel_set_member(NULL, (int)(vtotal + vsync),
						&entries[i], 0, 0xFFFFU);
			update_panel_set_member(NULL, (int)ps->v[21],
						&entries[i], 16, 0xFFFFU);
			break;

		case GE2D_PHYS_OSD_VACT_ALT:
			/*
			 * 0x0524C004: OSD v_active alt.
			 * IDA: _update_panel_set_member(NULL, ps[18], entry, 0, 0xFF)
			 *      _update_panel_set_member(NULL, ps[17], entry, 8, 0xFF)
			 */
			update_panel_set_member(NULL, (int)(vtotal & 0xFF),
						&entries[i], 0, 0xFFU);
			update_panel_set_member(NULL, (int)(htotal & 0xFF),
						&entries[i], 8, 0xFFU);
			break;

		case GE2D_PHYS_OSD_TIMING:
			/*
			 * 0x0524C014: OSD timing.
			 * IDA: _update_panel_set_member(NULL, ps[18]+ps[20], entry, 0, 0xFFFF)
			 *      _update_panel_set_member(NULL, ps[21], entry, 16, 0xFFFF)
			 */
			update_panel_set_member(NULL, (int)(vtotal + vsync),
						&entries[i], 0, 0xFFFFU);
			update_panel_set_member(NULL, (int)ps->v[21],
						&entries[i], 16, 0xFFFFU);
			break;

		case GE2D_PHYS_OSDB_VBLEND:
			/*
			 * 0x05280084: OSDB vblend.
			 * IDA: _update_panel_set_member(NULL, ps[21], entry, 0, 0xFFFF)
			 *      _update_panel_set_member(NULL, ps[22], entry, 16, 0xFFFF)
			 */
			update_panel_set_member(NULL, (int)ps->v[21],
						&entries[i], 0, 0xFFFFU);
			update_panel_set_member(NULL, (int)ps->v[22],
						&entries[i], 16, 0xFFFFU);
			break;

		case GE2D_PHYS_OSDB_HBLEND_A:
			/*
			 * 0x05280088: OSDB hblend A.
			 * IDA checks: (ps[4] & ~2) == 1 → dual_port path
			 * If dual_port==1: val = ps[18]+ps[20]-1 (vtotal+vsync-1)
			 * If dual_port==3: val = ps[18]+ps[20]
			 */
			{
				u32 v = vtotal + vsync;

				if ((dual_port & ~2U) == 1)
					v -= 1;
				update_panel_set_member(NULL, (int)v,
							&entries[i], 0, 0xFFFFU);
			}
			break;

		case GE2D_PHYS_OSDB_HBLEND_B:
			/*
			 * 0x0528008C: OSDB hblend B.
			 * IDA: val = ps[17]+ps[19]-77 (htotal+hsync-77, clamped to 0)
			 */
			{
				int v = (int)(htotal + hsync) - 77;

				if (v < 0)
					v = 0;
				update_panel_set_member(NULL, v,
							&entries[i], 0, 0xFFFFU);
			}
			break;

		default:
			break;
		}
	}
}

/* -----------------------------------------------------------------------
 * OSD framebuffer address update — __update_osd_buf_addr @ 0xe824
 *
 * Scans stream 2 entries for address == osd_base + 0x178 (376).
 * When fb_phys == (phys_addr_t)-1: clear bit 0 of value (disable scanout).
 * Otherwise: set entry->value = fb_phys.
 * ----------------------------------------------------------------------- */
/*
 * update_osd_buf_addr() — patch framebuffer physical address in OSD stream
 *
 * Port of __update_osd_buf_addr @ 0xe824.
 *
 * Scans entries for addr == GE2D_FB_ADDR_REG (0x05600178).
 * Verified from actual firmware: entry[12] in OSD sub-block for project 0x0030
 * has addr=0x05600178, val=0x6C100000 (Stock Android FB).
 *
 * When fb_phys == -1: clear bit 0 of value (disable scanout path in IDA).
 * Otherwise: set entry->value = fb_phys.
 */
static void update_osd_buf_addr(struct ge2d_fw_reg_entry *entries, u32 n,
				 phys_addr_t fb_phys)
{
	u32 i;

	for (i = 0; i < n; i++) {
		if (le32_to_cpu(entries[i].phys_addr) != GE2D_FB_ADDR_REG)
			continue;

		if (fb_phys == (phys_addr_t)-1) {
			/* Disable path: clear bit 0 */
			u32 v = le32_to_cpu(entries[i].value);

			v &= ~1U;
			entries[i].value = cpu_to_le32(v);
		} else {
			entries[i].value = cpu_to_le32((u32)fb_phys);
		}

		pr_info("ge2d: patched FB addr entry[%u]: 0x%08X -> 0x%08lX\n",
			i, GE2D_FB_ADDR_REG, (unsigned long)fb_phys);
		return;  /* only one FB addr entry per stream */
	}

	pr_warn("ge2d: FB addr register 0x%08X not found in stream\n",
		GE2D_FB_ADDR_REG);
}

/* -----------------------------------------------------------------------
 * Register write loop — __write_reg @ 0xf0a8
 *
 * For each entry:
 *   type 0..4:  read-modify-write via ioremap per-op
 *   type 0xFE:  clear then set bits
 *   type 0xFF:  udelay(value)
 *
 * If stream_type == 2 (OSD): write mixer init value before loop.
 *
 * dsb(st) + mb() before each writel matches stock __dsb(0xE) + arm_heavy_mb().
 * ----------------------------------------------------------------------- */
static void ge2d_write_stream(const struct ge2d_fw_reg_entry *entries,
			       u32 num_entries, u32 stream_type)
{
	u32 i;
	u32 addr, val, mask, type, old, new_val;
	void __iomem *ptr;

	/* __write_reg 0xf270: if stream_type == 2, write mixer init */
	if (stream_type == 2) {
		ptr = ioremap(GE2D_MIXER_BASE_PHYS + GE2D_MIXER_INIT_OFF, 4);
		if (ptr) {
			dsb(st);
			mb();
			writel(GE2D_MIXER_INIT_VAL, ptr);
			iounmap(ptr);
		}
	}

	for (i = 0; i < num_entries; i++) {
		addr = le32_to_cpu(entries[i].phys_addr);
		val  = le32_to_cpu(entries[i].value);
		mask = le32_to_cpu(entries[i].mask);
		type = le32_to_cpu(entries[i].type);

		if (type == GE2D_REG_TYPE_DELAY) {
			/* type 0xFF: delay in microseconds */
			udelay(val);
			continue;
		}

		if (type == GE2D_REG_TYPE_CLR_SET) {
			/* type 0xFE: clear bits then set bits */
			ptr = ioremap(addr, 4);
			if (!ptr) {
				pr_err("ge2d: ioremap 0x%08X failed (clr/set)\n",
				       addr);
				continue;
			}
			old = readl(ptr);
			dsb(st);
			mb();
			writel(old & ~mask, ptr);
			dsb(st);
			mb();
			writel(old | mask, ptr);
			iounmap(ptr);
			continue;
		}

		if (type <= GE2D_REG_TYPE_RMW_MAX) {
			/*
			 * Read-modify-write:
			 *   new = old ^ (mask & (val ^ old))
			 *       = (old & ~mask) | (val & mask)
			 * Stock does read and write as separate ioremap/iounmap pairs.
			 */

			/* Step 1: read current value */
			ptr = ioremap(addr, 4);
			if (!ptr) {
				pr_err("ge2d: ioremap 0x%08X failed (read)\n",
				       addr);
				continue;
			}
			old = readl(ptr);
			iounmap(ptr);

			/* Step 2: compute new value */
			new_val = old ^ (mask & (val ^ old));

			/* Step 3: write new value */
			ptr = ioremap(addr, 4);
			if (!ptr) {
				pr_err("ge2d: ioremap 0x%08X failed (write)\n",
				       addr);
				continue;
			}
			dsb(st);
			mb();
			writel(new_val, ptr);
			iounmap(ptr);
			continue;
		}

		/* Unknown type — log and skip */
		pr_warn("ge2d: unknown reg entry type %u at 0x%08X, skipping\n",
			type, addr);
	}
}

/* -----------------------------------------------------------------------
 * Public API
 * ----------------------------------------------------------------------- */

/**
 * ge2d_firmware_load() — Main entry point for firmware init sequence.
 *
 * Called from osd_resume_init(). Sequence:
 *  1. Enable display clock domain via sunxi_tvtop_clk_get(0)
 *  2. Load LogoRegData.bin via request_firmware()
 *  3. Validate header magic
 *  4. Find project entry matching gdev->panel.project_id
 *  5. Build flat panel_set[29] array from panel config
 *  6. For each stream (1=LVDS, 2=OSD):
 *     a. Get stream entries via ge2d_fw_get_stream()
 *     b. Allocate mutable copy
 *     c. Patch panel settings into the copy
 *     d. Patch OSD framebuffer address (stream 2 only)
 *     e. Write all register entries to hardware
 *     f. Free the copy
 *  7. Release firmware
 */
int ge2d_firmware_load(struct ge2d_device *gdev)
{
	const struct firmware *fw = NULL;
	struct ge2d_fw_ctx ctx;
	struct ge2d_panel_set ps;
	struct ge2d_fw_stream stream;
	struct ge2d_fw_reg_entry *entries_copy = NULL;
	int ret;

	dev_info(gdev->dev, "ge2d: calling sunxi_tvtop_clk_get(0)\n");
	ret = sunxi_tvtop_clk_get(0);
	dev_info(gdev->dev, "ge2d: sunxi_tvtop_clk_get(0) returned %d\n", ret);
	if (ret) {
		dev_err(gdev->dev, "ge2d: sunxi_tvtop_clk_get failed: %d\n", ret);
		return ret;
	}

	dev_info(gdev->dev, "ge2d: loading firmware %s\n", GE2D_FW_FILENAME);

	ret = request_firmware(&fw, GE2D_FW_FILENAME, gdev->dev);
	if (ret) {
		dev_err(gdev->dev, "ge2d: failed to load %s: %d\n",
			GE2D_FW_FILENAME, ret);
		return ret;
	}

	dev_info(gdev->dev, "ge2d: firmware loaded, size=%zu\n", fw->size);

	/* Parse and validate firmware */
	ret = ge2d_fw_parse(&ctx, fw->data, fw->size);
	if (ret) {
		dev_err(gdev->dev, "ge2d: firmware parse failed: %d\n", ret);
		goto out_release;
	}

	dev_info(gdev->dev, "ge2d: fw version=0x%08X projects=%u logos=%u\n",
		 le32_to_cpu(ctx.hdr->version),
		 ctx.num_projects, ctx.num_logos);

	/* Verify project exists (matches __is_project_valid @ 0xe634) */
	if (!ge2d_fw_find_project(&ctx, gdev->panel.project_id)) {
		dev_err(gdev->dev,
			"ge2d: project_id 0x%04X not found in firmware\n",
			gdev->panel.project_id);
		ret = -ENODEV;
		goto out_release;
	}

	/* Build flat panel_set array from driver's panel config */
	build_panel_set(&gdev->panel, &ps);

	/*
	 * Stock flow (IDA: osd_resume_request @ 0xff90):
	 *   tvtop_clk_get(0) -- skipped, U-Boot clocks active
	 *   for stream_idx = 0, 1, 2:
	 *     get_reg(obj, project_id, stream_idx, &data)
	 *     write_reg(&data)
	 *
	 * HY310 (project 0x0030) stream_ids = [1, 2, 0]:
	 *   idx 0 -> stream_id=1 in Logo[0] -> Init/clock stream
	 *   idx 1 -> stream_id=2 in Logo[1] -> LVDS (34 entries)
	 *   idx 2 -> stream_id=0 in Logo[2] -> OSD  (55 entries)
	 */

	/* ---- Stream 0: Init (clock gates, TVTOP config) ---- */
	ret = ge2d_fw_get_stream(&ctx, gdev->panel.project_id,
				  GE2D_STREAM_INIT, &stream);
	if (ret) {
		dev_info(gdev->dev, "ge2d: no init stream (idx 0) for this project, skipping\n");
	} else {
		entries_copy = ge2d_stream_alloc_copy(&stream, GFP_KERNEL);
		if (!entries_copy) {
			ret = -ENOMEM;
			goto out_release;
		}
		dev_info(gdev->dev, "ge2d: writing init stream (%u entries)\n",
			 stream.num_entries);
		/* ge2d_write_stream(entries_copy, stream.num_entries, GE2D_STREAM_INIT); */
	/* SKIPPED: firmware streams destroy MIPS display scanout path.
	 * Re-enable once ARM-side VBlender (0x05200000) is powered. */
	dev_info(gdev->dev, "ge2d: init stream SKIPPED (preserving MIPS scanout, %u entries)\n",
		 stream.num_entries);
		kfree(entries_copy);
		entries_copy = NULL;
	}

	/* ---- Stream 1: LVDS / timing ---- */
	ret = ge2d_fw_get_stream(&ctx, gdev->panel.project_id,
				  GE2D_STREAM_LVDS, &stream);
	if (ret) {
		dev_err(gdev->dev, "ge2d: failed to get LVDS stream: %d\n", ret);
		goto out_release;
	}

	entries_copy = ge2d_stream_alloc_copy(&stream, GFP_KERNEL);
	if (!entries_copy) {
		ret = -ENOMEM;
		goto out_release;
	}

	dev_info(gdev->dev, "ge2d: patching LVDS stream (%u entries)\n",
		 stream.num_entries);
	patch_stream1_lvds(entries_copy, stream.num_entries, &ps);

	dev_info(gdev->dev, "ge2d: writing LVDS stream (%u entries)\n",
		 stream.num_entries);
	/* ge2d_write_stream(entries_copy, stream.num_entries, GE2D_STREAM_LVDS); */
	/* SKIPPED: firmware streams destroy MIPS display scanout path.
	 * Re-enable once ARM-side VBlender (0x05200000) is powered. */
	dev_info(gdev->dev, "ge2d: LVDS stream SKIPPED (preserving MIPS scanout, %u entries)\n",
		 stream.num_entries);

	kfree(entries_copy);
	entries_copy = NULL;

	/* ---- Stream 2: OSD / display ---- */
	ret = ge2d_fw_get_stream(&ctx, gdev->panel.project_id,
				  GE2D_STREAM_OSD, &stream);
	if (ret) {
		dev_err(gdev->dev, "ge2d: failed to get OSD stream: %d\n", ret);
		goto out_release;
	}

	entries_copy = ge2d_stream_alloc_copy(&stream, GFP_KERNEL);
	if (!entries_copy) {
		ret = -ENOMEM;
		goto out_release;
	}

	dev_info(gdev->dev, "ge2d: patching OSD stream (%u entries)\n",
		 stream.num_entries);
	patch_stream2_osd(entries_copy, stream.num_entries, &ps);

	dev_info(gdev->dev, "ge2d: updating OSD buf addr to 0x%08lx\n",
		 (unsigned long)gdev->fb_phys);
	update_osd_buf_addr(entries_copy, stream.num_entries, gdev->fb_phys);

	dev_info(gdev->dev, "ge2d: writing OSD stream (%u entries)\n",
		 stream.num_entries);
	/* ge2d_write_stream(entries_copy, stream.num_entries, GE2D_STREAM_OSD); */
	/* SKIPPED: firmware streams destroy MIPS display scanout path.
	 * Re-enable once ARM-side VBlender (0x05200000) is powered. */
	dev_info(gdev->dev, "ge2d: OSD stream SKIPPED (preserving MIPS scanout, %u entries)\n",
		 stream.num_entries);

	kfree(entries_copy);
	entries_copy = NULL;

	dev_info(gdev->dev, "ge2d: firmware load complete\n");
	ret = 0;

	ret = 0;

out_release:
	kfree(entries_copy);
	release_firmware(fw);
	return ret;
}
EXPORT_SYMBOL_GPL(ge2d_firmware_load);

/**
 * ge2d_firmware_unload() — Release any firmware-related resources.
 *
 * Currently a no-op because firmware is loaded and released within
 * ge2d_firmware_load() — no persistent fw handle is stored.
 * Provided for symmetry and future use.
 */
void ge2d_firmware_unload(struct ge2d_device *gdev)
{
	dev_info(gdev->dev, "ge2d: firmware unloaded\n");
}
EXPORT_SYMBOL_GPL(ge2d_firmware_unload);

MODULE_DESCRIPTION("Sunxi GE2D display firmware loader");
MODULE_LICENSE("GPL v2");
