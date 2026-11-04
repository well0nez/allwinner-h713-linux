// SPDX-License-Identifier: GPL-3.0-only
//! The page against fakes of its three edges: an h713-osd that hands out a memfd and checks every `page show`, scripted
//! events for the remote and the receiver, a receiver's control socket that appears late, the remote's bytes in a pipe.
//! Tests that draw need Quicksand (H713_OSD_FONT, else the box's path) and say so when it is absent.

use std::fs::File;
mod fake_osd;

use std::io::{BufRead, BufReader, Write};
use std::os::fd::FromRawFd;
use std::os::unix::net::{UnixDatagram, UnixListener, UnixStream};
use std::path::PathBuf;
use std::sync::mpsc::{self, Sender};
use std::time::Duration;

use page::app::{self, Event, Key, Look, Remote};
use fake_osd::{fake_osd, Seen};
use page::canvas::Rect;
use page::osd::OsdLink;
use page::text::{font_path, Face};
use proto::ctl::{Client, State, Status};

fn face() -> Option<Face> {
    match Face::load(&font_path()) {
        Ok(f) => Some(f),
        Err(e) => {
            eprintln!("SKIPPED: no Quicksand ({e}); set H713_OSD_FONT to Quicksand-Medium.ttf");
            None
        }
    }
}

fn scratch(name: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("wp-d2-{}-{name}", std::process::id()));
    let _ = std::fs::remove_dir_all(&d);
    std::fs::create_dir_all(&d).unwrap();
    d
}

fn status(state: State) -> Box<Status> {
    let client = (state != State::Idle).then(|| Client { addr: "192.168.4.23".into(), name: "Peter's iPhone".into(), model: "iPhone17,1".into() });
    Box::new(Status {
        state,
        name: "HY320".into(),
        addrs: vec!["192.168.4.1@wlan0".into()],
        wifi: vec!["h713@wlan0".into()],
        client,
        ..Status::default()
    })
}

