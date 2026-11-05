// SPDX-License-Identifier: GPL-3.0-only
//! A Core Audio Format file with ALAC packets (`ffmpeg -c:a alac -f caf`), for the feeder's `--audio`.

use std::fmt;

#[derive(Debug, PartialEq)]
pub struct Caf {
    pub sample_rate: u32,
    pub channels: u8,
    pub frames_per_packet: u32,
    pub cookie: Vec<u8>,
    pub packets: Vec<Vec<u8>>,
}

#[derive(Debug, PartialEq, Eq)]
pub struct CafError(pub &'static str);

impl fmt::Display for CafError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "CAF: {}", self.0)
    }
}

fn be(b: &[u8]) -> u64 {
    b.iter().fold(0, |v, &x| v << 8 | u64::from(x))
}

/// A packet table entry: seven bits a byte, high bit set on all but the last.
fn varint(data: &[u8], at: &mut usize) -> Result<u64, CafError> {
    let mut v = 0u64;
    loop {
        let b = *data.get(*at).ok_or(CafError("packet table ends inside an entry"))?;
        *at += 1;
        v = v << 7 | u64::from(b & 0x7f);
        if b & 0x80 == 0 {
            return Ok(v);
        }
    }
}

pub fn parse(file: &[u8]) -> Result<Caf, CafError> {
    if file.get(0..4) != Some(b"caff") {
        return Err(CafError("not a CAF file"));
    }
    let (mut desc, mut cookie, mut pakt, mut data) = (None, Vec::new(), None, None);
    let mut at = 8;
    while at + 12 <= file.len() {
        let kind = &file[at..at + 4];
        let size = be(&file[at + 4..at + 12]) as i64;
        let body = at + 12;
        let end = if size < 0 { file.len() } else { body.saturating_add(size as usize).min(file.len()) };
        let chunk = &file[body..end];
        match kind {
            b"desc" if chunk.len() >= 32 => desc = Some(chunk),
            b"kuki" => cookie = chunk.to_vec(),
            b"pakt" => pakt = Some(chunk),
            b"data" if chunk.len() >= 4 => data = Some(&chunk[4..]),
            _ => {}
        }
        at = end;
    }
    let desc = desc.ok_or(CafError("no desc chunk"))?;
    if &desc[8..12] != b"alac" {
        return Err(CafError("not ALAC"));
    }
    let sample_rate = f64::from_bits(be(&desc[0..8])) as u32;
    let frames_per_packet = be(&desc[20..24]) as u32;
    let channels = be(&desc[24..28]) as u8;
    let (pakt, data) = (pakt.ok_or(CafError("no packet table"))?, data.ok_or(CafError("no data chunk"))?);
    if pakt.len() < 24 {
        return Err(CafError("short packet table"));
    }
    let mut at = 24;
    let mut offset = 0usize;
    let mut packets = Vec::new();
    for _ in 0..be(&pakt[0..8]) {
        let len = varint(pakt, &mut at)? as usize;
        if frames_per_packet == 0 {
            varint(pakt, &mut at)?;
        }
        let packet = data.get(offset..offset + len).ok_or(CafError("a packet past the data chunk"))?;
        packets.push(packet.to_vec());
        offset += len;
    }
    Ok(Caf { sample_rate, channels, frames_per_packet, cookie, packets })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn chunk(kind: &[u8; 4], body: &[u8]) -> Vec<u8> {
        [&kind[..], &(body.len() as u64).to_be_bytes(), body].concat()
    }

    fn desc() -> Vec<u8> {
        let mut d = 44100f64.to_bits().to_be_bytes().to_vec();
        d.extend_from_slice(b"alac");
        d.extend_from_slice(&[0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0x10, 0, 0, 0, 0, 2, 0, 0, 0, 0]);
        d
    }

    #[test]
    fn packets_come_out_as_the_table_cuts_them() {
        let mut pakt = [2u64.to_be_bytes(), 8192u64.to_be_bytes()].concat();
        pakt.extend_from_slice(&[0; 8]);
        pakt.extend_from_slice(&[3, 0x81, 0x01]);
        let mut data = vec![0, 0, 0, 1, 7, 8, 9];
        data.extend(std::iter::repeat_n(5, 129));
        let file = [b"caff\x00\x01\x00\x00".to_vec(), chunk(b"desc", &desc()), chunk(b"kuki", &[1; 24]), chunk(b"pakt", &pakt), chunk(b"data", &data)].concat();
        let caf = parse(&file).unwrap();
        assert_eq!((caf.sample_rate, caf.channels, caf.frames_per_packet), (44100, 2, 4096));
        assert_eq!(caf.cookie, vec![1; 24]);
        assert_eq!(caf.packets.len(), 2);
        assert_eq!(caf.packets[0], [7, 8, 9]);
        assert_eq!(caf.packets[1].len(), 129);
    }

    #[test]
    fn a_table_that_points_past_the_data_is_an_error() {
        let pakt = [1u64.to_be_bytes(), 0u64.to_be_bytes(), 0u64.to_be_bytes()].concat();
        let file = [b"caff\x00\x01\x00\x00".to_vec(), chunk(b"desc", &desc()), chunk(b"pakt", &[&pakt[..], &[9]].concat()), chunk(b"data", &[0, 0, 0, 1, 1])].concat();
        assert_eq!(parse(&file), Err(CafError("a packet past the data chunk")));
        assert_eq!(parse(b"RIFF"), Err(CafError("not a CAF file")));
    }
}
