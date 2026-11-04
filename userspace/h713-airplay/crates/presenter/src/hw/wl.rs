// SPDX-License-Identifier: GPL-3.0-only
//! The Wayland side: one fullscreen xdg toplevel on h713-warp's server, its size from the configure (the panel's),
//! the dma-buf format table from the default feedback, three wl_buffers made from our GBM buffers, a frame callback
//! and a presentation feedback per commit.

use super::gpu::Bo;
use crate::dmabuf::{self, PlaneRef};
use std::os::fd::{AsFd, AsRawFd, OwnedFd, RawFd};
use std::os::unix::net::UnixStream;
use std::path::Path;
use wayland_client::globals::registry_queue_init;
use wayland_client::protocol::{wl_buffer, wl_compositor, wl_surface};
use wayland_client::{Connection, EventQueue, QueueHandle};
use wayland_protocols::wp::linux_dmabuf::zv1::client::{zwp_linux_buffer_params_v1 as params, zwp_linux_dmabuf_v1 as linux_dmabuf};
use wayland_protocols::wp::presentation_time::client::wp_presentation;
use wayland_protocols::xdg::shell::client::{xdg_surface, xdg_toplevel, xdg_wm_base};

/// What a wl_buffer is: one of the GL path's panel-size buffers, a decoder frame lent as NV12, or the probe of the
/// first NV12 buffer of a surface set (made with `create`, so a refusal is a `failed` event and not a protocol error).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BufferId {
    Target(usize),
    Frame(u64),
    Probe,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Probe {
    Waiting,
    Created,
    Failed,
}

#[derive(Default)]
pub struct Events {
    pub probe: Option<Probe>,
    pub size: Option<(u32, u32)>,
    pub(super) configured: (i32, i32),
    pub(super) table: Vec<(u32, u64)>,
    pub(super) tranche: Vec<usize>,
    pub formats: Option<Vec<(u32, u64)>>,
    pub frame_done: bool,
    pub released: Vec<BufferId>,
    /// (arrival, presentation) in CLOCK_MONOTONIC microseconds; `None` for a discarded picture.
    pub presented: Vec<(u64, Option<u64>)>,
    pub closed: bool,
}

pub struct Wl {
    conn: Connection,
    queue: EventQueue<Events>,
    qh: QueueHandle<Events>,
    pub ev: Events,
    surface: wl_surface::WlSurface,
    xdg: xdg_surface::XdgSurface,
    top: xdg_toplevel::XdgToplevel,
    dmabuf: linux_dmabuf::ZwpLinuxDmabufV1,
    presentation: Option<wp_presentation::WpPresentation>,
}

/// One plane of a dma-buf as zwp_linux_buffer_params_v1.add takes it.
pub struct DmabufPlane<'a> {
    pub fd: &'a OwnedFd,
    pub at: PlaneRef,
    pub modifier: u64,
}

fn err(what: &str) -> impl Fn(&dyn std::fmt::Display) -> String + '_ {
    move |e| format!("{what}: {e}")
}

impl Wl {
    pub fn connect(path: &Path) -> Result<Wl, String> {
        let stream = UnixStream::connect(path).map_err(|e| format!("{}: {e}", path.display()))?;
        let conn = Connection::from_socket(stream).map_err(|e| err("Wayland")(&e))?;
        let (globals, queue) = registry_queue_init::<Events>(&conn).map_err(|e| err("Wayland registry")(&e))?;
        let qh = queue.handle();
        let compositor: wl_compositor::WlCompositor = globals.bind(&qh, 4..=6, ()).map_err(|e| err("wl_compositor v4")(&e))?;
        let wm: xdg_wm_base::XdgWmBase = globals.bind(&qh, 1..=5, ()).map_err(|e| err("xdg_wm_base")(&e))?;
        let dmabuf: linux_dmabuf::ZwpLinuxDmabufV1 = globals.bind(&qh, 4..=4, ()).map_err(|e| err("zwp_linux_dmabuf_v1 v4")(&e))?;
        let presentation = globals.bind(&qh, 1..=1, ()).ok();
        let surface = compositor.create_surface(&qh, ());
        let xdg = wm.get_xdg_surface(&surface, &qh, ());
        let top = xdg.get_toplevel(&qh, ());
        top.set_app_id("h713-airplay-show".into());
        top.set_title("AirPlay".into());
        surface.commit();
        let fb = dmabuf.get_default_feedback(&qh, ());
        let mut wl = Wl { conn, queue, qh, ev: Events { frame_done: true, ..Events::default() }, surface, xdg, top, dmabuf, presentation };
        let deadline = super::now_us() + 3_000_000;
        while wl.ev.size.is_none() || wl.ev.formats.is_none() {
            let left = deadline.saturating_sub(super::now_us());
            if left == 0 || wl.ev.closed {
                return Err("h713-warp gave no configure or no dma-buf format table within 3 s".into());
            }
            wl.pump(None, (left / 1000) as i32)?;
        }
        fb.destroy();
        Ok(wl)
    }

