// SPDX-License-Identifier: GPL-3.0-only
//! The one connection of a session: accepted on systemd's listening socket or on `--listen PATH`, within 3 s.

use std::io;
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::Path;
use std::time::Duration;

pub const ACCEPT_WITHIN: Duration = Duration::from_secs(3);
const SD_LISTEN_FDS_START: i32 = 3;

/// `Ok(None)`: nobody connected in time, or a stop signal came first (`stop` readable).
pub fn accept_within(listener: &UnixListener, within: Duration, stop: &impl AsRawFd) -> io::Result<Option<UnixStream>> {
    let mut pfd = [
        libc::pollfd { fd: listener.as_raw_fd(), events: libc::POLLIN, revents: 0 },
        libc::pollfd { fd: stop.as_raw_fd(), events: libc::POLLIN, revents: 0 },
    ];
    let ms = i32::try_from(within.as_millis()).unwrap_or(i32::MAX);
    loop {
        // SAFETY: two valid pollfds for the duration of the call.
        match unsafe { libc::poll(pfd.as_mut_ptr(), 2, ms) } {
            0 => return Ok(None),
            _ if pfd[1].revents != 0 => return Ok(None),
            n if n > 0 => return listener.accept().map(|(s, _)| Some(s)),
            _ => {
                let e = io::Error::last_os_error();
                if e.kind() != io::ErrorKind::Interrupted {
                    return Err(e);
                }
            }
        }
    }
}

/// systemd's listening socket, fd 3. The variables go, so nothing started from here takes it for its own.
pub fn activated() -> io::Result<UnixListener> {
    std::env::remove_var("LISTEN_FDS");
    std::env::remove_var("LISTEN_PID");
    std::env::remove_var("LISTEN_FDNAMES");
    // SAFETY: LISTEN_FDS=1 for this pid (args::parse checked) hands fd 3 to this process; nothing else owns it.
    let listener = unsafe { UnixListener::from_raw_fd(SD_LISTEN_FDS_START) };
    // SAFETY: fcntl on an fd this process owns.
    if unsafe { libc::fcntl(SD_LISTEN_FDS_START, libc::F_SETFD, libc::FD_CLOEXEC) } < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(listener)
}

pub fn listen(path: &Path) -> io::Result<UnixListener> {
    match std::fs::remove_file(path) {
        Err(e) if e.kind() != io::ErrorKind::NotFound => return Err(e),
        _ => {}
    }
    UnixListener::bind(path)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_waiting_client_is_accepted_and_silence_is_none() {
        let dir = std::env::temp_dir().join(format!("h713-show-conn-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("s");
        let l = listen(&path).unwrap();
        let (quiet, loud) = UnixStream::pair().unwrap();
        assert!(accept_within(&l, Duration::from_millis(0), &quiet).unwrap().is_none());
        let _client = UnixStream::connect(&path).unwrap();
        assert!(accept_within(&l, Duration::from_secs(1), &quiet).unwrap().is_some());
        let _second = UnixStream::connect(&path).unwrap();
        std::io::Write::write_all(&mut &loud, b"x").unwrap();
        assert!(accept_within(&l, Duration::from_secs(1), &quiet).unwrap().is_none(), "a stop goes before a client");
        let again = listen(&path).unwrap();
        drop(again);
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
