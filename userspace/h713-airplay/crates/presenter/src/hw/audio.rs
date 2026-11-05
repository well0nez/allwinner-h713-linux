// SPDX-License-Identifier: GPL-3.0-only
//! The sound: a bounded queue (the oldest frames go past 120 ms), libavcodec (AAC-ELD, AAC-LC, ALAC, PCM),
//! libswresample to S16 48 kHz stereo, a software gain for the AirPlay volume, ALSA (10 ms periods, 60 ms buffer).

use super::alsa::Pcm;
use super::{av_error, AVERROR_EOF, EAGAIN};
use crate::audiocfg;
use crate::stats::{add, Counters};
use crate::sys;
use proto::ipc::AudioCodec;
use std::collections::VecDeque;
use std::ffi::c_int;
use std::ptr;
use std::sync::atomic::Ordering::Relaxed;
use std::sync::{Condvar, Mutex};

const QUEUE_US: u64 = 120_000;
const RATE: u32 = super::alsa::RATE;

pub struct Config {
    pub codec: AudioCodec,
    pub sample_rate: u32,
    pub channels: u8,
    pub frame_len: u32,
    pub config: Vec<u8>,
}

enum Item {
    Config(Config),
    Frame(Vec<u8>, u64),
    Flush,
}

#[derive(Default)]
struct Q {
    items: VecDeque<Item>,
    queued_us: u64,
    frame_us: u64,
    gain: f32,
    quit: bool,
}

pub struct Queue {
    q: Mutex<Q>,
    cv: Condvar,
}

impl Queue {
    pub fn new() -> Queue {
        Queue { q: Mutex::new(Q { gain: 1.0, ..Q::default() }), cv: Condvar::new() }
    }

    fn with<R>(&self, f: impl FnOnce(&mut Q) -> R) -> R {
        let r = f(&mut self.q.lock().unwrap_or_else(|e| e.into_inner()));
        self.cv.notify_one();
        r
    }

    pub fn config(&self, c: Config) {
        self.with(|q| {
            q.frame_us = u64::from(c.frame_len.max(1)) * 1_000_000 / u64::from(c.sample_rate.max(1));
            q.items.push_back(Item::Config(c));
        });
    }

    pub fn frame(&self, data: Vec<u8>, counters: &Counters) {
        self.with(|q| {
            q.items.push_back(Item::Frame(data, q.frame_us));
            q.queued_us += q.frame_us;
            while q.queued_us > QUEUE_US {
                let Some(i) = q.items.iter().position(|i| matches!(i, Item::Frame(..))) else { break };
                if let Some(Item::Frame(_, us)) = q.items.remove(i) {
                    q.queued_us -= us;
                    add(&counters.audio_dropped);
                }
            }
        });
    }

    pub fn flush(&self) {
        self.with(|q| {
            q.items.retain(|i| matches!(i, Item::Config(_)));
            q.queued_us = 0;
            q.items.push_back(Item::Flush);
        });
    }

    pub fn volume(&self, db: f32) {
        self.with(|q| q.gain = audiocfg::gain(db));
    }

    pub fn quit(&self) {
        self.with(|q| q.quit = true);
    }

    fn next(&self) -> Option<(Item, f32, u64)> {
        let mut q = self.q.lock().unwrap_or_else(|e| e.into_inner());
        loop {
            if q.quit {
                return None;
            }
            if let Some(item) = q.items.pop_front() {
                if let Item::Frame(_, us) = item {
                    q.queued_us -= us.min(q.queued_us);
                }
                return Some((item, q.gain, q.queued_us));
            }
            q = self.cv.wait(q).unwrap_or_else(|e| e.into_inner());
        }
    }
}

struct Decoder {
    ctx: *mut sys::AVCodecContext,
    pkt: *mut sys::AVPacket,
    frame: *mut sys::AVFrame,
    swr: *mut sys::SwrContext,
    swr_in: (c_int, c_int, c_int),
    out: Vec<i16>,
}

