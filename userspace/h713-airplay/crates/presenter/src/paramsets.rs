// SPDX-License-Identifier: GPL-3.0-only
//! The codec record of `VideoConfig` (an avcC for H.264, an hvcC for H.265) to the parameter sets in Annex B, which
//! the presenter puts before every key frame; and the records built from parameter sets, for the feeder.

use proto::ipc::VideoCodec;
use std::fmt;

#[derive(Debug, PartialEq, Eq)]
pub enum RecordError {
    Short,
    Version(u8),
    NoParameterSets,
}

impl fmt::Display for RecordError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            RecordError::Short => write!(f, "the codec record ends inside a field"),
            RecordError::Version(v) => write!(f, "codec record version {v}, not 1"),
            RecordError::NoParameterSets => write!(f, "the codec record carries no parameter set"),
        }
    }
}

struct Cursor<'a>(&'a [u8]);

impl<'a> Cursor<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8], RecordError> {
        if self.0.len() < n {
            return Err(RecordError::Short);
        }
        let (a, b) = self.0.split_at(n);
        self.0 = b;
        Ok(a)
    }
    fn u8(&mut self) -> Result<u8, RecordError> {
        Ok(self.take(1)?[0])
    }
    fn u16(&mut self) -> Result<usize, RecordError> {
        let b = self.take(2)?;
        Ok(usize::from(b[0]) << 8 | usize::from(b[1]))
    }
    fn nal(&mut self) -> Result<Vec<u8>, RecordError> {
        let n = self.u16()?;
        Ok(self.take(n)?.to_vec())
    }
}

fn is_annexb(record: &[u8]) -> bool {
    record.starts_with(&[0, 0, 0, 1]) || record.starts_with(&[0, 0, 1])
}

/// The parameter sets of a record, in its order (SPS before PPS, VPS before both for H.265). A record that is
/// already Annex B (a start code first) is split as it stands.
pub fn parse(codec: VideoCodec, record: &[u8]) -> Result<Vec<Vec<u8>>, RecordError> {
    let nals = if is_annexb(record) {
        crate::annexb::split(record).into_iter().map(<[u8]>::to_vec).collect()
    } else {
        match codec {
            VideoCodec::H264 => parse_avcc(record)?,
            VideoCodec::H265 => parse_hvcc(record)?,
        }
    };
    if nals.is_empty() {
        return Err(RecordError::NoParameterSets);
    }
    Ok(nals)
}

fn parse_avcc(record: &[u8]) -> Result<Vec<Vec<u8>>, RecordError> {
    let mut c = Cursor(record);
    let version = c.u8()?;
    if version != 1 {
        return Err(RecordError::Version(version));
    }
    c.take(4)?;
    let mut nals = Vec::new();
    for _ in 0..(c.u8()? & 0x1f) {
        nals.push(c.nal()?);
    }
    for _ in 0..c.u8()? {
        nals.push(c.nal()?);
    }
    Ok(nals)
}

fn parse_hvcc(record: &[u8]) -> Result<Vec<Vec<u8>>, RecordError> {
    let mut c = Cursor(record);
    let version = c.u8()?;
    if version != 1 {
        return Err(RecordError::Version(version));
    }
    c.take(21)?;
    let mut nals = Vec::new();
    for _ in 0..c.u8()? {
        c.u8()?;
        for _ in 0..c.u16()? {
            nals.push(c.nal()?);
        }
    }
    Ok(nals)
}

pub fn annexb(nals: &[Vec<u8>]) -> Vec<u8> {
    let mut out = Vec::with_capacity(nals.iter().map(|n| n.len() + 4).sum());
    for n in nals {
        out.extend_from_slice(&[0, 0, 0, 1]);
        out.extend_from_slice(n);
    }
    out
}

fn put_nal(out: &mut Vec<u8>, nal: &[u8]) {
    out.extend_from_slice(&(nal.len() as u16).to_be_bytes());
    out.extend_from_slice(nal);
}

