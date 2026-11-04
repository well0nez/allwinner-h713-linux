// SPDX-License-Identifier: GPL-3.0-only
//! `h713-airplay page --render-png FILE --state ready|connecting|down [--size WxH] [--addrs IP@IF,...] [--wifi SSID@IF,...]
//! [--client NAME]`: the page as it would stand on the wall, into a PNG, without h713-osd, the remote or the receiver -
//! for review of the layout at either panel size.

use proto::config::Config;
use proto::ctl::{Client, State, Status};

use crate::canvas::{Canvas, GROUND};
use crate::text::{font_path, Face};
use crate::view::{self, View};

pub const USAGE: &str = "usage: h713-airplay page [--render-png FILE --state ready|connecting|down [--size WxH] [--addrs IP@IF,...] [--wifi SSID@IF,...] [--client NAME]]";

struct Args {
    file: String,
    state: String,
    size: (usize, usize),
    addrs: Vec<String>,
    wifi: Vec<String>,
    client: String,
}

fn parse(args: &[String]) -> Result<Args, String> {
    let mut a = Args {
        file: String::new(),
        state: "ready".into(),
        size: (1920, 1080),
        addrs: vec!["192.168.4.1@wlan0".into()],
        wifi: vec!["h713@wlan0".into()],
        client: "Peter's iPhone".into(),
    };
    let list = |v: &str| v.split(',').filter(|s| !s.is_empty()).map(str::to_string).collect::<Vec<_>>();
    let mut it = args.iter();
    while let Some(flag) = it.next() {
        let value = it.next().ok_or_else(|| format!("{flag} wants a value"))?;
        match flag.as_str() {
            "--render-png" => a.file = value.clone(),
            "--state" => a.state = value.clone(),
            "--size" => {
                let (w, h) = value.split_once('x').ok_or("--size WxH")?;
                a.size = (w.parse().map_err(|_| "--size WxH")?, h.parse().map_err(|_| "--size WxH")?);
            }
            "--addrs" => a.addrs = list(value),
            "--wifi" => a.wifi = list(value),
            "--client" => a.client = value.clone(),
            _ => return Err(format!("unknown {flag}")),
        }
    }
    if a.file.is_empty() {
        return Err("--render-png FILE is missing".into());
    }
    Ok(a)
}

fn status(a: &Args, name: &str) -> Result<Option<Status>, String> {
    let state = match a.state.as_str() {
        "down" => return Ok(None),
        "ready" => State::Idle,
        "connecting" => State::Connected,
        s => return Err(format!("--state {s}: ready, connecting or down")),
    };
    let client = (state == State::Connected).then(|| Client { addr: "192.168.4.23".into(), name: a.client.clone(), model: "iPhone17,1".into() });
    Ok(Some(Status { state, name: name.to_string(), addrs: a.addrs.clone(), wifi: a.wifi.clone(), client, ..Status::default() }))
}

/// The whole page into `px` (w x h, ARGB), as the live page draws it band by band.
pub fn paint(face: &Face, view: &View, px: &mut [u32], (w, h): (usize, usize)) {
    px.fill(GROUND);
    let mut c = Canvas { px, w, h, stride: w };
    for band in view::layout(face, view) {
        view::draw(face, &mut c, &band);
    }
}

fn write_png(path: &str, px: &[u32], (w, h): (usize, usize)) -> Result<(), String> {
    let f = std::fs::File::create(path).map_err(|e| format!("{path}: {e}"))?;
    let mut enc = png::Encoder::new(std::io::BufWriter::new(f), w as u32, h as u32);
    enc.set_color(png::ColorType::Rgba);
    enc.set_depth(png::BitDepth::Eight);
    let rgba: Vec<u8> = px.iter().flat_map(|p| [(p >> 16) as u8, (p >> 8) as u8, *p as u8, (p >> 24) as u8]).collect();
    enc.write_header().and_then(|mut wr| wr.write_image_data(&rgba)).map_err(|e| format!("{path}: {e}"))
}

pub fn main(config: &Config, args: &[String]) -> i32 {
    let a = match parse(args) {
        Ok(a) => a,
        Err(e) => {
            eprintln!("h713-airplay page: {e}\n{USAGE}");
            return 2;
        }
    };
    let st = match status(&a, &config.name) {
        Ok(st) => st,
        Err(e) => {
            eprintln!("h713-airplay page: {e}");
            return 2;
        }
    };
    let face = match Face::load(&font_path()) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("h713-airplay page: font {e}");
            return 5;
        }
    };
    let mut px = vec![0u32; a.size.0 * a.size.1];
    paint(&face, &View::of(st.as_ref(), &config.name), &mut px, a.size);
    match write_png(&a.file, &px, a.size) {
        Ok(()) => 0,
        Err(e) => {
            eprintln!("h713-airplay page: {e}");
            1
        }
    }
}
