// SPDX-License-Identifier: GPL-2.0+
/*
 * Allwinner H713 AV1 Hardware Decoder Driver - V4L2 Interface
 *
 * Copyright (C) 2025 HY300 Linux Porting Project
 *
 * This file implements the V4L2 stateless decoder interface for the H713 AV1 decoder.
 */

#include <linux/pm_runtime.h>
#include <media/v4l2-event.h>
#include <media/v4l2-mem2mem.h>
#include <media/v4l2-ioctl.h>
#include <media/videobuf2-dma-contig.h>
#include <media/v4l2-ctrls.h>

#include "sun50i-h713-av1.h"

#define AV1_MIN_WIDTH		64
#define AV1_MAX_WIDTH		7680
#define AV1_MIN_HEIGHT		64
#define AV1_MAX_HEIGHT		4320

/* Supported input formats */
static const u32 av1_input_formats[] = {
	V4L2_PIX_FMT_AV1_FRAME,
};

/* Supported output formats */
static const u32 av1_output_formats[] = {
	V4L2_PIX_FMT_YUV420,
	V4L2_PIX_FMT_YUV420M,
	V4L2_PIX_FMT_NV12,
	V4L2_PIX_FMT_NV12M,
};

static const struct v4l2_frmsize_discrete av1_frame_sizes[] = {
	{ 1920, 1080 },
	{ 3840, 2160 },
	{ 7680, 4320 },
};

/**
 * sun50i_av1_find_format - Find format information
 */
static const u32 *sun50i_av1_find_format(u32 fourcc, bool is_output)
{
	const u32 *formats;
	unsigned int num_formats;
	unsigned int i;

	if (is_output) {
		formats = av1_output_formats;
		num_formats = ARRAY_SIZE(av1_output_formats);
	} else {
		formats = av1_input_formats;
		num_formats = ARRAY_SIZE(av1_input_formats);
	}

	for (i = 0; i < num_formats; i++) {
		if (formats[i] == fourcc)
			return &formats[i];
	}

	return NULL;
}

/**
 * sun50i_av1_queue_setup - Setup buffer queue
 */
static int sun50i_av1_queue_setup(struct vb2_queue *vq,
				   unsigned int *nbuffers,
				   unsigned int *nplanes,
				   unsigned int sizes[],
				   struct device *alloc_devs[])
{
	struct sun50i_av1_ctx *ctx = vb2_get_drv_priv(vq);
	struct v4l2_pix_format_mplane *pix;
	unsigned int i;

	if (V4L2_TYPE_IS_OUTPUT(vq->type))
		pix = &ctx->src_fmt;
	else
		pix = &ctx->dst_fmt;

	if (*nplanes) {
		if (*nplanes != pix->num_planes)
			return -EINVAL;

		for (i = 0; i < pix->num_planes; i++) {
			if (sizes[i] < pix->plane_fmt[i].sizeimage)
				return -EINVAL;
		}
		return 0;
	}

	*nplanes = pix->num_planes;
	for (i = 0; i < pix->num_planes; i++)
		sizes[i] = pix->plane_fmt[i].sizeimage;

	return 0;
}

/**
 * sun50i_av1_buf_prepare - Prepare buffer for processing
 */
static int sun50i_av1_buf_prepare(struct vb2_buffer *vb)
{
	struct vb2_v4l2_buffer *vbuf = to_vb2_v4l2_buffer(vb);
	struct sun50i_av1_ctx *ctx = vb2_get_drv_priv(vb->vb2_queue);
	struct v4l2_pix_format_mplane *pix;
	unsigned int i;

	if (V4L2_TYPE_IS_OUTPUT(vb->type))
		pix = &ctx->src_fmt;
	else
		pix = &ctx->dst_fmt;

	if (V4L2_TYPE_IS_OUTPUT(vb->type)) {
		if (vbuf->field == V4L2_FIELD_ANY)
			vbuf->field = V4L2_FIELD_NONE;
		if (vbuf->field != V4L2_FIELD_NONE) {
			dev_err(ctx->dev->dev, "Unsupported field type\n");
			return -EINVAL;
		}
	}

	for (i = 0; i < pix->num_planes; i++) {
		if (vb2_plane_size(vb, i) < pix->plane_fmt[i].sizeimage) {
			dev_err(ctx->dev->dev,
				"Plane %d size too small (%lu < %u)\n",
				i, vb2_plane_size(vb, i),
				pix->plane_fmt[i].sizeimage);
			return -EINVAL;
		}
	}

	return 0;
}

