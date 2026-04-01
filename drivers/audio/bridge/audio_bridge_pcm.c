// SPDX-License-Identifier: GPL-2.0-only

#include <linux/jiffies.h>
#include <linux/module.h>
#include <linux/string.h>

#include "audio_bridge.h"

static const struct snd_pcm_hardware trid_playback_hw = {
	/*
	 * Stock trid_pcm_playback_open@0x1608: v3[56]=262403 = 0x40203
	 * Stock value lacks INTERLEAVED because stock userspace used MMAP only.
	 * We add INTERLEAVED for standard ALSA userspace (aplay, PulseAudio).
	 */
	.info = SNDRV_PCM_INFO_MMAP |
		SNDRV_PCM_INFO_MMAP_VALID |
		SNDRV_PCM_INFO_INTERLEAVED |
		SNDRV_PCM_INFO_BLOCK_TRANSFER |
		SNDRV_PCM_INFO_SYNC_APPLPTR,
	.formats = SNDRV_PCM_FMTBIT_S16_LE |
		   SNDRV_PCM_FMTBIT_S24_LE |
		   SNDRV_PCM_FMTBIT_S32_LE,
	.rates = SNDRV_PCM_RATE_8000 |
		 SNDRV_PCM_RATE_11025 |
		 SNDRV_PCM_RATE_16000 |
		 SNDRV_PCM_RATE_22050 |
		 SNDRV_PCM_RATE_32000 |
		 SNDRV_PCM_RATE_44100 |
		 SNDRV_PCM_RATE_48000 |
		 SNDRV_PCM_RATE_96000 |
		 SNDRV_PCM_RATE_192000,
	.rate_min = 8000,
	.rate_max = 192000,
	.channels_min = 1,
	.channels_max = 2,
	.buffer_bytes_max = 0x20000,
	.period_bytes_min = 256,
	.period_bytes_max = 0x4000,
	.periods_min = 1,
	.periods_max = 8,
	.fifo_size = 128,
};

static const struct snd_pcm_hardware trid_capture_hw = {
	/* Same as playback — add INTERLEAVED for standard ALSA userspace */
	.info = SNDRV_PCM_INFO_MMAP |
		SNDRV_PCM_INFO_MMAP_VALID |
		SNDRV_PCM_INFO_INTERLEAVED |
		SNDRV_PCM_INFO_BLOCK_TRANSFER |
		SNDRV_PCM_INFO_SYNC_APPLPTR,
	.formats = SNDRV_PCM_FMTBIT_S16_LE |
		   SNDRV_PCM_FMTBIT_S24_LE |
		   SNDRV_PCM_FMTBIT_S32_LE,
	.rates = SNDRV_PCM_RATE_48000,
	.rate_min = 48000,
	.rate_max = 48000,
	.channels_min = 2,
	.channels_max = 2,
	.buffer_bytes_max = 0x20000,
	.period_bytes_min = 256,
	.period_bytes_max = 0x4000,
	.periods_min = 1,
	.periods_max = 8,
	.fifo_size = 128,
};

static const char * const trid_arc_source_texts[] = {
	"APB",
	"MSP",
};

static const char * const trid_msp_owa_out_texts[] = {
	"NULL",
	"APB",
	"MSP",
};

static void trid_copy_ring(void *dst, size_t dst_size, size_t dst_off,
			   const void *src, size_t src_size, size_t src_off,
			   size_t bytes)
{
	const u8 *src8 = src;
	u8 *dst8 = dst;

	while (bytes) {
		size_t dst_chunk = min(bytes, dst_size - dst_off);
		size_t src_chunk = min(bytes, src_size - src_off);
		size_t chunk = min(dst_chunk, src_chunk);

		memcpy(dst8 + dst_off, src8 + src_off, chunk);
		bytes -= chunk;
		dst_off = (dst_off + chunk) % dst_size;
		src_off = (src_off + chunk) % src_size;
	}
}

static struct trid_stream_state *trid_get_stream(struct trid_audio_bridge *bridge,
						 struct snd_pcm_substream *substream)
{
	unsigned int devno = substream->pcm->device;

	if (substream->stream == SNDRV_PCM_STREAM_PLAYBACK)
		return &bridge->playback[devno];

	if (devno >= TRID_MAX_OSTREAMS)
		return NULL;

	return &bridge->capture[devno];
}

