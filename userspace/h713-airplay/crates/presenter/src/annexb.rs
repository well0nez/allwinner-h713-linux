// SPDX-License-Identifier: GPL-3.0-only
//! NAL unit framing: the mirror stream's 4-byte lengths to Annex B start codes (in place), Annex B split into NAL
//! units, and an Annex B file read as access units (the feeder).

use proto::ipc::VideoCodec;
use std::io::{self, Read};

#[derive(Debug, PartialEq, Eq)]
pub struct FramingError {
    pub at: usize,
}

/// What a frame holds after [`lengths_to_start_codes`].
#[derive(Debug, Default, PartialEq, Eq)]
pub struct Framed {
    pub nals: usize,
    pub random_access: bool,
}

pub fn nal_type(codec: VideoCodec, nal: &[u8]) -> u8 {
    match (codec, nal.first()) {
        (_, None) => 0xff,
        (VideoCodec::H264, Some(b)) => b & 0x1f,
        (VideoCodec::H265, Some(b)) => (b >> 1) & 0x3f,
    }
}

/// An IDR picture (H.264) or an IRAP picture (H.265): decoding may start here.
pub fn is_random_access(codec: VideoCodec, t: u8) -> bool {
    match codec {
        VideoCodec::H264 => t == 5,
        VideoCodec::H265 => (16..=21).contains(&t),
    }
}

pub fn is_parameter_set(codec: VideoCodec, t: u8) -> bool {
    match codec {
        VideoCodec::H264 => t == 7 || t == 8,
        VideoCodec::H265 => (32..=34).contains(&t),
    }
}

/// Replaces each 4-byte big-endian length with the start code `00 00 00 01`; the frame keeps its size.
pub fn lengths_to_start_codes(codec: VideoCodec, data: &mut [u8]) -> Result<Framed, FramingError> {
    let mut framed = Framed::default();
    let mut at = 0;
    while at < data.len() {
        let Some(len) = data.get(at..at + 4).map(|b| u32::from_be_bytes([b[0], b[1], b[2], b[3]]) as usize) else {
            return Err(FramingError { at });
        };
        let end = at + 4 + len;
        if len == 0 || end > data.len() {
            return Err(FramingError { at });
        }
        data[at..at + 4].copy_from_slice(&[0, 0, 0, 1]);
        framed.nals += 1;
        framed.random_access |= is_random_access(codec, nal_type(codec, &data[at + 4..end]));
        at = end;
    }
    Ok(framed)
}

fn start_code(data: &[u8], from: usize) -> Option<usize> {
    data.get(from..)?.windows(3).position(|w| w == [0, 0, 1]).map(|p| p + from)
}

fn trim_zeros(nal: &[u8]) -> &[u8] {
    let end = nal.iter().rposition(|&b| b != 0).map_or(0, |p| p + 1);
    &nal[..end]
}

/// The NAL units of an Annex B buffer, without start codes and trailing zero bytes.
pub fn split(data: &[u8]) -> Vec<&[u8]> {
    let mut out = Vec::new();
    let Some(mut at) = start_code(data, 0).map(|p| p + 3) else { return out };
    loop {
        let next = start_code(data, at);
        let nal = trim_zeros(&data[at..next.unwrap_or(data.len())]);
        if !nal.is_empty() {
            out.push(nal);
        }
        match next {
            Some(p) => at = p + 3,
            None => return out,
        }
    }
}

/// NAL units out of an Annex B stream of any length, read in chunks.
pub struct NalReader<R> {
    r: R,
    buf: Vec<u8>,
    start: Option<usize>,
    scan: usize,
    eof: bool,
}

impl<R: Read> NalReader<R> {
    pub fn new(r: R) -> Self {
        NalReader { r, buf: Vec::new(), start: None, scan: 0, eof: false }
    }

    fn fill(&mut self) -> io::Result<()> {
        let keep = self.start.unwrap_or(self.scan.saturating_sub(3)).min(self.buf.len());
        self.buf.drain(..keep);
        self.start = self.start.map(|s| s - keep);
        self.scan -= keep.min(self.scan);
        let old = self.buf.len();
        self.buf.resize(old + (256 << 10), 0);
        let n = self.r.read(&mut self.buf[old..])?;
        self.buf.truncate(old + n);
        self.eof = n == 0;
        Ok(())
    }

    pub fn next_nal(&mut self) -> io::Result<Option<Vec<u8>>> {
        loop {
            match (self.start, start_code(&self.buf, self.scan)) {
                (None, Some(p)) => {
                    self.start = Some(p + 3);
                    self.scan = p + 3;
                }
                (Some(s), Some(p)) => {
                    let nal = trim_zeros(&self.buf[s..p]).to_vec();
                    self.start = Some(p + 3);
                    self.scan = p + 3;
                    if !nal.is_empty() {
                        return Ok(Some(nal));
                    }
                }
                (start, None) if self.eof => {
                    self.start = None;
                    self.scan = self.buf.len();
                    let nal = start.map(|s| trim_zeros(&self.buf[s..]).to_vec()).unwrap_or_default();
                    return Ok((!nal.is_empty()).then_some(nal));
                }
                (_, None) => {
                    self.scan = self.buf.len().saturating_sub(2).max(self.start.unwrap_or(0));
                    self.fill()?;
                }
            }
        }
    }
}

