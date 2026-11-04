// SPDX-License-Identifier: GPL-3.0-only
//! Decoded pictures, and the one slot between the decoder and the presenter: the newest picture wins, an
//! eventfd wakes the presenter's poll.

use crate::sys;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::ptr::NonNull;
use std::sync::Mutex;

/// An AVFrame this side owns; its `pts` is the arrival time of its frame (CLOCK_MONOTONIC, microseconds).
pub struct Frame(NonNull<sys::AVFrame>);

// SAFETY: an AVFrame and its buffers are reference-counted by FFmpeg and may be used and freed on another thread;
// a Frame is owned by one thread at a time.
unsafe impl Send for Frame {}

impl Frame {
    /// # Safety
    /// `f` comes from av_frame_alloc and nothing else frees it.
    pub unsafe fn from_raw(f: NonNull<sys::AVFrame>) -> Frame {
        Frame(f)
    }
    pub fn get(&self) -> &sys::AVFrame {
        // SAFETY: the frame is valid while self lives.
        unsafe { self.0.as_ref() }
    }
    pub fn arrival_us(&self) -> u64 {
        self.get().pts.max(0) as u64
    }
    pub fn is_hw(&self) -> bool {
        self.get().format == sys::AV_PIX_FMT_VAAPI
    }
}

impl Drop for Frame {
    fn drop(&mut self) {
        let mut p = self.0.as_ptr();
        // SAFETY: the frame is ours (from_raw's contract).
        unsafe { sys::av_frame_free(&mut p) };
    }
}

struct Inner {
    frame: Option<Frame>,
    quit: bool,
}

pub struct Slot {
    inner: Mutex<Inner>,
    wake: OwnedFd,
}

impl Slot {
    pub fn new() -> io::Result<Slot> {
        // SAFETY: eventfd returns a new descriptor or -1.
        let fd = unsafe { libc::eventfd(0, libc::EFD_CLOEXEC | libc::EFD_NONBLOCK) };
        if fd < 0 {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: fd is a new descriptor nothing else owns.
        Ok(Slot { inner: Mutex::new(Inner { frame: None, quit: false }), wake: unsafe { OwnedFd::from_raw_fd(fd) } })
    }

    fn lock(&self) -> std::sync::MutexGuard<'_, Inner> {
        self.inner.lock().unwrap_or_else(|e| e.into_inner())
    }

    fn signal(&self) {
        let one = 1u64.to_ne_bytes();
        // SAFETY: an 8-byte write to our eventfd; a full counter (EAGAIN) still leaves it readable.
        unsafe { libc::write(self.wake.as_raw_fd(), one.as_ptr().cast(), 8) };
    }

    /// True when a picture that was never taken was replaced (one more `dropped`).
    pub fn put(&self, f: Frame) -> bool {
        let replaced = self.lock().frame.replace(f).is_some();
        self.signal();
        replaced
    }

    pub fn take(&self) -> Option<Frame> {
        self.lock().frame.take()
    }

    pub fn has_frame(&self) -> bool {
        self.lock().frame.is_some()
    }

    pub fn quit(&self) {
        self.lock().quit = true;
        self.signal();
    }

    pub fn quitting(&self) -> bool {
        self.lock().quit
    }

    pub fn drain(&self) {
        let mut v = [0u8; 8];
        // SAFETY: an 8-byte read from our nonblocking eventfd.
        unsafe { libc::read(self.wake.as_raw_fd(), v.as_mut_ptr().cast(), 8) };
    }

    pub fn wake_fd(&self) -> RawFd {
        self.wake.as_raw_fd()
    }
}