static enum trid_interface_type trid_playback_iface(unsigned int devno)
{
	switch (devno) {
	case 0:
		return TRID_IFACE_I2SO0;
	case 1:
		return TRID_IFACE_I2SO1;
	case 2:
		return TRID_IFACE_I2SO2;
	default:
		return TRID_IFACE_SPDO0;
	}
}

static enum trid_interface_type trid_capture_iface(unsigned int devno)
{
	return devno ? TRID_IFACE_SPDI1 : TRID_IFACE_SPDI0;
}

static unsigned long trid_period_jiffies(struct trid_stream_state *stream)
{
	unsigned int frame_bytes;
	unsigned long ms;

	frame_bytes = max_t(unsigned int, 1,
			     (stream->sample_bits / 8) * stream->channels);
	ms = DIV_ROUND_UP(stream->period_bytes * 1000,
			  max_t(unsigned int, 1, frame_bytes * stream->rate));

	return max_t(unsigned long, 1, msecs_to_jiffies(max_t(unsigned long, 1, ms)));
}

static void trid_stream_transfer(struct trid_audio_bridge *bridge,
				 struct trid_stream_state *stream)
{
	struct snd_pcm_substream *substream = stream->substream;
	struct snd_pcm_runtime *runtime;
	struct trid_dma_segment *segment;
	size_t segment_bytes;

	if (!substream)
		return;

	runtime = substream->runtime;
	if (!runtime || !runtime->dma_area)
		return;

	if (stream->capture) {
		segment = &bridge->ostream[stream->hw_stream];
		segment_bytes = segment->size;
		trid_copy_ring(runtime->dma_area, stream->buffer_bytes,
			       stream->hw_ptr_bytes,
			       segment->cpu, segment->size,
			       stream->bridge_offset,
			       stream->period_bytes);
	} else {
		segment = &bridge->istream[stream->hw_stream];
		segment_bytes = segment->size;
		trid_copy_ring(segment->cpu, segment->size,
			       stream->bridge_offset,
			       runtime->dma_area, stream->buffer_bytes,
			       stream->hw_ptr_bytes,
			       stream->period_bytes);
	}

	stream->hw_ptr_bytes = (stream->hw_ptr_bytes + stream->period_bytes) %
				       stream->buffer_bytes;
	stream->bridge_offset = (stream->bridge_offset + stream->period_bytes) %
				segment_bytes;
}

static void trid_stream_timer(struct timer_list *t)
{
	struct trid_stream_state *stream;
	struct trid_audio_bridge *bridge;
	struct snd_pcm_substream *substream;
	unsigned long flags;

	stream = timer_container_of(stream, t, timer);

	spin_lock_irqsave(&stream->lock, flags);
	if (!stream->running || !stream->substream) {
		spin_unlock_irqrestore(&stream->lock, flags);
		return;
	}

	substream = stream->substream;
	bridge = snd_pcm_substream_chip(substream);
	trid_stream_transfer(bridge, stream);
	spin_unlock_irqrestore(&stream->lock, flags);

	snd_pcm_period_elapsed(substream);

	/*
	 * Re-arm only if still running. snd_pcm_period_elapsed() may have
	 * triggered an xrun which sets running=false via the trigger callback.
	 * Without this check the timer loops forever → RCU stall.
	 */
	if (READ_ONCE(stream->running))
		mod_timer(&stream->timer,
			  jiffies + trid_period_jiffies(stream));
}

static int trid_pcm_open(struct snd_pcm_substream *substream)
{
	struct trid_audio_bridge *bridge = snd_pcm_substream_chip(substream);
	struct trid_stream_state *stream = trid_get_stream(bridge, substream);
	struct snd_pcm_runtime *runtime = substream->runtime;

	if (!stream)
		return -ENODEV;

	runtime->hw = substream->stream == SNDRV_PCM_STREAM_PLAYBACK ?
		trid_playback_hw : trid_capture_hw;
	snd_pcm_hw_constraint_integer(runtime, SNDRV_PCM_HW_PARAM_PERIODS);

	stream->substream = substream;
	stream->running = false;
	stream->capture = substream->stream == SNDRV_PCM_STREAM_CAPTURE;
	stream->pcm_dev = substream->pcm->device;
	stream->iface = stream->capture ? trid_capture_iface(stream->pcm_dev)
					 : trid_playback_iface(stream->pcm_dev);
	stream->hw_stream = stream->capture ? stream->pcm_dev % TRID_MAX_OSTREAMS
					     : stream->pcm_dev % TRID_MAX_ISTREAMS;
	stream->hw_ptr_bytes = 0;
	stream->bridge_offset = 0;
	spin_lock_init(&stream->lock);
	timer_setup(&stream->timer, trid_stream_timer, 0);

	return 0;
}