fn begins_access_unit(codec: VideoCodec, nal: &[u8]) -> bool {
    let t = nal_type(codec, nal);
    match codec {
        VideoCodec::H264 => matches!(t, 6..=9 | 14..=18) || ((t == 1 || t == 5) && nal.get(1).is_some_and(|b| b & 0x80 != 0)),
        VideoCodec::H265 => {
            matches!(t, 32..=35 | 39 | 41..=44 | 48..=55) || (t <= 31 && nal.get(2).is_some_and(|b| b & 0x80 != 0))
        }
    }
}

fn is_vcl(codec: VideoCodec, t: u8) -> bool {
    match codec {
        VideoCodec::H264 => (1..=5).contains(&t),
        VideoCodec::H265 => t <= 31,
    }
}

/// An Annex B stream as access units: a unit ends where the next picture's first NAL unit begins.
pub struct AccessUnits<R> {
    nals: NalReader<R>,
    codec: VideoCodec,
    next: Option<Vec<u8>>,
}

impl<R: Read> AccessUnits<R> {
    pub fn new(codec: VideoCodec, r: R) -> Self {
        AccessUnits { nals: NalReader::new(r), codec, next: None }
    }

    pub fn next_unit(&mut self) -> io::Result<Option<Vec<Vec<u8>>>> {
        let mut unit: Vec<Vec<u8>> = self.next.take().into_iter().collect();
        let mut vcl = unit.iter().any(|n| is_vcl(self.codec, nal_type(self.codec, n)));
        while let Some(nal) = self.nals.next_nal()? {
            if vcl && begins_access_unit(self.codec, &nal) {
                self.next = Some(nal);
                return Ok(Some(unit));
            }
            vcl |= is_vcl(self.codec, nal_type(self.codec, &nal));
            unit.push(nal);
        }
        Ok((!unit.is_empty()).then_some(unit))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lengths_become_start_codes_and_an_idr_is_found() {
        let mut f = vec![0, 0, 0, 2, 0x09, 0xf0, 0, 0, 0, 3, 0x65, 0x88, 0x84];
        let framed = lengths_to_start_codes(VideoCodec::H264, &mut f).unwrap();
        assert_eq!(f, [0, 0, 0, 1, 0x09, 0xf0, 0, 0, 0, 1, 0x65, 0x88, 0x84]);
        assert_eq!(framed, Framed { nals: 2, random_access: true });
        let mut hevc = vec![0, 0, 0, 2, 0x02, 0x01];
        assert!(!lengths_to_start_codes(VideoCodec::H265, &mut hevc).unwrap().random_access);
    }

    #[test]
    fn a_length_past_the_end_is_refused() {
        assert_eq!(lengths_to_start_codes(VideoCodec::H264, &mut [0, 0, 0, 9, 0x65]), Err(FramingError { at: 0 }));
        assert_eq!(lengths_to_start_codes(VideoCodec::H264, &mut [0, 0, 0, 1, 0x65, 0]), Err(FramingError { at: 5 }));
    }

    fn stream() -> Vec<u8> {
        let au = |idr: bool| -> Vec<u8> {
            let slice: &[u8] = if idr { &[0x65, 0x88, 0x80] } else { &[0x41, 0x9a, 0x00, 0x80] };
            [&[0u8, 0, 0, 1, 0x09, 0x10][..], &[0, 0, 1], slice, &[0, 0, 1, 0x41, 0x00, 0x10]].concat()
        };
        [&[0u8, 0, 0, 1, 0x67, 0x64][..], &[0, 0, 0, 1, 0x68, 0xeb], &au(true), &au(false), &[0, 0]].concat()
    }

    #[test]
    fn a_stream_read_in_small_chunks_gives_whole_access_units() {
        struct Trickle<'a>(&'a [u8]);
        impl Read for Trickle<'_> {
            fn read(&mut self, b: &mut [u8]) -> io::Result<usize> {
                let n = self.0.len().min(b.len()).min(2);
                b[..n].copy_from_slice(&self.0[..n]);
                self.0 = &self.0[n..];
                Ok(n)
            }
        }
        let data = stream();
        let mut units = AccessUnits::new(VideoCodec::H264, Trickle(&data));
        let first = units.next_unit().unwrap().unwrap();
        assert_eq!(first.iter().map(|n| n[0]).collect::<Vec<_>>(), [0x67, 0x68, 0x09, 0x65, 0x41]);
        let second = units.next_unit().unwrap().unwrap();
        assert_eq!(second.iter().map(|n| n[0]).collect::<Vec<_>>(), [0x09, 0x41, 0x41]);
        assert_eq!(second[1], [0x41, 0x9a, 0x00, 0x80], "a NAL unit keeps its inner zero bytes");
        assert_eq!(units.next_unit().unwrap(), None);
        assert_eq!(split(&data).len(), 8);
    }
}
