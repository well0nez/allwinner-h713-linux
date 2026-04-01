/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * sunxi_ge2d_firmware.h — Firmware loader for ge2d display driver
 *
 * Parses LogoRegData.bin, writes register streams to hardware, and patches
 * panel timing settings before writing. Matches stock ge2d_dev.ko behavior.
 */

#ifndef SUNXI_GE2D_FIRMWARE_H
#define SUNXI_GE2D_FIRMWARE_H

#include <linux/types.h>
#include "sunxi_ge2d.h"

/* -----------------------------------------------------------------------
 * Firmware binary file format
 * LogoRegData.bin, verified 15652-byte file, little-endian
 * ----------------------------------------------------------------------- */

#define GE2D_FW_MAGIC		0x6F676F6CU	/* "logo" in little-endian */
#define GE2D_FW_FILENAME	"LogoRegData.bin"

/* Top-level firmware header (16 bytes at offset 0) */
struct ge2d_fw_header {
	__le32	magic;			/* 0x6F676F6C */
	__le32	version;
	__le16	project_table_size;	/* bytes; each entry = 24 bytes */
	__le16	logo_table_size;	/* bytes; each entry = 12 bytes */
	__le32	reg_data_size;		/* bytes; total register data after logo table */
} __packed;

/*
 * Project entry — 24 bytes each
 * Accessed at stride 24 (6 DWORDs) within project_table.
 *
 * IDA accesses the sub-block stream_id for a given stream_type via:
 *   target_id = *(u16*)(project_entry + 8 + 2 * stream_type)
 * This indexes into a variable-length u16 array starting at byte 8.
 * For stream_type 0..N, the array has N+1 entries.
 *
 * For project 0x0030: stream_ids = {1, 2, 0, ...}
 *   stream_type=0 → target sub-block id=1
 *   stream_type=1 → target sub-block id=2
 *   stream_type=2 → target sub-block id=0
 */
struct ge2d_fw_project_entry {
	__le32	project_id;		/* e.g. 0x0030 for HY310 */
	__le32	version_info;
	__le16	stream_ids[4];		/* sub-block stream_id per stream_type */
	u8	padding[8];		/* 0x11111111... */
} __packed;

/* Logo/stream table entry — 12 bytes each */
struct ge2d_fw_logo_entry {
	__le32	index;		/* stream index number (0, 1, 2) */
	__le32	offset;		/* byte offset from logo_table start */
	__le32	size;		/* byte size of this logo section's data */
} __packed;

/*
 * Sub-block header — 8 bytes, embedded within each logo section.
 *
 * Each logo section contains multiple sub-blocks, one per project variant.
 * __get_reg (IDA @ 0xeb98) iterates these 8-byte headers to find the
 * sub-block whose stream_id matches the project's target stream_id.
 *
 * Layout within a logo section:
 *   { sub_block_header, reg_entry[data_size/16] } repeated N times
 */
struct ge2d_fw_sub_block_hdr {
	__le32	stream_id;	/* matched against project's stream_ids[stream_type] */
	__le32	data_size;	/* size in bytes of following reg_entry array */
} __packed;

/*
 * Register entry — 16 bytes each
 * Processed by __write_reg dispatch in stock driver.
 */
struct ge2d_fw_reg_entry {
	__le32	phys_addr;	/* physical MMIO address (0 for special entries) */
	__le32	value;		/* value to write (or delay_us for type 0xFF) */
	__le32	mask;		/* bitmask for RMW operation */
	__le32	type;		/* dispatch type; see GE2D_REG_TYPE_* */
} __packed;

/* Register entry type codes */
#define GE2D_REG_TYPE_RMW_MAX	4	/* types 0..4: read-modify-write */
#define GE2D_REG_TYPE_CLR_SET	0xFE	/* clear bits, then set bits */
#define GE2D_REG_TYPE_DELAY	0xFF	/* udelay(value) */

/*
 * Stream type indices used with ge2d_fw_project_entry.stream_indices[].
 * Stock driver passes stream_type 1 for LVDS/timing, 2 for OSD/display.
 */
#define GE2D_STREAM_INIT	0
#define GE2D_STREAM_LVDS	1
#define GE2D_STREAM_OSD		2

/* -----------------------------------------------------------------------
 * Internal parsed-firmware context (populated by ge2d_fw_parse)
 * ----------------------------------------------------------------------- */

/*
 * Holds pointers into the firmware blob after validation.
 * All pointers remain valid as long as `fw` (struct firmware*) is held.
 *
 * Note: logo_section_base corresponds to parse_reg[48] (IDA offset 0xC0)
 * in the stock code. It points to the start of the logo table, and
 * logo_entry->offset values are relative to this base.
 */
struct ge2d_fw_ctx {
	const struct ge2d_fw_header		*hdr;
	const struct ge2d_fw_project_entry	*project_table;
	u16					 num_projects;
	const struct ge2d_fw_logo_entry		*logo_table;
	u16					 num_logos;
	const u8				*logo_section_base;  /* = logo_table start (parse_reg[48]) */
	u32					 logo_section_total; /* total bytes from logo_table to EOF */
};

