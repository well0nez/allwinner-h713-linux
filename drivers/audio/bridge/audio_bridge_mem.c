// SPDX-License-Identifier: GPL-2.0-only

#include <linux/module.h>

#include "audio_bridge.h"

static void trid_setup_segments(struct trid_audio_bridge *bridge)
{
	size_t i;
	char *cpu = bridge->shared_cpu;
	dma_addr_t dma = bridge->shared_dma;
	size_t offset = 0;

	for (i = 0; i < TRID_MAX_ISTREAMS; i++) {
		bridge->istream[i].cpu = cpu + offset;
		bridge->istream[i].dma = dma + offset;
		bridge->istream[i].size = TRID_SEGMENT_BYTES;
		offset += TRID_SEGMENT_BYTES;
	}

	for (i = 0; i < TRID_MAX_OSTREAMS; i++) {
		bridge->ostream[i].cpu = cpu + offset;
		bridge->ostream[i].dma = dma + offset;
		bridge->ostream[i].size = TRID_SEGMENT_BYTES;
		offset += TRID_SEGMENT_BYTES;
	}

	for (i = 0; i < TRID_MAX_DELAYLINES; i++) {
		bridge->delayline[i].cpu = cpu + offset;
		bridge->delayline[i].dma = dma + offset;
		bridge->delayline[i].size = TRID_DELAYLINE_BYTES / TRID_MAX_DELAYLINES;
		offset += bridge->delayline[i].size;
	}
}

int trid_mem_init(struct trid_audio_bridge *bridge)
{
	bridge->shared_cpu = dma_alloc_coherent(bridge->dev, TRID_SHARED_DMA_BYTES,
					      &bridge->shared_dma,
					      GFP_KERNEL | __GFP_ZERO);
	if (!bridge->shared_cpu)
		return -ENOMEM;

	trid_setup_segments(bridge);
	return 0;
}
EXPORT_SYMBOL_GPL(trid_mem_init);

void trid_mem_exit(struct trid_audio_bridge *bridge)
{
	if (!bridge->shared_cpu)
		return;

	dma_free_coherent(bridge->dev, TRID_SHARED_DMA_BYTES,
				  bridge->shared_cpu, bridge->shared_dma);
	bridge->shared_cpu = NULL;
	bridge->shared_dma = 0;
}
EXPORT_SYMBOL_GPL(trid_mem_exit);
