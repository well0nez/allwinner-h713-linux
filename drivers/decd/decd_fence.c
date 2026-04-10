// SPDX-License-Identifier: GPL-2.0

#include <linux/file.h>
#include <linux/slab.h>
#include <linux/sync_file.h>

#include "decd_types.h"

static const char *dec_fence_get_driver_name(struct dma_fence *f)
{
	return DECD_NAME;
}

static const char *dec_fence_get_timeline_name(struct dma_fence *f)
{
	struct dec_fence *df = container_of(f, struct dec_fence, base);

	return df->ctx->name;
}

static bool dec_fence_signaled_internal(struct dma_fence *f)
{
	struct dec_fence *df = container_of(f, struct dec_fence, base);

	return df->signaled;
}

static void dec_fence_release_internal(struct dma_fence *f)
{
	struct dec_fence *df = container_of(f, struct dec_fence, base);

	kfree(df);
}

static const struct dma_fence_ops dec_fence_ops = {
	.get_driver_name = dec_fence_get_driver_name,
	.get_timeline_name = dec_fence_get_timeline_name,
	.signaled = dec_fence_signaled_internal,
	.release = dec_fence_release_internal,
};

struct dec_fence_context *dec_fence_context_alloc(const char *name)
{
	struct dec_fence_context *ctx;

	ctx = kzalloc(sizeof(*ctx), GFP_KERNEL);
	if (!ctx)
		return ERR_PTR(-ENOMEM);

	strscpy(ctx->name, name, sizeof(ctx->name));
	ctx->context = dma_fence_context_alloc(1);
	spin_lock_init(&ctx->lock);
	return ctx;
}

struct dec_fence *dec_fence_alloc(struct dec_fence_context *ctx)
{
	struct dec_fence *df;
	u32 seqno;

	df = kzalloc(sizeof(*df), GFP_KERNEL);
	if (!df)
		return NULL;

	spin_lock(&ctx->lock);
	seqno = ++ctx->seqno;
	dma_fence_init(&df->base, &dec_fence_ops, &ctx->lock, ctx->context,
		       seqno);
	df->ctx = ctx;
	spin_unlock(&ctx->lock);

	return df;
}

void dec_fence_signal(struct dec_fence *df)
{
	unsigned long flags;

	if (!df)
		return;

	spin_lock_irqsave(&df->ctx->lock, flags);
	dma_fence_signal_locked(&df->base);
	df->signaled = true;
	spin_unlock_irqrestore(&df->ctx->lock, flags);
}

int dec_fence_fd_create(struct dec_fence *df)
{
	struct sync_file *sync;
	int fd;

	fd = get_unused_fd_flags(O_CLOEXEC);
	if (fd < 0)
		return fd;

	sync = sync_file_create(&df->base);
	if (!sync) {
		put_unused_fd(fd);
		return -ENOMEM;
	}

	fd_install(fd, sync->file);
	return fd;
}
