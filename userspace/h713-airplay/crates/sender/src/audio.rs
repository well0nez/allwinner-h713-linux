// SPDX-License-Identifier: GPL-3.0-only
//! Screen audio for sendtest: 16-bit stereo 44.1 kHz PCM (a WAV file or a 440 Hz tone) as ALAC frames of 352
//! samples, stored uncompressed (the escape form any ALAC decoder reads, no encoder needed), sent as RTP.

use std::io;
use std::path::Path;

pub const SAMPLE_RATE: u32 = 44100;
pub const SPF: usize = 352;

/// Interleaved 16-bit stereo samples from a PCM WAV file (44.1 kHz, 2 channels, 16 bits only).
pub fn read_wav(path: &Path) -> io::Result<Vec<i16>> {
    let d = std::fs::read(path)?;
    let bad = |what: &str| io::Error::new(io::ErrorKind::InvalidData, format!("{}: {what}", path.display()));
    if d.len() < 12 || &d[0..4] != b"RIFF" || &d[8..12] != b"WAVE" {
        return Err(bad("not a WAV file"));
    }
    let (mut at, mut format_ok) = (12, false);
    while at + 8 <= d.len() {
        let id = &d[at..at + 4];
        let len = u32::from_le_bytes(d[at + 4..at + 8].try_into().expect("4")) as usize;
        let body = d.get(at + 8..(at + 8 + len).min(d.len())).ok_or_else(|| bad("cut chunk"))?;
        match id {
            b"fmt " if body.len() >= 16 => {
                let field = |o: usize| u16::from_le_bytes([body[o], body[o + 1]]);
                let rate = u32::from_le_bytes(body[4..8].try_into().expect("4"));
                format_ok = field(0) == 1 && field(2) == 2 && rate == SAMPLE_RATE && field(14) == 16;
            }
            b"data" => {
                if !format_ok {
                    return Err(bad("needs PCM, 2 channels, 44100 Hz, 16 bits"));
                }
                return Ok(body.chunks_exact(2).map(|s| i16::from_le_bytes([s[0], s[1]])).collect());
            }
            _ => {}
        }
        at += 8 + len + (len & 1);
    }
    Err(bad("no data chunk"))
}

pub fn tone(seconds: f64) -> Vec<i16> {
    let n = (seconds * f64::from(SAMPLE_RATE)) as usize;
    (0..n)
        .flat_map(|i| {
            let v = (f64::from(i as u32) * 440.0 * std::f64::consts::TAU / f64::from(SAMPLE_RATE)).sin();
            let s = (v * 8000.0) as i16;
            [s, s]
        })
        .collect()
}

struct BitWriter {
    out: Vec<u8>,
    acc: u64,
    n: u32,
}

impl BitWriter {
    fn put(&mut self, v: u32, bits: u32) {
        self.acc = (self.acc << bits) | u64::from(v & ((1u32 << bits) - 1));
        self.n += bits;
        while self.n >= 8 {
            self.n -= 8;
            self.out.push((self.acc >> self.n) as u8);
        }
    }
    fn finish(mut self) -> Vec<u8> {
        if self.n > 0 {
            let pad = 8 - self.n;
            self.put(0, pad);
        }
        self.out
    }
}

/// One ALAC frame: a channel pair element (tag 1) marked uncompressed, the samples, the end tag (7).
pub fn alac_frame(samples: &[i16]) -> Vec<u8> {
    let frames = samples.len() / 2;
    let mut w = BitWriter { out: Vec::with_capacity(frames * 4 + 8), acc: 0, n: 0 };
    w.put(1, 3);
    w.put(0, 4);
    w.put(0, 12);
    let partial = frames != SPF;
    w.put(u32::from(partial), 1);
    w.put(0, 2);
    w.put(1, 1);
    if partial {
        w.put((frames >> 16) as u32, 16);
        w.put(frames as u32 & 0xffff, 16);
    }
    for s in samples {
        w.put(u32::from(*s as u16), 16);
    }
    w.put(7, 3);
    w.finish()
}

pub fn alac_frames(pcm: &[i16]) -> Vec<Vec<u8>> {
    pcm.chunks(SPF * 2).map(alac_frame).collect()
}

/// The 12-byte RTP header of screen audio (payload type 96, the first packet marked).
pub fn rtp_header(seq: u16, timestamp: u32, ssrc: u32, first: bool) -> [u8; 12] {
    let mut h = [0u8; 12];
    h[0] = 0x80;
    h[1] = if first { 0xe0 } else { 0x60 };
    h[2..4].copy_from_slice(&seq.to_be_bytes());
    h[4..8].copy_from_slice(&timestamp.to_be_bytes());
    h[8..12].copy_from_slice(&ssrc.to_be_bytes());
    h
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn an_uncompressed_alac_frame_has_its_header_samples_and_end_tag() {
        let f = alac_frame(&vec![0x1234i16; SPF * 2]);
        assert_eq!(f.len(), (3 + 4 + 12 + 1 + 2 + 1 + SPF * 32 + 3).div_ceil(8));
        assert_eq!(f[0] >> 5, 1);
        assert_eq!((f[2] >> 1) & 1, 1, "escape flag: uncompressed");
        let first = (u32::from(f[2] & 1) << 15) | (u32::from(f[3]) << 7) | (u32::from(f[4]) >> 1);
        assert_eq!(first, 0x1234, "samples follow the 23-bit header");
    }
}
