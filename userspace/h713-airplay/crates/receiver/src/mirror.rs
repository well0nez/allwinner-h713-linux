// SPDX-License-Identifier: GPL-3.0-only
//! The mirror stream (raop_rtp_mirror.c L300-600): TCP, a 128-byte header per packet, then the payload.
//! Header: [0..4] payload size LE, [4..6] type, [6..8] option, [8..16] NTP timestamp; codec packets carry the
//! picture size as LE floats at 56/60 (40/44 and 16/20 as fallbacks).

use crate::crypto::{self, Ctr};
use crate::presenter::Link;
use crate::shared::{Counters, Shared};
use proto::ipc::{Msg, VideoCodec};
use std::io::{self, Read};
use std::net::{Shutdown, TcpListener, TcpStream};
use std::sync::atomic::Ordering;
use std::sync::Arc;

const MAX_PAYLOAD: usize = proto::ipc::MAX_FRAME - 64;

pub fn accept_loop(sh: Arc<Shared>, listener: TcpListener) {
    for (serial, stream) in (1u64..).zip(listener.incoming()) {
        let Ok(stream) = stream else { continue };
        let Ok(from) = stream.peer_addr() else { continue };
        crate::net::keepalive(&stream);
        let attached = {
            let mut inner = sh.lock();
            inner.session.as_mut().filter(|s| s.peer == from.ip()).and_then(|s| {
                let m = s.mirror.as_mut()?;
                let keys = s.keys?;
                if let Some(old) = m.conn.replace(stream.try_clone().ok()?) {
                    let _ = old.shutdown(Shutdown::Both);
                }
                m.serial = serial;
                Some((s.id, crypto::mirror_cipher(&keys.key, m.stream_id), s.link.clone(), s.counters.clone()))
            })
        };
        let Some((sid, cipher, link, counters)) = attached else {
            eprintln!("h713-airplay: mirror connection from {from} refused: no mirror stream set up");
            continue;
        };
        let sh = sh.clone();
        let spawned = std::thread::Builder::new().name("mirror".into()).spawn(move || {
            let reason = match read_loop(&sh, sid, stream, cipher, link, &counters) {
                Ok(()) => "mirror stream closed".to_string(),
                Err(e) => format!("mirror stream: {e}"),
            };
            let ending = sh.lock().session.as_ref().and_then(|s| {
                let mine = s.id == sid && s.mirror.as_ref().is_some_and(|m| m.serial == serial && m.conn.is_some());
                mine.then(|| s.ending.map_or(reason.clone(), str::to_string))
            });
            if let Some(reason) = ending {
                sh.end(sid, &reason);
            }
        });
        if let Err(e) = spawned {
            eprintln!("h713-airplay: mirror thread: {e}");
        }
    }
}

fn f32_at(h: &[u8; 128], at: usize) -> u32 {
    let v = f32::from_le_bytes(h[at..at + 4].try_into().expect("4"));
    if v.is_finite() && v > 0.0 && v < 65536.0 {
        v as u32
    } else {
        0
    }
}

fn picture_size(h: &[u8; 128]) -> (u32, u32) {
    [56, 40, 16].iter().map(|&at| (f32_at(h, at), f32_at(h, at + 4))).find(|(w, hh)| *w > 0 && *hh > 0).unwrap_or((0, 0))
}

fn read_full(stream: &mut TcpStream, buf: &mut [u8]) -> io::Result<bool> {
    let mut got = 0;
    while got < buf.len() {
        match stream.read(&mut buf[got..]) {
            Ok(0) if got == 0 => return Ok(false),
            Ok(0) => return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "cut inside a packet")),
            Ok(n) => got += n,
            Err(e) if e.kind() == io::ErrorKind::Interrupted => {}
            Err(e) => return Err(e),
        }
    }
    Ok(true)
}

fn read_loop(
    sh: &Shared,
    sid: u64,
    mut stream: TcpStream,
    mut cipher: Ctr,
    mut link: Option<Arc<Link>>,
    counters: &Counters,
) -> io::Result<()> {
    let mut header = [0u8; 128];
    let mut asleep = false;
    loop {
        if !read_full(&mut stream, &mut header)? {
            return Ok(());
        }
        let size = u32::from_le_bytes(header[0..4].try_into().expect("4")) as usize;
        if size > MAX_PAYLOAD {
            return Err(io::Error::new(io::ErrorKind::InvalidData, format!("payload of {size} bytes")));
        }
        let mut payload = vec![0u8; size];
        if size > 0 && !read_full(&mut stream, &mut payload)? {
            return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "cut before the payload"));
        }
        if link.is_none() {
            link = sh.lock().session.as_ref().filter(|s| s.id == sid).and_then(|s| s.link.clone());
        }
        match header[4] {
            0x00 => {
                crypto::mirror_decrypt(&mut cipher, &mut payload);
                counters.video_frames.fetch_add(1, Ordering::Relaxed);
                counters.video_bytes.fetch_add(size as u64, Ordering::Relaxed);
                let keyframe = header[5] & 0x10 != 0;
                let ntp = u64::from_le_bytes(header[8..16].try_into().expect("8"));
                if let Some(l) = &link {
                    l.push_video(Msg::VideoFrame { ntp, keyframe, data: payload }, keyframe);
                }
            }
            0x01 => {
                let (codec, name) = match header[6] {
                    0x1e | 0x5e => (VideoCodec::H265, "h265"),
                    _ => (VideoCodec::H264, "h264"),
                };
                let sleeping = matches!(header[6], 0x56 | 0x5e);
                if sleeping != asleep {
                    asleep = sleeping;
                    eprintln!("h713-airplay: session {sid} sender {}", if asleep { "paused its screen" } else { "resumed" });
                }
                if asleep || payload.is_empty() {
                    continue;
                }
                let (width, height) = picture_size(&header);
                if let Some(s) = sh.lock().session.as_mut().filter(|s| s.id == sid) {
                    let format = format!("{name} {width}x{height}");
                    if s.video_format.as_deref() != Some(&format) {
                        eprintln!("h713-airplay: session {sid} video {format}");
                        s.video_format = Some(format);
                    }
                }
                if let Some(l) = &link {
                    l.push_control(Msg::VideoConfig { codec, width, height, config: payload });
                }
            }
            _ => {}
        }
    }
}

pub fn video_text(format: Option<&str>, counters: &Counters) -> String {
    match format {
        Some(f) => format!(
            "{f} frames {} bytes {}",
            counters.video_frames.load(Ordering::Relaxed),
            counters.video_bytes.load(Ordering::Relaxed)
        ),
        None => "-".into(),
    }
}
