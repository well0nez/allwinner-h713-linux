// SPDX-License-Identifier: GPL-2.0-only

#include <linux/bitops.h>
#include <linux/module.h>
#include <linux/string.h>

#include "audio_bridge.h"

/* Forward declarations for I2SO subsystem */
static void trid_i2so_init(struct trid_audio_bridge *bridge);
static int trid_i2so_start(struct trid_audio_bridge *bridge, unsigned int ch,
			   unsigned int rate, unsigned int channels,
			   unsigned int sample_bits);
static void trid_i2so_stop(struct trid_audio_bridge *bridge, unsigned int ch);

static void trid_audbrg_irq_enable(struct trid_audio_bridge *bridge, bool enable)
{
	trid_reg_update_bits(bridge, TRID_AUDBRG_GLOBAL_IRQ_EN, BIT(0),
			     enable ? BIT(0) : 0);
}

static u32 trid_audif_known_irq_mask(void)
{
	return 0x300000 | 0x77000 | 0x780 | 0x8804 | 0x10007B;
}

static u32 trid_audif_iface_mask(enum trid_interface_type iface)
{
	switch (iface) {
	case TRID_IFACE_I2SO0:
		return 0x40000;
	case TRID_IFACE_I2SO1:
		return 0x20000;
	case TRID_IFACE_I2SO2:
		return 0x10000;
	case TRID_IFACE_SPDO0:
		return 0x8804;
	case TRID_IFACE_SPDI0:
		return 0x300052;
	case TRID_IFACE_SPDI1:
		return 0x300029;
	default:
		return 0;
	}
}

static u32 trid_audif_route_value(enum trid_interface_type iface)
{
	switch (iface) {
	case TRID_IFACE_I2SO0:
		return 0x3;
	case TRID_IFACE_I2SO1:
		return 0xc;
	case TRID_IFACE_I2SO2:
		return 0x30;
	case TRID_IFACE_SPDI0:
		return 0x400;
	case TRID_IFACE_SPDI1:
		return 0x800;
	default:
		return 0;
	}
}

static phys_addr_t trid_i2so_data_reg(enum trid_interface_type iface)
{
	switch (iface) {
	case TRID_IFACE_I2SO0:
		return TRID_AUDIF_ABPO1_DATA;
	case TRID_IFACE_I2SO1:
		return TRID_AUDIF_ABPO2_DATA;
	case TRID_IFACE_I2SO2:
		return TRID_AUDIF_ABPO3_DATA;
	default:
		return 0;
	}
}

static phys_addr_t trid_i2so_clk_reg(enum trid_interface_type iface)
{
	switch (iface) {
	case TRID_IFACE_I2SO0:
		return TRID_AUDIF_ABPO1_CLK;
	case TRID_IFACE_I2SO1:
		return TRID_AUDIF_ABPO2_CLK;
	case TRID_IFACE_I2SO2:
		return TRID_AUDIF_ABPO3_CLK;
	default:
		return 0;
	}
}

/*
 * trid_spdi_cfg_reg: returns the config register for a SPDI channel.
 * IDA confirms: SPDI1 cfg=0x6146038, status=0x614603c, data=0x6146040
 *               SPDI2 cfg=0x6146048, status=0x614604c, data=0x6146050
 * The old SPDI1_CTRL (0x34) and SPDI2_CTRL (0x44) do not exist in hardware.
 */
static phys_addr_t trid_spdi_cfg_reg(enum trid_interface_type iface)
{
	return iface == TRID_IFACE_SPDI1 ? TRID_AUDIF_SPDI2_CFG :
		TRID_AUDIF_SPDI1_CFG;
}

static phys_addr_t trid_spdi_data_reg(enum trid_interface_type iface)
{
	return iface == TRID_IFACE_SPDI1 ? TRID_AUDIF_SPDI2_DATA :
		TRID_AUDIF_SPDI1_DATA;
}

static phys_addr_t trid_spdi_status_reg(enum trid_interface_type iface)
{
	return iface == TRID_IFACE_SPDI1 ? TRID_AUDIF_SPDI2_STATUS :
		TRID_AUDIF_SPDI1_STATUS;
}

static unsigned int trid_spdo_rate_code(unsigned int rate)
{
	switch (rate) {
	case 32000:
		return 0x3;
	case 44100:
		return 0x0;
	case 48000:
		return 0x2;
	case 88200:
		return 0x8;
	case 96000:
		return 0xA;
	case 176400:
		return 0xC;
	case 192000:
		return 0xE;
	default:
		return 0x2;
	}
}

static void trid_i2so_program_fs(struct trid_audio_bridge *bridge,
				 enum trid_interface_type iface,
				 unsigned int rate,
				 unsigned int channels,
				 unsigned int sample_bits)
{
	phys_addr_t clk_reg;
	u64 bitclock;
	u64 frame_clk;
	u64 div_fp16;

	clk_reg = trid_i2so_clk_reg(iface);
	if (!clk_reg || !rate)
		return;

	bitclock = (u64)rate * max_t(unsigned int, channels, 1) *
		   max_t(unsigned int, sample_bits, 16);
	frame_clk = rate + (bitclock >> 8);
	if (!frame_clk)
		return;

	div_fp16 = DIV_ROUND_CLOSEST_ULL(324000000ULL << 16, frame_clk);
	trid_reg_write(bridge, clk_reg, (u32)div_fp16);
}

