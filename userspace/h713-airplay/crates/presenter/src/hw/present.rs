// SPDX-License-Identifier: GPL-3.0-only
//! The presenter thread. Each decoded picture goes one of two ways, chosen per surface pool and size: the decoder's
//! NV12 surface itself as a wl_buffer (when h713-warp offers NV12 with the surfaces' modifier: one GPU pass on the
//! device, h713-warp's), or the GL conversion (glpath). At most one picture is pending at h713-warp: the next goes
//! when the frame callback of the last commit has come (h713-warp takes at most one client picture a vsync), and the
//! newest decoded one wins. A lent surface goes back to the decoder at its wl_buffer.release.

use super::export::Exports;
use super::glpath::GlPath;
use super::slot::{Frame, Slot};
use super::wl::{BufferId, DmabufPlane, Wl};
use crate::dmabuf::{self, Path};
use crate::flight::Flight;
use crate::stats::{add, Counters};
use wayland_client::protocol::wl_buffer::WlBuffer;

/// A frame callback that never comes (a server that holds the picture) stops nothing for longer than this.
const CALLBACK_GIVE_UP_US: u64 = 250_000;

pub enum Ended {
    Quit,
    Closed,
}

struct Chooser {
    formats: Vec<(u32, u64)>,
    panel: (u32, u32),
    forced: bool,
    decided: Option<((usize, u32, u32), Path)>,
    said: Option<Path>,
}

impl Chooser {
    fn path(&mut self, wl: &mut Wl, exports: &mut Exports, frame: &Frame) -> Path {
        let f = frame.get();
        let size = (f.width as u32, f.height as u32);
        let key = (f.hw_frames_ctx as usize, size.0, size.1);
        let path = match (self.forced, frame.is_hw(), &self.decided) {
            (true, _, _) => Path::Convert("H713_AIRPLAY_SHOW_PATH=convert".into()),
            (_, false, _) => Path::Convert("a software-decoded picture".into()),
            (_, true, Some((k, p))) if *k == key => p.clone(),
            (_, true, _) => {
                let p = match exports.get(f) {
                    Err(e) => Path::Convert(e),
                    Ok(e) => match dmabuf::choose(&self.formats, e.modifier(), size, self.panel) {
                        Path::Passthrough { modifier } => match wl.probe_nv12(&planes(e, modifier), size) {
                            Ok(true) => Path::Passthrough { modifier },
                            Ok(false) => Path::Convert("h713-warp refused the NV12 buffer".into()),
                            Err(e) => Path::Convert(e),
                        },
                        convert => convert,
                    },
                };
                self.decided = Some((key, p.clone()));
                p
            }
        };
        if self.said.as_ref() != Some(&path) {
            match &path {
                Path::Passthrough { modifier } => eprintln!("h713-airplay-show: picture path: the decoder's NV12 surfaces to h713-warp as they are ({}x{}, modifier 0x{modifier:x})", size.0, size.1),
                Path::Convert(why) => eprintln!("h713-airplay-show: picture path: GL conversion into panel-size RGB buffers ({why})"),
            }
            self.said = Some(path.clone());
        }
        path
    }
}

fn planes(e: &super::export::Export, modifier: u64) -> [DmabufPlane<'_>; 2] {
    e.planes.map(|at| DmabufPlane { fd: &e.fds[at.object], at, modifier })
}

pub fn run(slot: &Slot, counters: &Counters, up: &dyn Fn(u32, u32, String)) -> Result<Ended, String> {
    let mut wl = Wl::connect(&proto::paths::warp_wayland())?;
    let panel = wl.ev.size.ok_or("no size")?;
    let formats = wl.ev.formats.take().unwrap_or_default();
    let forced = std::env::var("H713_AIRPLAY_SHOW_PATH").is_ok_and(|v| v == "convert");
    let nv12 = !forced && formats.iter().any(|&(f, _)| f == dmabuf::NV12);
    let mut gl = if nv12 { None } else { Some(GlPath::open(&mut wl, &formats, panel)?) };
    up(panel.0, panel.1, gl.as_ref().map_or_else(|| "h713-warp offers NV12: the decoder's surfaces go as they are".into(), |g| g.what.clone()));
    let mut chooser = Chooser { formats: formats.clone(), panel, forced, decided: None, said: None };
    let mut exports = Exports::default();
    let mut lent: Flight<(WlBuffer, Frame)> = Flight::default();
    let (mut passed, mut converted, mut committed_at) = (0u64, 0u64, 0u64);
    let ended = loop {
        for id in std::mem::take(&mut wl.ev.released) {
            match id {
                BufferId::Target(i) => gl.iter_mut().for_each(|g| g.released(i)),
                BufferId::Frame(n) => {
                    if let Some((b, frame)) = lent.release(n) {
                        b.destroy();
                        drop(frame);
                    }
                }
                BufferId::Probe => {}
            }
        }
        for (arrival, at) in wl.ev.presented.drain(..) {
            if let Some(at) = at {
                add(&counters.presented);
                Counters::mean(&counters.latency_us, at.saturating_sub(arrival));
            }
        }
        if wl.ev.closed {
            break Ended::Closed;
        }
        if slot.quitting() {
            break Ended::Quit;
        }
        gl.iter_mut().for_each(GlPath::retire);
        let now = super::now_us();
        if wl.ev.frame_done || now.saturating_sub(committed_at) > CALLBACK_GIVE_UP_US {
            if let Some(frame) = slot.take() {
                match chooser.path(&mut wl, &mut exports, &frame) {
                    Path::Passthrough { modifier } => match exports.get(frame.get()) {
                        Ok(e) => {
                            let size = (frame.get().width as u32, frame.get().height as u32);
                            let id = lent.next_id();
                            let b = wl.nv12_buffer(&planes(e, modifier), size, id);
                            wl.commit(&b, frame.arrival_us());
                            lent.lend(id, (b, frame));
                            passed += 1;
                            committed_at = now;
                        }
                        Err(e) => {
                            add(&counters.decode_errors);
                            eprintln!("h713-airplay-show: a surface as dma-bufs: {e}");
                        }
                    },
                    Path::Convert(_) => {
                        if gl.is_none() {
                            gl = Some(GlPath::open(&mut wl, &formats, panel)?);
                        }
                        let g = gl.as_mut().ok_or("no GL path")?;
                        match g.present(&mut wl, frame, &mut exports) {
                            Ok(true) => {
                                converted += 1;
                                committed_at = now;
                            }
                            Ok(false) => add(&counters.dropped),
                            Err(e) => {
                                add(&counters.decode_errors);
                                eprintln!("h713-airplay-show: drawing a picture: {e}");
                            }
                        }
                    }
                }
            }
        }
        let timeout = if !wl.ev.frame_done && slot.has_frame() { 50 } else { -1 };
        if wl.pump(Some(slot.wake_fd()), timeout)? {
            slot.drain();
        }
    };
    eprintln!("h713-airplay-show: pictures committed: {passed} as NV12 surfaces, {converted} converted");
    lent.drain().for_each(|(b, _)| b.destroy());
    if let Some(g) = gl {
        g.close();
    }
    wl.close();
    Ok(ended)
}