static int trid_pcm_close(struct snd_pcm_substream *substream)
{
	struct trid_audio_bridge *bridge = snd_pcm_substream_chip(substream);
	struct trid_stream_state *stream = trid_get_stream(bridge, substream);

	if (!stream)
		return 0;

	timer_delete_sync(&stream->timer);
	stream->running = false;
	stream->substream = NULL;
	return 0;
}

static int trid_pcm_hw_params(struct snd_pcm_substream *substream,
			      struct snd_pcm_hw_params *params)
{
	return snd_pcm_lib_malloc_pages(substream, params_buffer_bytes(params));
}

static int trid_pcm_hw_free(struct snd_pcm_substream *substream)
{
	return snd_pcm_lib_free_pages(substream);
}

static int trid_pcm_prepare(struct snd_pcm_substream *substream)
{
	struct trid_audio_bridge *bridge = snd_pcm_substream_chip(substream);
	struct trid_stream_state *stream = trid_get_stream(bridge, substream);
	struct snd_pcm_runtime *runtime = substream->runtime;
	unsigned int sample_bits;
	int ret;

	if (!stream)
		return -ENODEV;

	sample_bits = snd_pcm_format_physical_width(runtime->format);
	stream->channels = runtime->channels;
	stream->rate = runtime->rate;
	stream->sample_bits = sample_bits;
	stream->period_bytes = frames_to_bytes(runtime, runtime->period_size);
	stream->buffer_bytes = frames_to_bytes(runtime, runtime->buffer_size);
	stream->hw_ptr_bytes = 0;
	stream->bridge_offset = 0;

	ret = trid_iface_prepare(bridge, stream->iface, runtime->rate,
				 runtime->channels, sample_bits,
				 stream->period_bytes, true);

	return ret;
}

static int trid_pcm_trigger(struct snd_pcm_substream *substream, int cmd)
{
	struct trid_audio_bridge *bridge = snd_pcm_substream_chip(substream);
	struct trid_stream_state *stream = trid_get_stream(bridge, substream);
	unsigned long flags;
	int ret = 0;

	if (!stream)
		return -ENODEV;

	spin_lock_irqsave(&stream->lock, flags);
	switch (cmd) {
	case SNDRV_PCM_TRIGGER_START:
	case SNDRV_PCM_TRIGGER_RESUME:
	case SNDRV_PCM_TRIGGER_PAUSE_RELEASE:
		stream->running = true;
		break;
	case SNDRV_PCM_TRIGGER_STOP:
	case SNDRV_PCM_TRIGGER_SUSPEND:
	case SNDRV_PCM_TRIGGER_PAUSE_PUSH:
		stream->running = false;
		break;
	default:
		ret = -EINVAL;
		break;
	}
	spin_unlock_irqrestore(&stream->lock, flags);

	if (ret)
		return ret;

	switch (cmd) {
	case SNDRV_PCM_TRIGGER_START:
	case SNDRV_PCM_TRIGGER_RESUME:
	case SNDRV_PCM_TRIGGER_PAUSE_RELEASE:
		if (!stream->capture)
			trid_stream_transfer(bridge, stream);
		if (stream->capture)
			ret = trid_ostream_start(bridge, stream->hw_stream);
		else
			ret = trid_istream_start(bridge, stream->hw_stream);
		if (!ret)
			mod_timer(&stream->timer,
				  jiffies + trid_period_jiffies(stream));
		break;
	case SNDRV_PCM_TRIGGER_STOP:
	case SNDRV_PCM_TRIGGER_SUSPEND:
	case SNDRV_PCM_TRIGGER_PAUSE_PUSH:
			timer_delete(&stream->timer); /* NOT _sync: may be called from timer via xrun */
		if (stream->capture)
			ret = trid_ostream_stop(bridge, stream->hw_stream);
		else
			ret = trid_istream_stop(bridge, stream->hw_stream);
		break;
	}

	return ret;
}

