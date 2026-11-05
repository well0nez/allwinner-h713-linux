// SPDX-License-Identifier: GPL-3.0-only
//! Y'CbCr to R'G'B' for the shader: the matrix the stream's VUI names (BT.709, else BT.601), limited or full range.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Matrix {
    Bt601,
    Bt709,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Conversion {
    /// Column-major, as `glUniformMatrix3fv` takes it with `transpose = GL_FALSE`.
    pub m: [f32; 9],
    pub offset: [f32; 3],
}

/// A picture without a usable colour description: BT.709 from 720 lines up, BT.601 below (what players assume).
pub fn guess(height: u32) -> Matrix {
    if height >= 720 { Matrix::Bt709 } else { Matrix::Bt601 }
}

pub fn conversion(matrix: Matrix, full_range: bool) -> Conversion {
    let (kr, kb) = match matrix {
        Matrix::Bt601 => (0.299f32, 0.114f32),
        Matrix::Bt709 => (0.2126, 0.0722),
    };
    let kg = 1.0 - kr - kb;
    let (ys, cs, y0) = if full_range { (1.0, 1.0, 0.0) } else { (255.0 / 219.0, 255.0 / 224.0, 16.0 / 255.0) };
    let rv = 2.0 * (1.0 - kr);
    let bu = 2.0 * (1.0 - kb);
    let gu = -bu * kb / kg;
    let gv = -rv * kr / kg;
    Conversion {
        m: [ys, ys, ys, 0.0, gu * cs, bu * cs, rv * cs, gv * cs, 0.0],
        offset: [y0, 128.0 / 255.0, 128.0 / 255.0],
    }
}

impl Conversion {
    pub fn apply(&self, yuv: [f32; 3]) -> [f32; 3] {
        let v = [yuv[0] - self.offset[0], yuv[1] - self.offset[1], yuv[2] - self.offset[2]];
        let m = &self.m;
        [0, 1, 2].map(|r| m[r] * v[0] + m[3 + r] * v[1] + m[6 + r] * v[2])
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn close(a: [f32; 3], b: [f32; 3]) -> bool {
        a.iter().zip(b).all(|(x, y)| (x - y).abs() < 1.5 / 255.0)
    }

    fn px(y: u8, u: u8, v: u8) -> [f32; 3] {
        [y, u, v].map(|c| f32::from(c) / 255.0)
    }

    #[test]
    fn limited_range_black_and_white_reach_the_ends() {
        for m in [Matrix::Bt601, Matrix::Bt709] {
            let c = conversion(m, false);
            assert!(close(c.apply(px(16, 128, 128)), [0.0; 3]));
            assert!(close(c.apply(px(235, 128, 128)), [1.0; 3]));
        }
    }

    #[test]
    fn bt709_limited_red_is_red() {
        assert!(close(conversion(Matrix::Bt709, false).apply(px(63, 102, 240)), [1.0, 0.0, 0.0]));
        assert!(close(conversion(Matrix::Bt601, false).apply(px(81, 90, 240)), [1.0, 0.0, 0.0]));
    }

    #[test]
    fn full_range_white_is_255() {
        assert!(close(conversion(Matrix::Bt709, true).apply(px(255, 128, 128)), [1.0; 3]));
    }
}
