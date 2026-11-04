// SPDX-License-Identifier: GPL-3.0-only
//! What h713-warp's dma-buf feedback offers, and which picture path that allows: the decoder's NV12 surfaces handed
//! over as they are (one GPU pass on the device: h713-warp's own) when the table has NV12 with the surfaces'
//! modifier and the picture fits the panel the way scale-to-fit would place it; else the presenter's GL conversion.

pub const fn fourcc(c: &[u8; 4]) -> u32 {
    c[0] as u32 | (c[1] as u32) << 8 | (c[2] as u32) << 16 | (c[3] as u32) << 24
}
pub const R8: u32 = fourcc(b"R8  ");
pub const GR88: u32 = fourcc(b"GR88");
pub const NV12: u32 = fourcc(b"NV12");
pub const MOD_LINEAR: u64 = 0;
pub const MOD_INVALID: u64 = 0x00ff_ffff_ffff_ffff;

pub fn fourcc_str(f: u32) -> String {
    f.to_le_bytes().iter().map(|&b| char::from(b)).collect::<String>().trim_end().to_string()
}

/// The format table of zwp_linux_dmabuf_feedback_v1: 16 bytes an entry, u32 format, 4 bytes padding, u64 modifier.
pub fn parse_table(bytes: &[u8]) -> Vec<(u32, u64)> {
    bytes
        .chunks_exact(16)
        .map(|c| (u32::from_ne_bytes([c[0], c[1], c[2], c[3]]), u64::from_ne_bytes([c[8], c[9], c[10], c[11], c[12], c[13], c[14], c[15]])))
        .collect()
}

/// A tranche's `formats` array: u16 indices into the table.
pub fn tranche_indices(bytes: &[u8]) -> Vec<usize> {
    bytes.chunks_exact(2).map(|c| usize::from(u16::from_ne_bytes([c[0], c[1]]))).collect()
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PlaneRef {
    pub object: usize,
    pub offset: u32,
    pub pitch: u32,
}

/// One layer of a DRM PRIME descriptor.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Layer {
    pub format: u32,
    pub planes: Vec<PlaneRef>,
}

/// Y and CbCr: libva's separate layers (R8, GR88) or one NV12 layer of two planes.
pub fn nv12_planes(layers: &[Layer]) -> Result<[PlaneRef; 2], String> {
    match layers {
        [y, c] if y.format == R8 && c.format == GR88 && !y.planes.is_empty() && !c.planes.is_empty() => Ok([y.planes[0], c.planes[0]]),
        [l] if l.format == NV12 && l.planes.len() == 2 => Ok([l.planes[0], l.planes[1]]),
        _ => Err(format!(
            "a DRM PRIME picture of {} layers ({})",
            layers.len(),
            layers.iter().map(|l| format!("{} with {} planes", fourcc_str(l.format), l.planes.len())).collect::<Vec<_>>().join(", ")
        )),
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Path {
    /// The surface goes to h713-warp as NV12 with this modifier (one the table offers).
    Passthrough { modifier: u64 },
    /// The presenter converts into an RGB buffer of the panel's size; why the surface cannot go as it is.
    Convert(String),
}

/// Whether a decoded surface of `size` whose dma-buf has `modifier` may go to h713-warp as it is. h713-warp centres a
/// smaller picture and never scales, so that equals scale-to-fit only when one side is the panel's.
pub fn choose(table: &[(u32, u64)], modifier: u64, size: (u32, u32), panel: (u32, u32)) -> Path {
    let offered = |m: u64| table.contains(&(NV12, m));
    let modifier = match modifier {
        m if offered(m) => m,
        MOD_INVALID if offered(MOD_LINEAR) => MOD_LINEAR,
        m if table.iter().any(|&(f, _)| f == NV12) => return Path::Convert(format!("h713-warp offers NV12, not with modifier 0x{m:x}")),
        _ => return Path::Convert("h713-warp offers no NV12".into()),
    };
    let ((w, h), (pw, ph)) = (size, panel);
    if w == 0 || h == 0 || w > pw || h > ph {
        return Path::Convert(format!("{w}x{h} does not fit the panel {pw}x{ph}"));
    }
    if w != pw && h != ph {
        return Path::Convert(format!("{w}x{h} would stand unscaled in the panel {pw}x{ph}"));
    }
    Path::Passthrough { modifier }
}

#[cfg(test)]
mod tests {
    use super::*;

    const XR24: u32 = fourcc(b"XR24");
    const AFBC: u64 = 0x0800_0000_0000_0062;

    fn entry(f: u32, m: u64) -> Vec<u8> {
        [&f.to_ne_bytes()[..], &[0; 4], &m.to_ne_bytes()].concat()
    }

    #[test]
    fn the_feedback_table_and_a_tranche_parse() {
        let bytes = [entry(XR24, AFBC), entry(NV12, MOD_LINEAR), vec![1, 2, 3]].concat();
        assert_eq!(parse_table(&bytes), vec![(XR24, AFBC), (NV12, MOD_LINEAR)]);
        assert_eq!(tranche_indices(&[1, 0, 0, 0, 7]), vec![1, 0]);
    }

    #[test]
    fn todays_rgb_only_warp_gets_the_conversion() {
        let table = [(XR24, AFBC), (XR24, MOD_LINEAR)];
        assert_eq!(choose(&table, MOD_LINEAR, (1920, 1080), (1920, 1080)), Path::Convert("h713-warp offers no NV12".into()));
    }

    #[test]
    fn nv12_with_the_surfaces_modifier_goes_as_it_is() {
        let table = [(XR24, AFBC), (NV12, MOD_LINEAR)];
        assert_eq!(choose(&table, MOD_LINEAR, (1920, 1080), (1920, 1080)), Path::Passthrough { modifier: MOD_LINEAR });
        assert_eq!(choose(&table, MOD_INVALID, (1920, 1080), (1920, 1080)), Path::Passthrough { modifier: MOD_LINEAR }, "an implicit modifier is the linear layout cedrus writes");
        assert_eq!(choose(&table, MOD_LINEAR, (1920, 886), (1920, 1080)), Path::Passthrough { modifier: MOD_LINEAR }, "bars top and bottom: the same as scale-to-fit");
        assert!(matches!(choose(&table, AFBC, (1920, 1080), (1920, 1080)), Path::Convert(_)));
    }

    #[test]
    fn a_picture_the_warp_would_not_scale_is_converted() {
        let table = [(NV12, MOD_LINEAR)];
        assert!(matches!(choose(&table, MOD_LINEAR, (1280, 720), (1920, 1080)), Path::Convert(_)));
        assert!(matches!(choose(&table, MOD_LINEAR, (2532, 1170), (1920, 1080)), Path::Convert(_)));
    }

    #[test]
    fn both_layouts_of_a_drm_prime_picture_give_y_and_cbcr() {
        let p = |object, offset| PlaneRef { object, offset, pitch: 1920 };
        let separate = [Layer { format: R8, planes: vec![p(0, 0)] }, Layer { format: GR88, planes: vec![p(0, 1920 * 1088)] }];
        assert_eq!(nv12_planes(&separate), Ok([p(0, 0), p(0, 1920 * 1088)]));
        let composed = [Layer { format: NV12, planes: vec![p(0, 0), p(1, 0)] }];
        assert_eq!(nv12_planes(&composed), Ok([p(0, 0), p(1, 0)]));
        assert!(nv12_planes(&[Layer { format: R8, planes: vec![p(0, 0)] }]).is_err());
    }
}
