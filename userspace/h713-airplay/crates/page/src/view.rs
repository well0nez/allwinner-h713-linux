// SPDX-License-Identifier: GPL-3.0-only
//! What the page says and where (README.md, "The waiting page"): the symbol, `Screen Mirroring`, the AirPlay name large, the
//! instruction, one pill per interface the receiver answers on, the status line, `BACK close` at the launcher's foot. All
//! centred in the 5 % safe margin, in 1080-line units. The page is cut into horizontal bands that tile it; a band is drawn
//! again (and shown) only when its place or its content changed, so a state change costs the status band alone.

use proto::ctl::{State, Status};

use crate::canvas::{Canvas, Pen, Rect, Units, PILL};
use crate::text::Face;

/// The safe area's sides: 5 % of 1920.
const SAFE_X0: f64 = 96.0;
const SAFE_X1: f64 = 1824.0;
/// The launcher's foot band starts here (osd.c LAU_FOOT) and its hint stands on 1010.
const FOOT: f64 = 958.0;
const CX: f64 = 960.0;

const NAME_EM: f64 = 120.0;
const PILL_H: f64 = 68.0;
const PILL_GAP: f64 = 16.0;

#[derive(Clone, Debug, PartialEq)]
pub enum Phase {
    /// The receiver's socket is not there.
    Down,
    Ready,
    /// A sender talks to the receiver (connected or starting), by its name when it gave one.
    Connecting(Option<String>),
}

/// One interface the receiver answers on: (label, value) pairs, `Wi-Fi h713`, `IP 192.168.4.1`.
pub type Net = Vec<(String, String)>;

#[derive(Clone, Debug, PartialEq)]
pub struct View {
    pub name: String,
    pub nets: Vec<Net>,
    pub phase: Phase,
}

fn kind_of(iface: &str) -> &'static str {
    if iface.starts_with("wl") {
        "Wi-Fi"
    } else if iface.starts_with("eth") || iface.starts_with("en") {
        "Ethernet"
    } else {
        "Network"
    }
}

impl View {
    /// The page for what the receiver says (`None`: it is not running); `name` stands when the receiver gave none.
    pub fn of(status: Option<&Status>, name: &str) -> View {
        let Some(st) = status else {
            return View { name: name.to_string(), nets: Vec::new(), phase: Phase::Down };
        };
        let nets = st
            .addrs
            .iter()
            .map(|a| {
                let (ip, iface) = a.split_once('@').unwrap_or((a, ""));
                let ssid = st.wifi.iter().find_map(|w| w.rsplit_once('@').filter(|(_, i)| *i == iface).map(|(s, _)| s));
                let first = match ssid {
                    Some(s) => ("Wi-Fi".to_string(), s.to_string()),
                    None if iface.is_empty() => (String::new(), String::new()),
                    None => (kind_of(iface).to_string(), iface.to_string()),
                };
                [first, ("IP".to_string(), ip.to_string())].into_iter().filter(|(l, _)| !l.is_empty()).collect()
            })
            .collect();
        let phase = match st.state {
            State::Idle => Phase::Ready,
            State::Connected | State::Starting => {
                Phase::Connecting(st.client.as_ref().map(|c| c.name.clone()).filter(|n| !n.is_empty()))
            }
            State::Streaming => Phase::Ready, // the page ends before it is drawn (exit 16)
        };
        View { name: if st.name.is_empty() { name.to_string() } else { st.name.clone() }, nets, phase }
    }
}

