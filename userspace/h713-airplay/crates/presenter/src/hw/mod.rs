// SPDX-License-Identifier: GPL-3.0-only
//! The board's picture and sound path (aarch64 only): FFmpeg, EGL/GLES, GBM, ALSA through `crate::sys`.

pub mod alsa;
pub mod audio;
pub mod decode;
pub mod export;
pub mod glpath;
pub mod gpu;
pub mod present;
pub mod render;
pub mod session;
pub mod slot;
pub mod wl;
mod wl_dispatch;

use crate::sys;
use std::ffi::{c_int, CStr};

/// CLOCK_MONOTONIC in microseconds: the clock of wp_presentation's timestamps.
pub fn now_us() -> u64 {
    let mut ts = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    // SAFETY: clock_gettime writes one timespec.
    unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut ts) };
    ts.tv_sec as u64 * 1_000_000 + ts.tv_nsec as u64 / 1000
}

pub fn av_error(code: c_int) -> String {
    let mut buf = [0 as std::ffi::c_char; 128];
    // SAFETY: av_strerror writes a NUL-terminated string of at most buf.len() bytes.
    unsafe {
        sys::av_strerror(code, buf.as_mut_ptr(), buf.len());
        CStr::from_ptr(buf.as_ptr()).to_string_lossy().into_owned()
    }
}

#[link(name = "avcodec")]
#[link(name = "avutil")]
#[link(name = "swresample")]
#[link(name = "EGL")]
#[link(name = "GLESv2")]
#[link(name = "gbm")]
#[link(name = "asound")]
extern "C" {}

pub const EAGAIN: c_int = -libc::EAGAIN;
/// AVERROR_EOF, FFERRTAG('E','O','F',' ').
pub const AVERROR_EOF: c_int = -0x2046_4f45;
