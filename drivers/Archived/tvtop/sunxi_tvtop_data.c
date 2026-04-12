// SPDX-License-Identifier: GPL-2.0
/*
 * Allwinner H713 TV Subsystem Top — Static Hardware Data Tables
 *
 * Clock rates, register values, and hardware descriptions extracted
 * from stock sunxi_tvtop.ko binary (.data/.rodata sections).
 */

#include "sunxi_tvtop.h"

/* ================================================================
 * Clock descriptor arrays (per submodule)
 * Each entry: { name, { rate_1080p, rate_generic, rate_360p, rate_720p }, parent }
 * NULL name terminates array.
 * ================================================================ */

static const struct tvtop_clk_desc tvdisp_clks[] = {
	{ "svp_dtl_clk",  { 200000000, 200000000, 200000000,         0 }, 1200000000 },
	{ "deint_clk",    { 1032000000, 1032000000, 516000000, 516000000 }, 1032000000 },
	{ "panel_clk",    { 1032000000, 516000000, 516000000, 516000000 }, 1032000000 },
	{ NULL, {0}, 0 },
};

static const struct tvtop_clk_desc tvcap_clks[] = {
	{ "tcd3_clk",         {  27000000,  27000000, 0, 0 }, 1296000000 },
	{ "vincap_dma_clk",   { 300000000, 300000000, 0, 0 },  600000000 },
	{ "hdmi_audio_clk",   { 1152000000, 1152000000, 0, 0 }, 1152000000 },
	{ "cap_300m",         { 0, 0, 0, 0 }, 0 },
	{ "hdmi_audio_bus",   { 0, 0, 0, 0 }, 0 },
	{ NULL, {0}, 0 },
};

static const struct tvtop_clk_desc tvfe_clks[] = {
	{ "cip_tsp_clk",      { 333000000, 333000000, 0, 0 }, 1296000000 },
	{ "cip_tsx_clk",      { 200000000, 200000000, 0, 0 },  600000000 },
	{ "cip_mcx_clk",      { 100000000, 100000000, 0, 0 },  600000000 },
	{ "tsa_tsp_clk",      { 333000000, 333000000, 0, 0 }, 1296000000 },
	{ "tsa432_clk",       { 432000000, 432000000, 0, 0 }, 1296000000 },
	{ "audio_ihb_clk",    { 200000000, 200000000, 0, 0 },  600000000 },
	{ "i2h_clk",          { 200000000, 200000000, 0, 0 }, 1200000000 },
	{ "cip_mts0_clk",     {  27000000,  27000000, 0, 0 }, 1296000000 },
	{ "cip27_clk",        {  27000000,  27000000, 0, 0 },  324000000 },
	{ "tvfe_1296M_clk",   { 1296000000, 1296000000, 0, 0 }, 1296000000 },
	{ "audio_cpu",        { 400000000, 400000000, 0, 0 }, 1200000000 },
	{ "audio_umac",       { 200000000, 200000000, 0, 0 },  600000000 },
	{ "mpg0",             {  27000000,  27000000, 0, 0 }, 1296000000 },
	{ "mpg1",             {  27000000,  27000000, 0, 0 }, 1296000000 },
	{ "adc",              {  54000000,  54000000, 0, 0 }, 1296000000 },
	{ NULL, {0}, 0 },
};

/* ================================================================
 * Per-submodule hardware descriptions
 * Order: [0]=tvdisp, [1]=tvcap, [2]=tvfe
 * ================================================================ */

const struct tvtop_hw_data tvtop_hw_data[TVTOP_SUB_COUNT] = {
	[TVTOP_SUB_TVDISP] = {
		.name      = "tvdisp",
		.iomap_idx = 0,
		.rst_name  = "reset_bus_disp",
		.clk_name  = "clk_bus_disp",
		.pm_domain = NULL,
		.clk_descs = tvdisp_clks,
	},
	[TVTOP_SUB_TVCAP] = {
		.name      = "tvcap",
		.iomap_idx = 1,
		.rst_name  = "reset_bus_tvcap",
		.clk_name  = "clk_bus_tvcap",
		.pm_domain = "pd_tvcap",
		.clk_descs = tvcap_clks,
	},
	[TVTOP_SUB_TVFE] = {
		.name      = "tvfe",
		.iomap_idx = 2,
		.rst_name  = "reset_bus_demod",
		.clk_name  = "clk_bus_demod",
		.pm_domain = "pd_tvfe",
		.clk_descs = tvfe_clks,
	},
};

/* ================================================================
 * Display register table (tvdisp subsystem)
 *
 * Written to tvdisp iobase on enable (after first init).
 * 7 register writes per resolution type.
 * Indexed as: tvtop_disp_regs[resolution_type][entry_index]
 *
 * Only difference: type 0 (1080p) has 0xFFF000EF for reg 0x84,
 * all others have 0xFFF000FF.
 * ================================================================ */

const struct tvtop_reg_entry
tvtop_disp_regs[TVTOP_RES_TYPE_COUNT][TVTOP_DISP_REG_COUNT] = {
	/* Resolution type 0: 1920×1080 */
	[TVTOP_RES_1080P] = {
		{ 0x04, 0x00000001 },
		{ 0x44, 0x11111111 },
		{ 0x88, 0xFFFFFFFF },
		{ 0x00, 0x00011111 },
		{ 0x40, 0x00011111 },
		{ 0x80, 0x00001111 },
		{ 0x84, 0xFFF000EF },
	},
	/* Resolution type 1: (same as type 2/3 in stock) */
	[1] = {
		{ 0x04, 0x00000001 },
		{ 0x44, 0x11111111 },
		{ 0x88, 0xFFFFFFFF },
		{ 0x00, 0x00011111 },
		{ 0x40, 0x00011111 },
		{ 0x80, 0x00001111 },
		{ 0x84, 0xFFF000FF },
	},
	/* Resolution type 2: 640×360 */
	[TVTOP_RES_360P] = {
		{ 0x04, 0x00000001 },
		{ 0x44, 0x11111111 },
		{ 0x88, 0xFFFFFFFF },
		{ 0x00, 0x00011111 },
		{ 0x40, 0x00011111 },
		{ 0x80, 0x00001111 },
		{ 0x84, 0xFFF000FF },
	},
	/* Resolution type 3: 1280×720 / 1366×768 / generic */
	[TVTOP_RES_720P] = {
		{ 0x04, 0x00000001 },
		{ 0x44, 0x11111111 },
		{ 0x88, 0xFFFFFFFF },
		{ 0x00, 0x00011111 },
		{ 0x40, 0x00011111 },
		{ 0x80, 0x00001111 },
		{ 0x84, 0xFFF000FF },
	},
};