/*
 * Read the real HW pointer from the bridge hardware.
 * Kept for future use (xrun detection, sync verification).
 *
 * Stock audbrg_istream_putdata2HW@0x38e0 (playback / istream):
 *   high = REG_Read(HIGH_ADDR_CTL) & 0xF
 *   ptr  = REG_Read(ISTREAM_PTR(stream)) & 0xFFFFFF
 *   phys = (high << 28) | (ptr << 4)
 *
 * Stock audbrg_ostream_putdata2SW@0x3f5c (capture / ostream):
 *   high = REG_Read(HIGH_ADDR_CTL) & 0xF0
 *   ptr  = REG_Read(OSTREAM_PTR(stream)) & 0xFFFFFF
 *   phys = (high << 24) | (ptr << 4)
 */

/*
 * ALSA pointer callback — reports the current buffer position.
 *
 * We use the timer-tracked hw_ptr_bytes (updated by trid_stream_transfer)
 * rather than the real HW pointer. Reason: the bridge hardware reads from
 * the shared buffer asynchronously. The HW PTR register reflects the bridge's
 * consumption position, which lags behind our write position. Using it
 * directly causes false xruns because ALSA sees "no progress" right after
 * a period transfer.
 */
static snd_pcm_uframes_t trid_pcm_pointer(struct snd_pcm_substream *substream)
{
	struct trid_audio_bridge *bridge = snd_pcm_substream_chip(substream);
	struct trid_stream_state *stream = trid_get_stream(bridge, substream);

	if (!stream)
		return 0;

	return bytes_to_frames(substream->runtime, stream->hw_ptr_bytes);
}

static const struct snd_pcm_ops trid_playback_ops = {
	.open = trid_pcm_open,
	.close = trid_pcm_close,
	.ioctl = snd_pcm_lib_ioctl,
	.hw_params = trid_pcm_hw_params,
	.hw_free = trid_pcm_hw_free,
	.prepare = trid_pcm_prepare,
	.trigger = trid_pcm_trigger,
	.pointer = trid_pcm_pointer,
};

static const struct snd_pcm_ops trid_capture_ops = {
	.open = trid_pcm_open,
	.close = trid_pcm_close,
	.ioctl = snd_pcm_lib_ioctl,
	.hw_params = trid_pcm_hw_params,
	.hw_free = trid_pcm_hw_free,
	.prepare = trid_pcm_prepare,
	.trigger = trid_pcm_trigger,
	.pointer = trid_pcm_pointer,
};

static int trid_delayline_info(struct snd_kcontrol *kcontrol,
			      struct snd_ctl_elem_info *uinfo)
{
	uinfo->type = SNDRV_CTL_ELEM_TYPE_INTEGER;
	uinfo->count = 1;
	uinfo->value.integer.min = 0;
	uinfo->value.integer.max = 500;
	return 0;
}

static int trid_delayline_get(struct snd_kcontrol *kcontrol,
			     struct snd_ctl_elem_value *ucontrol)
{
	struct trid_audio_bridge *bridge = snd_kcontrol_chip(kcontrol);
	unsigned int idx = kcontrol->private_value;

	ucontrol->value.integer.value[0] = bridge->delayline_ms[idx];
	return 0;
}

static int trid_delayline_put(struct snd_kcontrol *kcontrol,
			     struct snd_ctl_elem_value *ucontrol)
{
	struct trid_audio_bridge *bridge = snd_kcontrol_chip(kcontrol);
	unsigned int idx = kcontrol->private_value;
	unsigned int val = ucontrol->value.integer.value[0];
	unsigned int ticks;

	val = clamp_val(val, 0, 500);
	if (bridge->delayline_ms[idx] == val)
		return 0;

	/*
	 * H4: Stock trid_delayline1_put@0x1cd8 converts ms to HW ticks:
	 *   Trid_Audio_Output_DelayLine_Set(0, (48768 * value + 500) / 1000);
	 */
	ticks = (48768u * val + 500) / 1000;
	trid_delayline_set(bridge, idx, ticks);
	bridge->delayline_ms[idx] = val;
	return 1;
}

static int trid_arc_source_info(struct snd_kcontrol *kcontrol,
			       struct snd_ctl_elem_info *uinfo)
{
	return snd_ctl_enum_info(uinfo, 1,
				 ARRAY_SIZE(trid_arc_source_texts),
				 trid_arc_source_texts);
}

static int trid_arc_source_get(struct snd_kcontrol *kcontrol,
			      struct snd_ctl_elem_value *ucontrol)
{
	struct trid_audio_bridge *bridge = snd_kcontrol_chip(kcontrol);

