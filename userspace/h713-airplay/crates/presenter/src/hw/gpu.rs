// SPDX-License-Identifier: GPL-3.0-only
//! The render node, once: a GBM device on renderD128 allocates the panel-size buffers, and EGL on that same GBM
//! device (EGL_PLATFORM_GBM_KHR, a surfaceless GLES 3 context without a config) draws into them and imports the
//! decoder's dma-bufs. One device for both, so every buffer is the driver's own (panfrost).

use crate::sys;
use std::ffi::CStr;
use std::fs::{File, OpenOptions};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::fs::OpenOptionsExt;
use std::ptr;

pub use crate::dmabuf::{fourcc, MOD_INVALID, MOD_LINEAR};
pub const XRGB8888: u32 = fourcc(b"XR24");
pub const XBGR8888: u32 = fourcc(b"XB24");
pub const ARGB8888: u32 = fourcc(b"AR24");
pub const ABGR8888: u32 = fourcc(b"AB24");

pub fn is_afbc(m: u64) -> bool {
    m >> 56 == 0x08 && (m >> 52) & 0xf == 0
}

#[derive(Clone, Copy, Debug)]
pub struct Plane {
    pub fd: RawFd,
    pub offset: u32,
    pub pitch: u32,
    pub modifier: u64,
}

pub struct Gpu {
    _node: File,
    gbm: *mut sys::gbm_device,
    pub dpy: sys::EGLDisplay,
    ctx: sys::EGLContext,
    pub texture_from_image: unsafe extern "C" fn(sys::GLenum, sys::GLeglImageOES),
    pub renderbuffer_from_image: unsafe extern "C" fn(sys::GLenum, sys::GLeglImageOES),
}

fn has(exts: *const std::ffi::c_char, name: &str) -> bool {
    // SAFETY: an extension string from eglQueryString is NUL-terminated and static.
    !exts.is_null() && unsafe { CStr::from_ptr(exts) }.to_string_lossy().split(' ').any(|e| e == name)
}

fn proc(name: &CStr) -> Result<unsafe extern "C" fn(sys::GLenum, sys::GLeglImageOES), String> {
    // SAFETY: both extension entry points have this signature (OES_EGL_image).
    unsafe { sys::eglGetProcAddress(name.as_ptr()).map(|f| std::mem::transmute::<unsafe extern "C" fn(), _>(f)) }
        .ok_or_else(|| format!("no {}", name.to_string_lossy()))
}

impl Gpu {
    pub fn open(node: &str) -> Result<Gpu, String> {
        let file = OpenOptions::new().read(true).write(true).custom_flags(libc::O_CLOEXEC).open(node).map_err(|e| format!("{node}: {e}"))?;
        // SAFETY: EGL/GBM setup on a device we hold open; each result is checked, and Drop undoes what was made.
        unsafe {
            let gbm = sys::gbm_create_device(file.as_raw_fd());
            if gbm.is_null() {
                return Err(format!("gbm_create_device on {node}"));
            }
            let mut gpu = Gpu {
                _node: file,
                gbm,
                dpy: ptr::null_mut(),
                ctx: ptr::null_mut(),
                texture_from_image: proc(c"glEGLImageTargetTexture2DOES")?,
                renderbuffer_from_image: proc(c"glEGLImageTargetRenderbufferStorageOES")?,
            };
            gpu.dpy = sys::eglGetPlatformDisplay(sys::EGL_PLATFORM_GBM_KHR, gbm.cast(), ptr::null());
            let (mut major, mut minor) = (0, 0);
            if gpu.dpy.is_null() || sys::eglInitialize(gpu.dpy, &mut major, &mut minor) == 0 {
                return Err(format!("EGL on the GBM device: 0x{:x}", sys::eglGetError()));
            }
            let exts = sys::eglQueryString(gpu.dpy, sys::EGL_EXTENSIONS as i32);
            for e in ["EGL_EXT_image_dma_buf_import", "EGL_EXT_image_dma_buf_import_modifiers", "EGL_KHR_surfaceless_context", "EGL_KHR_no_config_context"] {
                if !has(exts, e) {
                    return Err(format!("EGL {major}.{minor} has no {e}"));
                }
            }
            sys::eglBindAPI(sys::EGL_OPENGL_ES_API);
            let attrs = [sys::EGL_CONTEXT_MAJOR_VERSION as i32, 3, sys::EGL_NONE as i32];
            gpu.ctx = sys::eglCreateContext(gpu.dpy, ptr::null_mut(), ptr::null_mut(), attrs.as_ptr());
            if gpu.ctx.is_null() || sys::eglMakeCurrent(gpu.dpy, ptr::null_mut(), ptr::null_mut(), gpu.ctx) == 0 {
                return Err(format!("a GLES 3 context: 0x{:x}", sys::eglGetError()));
            }
            Ok(gpu)
        }
    }

    pub fn renderer(&self) -> String {
        // SAFETY: glGetString returns a static string or null with a current context.
        let s = unsafe { sys::glGetString(sys::GL_RENDERER) };
        if s.is_null() { "?".into() } else { unsafe { CStr::from_ptr(s.cast()) }.to_string_lossy().into_owned() }
    }

