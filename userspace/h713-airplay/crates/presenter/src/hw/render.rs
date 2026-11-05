// SPDX-License-Identifier: GPL-3.0-only
//! One decoded picture into one panel-size RGB buffer: cleared black, the picture scaled to fit (aspect kept) and
//! converted from Y'CbCr in a fragment shader (three multiply-adds with the offsets folded into one bias: on the
//! Mali-G31 every operation after the fetch costs, 14 against 20 ms a 1080p frame at 200-300 MHz, measured 05.11.2026). A VAAPI surface is imported as two images, Y as R8 and CbCr as
//! GR88, once per surface (cached by surface id); a software picture is uploaded into R8 textures.

use super::export::Exports;
use super::gpu::{Bo, Gpu, Plane};
use crate::dmabuf::{GR88, R8};
use std::os::fd::AsRawFd;
use super::slot::Frame;
use crate::colour::{self, Conversion, Matrix};
use crate::fit::fit;
use crate::sys::*;
use std::collections::HashMap;
use std::ffi::CString;
use std::ptr;

const VS: &str = "#version 300 es\nin vec2 pos;\nout highp vec2 uv;\nvoid main() { uv = pos * 0.5 + 0.5; gl_Position = vec4(pos, 0.0, 1.0); }\n";
const FS_NV12: &str = "#version 300 es\nprecision mediump float;\nuniform sampler2D ty;\nuniform sampler2D tc;\nuniform mat3 m;\nuniform vec3 bias;\nin highp vec2 uv;\nout vec4 rgb;\nvoid main() { vec2 c = texture(tc, uv).rg; rgb = vec4(texture(ty, uv).r * m[0] + c.x * m[1] + (c.y * m[2] + bias), 1.0); }\n";
const FS_I420: &str = "#version 300 es\nprecision mediump float;\nuniform sampler2D ty;\nuniform sampler2D tc;\nuniform sampler2D tv;\nuniform mat3 m;\nuniform vec3 bias;\nin highp vec2 uv;\nout vec4 rgb;\nvoid main() { rgb = vec4(texture(ty, uv).r * m[0] + texture(tc, uv).r * m[1] + (texture(tv, uv).r * m[2] + bias), 1.0); }\n";

struct Program {
    id: GLuint,
    m: GLint,
    bias: GLint,
}

fn compile(kind: GLenum, src: &str) -> Result<GLuint, String> {
    let c = CString::new(src).map_err(|_| "a shader with a NUL")?;
    // SAFETY: GL calls on the current context with a NUL-terminated source.
    unsafe {
        let s = glCreateShader(kind);
        glShaderSource(s, 1, &c.as_ptr(), ptr::null());
        glCompileShader(s);
        let mut ok = 0;
        glGetShaderiv(s, GL_COMPILE_STATUS, &mut ok);
        if ok == 0 {
            let mut log = [0u8; 512];
            glGetShaderInfoLog(s, 512, ptr::null_mut(), log.as_mut_ptr().cast());
            return Err(format!("shader: {}", String::from_utf8_lossy(&log).trim_end_matches('\0')));
        }
        Ok(s)
    }
}

impl Program {
    fn new(fs: &str, samplers: &[&std::ffi::CStr]) -> Result<Program, String> {
        let (v, f) = (compile(GL_VERTEX_SHADER, VS)?, compile(GL_FRAGMENT_SHADER, fs)?);
        // SAFETY: GL calls on the current context.
        unsafe {
            let id = glCreateProgram();
            glAttachShader(id, v);
            glAttachShader(id, f);
            glBindAttribLocation(id, 0, c"pos".as_ptr());
            glLinkProgram(id);
            let mut ok = 0;
            glGetProgramiv(id, GL_LINK_STATUS, &mut ok);
            if ok == 0 {
                return Err("a shader program did not link".into());
            }
            glUseProgram(id);
            for (unit, name) in samplers.iter().enumerate() {
                glUniform1i(glGetUniformLocation(id, name.as_ptr()), unit as GLint);
            }
            Ok(Program { id, m: glGetUniformLocation(id, c"m".as_ptr()), bias: glGetUniformLocation(id, c"bias".as_ptr()) })
        }
    }
}

pub struct Target {
    pub bo: Bo,
    fbo: GLuint,
}

struct Imported {
    images: [EGLImage; 2],
    tex: [GLuint; 2],
}