	bridge->arc_source = trid_reg_read(bridge, TRID_ARC_SRC_PHYS) & 0x1;
	ucontrol->value.enumerated.item[0] = bridge->arc_source;
	return 0;
}

static int trid_arc_source_put(struct snd_kcontrol *kcontrol,
			      struct snd_ctl_elem_value *ucontrol)
{
	struct trid_audio_bridge *bridge = snd_kcontrol_chip(kcontrol);
	unsigned int val = !!ucontrol->value.enumerated.item[0];

	if (bridge->arc_source == val)
		return 0;

	bridge->arc_source = val;
	trid_reg_update_bits(bridge, TRID_ARC_SRC_PHYS, BIT(0), val ? BIT(0) : 0);
	return 1;
}

static int trid_msp_owa_out_info(struct snd_kcontrol *kcontrol,
				 struct snd_ctl_elem_info *uinfo)
{
	return snd_ctl_enum_info(uinfo, 1,
				 ARRAY_SIZE(trid_msp_owa_out_texts),
				 trid_msp_owa_out_texts);
}

static int trid_msp_owa_out_get(struct snd_kcontrol *kcontrol,
				struct snd_ctl_elem_value *ucontrol)
{
	struct trid_audio_bridge *bridge = snd_kcontrol_chip(kcontrol);
	u32 reg;

	reg = trid_reg_read(bridge, TRID_MSP_OWA_OUT_SRC_PHYS) & 0xF000;
	if (reg == 0x2000)
		bridge->msp_owa_out_source = 1;
	else if (reg == 0x6000)
		bridge->msp_owa_out_source = 2;
	else
		bridge->msp_owa_out_source = 0;

	ucontrol->value.enumerated.item[0] = bridge->msp_owa_out_source;
	return 0;
}

static int trid_msp_owa_out_put(struct snd_kcontrol *kcontrol,
				struct snd_ctl_elem_value *ucontrol)
{
	struct trid_audio_bridge *bridge = snd_kcontrol_chip(kcontrol);
	unsigned int val = ucontrol->value.enumerated.item[0];
	u32 reg;

	if (val >= ARRAY_SIZE(trid_msp_owa_out_texts))
		return -EINVAL;
	if (bridge->msp_owa_out_source == val)
		return 0;

	bridge->msp_owa_out_source = val;
	switch (val) {
	case 1:
		reg = 0x2000;
		break;
	case 2:
		reg = 0x6000;
		break;
	default:
		reg = 0;
		break;
	}

	trid_reg_update_bits(bridge, TRID_MSP_OWA_OUT_SRC_PHYS, 0xF000, reg);
	return 1;
}

static const struct snd_kcontrol_new trid_controls[] = {
	{
		.iface = SNDRV_CTL_ELEM_IFACE_MIXER,
		.name = "DelayLine1 Time Set",
		.info = trid_delayline_info,
		.get = trid_delayline_get,
		.put = trid_delayline_put,
		.private_value = TRID_CTL_DELAYLINE1,
	},
	{
		.iface = SNDRV_CTL_ELEM_IFACE_MIXER,
		.name = "DelayLine2 Time Set",
		.info = trid_delayline_info,
		.get = trid_delayline_get,
		.put = trid_delayline_put,
		.private_value = TRID_CTL_DELAYLINE2,
	},
	{
		.iface = SNDRV_CTL_ELEM_IFACE_MIXER,
		.name = "DelayLine3 Time Set",
		.info = trid_delayline_info,
		.get = trid_delayline_get,
		.put = trid_delayline_put,
		.private_value = TRID_CTL_DELAYLINE3,
	},
	{
		.iface = SNDRV_CTL_ELEM_IFACE_MIXER,
		.name = "DelayLine4 Time Set",
		.info = trid_delayline_info,
		.get = trid_delayline_get,
		.put = trid_delayline_put,
		.private_value = TRID_CTL_DELAYLINE4,
	},
	{
		.iface = SNDRV_CTL_ELEM_IFACE_MIXER,
		.name = "ARC source selector",
		.info = trid_arc_source_info,
		.get = trid_arc_source_get,
		.put = trid_arc_source_put,
	},
	{
		.iface = SNDRV_CTL_ELEM_IFACE_MIXER,
		.name = "MSP OWA OUT selector",
		.info = trid_msp_owa_out_info,
		.get = trid_msp_owa_out_get,
		.put = trid_msp_owa_out_put,
	},
};

