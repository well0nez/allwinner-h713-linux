// SPDX-License-Identifier: GPL-3.0-only
//! The control socket (proto::ctl): one command per connection.

use crate::shared::Shared;
use proto::ctl::{parse_command, Command, State, Status};
use std::io::{BufRead, BufReader, Read, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

pub fn serve(sh: Arc<Shared>, listener: UnixListener) {
    for stream in listener.incoming() {
        let Ok(stream) = stream else { continue };
        let sh = sh.clone();
        if let Err(e) = std::thread::Builder::new().name("ctl".into()).spawn(move || handle(&sh, stream)) {
            eprintln!("h713-airplay: ctl thread: {e}");
        }
    }
}

fn wifi_env() -> std::path::PathBuf {
    std::env::var_os("H713_WIFI_ENV").map(Into::into).unwrap_or_else(|| crate::net::WIFI_ENV.into())
}

pub fn status(sh: &Shared) -> Status {
    let addrs = crate::net::addrs(&sh.config.interfaces);
    let mut wifi = crate::nl80211::ssids();
    if wifi.is_empty() {
        wifi = crate::net::wifi(&wifi_env());
    }
    let mut mdns = sh.mdns.lock().unwrap().clone();
    if mdns == "published" {
        for name in crate::net::interface_names(&addrs) {
            mdns.push(' ');
            mdns.push_str(&name);
        }
    }
    let inner = sh.lock();
    let s = inner.session.as_ref();
    Status {
        state: inner.state,
        name: sh.config.name.clone(),
        mdns,
        addrs,
        wifi,
        client: s.map(|s| s.client.clone()),
        video: s.map_or("-".into(), |s| crate::mirror::video_text(s.video_format.as_deref(), &s.counters)),
        audio: s.and_then(|s| {
            let a = s.audio.as_ref()?;
            let frames = s.counters.audio_frames.load(Ordering::Relaxed);
            Some(format!("{} {} frames {frames}", crate::audio::codec_name(a.codec), a.sample_rate))
        })
        .unwrap_or_else(|| "-".into()),
        presenter: s.map_or("none".into(), |s| s.presenter.clone()),
        sessions: inner.sessions,
    }
}

fn wait(sh: &Shared, target: State, timeout: Duration) -> String {
    let deadline = Instant::now() + timeout;
    let mut g = sh.lock();
    let since = Shared::generation(&g);
    loop {
        if g.state == target || Shared::changes_since(&g, since).0.contains(&target) {
            return format!("ok {}\n", target.as_str());
        }
        let now = Instant::now();
        if now >= deadline {
            return format!("error timeout {}\n", g.state.as_str());
        }
        g = sh.wait_change(g, Some(deadline - now));
    }
}

fn watch(sh: &Shared, mut stream: UnixStream) {
    let closed = Arc::new(AtomicBool::new(false));
    let mut seen = {
        let g = sh.lock();
        if stream.write_all(format!("ok watch\nstate {}\n", g.state.as_str()).as_bytes()).is_err() {
            return;
        }
        Shared::generation(&g)
    };
    let Ok(mut client) = stream.try_clone() else { return };
    let flag = closed.clone();
    std::thread::scope(|scope| {
        scope.spawn(|| {
            let mut sink = [0u8; 64];
            while matches!(client.read(&mut sink), Ok(n) if n > 0) {}
            flag.store(true, Ordering::Relaxed);
            sh.poke();
        });
        loop {
            let mut g = sh.lock();
            let states = loop {
                if closed.load(Ordering::Relaxed) {
                    let _ = stream.shutdown(std::net::Shutdown::Both);
                    return;
                }
                let (states, now) = Shared::changes_since(&g, seen);
                if !states.is_empty() {
                    seen = now;
                    break states;
                }
                g = sh.wait_change(g, None);
            };
            drop(g);
            let text: String = states.iter().map(|s| format!("state {}\n", s.as_str())).collect();
            if stream.write_all(text.as_bytes()).is_err() {
                let _ = stream.shutdown(std::net::Shutdown::Both);
                return;
            }
        }
    });
}

fn handle(sh: &Shared, stream: UnixStream) {
    let Ok(read_half) = stream.try_clone() else { return };
    let mut line = String::new();
    if BufReader::new(read_half.take(512)).read_line(&mut line).is_err() {
        return;
    }
    let mut out = &stream;
    let answer = match parse_command(&line) {
        Err(e) => format!("error {e}\n"),
        Ok(Command::Status) => status(sh).to_text(),
        Ok(Command::Wait { state, timeout_ms }) => wait(sh, state, Duration::from_millis(timeout_ms)),
        Ok(Command::Watch) => return watch(sh, stream),
        Ok(Command::Disconnect) => match sh.current() {
            Some(id) => {
                sh.end(id, "ctl disconnect");
                "ok\n".into()
            }
            None => "ok idle\n".into(),
        },
    };
    let _ = out.write_all(answer.as_bytes());
}
