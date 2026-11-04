// SPDX-License-Identifier: GPL-3.0-only
//! A VAAPI surface as dma-bufs: mapped to DRM PRIME once per surface and the descriptors' fds kept (dup'ed), so every
//! later frame of that surface is the same dma-buf - the same inode, which h713-warp's import cache finds again.

use crate::dmabuf::{nv12_planes, Layer, PlaneRef};
use crate::sys::*;
use std::collections::hash_map::{Entry, HashMap};
use std::os::fd::{FromRawFd, OwnedFd};

pub struct Export {
    pub fds: Vec<OwnedFd>,
    pub modifiers: Vec<u64>,
    /// Y and CbCr.
    pub planes: [PlaneRef; 2],
}

impl Export {
    pub fn modifier(&self) -> u64 {
        self.modifiers[self.planes[0].object]
    }
}

fn layers(d: &AVDRMFrameDescriptor) -> Vec<Layer> {
    d.layers[..d.nb_layers.clamp(0, 4) as usize]
        .iter()
        .map(|l| Layer {
            format: l.format,
            planes: l.planes[..l.nb_planes.clamp(0, 4) as usize]
                .iter()
                .map(|p| PlaneRef { object: p.object_index as usize, offset: p.offset as u32, pitch: p.pitch as u32 })
                .collect(),
        })
        .collect()
}

fn export(f: &AVFrame) -> Result<Export, String> {
    // SAFETY: a DRM PRIME mapping of a VAAPI frame, read while the mapping lives; its fds are dup'ed before
    // av_frame_free closes them.
    unsafe {
        let mut map = av_frame_alloc();
        if map.is_null() {
            return Err("out of memory".into());
        }
        (*map).format = AV_PIX_FMT_DRM_PRIME;
        let r = av_hwframe_map(map, f, AV_HWFRAME_MAP_READ as i32);
        let out = if r < 0 {
            Err(format!("av_hwframe_map to DRM PRIME: {}", super::av_error(r)))
        } else {
            let d = &*((*map).data[0] as *const AVDRMFrameDescriptor);
            let objects = &d.objects[..d.nb_objects.clamp(0, 4) as usize];
            let planes = nv12_planes(&layers(d)).and_then(|p| match p.iter().all(|x| x.object < objects.len()) {
                true => Ok(p),
                false => Err("a plane names an object the descriptor does not have".into()),
            });
            planes.and_then(|planes| {
                let fds = objects
                    .iter()
                    .map(|o| match libc::fcntl(o.fd, libc::F_DUPFD_CLOEXEC, 0) {
                        fd if fd >= 0 => Ok(OwnedFd::from_raw_fd(fd)),
                        _ => Err(format!("dup of a dma-buf: {}", std::io::Error::last_os_error())),
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                Ok(Export { fds, modifiers: objects.iter().map(|o| o.format_modifier).collect(), planes })
            })
        };
        av_frame_free(&mut map);
        out
    }
}

/// The exports of the decoder's current surface pool; a new pool (a new frames context) starts again.
#[derive(Default)]
pub struct Exports {
    frames_ctx: usize,
    by_surface: HashMap<usize, Export>,
}

impl Exports {
    pub fn get(&mut self, f: &AVFrame) -> Result<&Export, String> {
        let ctx = f.hw_frames_ctx as usize;
        if ctx != self.frames_ctx {
            self.by_surface.clear();
            self.frames_ctx = ctx;
        }
        let surface = f.data[3] as usize;
        match self.by_surface.entry(surface) {
            Entry::Occupied(o) => Ok(o.into_mut()),
            Entry::Vacant(v) => Ok(v.insert(export(f)?)),
        }
    }
}
