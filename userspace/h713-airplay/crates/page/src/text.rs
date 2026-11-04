// SPDX-License-Identifier: GPL-3.0-only
//! The face: Quicksand, as libh713osd's text.c sets it. A size is the em in pixels (FreeType at 72 dpi), glyphs are
//! unhinted and advance by their linear widths, so a word is as wide at 720 lines as at 1080, scaled.

use ab_glyph::{Font, FontVec, GlyphId, PxScale, ScaleFont};

use crate::canvas::Pen;

/// The face h713-osd draws the launcher with (`H713_OSD_FONT` overrides it).
pub const FONT: &str = "/usr/share/fonts/truetype/quicksand/Quicksand-Medium.ttf";

pub fn font_path() -> std::path::PathBuf {
    std::env::var_os("H713_OSD_FONT").map(Into::into).unwrap_or_else(|| FONT.into())
}

pub struct Face {
    font: FontVec,
}

impl Face {
    pub fn load(path: &std::path::Path) -> Result<Face, String> {
        let bytes = std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
        let font = FontVec::try_from_vec(bytes).map_err(|e| format!("{}: {e}", path.display()))?;
        Ok(Face { font })
    }

    /// ab_glyph's scale is the ascent-to-descent height; the em is what FreeType's char size names.
    fn scale(&self, em: f64) -> PxScale {
        let per_em = self.font.units_per_em().unwrap_or(1000.0);
        PxScale::from((em * f64::from(self.font.height_unscaled()) / f64::from(per_em)) as f32)
    }

    /// The pen positions of a string: (glyph, x offset from the start) and the whole advance.
    fn run(&self, s: &str, em: f64) -> (Vec<(GlyphId, f64)>, f64) {
        let sf = self.font.as_scaled(self.scale(em));
        let mut pen = 0.0;
        let mut prev: Option<GlyphId> = None;
        let mut out = Vec::with_capacity(s.len());
        for ch in s.chars() {
            let id = self.font.glyph_id(ch);
            if let Some(p) = prev {
                pen += f64::from(sf.kern(p, id));
            }
            out.push((id, pen));
            pen += f64::from(sf.h_advance(id));
            prev = Some(id);
        }
        (out, pen)
    }

    /// The advance of `s` at `em`, in the same units as `em`.
    pub fn width(&self, s: &str, em: f64) -> f64 {
        self.run(s, em).1
    }

    /// `s` cut with "..." so it is no wider than `max` (units as `em`).
    pub fn fit(&self, s: &str, em: f64, max: f64) -> String {
        if self.width(s, em) <= max {
            return s.to_string();
        }
        let chars: Vec<char> = s.chars().collect();
        (0..chars.len())
            .rev()
            .map(|n| format!("{}...", chars[..n].iter().collect::<String>().trim_end()))
            .find(|t| self.width(t, em) <= max)
            .unwrap_or_default()
    }

    /// Words laid into lines no wider than `max`; a word wider than a line stands alone on its own.
    pub fn wrap(&self, s: &str, em: f64, max: f64) -> Vec<String> {
        let mut lines: Vec<String> = Vec::new();
        for word in s.split_whitespace() {
            match lines.last_mut() {
                Some(l) if self.width(&format!("{l} {word}"), em) <= max => {
                    l.push(' ');
                    l.push_str(word);
                }
                _ => lines.push(word.to_string()),
            }
        }
        lines
    }

    /// Draw `s` with its baseline at `baseline`, starting at `x` (design units), `em` units high, white at `alpha`.
    pub fn draw(&self, pen: &mut Pen, s: &str, x: f64, baseline: f64, em: f64, alpha: f64) {
        let g = pen.g;
        let scale = self.scale(em * g.u);
        let (glyphs, _) = self.run(s, em * g.u);
        let (x0, y0) = (g.x(x), g.y(baseline));
        for (id, dx) in glyphs {
            let glyph = id.with_scale_and_position(scale, ab_glyph::point((x0 + dx) as f32, y0 as f32));
            let Some(outline) = self.font.outline_glyph(glyph) else { continue };
            let b = outline.px_bounds();
            outline.draw(|gx, gy, cov| {
                let (px, py) = (b.min.x as i64 + i64::from(gx), b.min.y as i64 + i64::from(gy));
                pen.mix(px, py, crate::canvas::TEXT, f64::from(cov) * alpha);
            });
        }
    }

    /// Draw `s` centred on `cx`.
    pub fn centred(&self, pen: &mut Pen, s: &str, cx: f64, baseline: f64, em: f64, alpha: f64) {
        self.draw(pen, s, cx - self.width(s, em) / 2.0, baseline, em, alpha);
    }
}