/**
 * sun50i_av1_buf_queue - Queue buffer for processing
 */
static void sun50i_av1_buf_queue(struct vb2_buffer *vb)
{
	struct vb2_v4l2_buffer *vbuf = to_vb2_v4l2_buffer(vb);
	struct sun50i_av1_ctx *ctx = vb2_get_drv_priv(vb->vb2_queue);

	v4l2_m2m_buf_queue(ctx->m2m_ctx, vbuf);
}

/**
 * sun50i_av1_start_streaming - Start streaming
 */
static int sun50i_av1_start_streaming(struct vb2_queue *q, unsigned int count)
{
	struct sun50i_av1_ctx *ctx = vb2_get_drv_priv(q);
	struct sun50i_av1_dev *dev = ctx->dev;
	int ret;

	if (V4L2_TYPE_IS_OUTPUT(q->type))
		ctx->streamon_out = true;
	else
		ctx->streamon_cap = true;

	/* Enable runtime PM */
	ret = pm_runtime_get_sync(dev->dev);
	if (ret < 0) {
		dev_err(dev->dev, "Failed to enable runtime PM: %d\n", ret);
		return ret;
	}

	/* Update session count */
	atomic_inc(&av1_metrics.current_sessions);

	return 0;
}

/**
 * sun50i_av1_stop_streaming - Stop streaming
 */
static void sun50i_av1_stop_streaming(struct vb2_queue *q)
{
	struct sun50i_av1_ctx *ctx = vb2_get_drv_priv(q);
	struct sun50i_av1_dev *dev = ctx->dev;
	struct vb2_v4l2_buffer *vbuf;

	if (V4L2_TYPE_IS_OUTPUT(q->type)) {
		ctx->streamon_out = false;
		while ((vbuf = v4l2_m2m_src_buf_remove(ctx->m2m_ctx)))
			v4l2_m2m_buf_done(vbuf, VB2_BUF_STATE_ERROR);
	} else {
		ctx->streamon_cap = false;
		while ((vbuf = v4l2_m2m_dst_buf_remove(ctx->m2m_ctx)))
			v4l2_m2m_buf_done(vbuf, VB2_BUF_STATE_ERROR);
	}

	/* Update session count */
	atomic_dec(&av1_metrics.current_sessions);

	/* Disable runtime PM */
	pm_runtime_put_sync(dev->dev);
}

static const struct vb2_ops sun50i_av1_queue_ops = {
	.queue_setup		= sun50i_av1_queue_setup,
	.buf_prepare		= sun50i_av1_buf_prepare,
	.buf_queue		= sun50i_av1_buf_queue,
	.start_streaming	= sun50i_av1_start_streaming,
	.stop_streaming		= sun50i_av1_stop_streaming,
	.wait_prepare		= vb2_ops_wait_prepare,
	.wait_finish		= vb2_ops_wait_finish,
};

/**
 * sun50i_av1_queue_init - Initialize buffer queue
 */
static int sun50i_av1_queue_init(void *priv, struct vb2_queue *src_vq,
				  struct vb2_queue *dst_vq)
{
	struct sun50i_av1_ctx *ctx = priv;
	int ret;

	src_vq->type = V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE;
	src_vq->io_modes = VB2_MMAP | VB2_DMABUF;
	src_vq->drv_priv = ctx;
	src_vq->buf_struct_size = sizeof(struct v4l2_m2m_buffer);
	src_vq->ops = &sun50i_av1_queue_ops;
	src_vq->mem_ops = &vb2_dma_contig_memops;
	src_vq->timestamp_flags = V4L2_BUF_FLAG_TIMESTAMP_COPY;
	src_vq->lock = &ctx->dev->dev_mutex;
	src_vq->dev = ctx->dev->dma_dev;