static void trid_spdo_program(struct trid_audio_bridge *bridge,
			      unsigned int rate,
			      unsigned int channels,
			      unsigned int sample_bits)
{
	u32 cfg0;
	u32 cfg1;
	u32 cfg2;
	u32 cfg3;
	u64 mclk_div;

	cfg0 = ((channels & 0x1f) << 8) |
	       (sample_bits >= 24 ? BIT(11) : 0) |
	       BIT(18);
	cfg1 = ((sample_bits & 0xff) << 24) |
	       ((channels & 0x3) << 5) |
	       (sample_bits >= 24 ? 0x1 : 0x0);
	cfg2 = (trid_spdo_rate_code(rate) & 0xF) << 4;
	cfg3 = ((sample_bits != 16) << 31) |
	       ((sample_bits & 0xF) << 24);

	trid_reg_write(bridge, TRID_AUDIF_SPDO_CFG0, cfg0);
	trid_reg_write(bridge, TRID_AUDIF_SPDO_CFG1, cfg1);
	trid_reg_write(bridge, TRID_AUDIF_SPDO_CFG2, cfg2);
	trid_reg_write(bridge, TRID_AUDIF_SPDO_CFG3, cfg3);

	if (!rate)
		return;

	mclk_div = DIV_ROUND_CLOSEST_ULL((u64)1296000000 << 5,
					 (u64)rate * max_t(unsigned int, channels, 2));
	/*
	 * H2: Stock AudIf_spdo_config@0x5470 preserves the lower byte of the
	 * divider register (sub-divider bits): v30 = (u8)old | (result << 8).
	 */
	{
		u32 old_div = trid_reg_read(bridge, TRID_AUDIF_SPDO_DIV);

		trid_reg_write(bridge, TRID_AUDIF_SPDO_DIV,
			       (old_div & 0xFF) | ((u32)mclk_div << 8));
	}
	trid_reg_write(bridge, TRID_AUDIF_SPDO_DATA, 0);

	/*
	 * IDA: stock AudIf_spdo_Open sets IRQ_ROUTE to the SPDO_DATA register
	 * address so the AudIf IRQ handler knows where to write OWA frames.
	 * Set this here so it is correct before any interrupt fires.
	 */
	trid_reg_write(bridge, TRID_AUDIF_IRQ_ROUTE, TRID_AUDIF_SPDO_DATA);
}

static void trid_audif_irq_enable(struct trid_audio_bridge *bridge,
				  enum trid_interface_type iface,
				  bool enable)
{
	u32 mask = trid_audif_iface_mask(iface);
	u32 cur;

	if (!mask)
		return;

	/*
	 * H8: Stock AudIf_i2so_Open@0x435c clears pending IRQ status via W1C
	 * before enabling the IRQ mask, preventing stale interrupts from firing.
	 */
	if (enable)
		trid_reg_write(bridge, TRID_AUDIF_IRQ_STATUS, mask);

	cur = trid_reg_read(bridge, TRID_AUDIF_IRQ_MASK);
	if (enable)
		cur |= mask;
	else
		cur &= ~mask;
	trid_reg_write(bridge, TRID_AUDIF_IRQ_MASK, cur);
	bridge->audif_irq_mask = cur;
	if (enable && trid_audif_route_value(iface))
		trid_reg_write(bridge, TRID_AUDIF_IRQ_ROUTE,
			       trid_audif_route_value(iface));
}

static phys_addr_t trid_delayline_reg(unsigned int line)
{
	switch (line) {
	case 0:
		return TRID_AUDIF_DLY1_REG;
	case 1:
		return TRID_AUDIF_DLY2_REG;
	case 2:
		return TRID_AUDIF_DLY3_REG;
	case 3:
		return TRID_AUDIF_DLY4_REG;
	default:
		return 0;
	}
}

static void trid_delayline_cfg_bits(unsigned int line, bool open, bool run,
				    u32 *mask, u32 *value)
{
	switch (line) {
	case 0:
		*mask = GENMASK(7, 6);
		*value = (open ? BIT(6) : 0) | (run ? BIT(7) : 0);
		break;
	case 1:
		*mask = GENMASK(5, 4);
		*value = (open ? BIT(4) : 0) | (run ? BIT(5) : 0);
		break;
	case 2:
		*mask = GENMASK(3, 2);
		*value = (open ? BIT(2) : 0) | (run ? BIT(3) : 0);
		break;
	case 3:
		*mask = GENMASK(1, 0);
		*value = (open ? BIT(0) : 0) | (run ? BIT(1) : 0);
		break;
	default:
		*mask = 0;
		*value = 0;
		break;
	}
}

static void trid_delayline_apply_state(struct trid_audio_bridge *bridge,
				       unsigned int line)
{
	u32 mask;
	u32 value;

	trid_delayline_cfg_bits(line, bridge->delayline_open[line],
			       bridge->delayline_running[line],
			       &mask, &value);
	if (!mask)
		return;

	trid_reg_update_bits(bridge, TRID_AUDIF_DLY_CFG, mask, value);
}

static int trid_delayline_open_locked(struct trid_audio_bridge *bridge,
				      unsigned int line)
{
	phys_addr_t reg;

	reg = trid_delayline_reg(line);
	if (!reg)
		return -EINVAL;

	trid_reg_write(bridge, TRID_AUDIF_IRQ_ROUTE, reg);
	trid_reg_write(bridge, TRID_AUDIF_IRQ_STATUS, BIT(7 - line));
	bridge->delayline_open[line] = true;
	bridge->delayline_running[line] = false;
	trid_delayline_apply_state(bridge, line);
	return 0;
}