pub struct Renderer {
    nv12: Program,
    i420: Program,
    vbo: GLuint,
    sw: [GLuint; 3],
    frames_ctx: usize,
    cache: HashMap<usize, Imported>,
    pub hw_import_failed: Option<String>,
}

fn texture() -> GLuint {
    let mut t = 0;
    // SAFETY: GL calls on the current context.
    unsafe {
        glGenTextures(1, &mut t);
        glBindTexture(GL_TEXTURE_2D, t);
        for (k, v) in [(GL_TEXTURE_MIN_FILTER, GL_LINEAR), (GL_TEXTURE_MAG_FILTER, GL_LINEAR), (GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE), (GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)] {
            glTexParameteri(GL_TEXTURE_2D, k, v as GLint);
        }
    }
    t
}

fn conversion_of(f: &AVFrame) -> Conversion {
    let matrix = match f.colorspace {
        AVCOL_SPC_BT709 => Matrix::Bt709,
        AVCOL_SPC_BT470BG | AVCOL_SPC_SMPTE170M => Matrix::Bt601,
        _ => colour::guess(f.height as u32),
    };
    colour::conversion(matrix, f.color_range == AVCOL_RANGE_JPEG)
}

impl Renderer {
    pub fn new() -> Result<Renderer, String> {
        let nv12 = Program::new(FS_NV12, &[c"ty", c"tc"])?;
        let i420 = Program::new(FS_I420, &[c"ty", c"tc", c"tv"])?;
        let quad: [f32; 8] = [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0];
        let mut vbo = 0;
        // SAFETY: GL calls on the current context; the data is copied by glBufferData.
        unsafe {
            glGenBuffers(1, &mut vbo);
            glBindBuffer(GL_ARRAY_BUFFER, vbo);
            glBufferData(GL_ARRAY_BUFFER, 32, quad.as_ptr().cast(), GL_STATIC_DRAW);
            glVertexAttribPointer(0, 2, GL_FLOAT, 0, 0, ptr::null());
            glEnableVertexAttribArray(0);
        }
        Ok(Renderer { nv12, i420, vbo, sw: [texture(), texture(), texture()], frames_ctx: 0, cache: HashMap::new(), hw_import_failed: None })
    }