	ret = vb2_queue_init(src_vq);
	if (ret)
		return ret;

	dst_vq->type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
	dst_vq->io_modes = VB2_MMAP | VB2_DMABUF;
	dst_vq->drv_priv = ctx;
	dst_vq->buf_struct_size = sizeof(struct v4l2_m2m_buffer);
	dst_vq->ops = &sun50i_av1_queue_ops;
	dst_vq->mem_ops = &vb2_dma_contig_memops;
	dst_vq->timestamp_flags = V4L2_BUF_FLAG_TIMESTAMP_COPY;
	dst_vq->lock = &ctx->dev->dev_mutex;
	dst_vq->dev = ctx->dev->dma_dev;

	return vb2_queue_init(dst_vq);
}

/**
 * sun50i_av1_device_run - Process a decode request
 */
static void sun50i_av1_device_run(void *priv)
{
	struct sun50i_av1_ctx *ctx = priv;
	struct sun50i_av1_dev *dev = ctx->dev;
	struct vb2_v4l2_buffer *src_buf, *dst_buf;
	struct av1_frame_config *config = &ctx->frame_config;
	ktime_t start_time;
	int ret;

	src_buf = v4l2_m2m_next_src_buf(ctx->m2m_ctx);
	dst_buf = v4l2_m2m_next_dst_buf(ctx->m2m_ctx);

	/* Configure frame parameters from buffers */
	config->format = AV1_FORMAT_YUV420P_10BIT_AV1;
	config->fbd_enable = true;
	config->blue_enable = false;
	config->interlace_enable = false;

	/* Set output buffer addresses */
	config->image_addr[0] = vb2_dma_contig_plane_dma_addr(&dst_buf->vb2_buf, 0);
	if (ctx->dst_fmt.num_planes > 1) {
		config->image_addr[1] = vb2_dma_contig_plane_dma_addr(&dst_buf->vb2_buf, 1);
		config->image_addr[2] = vb2_dma_contig_plane_dma_addr(&dst_buf->vb2_buf, 2);
	} else {
		/* NV12 format - UV interleaved */
		config->image_addr[1] = config->image_addr[0] +
					ctx->dst_fmt.plane_fmt[0].bytesperline *
					ctx->dst_fmt.height;
		config->image_addr[2] = 0;
	}

	/* Set dimensions and stride */
	config->image_width[0] = ctx->dst_fmt.width;
	config->image_height[0] = ctx->dst_fmt.height;

	/* Configure metadata from source buffer */
	config->metadata_addr = vb2_dma_contig_plane_dma_addr(&src_buf->vb2_buf, 0);
	config->metadata_size = vb2_get_plane_payload(&src_buf->vb2_buf, 0);

	/* Record start time for metrics */
	start_time = ktime_get();

	/* Start hardware decode */
	ret = sun50i_av1_hw_start_decode(dev, config);
	if (ret) {
		dev_err(dev->dev, "Failed to start decode: %d\n", ret);
		
		/* Mark buffers as error */
		src_buf = v4l2_m2m_src_buf_remove(ctx->m2m_ctx);
		dst_buf = v4l2_m2m_dst_buf_remove(ctx->m2m_ctx);
		
		v4l2_m2m_buf_done(src_buf, VB2_BUF_STATE_ERROR);
		v4l2_m2m_buf_done(dst_buf, VB2_BUF_STATE_ERROR);
		
		/* Update error metrics */
		atomic64_inc(&av1_metrics.decode_errors);
		
		/* Schedule next job */
		v4l2_m2m_job_finish(dev->m2m_dev, ctx->m2m_ctx);
		return;
	}

	/* Store start time in context for completion handling */
	ctx->decode_start_time = start_time;

	dev_dbg(dev->dev, "Decode started for frame %llu\n", src_buf->vb2_buf.timestamp);
}

static const struct v4l2_m2m_ops sun50i_av1_m2m_ops = {
	.device_run	= sun50i_av1_device_run,
};

/**
 * sun50i_av1_open - Open device instance
 */