/// An avcC record with 4-byte lengths. The profile bytes come from the first SPS.
pub fn build_avcc(sps: &[Vec<u8>], pps: &[Vec<u8>]) -> Vec<u8> {
    let first = sps.first().map(Vec::as_slice).unwrap_or(&[]);
    let at = |i: usize| first.get(i).copied().unwrap_or(0);
    let mut out = vec![1, at(1), at(2), at(3), 0xff, 0xe0 | sps.len() as u8];
    sps.iter().for_each(|n| put_nal(&mut out, n));
    out.push(pps.len() as u8);
    pps.iter().for_each(|n| put_nal(&mut out, n));
    out
}

/// An hvcC record with 4-byte lengths and three arrays (VPS, SPS, PPS). The general profile, tier and level are
/// copied from the first SPS: its bytes 3..15, profile_tier_level after the two-byte NAL header and the sub-layer byte.
pub fn build_hvcc(vps: &[Vec<u8>], sps: &[Vec<u8>], pps: &[Vec<u8>]) -> Vec<u8> {
    let first = sps.first().map(Vec::as_slice).unwrap_or(&[]);
    let mut out = vec![1u8];
    out.extend((3..15).map(|i| first.get(i).copied().unwrap_or(0)));
    out.extend_from_slice(&[0xf0, 0x00, 0xfc, 0xfd, 0xf8, 0xf8, 0, 0, 0x0f, 3]);
    for (kind, list) in [(32u8, vps), (33, sps), (34, pps)] {
        out.push(0x80 | kind);
        out.extend_from_slice(&(list.len() as u16).to_be_bytes());
        list.iter().for_each(|n| put_nal(&mut out, n));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    const SPS: &[u8] = &[0x67, 0x64, 0x00, 0x2a, 0xac, 0xd9];
    const PPS: &[u8] = &[0x68, 0xeb, 0xe3, 0xcb];

    #[test]
    fn an_avcc_record_from_a_sender_gives_its_sps_and_pps() {
        let record = [
            &[1u8, 0x64, 0x00, 0x2a, 0xff, 0xe1, 0, 6][..], SPS, &[1, 0, 4], PPS,
        ]
        .concat();
        assert_eq!(parse(VideoCodec::H264, &record).unwrap(), vec![SPS.to_vec(), PPS.to_vec()]);
        assert_eq!(annexb(&[SPS.to_vec(), PPS.to_vec()]), [&[0u8, 0, 0, 1][..], SPS, &[0, 0, 0, 1], PPS].concat());
    }

    #[test]
    fn built_records_parse_back_to_the_same_parameter_sets() {
        let (sps, pps) = (vec![SPS.to_vec()], vec![PPS.to_vec()]);
        assert_eq!(parse(VideoCodec::H264, &build_avcc(&sps, &pps)).unwrap(), [sps.clone(), pps.clone()].concat());
        let vps = vec![vec![0x40, 0x01, 0x0c]];
        let hsps = vec![vec![0x42, 0x01, 0x01, 0x01, 0x60, 0, 0, 0x03, 0x00, 0x90, 0, 0, 0x03, 0, 0, 0x7b]];
        let hpps = vec![vec![0x44, 0x01, 0xc1]];
        let record = build_hvcc(&vps, &hsps, &hpps);
        assert_eq!(record[1..13], hsps[0][3..15]);
        assert_eq!(parse(VideoCodec::H265, &record).unwrap(), [vps, hsps, hpps].concat());
    }

    #[test]
    fn a_broken_record_is_an_error_not_a_guess() {
        assert_eq!(parse(VideoCodec::H264, &[1, 0x64, 0, 0x2a, 0xff, 0xe1, 0, 9, 0x67]), Err(RecordError::Short));
        assert_eq!(parse(VideoCodec::H265, &[0; 23]), Err(RecordError::Version(0)));
        assert_eq!(parse(VideoCodec::H264, &[1, 0x64, 0, 0x2a, 0xff, 0xe0, 0]), Err(RecordError::NoParameterSets));
    }

    #[test]
    fn an_annexb_record_is_taken_as_it_stands() {
        let record = [&[0u8, 0, 0, 1][..], SPS, &[0, 0, 1], PPS].concat();
        assert_eq!(parse(VideoCodec::H264, &record).unwrap(), vec![SPS.to_vec(), PPS.to_vec()]);
    }
}
