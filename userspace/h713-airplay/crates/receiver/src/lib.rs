// SPDX-License-Identifier: GPL-3.0-only
//! The receiver daemon (`h713-airplay run`, README.md): one thread per socket, each blocked in a syscall while
//! nothing happens. RTSP on `port`, the mirror stream on `port + 100` (TCP), timing on `port + 11`, screen audio
//! on `audio_data_port`/`audio_control_port` (UDP), the control socket, the mDNS responder.

mod audio;
mod conn;
mod crypto;
mod ctl;
mod identity;
mod info;
mod link;
mod mdns;
mod mirror;
mod net;
mod nl80211;
mod ntp;
mod pairing;
mod presenter;
mod rtsp;
mod setup;
mod shared;

pub use shared::Ports;

use proto::config::Config;
use shared::Shared;
use std::io;
use std::net::{Ipv4Addr, TcpListener, UdpSocket};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::{UnixListener, UnixStream};
use std::sync::Arc;

pub struct Options {
    /// The ports to listen on; 0 picks a free one (tests).
    pub ports: Ports,
    pub mdns: bool,
}

/// A running receiver; its threads live as long as the process.
pub struct Handle {
    pub ports: Ports,
}

pub fn config_ports(c: &Config) -> Ports {
    Ports {
        rtsp: c.port,
        mirror: c.mirror_port(),
        timing: c.timing_port(),
        audio_data: c.audio_data_port,
        audio_control: c.audio_control_port,
    }
}

fn ctl_listener() -> io::Result<UnixListener> {
    let path = proto::paths::ctl_socket();
    if UnixStream::connect(&path).is_ok() {
        return Err(io::Error::new(io::ErrorKind::AddrInUse, format!("{}: a receiver is running", path.display())));
    }
    let _ = std::fs::remove_file(&path);
    let l = UnixListener::bind(&path).map_err(|e| io::Error::new(e.kind(), format!("{}: {e}", path.display())))?;
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o666))?;
    Ok(l)
}

fn spawn(name: &str, f: impl FnOnce() + Send + 'static) -> io::Result<()> {
    std::thread::Builder::new().name(name.into()).spawn(f).map(drop)
}

fn bind_err(what: &str, port: u16) -> impl FnOnce(io::Error) -> io::Error + '_ {
    move |e| io::Error::new(e.kind(), format!("{what} port {port}: {e}"))
}

pub fn start(config: Config, opts: Options) -> io::Result<Handle> {
    let identity = identity::load(&proto::paths::state_dir())?;
    let any = Ipv4Addr::UNSPECIFIED;
    let p = opts.ports;
    let rtsp = TcpListener::bind((any, p.rtsp)).map_err(bind_err("RTSP", p.rtsp))?;
    let mirror = TcpListener::bind((any, p.mirror)).map_err(bind_err("mirror", p.mirror))?;
    let timing = UdpSocket::bind((any, p.timing)).map_err(bind_err("timing", p.timing))?;
    let audio_data = UdpSocket::bind((any, p.audio_data)).map_err(bind_err("audio data", p.audio_data))?;
    let audio_control = UdpSocket::bind((any, p.audio_control)).map_err(bind_err("audio control", p.audio_control))?;
    let ports = Ports {
        rtsp: rtsp.local_addr()?.port(),
        mirror: mirror.local_addr()?.port(),
        timing: timing.local_addr()?.port(),
        audio_data: audio_data.local_addr()?.port(),
        audio_control: audio_control.local_addr()?.port(),
    };
    let ctl = ctl_listener()?;
    let sh = Arc::new(Shared::new(config, identity, ports, timing.try_clone()?));

    let s = sh.clone();
    spawn("rtsp", move || {
        for stream in rtsp.incoming().flatten() {
            let s = s.clone();
            if let Err(e) = spawn("rtsp-conn", move || conn::serve(s, stream)) {
                eprintln!("h713-airplay: rtsp thread: {e}");
            }
        }
    })?;
    let s = sh.clone();
    spawn("mirror-accept", move || mirror::accept_loop(s, mirror))?;
    let s = sh.clone();
    spawn("audio-data", move || audio::data_loop(s, audio_data))?;
    spawn("audio-control", move || audio::control_loop(audio_control))?;
    spawn("timing", move || ntp::serve(timing))?;
    let s = sh.clone();
    spawn("ctl", move || ctl::serve(s, ctl))?;
    if opts.mdns {
        mdns::start(sh.clone());
    }
    eprintln!(
        "h713-airplay: {} ({}) on RTSP {}, mirror {}, timing {}, audio {}/{}, features {}",
        sh.config.name,
        sh.identity.device_id(),
        ports.rtsp,
        ports.mirror,
        ports.timing,
        ports.audio_data,
        ports.audio_control,
        info::features_txt(sh.config.hevc)
    );
    Ok(Handle { ports })
}

pub fn run(config: Config) -> io::Result<()> {
    let ports = config_ports(&config);
    start(config, Options { ports, mdns: true })?;
    loop {
        std::thread::park();
    }
}