static int sun50i_av1_open(struct file *file)
{
	struct sun50i_av1_dev *dev = video_drvdata(file);
	struct sun50i_av1_ctx *ctx;
	int ret;

	ctx = kzalloc(sizeof(*ctx), GFP_KERNEL);
	if (!ctx)
		return -ENOMEM;

	ctx->dev = dev;
	v4l2_fh_init(&ctx->fh, &dev->vdev);
	file->private_data = &ctx->fh;
	v4l2_fh_add(&ctx->fh);

	/* Initialize M2M context */
	ctx->m2m_ctx = v4l2_m2m_ctx_init(dev->m2m_dev, ctx,
					  sun50i_av1_queue_init);
	if (IS_ERR(ctx->m2m_ctx)) {
		ret = PTR_ERR(ctx->m2m_ctx);
		goto err_free_ctx;
	}

	/* Set default formats */
	ctx->src_fmt.pixelformat = V4L2_PIX_FMT_AV1_FRAME;
	ctx->src_fmt.num_planes = 1;
	ctx->src_fmt.plane_fmt[0].sizeimage = SZ_1M;

	ctx->dst_fmt.pixelformat = V4L2_PIX_FMT_NV12;
	ctx->dst_fmt.width = 1920;
	ctx->dst_fmt.height = 1080;
	ctx->dst_fmt.num_planes = 1;
	ctx->dst_fmt.plane_fmt[0].bytesperline = 1920;
	ctx->dst_fmt.plane_fmt[0].sizeimage = 1920 * 1080 * 3 / 2;

	atomic_inc(&dev->num_inst);

	dev_dbg(dev->dev, "AV1 decoder opened (instances: %d)\n",
		atomic_read(&dev->num_inst));

	return 0;

err_free_ctx:
	v4l2_fh_del(&ctx->fh);
	v4l2_fh_exit(&ctx->fh);
	kfree(ctx);
	return ret;
}

/**
 * sun50i_av1_release - Release device instance
 */
static int sun50i_av1_release(struct file *file)
{
	struct sun50i_av1_ctx *ctx = container_of(file->private_data,
						  struct sun50i_av1_ctx, fh);
	struct sun50i_av1_dev *dev = ctx->dev;

	dev_dbg(dev->dev, "AV1 decoder release\n");

	/* Cleanup M2M context */
	v4l2_m2m_ctx_release(ctx->m2m_ctx);

	/* Cleanup V4L2 file handle */
	v4l2_fh_del(&ctx->fh);
	v4l2_fh_exit(&ctx->fh);

	atomic_dec(&dev->num_inst);
	kfree(ctx);

	dev_dbg(dev->dev, "AV1 decoder released (instances: %d)\n",
		atomic_read(&dev->num_inst));

	return 0;
}

static const struct v4l2_file_operations sun50i_av1_fops = {
	.owner		= THIS_MODULE,
	.open		= sun50i_av1_open,
	.release	= sun50i_av1_release,
	.poll		= v4l2_m2m_fop_poll,
	.unlocked_ioctl	= video_ioctl2,
	.mmap		= v4l2_m2m_fop_mmap,
};

/**
 * sun50i_av1_querycap - Query device capabilities
 */
static int sun50i_av1_querycap(struct file *file, void *priv,
				struct v4l2_capability *cap)
{
	strscpy(cap->driver, "sun50i-h713-av1", sizeof(cap->driver));
	strscpy(cap->card, "Allwinner H713 AV1 Decoder", sizeof(cap->card));
	strscpy(cap->bus_info, "platform:sun50i-h713-av1", sizeof(cap->bus_info));

	cap->capabilities = V4L2_CAP_VIDEO_M2M_MPLANE | V4L2_CAP_STREAMING;

	return 0;
}

/**
 * sun50i_av1_enum_fmt - Enumerate supported formats
 */
static int sun50i_av1_enum_fmt(struct file *file, void *priv,
				struct v4l2_fmtdesc *f)
{
	const u32 *formats;
	unsigned int num_formats;
	bool is_output = V4L2_TYPE_IS_OUTPUT(f->type);

	if (is_output) {
		formats = av1_input_formats;
		num_formats = ARRAY_SIZE(av1_input_formats);
	} else {
		formats = av1_output_formats;
		num_formats = ARRAY_SIZE(av1_output_formats);
	}

