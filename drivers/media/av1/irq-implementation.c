/**
 * sun50i_av1_irq_handler - AV1 hardware interrupt handler
 * @irq: IRQ number
 * @priv: Device context
 *
 * Returns: IRQ_HANDLED if interrupt was handled, IRQ_NONE otherwise
 */
irqreturn_t sun50i_av1_irq_handler(int irq, void *priv)
{
	struct sun50i_av1_dev *dev = priv;
	u32 status;
	bool handled = false;
	
	/* Read interrupt status */
	status = av1_read(dev, AV1_REG_INT_STATUS);
	if (!status)
		return IRQ_NONE;
	
	/* Clear interrupts */
	av1_write(dev, AV1_REG_INT_STATUS, status);
	
	dev_dbg(dev->dev, "AV1 IRQ: status=0x%08x\n", status);
	
	/* Handle decode completion */
	if (status & AV1_INT_DECODE_DONE) {
		struct sun50i_av1_ctx *ctx = NULL;
		struct vb2_v4l2_buffer *src_buf, *dst_buf;
		ktime_t decode_time;
		
		dev_dbg(dev->dev, "Decode completion interrupt\n");
		
		/* Find active context */
		if (dev->m2m_dev) {
			ctx = v4l2_m2m_get_curr_priv(dev->m2m_dev);
		}
		
		if (ctx && ctx->m2m_ctx) {
			/* Calculate decode time */
			decode_time = ktime_sub(ktime_get(), ctx->decode_start_time);
			av1_metrics.total_decode_time_us += ktime_to_us(decode_time);
			
			/* Get buffers */
			src_buf = v4l2_m2m_src_buf_remove(ctx->m2m_ctx);
			dst_buf = v4l2_m2m_dst_buf_remove(ctx->m2m_ctx);
			
			if (src_buf && dst_buf) {
				/* Copy timestamp */
				dst_buf->vb2_buf.timestamp = src_buf->vb2_buf.timestamp;
				
				/* Mark buffers as done */
				v4l2_m2m_buf_done(src_buf, VB2_BUF_STATE_DONE);
				v4l2_m2m_buf_done(dst_buf, VB2_BUF_STATE_DONE);
				
				/* Update metrics */
				atomic64_inc(&av1_metrics.frames_decoded);
			}
			
			/* Schedule next job */
			v4l2_m2m_job_finish(dev->m2m_dev, ctx->m2m_ctx);
		}
		
		handled = true;
	}
	
	/* Handle decode errors */
	if (status & AV1_INT_DECODE_ERROR) {
		struct sun50i_av1_ctx *ctx = NULL;
		struct vb2_v4l2_buffer *src_buf, *dst_buf;
		
		dev_err(dev->dev, "Decode error interrupt\n");
		
		/* Find active context */
		if (dev->m2m_dev) {
			ctx = v4l2_m2m_get_curr_priv(dev->m2m_dev);
		}
		
		if (ctx && ctx->m2m_ctx) {
			/* Get buffers */
			src_buf = v4l2_m2m_src_buf_remove(ctx->m2m_ctx);
			dst_buf = v4l2_m2m_dst_buf_remove(ctx->m2m_ctx);
			
			if (src_buf && dst_buf) {
				/* Mark buffers as error */
				v4l2_m2m_buf_done(src_buf, VB2_BUF_STATE_ERROR);
				v4l2_m2m_buf_done(dst_buf, VB2_BUF_STATE_ERROR);
				
				/* Update error metrics */
				atomic64_inc(&av1_metrics.decode_errors);
			}
			
			/* Schedule next job */
			v4l2_m2m_job_finish(dev->m2m_dev, ctx->m2m_ctx);
		}
		
		handled = true;
	}
	
	/* Handle frame ready */
	if (status & AV1_INT_FRAME_READY) {
		dev_dbg(dev->dev, "Frame ready interrupt\n");
		/* Signal completion for waiting threads */
		complete(&dev->decode_complete);
		handled = true;
	}
	
	return handled ? IRQ_HANDLED : IRQ_NONE;
}
