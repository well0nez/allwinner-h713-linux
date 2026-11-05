// SPDX-License-Identifier: GPL-3.0-only
//! The keys h713-keys would take if it saw them: while the page holds the remote they are done here, by the same
//! commands (docs/tools/h713-keys.md; h713-settings' rows_hotkey). Volume and mute go to h713-tv's control socket -
//! louder and quieter in steps of keys.conf's `volume_step`, both lifting a mute first; mute toggles. Focus runs
//! `h713-focus up|down N` with `focus_steps`, one run at a time and never waited for: presses during a run wait for the
//! next (at most two presses' worth, a press the other way replaces them), and the run's end comes back as
//! [`Event::Reaped`].

use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc::Sender;
use std::time::Duration;

use crate::app::{Event, Key};

pub struct Hotkeys {
    tv: PathBuf,
    keys_conf: PathBuf,
    focus: Vec<String>,
    events: Option<Sender<Event>>,
    running: bool,
    pending: i32,
}

/// `key = value` of keys.conf as a number within lo..=hi, `default` when the line or the file is not there.
fn conf_number(path: &Path, key: &str, default: i32, (lo, hi): (i32, i32)) -> i32 {
    let text = std::fs::read_to_string(path).unwrap_or_default();
    text.lines()
        .filter_map(|l| l.split('#').next()?.split_once('='))
        .find(|(k, _)| k.trim() == key)
        .and_then(|(_, v)| v.trim().parse::<i32>().ok())
        .map_or(default, |v| v.clamp(lo, hi))
}

impl Hotkeys {
    /// The box's places: `H713_AIRPLAY_PAGE_TV` (h713-tv's socket), `H713_AIRPLAY_PAGE_ETC` (keys.conf's directory),
    /// `H713_AIRPLAY_PAGE_FOCUS` (the focus program, words split at spaces) override them.
    pub fn from_env() -> Hotkeys {
        let var = |k: &str, d: &str| std::env::var(k).ok().filter(|v| !v.is_empty()).unwrap_or_else(|| d.to_string());
        Hotkeys::new(
            var("H713_AIRPLAY_PAGE_TV", "/run/h713-tv/ctl").into(),
            Path::new(&var("H713_AIRPLAY_PAGE_ETC", "/etc/h713")).join("keys.conf"),
            var("H713_AIRPLAY_PAGE_FOCUS", "h713-focus").split_whitespace().map(str::to_string).collect(),
        )
    }

    pub fn new(tv: PathBuf, keys_conf: PathBuf, focus: Vec<String>) -> Hotkeys {
        Hotkeys { tv, keys_conf, focus, events: None, running: false, pending: 0 }
    }

    /// Where a focus run's end is reported.
    pub fn report_to(&mut self, events: Sender<Event>) {
        self.events = Some(events);
    }

    /// One line to h713-tv; its answer when it starts with `ok`.
    fn tv(&self, line: &str) -> Option<String> {
        match proto::ctl::request(&self.tv, line, Some(Duration::from_secs(3))) {
            Ok(a) if a.starts_with("ok") => Some(a),
            Ok(a) => {
                eprintln!("h713-airplay page: h713-tv refused {line:?}: {}", a.lines().next().unwrap_or("-"));
                None
            }
            Err(e) => {
                eprintln!("h713-airplay page: h713-tv {}: {e}", self.tv.display());
                None
            }
        }
    }

    fn muted(&self) -> Option<bool> {
        self.tv("mute").map(|a| a.starts_with("ok mute on"))
    }

    fn volume_by(&self, dir: i32) {
        let step = conf_number(&self.keys_conf, "volume_step", 5, (1, 20));
        let volume = self.tv("volume").and_then(|a| a.strip_prefix("ok volume ")?.split_whitespace().next()?.parse::<i32>().ok());
        let (Some(muted), Some(volume)) = (self.muted(), volume) else { return };
        if muted {
            self.tv("mute off");
        }
        let want = (volume + dir * step).clamp(0, 100);
        if want != volume {
            self.tv(&format!("volume {want}"));
        }
    }

    /// The next focus run, when none runs and presses wait.
    fn focus_start(&mut self) {
        if self.running || self.pending == 0 {
            return;
        }
        let steps = conf_number(&self.keys_conf, "focus_steps", 20, (1, 100));
        let word = if self.pending > 0 { "up" } else { "down" };
        let n = (self.pending.abs() * steps).clamp(1, 100);
        self.pending = 0;
        let Some((program, args)) = self.focus.split_first() else { return };
        let child = Command::new(program).args(args).args([word, &n.to_string()]).stdin(Stdio::null()).stdout(Stdio::null()).spawn();
        match child {
            Ok(mut child) => {
                self.running = true;
                let events = self.events.clone();
                std::thread::spawn(move || {
                    let _ = child.wait();
                    if let Some(e) = events {
                        let _ = e.send(Event::Reaped);
                    }
                });
            }
            Err(e) => eprintln!("h713-airplay page: {program} does not start ({e}) -- the focus keys do nothing"),
        }
    }

    pub fn key(&mut self, key: Key) {
        match key {
            Key::VolumeUp => self.volume_by(1),
            Key::VolumeDown => self.volume_by(-1),
            Key::Mute => {
                if let Some(muted) = self.muted() {
                    self.tv(if muted { "mute off" } else { "mute on" });
                }
            }
            Key::FocusUp | Key::FocusDown => {
                let dir = if key == Key::FocusUp { 1 } else { -1 };
                self.pending = if self.pending * dir < 0 { dir } else { (self.pending + dir).clamp(-2, 2) };
                self.focus_start();
            }
            Key::Ok | Key::Back | Key::Home | Key::Power => {}
        }
    }

    /// The focus run ended: the presses that waited start the next.
    pub fn reaped(&mut self) {
        self.running = false;
        self.focus_start();
    }
}
