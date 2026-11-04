// SPDX-License-Identifier: GPL-3.0-only
//! The conversion path: the picture drawn scaled to fit into one of four panel-size RGB buffers of our own (GBM,
//! AFBC when h713-warp offers it) and that buffer committed. For an h713-warp without NV12, a software picture, a
//! picture h713-warp would not scale. A decoded picture is kept until the GPU has read it (an EGL fence).

use super::export::Exports;
use super::gpu::{self, is_afbc, Gpu, MOD_INVALID, MOD_LINEAR};
use super::render::{Renderer, Target};
use super::slot::Frame;
use super::wl::Wl;
use crate::sys;
use std::collections::VecDeque;
use wayland_client::protocol::wl_buffer::WlBuffer;

const BUFFERS: usize = 4;

/// Candidate modifier lists for one RGB format, best first: AFBC (what h713-warp reads cheapest), LINEAR, any.
fn candidates(formats: &[(u32, u64)]) -> Vec<(u32, Vec<u64>)> {
    let mut out = Vec::new();
    for f in [gpu::XRGB8888, gpu::XBGR8888, gpu::ARGB8888, gpu::ABGR8888] {
        let mods: Vec<u64> = formats.iter().filter(|&&(ff, m)| ff == f && m != MOD_INVALID).map(|&(_, m)| m).collect();
        let afbc: Vec<u64> = mods.iter().copied().filter(|&m| is_afbc(m)).collect();
        if !afbc.is_empty() {
            out.push((f, afbc));
        }
        if mods.contains(&MOD_LINEAR) {
            out.push((f, vec![MOD_LINEAR]));
        }
    }
    out
}

fn targets(gpu: &Gpu, r: &Renderer, formats: &[(u32, u64)], w: u32, h: u32) -> Result<Vec<Target>, String> {
    let mut why = String::from("h713-warp offers no XRGB/XBGR/ARGB/ABGR8888 dma-buf format");
    for (fourcc, mods) in candidates(formats) {
        let made: Result<Vec<Target>, String> = (0..BUFFERS)
            .map(|_| {
                let bo = gpu.bo(w, h, fourcc, &mods)?;
                if !formats.contains(&(fourcc, bo.modifier)) {
                    return Err(format!("GBM chose modifier 0x{:x}, which h713-warp does not offer", bo.modifier));
                }
                r.target(gpu, bo)
            })
            .collect();
        match made {
            Ok(t) => return Ok(t),
            Err(e) => why = e,
        }
    }
    Err(why)
}



/// `H713_AIRPLAY_SHOW_TRACE=1`: each draw waits for the GPU (glFinish) and the means go to stderr every 60 draws.
#[derive(Default)]
struct Trace {
    on: bool,
    cpu_us: u64,
    gpu_us: u64,
    n: u64,
}

impl Trace {
    fn note(&mut self, t0: u64, t1: u64) {
        if !self.on {
            return;
        }
        // SAFETY: waits for the current context's work.
        unsafe { sys::glFinish() };
        let t2 = super::now_us();
        self.cpu_us += t1 - t0;
        self.gpu_us += t2 - t1;
        self.n += 1;
        if self.n == 60 {
            eprintln!("h713-airplay-show: trace: draw {} us on the CPU, then {} us until the GPU is done (means of 60)", self.cpu_us / 60, self.gpu_us / 60);
            *self = Trace { on: true, ..Trace::default() };
        }
    }
}

/// Fields drop in this order: the buffers and the drawn pictures before the GPU (gbm_bo_destroy needs the device).
pub struct GlPath {
    drawn: VecDeque<(Frame, sys::EGLSync)>,
    targets: Vec<Target>,
    renderer: Renderer,
    buffers: Vec<WlBuffer>,
    free: Vec<bool>,
    trace: Trace,
    pub what: String,
    gpu: Gpu,
}

impl GlPath {
    pub fn open(wl: &mut Wl, formats: &[(u32, u64)], (w, h): (u32, u32)) -> Result<GlPath, String> {
        let gpu = Gpu::open("/dev/dri/renderD128")?;
        let renderer = Renderer::new()?;
        let targets = targets(&gpu, &renderer, formats, w, h)?;
        let buffers = targets.iter().enumerate().map(|(i, t)| wl.target_buffer(&t.bo, i)).collect();
        let b = &targets[0].bo;
        let what = format!("{}, {} modifier 0x{:x}", gpu.renderer(), crate::dmabuf::fourcc_str(b.fourcc), b.modifier);
        let trace = Trace { on: std::env::var_os("H713_AIRPLAY_SHOW_TRACE").is_some(), ..Trace::default() };
        Ok(GlPath { gpu, renderer, free: vec![true; targets.len()], targets, buffers, drawn: VecDeque::new(), trace, what })
    }

    pub fn released(&mut self, i: usize) {
        if let Some(f) = self.free.get_mut(i) {
            *f = true;
        }
    }

    /// The decoded pictures the GPU has read go back to the decoder.
    pub fn retire(&mut self) {
        while let Some((_, sync)) = self.drawn.front() {
            let wait = if self.drawn.len() > BUFFERS + 1 { 50_000_000 } else { 0 };
            if !self.gpu.done(*sync, wait) {
                return;
            }
            self.drawn.pop_front();
        }
    }

    /// Draws `frame` into a free buffer and commits it; `Ok(false)`: no buffer is free, the picture is not shown.
    pub fn present(&mut self, wl: &mut Wl, frame: Frame, exports: &mut Exports) -> Result<bool, String> {
        let Some(i) = self.free.iter().position(|&f| f) else { return Ok(false) };
        let t0 = super::now_us();
        self.renderer.draw(&self.gpu, &self.targets[i], &frame, exports)?;
        let sync = self.gpu.fence();
        // SAFETY: submits the draw on the current context.
        unsafe { sys::glFlush() };
        self.trace.note(t0, super::now_us());
        self.free[i] = false;
        wl.commit(&self.buffers[i], frame.arrival_us());
        self.drawn.push_back((frame, sync));
        Ok(true)
    }

    pub fn close(self) {
        self.buffers.iter().for_each(WlBuffer::destroy);
    }
}