/// What a band holds: two bands with the same place and content have the same pixels.
#[derive(Clone, Debug, PartialEq)]
pub enum Content {
    /// The symbol, the title, the name (its size) and the instruction's lines; `top` the symbol's top.
    Head { top: f64, name: String, name_em: f64, lines: Vec<String> },
    /// The pills' top and their lines.
    Nets { top: f64, nets: Vec<Net> },
    Status { baseline: f64, text: String, alpha: f64 },
    Foot,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Band {
    /// In units; the first band starts at 0, the last ends at 1080.
    pub y0: f64,
    pub y1: f64,
    pub content: Content,
}

/// The bands of a view, top to bottom, tiling 0..1080. The content block is centred a little above the panel's middle
/// (the symbol weighs at its top); with three interfaces it still ends above the foot.
pub fn layout(face: &Face, v: &View) -> Vec<Band> {
    let width = SAFE_X1 - SAFE_X0;
    let mut name_em = NAME_EM;
    while name_em > 64.0 && face.width(&v.name, name_em) > width {
        name_em -= 4.0;
    }
    let name = face.fit(&v.name, name_em, width);
    let instruction =
        format!("On your iPhone, iPad or Mac: open Control Center, tap Screen Mirroring, choose {name}.");
    let lines = face.wrap(&instruction, 32.0, width);
    let head_h = 104.0 + 64.0 + 128.0 + 82.0 + 44.0 * (lines.len().max(1) - 1) as f64 + 40.0;
    let nets_h = if v.nets.is_empty() { 0.0 } else { 24.0 + v.nets.len() as f64 * (PILL_H + PILL_GAP) - PILL_GAP };
    let total = head_h + nets_h + 76.0 + 16.0 * f64::from(u8::from(!v.nets.is_empty())) + 30.0;
    let top = (530.0 - total / 2.0).round();
    let head_end = top + head_h;
    let nets_end = head_end + nets_h;
    let (text, alpha) = match &v.phase {
        Phase::Down => ("AirPlay is not running".to_string(), 0.6),
        Phase::Ready => ("Ready".to_string(), 0.94),
        Phase::Connecting(Some(c)) => (face.fit(&format!("Connecting to {c}..."), 44.0, width), 0.94),
        Phase::Connecting(None) => ("Connecting...".to_string(), 0.94),
    };
    let baseline = nets_end + 76.0 + if v.nets.is_empty() { 0.0 } else { 16.0 };
    let mut bands = vec![Band { y0: 0.0, y1: head_end, content: Content::Head { top, name, name_em, lines } }];
    if !v.nets.is_empty() {
        let nets = Content::Nets { top: head_end + 24.0, nets: v.nets.clone() };
        bands.push(Band { y0: head_end, y1: nets_end + 8.0, content: nets });
    }
    let y0 = bands.last().map_or(0.0, |b| b.y1);
    bands.push(Band { y0, y1: FOOT, content: Content::Status { baseline, text, alpha } });
    bands.push(Band { y0: FOOT, y1: 1080.0, content: Content::Foot });
    bands
}

/// A band's rows on this panel, the whole width.
pub fn rect(c: &Canvas, band: &Band) -> Rect {
    let g = Units::of(c.w, c.h);
    let y0 = if band.y0 <= 0.0 { 0 } else { g.row(band.y0).min(c.h) };
    let y1 = if band.y1 >= 1080.0 { c.h } else { g.row(band.y1).min(c.h) };
    Rect { x: 0, y: y0, w: c.w, h: y1.saturating_sub(y0) }
}

fn draw_net(face: &Face, pen: &mut Pen, net: &Net, top: f64) {
    const EM: f64 = 32.0;
    let (inner, outer) = (14.0, 44.0);
    let w: f64 = net.iter().map(|(l, v)| face.width(l, EM) + inner + face.width(v, EM)).sum::<f64>()
        + outer * (net.len().saturating_sub(1)) as f64;
    let x0 = CX - w / 2.0;
    pen.pill(x0 - 36.0, top, x0 + w + 36.0, top + PILL_H, PILL);
    let baseline = top + 45.0;
    let mut x = x0;
    for (label, value) in net {
        face.draw(pen, label, x, baseline, EM, 0.42);
        x += face.width(label, EM) + inner;
        face.draw(pen, value, x, baseline, EM, 0.94);
        x += face.width(value, EM) + outer;
    }
}

/// Draw one band: its rows set to the ground, then what it holds; returns the rectangle to show.
pub fn draw(face: &Face, c: &mut Canvas, band: &Band) -> Rect {
    let clip = rect(c, band);
    let g = Units::of(c.w, c.h);
    let mut pen = Pen { c, clip, g };
    pen.ground();
    match &band.content {
        Content::Head { top, name, name_em, lines } => {
            pen.airplay(CX, *top, crate::canvas::TEXT, 0.94);
            face.centred(&mut pen, "Screen Mirroring", CX, top + 168.0, 38.0, 0.6);
            face.centred(&mut pen, name, CX, top + 296.0, *name_em, 0.94);
            for (i, l) in lines.iter().enumerate() {
                face.centred(&mut pen, l, CX, top + 378.0 + 44.0 * i as f64, 32.0, 0.6);
            }
        }
        Content::Nets { top, nets } => {
            for (i, n) in nets.iter().enumerate() {
                draw_net(face, &mut pen, n, top + i as f64 * (PILL_H + PILL_GAP));
            }
        }
        Content::Status { baseline, text, alpha } => face.centred(&mut pen, text, CX, *baseline, 44.0, *alpha),
        Content::Foot => face.centred(&mut pen, "BACK close", CX, 1010.0, 26.0, 0.42),
    }
    clip
}