static int trid_delayline_stop_locked(struct trid_audio_bridge *bridge,
				      unsigned int line)
{
	phys_addr_t reg;

	reg = trid_delayline_reg(line);
	if (!reg)
		return -EINVAL;

	bridge->delayline_running[line] = false;
	bridge->delayline_open[line] = false;
	bridge->delayline_ticks[line] = 0;
	trid_reg_write(bridge, reg, 0);
	trid_delayline_apply_state(bridge, line);
	return 0;
}

/*
 * Step 7: I2SO interrupt handler — equivalent to AudIf_i2so_Interrupt@0x45a8.
 * Advances the frame ring read pointer and writes the next DATA register value.
 * On underrun (ring empty), logs a warning.
 */
static void trid_i2so_irq_channel(struct trid_audio_bridge *bridge,
				  unsigned int ch)
{
	struct trid_i2so_state *s = &bridge->i2so[ch];
	u32 wr, rd, ring_count;

	if (s->state < 1) /* not opened */
		return;

	wr = s->frame_write;
	rd = s->frame_read;
	ring_count = (wr - rd) & 0x1F;

	if (ring_count == 0) {
		/* Underrun — ring empty */
		dev_warn_ratelimited(bridge->dev, "I2SO%u underrun\n", ch);
		return;
	}

	/* If more than 1 frame queued, write next format to DATA reg */
	if (ring_count > 1) {
		u32 next_rd = (rd + 1) & 0x1F;

		s->data_word = s->frames[next_rd].format & 0xFFFF;
		trid_reg_write(bridge, s->data_reg, s->data_word);
	}

	/* Advance read pointer */
	s->frame_read = (rd + 1) & 0x1F;

	/* Clear SPDS overflow/underflow status */
	trid_reg_write(bridge, TRID_AUDIF_SPDS_STATUS, s->spds_w1c);
}

static void trid_handle_i2so_irq(struct trid_audio_bridge *bridge, u32 status)
{
	/* I2SO0 = bit 18 (0x40000) */
	if (status & 0x40000)
		trid_i2so_irq_channel(bridge, 0);
	/* I2SO1 = bit 17 (0x20000) */
	if (status & 0x20000)
		trid_i2so_irq_channel(bridge, 1);
	/* I2SO2 = bit 16 (0x10000) */
	if (status & 0x10000)
		trid_i2so_irq_channel(bridge, 2);

	/* Also notify PCM layer for timer-based streams */
	trid_pcm_notify_irq(bridge, true, status & 0x77000);
}

static void trid_handle_spdo_irq(struct trid_audio_bridge *bridge, u32 status)
{
	trid_pcm_notify_irq(bridge, true, status & 0x8804);
}

/*
 * H3: SPDI interrupt state machine — implements stock AudIf_spdi_Interrupt@0x4ff8.
 *
 * Per-channel status register bits:
 *   (local_status & 3): 0=sync_lost, 1=sync_found, 2=data_ready
 * Error bits in main AudIf status:
 *   0x40 = SPDI1 HW error, 0x20 = SPDI2 HW error
 */
static void trid_spdi_run_channel(struct trid_audio_bridge *bridge,
				  unsigned int ch,
				  enum trid_interface_type iface,
				  u32 main_status, u32 err_bit)
{
	phys_addr_t status_reg = trid_spdi_status_reg(iface);
	phys_addr_t cfg_reg = trid_spdi_cfg_reg(iface);
	phys_addr_t data_reg = trid_spdi_data_reg(iface);
	u32 local_status;
	unsigned int sync_bits;

	/* Handle HW error (overflow) */
	if (main_status & err_bit) {
		u32 spds = trid_reg_read(bridge, TRID_AUDIF_SPDS_STATUS);

		trid_reg_write(bridge, TRID_AUDIF_SPDS_STATUS, spds);
		dev_warn_ratelimited(bridge->dev,
			"SPDI%u HW error (SPDS=0x%08x)\n", ch + 1, spds);
		return;
	}

	local_status = trid_reg_read(bridge, status_reg);
	sync_bits = local_status & 3;

	switch (bridge->spdi_state[ch]) {
	case TRID_SPDI_WAITING_SYNC:
		if (sync_bits == 1) {
			/* Sync found — read preamble data, write CFG to arm */
			(void)trid_reg_read(bridge, data_reg);
			trid_reg_write(bridge, cfg_reg, local_status);
			bridge->spdi_state[ch] = TRID_SPDI_RUNNING;
		}
		break;

	case TRID_SPDI_RUNNING:
		if (sync_bits == 2) {
			/* Data ready — notify PCM layer */
			trid_pcm_notify_irq(bridge, true, main_status);
		} else if (sync_bits == 1) {
			/* Re-sync — re-read preamble, re-write CFG */
			(void)trid_reg_read(bridge, data_reg);
			trid_reg_write(bridge, cfg_reg, local_status);
		} else {
			/* Sync lost — deactivate, back to WAITING_SYNC */
			dev_warn_ratelimited(bridge->dev,
				"SPDI%u sync lost\n", ch + 1);
			trid_reg_write(bridge, cfg_reg, 0);
			bridge->spdi_state[ch] = TRID_SPDI_WAITING_SYNC;
		}
		break;

	default: /* TRID_SPDI_IDLE — shouldn't fire IRQs */
		break;
	}
}

static void trid_handle_spdi_irq(struct trid_audio_bridge *bridge, u32 status)
{
	/* SPDI1 active on bit 0x02, error on bit 0x40 */
	if (status & 0x42)
		trid_spdi_run_channel(bridge, 0, TRID_IFACE_SPDI0,
				      status, 0x40);
	/* SPDI2 active on bit 0x01, error on bit 0x20 */
	if (status & 0x21)
		trid_spdi_run_channel(bridge, 1, TRID_IFACE_SPDI1,
				      status, 0x20);
}

