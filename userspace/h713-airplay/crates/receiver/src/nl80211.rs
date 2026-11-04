// SPDX-License-Identifier: GPL-3.0-only
//! The SSID of every wireless interface, asked of the kernel when `ctl status` is answered: generic netlink,
//! family "nl80211" (CTRL_CMD_GETFAMILY), then NL80211_CMD_GET_INTERFACE as a dump. The kernel reports
//! NL80211_ATTR_SSID for an access point and for a connected station; GET_INTERFACE has no GENL_ADMIN_PERM
//! ("can be retrieved by unprivileged users", net/wireless/nl80211.c), so the h713-airplay user may ask.

use std::io;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};

const GENL_ID_CTRL: u16 = 16;
const CTRL_CMD_GETFAMILY: u8 = 3;
const CTRL_ATTR_FAMILY_ID: u16 = 1;
const CTRL_ATTR_FAMILY_NAME: u16 = 2;
const NL80211_CMD_GET_INTERFACE: u8 = 5;
const NL80211_ATTR_IFNAME: u16 = 4;
const NL80211_ATTR_IFTYPE: u16 = 5;
const NL80211_ATTR_SSID: u16 = 52;
/// ADHOC, STATION, AP, P2P_CLIENT, P2P_GO: the interface types the kernel reports an SSID for.
const SSID_TYPES: [u32; 5] = [1, 2, 3, 8, 9];
const NLMSG_ERROR: u16 = 2;
const NLMSG_DONE: u16 = 3;
const NLM_F_REQUEST: u16 = 1;
const NLM_F_DUMP: u16 = 0x300;
const HEADER: usize = 16;
const GENL_HEADER: usize = 4;

#[derive(Debug, PartialEq)]
pub struct Iface {
    pub name: String,
    pub iftype: u32,
    pub ssid: Vec<u8>,
}

fn malformed(what: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, format!("nl80211: {what}"))
}

fn align4(n: usize) -> usize {
    (n + 3) & !3
}

/// `(type, payload)` of each netlink attribute; a length that leaves the buffer is an error.
fn attrs(mut b: &[u8]) -> io::Result<Vec<(u16, &[u8])>> {
    let mut out = Vec::new();
    while b.len() >= 4 {
        let len = usize::from(u16::from_ne_bytes([b[0], b[1]]));
        if len < 4 || len > b.len() {
            return Err(malformed("attribute length"));
        }
        out.push((u16::from_ne_bytes([b[2], b[3]]) & 0x3fff, &b[4..len]));
        b = &b[align4(len).min(b.len())..];
    }
    Ok(out)
}

struct Message<'a> {
    kind: u16,
    seq: u32,
    payload: &'a [u8],
}

fn messages(mut b: &[u8]) -> io::Result<Vec<Message<'_>>> {
    let mut out = Vec::new();
    while b.len() >= HEADER {
        let len = u32::from_ne_bytes(b[0..4].try_into().expect("4")) as usize;
        if len < HEADER || len > b.len() {
            return Err(malformed("message length"));
        }
        let kind = u16::from_ne_bytes([b[4], b[5]]);
        let seq = u32::from_ne_bytes(b[8..12].try_into().expect("4"));
        out.push(Message { kind, seq, payload: &b[HEADER..len] });
        b = &b[align4(len).min(b.len())..];
    }
    Ok(out)
}

/// An NLMSG_ERROR's errno (0 is an acknowledgement).
fn errno(payload: &[u8]) -> io::Result<i32> {
    let code: [u8; 4] = payload.get(..4).and_then(|s| s.try_into().ok()).ok_or_else(|| malformed("short error"))?;
    Ok(-i32::from_ne_bytes(code))
}

fn genl_attrs(payload: &[u8]) -> io::Result<Vec<(u16, &[u8])>> {
    attrs(payload.get(GENL_HEADER..).ok_or_else(|| malformed("short generic netlink header"))?)
}

enum Answer<T> {
    Pending,
    Got(T),
}

/// The family id from CTRL_CMD_GETFAMILY's answer; `None` when the kernel has no nl80211 (no Wi-Fi driver).
fn family_answer(buf: &[u8], seq: u32) -> io::Result<Answer<Option<u16>>> {
    for m in messages(buf)?.into_iter().filter(|m| m.seq == seq) {
        match m.kind {
            NLMSG_ERROR => match errno(m.payload)? {
                0 => {}
                libc::ENOENT => return Ok(Answer::Got(None)),
                e => return Err(io::Error::from_raw_os_error(e)),
            },
            GENL_ID_CTRL => {
                let id = genl_attrs(m.payload)?.into_iter().find(|(t, _)| *t == CTRL_ATTR_FAMILY_ID);
                let id = id.and_then(|(_, v)| Some(u16::from_ne_bytes(v.get(..2)?.try_into().ok()?)));
                return id.map(|i| Answer::Got(Some(i))).ok_or_else(|| malformed("family without an id"));
            }
            _ => {}
        }
    }
    Ok(Answer::Pending)
}

