// SPDX-License-Identifier: GPL-3.0-only
//! Where the picture goes in the panel-size buffer: as large as fits, aspect kept, centred, black around it.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Rect {
    pub x: u32,
    pub y: u32,
    pub w: u32,
    pub h: u32,
}

pub fn fit(src_w: u32, src_h: u32, dst_w: u32, dst_h: u32) -> Rect {
    if src_w == 0 || src_h == 0 {
        return Rect { x: 0, y: 0, w: dst_w, h: dst_h };
    }
    let (sw, sh, dw, dh) = (u64::from(src_w), u64::from(src_h), u64::from(dst_w), u64::from(dst_h));
    let (w, h) = if sw * dh >= sh * dw { (dw, (dw * sh + sw / 2) / sw) } else { ((dh * sw + sh / 2) / sh, dh) };
    let (w, h) = (w.clamp(1, dw) as u32, h.clamp(1, dh) as u32);
    Rect { x: (dst_w - w) / 2, y: (dst_h - h) / 2, w, h }
}

impl Rect {
    pub fn covers(&self, w: u32, h: u32) -> bool {
        self.x == 0 && self.y == 0 && self.w == w && self.h == h
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_same_aspect_fills_the_panel() {
        assert!(fit(1920, 1080, 1920, 1080).covers(1920, 1080));
        assert!(fit(1280, 720, 1920, 1080).covers(1920, 1080));
    }

    #[test]
    fn a_narrower_picture_gets_bars_left_and_right() {
        assert_eq!(fit(1440, 1080, 1920, 1080), Rect { x: 240, y: 0, w: 1440, h: 1080 });
        assert_eq!(fit(886, 1920, 1920, 1080), Rect { x: 711, y: 0, w: 498, h: 1080 });
    }

    #[test]
    fn a_wider_picture_gets_bars_top_and_bottom() {
        assert_eq!(fit(1920, 886, 1920, 1080), Rect { x: 0, y: 97, w: 1920, h: 886 });
        assert_eq!(fit(2532, 1170, 1920, 1080), Rect { x: 0, y: 96, w: 1920, h: 887 });
    }

    #[test]
    fn no_size_yet_means_the_whole_panel() {
        assert_eq!(fit(0, 0, 1920, 1080), Rect { x: 0, y: 0, w: 1920, h: 1080 });
    }
}