static int trid_create_pcm(struct trid_audio_bridge *bridge,
			   unsigned int device, bool capture)
{
	struct snd_pcm *pcm;
	int ret;

	ret = snd_pcm_new(bridge->card, TRID_PCM_NAME, device,
			  1, capture ? 1 : 0, &pcm);
	if (ret < 0)
		return ret;

	pcm->private_data = bridge;
	strscpy(pcm->name, "Trid PCM", sizeof(pcm->name));
	snd_pcm_set_ops(pcm, SNDRV_PCM_STREAM_PLAYBACK, &trid_playback_ops);
	if (capture)
		snd_pcm_set_ops(pcm, SNDRV_PCM_STREAM_CAPTURE, &trid_capture_ops);
	snd_pcm_set_managed_buffer_all(pcm, SNDRV_DMA_TYPE_CONTINUOUS,
				       bridge->dev, 64 * 1024, 128 * 1024);
	bridge->pcm[device] = pcm;
	return 0;
}

int trid_register_pcm(struct trid_audio_bridge *bridge, int card_index,
		      const char *card_id)
{
	unsigned int i;
	int ret;

	ret = snd_card_new(bridge->dev, card_index, card_id, THIS_MODULE, 0,
			   &bridge->card);
	if (ret < 0)
		return ret;

	strscpy(bridge->card->driver, "snd_alsa_trid",
		sizeof(bridge->card->driver));
	strscpy(bridge->card->shortname, TRID_CARD_NAME,
		sizeof(bridge->card->shortname));
	snprintf(bridge->card->longname, sizeof(bridge->card->longname),
		 "%s%u", TRID_CARD_NAME, bridge->card->number + 1);
	strscpy(bridge->card->mixername, TRID_MIXER_NAME,
		sizeof(bridge->card->mixername));

	for (i = 0; i < TRID_MAX_DELAYLINES; i++)
		bridge->delayline_ms[i] = 100;

	ret = trid_create_pcm(bridge, 0, true);
	if (ret < 0)
		goto err_card;
	ret = trid_create_pcm(bridge, 1, true);
	if (ret < 0)
		goto err_card;
	ret = trid_create_pcm(bridge, 2, false);
	if (ret < 0)
		goto err_card;
	ret = trid_create_pcm(bridge, 3, false);
	if (ret < 0)
		goto err_card;

	for (i = 0; i < ARRAY_SIZE(trid_controls); i++) {
		ret = snd_ctl_add(bridge->card,
				snd_ctl_new1(&trid_controls[i], bridge));
		if (ret < 0)
			goto err_card;
	}

	ret = snd_card_register(bridge->card);
	if (ret < 0)
		goto err_card;

	return 0;

err_card:
	snd_card_free(bridge->card);
	bridge->card = NULL;
	return ret;
}
EXPORT_SYMBOL_GPL(trid_register_pcm);

void trid_unregister_pcm(struct trid_audio_bridge *bridge)
{
	if (!bridge->card)
		return;

	snd_card_free(bridge->card);
	bridge->card = NULL;
}
EXPORT_SYMBOL_GPL(trid_unregister_pcm);

void trid_pcm_notify_irq(struct trid_audio_bridge *bridge, bool audif_irq,
			 u32 status)
{
	unsigned int i;

	for (i = 0; i < TRID_MAX_PCMS; i++) {
		if (!bridge->playback[i].running || !bridge->playback[i].substream)
			continue;
		if (!timer_pending(&bridge->playback[i].timer) &&
		    ((audif_irq &&
		      (status & (bridge->playback[i].iface == TRID_IFACE_SPDO0 ?
				  0x8804 : 0x77000))) ||
		     (!audif_irq && (status & 0x30))))
			snd_pcm_period_elapsed(bridge->playback[i].substream);
	}

	for (i = 0; i < TRID_MAX_OSTREAMS; i++) {
		if (!bridge->capture[i].running || !bridge->capture[i].substream)
			continue;
		if (!timer_pending(&bridge->capture[i].timer) &&
		    ((audif_irq &&
		      (status & (bridge->capture[i].iface == TRID_IFACE_SPDI1 ?
				  0x10007B : 0x10007B))) ||
		     (!audif_irq && (status & 0x3C00))))
			snd_pcm_period_elapsed(bridge->capture[i].substream);
	}
}
EXPORT_SYMBOL_GPL(trid_pcm_notify_irq);