    pub fn image(&self, w: u32, h: u32, fourcc: u32, p: &Plane) -> Result<sys::EGLImage, String> {
        let mut a: Vec<sys::EGLAttrib> = [
            (sys::EGL_WIDTH, w as isize),
            (sys::EGL_HEIGHT, h as isize),
            (sys::EGL_LINUX_DRM_FOURCC_EXT, fourcc as isize),
            (sys::EGL_DMA_BUF_PLANE0_FD_EXT, p.fd as isize),
            (sys::EGL_DMA_BUF_PLANE0_OFFSET_EXT, p.offset as isize),
            (sys::EGL_DMA_BUF_PLANE0_PITCH_EXT, p.pitch as isize),
        ]
        .iter()
        .flat_map(|&(k, v)| [k as isize, v])
        .collect();
        if p.modifier != MOD_INVALID {
            a.extend([sys::EGL_DMA_BUF_PLANE0_MODIFIER_LO_EXT as isize, (p.modifier & 0xffff_ffff) as isize]);
            a.extend([sys::EGL_DMA_BUF_PLANE0_MODIFIER_HI_EXT as isize, (p.modifier >> 32) as isize]);
        }
        a.push(sys::EGL_NONE as isize);
        // SAFETY: the attribute list ends in EGL_NONE; EGL dups what it keeps of the fd.
        let img = unsafe { sys::eglCreateImage(self.dpy, ptr::null_mut(), sys::EGL_LINUX_DMA_BUF_EXT, ptr::null_mut(), a.as_ptr()) };
        if img.is_null() {
            // SAFETY: no arguments.
            let e = unsafe { sys::eglGetError() };
            return Err(format!("EGL import of {w}x{h} {:?} pitch {} modifier 0x{:x}: 0x{e:x}", fourcc.to_le_bytes().map(char::from), p.pitch, p.modifier));
        }
        Ok(img)
    }

    pub fn destroy_image(&self, img: sys::EGLImage) {
        // SAFETY: an image of this display.
        unsafe { sys::eglDestroyImage(self.dpy, img) };
    }

    pub fn fence(&self) -> sys::EGLSync {
        // SAFETY: a fence sync on the current context; null on failure, which `done` takes as done.
        unsafe { sys::eglCreateSync(self.dpy, sys::EGL_SYNC_FENCE, ptr::null()) }
    }

    /// Whether the GPU has passed `sync`, waiting up to `ns`; the sync is gone when this says yes.
    pub fn done(&self, sync: sys::EGLSync, ns: u64) -> bool {
        if sync.is_null() {
            return true;
        }
        // SAFETY: a sync of this display, destroyed exactly once (here, when passed).
        unsafe {
            let r = sys::eglClientWaitSync(self.dpy, sync, 0, ns);
            if r == sys::EGL_TIMEOUT_EXPIRED as i32 {
                return false;
            }
            sys::eglDestroySync(self.dpy, sync);
            true
        }
    }

    pub fn bo(&self, w: u32, h: u32, fourcc: u32, modifiers: &[u64]) -> Result<Bo, String> {
        // SAFETY: GBM calls on our device; the bo is destroyed by Bo's Drop.
        unsafe {
            let raw = if modifiers.is_empty() {
                sys::gbm_bo_create(self.gbm, w, h, fourcc, sys::GBM_BO_USE_RENDERING)
            } else {
                sys::gbm_bo_create_with_modifiers2(self.gbm, w, h, fourcc, modifiers.as_ptr(), modifiers.len() as u32, sys::GBM_BO_USE_RENDERING)
            };
            if raw.is_null() {
                return Err(format!("a {w}x{h} buffer from GBM ({} modifiers offered)", modifiers.len()));
            }
            let fd = sys::gbm_bo_get_fd(raw);
            let bo = Bo {
                raw,
                fd: OwnedFd::from_raw_fd(fd.max(0)),
                w,
                h,
                fourcc,
                offset: sys::gbm_bo_get_offset(raw, 0),
                stride: sys::gbm_bo_get_stride_for_plane(raw, 0),
                modifier: sys::gbm_bo_get_modifier(raw),
            };
            if fd < 0 || sys::gbm_bo_get_plane_count(raw) != 1 {
                return Err("a GBM buffer without one dma-buf plane".into());
            }
            Ok(bo)
        }
    }
}

impl Drop for Gpu {
    fn drop(&mut self) {
        // SAFETY: undoes open in reverse; EGL takes null handles from a failed open.
        unsafe {
            if !self.dpy.is_null() {
                sys::eglMakeCurrent(self.dpy, ptr::null_mut(), ptr::null_mut(), ptr::null_mut());
                if !self.ctx.is_null() {
                    sys::eglDestroyContext(self.dpy, self.ctx);
                }
                sys::eglTerminate(self.dpy);
            }
            sys::gbm_device_destroy(self.gbm);
        }
    }
}

pub struct Bo {
    raw: *mut sys::gbm_bo,
    pub fd: OwnedFd,
    pub w: u32,
    pub h: u32,
    pub fourcc: u32,
    pub offset: u32,
    pub stride: u32,
    pub modifier: u64,
}

impl Bo {
    pub fn plane(&self) -> Plane {
        Plane { fd: self.fd.as_raw_fd(), offset: self.offset, pitch: self.stride, modifier: self.modifier }
    }
}

impl Drop for Bo {
    fn drop(&mut self) {
        // SAFETY: our bo, destroyed once.
        unsafe { sys::gbm_bo_destroy(self.raw) };
    }
}
