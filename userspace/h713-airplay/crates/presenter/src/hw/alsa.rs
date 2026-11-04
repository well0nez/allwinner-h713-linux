// SPDX-License-Identifier: GPL-3.0-only
//! The ALSA playback device: S16_LE, two channels, 48 kHz (all the DSP bridge takes), ~10 ms periods, ~60 ms
//! buffer, started half full; an underrun is counted and the device prepared again.

use crate::stats::{add, Counters};
use crate::sys;
use std::ffi::{c_int, CStr, CString};
use std::ptr;

pub const RATE: u32 = 48_000;

pub struct Pcm(*mut sys::snd_pcm_t);

impl Pcm {
    pub fn open(device: &str) -> Result<Pcm, String> {
        let name = CString::new(device).map_err(|_| "a device name with a NUL")?;
        // SAFETY: snd_strerror returns a static NUL-terminated string.
        let fail = |what: &str, r: c_int| format!("ALSA {device}: {what}: {}", unsafe { CStr::from_ptr(sys::snd_strerror(r)) }.to_string_lossy());
        // SAFETY: ALSA calls on our handle and parameter blocks, each freed before returning.
        unsafe {
            let mut p = Pcm(ptr::null_mut());
            let r = sys::snd_pcm_open(&mut p.0, name.as_ptr(), sys::SND_PCM_STREAM_PLAYBACK, 0);
            if r < 0 {
                return Err(fail("open", r));
            }
            let mut hw = ptr::null_mut();
            sys::snd_pcm_hw_params_malloc(&mut hw);
            let (mut rate, mut period, mut buffer) = (RATE, 10_000u32, 60_000u32);
            let mut r = sys::snd_pcm_hw_params_any(p.0, hw);
            r = r.min(sys::snd_pcm_hw_params_set_access(p.0, hw, sys::SND_PCM_ACCESS_RW_INTERLEAVED));
            r = r.min(sys::snd_pcm_hw_params_set_format(p.0, hw, sys::SND_PCM_FORMAT_S16_LE));
            r = r.min(sys::snd_pcm_hw_params_set_channels(p.0, hw, 2));
            r = r.min(sys::snd_pcm_hw_params_set_rate_near(p.0, hw, &mut rate, ptr::null_mut()));
            r = r.min(sys::snd_pcm_hw_params_set_period_time_near(p.0, hw, &mut period, ptr::null_mut()));
            r = r.min(sys::snd_pcm_hw_params_set_buffer_time_near(p.0, hw, &mut buffer, ptr::null_mut()));
            r = r.min(sys::snd_pcm_hw_params(p.0, hw));
            let (mut frames, mut pframes) = (0, 0);
            sys::snd_pcm_hw_params_get_buffer_size(hw, &mut frames);
            sys::snd_pcm_hw_params_get_period_size(hw, &mut pframes, ptr::null_mut());
            sys::snd_pcm_hw_params_free(hw);
            if r < 0 {
                return Err(fail("S16_LE 2 ch 48000 Hz", r));
            }
            let mut sw = ptr::null_mut();
            sys::snd_pcm_sw_params_malloc(&mut sw);
            sys::snd_pcm_sw_params_current(p.0, sw);
            sys::snd_pcm_sw_params_set_start_threshold(p.0, sw, frames / 2);
            sys::snd_pcm_sw_params_set_avail_min(p.0, sw, pframes);
            let r = sys::snd_pcm_sw_params(p.0, sw);
            sys::snd_pcm_sw_params_free(sw);
            if r < 0 {
                return Err(fail("software parameters", r));
            }
            eprintln!("h713-airplay-show: ALSA {device}: {rate} Hz, period {pframes} frames, buffer {frames} frames");
            Ok(p)
        }
    }

    pub fn write(&mut self, s: &[i16], counters: &Counters) {
        let mut at = 0;
        while at < s.len() {
            // SAFETY: (len - at) / 2 interleaved stereo frames from `s`.
            let n = unsafe { sys::snd_pcm_writei(self.0, s[at..].as_ptr().cast(), ((s.len() - at) / 2) as _) };
            match n {
                n if n >= 0 => at += n as usize * 2,
                n if n == -(libc::EPIPE as sys::snd_pcm_sframes_t) => {
                    add(&counters.audio_underruns);
                    // SAFETY: our handle.
                    unsafe { sys::snd_pcm_prepare(self.0) };
                }
                // SAFETY: our handle; recover handles EINTR and ESTRPIPE, anything else drops this packet.
                n => unsafe {
                    if sys::snd_pcm_recover(self.0, n as c_int, 1) < 0 {
                        return;
                    }
                },
            }
        }
    }

    pub fn delay_ms(&self) -> u32 {
        let mut d = 0;
        // SAFETY: our handle.
        if unsafe { sys::snd_pcm_delay(self.0, &mut d) } < 0 {
            return 0;
        }
        (d.max(0) as u64 * 1000 / u64::from(RATE)) as u32
    }

    pub fn drop_queued(&mut self) {
        // SAFETY: our handle.
        unsafe {
            sys::snd_pcm_drop(self.0);
            sys::snd_pcm_prepare(self.0);
        }
    }
}

impl Drop for Pcm {
    fn drop(&mut self) {
        if !self.0.is_null() {
            // SAFETY: ours, closed once.
            unsafe {
                sys::snd_pcm_drop(self.0);
                sys::snd_pcm_close(self.0);
            }
        }
    }
}

