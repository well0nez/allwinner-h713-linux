// SPDX-License-Identifier: GPL-3.0-only
//! The receiver's one session and its state (`idle`, `connected`, `starting`, `streaming`), shared by every
//! thread. A state change wakes `ctl wait` and `ctl watch` through one condition variable.

use crate::identity::Identity;
use crate::presenter::Link;
use proto::config::Config;
use proto::ctl::{Client, State};
use std::collections::VecDeque;
use std::net::{IpAddr, Shutdown, TcpStream, UdpSocket};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc::Sender;
use std::sync::{Arc, Condvar, Mutex, MutexGuard};
use std::time::Duration;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Ports {
    pub rtsp: u16,
    pub mirror: u16,
    pub timing: u16,
    pub audio_data: u16,
    pub audio_control: u16,
}

#[derive(Clone, Copy)]
pub struct Keys {
    pub key: [u8; 16],
    pub iv: [u8; 16],
}

#[derive(Default)]
pub struct Counters {
    pub video_frames: AtomicU64,
    pub video_bytes: AtomicU64,
    pub audio_frames: AtomicU64,
}

pub struct MirrorSetup {
    pub stream_id: u64,
    pub conn: Option<TcpStream>,
    /// Which accepted connection `conn` is (the mirror thread of an older one must not end the session).
    pub serial: u64,
}

#[derive(Clone)]
pub struct AudioSetup {
    pub codec: proto::ipc::AudioCodec,
    pub sample_rate: u32,
    pub spf: u32,
    pub keys: Keys,
}

pub struct Session {
    pub id: u64,
    pub conn: u64,
    pub peer: IpAddr,
    pub rtsp: TcpStream,
    pub client: Client,
    pub keys: Option<Keys>,
    pub mirror: Option<MirrorSetup>,
    pub audio: Option<AudioSetup>,
    pub link: Option<Arc<Link>>,
    pub ntp_stop: Option<Sender<()>>,
    pub timing_peer: Option<std::net::SocketAddr>,
    pub counters: Arc<Counters>,
    /// `h264 1920x1080`, set by the mirror stream's codec packets.
    pub video_format: Option<String>,
    pub presenter: String,
    /// Set by TEARDOWN: the reason the session ends once the sender closes its mirror connection.
    pub ending: Option<&'static str>,
}

pub struct Inner {
    pub state: State,
    generation: u64,
    history: VecDeque<(u64, State)>,
    pub session: Option<Session>,
    next_session: u64,
    pub sessions: u64,
}

pub struct Shared {
    pub config: Config,
    pub identity: Identity,
    pub ports: Ports,
    pub timing: UdpSocket,
    pub mdns: Mutex<String>,
    /// The last `SET_PARAMETER volume`, dB (-30..0, -144 mute).
    pub volume: Mutex<f32>,
    inner: Mutex<Inner>,
    changed: Condvar,
    next_conn: AtomicU64,
}

pub enum Claim {
    Owner(u64),
    Conflict,
}

impl Shared {
    pub fn new(config: Config, identity: Identity, ports: Ports, timing: UdpSocket) -> Shared {
        Shared {
            config,
            identity,
            ports,
            timing,
            mdns: Mutex::new("off".into()),
            volume: Mutex::new(0.0),
            inner: Mutex::new(Inner {
                state: State::Idle,
                generation: 0,
                history: VecDeque::new(),
                session: None,
                next_session: 1,
                sessions: 0,
            }),
            changed: Condvar::new(),
            next_conn: AtomicU64::new(1),
        }
    }

    pub fn conn_id(&self) -> u64 {
        self.next_conn.fetch_add(1, Ordering::Relaxed)
    }

