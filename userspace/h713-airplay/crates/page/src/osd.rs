// SPDX-License-Identifier: GPL-3.0-only
//! h713-osd's page channel (docs/tools/h713-osd.md, "The page channel"; h713-settings' page.c): `page open` answers
//! `ok W H PITCH argb8888` with one memfd (SCM_RIGHTS) the page maps and draws into, `page show X Y W H` says which
//! rectangle is new and is answered after the refresh. The connection is the page's life.

use std::io::{self, BufRead, BufReader, Write};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::sync::mpsc::Sender;
use std::time::Duration;

use crate::app::{Event, Shown, Wall};
use crate::canvas::{Canvas, Rect};

pub enum OpenError {
    /// h713-osd is not there or does not answer.
    Absent(String),
    /// `ok unseen` (nothing can be seen) or an error: no page.
    Refused(String),
}

pub struct OsdLink {
    sock: UnixStream,
    answers: BufReader<UnixStream>,
    map: *mut u32,
    words: usize,
    w: usize,
    h: usize,
    stride: usize,
}

/// One line and the descriptor that came with it.
fn recv_with_fd(sock: &UnixStream) -> io::Result<(String, Option<OwnedFd>)> {
    let mut line = [0u8; 160];
    let mut cbuf = [0u64; 8]; // CMSG_SPACE(sizeof(int)), aligned for cmsghdr
    let mut iov = libc::iovec { iov_base: line.as_mut_ptr().cast(), iov_len: line.len() };
    // SAFETY: msghdr is plain data; every pointer in it refers to the buffers above, which outlive the call.
    let mut msg: libc::msghdr = unsafe { std::mem::zeroed() };
    msg.msg_iov = &mut iov;
    msg.msg_iovlen = 1;
    msg.msg_control = cbuf.as_mut_ptr().cast();
    msg.msg_controllen = std::mem::size_of_val(&cbuf) as _;
    // SAFETY: a valid socket and the msghdr set up above.
    let got = unsafe { libc::recvmsg(sock.as_raw_fd(), &mut msg, libc::MSG_CMSG_CLOEXEC) };
    if got <= 0 {
        return Err(if got == 0 { io::ErrorKind::UnexpectedEof.into() } else { io::Error::last_os_error() });
    }
    let mut fd = None;
    // SAFETY: the CMSG_* walk stays within msg_control as the kernel filled it in.
    unsafe {
        let mut cm = libc::CMSG_FIRSTHDR(&msg);
        while !cm.is_null() {
            if (*cm).cmsg_level == libc::SOL_SOCKET && (*cm).cmsg_type == libc::SCM_RIGHTS {
                let raw: RawFd = std::ptr::read_unaligned(libc::CMSG_DATA(cm).cast());
                fd = Some(OwnedFd::from_raw_fd(raw));
            }
            cm = libc::CMSG_NXTHDR(&msg, cm);
        }
    }
    Ok((String::from_utf8_lossy(&line[..got as usize]).into_owned(), fd))
}

impl OsdLink {
    /// `page open` on h713-osd's control socket.
    pub fn open(path: &Path, events: Sender<Event>) -> Result<OsdLink, OpenError> {
        let sock = UnixStream::connect(path)
            .map_err(|e| OpenError::Absent(format!("{}: {e} -- is h713-osd running?", path.display())))?;
        OsdLink::over(sock, events)
    }

    /// `page open` over a connected stream (the tests' fake h713-osd); a thread reports the connection's end as
    /// [`Event::OsdGone`].
    pub fn over(mut sock: UnixStream, events: Sender<Event>) -> Result<OsdLink, OpenError> {
        let absent = |e: io::Error| OpenError::Absent(format!("\"page open\" got no answer: {e}"));
        sock.set_read_timeout(Some(Duration::from_secs(3))).map_err(absent)?;
        sock.write_all(b"page open\n").map_err(absent)?;
        let (line, fd) = recv_with_fd(&sock).map_err(absent)?;
        let line = line.trim_end().to_string();
        let words: Vec<&str> = line.split_whitespace().collect();
        let (w, h, pitch) = match (words.as_slice(), fd.as_ref()) {
            (["ok", w, h, p, "argb8888"], Some(_)) => match (w.parse::<usize>(), h.parse::<usize>(), p.parse::<usize>()) {
                (Ok(w), Ok(h), Ok(p)) if p >= w * 4 && w > 0 && h > 0 => (w, h, p),
                _ => return Err(OpenError::Refused(line)),
            },
            _ => return Err(OpenError::Refused(line)),
        };
        let fd = fd.ok_or_else(|| OpenError::Refused(line.clone()))?;
        let len = pitch * h;
        // SAFETY: mapping the memfd h713-osd sized to PITCH x H; the mapping lives until Drop unmaps it.
        let map = unsafe {
            libc::mmap(std::ptr::null_mut(), len, libc::PROT_READ | libc::PROT_WRITE, libc::MAP_SHARED, fd.as_raw_fd(), 0)
        };
        if map == libc::MAP_FAILED {
            return Err(OpenError::Refused(format!("mapping the canvas: {}", io::Error::last_os_error())));
        }
        let answers = sock.try_clone().map(BufReader::new);
        let watch = sock.try_clone();
        let link = OsdLink { sock, answers: answers.map_err(absent)?, map: map.cast(), words: len / 4, w, h, stride: pitch / 4 };
        let watch = watch.map_err(absent)?;
        std::thread::spawn(move || {
            let mut p = libc::pollfd { fd: watch.as_raw_fd(), events: libc::POLLRDHUP, revents: 0 };
            // SAFETY: one pollfd on a socket this thread owns. Only the hang-up is asked for: the answers are not ours to read.
            while unsafe { libc::poll(&mut p, 1, -1) } < 0 && io::Error::last_os_error().kind() == io::ErrorKind::Interrupted {}
            let _ = events.send(Event::OsdGone);
        });
        Ok(link)
    }

    fn line(&mut self, s: &str) -> io::Result<()> {
        (&self.sock).write_all(s.as_bytes())
    }
}

impl Wall for OsdLink {
    fn canvas(&mut self) -> Canvas<'_> {
        // SAFETY: the mapping is `words` u32 long and only this link writes it while it is borrowed mutably.
        let px = unsafe { std::slice::from_raw_parts_mut(self.map, self.words) };
        Canvas { px, w: self.w, h: self.h, stride: self.stride }
    }

    fn show(&mut self, r: Rect) -> Result<Shown, String> {
        self.line(&format!("page show {} {} {} {}\n", r.x, r.y, r.w, r.h)).map_err(|e| e.to_string())?;
        let mut answer = String::new();
        match self.answers.read_line(&mut answer) {
            Ok(0) => return Err("the connection ended".into()),
            Ok(_) => {}
            Err(e) => return Err(e.to_string()),
        }
        match answer.trim_end() {
            "ok" => Ok(Shown::OnTheWall),
            a if a.starts_with("ok waiting") || a.starts_with("ok unseen") => Ok(Shown::Kept),
            a => Err(format!("answers {a:?}")),
        }
    }

    fn hide(&mut self) {
        let _ = self.line("page hide\n");
    }

    fn handover(&mut self) {
        let _ = self.line("page handover\n");
    }
}

impl Drop for OsdLink {
    fn drop(&mut self) {
        // the end of the connection for every clone (the watch thread holds one), so h713-osd takes the page at once
        let _ = self.sock.shutdown(std::net::Shutdown::Both);
        // SAFETY: the mapping made in `over`, unmapped once.
        unsafe { libc::munmap(self.map.cast(), self.words * 4) };
    }
}