static void trid_handle_spds_irq(struct trid_audio_bridge *bridge, u32 status)
{
	trid_pcm_notify_irq(bridge, true, status & 0x300000);
}

static void trid_handle_dly_irq(struct trid_audio_bridge *bridge, u32 status)
{
	if (status & BIT(10))
		trid_delayline_apply_state(bridge, 0);
	if (status & BIT(9))
		trid_delayline_apply_state(bridge, 1);
	if (status & BIT(8))
		trid_delayline_apply_state(bridge, 2);
	if (status & BIT(7))
		trid_delayline_apply_state(bridge, 3);
}

static void trid_audbrg_irq_ack(struct trid_audio_bridge *bridge, u32 mask)
{
	trid_reg_update_bits(bridge, TRID_AUDBRG_IRQ_STATUS, mask, mask);
}

static void trid_istream_irq_enable(struct trid_audio_bridge *bridge,
				    unsigned int stream, bool enable)
{
	u32 bit;

	if (stream >= TRID_MAX_ISTREAMS)
		return;

	bit = BIT(stream + 10);
	trid_reg_update_bits(bridge, TRID_AUDBRG_IRQ_MASK, bit, enable ? bit : 0);
	trid_audbrg_irq_ack(bridge, bit);
}

static void trid_ostream_irq_enable(struct trid_audio_bridge *bridge,
				    unsigned int stream, bool enable)
{
	u32 bit;

	if (stream >= TRID_MAX_OSTREAMS)
		return;

	bit = BIT(stream + 4);
	trid_reg_update_bits(bridge, TRID_AUDBRG_IRQ_MASK, bit, enable ? bit : 0);
	trid_audbrg_irq_ack(bridge, bit);
}

static void trid_flush_stream(struct trid_audio_bridge *bridge, phys_addr_t reg)
{
	trid_reg_update_bits(bridge, reg, BIT(0), BIT(0));
	trid_reg_update_bits(bridge, reg, BIT(0), 0);
}

static unsigned int trid_sample_width_code(unsigned int sample_bits)
{
	switch (sample_bits) {
	case 32:
		return 1;
	case 24:
		return 1;
	default:
		return 0;
	}
}

int trid_audioio_init(struct trid_audio_bridge *bridge)
{
	u32 v;

	v = trid_reg_read(bridge, TRID_AUDIO_TOP_CLK_CTL);
	trid_reg_write(bridge, TRID_AUDIO_TOP_CLK_CTL, v | 0x700);

	v = trid_reg_read(bridge, TRID_AUDIO_TOP_CLK_CFG);
	v = (v & 0xFF000000) | 0x001A5E00;
	trid_reg_write(bridge, TRID_AUDIO_TOP_CLK_CFG, v);
	trid_reg_write(bridge, TRID_AUDIO_TOP_CLK_CFG, v | 0x01000000);

	/*
	 * Clear stale AudIf events but do NOT pre-enable all IRQ masks.
	 * Stock enables I2SO/SPDI/SPDO masks at open time, not at init.
	 * Pre-enabling them causes IRQ storms when the MIPS DSP has not
	 * yet been configured to service those interfaces.
	 */
	v = trid_audif_known_irq_mask();
	trid_reg_write(bridge, TRID_AUDIF_IRQ_STATUS, v);
	bridge->audif_irq_mask = 0;
	trid_reg_write(bridge, TRID_AUDIF_IRQ_MASK, 0);

	/* pure timer mode: no HW IRQs at init */
	bridge->pm_error = false;
	bridge->arc_source = trid_reg_read(bridge, TRID_ARC_SRC_PHYS) & 0x1;
	/* H7: Stock snd_trid_probe@0x2424 clears BIT(0) after reading ARC_SRC */
	trid_reg_update_bits(bridge, TRID_ARC_SRC_PHYS, BIT(0), 0);

	v = trid_reg_read(bridge, TRID_MSP_OWA_OUT_SRC_PHYS) & 0xF000;
	if (v == 0x2000)
		bridge->msp_owa_out_source = 1;
	else if (v == 0x6000)
		bridge->msp_owa_out_source = 2;
	else
		bridge->msp_owa_out_source = 0;

	/* H3: Initialize SPDI state machines to idle */
	bridge->spdi_state[0] = TRID_SPDI_IDLE;
	bridge->spdi_state[1] = TRID_SPDI_IDLE;

	/* Step 2: Initialize I2SO output channels */
	trid_i2so_init(bridge);

	return 0;
}
EXPORT_SYMBOL_GPL(trid_audioio_init);

void trid_audioio_exit(struct trid_audio_bridge *bridge)
{
	trid_audbrg_irq_enable(bridge, false);
	bridge->audif_irq_mask = 0;
	trid_reg_write(bridge, TRID_AUDIF_IRQ_MASK, 0);
}
EXPORT_SYMBOL_GPL(trid_audioio_exit);

/* ========== I2SO Output Interface (Steps 2-6) ========== */

/*
 * Step 2: Initialize I2SO channel state — equivalent to ABP_DTV_Init@0x63a8
 * + AudIf_GetHandle_abpo1/2/3 @0x4104/0x4150/0x41a0.
 *
 * Called from trid_audioio_init(). Sets register addresses per channel.
 * Stock ABP_DTV_Init also requests the AudIf IRQ — we already do that in probe.
 */