    pub fn lock(&self) -> MutexGuard<'_, Inner> {
        self.inner.lock().unwrap()
    }

    /// Notifies every `wait`/`watch` without a state change (a watcher's client went away). Taking the lock
    /// first means a watcher between its check and its wait cannot miss this.
    pub fn poke(&self) {
        let _held = self.lock();
        self.changed.notify_all();
    }

    pub fn set_state(&self, inner: &mut Inner, state: State) {
        if inner.state == state {
            return;
        }
        inner.state = state;
        inner.generation += 1;
        inner.history.push_back((inner.generation, state));
        if inner.history.len() > 64 {
            inner.history.pop_front();
        }
        eprintln!("h713-airplay: state {}", state.as_str());
        self.changed.notify_all();
    }

    pub fn generation(inner: &Inner) -> u64 {
        inner.generation
    }

    /// The states entered after `since`, oldest first, and the generation now.
    pub fn changes_since(inner: &Inner, since: u64) -> (Vec<State>, u64) {
        (inner.history.iter().filter(|(g, _)| *g > since).map(|(_, s)| *s).collect(), inner.generation)
    }

    pub fn wait_change<'a>(&self, g: MutexGuard<'a, Inner>, timeout: Option<Duration>) -> MutexGuard<'a, Inner> {
        match timeout {
            Some(t) => self.changed.wait_timeout(g, t).unwrap().0,
            None => self.changed.wait(g).unwrap(),
        }
    }

    /// The connection `conn` takes the session: a new one, or the one it already owns. Another sender's
    /// session is ended first when `takeover` is on (or it comes from the same address), else this connection
    /// gets a conflict.
    pub fn claim(&self, conn: u64, rtsp: &TcpStream, peer: IpAddr, name: &str) -> Claim {
        let mut inner = self.lock();
        if let Some(s) = &inner.session {
            if s.conn == conn {
                return Claim::Owner(s.id);
            }
            if !self.config.takeover && s.peer != peer {
                eprintln!("h713-airplay: {peer} refused (409): {} is connected", s.peer);
                return Claim::Conflict;
            }
            let old = inner.session.take();
            self.set_state(&mut inner, State::Idle);
            drop(inner);
            if let Some(old) = old {
                eprintln!("h713-airplay: session {} ended: taken over by {peer}", old.id);
                close(old, "taken over");
            }
            inner = self.lock();
        }
        let Ok(rtsp) = rtsp.try_clone() else { return Claim::Conflict };
        let id = inner.next_session;
        inner.next_session += 1;
        inner.sessions += 1;
        inner.session = Some(Session {
            id,
            conn,
            peer,
            rtsp,
            client: Client { addr: peer.to_string(), name: name.to_string(), model: String::new() },
            keys: None,
            mirror: None,
            audio: None,
            link: None,
            ntp_stop: None,
            timing_peer: None,
            counters: Arc::default(),
            video_format: None,
            presenter: "none".into(),
            ending: None,
        });
        eprintln!("h713-airplay: session {id} from {peer} {name}");
        self.set_state(&mut inner, State::Connected);
        Claim::Owner(id)
    }

    /// Ends session `id` (when it is still the one): the presenter gets `End`, the sender's sockets close.
    pub fn end(&self, id: u64, reason: &str) -> bool {
        let mut inner = self.lock();
        if inner.session.as_ref().map(|s| s.id) != Some(id) {
            return false;
        }
        let session = inner.session.take().expect("checked");
        self.set_state(&mut inner, State::Idle);
        drop(inner);
        let c = &session.counters;
        let (dropped_video, dropped_audio) = session.link.as_ref().map_or((0, 0), |l| l.dropped());
        eprintln!(
            "h713-airplay: session {id} ended: {reason} (video frames {} bytes {}, audio frames {}, queue dropped video {dropped_video} audio {dropped_audio})",
            c.video_frames.load(Ordering::Relaxed),
            c.video_bytes.load(Ordering::Relaxed),
            c.audio_frames.load(Ordering::Relaxed)
        );
        close(session, reason);
        true
    }

    /// Ends session `id` for `reason` after the frames already sent: when the sender closes its mirror connection
    /// (the mirror thread then ends it) or after `grace`, whichever is first.
    pub fn end_after_mirror(&self, id: u64, reason: &'static str, grace: Duration) {
        let deadline = std::time::Instant::now() + grace;
        let mut inner = self.lock();
        loop {
            let Some(s) = inner.session.as_mut().filter(|s| s.id == id) else { return };
            s.ending = Some(reason);
            let open = s.mirror.as_ref().is_some_and(|m| m.conn.is_some());
            let now = std::time::Instant::now();
            if !open || now >= deadline {
                break;
            }
            inner = self.wait_change(inner, Some(deadline - now));
        }
        drop(inner);
        self.end(id, reason);
    }

    pub fn current(&self) -> Option<u64> {
        self.lock().session.as_ref().map(|s| s.id)
    }
}

fn close(session: Session, reason: &str) {
    if let Some(link) = &session.link {
        link.finish(reason);
    }
    let _ = session.rtsp.shutdown(Shutdown::Both);
    if let Some(conn) = session.mirror.as_ref().and_then(|m| m.conn.as_ref()) {
        let _ = conn.shutdown(Shutdown::Both);
    }
    drop(session.ntp_stop);
}
