// SPDX-License-Identifier: GPL-3.0-only
//! Screen audio on UDP (raop_rtp.c, raop_buffer.c): RTP packets with a 12-byte header on the data port,
//! decrypted on arrival and handed to the presenter. The control port (sync, resend) is read and dropped.
//! Without a jitter buffer a packet is only passed on when its sequence number is newer than the last one:
//! senders repeat recent packets for redundancy (doubletake sends N-2, N-1, N each time).

use crate::crypto;
use proto::ipc::{AudioCodec, Msg};
use crate::shared::Shared;
use std::net::UdpSocket;
use std::sync::atomic::Ordering;
use std::sync::Arc;

pub fn data_loop(sh: Arc<Shared>, sock: UdpSocket) {
    let mut buf = [0u8; 2048];
    let mut last: Option<(u64, u16)> = None;
    loop {
        let Ok((n, from)) = sock.recv_from(&mut buf) else { continue };
        if n <= 12 || buf[0] & 0xc0 != 0x80 {
            continue;
        }
        let ctx = {
            let inner = sh.lock();
            inner.session.as_ref().filter(|s| s.peer == from.ip()).and_then(|s| {
                let a = s.audio.as_ref()?;
                Some((s.id, a.keys, s.link.clone(), s.counters.clone()))
            })
        };
        let Some((sid, keys, link, counters)) = ctx else { continue };
        let seq = u16::from_be_bytes([buf[2], buf[3]]);
        if !newer(last, sid, seq) {
            continue;
        }
        last = Some((sid, seq));
        let rtp = u32::from_be_bytes([buf[4], buf[5], buf[6], buf[7]]);
        let mut data = buf[12..n].to_vec();
        crypto::audio_decrypt(&keys.key, &keys.iv, &mut data);
        counters.audio_frames.fetch_add(1, Ordering::Relaxed);
        if let Some(link) = link {
            link.push_audio(Msg::AudioFrame { rtp, seq, data });
        }
    }
}

fn newer(last: Option<(u64, u16)>, sid: u64, seq: u16) -> bool {
    match last {
        Some((s, l)) if s == sid => (seq.wrapping_sub(l) as i16) > 0,
        _ => true,
    }
}

pub fn control_loop(sock: UdpSocket) {
    let mut buf = [0u8; 2048];
    while sock.recv_from(&mut buf).is_ok() {}
}

pub fn codec_name(c: AudioCodec) -> &'static str {
    match c {
        AudioCodec::AacEld => "aac-eld",
        AudioCodec::Alac => "alac",
        AudioCodec::AacLc => "aac-lc",
        AudioCodec::Pcm => "pcm",
    }
}

#[cfg(test)]
mod tests {
    use super::newer;

    #[test]
    fn repeated_and_older_sequence_numbers_are_dropped_across_the_wrap() {
        assert!(newer(None, 1, 7));
        assert!(!newer(Some((1, 7)), 1, 7));
        assert!(!newer(Some((1, 7)), 1, 5));
        assert!(newer(Some((1, 65535)), 1, 0));
        assert!(newer(Some((1, 7)), 2, 3), "a new session starts afresh");
    }
}
