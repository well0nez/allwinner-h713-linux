// SPDX-License-Identifier: GPL-3.0-only
//! SIGTERM and SIGINT as a file descriptor: blocked in every thread (taken before the first thread starts) and read
//! from a signalfd, so a stop is seen by `poll` while waiting for the connection and by one thread in a session.

use std::io;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};

pub struct Signals(OwnedFd);

impl Signals {
    pub fn block() -> io::Result<Signals> {
        // SAFETY: a zeroed sigset_t is filled by sigemptyset before use; both calls take pointers to locals.
        unsafe {
            let mut set: libc::sigset_t = std::mem::zeroed();
            libc::sigemptyset(&mut set);
            libc::sigaddset(&mut set, libc::SIGTERM);
            libc::sigaddset(&mut set, libc::SIGINT);
            let e = libc::pthread_sigmask(libc::SIG_BLOCK, &set, std::ptr::null_mut());
            if e != 0 {
                return Err(io::Error::from_raw_os_error(e));
            }
            let fd = libc::signalfd(-1, &set, libc::SFD_CLOEXEC);
            if fd < 0 {
                return Err(io::Error::last_os_error());
            }
            Ok(Signals(OwnedFd::from_raw_fd(fd)))
        }
    }

    /// Blocks until SIGTERM or SIGINT; the signal's number.
    pub fn wait(&self) -> io::Result<i32> {
        // SAFETY: signalfd_siginfo is plain data; read fills at most its size.
        let mut info: libc::signalfd_siginfo = unsafe { std::mem::zeroed() };
        let size = std::mem::size_of::<libc::signalfd_siginfo>();
        loop {
            // SAFETY: the buffer is `size` bytes of `info`.
            let n = unsafe { libc::read(self.0.as_raw_fd(), (&mut info as *mut libc::signalfd_siginfo).cast(), size) };
            if n == size as isize {
                return Ok(info.ssi_signo as i32);
            }
            let e = io::Error::last_os_error();
            if n >= 0 || e.kind() != io::ErrorKind::Interrupted {
                return Err(e);
            }
        }
    }
}

impl AsRawFd for Signals {
    fn as_raw_fd(&self) -> RawFd {
        self.0.as_raw_fd()
    }
}
