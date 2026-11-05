// SPDX-License-Identifier: GPL-3.0-only
//! `/etc/h713/airplay.conf`: `key = value` lines, `#` starts a comment. A line that is not understood is a
//! warning (returned, the caller logs it) and the other lines still count - the convention of keys.conf.

use std::fmt;
use std::path::Path;

#[derive(Clone, Debug, PartialEq)]
pub struct Config {
    /// What the sender lists: the AirPlay name (mDNS instance name, `/info` name).
    pub name: String,
    /// The RTSP port; the mirror data port is `port + 100`, timing `port + 11`, audio data/control 6000/6001
    /// as UxPlay's `-p` lays them out, so a firewall rule can name them.
    pub port: u16,
    pub audio_data_port: u16,
    pub audio_control_port: u16,
    /// The display the receiver advertises (`/info` displays[0]); a sender scales its screen into it.
    pub width: u32,
    pub height: u32,
    pub fps: u32,
    /// Advertise H.265 (feature bit 42, SupportsScreenMultiCodec): iOS 27 sends nothing usable without it.
    pub hevc: bool,
    pub audio: bool,
    /// The ALSA device of the presenter: `default` is the DSP bridge (hw:hy310hdmi,0, S16 48 kHz).
    pub audio_device: String,
    /// A new sender replaces the one that streams (Apple TV's way); off: it gets 409 Conflict.
    pub takeover: bool,
    /// Network interfaces to answer mDNS on; empty: every interface that is up and has an address.
    pub interfaces: Vec<String>,
}

impl Default for Config {
    fn default() -> Self {
        Config {
            name: default_name(),
            port: 7000,
            audio_data_port: 6000,
            audio_control_port: 6001,
            width: 1920,
            height: 1080,
            fps: 60,
            hevc: true,
            audio: true,
            audio_device: "default".into(),
            takeover: true,
            interfaces: Vec::new(),
        }
    }
}

impl Config {
    pub fn mirror_port(&self) -> u16 {
        self.port.wrapping_add(100)
    }
    pub fn timing_port(&self) -> u16 {
        self.port.wrapping_add(11)
    }
}

/// The host name in capitals ("hy320" -> "HY320"), else "H713".
pub fn default_name() -> String {
    std::fs::read_to_string("/etc/hostname")
        .ok()
        .map(|s| s.trim().to_uppercase())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "H713".into())
}

#[derive(Debug, PartialEq)]
pub struct Warning {
    pub line: usize,
    pub text: String,
}

impl fmt::Display for Warning {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "line {}: {}", self.line, self.text)
    }
}

fn on_off(v: &str) -> Option<bool> {
    match v {
        "on" | "yes" | "true" | "1" => Some(true),
        "off" | "no" | "false" | "0" => Some(false),
        _ => None,
    }
}

pub fn parse(text: &str) -> (Config, Vec<Warning>) {
    let mut c = Config::default();
    let mut warnings = Vec::new();
    for (i, raw) in text.lines().enumerate() {
        let line = raw.split('#').next().unwrap_or("").trim();
        if line.is_empty() {
            continue;
        }
        let Some((k, v)) = line.split_once('=') else {
            warnings.push(Warning { line: i + 1, text: format!("not key = value: {raw}") });
            continue;
        };
        let (k, v) = (k.trim(), v.trim());
        let bad = |what: &str| Warning { line: i + 1, text: format!("{k} = {v}: {what}") };
        match k {
            "name" if !v.is_empty() && v.len() <= 63 => c.name = v.to_string(),
            "port" => match v.parse::<u16>() {
                Ok(p) if p >= 1024 && p <= 65000 => c.port = p,
                _ => warnings.push(bad("a port 1024..65000")),
            },
            "width" | "height" | "fps" => match v.parse::<u32>() {
                Ok(n) if k == "fps" && (24..=60).contains(&n) => c.fps = n,
                Ok(n) if k == "width" && (640..=3840).contains(&n) => c.width = n,
                Ok(n) if k == "height" && (480..=2160).contains(&n) => c.height = n,
                _ => warnings.push(bad("out of range")),
            },
            "hevc" | "audio" | "takeover" => match on_off(v) {
                Some(b) if k == "hevc" => c.hevc = b,
                Some(b) if k == "audio" => c.audio = b,
                Some(b) => c.takeover = b,
                None => warnings.push(bad("on or off")),
            },
            "audio_device" if !v.is_empty() => c.audio_device = v.to_string(),
            "interfaces" => c.interfaces = v.split_whitespace().map(str::to_string).collect(),
            _ => warnings.push(bad("unknown key or empty value")),
        }
    }
    (c, warnings)
}

/// The configuration file, or the defaults when it is not there.
pub fn load(path: &Path) -> (Config, Vec<Warning>) {
    match std::fs::read_to_string(path) {
        Ok(t) => parse(&t),
        Err(_) => (Config::default(), Vec::new()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_known_keys_and_keeps_going_after_a_bad_line() {
        let (c, w) = parse("name = Living Room\nport = 7100\nbogus\nhevc = off\nfps = 99\ninterfaces = wlan0 wlan1\n");
        assert_eq!(c.name, "Living Room");
        assert_eq!(c.port, 7100);
        assert_eq!(c.mirror_port(), 7200);
        assert!(!c.hevc);
        assert_eq!(c.fps, 60);
        assert_eq!(c.interfaces, vec!["wlan0", "wlan1"]);
        assert_eq!(w.iter().map(|w| w.line).collect::<Vec<_>>(), vec![3, 5]);
    }
}
