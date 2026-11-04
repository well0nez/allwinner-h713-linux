// SPDX-License-Identifier: GPL-3.0-only
//! `h713-airplay page`, the waiting screen of the launcher's Screen Mirroring entry (README.md, "The waiting page"): an
//! opaque page through h713-osd's page channel ([`osd`]), the remote held like h713-settings ([`input`]), the receiver
//! followed with `watch` ([`receiver`]); [`app`] is the loop between them, [`view`] what is drawn where.
//!
//! The arguments after `page` are read here (src/main.rs passes the configuration only): none for the page on the
//! wall, `--render-png ...` for a picture of it ([`render`]).

pub mod app;
pub mod canvas;
pub mod hotkeys;
pub mod input;
pub mod osd;
pub mod receiver;
pub mod render;
pub mod text;
pub mod view;

use std::sync::mpsc;

use proto::config::Config;

/// SIGTERM and SIGINT as [`app::Event::Signal`]: blocked in every thread (call before any is spawned), taken by one.
fn signals(events: mpsc::Sender<app::Event>) {
    // SAFETY: a sigset_t filled by sigemptyset/sigaddset, blocked for this thread and the threads spawned after it.
    let set = unsafe {
        let mut set: libc::sigset_t = std::mem::zeroed();
        libc::sigemptyset(&mut set);
        libc::sigaddset(&mut set, libc::SIGTERM);
        libc::sigaddset(&mut set, libc::SIGINT);
        libc::pthread_sigmask(libc::SIG_BLOCK, &set, std::ptr::null_mut());
        set
    };
    std::thread::spawn(move || {
        let mut sig = 0;
        // SAFETY: waits for one of the blocked signals in `set`.
        unsafe { libc::sigwait(&set, &mut sig) };
        let _ = events.send(app::Event::Signal);
    });
}

/// The exit status is h713-settings' convention (README.md, "The waiting page"): 0 Back, 10 Home, 11 Power, 13 nothing
/// seen for a while, 14 h713-osd gone, 15 a signal, 16 a stream took the wall; 3 no page (h713-osd absent or `ok unseen`),
/// 4 no remote to hold, 5 no font.
pub fn run(config: &Config) -> i32 {
    let args: Vec<String> = std::env::args().skip(2).collect();
    if !args.is_empty() {
        return render::main(config, &args);
    }
    let face = match text::Face::load(&text::font_path()) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("h713-airplay page: font {e} -- a page without words is not opened");
            return 5;
        }
    };
    let (tx, rx) = mpsc::channel();
    signals(tx.clone());
    receiver::follow(proto::paths::ctl_socket(), tx.clone());
    // on the wall first (a page nobody can see is not opened), then the remote
    let mut wall = match osd::OsdLink::open(&proto::paths::osd_ctl(), tx.clone()) {
        Ok(w) => w,
        Err(osd::OpenError::Absent(e)) => {
            eprintln!("h713-airplay page: {e}");
            return 3;
        }
        Err(osd::OpenError::Refused(line)) => {
            eprintln!("h713-airplay page: h713-osd answers \"{line}\" -- no page");
            return 3;
        }
    };
    let mut remote = match input::Evdev::open() {
        Ok(r) => r,
        Err(e) => {
            eprintln!("h713-airplay page: {e} -- not opened");
            return 4;
        }
    };
    remote.start(tx);
    let look = app::Look { face: &face, name: config.name.clone() };
    app::serve(&mut wall, &mut remote, &rx, &look)
}
