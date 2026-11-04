// SPDX-License-Identifier: GPL-3.0-only
//! The page's pixels: an ARGB8888 canvas (h713-osd's memfd, or a vector for `--render-png`), the design's units, and the
//! shapes drawn with antialiased coverage. Everything is drawn over the opaque ground, so every pixel stays opaque.

/// The launcher's ground (docs/tools/h713-osd.md, `launcher`).
pub const GROUND: u32 = 0xff0b_0e0d;
/// The launcher's lit pill on the opaque page.
pub const PILL: u32 = 0x1c_2321;
/// The text's colour, as libh713osd draws its labels.
pub const TEXT: u32 = 0xfa_fafa;

/// Pixel rows and columns, x y w h.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Rect {
    pub x: usize,
    pub y: usize,
    pub w: usize,
    pub h: usize,
}

pub struct Canvas<'a> {
    pub px: &'a mut [u32],
    pub w: usize,
    pub h: usize,
    /// In pixels (the pitch / 4).
    pub stride: usize,
}

/// The design's units: a 1920 x 1080 page, scaled by the panel's height and centred on a wider panel (h713-settings' U, XOFF).
#[derive(Clone, Copy, Debug)]
pub struct Units {
    pub u: f64,
    pub xoff: f64,
}

impl Units {
    pub fn of(w: usize, h: usize) -> Units {
        let u = h as f64 / 1080.0;
        Units { u, xoff: (w as f64 - 1920.0 * u) / 2.0 }
    }
    pub fn x(self, x: f64) -> f64 {
        x * self.u + self.xoff
    }
    pub fn y(self, y: f64) -> f64 {
        y * self.u
    }
    /// A band's edge in pixel rows, rounded once so bands that meet in units meet in pixels.
    pub fn row(self, y: f64) -> usize {
        (y * self.u + 0.5).floor().max(0.0) as usize
    }
}

/// `rgb` over the opaque pixel with coverage `a` (straight alpha over an opaque ground stays opaque).
fn blend(p: &mut u32, rgb: u32, a: f64) {
    if a <= 0.0 {
        return;
    }
    let a = a.min(1.0);
    let ch = |shift: u32| {
        let s = f64::from((rgb >> shift) & 255);
        let d = f64::from((*p >> shift) & 255);
        ((s * a + d * (1.0 - a)) + 0.5) as u32
    };
    *p = 0xff00_0000 | ch(16) << 16 | ch(8) << 8 | ch(0);
}

/// Drawing confined to one band: nothing outside `clip` is touched, so a band drawn again leaves its neighbours as they are.
pub struct Pen<'c, 'a> {
    pub c: &'c mut Canvas<'a>,
    pub clip: Rect,
    pub g: Units,
}

impl Pen<'_, '_> {
    /// The band's rectangle set to the ground.
    pub fn ground(&mut self) {
        let Rect { x, y, w, h } = self.clip;
        for row in y..y + h {
            self.c.px[row * self.c.stride + x..row * self.c.stride + x + w].fill(GROUND);
        }
    }

    /// Mix `rgb` at panel pixel (x, y) with coverage `a`, inside the clip only.
    pub fn mix(&mut self, x: i64, y: i64, rgb: u32, a: f64) {
        let r = self.clip;
        if x < r.x as i64 || y < r.y as i64 || x >= (r.x + r.w) as i64 || y >= (r.y + r.h) as i64 {
            return;
        }
        blend(&mut self.c.px[y as usize * self.c.stride + x as usize], rgb, a);
    }

    /// Coverage from a signed distance (in panel pixels, negative inside) over a box given in design units.
    fn shade(&mut self, b: [f64; 4], rgb: u32, alpha: f64, dist: impl Fn(f64, f64) -> f64) {
        let g = self.g;
        let (x0, y0) = (g.x(b[0]).floor() as i64 - 1, g.y(b[1]).floor() as i64 - 1);
        let (x1, y1) = (g.x(b[2]).ceil() as i64 + 1, g.y(b[3]).ceil() as i64 + 1);
        for y in y0.max(self.clip.y as i64)..y1.min((self.clip.y + self.clip.h) as i64) {
            for x in x0..x1 {
                let d = dist(x as f64 + 0.5, y as f64 + 0.5);
                let cov = (0.5 - d).clamp(0.0, 1.0);
                if cov > 0.0 {
                    self.mix(x, y, rgb, cov * alpha);
                }
            }
        }
    }

