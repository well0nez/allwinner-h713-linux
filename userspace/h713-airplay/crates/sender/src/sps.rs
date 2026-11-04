// SPDX-License-Identifier: GPL-3.0-only
//! Just enough of an SPS for the codec packet: the picture size (H.264 7.3.2.1.1, H.265 7.3.2.2) and the
//! hvcC header fields. A field this parser does not follow gives 0, which the receiver passes on as unknown.

/// The RBSP: emulation prevention bytes (`00 00 03`) removed.
pub fn rbsp(nal: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(nal.len());
    let mut zeros = 0;
    for &b in nal {
        if zeros >= 2 && b == 3 {
            zeros = 0;
            continue;
        }
        zeros = if b == 0 { zeros + 1 } else { 0 };
        out.push(b);
    }
    out
}

struct Bits<'a> {
    data: &'a [u8],
    pos: usize,
}

impl Bits<'_> {
    fn bit(&mut self) -> Option<u32> {
        let byte = *self.data.get(self.pos / 8)?;
        let b = (byte >> (7 - self.pos % 8)) & 1;
        self.pos += 1;
        Some(u32::from(b))
    }
    fn bits(&mut self, n: u32) -> Option<u32> {
        (0..n).try_fold(0u32, |acc, _| Some((acc << 1) | self.bit()?))
    }
    fn skip(&mut self, n: usize) {
        self.pos += n;
    }
    fn ue(&mut self) -> Option<u32> {
        let mut zeros = 0;
        while self.bit()? == 0 {
            zeros += 1;
            if zeros > 31 {
                return None;
            }
        }
        Some((1u32 << zeros) - 1 + self.bits(zeros)?)
    }
    fn se(&mut self) -> Option<i32> {
        let v = self.ue()?;
        Some(if v % 2 == 1 { v.div_ceil(2) as i32 } else { -((v / 2) as i32) })
    }
}

fn h264_size(sps: &[u8]) -> Option<(u32, u32)> {
    let data = rbsp(sps.get(1..)?);
    let mut r = Bits { data: &data, pos: 0 };
    let profile = r.bits(8)?;
    r.skip(16);
    r.ue()?;
    let mut chroma = 1;
    if [100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135].contains(&profile) {
        chroma = r.ue()?;
        if chroma == 3 {
            r.bit()?;
        }
        r.ue()?;
        r.ue()?;
        r.bit()?;
        if r.bit()? == 1 {
            for i in 0..if chroma == 3 { 12 } else { 8 } {
                if r.bit()? == 1 {
                    let size = if i < 6 { 16 } else { 64 };
                    let (mut last, mut next) = (8i32, 8i32);
                    for _ in 0..size {
                        if next != 0 {
                            next = (last + r.se()? + 256) % 256;
                        }
                        last = if next == 0 { last } else { next };
                    }
                }
            }
        }
    }
    r.ue()?;
    match r.ue()? {
        0 => {
            r.ue()?;
        }
        1 => {
            r.bit()?;
            r.se()?;
            r.se()?;
            for _ in 0..r.ue()? {
                r.se()?;
            }
        }
        _ => {}
    }
    r.ue()?;
    r.bit()?;
    let width_mbs = r.ue()? + 1;
    let height_units = r.ue()? + 1;
    let frame_mbs_only = r.bit()?;
    if frame_mbs_only == 0 {
        r.bit()?;
    }
    r.bit()?;
    let (cx, cy) = match chroma {
        1 => (2, 2 * (2 - frame_mbs_only)),
        2 => (2, 2 - frame_mbs_only),
        _ => (1, 2 - frame_mbs_only),
    };
    let crop = if r.bit()? == 1 { [r.ue()?, r.ue()?, r.ue()?, r.ue()?] } else { [0; 4] };
    let w = width_mbs * 16 - (crop[0] + crop[1]) * cx;
    let h = (2 - frame_mbs_only) * height_units * 16 - (crop[2] + crop[3]) * cy;
    Some((w, h))
}

#[derive(Default)]
pub struct H265 {
    pub width: u32,
    pub height: u32,
    pub chroma: u8,
    pub luma8: u8,
    pub chroma8: u8,
    pub sub_layers: u8,
    pub nested: bool,
}

fn h265_parse(sps: &[u8]) -> Option<H265> {
    let data = rbsp(sps.get(2..)?);
    let mut r = Bits { data: &data, pos: 0 };
    r.skip(4);
    let max_sub_layers_minus1 = r.bits(3)?;
    let nested = r.bit()? == 1;
    r.skip(96);
    let flags: Vec<(u32, u32)> = (0..max_sub_layers_minus1).map(|_| Some((r.bit()?, r.bit()?))).collect::<Option<_>>()?;
    if max_sub_layers_minus1 > 0 {
        r.skip(2 * (8 - max_sub_layers_minus1 as usize));
    }
    for (profile, level) in flags {
        r.skip(88 * profile as usize + 8 * level as usize);
    }
    r.ue()?;
    let chroma = r.ue()?;
    if chroma == 3 {
        r.bit()?;
    }
    let (w, h) = (r.ue()?, r.ue()?);
    let (sw, shh) = match chroma {
        1 => (2, 2),
        2 => (2, 1),
        _ => (1, 1),
    };
    let crop = if r.bit()? == 1 { [r.ue()?, r.ue()?, r.ue()?, r.ue()?] } else { [0; 4] };
    let luma8 = r.ue()? as u8;
    let chroma8 = r.ue()? as u8;
    Some(H265 {
        width: w - sw * (crop[0] + crop[1]),
        height: h - shh * (crop[2] + crop[3]),
        chroma: chroma as u8,
        luma8,
        chroma8,
        sub_layers: max_sub_layers_minus1 as u8 + 1,
        nested,
    })
}

pub fn h264(sps: &[u8]) -> (u32, u32) {
    h264_size(sps).unwrap_or((0, 0))
}

pub fn h265(sps: &[u8]) -> H265 {
    h265_parse(sps).unwrap_or(H265 { chroma: 1, sub_layers: 1, ..H265::default() })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn hex(s: &str) -> Vec<u8> {
        (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap()).collect()
    }

    #[test]
    fn sizes_of_real_parameter_sets() {
        assert_eq!(h264(&hex("67f4000d919b28283f6022000003000200000300781e28532c")), (320, 240));
        let hevc = h265(&hex(
            "4201010408000003009e0800000300003c90014101e2cb2b349265780b7020200040000003004000000782",
        ));
        assert_eq!((hevc.width, hevc.height, hevc.chroma), (320, 240, 3));
    }
}