    pub fn target(&self, gpu: &Gpu, bo: Bo) -> Result<Target, String> {
        let img = gpu.image(bo.w, bo.h, bo.fourcc, &bo.plane())?;
        let (mut rb, mut fbo) = (0, 0);
        // SAFETY: GL calls on the current context; the image lives as long as the renderbuffer uses it.
        unsafe {
            glGenRenderbuffers(1, &mut rb);
            glBindRenderbuffer(GL_RENDERBUFFER, rb);
            (gpu.renderbuffer_from_image)(GL_RENDERBUFFER, img);
            glGenFramebuffers(1, &mut fbo);
            glBindFramebuffer(GL_FRAMEBUFFER, fbo);
            glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, rb);
            let status = glCheckFramebufferStatus(GL_FRAMEBUFFER);
            if status != GL_FRAMEBUFFER_COMPLETE {
                return Err(format!("the panel-size buffer as a render target: 0x{status:x}"));
            }
        }
        Ok(Target { bo, fbo })
    }

    fn flush_cache(&mut self, gpu: &Gpu) {
        for (_, imp) in self.cache.drain() {
            // SAFETY: textures of the current context.
            unsafe { glDeleteTextures(2, imp.tex.as_ptr()) };
            imp.images.into_iter().for_each(|i| gpu.destroy_image(i));
        }
    }

    fn import(&mut self, gpu: &Gpu, f: &AVFrame, exports: &mut Exports) -> Result<[GLuint; 2], String> {
        let ctx = f.hw_frames_ctx as usize;
        if ctx != self.frames_ctx || self.cache.len() > 32 {
            self.flush_cache(gpu);
            self.frames_ctx = ctx;
        }
        let surface = f.data[3] as usize;
        if let Some(imp) = self.cache.get(&surface) {
            return Ok(imp.tex);
        }
        let (w, h) = (f.width as u32, f.height as u32);
        let e = exports.get(f)?;
        let plane = |i: usize| {
            let p = e.planes[i];
            Plane { fd: e.fds[p.object].as_raw_fd(), offset: p.offset, pitch: p.pitch, modifier: e.modifiers[p.object] }
        };
        let iy = gpu.image(w, h, R8, &plane(0))?;
        let ic = gpu.image(w.div_ceil(2), h.div_ceil(2), GR88, &plane(1)).inspect_err(|_| gpu.destroy_image(iy))?;
        let images = [iy, ic];
        let tex = [texture(), texture()];
        // SAFETY: GL calls on the current context; the images live in the cache as long as the textures.
        unsafe {
            for (t, i) in tex.iter().zip(images) {
                glBindTexture(GL_TEXTURE_2D, *t);
                (gpu.texture_from_image)(GL_TEXTURE_2D, i);
            }
        }
        self.cache.insert(surface, Imported { images, tex });
        Ok(tex)
    }

    fn upload(&self, f: &AVFrame) -> Result<&Program, String> {
        let (w, h) = (f.width, f.height);
        let (cw, ch) = ((w + 1) / 2, (h + 1) / 2);
        let planes: &[(GLenum, GLint, GLint, usize)] = match f.format {
            AV_PIX_FMT_YUV420P | AV_PIX_FMT_YUVJ420P => &[(GL_R8, w, h, 1), (GL_R8, cw, ch, 1), (GL_R8, cw, ch, 1)],
            AV_PIX_FMT_NV12 => &[(GL_R8, w, h, 1), (GL_RG8, cw, ch, 2)],
            other => return Err(format!("software pictures in pixel format {other}")),
        };
        // SAFETY: each plane is linesize x rows bytes of the frame; GL copies it.
        unsafe {
            for (i, &(fmt, pw, ph, bpp)) in planes.iter().enumerate() {
                glActiveTexture(GL_TEXTURE0 + i as GLenum);
                glBindTexture(GL_TEXTURE_2D, self.sw[i]);
                glPixelStorei(GL_UNPACK_ROW_LENGTH, f.linesize[i] / bpp as GLint);
                let client = if bpp == 2 { GL_RG } else { GL_RED };
                glTexImage2D(GL_TEXTURE_2D, 0, fmt as GLint, pw, ph, 0, client, GL_UNSIGNED_BYTE, f.data[i].cast());
            }
            glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
        }
        Ok(if planes.len() == 3 { &self.i420 } else { &self.nv12 })
    }

    pub fn draw(&mut self, gpu: &Gpu, target: &Target, frame: &Frame, exports: &mut Exports) -> Result<(), String> {
        let f = frame.get();
        let (pw, ph) = (target.bo.w, target.bo.h);
        let rect = fit(f.width as u32, f.height as u32, pw, ph);
        let program_id;
        let conv = conversion_of(f);
        // SAFETY: GL calls on the current context; the frame outlives the draw (the caller keeps it until a fence).
        unsafe {
            glBindFramebuffer(GL_FRAMEBUFFER, target.fbo);
            glViewport(0, 0, pw as GLint, ph as GLint);
            glClearColor(0.0, 0.0, 0.0, 1.0);
            glClear(GL_COLOR_BUFFER_BIT);
            let imported = match (frame.is_hw(), &self.hw_import_failed) {
                (true, None) => match self.import(gpu, f, exports) {
                    Ok(tex) => Some(tex),
                    Err(e) => {
                        eprintln!("h713-airplay-show: {e}; the pictures are copied out of the decoder from now on");
                        self.hw_import_failed = Some(e);
                        None
                    }
                },
                _ => None,
            };
            if let Some(tex) = imported {
                for (i, t) in tex.iter().enumerate() {
                    glActiveTexture(GL_TEXTURE0 + i as GLenum);
                    glBindTexture(GL_TEXTURE_2D, *t);
                }
                program_id = (self.nv12.id, self.nv12.m, self.nv12.bias);
            } else if frame.is_hw() {
                let sw = av_frame_alloc();
                let r = av_hwframe_transfer_data(sw, f, 0);
                let p = if r < 0 { Err(format!("copying a picture out of the decoder: {}", super::av_error(r))) } else { self.upload(&*sw).map(|p| (p.id, p.m, p.bias)) };
                let mut sw = sw;
                av_frame_free(&mut sw);
                program_id = p?;
            } else {
                let p = self.upload(f)?;
                program_id = (p.id, p.m, p.bias);
            }
            glUseProgram(program_id.0);
            glUniformMatrix3fv(program_id.1, 1, 0, conv.m.as_ptr());
            let bias = conv.apply([0.0; 3]);
            glUniform3f(program_id.2, bias[0], bias[1], bias[2]);
            glViewport(rect.x as GLint, rect.y as GLint, rect.w as GLint, rect.h as GLint);
            glBindBuffer(GL_ARRAY_BUFFER, self.vbo);
            glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
        }
        Ok(())
    }
}