static void trid_i2so_init(struct trid_audio_bridge *bridge)
{
	struct trid_i2so_state *s;

	/* ABPO1 = I2SO0 */
	s = &bridge->i2so[0];
	memset(s, 0, sizeof(*s));
	s->data_reg = TRID_AUDIF_ABPO1_DATA;
	s->clk_reg  = TRID_AUDIF_ABPO1_CLK;
	s->w1c_mask = 0x40000;
	s->irq_route = 0x3;
	s->spds_w1c = 0x3;

	/* ABPO2 = I2SO1 */
	s = &bridge->i2so[1];
	memset(s, 0, sizeof(*s));
	s->data_reg = TRID_AUDIF_ABPO2_DATA;
	s->clk_reg  = TRID_AUDIF_ABPO2_CLK;
	s->w1c_mask = 0x20000;
	s->irq_route = 0xC;
	s->spds_w1c = 0xC;

	/* ABPO3 = I2SO2 */
	s = &bridge->i2so[2];
	memset(s, 0, sizeof(*s));
	s->data_reg = TRID_AUDIF_ABPO3_DATA;
	s->clk_reg  = TRID_AUDIF_ABPO3_CLK;
	s->w1c_mask = 0x10000;
	s->irq_route = 0x30;
	s->spds_w1c = 0x30;

	dev_dbg(bridge->dev, "I2SO channels initialized\n");
}

/*
 * Step 3: Open I2SO channel — equivalent to AudIf_i2so_Open@0x435c.
 * Clears state, sets state=1 (opened), enables IRQ.
 */
static int trid_i2so_open(struct trid_audio_bridge *bridge, unsigned int ch)
{
	struct trid_i2so_state *s;
	u32 cur;

	if (ch >= TRID_MAX_I2SO)
		return -EINVAL;

	s = &bridge->i2so[ch];
	if (s->state != 0) /* already opened */
		return 0;

	/* AudIf_i2so_ClearState@0x4058 */
	s->rate = 0xFFFF;
	s->channels = 0;
	s->data_word = 0;
	s->frame_write = 0;
	s->frame_read = 0;
	s->state = 1; /* opened */

	/* W1C clear stale IRQ status, then enable mask */
	trid_reg_write(bridge, TRID_AUDIF_IRQ_STATUS, s->w1c_mask);
	trid_reg_write(bridge, TRID_AUDIF_SPDS_STATUS, s->spds_w1c);
	cur = trid_reg_read(bridge, TRID_AUDIF_IRQ_MASK);
	trid_reg_write(bridge, TRID_AUDIF_IRQ_MASK, cur | s->w1c_mask);
	bridge->audif_irq_mask |= s->w1c_mask;

	dev_dbg(bridge->dev, "I2SO%u opened\n", ch);
	return 0;
}

/*
 * Step 3b: Close I2SO channel — equivalent to AudIf_i2so_Close@0x43fc.
 */
static void trid_i2so_close(struct trid_audio_bridge *bridge, unsigned int ch)
{
	struct trid_i2so_state *s;
	u32 cur;

	if (ch >= TRID_MAX_I2SO)
		return;

	s = &bridge->i2so[ch];
	s->state = 0;
	s->frame_write = 0;
	s->frame_read = 0;

	/* Disable IRQ mask bit */
	cur = trid_reg_read(bridge, TRID_AUDIF_IRQ_MASK);
	trid_reg_write(bridge, TRID_AUDIF_IRQ_MASK, cur & ~s->w1c_mask);
	bridge->audif_irq_mask &= ~s->w1c_mask;
}

/*
 * Step 4: Set I2SO clock divider — matches stock AudIf_i2so_setFs@0x4294.
 * Stock formula (fixed-point, 8-bit fraction):
 *   divisor = rate  (for normal mode, channels < 256)
 *   integer = 324000000 / divisor
 *   remainder = 324000000 % divisor
 *   frac = ((remainder << 9) / divisor + 1) >> 1
 *   result = (integer << 8) + frac
 *   REG_Write(clk_reg, result << 8)
 */
static void trid_i2so_set_fs(struct trid_audio_bridge *bridge,
			     unsigned int ch, unsigned int rate,
			     unsigned int channels)
{
	struct trid_i2so_state *s = &bridge->i2so[ch];
	u32 divisor, integer_part, remainder, frac_part, result;

	if (!rate)
		return;

	divisor = rate;
	integer_part = 324000000u / divisor;
	remainder = 324000000u % divisor;
	frac_part = (((remainder << 9) / divisor) + 1) >> 1;
	result = (integer_part << 8) + frac_part;

	trid_reg_write(bridge, s->clk_reg, result << 8);
}

/*
 * Step 5: Declare a new frame — equivalent to AudIf_i2so_NewFrameAvail@0x4a90.
 * Adds a frame to the ring buffer. If it's the first frame (ring was empty),
 * writes the initial DATA register value.
 */
static int trid_i2so_new_frame(struct trid_audio_bridge *bridge,
			       unsigned int ch, u32 rate, u32 channels)
{
	struct trid_i2so_state *s;
	u32 wr, rd;
	bool was_empty;

	if (ch >= TRID_MAX_I2SO)
		return -EINVAL;

	s = &bridge->i2so[ch];
	wr = s->frame_write;
	rd = s->frame_read;

	/* Ring full? */
	if (((wr - rd) & 0x1F) == 0x1F)
		return -ENOSPC;

	was_empty = (((wr - rd) & 0x1F) == 0);

	/* Store frame */
	s->frames[wr & 0x1F].rate = rate;
	s->frames[wr & 0x1F].format = channels; /* simplified: store channels */
	s->frame_write = (wr + 1) & 0x1F;

	/* If first frame: write initial DATA reg */
	if (was_empty) {
		s->data_word = s->frames[rd & 0x1F].format & 0xFFFF;
		trid_reg_write(bridge, s->data_reg, s->data_word);
	}

	return 0;
}

