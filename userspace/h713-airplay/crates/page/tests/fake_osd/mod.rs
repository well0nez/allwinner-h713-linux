// SPDX-License-Identifier: GPL-3.0-only
//! A fake h713-osd for the page's tests: the page channel's `page open` with a memfd, and a check of every `page show`.

use std::io::{BufRead, BufReader, Write};
use std::os::fd::AsRawFd;
use std::os::unix::net::UnixStream;
use std::thread::JoinHandle;

use page::canvas::Rect;

/// What the fake h713-osd saw: every line, the rectangles shown, and every broken rule.
#[derive(Debug, Default)]
pub struct Seen {
    pub lines: Vec<String>,
    pub shows: Vec<Rect>,
    pub faults: Vec<String>,
}

/// A fake h713-osd on one end of a socket pair: `page open` answers with a memfd of `pitch` x `h`; each `page show` is
/// checked - its rows wholly opaque, and no pixel changed since the last show outside its rectangle - and answered `ok`.
/// `close_after_last_row`: the connection ends after the show that reaches the canvas' last row.
pub fn fake_osd(server: UnixStream, (w, h): (usize, usize), close_after_last_row: bool) -> JoinHandle<Seen> {
    std::thread::spawn(move || {
        let pitch = w * 4 + 64; // a pitch wider than the row, as a panel's may be
        let mut seen = Seen::default();
        let mut r = BufReader::new(server.try_clone().unwrap());
        let mut line = String::new();
        r.read_line(&mut line).unwrap();
        assert_eq!(line, "page open\n");
        // SAFETY: a new memfd sized and mapped here; the test owns both for its life.
        let (fd, map) = unsafe {
            let fd = libc::memfd_create(c"page".as_ptr(), libc::MFD_CLOEXEC);
            assert!(fd >= 0 && libc::ftruncate(fd, (pitch * h) as libc::off_t) == 0);
            let m = libc::mmap(std::ptr::null_mut(), pitch * h, libc::PROT_READ, libc::MAP_SHARED, fd, 0);
            assert_ne!(m, libc::MAP_FAILED);
            (fd, std::slice::from_raw_parts(m.cast::<u32>(), pitch * h / 4))
        };
        let answer = format!("ok {w} {h} {pitch} argb8888\n");
        let mut iov = libc::iovec { iov_base: answer.as_ptr() as *mut _, iov_len: answer.len() };
        let mut cbuf = [0u64; 8];
        // SAFETY: a msghdr over the buffers above with one SCM_RIGHTS descriptor.
        unsafe {
            let mut msg: libc::msghdr = std::mem::zeroed();
            msg.msg_iov = &mut iov;
            msg.msg_iovlen = 1;
            msg.msg_control = cbuf.as_mut_ptr().cast();
            msg.msg_controllen = libc::CMSG_SPACE(4) as _;
            let cm = libc::CMSG_FIRSTHDR(&msg);
            (*cm).cmsg_level = libc::SOL_SOCKET;
            (*cm).cmsg_type = libc::SCM_RIGHTS;
            (*cm).cmsg_len = libc::CMSG_LEN(4) as _;
            std::ptr::write_unaligned(libc::CMSG_DATA(cm).cast::<i32>(), fd);
            assert!(libc::sendmsg(server.as_raw_fd(), &msg, 0) > 0);
        }
        let stride = pitch / 4;
        let mut last = vec![0u32; stride * h];
        loop {
            line.clear();
            if r.read_line(&mut line).unwrap_or(0) == 0 {
                return seen;
            }
            let l = line.trim_end().to_string();
            seen.lines.push(l.clone());
            let n: Vec<usize> = l.strip_prefix("page show ").map(|s| s.split(' ').map(|v| v.parse().unwrap()).collect()).unwrap_or_default();
            if let [x, y, rw, rh] = n[..] {
                let rect = Rect { x, y, w: rw, h: rh };
                for py in 0..h {
                    for px in 0..w {
                        let (p, inside) = (map[py * stride + px], px >= x && px < x + rw && py >= y && py < y + rh);
                        if inside && p >> 24 != 0xff {
                            seen.faults.push(format!("{rect:?}: pixel {px},{py} is {p:#010x}, not opaque"));
                        }
                        if !inside && p != last[py * stride + px] {
                            seen.faults.push(format!("{rect:?}: pixel {px},{py} changed outside the rectangle shown"));
                        }
                    }
                }
                seen.faults.truncate(8);
                last.copy_from_slice(map);
                seen.shows.push(rect);
                (&server).write_all(b"ok\n").unwrap();
                if close_after_last_row && y + rh == h {
                    return seen;
                }
            } else if l == "page hide" {
                return seen;
            }
        }
    })
}