/*
 * Resolved stream descriptor returned by ge2d_fw_get_stream().
 * Points directly into fw_ctx->reg_data — no extra allocation.
 */
struct ge2d_fw_stream {
	const struct ge2d_fw_reg_entry	*entries;
	u32				 num_entries;
	u32				 stream_type;	/* GE2D_STREAM_* */
};

/*
 * Flat panel settings array, matching stock g_panel_set[29].
 * Built from ge2d_panel_config, skipping pwm/delay fields.
 */
#define GE2D_PANEL_SET_COUNT	29

struct ge2d_panel_set {
	u32 v[GE2D_PANEL_SET_COUNT];
};

/* -----------------------------------------------------------------------
 * Physical addresses matched during panel setting update
 * ----------------------------------------------------------------------- */

/*
 * Addresses matched in __update_panel_setting (IDA @ 0xf2b8).
 * Verified by cross-referencing IDA decimal constants with actual
 * firmware entries for project 0x0030.
 *
 * IMPORTANT: Original IDA decompilation shows these as decimal integers.
 * The hex conversions were verified via Python int→hex.
 */

/* Stream 1 — LVDS PHY / timing (Logo[1]) */
#define GE2D_PHYS_LVDS_CFG	0x05800000U	/* IDA 92274688: LVDS main config */
#define GE2D_PHYS_LVDS_PLL_CFG	0x058C0014U	/* IDA 93061140: LVDS PLL config */
#define GE2D_PHYS_LVDS_PLL_DAT	0x058C0018U	/* IDA 93061144: LVDS PLL data */
#define GE2D_PHYS_LVDS_SSC_A	0x058C0020U	/* IDA 93061152: LVDS SSC/current A */
#define GE2D_PHYS_LVDS_SSC_B	0x058C0024U	/* IDA 93061156: LVDS SSC/current B */
#define GE2D_PHYS_LVDS_POL	0x0588000CU	/* IDA 92798988: LVDS polarity/current */

/* Stream 2 — OSD / display (Logo[2]) */
#define GE2D_PHYS_AFBD_CFG	0x05600140U	/* IDA 90177856: AFBD config (dual_port) */
#define GE2D_PHYS_MIXER_BASE	0x0525C000U	/* IDA 86360064: Mixer/OSD htotal+vsync */
#define GE2D_PHYS_MIXER_VACT	0x0525C004U	/* IDA 86360068: Mixer v_active */
#define GE2D_PHYS_MIXER_HACT	0x0525C01CU	/* IDA 86360092: Mixer h_active */
#define GE2D_PHYS_MIXER_VTOT	0x0525C020U	/* IDA 86360096: Mixer v_total */
#define GE2D_PHYS_MIXER_VSEND	0x0525C030U	/* IDA 86360112: Mixer v_sync end */
#define GE2D_PHYS_MIXER_HSEND	0x0525C034U	/* IDA 86360116: Mixer h_sync end */
#define GE2D_PHYS_OSD_VACT_ALT	0x0524C004U	/* IDA 86294532: OSD v_active alt */
#define GE2D_PHYS_OSD_BASE_ALT	0x0524C010U	/* IDA 86294544: OSD base alt */
#define GE2D_PHYS_OSD_TIMING	0x0524C014U	/* IDA 86294548: OSD timing */
#define GE2D_PHYS_OSDB_VBLEND	0x05280084U	/* IDA 86507652: OSDB vblend start */
#define GE2D_PHYS_OSDB_HBLEND_A 0x05280088U	/* IDA 86507656: OSDB hblend A */
#define GE2D_PHYS_OSDB_HBLEND_B 0x0528008CU	/* IDA 86507660: OSDB hblend B */

/*
 * AFBD framebuffer address register.
 * Verified from actual LogoRegData.bin project 0x0030 OSD stream entry[12]:
 *   addr=0x05600178 val=0x6C100000 (Stock Android FB phys addr)
 * This must be patched to our reserved-memory FB address (0x4BF41000).
 */
#define GE2D_FB_ADDR_REG	0x05600178U

/* Mixer base write for stream type 2 pre-write */
#define GE2D_MIXER_BASE_PHYS	0x0525C000U
#define GE2D_MIXER_INIT_OFF	0x38U
#define GE2D_MIXER_INIT_VAL	256U

/* -----------------------------------------------------------------------
 * Public API
 * ----------------------------------------------------------------------- */

/**
 * ge2d_firmware_load() — Load firmware, apply panel patches, write registers.
 *
 * Called from osd_resume_init(). Loads LogoRegData.bin via request_firmware(),
 * validates the header, finds project_id matching gdev->panel.project_id,
 * applies panel timing patches, then writes both register streams to hardware.
 *
 * Returns 0 on success, negative errno on failure.
 */
int ge2d_firmware_load(struct ge2d_device *gdev);

/**
 * ge2d_firmware_unload() — Release firmware resources.
 *
 * Must be called from the driver's remove/cleanup path.
 */
void ge2d_firmware_unload(struct ge2d_device *gdev);

#endif /* SUNXI_GE2D_FIRMWARE_H */