/*
 * Step 6: Activate I2SO — equivalent to AudIf_i2so_activate@0x48d8.
 * Sets state=3 (activated), writes CLK + DATA, sets IRQ route.
 */
static void trid_i2so_activate(struct trid_audio_bridge *bridge,
			       unsigned int ch)
{
	struct trid_i2so_state *s = &bridge->i2so[ch];

	s->state = 3; /* activated */

	/* Write DATA register (format/channels word) */
	trid_reg_write(bridge, s->data_reg, s->data_word);

	/* Set CLK divider */
	trid_i2so_set_fs(bridge, ch, s->rate, s->channels);

	/* Set IRQ route for this channel */
	trid_reg_write(bridge, TRID_AUDIF_IRQ_ROUTE, s->irq_route);
}

/*
 * Step 6: Run I2SO — equivalent to Trid_Audio_Start_I2SO_Interface@0x719c
 * + AudIf_i2so_Run@0x4a08.
 * Sets info, stores config, triggers activate.
 */
static int trid_i2so_start(struct trid_audio_bridge *bridge, unsigned int ch,
			   unsigned int rate, unsigned int channels,
			   unsigned int sample_bits)
{
	struct trid_i2so_state *s;
	int ret;

	if (ch >= TRID_MAX_I2SO)
		return -EINVAL;

	s = &bridge->i2so[ch];

	/* Open if not already */
	ret = trid_i2so_open(bridge, ch);
	if (ret)
		return ret;

	/* Store config */
	s->rate = rate;
	s->channels = channels;
	s->sample_bits = sample_bits;

	/* Declare first frame */
	ret = trid_i2so_new_frame(bridge, ch, rate, channels);
	if (ret && ret != -ENOSPC)
		return ret;

	/* Activate: write CLK + DATA, start output */
	trid_i2so_activate(bridge, ch);

	dev_dbg(bridge->dev, "I2SO%u started: %uHz %uch %ubit\n",
		ch, rate, channels, sample_bits);
	return 0;
}

static void trid_i2so_stop(struct trid_audio_bridge *bridge, unsigned int ch)
{
	if (ch >= TRID_MAX_I2SO)
		return;

	trid_i2so_close(bridge, ch);
	dev_dbg(bridge->dev, "I2SO%u stopped\n", ch);
}

int trid_istream_config(struct trid_audio_bridge *bridge, unsigned int stream,
		       unsigned int rate, unsigned int channels,
		       unsigned int sample_bits, size_t period_bytes,
		       bool irq_enable)
{
	phys_addr_t base;
	dma_addr_t dma;
	size_t size;
	u32 step;
	u32 cfg;

	if (stream >= TRID_MAX_ISTREAMS)
		return -EINVAL;

	dma = bridge->istream[stream].dma;
	size = bridge->istream[stream].size;
	base = TRID_AUDBRG_ISTREAM_BASE(stream);
	step = ALIGN(period_bytes, 16);
	if (!step || step > size)
		step = size;

	/*
	 * H5: Stock audbrg_istream_config@0x32e8 CFG register layout:
	 *   v19 = (format_code << 12) | (end_addr >> 4) | (wflag << 11) |
	 *         (bytes_per_sample << 8) | (channels << 14)
	 * Verified via caller Thal_Alsa_Audio_Play_Start@0x8408:
	 *   a2=channels, a3=bytes_per_sample, a4=format_code, a5=width_flag
	 * Stock format_code: 2 for 16-bit, 1 for 32/24-bit.
	 * Lower 8 bits (v17 >> 4) = (buffer_end_phys >> 4) & 0xFF.
	 */
	{
		unsigned int bps = sample_bits / 8;
		unsigned int wflag = (sample_bits > 16) ? 1 : 0;
		unsigned int fcode = (sample_bits <= 16) ? 2 : 1;
		u32 end_field = (lower_32_bits(dma + size - 1) >> 4) & 0xFF;

		cfg = end_field |
		      ((bps & 0x7) << 8) |
		      (wflag << 11) |
		      ((fcode & 0x3) << 12) |
		      ((channels & 0x7) << 14);
	}

	trid_reg_update_bits(bridge, TRID_HIGH_ADDR_CTL_PHYS,
			     GENMASK(3, 0), upper_32_bits(dma));
	trid_reg_write(bridge, base + TRID_STREAM_REG_START,
		       (lower_32_bits(dma) >> 4) & 0x00FFFFFF);
	trid_reg_write(bridge, base + TRID_STREAM_REG_END,
		       (lower_32_bits(dma + size - 1) >> 4) & 0x00FFFFFF);
	trid_reg_write(bridge, base + TRID_STREAM_REG_STEP,
		       (u32)(step >> 4));
	trid_reg_write(bridge, base + TRID_STREAM_REG_CFG, cfg);
	trid_reg_write(bridge, TRID_AUDBRG_STREAM_SYNC, 0);
	trid_istream_irq_enable(bridge, stream, irq_enable);

	return 0;
}
EXPORT_SYMBOL_GPL(trid_istream_config);

