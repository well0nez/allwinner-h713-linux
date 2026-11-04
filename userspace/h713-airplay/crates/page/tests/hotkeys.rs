// SPDX-License-Identifier: GPL-3.0-only
//! Volume, mute and focus while the page holds the remote, against a fake h713-tv (its control socket, one line per
//! connection, as h713-tv answers) and a stand-in h713-focus that writes down its arguments.

use std::io::{BufRead, BufReader, Write};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::UnixListener;
use std::path::{Path, PathBuf};
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use page::app::{Event, Key};
use page::hotkeys::Hotkeys;

fn scratch(name: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("wp-d2-{}-{name}", std::process::id()));
    let _ = std::fs::remove_dir_all(&d);
    std::fs::create_dir_all(&d).unwrap();
    d
}

/// A fake h713-tv at `dir`/tv: volume and mute as state, every setting line written down.
fn fake_tv(dir: &Path, volume: u32, muted: bool) -> Arc<Mutex<Vec<String>>> {
    let listener = UnixListener::bind(dir.join("tv")).unwrap();
    let said = Arc::new(Mutex::new(Vec::new()));
    let log = Arc::clone(&said);
    std::thread::spawn(move || {
        let (mut volume, mut muted) = (volume, muted);
        for conn in listener.incoming() {
            let mut s = conn.unwrap();
            let mut line = String::new();
            BufReader::new(&s).read_line(&mut line).unwrap();
            let line = line.trim_end();
            let answer = match line.split(' ').collect::<Vec<_>>()[..] {
                ["volume"] => format!("ok volume {volume}"),
                ["volume", n] => {
                    volume = n.parse().unwrap();
                    format!("ok volume {volume}")
                }
                ["mute"] => format!("ok mute {}", if muted { "on" } else { "off" }),
                ["mute", w] => {
                    muted = w == "on";
                    format!("ok mute {w}")
                }
                _ => "error unknown".into(),
            };
            if line.contains(' ') {
                log.lock().unwrap().push(line.to_string());
            }
            s.write_all(format!("{answer}\n").as_bytes()).unwrap();
        }
    });
    said
}

fn hotkeys(dir: &Path, conf: &str) -> Hotkeys {
    std::fs::write(dir.join("keys.conf"), conf).unwrap();
    let focus = dir.join("h713-focus");
    std::fs::write(&focus, format!("#!/bin/sh\necho \"$@\" >> {}\n", dir.join("focus.log").display())).unwrap();
    std::fs::set_permissions(&focus, std::fs::Permissions::from_mode(0o755)).unwrap();
    Hotkeys::new(dir.join("tv"), dir.join("keys.conf"), vec![focus.display().to_string()])
}

#[test]
fn louder_goes_in_volume_steps_and_quieter_back() {
    let dir = scratch("volume");
    let said = fake_tv(&dir, 40, false);
    let mut keys = hotkeys(&dir, "# keys.conf\nvolume_step = 5   # the default\n");
    keys.key(Key::VolumeUp);
    keys.key(Key::VolumeUp);
    keys.key(Key::VolumeDown);
    assert_eq!(*said.lock().unwrap(), ["volume 45", "volume 50", "volume 45"]);
    let _ = std::fs::remove_dir_all(dir);
}

#[test]
fn volume_while_muted_lifts_the_mute_first_and_mute_toggles() {
    let dir = scratch("mute");
    let said = fake_tv(&dir, 40, true);
    let mut keys = hotkeys(&dir, "volume_step = 3\n");
    keys.key(Key::VolumeDown);
    keys.key(Key::Mute);
    keys.key(Key::Mute);
    assert_eq!(*said.lock().unwrap(), ["mute off", "volume 37", "mute on", "mute off"]);
    let _ = std::fs::remove_dir_all(dir);
}

/// One run at a time: presses during a run wait for its end (Event::Reaped), a press the other way replaces them.
#[test]
fn focus_runs_one_at_a_time_with_focus_steps() {
    let dir = scratch("focus");
    let mut keys = hotkeys(&dir, "");
    let (tx, rx) = mpsc::channel();
    keys.report_to(tx);
    let reaped = || assert!(matches!(rx.recv_timeout(Duration::from_secs(20)), Ok(Event::Reaped)));
    keys.key(Key::FocusUp);
    keys.key(Key::FocusUp);
    keys.key(Key::FocusUp);
    reaped();
    keys.reaped();
    keys.key(Key::FocusUp);
    keys.key(Key::FocusDown);
    reaped();
    keys.reaped();
    reaped();
    keys.reaped();
    let log = std::fs::read_to_string(dir.join("focus.log")).unwrap();
    assert_eq!(log.lines().collect::<Vec<_>>(), ["up 20", "up 40", "down 20"]);
    let _ = std::fs::remove_dir_all(dir);
}