#[derive(Default)]
struct FakeRemote(Vec<&'static str>);

impl Remote for FakeRemote {
    fn release(&mut self) {
        self.0.push("release");
    }
    fn power(&mut self) {
        self.0.push("power");
    }
    fn hotkey(&mut self, key: Key) {
        self.0.push(if key == Key::Mute { "mute" } else { "hotkey" });
    }
    fn reaped(&mut self) {
        self.0.push("reaped");
    }
}

/// The page served over a fake h713-osd with `script` queued as its events: (exit status, what h713-osd saw, the remote's calls).
fn serve(size: (usize, usize), script: Vec<Event>, close_after_last_row: bool) -> Option<(i32, Seen, Vec<&'static str>)> {
    let face = face()?;
    let (client, server) = UnixStream::pair().unwrap();
    let osd = fake_osd(server, size, close_after_last_row);
    let (tx, rx) = mpsc::channel();
    let Ok(mut wall) = OsdLink::over(client, tx.clone()) else { panic!("page open failed") };
    for e in script {
        tx.send(e).unwrap();
    }
    let mut remote = FakeRemote::default();
    let code = app::serve(&mut wall, &mut remote, &rx, &Look { face: &face, name: "HY320".into() });
    drop(wall);
    Some((code, osd.join().unwrap(), remote.0))
}

fn covered(shows: &[Rect], h: usize) -> bool {
    (0..h).all(|y| shows.iter().any(|r| y >= r.y && y < r.y + r.h))
}

#[test]
fn a_state_change_redraws_only_the_status_band_and_a_stream_ends_the_page_with_16() {
    for size in [(1920, 1080), (1280, 720)] {
        let script = vec![
            Event::Receiver(Some(status(State::Idle))),
            Event::Receiver(Some(status(State::Connected))),
            Event::Key(Key::Ok),
            Event::Receiver(Some(status(State::Streaming))),
        ];
        let Some((code, seen, _)) = serve(size, script, false) else { return };
        assert_eq!(code, app::EXIT_STREAM);
        assert!(seen.faults.is_empty(), "{:?}", seen.faults);
        assert_eq!(seen.shows.len(), 2, "the whole panel, then the status band: {:?}", seen.shows);
        let status_band = seen.shows[1];
        assert!(status_band.y > size.1 / 2 && status_band.y + status_band.h < size.1, "{status_band:?}");
        assert_eq!(seen.lines.last().map(String::as_str), Some("page hide"));
    }
}

/// h713-osd judges opacity by the rows it was shown (a row never shown is a hole): the first show is the whole panel,
/// and the mapped canvas is opaque to its last pixel by then.
#[test]
fn the_first_show_is_the_whole_opaque_panel() {
    for (size, first) in [((1920, 1080), Event::Receiver(None)), ((1280, 720), Event::Receiver(Some(status(State::Idle))))] {
        let Some((_, seen, _)) = serve(size, vec![first, Event::Key(Key::Home)], false) else { return };
        assert_eq!(seen.shows.first(), Some(&Rect { x: 0, y: 0, w: size.0, h: size.1 }), "{:?}", seen.shows);
        assert_eq!(seen.opaque_at_first_show, Some(true));
        assert!(seen.faults.is_empty(), "{:?}", seen.faults);
    }
}

#[test]
fn back_hands_the_wall_to_the_launcher() {
    let script = vec![Event::Receiver(None), Event::Key(Key::Back)];
    let Some((code, seen, remote)) = serve((1280, 720), script, false) else { return };
    assert_eq!(code, app::EXIT_BACK);
    assert!(seen.faults.is_empty(), "{:?}", seen.faults);
    assert!(covered(&seen.shows, 720));
    assert_eq!(seen.lines.last().map(String::as_str), Some("page handover"));
    assert_eq!(remote, ["release"]);
}

#[test]
fn home_power_and_a_signal_hide_the_page_with_their_status() {
    for (ev, code_wanted, remote_wanted) in [
        (Event::Key(Key::Home), app::EXIT_HOME, &["release"][..]),
        (Event::Key(Key::Power), app::EXIT_POWER, &["release", "power", "release"][..]),
        (Event::Signal, app::EXIT_SIGNAL, &["release"][..]),
    ] {
        let Some((code, seen, remote)) = serve((1280, 720), vec![Event::Receiver(Some(status(State::Idle))), ev], false) else { return };
        assert_eq!(code, code_wanted);
        assert_eq!(seen.lines.last().map(String::as_str), Some("page hide"));
        assert_eq!(remote, remote_wanted);
    }
}

#[test]
fn volume_mute_and_focus_go_to_the_remote_and_the_page_stays() {
    let script = vec![
        Event::Receiver(Some(status(State::Idle))),
        Event::Key(Key::VolumeUp),
        Event::Key(Key::Mute),
        Event::Key(Key::FocusUp),
        Event::Reaped,
        Event::Key(Key::Back),
    ];
    let Some((code, seen, remote)) = serve((1280, 720), script, false) else { return };
    assert_eq!(code, app::EXIT_BACK);
    assert_eq!(remote, ["hotkey", "mute", "hotkey", "reaped", "release"]);
    assert_eq!(seen.shows.len(), 1, "the keys draw nothing: {:?}", seen.shows);
}

#[test]
fn h713_osd_going_ends_the_page_with_14() {
    let Some((code, seen, _)) = serve((1280, 720), vec![Event::Receiver(Some(status(State::Idle)))], true) else { return };
    assert_eq!(code, app::EXIT_GONE);
    assert!(seen.faults.is_empty(), "{:?}", seen.faults);
}

/// The receiver's socket is not there at first: the page says so, then follows it when it appears (no sleep: the
/// fake answers in the order the page asks, and the page is woken by inotify).
#[test]
fn the_receiver_is_followed_from_absent_to_connected_to_gone() {
    let dir = scratch("ctl");
    let path = dir.join("h713-airplay/ctl");
    let (tx, rx) = mpsc::channel();
    page::receiver::follow(path.clone(), tx);
    let recv = || rx.recv_timeout(Duration::from_secs(20)).expect("an event");
    assert!(matches!(recv(), Event::Receiver(None)));
    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    let listener = UnixListener::bind(&path).unwrap();
    let (watch, _) = listener.accept().unwrap();
    let mut wr = BufReader::new(watch.try_clone().unwrap());
    let mut line = String::new();
    wr.read_line(&mut line).unwrap();
    assert_eq!(line, "watch\n");
    let answer_status = |state: State| {
        let (mut s, _) = listener.accept().unwrap();
        let mut l = String::new();
        BufReader::new(s.try_clone().unwrap()).read_line(&mut l).unwrap();
        assert_eq!(l, "status\n");
        s.write_all(status(state).to_text().as_bytes()).unwrap();
    };
    (&watch).write_all(b"ok watch\nstate idle\n").unwrap();
    answer_status(State::Idle);
    assert!(matches!(recv(), Event::Receiver(Some(s)) if s.state == State::Idle && s.wifi == ["h713@wlan0"]));
    (&watch).write_all(b"state connected\n").unwrap();
    answer_status(State::Connected);
    let Event::Receiver(Some(s)) = recv() else { panic!("not a state") };
    assert_eq!((s.state, s.client.map(|c| c.name)), (State::Connected, Some("Peter's iPhone".into())));
    drop((watch, wr));
    std::fs::remove_file(&path).unwrap();
    assert!(matches!(recv(), Event::Receiver(None)));
    let _ = std::fs::remove_dir_all(dir);
}

fn pipe() -> (File, File) {
    let mut fds = [0; 2];
    // SAFETY: pipe fills two new descriptors, owned by the Files from here on.
    unsafe {
        assert_eq!(libc::pipe(fds.as_mut_ptr()), 0);
        (File::from_raw_fd(fds[0]), File::from_raw_fd(fds[1]))
    }
}

fn input_event(kind: u16, code: u16, value: i32) -> [u8; 24] {
    let mut ev = [0u8; 24];
    ev[16..18].copy_from_slice(&kind.to_ne_bytes());
    ev[18..20].copy_from_slice(&code.to_ne_bytes());
    ev[20..24].copy_from_slice(&value.to_ne_bytes());
    ev
}

#[test]
fn the_remote_gives_presses_only_and_power_goes_to_h713_power() {
    let dir = scratch("remote");
    let power = UnixDatagram::bind(dir.join("power.sock")).unwrap();
    let (r, mut w) = pipe();
    let mut remote = page::input::Evdev::over(vec![r], dir.join("power.sock"));
    let (tx, rx): (Sender<Event>, _) = mpsc::channel();
    remote.start(tx);
    for (kind, code, value) in [(1, 158, 1), (1, 158, 0), (0, 0, 0), (1, 28, 2), (1, 28, 1), (1, 172, 1), (1, 115, 1), (1, 115, 2), (1, 115, 0), (1, 113, 2), (1, 113, 1), (1, 62, 2), (1, 116, 1)] {
        w.write_all(&input_event(kind, code, value)).unwrap();
    }
    let keys: Vec<Key> = (0..8).map(|_| match rx.recv_timeout(Duration::from_secs(20)) {
        Ok(Event::Key(k)) => k,
        other => panic!("{other:?}"),
    }).collect();
    assert_eq!(keys, [Key::Back, Key::Ok, Key::Home, Key::VolumeUp, Key::VolumeUp, Key::Mute, Key::FocusUp, Key::Power]);
    remote.release();
    remote.power();
    let mut buf = [0u8; 16];
    let n = power.recv(&mut buf).unwrap();
    assert_eq!(&buf[..n], b"down");
    let _ = std::fs::remove_dir_all(dir);
}

#[test]
fn the_stock_remote_is_found_by_sysfs() {
    let sys = scratch("sys");
    for (ev, vendor, product, name) in [("event0", "", "", "sunxi-ir"), ("event1", "", "", "gpio-keys"), ("event2", "1d5a", "c081", "remote")] {
        let d = sys.join("class/input").join(ev).join("device");
        std::fs::create_dir_all(d.join("id")).unwrap();
        std::fs::write(d.join("name"), format!("{name}\n")).unwrap();
        std::fs::write(d.join("id/vendor"), format!("{vendor}\n")).unwrap();
        std::fs::write(d.join("id/product"), format!("{product}\n")).unwrap();
    }
    let found = page::input::discover(&sys, std::path::Path::new("/dev/input"));
    assert_eq!(found, [PathBuf::from("/dev/input/event0"), PathBuf::from("/dev/input/event2")]);
    let _ = std::fs::remove_dir_all(sys);
}

/// Every state at both panel sizes: every pixel opaque, and nothing but the ground outside the 5 % safe margin.
#[test]
fn every_page_is_opaque_and_inside_the_safe_margin() {
    let Some(face) = face() else { return };
    let long = Status { name: "Peter's Living Room Projector HY320".into(), addrs: vec!["192.168.4.1@wlan0".into(), "10.0.0.17@eth0".into()], ..*status(State::Connected) };
    for (w, h) in [(1920, 1080), (1280, 720)] {
        for st in [None, Some(*status(State::Idle)), Some(*status(State::Connected)), Some(long.clone())] {
            let mut px = vec![0u32; w * h];
            page::render::paint(&face, &page::view::View::of(st.as_ref(), "HY320"), &mut px, (w, h));
            let g = page::canvas::Units::of(w, h);
            let (x0, x1, y0, y1) = (g.x(96.0) as usize, g.x(1824.0).ceil() as usize, g.y(54.0) as usize, g.y(1026.0).ceil() as usize);
            for (i, p) in px.iter().enumerate() {
                let (x, y) = (i % w, i / w);
                assert_eq!(p >> 24, 0xff, "{w}x{h} {st:?}: pixel {x},{y}");
                let outside = x < x0 || x >= x1 || y < y0 || y >= y1;
                assert!(!outside || *p == page::canvas::GROUND, "{w}x{h}: pixel {x},{y} outside the safe margin");
            }
        }
    }
}
