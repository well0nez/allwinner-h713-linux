// SPDX-License-Identifier: GPL-3.0-only
//! The events of h713-warp's objects into `wl::Events`.

use super::wl::{BufferId, Events, Probe};
use crate::dmabuf;
use std::os::fd::{AsRawFd, OwnedFd};
use wayland_client::globals::GlobalListContents;
use wayland_client::protocol::{wl_buffer, wl_callback, wl_compositor, wl_registry, wl_surface};
use wayland_client::{delegate_noop, event_created_child, Connection, Dispatch, QueueHandle};
use wayland_protocols::wp::linux_dmabuf::zv1::client::{zwp_linux_buffer_params_v1 as params, zwp_linux_dmabuf_feedback_v1 as feedback, zwp_linux_dmabuf_v1 as linux_dmabuf};
use wayland_protocols::wp::presentation_time::client::{wp_presentation, wp_presentation_feedback as pfb};
use wayland_protocols::xdg::shell::client::{xdg_surface, xdg_toplevel, xdg_wm_base};

delegate_noop!(Events: wl_compositor::WlCompositor);
delegate_noop!(Events: ignore wl_surface::WlSurface);
delegate_noop!(Events: ignore linux_dmabuf::ZwpLinuxDmabufV1);

impl Dispatch<params::ZwpLinuxBufferParamsV1, ()> for Events {
    fn event(ev: &mut Self, _: &params::ZwpLinuxBufferParamsV1, e: params::Event, _: &(), _: &Connection, _: &QueueHandle<Self>) {
        match e {
            params::Event::Created { buffer } => {
                buffer.destroy();
                ev.probe = Some(Probe::Created);
            }
            params::Event::Failed => ev.probe = Some(Probe::Failed),
            _ => {}
        }
    }

    event_created_child!(Events, params::ZwpLinuxBufferParamsV1, [
        params::EVT_CREATED_OPCODE => (wl_buffer::WlBuffer, BufferId::Probe),
    ]);
}
delegate_noop!(Events: ignore wp_presentation::WpPresentation);

impl Dispatch<wl_registry::WlRegistry, GlobalListContents> for Events {
    fn event(_: &mut Self, _: &wl_registry::WlRegistry, _: wl_registry::Event, _: &GlobalListContents, _: &Connection, _: &QueueHandle<Self>) {}
}

impl Dispatch<xdg_wm_base::XdgWmBase, ()> for Events {
    fn event(_: &mut Self, wm: &xdg_wm_base::XdgWmBase, e: xdg_wm_base::Event, _: &(), _: &Connection, _: &QueueHandle<Self>) {
        if let xdg_wm_base::Event::Ping { serial } = e {
            wm.pong(serial);
        }
    }
}

impl Dispatch<xdg_surface::XdgSurface, ()> for Events {
    fn event(ev: &mut Self, s: &xdg_surface::XdgSurface, e: xdg_surface::Event, _: &(), _: &Connection, _: &QueueHandle<Self>) {
        if let xdg_surface::Event::Configure { serial } = e {
            s.ack_configure(serial);
            if let (w @ 1.., h @ 1..) = ev.configured {
                ev.size = Some((w as u32, h as u32));
            }
        }
    }
}

impl Dispatch<xdg_toplevel::XdgToplevel, ()> for Events {
    fn event(ev: &mut Self, _: &xdg_toplevel::XdgToplevel, e: xdg_toplevel::Event, _: &(), _: &Connection, _: &QueueHandle<Self>) {
        match e {
            xdg_toplevel::Event::Configure { width, height, .. } => ev.configured = (width, height),
            xdg_toplevel::Event::Close => ev.closed = true,
            _ => {}
        }
    }
}

fn read_table(fd: &OwnedFd, size: u32) -> Vec<(u32, u64)> {
    let len = size as usize;
    // SAFETY: a read-only private mapping of the table the server sent, unmapped before returning.
    unsafe {
        let p = libc::mmap(std::ptr::null_mut(), len, libc::PROT_READ, libc::MAP_PRIVATE, fd.as_raw_fd(), 0);
        if p == libc::MAP_FAILED {
            return Vec::new();
        }
        let t = dmabuf::parse_table(std::slice::from_raw_parts(p.cast::<u8>(), len));
        libc::munmap(p, len);
        t
    }
}

impl Dispatch<feedback::ZwpLinuxDmabufFeedbackV1, ()> for Events {
    fn event(ev: &mut Self, _: &feedback::ZwpLinuxDmabufFeedbackV1, e: feedback::Event, _: &(), _: &Connection, _: &QueueHandle<Self>) {
        match e {
            feedback::Event::FormatTable { fd, size } => ev.table = read_table(&fd, size),
            feedback::Event::TrancheFormats { indices } => ev.tranche.extend(dmabuf::tranche_indices(&indices)),
            feedback::Event::Done => {
                let all: Vec<usize> = if ev.tranche.is_empty() { (0..ev.table.len()).collect() } else { std::mem::take(&mut ev.tranche) };
                ev.formats = Some(all.into_iter().filter_map(|i| ev.table.get(i).copied()).collect());
            }
            _ => {}
        }
    }
}

impl Dispatch<wl_buffer::WlBuffer, BufferId> for Events {
    fn event(ev: &mut Self, _: &wl_buffer::WlBuffer, e: wl_buffer::Event, id: &BufferId, _: &Connection, _: &QueueHandle<Self>) {
        if let wl_buffer::Event::Release = e {
            ev.released.push(*id);
        }
    }
}

impl Dispatch<wl_callback::WlCallback, ()> for Events {
    fn event(ev: &mut Self, _: &wl_callback::WlCallback, _: wl_callback::Event, _: &(), _: &Connection, _: &QueueHandle<Self>) {
        ev.frame_done = true;
    }
}

impl Dispatch<pfb::WpPresentationFeedback, u64> for Events {
    fn event(ev: &mut Self, _: &pfb::WpPresentationFeedback, e: pfb::Event, arrival: &u64, _: &Connection, _: &QueueHandle<Self>) {
        match e {
            pfb::Event::Presented { tv_sec_hi, tv_sec_lo, tv_nsec, .. } => {
                let sec = u64::from(tv_sec_hi) << 32 | u64::from(tv_sec_lo);
                ev.presented.push((*arrival, Some(sec * 1_000_000 + u64::from(tv_nsec) / 1000)));
            }
            pfb::Event::Discarded => ev.presented.push((*arrival, None)),
            _ => {}
        }
    }
}
