// SPDX-License-Identifier: GPL-3.0-only
//! The page's life: events from its three edges - the remote, the receiver, h713-osd (and a signal) - come in on one
//! channel, each one is answered at once, and the bands that changed are drawn and shown. How it ends is the exit status
//! (README.md, "The waiting page"; h713-settings' convention).

use std::sync::mpsc::{Receiver, RecvTimeoutError};
use std::time::{Duration, Instant};

use proto::ctl::{State, Status};

use crate::canvas::{Canvas, Rect};
use crate::text::Face;
use crate::view::{self, Band, View};

pub const EXIT_BACK: i32 = 0;
pub const EXIT_HOME: i32 = 10;
pub const EXIT_POWER: i32 = 11;
/// h713-settings' 13: h713-osd only kept the page (`ok waiting` / `ok unseen`) for [`PATIENCE`].
pub const EXIT_UNSEEN: i32 = 13;
pub const EXIT_GONE: i32 = 14;
pub const EXIT_SIGNAL: i32 = 15;
pub const EXIT_STREAM: i32 = 16;

/// How long the page waits for its picture to be on the wall again (h713-settings' H713_SETTINGS_PATIENCE).
pub const PATIENCE: Duration = Duration::from_secs(10);
/// How long the first drawing waits for the receiver's first word, so the page does not open on a guess.
const FIRST_WORD: Duration = Duration::from_millis(800);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Key {
    Ok,
    Back,
    Home,
    Power,
    VolumeUp,
    VolumeDown,
    Mute,
    FocusUp,
    FocusDown,
}

#[derive(Debug)]
pub enum Event {
    Key(Key),
    /// What the receiver says now; `None`: its socket is not there (or it went).
    Receiver(Option<Box<Status>>),
    /// h713-osd ended the page's connection.
    OsdGone,
    /// SIGTERM or SIGINT.
    Signal,
    /// A focus run (crate::hotkeys) ended.
    Reaped,
}

/// What h713-osd did with a `page show`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Shown {
    OnTheWall,
    /// `ok waiting` (or `ok unseen`): kept for the picture's return.
    Kept,
}

/// The page channel (crate::osd::OsdLink on the box).
pub trait Wall {
    fn canvas(&mut self) -> Canvas<'_>;
    /// `Err`: h713-osd is gone or refuses.
    fn show(&mut self, r: Rect) -> Result<Shown, String>;
    fn hide(&mut self);
    /// The launcher follows: the page stays on the wall until it is drawn.
    fn handover(&mut self);
}

/// The remote, held while the page is open (crate::input::Evdev on the box).
pub trait Remote {
    /// Let the remote's devices go (h713-keys and h713-power see them again).
    fn release(&mut self);
    /// Hand a Power press to h713-power (after `release`).
    fn power(&mut self);
    /// Volume, mute or focus: what h713-keys would do with it (crate::hotkeys).
    fn hotkey(&mut self, key: Key);
    /// A focus run ended.
    fn reaped(&mut self);
}

pub struct Look<'a> {
    pub face: &'a Face,
    /// The AirPlay name while the receiver does not say it (airplay.conf's `name`).
    pub name: String,
}

/// Draw every band that differs from `shown` and show it; `shown` becomes the new bands.
fn refresh(wall: &mut dyn Wall, look: &Look, view: &View, shown: &mut Vec<Band>) -> Result<Shown, String> {
    let bands = view::layout(look.face, view);
    let mut result = Shown::OnTheWall;
    for band in bands.iter().filter(|b| !shown.contains(b)) {
        let r = view::draw(look.face, &mut wall.canvas(), band);
        if r.h > 0 && wall.show(r)? == Shown::Kept {
            result = Shown::Kept;
        }
    }
    *shown = bands;
    Ok(result)
}

/// The page until it ends: returns the exit status, with the page hidden or handed over and the remote let go.
pub fn serve(wall: &mut dyn Wall, remote: &mut dyn Remote, events: &Receiver<Event>, look: &Look) -> i32 {
    let code = run(wall, remote, events, look);
    remote.release();
    match code {
        EXIT_BACK => wall.handover(),
        EXIT_GONE => {}
        _ => wall.hide(),
    }
    code
}

fn run(wall: &mut dyn Wall, remote: &mut dyn Remote, events: &Receiver<Event>, look: &Look) -> i32 {
    let mut status: Option<Status> = None;
    let mut heard = false;
    let mut shown: Vec<Band> = Vec::new();
    let mut unseen_since: Option<Instant> = None;
    let first = Instant::now() + FIRST_WORD;
    loop {
        let deadline = match (heard, unseen_since) {
            (false, _) => Some(first),
            (true, Some(t)) => Some(t + PATIENCE),
            (true, None) => None,
        };
        let ev = match deadline {
            Some(d) => events.recv_timeout(d.saturating_duration_since(Instant::now())),
            None => events.recv().map_err(|_| RecvTimeoutError::Disconnected),
        };
        match ev {
            Ok(Event::Key(Key::Back)) => return EXIT_BACK,
            Ok(Event::Key(Key::Home)) => return EXIT_HOME,
            Ok(Event::Key(Key::Power)) => {
                remote.release();
                remote.power();
                return EXIT_POWER;
            }
            Ok(Event::Key(Key::Ok)) => continue, // nothing to choose on this page
            Ok(Event::Key(k @ (Key::VolumeUp | Key::VolumeDown | Key::Mute | Key::FocusUp | Key::FocusDown))) => {
                remote.hotkey(k);
                continue;
            }
            Ok(Event::Reaped) => {
                remote.reaped();
                continue;
            }
            Ok(Event::OsdGone) => return EXIT_GONE,
            Ok(Event::Signal) => return EXIT_SIGNAL,
            Ok(Event::Receiver(Some(st))) if st.state == State::Streaming => return EXIT_STREAM,
            Ok(Event::Receiver(st)) => {
                status = st.map(|b| *b);
                heard = true;
            }
            Err(RecvTimeoutError::Timeout) if heard => {
                eprintln!("h713-airplay page: nothing can be seen for {} s -- closing", PATIENCE.as_secs());
                return EXIT_UNSEEN;
            }
            Err(RecvTimeoutError::Timeout) => heard = true, // the receiver is slow to answer: draw what is known
            Err(RecvTimeoutError::Disconnected) => return EXIT_GONE,
        }
        match refresh(wall, look, &View::of(status.as_ref(), &look.name), &mut shown) {
            Ok(Shown::OnTheWall) => unseen_since = None,
            Ok(Shown::Kept) => {
                unseen_since.get_or_insert_with(Instant::now);
            }
            Err(e) => {
                eprintln!("h713-airplay page: h713-osd: {e} -- closing");
                return EXIT_GONE;
            }
        }
    }
}