	if (f->index >= num_formats)
		return -EINVAL;

	f->pixelformat = formats[f->index];

	return 0;
}

/**
 * sun50i_av1_g_fmt - Get format
 */
static int sun50i_av1_g_fmt(struct file *file, void *priv,
			     struct v4l2_format *f)
{
	struct sun50i_av1_ctx *ctx = container_of(file->private_data,
						  struct sun50i_av1_ctx, fh);

	if (V4L2_TYPE_IS_OUTPUT(f->type))
		f->fmt.pix_mp = ctx->src_fmt;
	else
		f->fmt.pix_mp = ctx->dst_fmt;

	return 0;
}

/**
 * sun50i_av1_try_fmt - Try format
 */
static int sun50i_av1_try_fmt(struct file *file, void *priv,
			       struct v4l2_format *f)
{
	const u32 *format;
	bool is_output = V4L2_TYPE_IS_OUTPUT(f->type);

	format = sun50i_av1_find_format(f->fmt.pix_mp.pixelformat, !is_output);
	if (!format) {
		if (is_output)
			f->fmt.pix_mp.pixelformat = av1_input_formats[0];
		else
			f->fmt.pix_mp.pixelformat = av1_output_formats[0];
	}

	/* Clamp dimensions */
	f->fmt.pix_mp.width = clamp(f->fmt.pix_mp.width,
				    AV1_MIN_WIDTH, AV1_MAX_WIDTH);
	f->fmt.pix_mp.height = clamp(f->fmt.pix_mp.height,
				     AV1_MIN_HEIGHT, AV1_MAX_HEIGHT);

	/* Set plane information based on format */
	if (is_output) {
		f->fmt.pix_mp.num_planes = 1;
		f->fmt.pix_mp.plane_fmt[0].sizeimage = SZ_1M;
		f->fmt.pix_mp.plane_fmt[0].bytesperline = 0;
	} else {
		if (f->fmt.pix_mp.pixelformat == V4L2_PIX_FMT_NV12 ||
		    f->fmt.pix_mp.pixelformat == V4L2_PIX_FMT_YUV420) {
			f->fmt.pix_mp.num_planes = 1;
			f->fmt.pix_mp.plane_fmt[0].bytesperline = f->fmt.pix_mp.width;
			f->fmt.pix_mp.plane_fmt[0].sizeimage =
				f->fmt.pix_mp.width * f->fmt.pix_mp.height * 3 / 2;
		} else {
			f->fmt.pix_mp.num_planes = 3;
			f->fmt.pix_mp.plane_fmt[0].bytesperline = f->fmt.pix_mp.width;
			f->fmt.pix_mp.plane_fmt[0].sizeimage =
				f->fmt.pix_mp.width * f->fmt.pix_mp.height;
			f->fmt.pix_mp.plane_fmt[1].bytesperline = f->fmt.pix_mp.width / 2;
			f->fmt.pix_mp.plane_fmt[1].sizeimage =
				f->fmt.pix_mp.width * f->fmt.pix_mp.height / 4;
			f->fmt.pix_mp.plane_fmt[2].bytesperline = f->fmt.pix_mp.width / 2;
			f->fmt.pix_mp.plane_fmt[2].sizeimage =
				f->fmt.pix_mp.width * f->fmt.pix_mp.height / 4;
		}
	}

	return 0;
}

/**
 * sun50i_av1_s_fmt - Set format
 */
static int sun50i_av1_s_fmt(struct file *file, void *priv,
			     struct v4l2_format *f)
{
	struct sun50i_av1_ctx *ctx = container_of(file->private_data,
						  struct sun50i_av1_ctx, fh);
	int ret;

	ret = sun50i_av1_try_fmt(file, priv, f);
	if (ret)
		return ret;

	if (V4L2_TYPE_IS_OUTPUT(f->type))
		ctx->src_fmt = f->fmt.pix_mp;
	else
		ctx->dst_fmt = f->fmt.pix_mp;

	return 0;
}