impl Decoder {
    fn open(c: &Config) -> Result<Decoder, String> {
        let id = match c.codec {
            AudioCodec::AacEld | AudioCodec::AacLc => sys::AV_CODEC_ID_AAC,
            AudioCodec::Alac => sys::AV_CODEC_ID_ALAC,
            AudioCodec::Pcm => sys::AV_CODEC_ID_PCM_S16BE,
        };
        let extra = audiocfg::extradata(c.codec, &c.config, c.sample_rate, c.channels, c.frame_len);
        // SAFETY: FFmpeg setup; extradata is av_mallocz'd with the padding FFmpeg reads past its end; Drop frees all.
        unsafe {
            let codec = sys::avcodec_find_decoder(id);
            let d = Decoder { ctx: sys::avcodec_alloc_context3(codec), pkt: sys::av_packet_alloc(), frame: sys::av_frame_alloc(), swr: ptr::null_mut(), swr_in: (0, 0, 0), out: Vec::new() };
            if codec.is_null() || d.ctx.is_null() || d.pkt.is_null() || d.frame.is_null() {
                return Err(format!("no {:?} decoder", c.codec));
            }
            (*d.ctx).sample_rate = c.sample_rate as c_int;
            sys::av_channel_layout_default(&mut (*d.ctx).ch_layout, c_int::from(c.channels.max(1)));
            if !extra.is_empty() {
                let x = sys::av_mallocz(extra.len() + sys::AV_INPUT_BUFFER_PADDING_SIZE as usize).cast::<u8>();
                ptr::copy_nonoverlapping(extra.as_ptr(), x, extra.len());
                (*d.ctx).extradata = x;
                (*d.ctx).extradata_size = extra.len() as c_int;
            }
            let r = sys::avcodec_open2(d.ctx, codec, ptr::null_mut());
            if r < 0 {
                return Err(format!("opening the {:?} decoder: {}", c.codec, av_error(r)));
            }
            Ok(d)
        }
    }

    /// Decodes one packet into S16 48 kHz stereo with the gain applied, handed to `play`.
    fn decode(&mut self, data: &[u8], g: f32, play: &mut dyn FnMut(&[i16])) -> Result<(), String> {
        // SAFETY: our context, packet and frame; swr_convert writes at most `cap` frames into `out`.
        unsafe {
            if sys::av_new_packet(self.pkt, data.len() as c_int) < 0 {
                return Err("out of memory".into());
            }
            ptr::copy_nonoverlapping(data.as_ptr(), (*self.pkt).data, data.len());
            let r = sys::avcodec_send_packet(self.ctx, self.pkt);
            sys::av_packet_unref(self.pkt);
            if r < 0 {
                return Err(av_error(r));
            }
            loop {
                let r = sys::avcodec_receive_frame(self.ctx, self.frame);
                if r == EAGAIN || r == AVERROR_EOF {
                    return Ok(());
                }
                if r < 0 {
                    return Err(av_error(r));
                }
                let f = &*self.frame;
                let input = (f.format, f.sample_rate, f.ch_layout.nb_channels);
                if self.swr.is_null() || self.swr_in != input {
                    sys::swr_free(&mut self.swr);
                    let mut out_layout = std::mem::zeroed();
                    sys::av_channel_layout_default(&mut out_layout, 2);
                    let r = sys::swr_alloc_set_opts2(&mut self.swr, &out_layout, sys::AV_SAMPLE_FMT_S16, RATE as c_int, &f.ch_layout, f.format, f.sample_rate, 0, ptr::null_mut());
                    if r < 0 || sys::swr_init(self.swr) < 0 {
                        sys::swr_free(&mut self.swr);
                        return Err("libswresample refused the conversion".into());
                    }
                    self.swr_in = input;
                }
                let cap = sys::swr_get_out_samples(self.swr, f.nb_samples).max(0) as usize;
                self.out.resize(cap * 2, 0);
                let dst = self.out.as_mut_ptr().cast::<u8>();
                let n = sys::swr_convert(self.swr, &dst, cap as c_int, f.extended_data as *const *const u8, f.nb_samples);
                sys::av_frame_unref(self.frame);
                let samples = &mut self.out[..n.max(0) as usize * 2];
                if g < 1.0 {
                    samples.iter_mut().for_each(|s| *s = (f32::from(*s) * g) as i16);
                }
                play(samples);
            }
        }
    }
}

impl Drop for Decoder {
    fn drop(&mut self) {
        // SAFETY: ours; the free functions take null.
        unsafe {
            sys::swr_free(&mut self.swr);
            sys::av_frame_free(&mut self.frame);
            sys::av_packet_free(&mut self.pkt);
            sys::avcodec_free_context(&mut self.ctx);
        }
    }
}

pub fn run(queue: &Queue, device: &str, counters: &Counters) {
    let (mut dec, mut pcm): (Option<Decoder>, Option<Pcm>) = (None, None);
    while let Some((item, g, queued_us)) = queue.next() {
        match item {
            Item::Config(c) => {
                dec = Decoder::open(&c).inspect_err(|e| eprintln!("h713-airplay-show: sound: {e}")).ok();
                if pcm.is_none() {
                    pcm = Pcm::open(device).inspect_err(|e| eprintln!("h713-airplay-show: {e}")).ok();
                }
            }
            Item::Frame(data, _) => {
                let (Some(d), Some(p)) = (dec.as_mut(), pcm.as_mut()) else { continue };
                match d.decode(&data, g, &mut |s| p.write(s, counters)) {
                    Ok(()) => add(&counters.audio_frames),
                    Err(_) => add(&counters.audio_dropped),
                }
                counters.audio_delay_ms.store(p.delay_ms() + (queued_us / 1000) as u32, Relaxed);
            }
            Item::Flush => pcm.iter_mut().for_each(Pcm::drop_queued),
        }
    }
}