/// One received part of the interface dump: the interfaces in it, and whether NLMSG_DONE ended the dump.
fn dump_part(buf: &[u8], seq: u32, family: u16, into: &mut Vec<Iface>) -> io::Result<bool> {
    for m in messages(buf)?.into_iter().filter(|m| m.seq == seq) {
        match m.kind {
            NLMSG_DONE => return Ok(true),
            NLMSG_ERROR => match errno(m.payload)? {
                0 => {}
                e => return Err(io::Error::from_raw_os_error(e)),
            },
            k if k == family => {
                let (mut name, mut iftype, mut ssid) = (None, 0, Vec::new());
                for (t, v) in genl_attrs(m.payload)? {
                    match t {
                        NL80211_ATTR_IFNAME => {
                            name = Some(String::from_utf8_lossy(v.split(|b| *b == 0).next().unwrap_or(v)).into_owned())
                        }
                        NL80211_ATTR_IFTYPE => {
                            iftype = u32::from_ne_bytes(v.get(..4).ok_or_else(|| malformed("iftype"))?.try_into().expect("4"))
                        }
                        NL80211_ATTR_SSID => ssid = v.to_vec(),
                        _ => {}
                    }
                }
                if let Some(name) = name {
                    into.push(Iface { name, iftype, ssid });
                }
            }
            _ => {}
        }
    }
    Ok(false)
}

fn request(seq: u32, kind: u16, flags: u16, cmd: u8, attrs: &[(u16, &[u8])]) -> Vec<u8> {
    let mut m = vec![0u8; HEADER];
    m.extend_from_slice(&[cmd, 1, 0, 0]);
    for (t, v) in attrs {
        m.extend_from_slice(&((4 + v.len()) as u16).to_ne_bytes());
        m.extend_from_slice(&t.to_ne_bytes());
        m.extend_from_slice(v);
        m.resize(align4(m.len()), 0);
    }
    let len = m.len() as u32;
    m[0..4].copy_from_slice(&len.to_ne_bytes());
    m[4..6].copy_from_slice(&kind.to_ne_bytes());
    m[6..8].copy_from_slice(&(NLM_F_REQUEST | flags).to_ne_bytes());
    m[8..12].copy_from_slice(&seq.to_ne_bytes());
    m
}

fn open() -> io::Result<OwnedFd> {
    // SAFETY: plain socket(2); the descriptor is owned by the OwnedFd from here on.
    let fd = unsafe { libc::socket(libc::AF_NETLINK, libc::SOCK_RAW | libc::SOCK_CLOEXEC, libc::NETLINK_GENERIC) };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: fd was just returned by socket(2) and nothing else owns it.
    let fd = unsafe { OwnedFd::from_raw_fd(fd) };
    // SAFETY: a zeroed sockaddr_nl is valid (port 0: the kernel picks one); the size passed is its own.
    let mut addr: libc::sockaddr_nl = unsafe { std::mem::zeroed() };
    addr.nl_family = libc::AF_NETLINK as libc::sa_family_t;
    let size = size_of::<libc::sockaddr_nl>() as libc::socklen_t;
    // SAFETY: addr lives across the call and size is its size.
    if unsafe { libc::bind(fd.as_raw_fd(), (&addr as *const libc::sockaddr_nl).cast(), size) } < 0 {
        return Err(io::Error::last_os_error());
    }
    let timeout = libc::timeval { tv_sec: 1, tv_usec: 0 };
    let tsize = size_of::<libc::timeval>() as libc::socklen_t;
    // SAFETY: timeout lives across the call and tsize is its size; a bound on recv only while a status is built.
    unsafe { libc::setsockopt(fd.as_raw_fd(), libc::SOL_SOCKET, libc::SO_RCVTIMEO, (&timeout as *const libc::timeval).cast(), tsize) };
    Ok(fd)
}

fn send(fd: &OwnedFd, msg: &[u8]) -> io::Result<()> {
    // SAFETY: msg is a live buffer of msg.len() bytes; netlink sends to the kernel without an address.
    if unsafe { libc::send(fd.as_raw_fd(), msg.as_ptr().cast(), msg.len(), 0) } < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

fn recv<'a>(fd: &OwnedFd, buf: &'a mut [u8]) -> io::Result<&'a [u8]> {
    // SAFETY: buf is a live, writable buffer of buf.len() bytes.
    let n = unsafe { libc::recv(fd.as_raw_fd(), buf.as_mut_ptr().cast(), buf.len(), 0) };
    if n < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(&buf[..n as usize])
}

pub fn interfaces() -> io::Result<Vec<Iface>> {
    let fd = open()?;
    let mut buf = vec![0u8; 32 << 10];
    send(&fd, &request(1, GENL_ID_CTRL, 0, CTRL_CMD_GETFAMILY, &[(CTRL_ATTR_FAMILY_NAME, b"nl80211\0")]))?;
    let family = loop {
        if let Answer::Got(f) = family_answer(recv(&fd, &mut buf)?, 1)? {
            break f;
        }
    };
    let Some(family) = family else { return Ok(Vec::new()) };
    send(&fd, &request(2, family, NLM_F_DUMP, NL80211_CMD_GET_INTERFACE, &[]))?;
    let mut out = Vec::new();
    while !dump_part(recv(&fd, &mut buf)?, 2, family, &mut out)? {}
    Ok(out)
}

pub fn ssids() -> Vec<String> {
    match interfaces() {
        Ok(i) => report(i),
        Err(e) => {
            eprintln!("h713-airplay: nl80211: {e}");
            Vec::new()
        }
    }
}

/// `ssid@ifname` for every AP or connected station; an interface without an SSID is left out.
fn report(ifaces: Vec<Iface>) -> Vec<String> {
    let mut out: Vec<String> = ifaces
        .into_iter()
        .filter(|i| !i.ssid.is_empty() && SSID_TYPES.contains(&i.iftype))
        .map(|i| format!("{}@{}", String::from_utf8_lossy(&i.ssid).replace(char::is_whitespace, "_"), i.name))
        .collect();
    out.sort();
    out
}

#[cfg(test)]
#[path = "nl80211_tests.rs"]
mod tests;
