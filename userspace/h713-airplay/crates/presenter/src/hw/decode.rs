// SPDX-License-Identifier: GPL-3.0-only
//! The video decoder: FFmpeg's H.264/HEVC decoder with the VAAPI hwaccel on the render node (libva-v4l2-request,
//! cedrus), low delay, no frame threads; the software decoder when VAAPI is not there or refuses the stream.

use super::slot::Frame;
use super::{av_error, AVERROR_EOF, EAGAIN};
use crate::annexb::lengths_to_start_codes;
use crate::paramsets;
use crate::sys;
use proto::ipc::VideoCodec;
use std::ffi::c_int;
use std::ptr::{self, NonNull};

pub const RENDER_NODE: &std::ffi::CStr = c"/dev/dri/renderD128";

pub struct HwDevice(*mut sys::AVBufferRef);

// SAFETY: a hw device context is reference-counted and thread-safe in FFmpeg; this handle is only unref'd once.
unsafe impl Send for HwDevice {}

impl HwDevice {
    pub fn open() -> Result<HwDevice, String> {
        let mut dev = ptr::null_mut();
        // SAFETY: dev receives a new reference or stays null.
        let r = unsafe { sys::av_hwdevice_ctx_create(&mut dev, sys::AV_HWDEVICE_TYPE_VAAPI, RENDER_NODE.as_ptr(), ptr::null_mut(), 0) };
        if r < 0 {
            return Err(format!("VAAPI on {}: {}", RENDER_NODE.to_string_lossy(), av_error(r)));
        }
        Ok(HwDevice(dev))
    }
}

impl Drop for HwDevice {
    fn drop(&mut self) {
        // SAFETY: our one reference.
        unsafe { sys::av_buffer_unref(&mut self.0) };
    }
}

unsafe extern "C" fn get_format(ctx: *mut sys::AVCodecContext, fmts: *const sys::AVPixelFormat) -> sys::AVPixelFormat {
    // SAFETY: FFmpeg passes its context and a list ending in AV_PIX_FMT_NONE.
    unsafe {
        if !(*ctx).hw_device_ctx.is_null() {
            let mut p = fmts;
            while *p != sys::AV_PIX_FMT_NONE {
                if *p == sys::AV_PIX_FMT_VAAPI {
                    return sys::AV_PIX_FMT_VAAPI;
                }
                p = p.add(1);
            }
        }
        sys::avcodec_default_get_format(ctx, fmts)
    }
}

pub struct Decoder {
    ctx: *mut sys::AVCodecContext,
    pkt: *mut sys::AVPacket,
    codec: VideoCodec,
    record: Vec<u8>,
    params: Vec<u8>,
    first: bool,
}

// SAFETY: the decoder is created, used and freed by one thread at a time (the decoder thread).
unsafe impl Send for Decoder {}

impl Decoder {
    pub fn open(codec: VideoCodec, record: &[u8], hw: Option<&HwDevice>) -> Result<Decoder, String> {
        let sets = paramsets::parse(codec, record).map_err(|e| e.to_string())?;
        let id = match codec {
            VideoCodec::H264 => sys::AV_CODEC_ID_H264,
            VideoCodec::H265 => sys::AV_CODEC_ID_HEVC,
        };
        // SAFETY: plain FFmpeg setup; every pointer checked before use, freed in Drop.
        unsafe {
            let c = sys::avcodec_find_decoder(id);
            if c.is_null() {
                return Err(format!("no {codec:?} decoder in libavcodec"));
            }
            let ctx = sys::avcodec_alloc_context3(c);
            let pkt = sys::av_packet_alloc();
            let mut dec = Decoder { ctx, pkt, codec, record: record.to_vec(), params: paramsets::annexb(&sets), first: true };
            if ctx.is_null() || pkt.is_null() {
                return Err("out of memory".into());
            }
            (*ctx).flags |= sys::AV_CODEC_FLAG_LOW_DELAY as c_int;
            (*ctx).get_format = Some(get_format);
            match hw {
                Some(dev) => {
                    (*ctx).hw_device_ctx = sys::av_buffer_ref(dev.0);
                    (*ctx).extra_hw_frames = 6;
                    (*ctx).thread_count = 1;
                }
                None => {
                    (*ctx).thread_type = sys::FF_THREAD_SLICE as c_int;
                    (*ctx).thread_count = 0;
                }
            }
            let r = sys::avcodec_open2(ctx, c, ptr::null_mut());
            if r < 0 {
                return Err(format!("opening the {codec:?} decoder: {}", av_error(r)));
            }
            dec.first = true;
            Ok(dec)
        }
    }

    pub fn is_for(&self, codec: VideoCodec, record: &[u8]) -> bool {
        self.codec == codec && self.record == record
    }

    /// Decodes one frame of the mirror stream (4-byte lengths); every picture it completes goes to `out`.
    pub fn decode(&mut self, mut data: Vec<u8>, keyframe: bool, arrival_us: u64, out: &mut dyn FnMut(Frame)) -> Result<(), String> {
        let framed = lengths_to_start_codes(self.codec, &mut data).map_err(|e| format!("a NAL length at byte {} runs past the frame", e.at))?;
        let prefix: &[u8] = if keyframe || framed.random_access || self.first { &self.params } else { &[] };
        self.first = false;
        // SAFETY: pkt and ctx are ours; av_new_packet gives size bytes plus zeroed padding.
        unsafe {
            let r = sys::av_new_packet(self.pkt, (prefix.len() + data.len()) as c_int);
            if r < 0 {
                return Err(av_error(r));
            }
            let dst = std::slice::from_raw_parts_mut((*self.pkt).data, prefix.len() + data.len());
            dst[..prefix.len()].copy_from_slice(prefix);
            dst[prefix.len()..].copy_from_slice(&data);
            (*self.pkt).pts = arrival_us as i64;
            if keyframe || framed.random_access {
                (*self.pkt).flags |= sys::AV_PKT_FLAG_KEY as c_int;
            }
            let mut sent = sys::avcodec_send_packet(self.ctx, self.pkt);
            if sent == EAGAIN {
                self.receive(out)?;
                sent = sys::avcodec_send_packet(self.ctx, self.pkt);
            }
            sys::av_packet_unref(self.pkt);
            let received = self.receive(out);
            if sent < 0 {
                return Err(format!("decoding: {}", av_error(sent)));
            }
            received
        }
    }

    fn receive(&mut self, out: &mut dyn FnMut(Frame)) -> Result<(), String> {
        loop {
            // SAFETY: a new frame, handed to Frame (which frees it) or freed here.
            unsafe {
                let Some(f) = NonNull::new(sys::av_frame_alloc()) else { return Err("out of memory".into()) };
                let r = sys::avcodec_receive_frame(self.ctx, f.as_ptr());
                if r < 0 {
                    drop(Frame::from_raw(f));
                    return if r == EAGAIN || r == AVERROR_EOF { Ok(()) } else { Err(format!("decoding: {}", av_error(r))) };
                }
                out(Frame::from_raw(f));
            }
        }
    }
}

impl Drop for Decoder {
    fn drop(&mut self) {
        // SAFETY: both are ours; the free functions take null too.
        unsafe {
            sys::av_packet_free(&mut self.pkt);
            sys::avcodec_free_context(&mut self.ctx);
        }
    }
}