    pub fn target_buffer(&mut self, bo: &Bo, idx: usize) -> wl_buffer::WlBuffer {
        let p = self.dmabuf.create_params(&self.qh, ());
        p.add(bo.fd.as_fd(), 0, bo.offset, bo.stride, (bo.modifier >> 32) as u32, bo.modifier as u32);
        let b = p.create_immed(bo.w as i32, bo.h as i32, bo.fourcc, params::Flags::empty(), &self.qh, BufferId::Target(idx));
        p.destroy();
        b
    }

    fn nv12_params(&self, planes: &[DmabufPlane; 2]) -> params::ZwpLinuxBufferParamsV1 {
        let p = self.dmabuf.create_params(&self.qh, ());
        for (i, pl) in planes.iter().enumerate() {
            p.add(pl.fd.as_fd(), i as u32, pl.at.offset, pl.at.pitch, (pl.modifier >> 32) as u32, pl.modifier as u32);
        }
        p
    }

    /// A decoder frame as an NV12 wl_buffer of its visible size.
    pub fn nv12_buffer(&mut self, planes: &[DmabufPlane; 2], size: (u32, u32), id: u64) -> wl_buffer::WlBuffer {
        let p = self.nv12_params(planes);
        let b = p.create_immed(size.0 as i32, size.1 as i32, dmabuf::NV12, params::Flags::empty(), &self.qh, BufferId::Frame(id));
        p.destroy();
        b
    }

    /// Whether h713-warp takes such an NV12 buffer at all: `create` and its answer (within 1 s); the probe buffer goes.
    pub fn probe_nv12(&mut self, planes: &[DmabufPlane; 2], size: (u32, u32)) -> Result<bool, String> {
        let p = self.nv12_params(planes);
        self.ev.probe = Some(Probe::Waiting);
        p.create(size.0 as i32, size.1 as i32, dmabuf::NV12, params::Flags::empty());
        let deadline = super::now_us() + 1_000_000;
        while self.ev.probe == Some(Probe::Waiting) && super::now_us() < deadline {
            self.pump(None, 100)?;
        }
        p.destroy();
        Ok(self.ev.probe.take() == Some(Probe::Created))
    }

    pub fn commit(&mut self, buffer: &wl_buffer::WlBuffer, arrival_us: u64) {
        self.surface.attach(Some(buffer), 0, 0);
        self.surface.damage_buffer(0, 0, i32::MAX, i32::MAX);
        self.surface.frame(&self.qh, ());
        if let Some(p) = &self.presentation {
            p.feedback(&self.surface, &self.qh, arrival_us);
        }
        self.surface.commit();
        self.ev.frame_done = false;
    }

    /// Sends what is queued, waits up to `timeout_ms` (-1: no limit) for the server or `extra` and handles every
    /// event that came. True when `extra` is readable.
    pub fn pump(&mut self, extra: Option<RawFd>, timeout_ms: i32) -> Result<bool, String> {
        self.queue.dispatch_pending(&mut self.ev).map_err(|e| err("Wayland")(&e))?;
        self.conn.flush().map_err(|e| err("Wayland flush")(&e))?;
        let Some(guard) = self.queue.prepare_read() else {
            self.queue.dispatch_pending(&mut self.ev).map_err(|e| err("Wayland")(&e))?;
            return Ok(false);
        };
        let mut pfd = [
            libc::pollfd { fd: guard.connection_fd().as_raw_fd(), events: libc::POLLIN, revents: 0 },
            libc::pollfd { fd: extra.unwrap_or(-1), events: libc::POLLIN, revents: 0 },
        ];
        // SAFETY: two pollfds for the duration of the call; a negative fd is ignored by poll.
        let n = unsafe { libc::poll(pfd.as_mut_ptr(), 2, timeout_ms) };
        if n < 0 && std::io::Error::last_os_error().kind() != std::io::ErrorKind::Interrupted {
            return Err(format!("poll: {}", std::io::Error::last_os_error()));
        }
        if pfd[0].revents != 0 {
            match guard.read() {
                Ok(_) => {}
                Err(wayland_client::backend::WaylandError::Io(e)) if e.kind() == std::io::ErrorKind::WouldBlock => {}
                Err(e) => return Err(format!("the connection to h713-warp: {e}")),
            }
        } else {
            drop(guard);
        }
        self.queue.dispatch_pending(&mut self.ev).map_err(|e| err("Wayland")(&e))?;
        Ok(pfd[1].revents != 0)
    }

    pub fn close(self) {
        self.top.destroy();
        self.xdg.destroy();
        self.surface.destroy();
        self.dmabuf.destroy();
        let _ = self.conn.flush();
    }
}