static const struct v4l2_ioctl_ops sun50i_av1_ioctl_ops = {
	.vidioc_querycap		= sun50i_av1_querycap,
	.vidioc_enum_fmt_vid_cap	= sun50i_av1_enum_fmt,
	.vidioc_enum_fmt_vid_out	= sun50i_av1_enum_fmt,
	.vidioc_g_fmt_vid_cap_mplane	= sun50i_av1_g_fmt,
	.vidioc_g_fmt_vid_out_mplane	= sun50i_av1_g_fmt,
	.vidioc_try_fmt_vid_cap_mplane	= sun50i_av1_try_fmt,
	.vidioc_try_fmt_vid_out_mplane	= sun50i_av1_try_fmt,
	.vidioc_s_fmt_vid_cap_mplane	= sun50i_av1_s_fmt,
	.vidioc_s_fmt_vid_out_mplane	= sun50i_av1_s_fmt,

	.vidioc_reqbufs			= v4l2_m2m_ioctl_reqbufs,
	.vidioc_querybuf		= v4l2_m2m_ioctl_querybuf,
	.vidioc_qbuf			= v4l2_m2m_ioctl_qbuf,
	.vidioc_dqbuf			= v4l2_m2m_ioctl_dqbuf,
	.vidioc_prepare_buf		= v4l2_m2m_ioctl_prepare_buf,
	.vidioc_create_bufs		= v4l2_m2m_ioctl_create_bufs,
	.vidioc_expbuf			= v4l2_m2m_ioctl_expbuf,

	.vidioc_streamon		= v4l2_m2m_ioctl_streamon,
	.vidioc_streamoff		= v4l2_m2m_ioctl_streamoff,

	.vidioc_subscribe_event		= v4l2_ctrl_subscribe_event,
	.vidioc_unsubscribe_event	= v4l2_event_unsubscribe,
};

/**
 * sun50i_av1_v4l2_init - Initialize V4L2 interface
 * @dev: Device context
 *
 * Returns: 0 on success, negative error code on failure
 */
int sun50i_av1_v4l2_init(struct sun50i_av1_dev *dev)
{
	struct video_device *vdev = &dev->vdev;
	int ret;

	dev_dbg(dev->dev, "Initializing V4L2 interface\n");

	/* Initialize M2M device */
	dev->m2m_dev = v4l2_m2m_init(&sun50i_av1_m2m_ops);
	if (IS_ERR(dev->m2m_dev)) {
		dev_err(dev->dev, "Failed to initialize M2M device\n");
		return PTR_ERR(dev->m2m_dev);
	}

	/* Initialize video device */
	vdev->fops = &sun50i_av1_fops;
	vdev->ioctl_ops = &sun50i_av1_ioctl_ops;
	vdev->minor = -1;
	vdev->release = video_device_release_empty;
	vdev->lock = &dev->dev_mutex;
	vdev->v4l2_dev = &dev->v4l2_dev;
	vdev->vfl_dir = VFL_DIR_M2M;
	vdev->device_caps = V4L2_CAP_VIDEO_M2M_MPLANE | V4L2_CAP_STREAMING;

	strscpy(vdev->name, "sun50i-h713-av1-dec", sizeof(vdev->name));

	video_set_drvdata(vdev, dev);

	/* Register video device */
	ret = video_register_device(vdev, VFL_TYPE_VIDEO, -1);
	if (ret) {
		dev_err(dev->dev, "Failed to register video device: %d\n", ret);
		goto err_m2m_release;
	}

	dev_info(dev->dev, "V4L2 AV1 decoder registered as %s\n",
		 video_device_node_name(vdev));

	return 0;

err_m2m_release:
	v4l2_m2m_release(dev->m2m_dev);
	return ret;
}

/**
 * sun50i_av1_v4l2_cleanup - Cleanup V4L2 interface
 * @dev: Device context
 */
void sun50i_av1_v4l2_cleanup(struct sun50i_av1_dev *dev)
{
	dev_dbg(dev->dev, "Cleaning up V4L2 interface\n");

	video_unregister_device(&dev->vdev);
	v4l2_m2m_release(dev->m2m_dev);

	dev_dbg(dev->dev, "V4L2 interface cleaned up\n");
}