static int trid_i2so_config(struct trid_audio_bridge *bridge,
			    enum trid_interface_type iface,
			    unsigned int rate, unsigned int channels,
			    unsigned int sample_bits, size_t period_bytes,
			    bool irq_enable)
{
	unsigned int stream;

	switch (iface) {
	case TRID_IFACE_I2SO0:
		stream = 0;
		break;
	case TRID_IFACE_I2SO1:
		stream = 1;
		break;
	case TRID_IFACE_I2SO2:
		stream = 2;
		break;
	default:
		return -EINVAL;
	}

	if (trid_i2so_data_reg(iface))
		trid_reg_write(bridge, trid_i2so_data_reg(iface), 0);
	trid_i2so_program_fs(bridge, iface, rate, channels, sample_bits);
	trid_audif_irq_enable(bridge, iface, irq_enable);
	return trid_istream_config(bridge, stream, rate, channels, sample_bits,
				 period_bytes, irq_enable);
}

static int trid_spdi_config(struct trid_audio_bridge *bridge,
			    enum trid_interface_type iface,
			    unsigned int rate, unsigned int channels,
			    unsigned int sample_bits, size_t period_bytes,
			    bool irq_enable)
{
	unsigned int stream;

	switch (iface) {
	case TRID_IFACE_SPDI0:
		stream = 0;
		break;
	case TRID_IFACE_SPDI1:
		stream = 1;
		break;
	default:
		return -EINVAL;
	}

	/*
	 * IDA: stock AudIf_spdi_activate writes CFG then STATUS registers.
	 * M7: The old port wrote DATA instead of STATUS — fixed to match stock.
	 * There is no separate SPDI2_RATE register; that offset is SPDI2_STATUS.
	 */
	trid_reg_write(bridge, trid_spdi_cfg_reg(iface), 0);
	trid_reg_write(bridge,
		       iface == TRID_IFACE_SPDI1 ? TRID_AUDIF_SPDI2_STATUS
						  : TRID_AUDIF_SPDI1_STATUS,
		       rate);
	/* H3: Arm the SPDI state machine for this channel */
	bridge->spdi_state[stream] = TRID_SPDI_WAITING_SYNC;
	trid_audif_irq_enable(bridge, iface, irq_enable);
	return trid_ostream_config(bridge, stream, rate, channels, sample_bits,
				 period_bytes, irq_enable);
}

int trid_ostream_config(struct trid_audio_bridge *bridge, unsigned int stream,
		       unsigned int rate, unsigned int channels,
		       unsigned int sample_bits, size_t period_bytes,
		       bool irq_enable)
{
	phys_addr_t base;
	dma_addr_t dma;
	size_t size;
	u32 step;
	u32 cfg;

	if (stream >= TRID_MAX_OSTREAMS)
		return -EINVAL;

	dma = bridge->ostream[stream].dma;
	size = bridge->ostream[stream].size;
	base = TRID_AUDBRG_OSTREAM_BASE(stream);
	step = ALIGN(period_bytes, 16);
	if (!step || step > size)
		step = min_t(size_t, size, 3072);

	cfg = ((channels & 0x1f) << 8) |
	      (trid_sample_width_code(sample_bits) << 11);

	trid_reg_update_bits(bridge, TRID_HIGH_ADDR_CTL_PHYS,
			     GENMASK(7, 4), upper_32_bits(dma) << 4);
	trid_reg_write(bridge, base + TRID_STREAM_REG_START,
		       (lower_32_bits(dma) >> 4) & 0x00FFFFFF);
	trid_reg_write(bridge, base + TRID_STREAM_REG_END,
		       (lower_32_bits(dma + size - 1) >> 4) & 0x00FFFFFF);
	trid_reg_write(bridge, base + TRID_STREAM_REG_STEP,
		       (u32)(step >> 4));
	trid_reg_write(bridge, base + TRID_STREAM_REG_CFG, cfg);
	trid_reg_write(bridge, TRID_AUDBRG_STREAM_SYNC, 0);
	trid_ostream_irq_enable(bridge, stream, irq_enable);

	return 0;
}
EXPORT_SYMBOL_GPL(trid_ostream_config);

int trid_delayline_set(struct trid_audio_bridge *bridge, unsigned int line,
		      unsigned int delay_ticks)
{
	phys_addr_t reg;
	u32 mask;
	u32 value;
	u32 ticks;

	if (line >= TRID_MAX_DELAYLINES)
		return -EINVAL;

	if (!delay_ticks)
		return trid_delayline_stop_locked(bridge, line);

	if (!bridge->delayline_open[line]) {
		if (trid_delayline_open_locked(bridge, line))
			return -EINVAL;
	}

	reg = trid_delayline_reg(line);
	if (!reg)
		return -EINVAL;

	/* Stock writes the runtime value masked to 17 bits before enabling the
	 * line. Keep the same externally visible limit.
	 * H4: Callers now pass hardware ticks (48768 * ms + 500) / 1000.
	 */
	ticks = delay_ticks & 0x1FFFF;
	trid_reg_write(bridge, reg, ticks);
	trid_reg_write(bridge, TRID_AUDIF_IRQ_ROUTE, reg);

	bridge->delayline_ticks[line] = ticks;
	bridge->delayline_open[line] = true;
	bridge->delayline_running[line] = true;
	trid_delayline_cfg_bits(line, true, true, &mask, &value);
	trid_reg_update_bits(bridge, TRID_AUDIF_DLY_CFG, mask, value);
	/* NOTE: delayline_ms is set by the kcontrol _put caller, not here */
	return 0;
}
EXPORT_SYMBOL_GPL(trid_delayline_set);

