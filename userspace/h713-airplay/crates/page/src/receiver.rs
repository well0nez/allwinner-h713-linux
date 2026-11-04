// SPDX-License-Identifier: GPL-3.0-only
//! The receiver, followed without polling: `watch` on its control socket gives every state change, and each one is
//! completed with `status` (the name, the interfaces, the sender). While the socket is not there, an inotify watch on
//! its directory - or on the directory above while systemd has not made `RuntimeDirectory=` yet - wakes the page when it
//! appears; a slow retry (RETRY) covers a socket that was there but refused, and the gap between bind and listen.

use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::ffi::OsStrExt;
use std::path::{Path, PathBuf};
use std::sync::mpsc::Sender;
use std::time::Duration;

use proto::ctl::{self, Status};

use crate::app::Event;

/// The backstop while waiting for the socket.
const RETRY: Duration = Duration::from_secs(5);
/// After the socket appeared: once more this soon, should the receiver not be listening yet.
const SETTLE: Duration = Duration::from_millis(100);

/// An inotify descriptor on the first directory of `socket`'s that exists, for what is created in it.
fn watch_dir(socket: &Path) -> Option<OwnedFd> {
    // SAFETY: inotify_init1 returns a new descriptor or -1.
    let fd = unsafe { libc::inotify_init1(libc::IN_CLOEXEC) };
    if fd < 0 {
        return None;
    }
    // SAFETY: a descriptor just made and owned from here on.
    let fd = unsafe { OwnedFd::from_raw_fd(fd) };
    let dir = socket.ancestors().skip(1).find(|d| d.is_dir())?;
    let mut c = dir.as_os_str().as_bytes().to_vec();
    c.push(0);
    let mask = libc::IN_CREATE | libc::IN_MOVED_TO | libc::IN_ATTRIB | libc::IN_DELETE_SELF;
    // SAFETY: a NUL-terminated path and a valid inotify descriptor.
    (unsafe { libc::inotify_add_watch(fd.as_raw_fd(), c.as_ptr().cast(), mask) } >= 0).then_some(fd)
}

/// Wait for something in the watched directory, at most `RETRY`; true when it was an event.
fn wait(fd: Option<&OwnedFd>) -> bool {
    let Some(fd) = fd else {
        std::thread::sleep(RETRY);
        return false;
    };
    let mut p = libc::pollfd { fd: fd.as_raw_fd(), events: libc::POLLIN, revents: 0 };
    // SAFETY: one pollfd on a descriptor this function borrows.
    unsafe { libc::poll(&mut p, 1, RETRY.as_millis() as libc::c_int) > 0 }
}

/// `status` with the state `watch` just gave (the newer word of the two); the last one known when `status` fails.
fn status_now(path: &Path, state: ctl::State, last: &mut Status) -> Status {
    let st = ctl::request(path, "status", Some(Duration::from_secs(2))).ok().and_then(|t| Status::from_text(&t).ok());
    if let Some(st) = st {
        *last = st;
    }
    Status { state, ..last.clone() }
}

/// Follow the receiver at `path` for ever, on a thread: one [`Event::Receiver`] per state, `None` while it is not there.
pub fn follow(path: PathBuf, events: Sender<Event>) {
    std::thread::spawn(move || {
        let mut said_down = false;
        let mut last = Status::default();
        loop {
            let dir = watch_dir(&path); // first the watch, then the try: a socket that comes in between is not missed
            let mut alive = true;
            let followed = ctl::watch(&path, |state| {
                said_down = false;
                alive = events.send(Event::Receiver(Some(Box::new(status_now(&path, state, &mut last))))).is_ok();
                alive
            });
            if !alive {
                return;
            }
            if !said_down {
                if events.send(Event::Receiver(None)).is_err() {
                    return;
                }
                said_down = true;
            }
            if followed.is_ok() {
                continue; // the receiver closed the watch (it stops): its socket goes or comes back, look again
            }
            if wait(dir.as_ref()) {
                std::thread::sleep(SETTLE);
            }
        }
    });
}
