// SPDX-License-Identifier: GPL-3.0-only
//! An H.264/H.265 Annex B stream cut into access units, the AVCC/HVCC payloads a mirror stream carries, and the
//! avcC/hvcC record of its codec packet.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Codec {
    H264,
    H265,
}

pub struct AccessUnit<'a> {
    pub nals: Vec<&'a [u8]>,
    pub params: Vec<&'a [u8]>,
    pub key: bool,
}

impl AccessUnit<'_> {
    /// The mirror stream's payload: every NAL unit with a 4-byte big-endian length.
    pub fn avcc(&self) -> Vec<u8> {
        let mut out = Vec::with_capacity(self.nals.iter().map(|n| n.len() + 4).sum());
        for n in &self.nals {
            out.extend_from_slice(&(n.len() as u32).to_be_bytes());
            out.extend_from_slice(n);
        }
        out
    }
}

pub fn split_nals(data: &[u8]) -> Vec<&[u8]> {
    let mut starts = Vec::new();
    let mut i = 0;
    while i + 3 <= data.len() {
        if data[i] == 0 && data[i + 1] == 0 && data[i + 2] == 1 {
            starts.push(i + 3);
            i += 3;
        } else {
            i += 1;
        }
    }
    let mut out = Vec::new();
    for (k, &s) in starts.iter().enumerate() {
        let end = starts.get(k + 1).map_or(data.len(), |&n| n - 3);
        let mut nal = &data[s..end];
        while let [rest @ .., 0] = nal {
            nal = rest;
        }
        if !nal.is_empty() {
            out.push(nal);
        }
    }
    out
}

pub fn nal_type(codec: Codec, nal: &[u8]) -> u8 {
    match codec {
        Codec::H264 => nal[0] & 0x1f,
        Codec::H265 => (nal[0] >> 1) & 0x3f,
    }
}

struct Kinds {
    vcl: bool,
    first_slice: bool,
    param: bool,
    aud: bool,
    key: bool,
    opens_au: bool,
}

fn kinds(codec: Codec, nal: &[u8]) -> Kinds {
    let t = nal_type(codec, nal);
    match codec {
        Codec::H264 => Kinds {
            vcl: (1..=5).contains(&t),
            first_slice: nal.get(1).is_some_and(|b| b & 0x80 != 0),
            param: t == 7 || t == 8,
            aud: t == 9,
            key: t == 5,
            opens_au: (6..=9).contains(&t),
        },
        Codec::H265 => Kinds {
            vcl: t <= 31,
            first_slice: nal.get(2).is_some_and(|b| b & 0x80 != 0),
            param: (32..=34).contains(&t),
            aud: t == 35,
            key: (16..=21).contains(&t),
            opens_au: (32..=35).contains(&t) || t == 39 || (41..=44).contains(&t),
        },
    }
}

pub fn access_units(codec: Codec, data: &[u8]) -> Vec<AccessUnit<'_>> {
    let mut out = Vec::new();
    let mut cur = AccessUnit { nals: Vec::new(), params: Vec::new(), key: false };
    let mut has_vcl = false;
    for nal in split_nals(data) {
        let k = kinds(codec, nal);
        if has_vcl && ((k.vcl && k.first_slice) || (!k.vcl && k.opens_au)) {
            out.push(std::mem::replace(&mut cur, AccessUnit { nals: Vec::new(), params: Vec::new(), key: false }));
            has_vcl = false;
        }
        if k.param {
            cur.params.push(nal);
        } else if !k.aud {
            cur.nals.push(nal);
        }
        has_vcl |= k.vcl;
        cur.key |= k.key;
    }
    if has_vcl {
        out.push(cur);
    }
    out
}

/// Parameter sets in the order the codec packet lists them: VPS, SPS, PPS (H.264: SPS, PPS).
pub fn parameter_sets<'a>(codec: Codec, params: &[&'a [u8]]) -> Option<Vec<&'a [u8]>> {
    let wanted: &[u8] = match codec {
        Codec::H264 => &[7, 8],
        Codec::H265 => &[32, 33, 34],
    };
    wanted.iter().map(|t| params.iter().rev().find(|n| nal_type(codec, n) == *t).copied()).collect()
}

pub fn avcc_record(sps: &[u8], pps: &[u8]) -> Vec<u8> {
    let mut c = vec![1, sps[1], sps[2], sps[3], 0xff, 0xe1];
    c.extend_from_slice(&(sps.len() as u16).to_be_bytes());
    c.extend_from_slice(sps);
    c.push(1);
    c.extend_from_slice(&(pps.len() as u16).to_be_bytes());
    c.extend_from_slice(pps);
    c
}

pub fn hvcc_record(vps: &[u8], sps: &[u8], pps: &[u8]) -> Vec<u8> {
    let info = crate::sps::h265(sps);
    let rbsp = crate::sps::rbsp(&sps[2..]);
    let ptl: [u8; 12] = rbsp.get(1..13).and_then(|s| s.try_into().ok()).unwrap_or([0; 12]);
    let mut c = vec![1];
    c.extend_from_slice(&ptl);
    c.extend_from_slice(&[0xf0, 0x00, 0xfc, 0xfc | info.chroma, 0xf8 | info.luma8, 0xf8 | info.chroma8, 0, 0]);
    c.push((info.sub_layers << 3) | (u8::from(info.nested) << 2) | 3);
    c.push(3);
    for (t, nal) in [(32u8, vps), (33, sps), (34, pps)] {
        c.push(0x80 | t);
        c.extend_from_slice(&1u16.to_be_bytes());
        c.extend_from_slice(&(nal.len() as u16).to_be_bytes());
        c.extend_from_slice(nal);
    }
    c
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn access_units_split_at_first_slices_and_keep_parameter_sets_apart() {
        let wire = [
            &[0, 0, 0, 1, 0x09, 0xf0][..],
            &[0, 0, 0, 1, 0x67, 1, 2, 3],
            &[0, 0, 1, 0x68, 4],
            &[0, 0, 1, 0x65, 0x88, 9, 0, 0],
            &[0, 0, 1, 0x65, 0x08, 8],
            &[0, 0, 1, 0x41, 0x9a, 7],
            &[0, 0, 1, 0x41, 0x9b, 6],
        ]
        .concat();
        let aus = access_units(Codec::H264, &wire);
        assert_eq!(aus.len(), 3);
        assert!(aus[0].key && !aus[1].key);
        assert_eq!(aus[0].nals, vec![&[0x65, 0x88, 9][..], &[0x65, 0x08, 8]]);
        assert_eq!(aus[0].params.len(), 2);
        assert_eq!(aus[1].avcc(), vec![0, 0, 0, 3, 0x41, 0x9a, 7]);
    }
}