    /// A rounded box's signed distance at panel pixel (px, py): centre and half sizes in units.
    fn rbox(&self, c: (f64, f64), half: (f64, f64), r: f64) -> impl Fn(f64, f64) -> f64 {
        let g = self.g;
        let (cx, cy, hx, hy, r) = (g.x(c.0), g.y(c.1), half.0 * g.u, half.1 * g.u, r * g.u);
        move |px: f64, py: f64| {
            let qx = (px - cx).abs() - (hx - r);
            let qy = (py - cy).abs() - (hy - r);
            qx.max(0.0).hypot(qy.max(0.0)) + qx.max(qy).min(0.0) - r
        }
    }

    /// A filled pill (rounded rectangle) from x0, y0 to x1, y1 in units, the radius half its height.
    pub fn pill(&mut self, x0: f64, y0: f64, x1: f64, y1: f64, rgb: u32) {
        let d = self.rbox(((x0 + x1) / 2.0, (y0 + y1) / 2.0), ((x1 - x0) / 2.0, (y1 - y0) / 2.0), (y1 - y0) / 2.0);
        self.shade([x0, y0, x1, y1], rgb, 1.0, d);
    }

    /// The AirPlay symbol, the screen's top edge at `top`, centred at `cx`: a screen outline open at the foot where a
    /// triangle rises into it (the shape every Apple device shows for AirPlay), in the launcher's stroke.
    pub fn airplay(&mut self, cx: f64, top: f64, rgb: u32, alpha: f64) {
        let g = self.g;
        let (hw, hh, lw, gap) = (64.0, 42.0, 5.0, 30.0);
        let screen = self.rbox((cx, top + hh), (hw, hh), 12.0);
        let (lw_px, gap_px, cxp, foot) = (lw * g.u, gap * g.u, g.x(cx), g.y(top + hh));
        self.shade([cx - hw, top, cx + hw, top + 2.0 * hh], rgb, alpha, |x, y| {
            let ring = screen(x, y).abs() - lw_px / 2.0;
            // the gap in the bottom edge: below the middle, closer to the centre than the gap
            let cut = if y > foot { gap_px - (x - cxp).abs() } else { f64::MIN };
            ring.max(cut)
        });
        // the triangle: apex in the screen, base below it; signed distance as the largest of its three edges'
        let (apex, base, half) = ((g.x(cx), g.y(top + 52.0)), g.y(top + 106.0), 34.0 * g.u);
        let len = (half * half + (base - apex.1).powi(2)).sqrt();
        let (nx, ny) = ((base - apex.1) / len, half / len);
        self.shade([cx - 36.0, top + 50.0, cx + 36.0, top + 108.0], rgb, alpha, |x, y| {
            let dx = (x - apex.0).abs();
            let side = dx * nx + (apex.1 - y) * ny;
            side.max(y - base)
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_band_never_touches_its_neighbours() {
        let mut px = vec![0u32; 64 * 32];
        let mut c = Canvas { px: &mut px, w: 64, h: 32, stride: 64 };
        let clip = Rect { x: 0, y: 8, w: 64, h: 8 };
        let mut pen = Pen { c: &mut c, clip, g: Units::of(64, 32) };
        pen.ground();
        pen.pill(0.0, 0.0, 1920.0, 1080.0, PILL);
        for (i, p) in px.iter().enumerate() {
            let inside = (8..16).contains(&(i / 64));
            assert_eq!(*p >> 24, if inside { 0xff } else { 0 }, "pixel {i}");
        }
    }
}