int trid_istream_start(struct trid_audio_bridge *bridge, unsigned int stream)
{
	if (stream >= TRID_MAX_ISTREAMS)
		return -EINVAL;

	/*
	 * Do NOT enable AudIF I2SO IRQs here.  On stock the speaker path
	 * does NOT use I2SO (stock I2SO registers are all zero).  The MIPS
	 * DSP reads directly from the ISTREAM shared buffer and writes to
	 * the internal DAC.  Enabling I2SO IRQs without a fully configured
	 * I2SO output causes an IRQ storm that leads to an RCU stall.
	 *
	 * Only the bridge-side ISTREAM IRQ is needed for DMA flow control.
	 */
	/* pure timer mode: no HW IRQs */
	trid_flush_stream(bridge, TRID_AUDBRG_ISTREAM_FLUSH(stream));
	trid_reg_write(bridge, TRID_AUDBRG_ISTREAM_UMACREQ(stream), 1);
	trid_reg_write(bridge, TRID_AUDBRG_ISTREAM_UMACREQ(stream), 0);

	return 0;
}
EXPORT_SYMBOL_GPL(trid_istream_start);

int trid_istream_stop(struct trid_audio_bridge *bridge, unsigned int stream)
{
	if (stream >= TRID_MAX_ISTREAMS)
		return -EINVAL;

	trid_istream_irq_enable(bridge, stream, false);
	trid_reg_write(bridge, TRID_AUDBRG_ISTREAM_UMACREQ(stream), 0);
	trid_flush_stream(bridge, TRID_AUDBRG_ISTREAM_FLUSH(stream));
	return 0;
}
EXPORT_SYMBOL_GPL(trid_istream_stop);

int trid_ostream_start(struct trid_audio_bridge *bridge, unsigned int stream)
{
	if (stream >= TRID_MAX_OSTREAMS)
		return -EINVAL;

	/* H6: Stock audbrg_ostream_start@0x3cf8 zeroes the output buffer */
	if (bridge->ostream[stream].cpu)
		memset(bridge->ostream[stream].cpu, 0,
		       bridge->ostream[stream].size);

	trid_audif_irq_enable(bridge, TRID_IFACE_SPDI0 + stream, true);
	trid_flush_stream(bridge, TRID_AUDBRG_OSTREAM_FLUSH(stream));
	trid_audbrg_irq_enable(bridge, true);
	return 0;
}
EXPORT_SYMBOL_GPL(trid_ostream_start);

int trid_ostream_stop(struct trid_audio_bridge *bridge, unsigned int stream)
{
	if (stream >= TRID_MAX_OSTREAMS)
		return -EINVAL;

	trid_audif_irq_enable(bridge, TRID_IFACE_SPDI0 + stream, false);
	trid_flush_stream(bridge, TRID_AUDBRG_OSTREAM_FLUSH(stream));
	return 0;
}
EXPORT_SYMBOL_GPL(trid_ostream_stop);

int trid_iface_prepare(struct trid_audio_bridge *bridge,
		      enum trid_interface_type iface,
		      unsigned int rate, unsigned int channels,
		      unsigned int sample_bits, size_t period_bytes,
		      bool irq_enable)
{
	switch (iface) {
	case TRID_IFACE_I2SO0:
	case TRID_IFACE_I2SO1:
	case TRID_IFACE_I2SO2:
		return trid_i2so_config(bridge, iface, rate, channels,
				       sample_bits, period_bytes, irq_enable);
	case TRID_IFACE_SPDO0:
		trid_audif_irq_enable(bridge, iface, irq_enable);
		if (trid_ostream_config(bridge, 1, rate, channels,
				       sample_bits, period_bytes, irq_enable))
			return -EINVAL;
		trid_spdo_program(bridge, rate, channels, sample_bits);
		return 0;
	case TRID_IFACE_SPDI0:
	case TRID_IFACE_SPDI1:
		return trid_spdi_config(bridge, iface, rate, channels,
				       sample_bits, period_bytes, irq_enable);
	default:
		return -EINVAL;
	}
}
EXPORT_SYMBOL_GPL(trid_iface_prepare);

irqreturn_t trid_audbrg_irq_thread(int irq, void *data)
{
	struct trid_audio_bridge *bridge = data;
	u32 status;
	u32 handled;

	status = trid_reg_read(bridge, TRID_AUDBRG_IRQ_STATUS);
	handled = status & 0x3FFF;
	if (!handled)
		return IRQ_NONE;

	trid_audbrg_irq_ack(bridge, handled);
	trid_pcm_notify_irq(bridge, false, status);
	return IRQ_HANDLED;
}
EXPORT_SYMBOL_GPL(trid_audbrg_irq_thread);

irqreturn_t trid_audif_irq_thread(int irq, void *data)
{
	struct trid_audio_bridge *bridge = data;
	u32 status;

	status = trid_reg_read(bridge, TRID_AUDIF_IRQ_STATUS);
	if (!status)
		return IRQ_NONE;

	/* Always W1C-clear all pending bits to deassert the IRQ line,
	 * even for sources not in our software mask.  Without this,
	 * unmasked HW sources keep the line asserted -> "nobody cared". */
	trid_reg_write(bridge, TRID_AUDIF_IRQ_STATUS, status);
	status &= bridge->audif_irq_mask;
	if (!status)
		return IRQ_HANDLED;
	if ((status & 0x300000) != 0 &&
	    (trid_reg_read(bridge, TRID_AUDIF_IRQ_MASK) & 0x300000) == 0x300000)
		trid_handle_spds_irq(bridge, status);
	if (status & 0x77000)
		trid_handle_i2so_irq(bridge, status);
	if (status & 0x780)
		trid_handle_dly_irq(bridge, status);
	if (status & 0x8804)
		trid_handle_spdo_irq(bridge, status);
	if (status & 0x10007B)
		trid_handle_spdi_irq(bridge, status);
	return IRQ_HANDLED;
}
EXPORT_SYMBOL_GPL(trid_audif_irq_thread);
