// SPDX-License-Identifier: GPL-3.0-only
//! The presenter (`h713-airplay-show`, work package C of README.md): one session per start. It takes the stream
//! of crates/proto/src/ipc.rs, decodes the pictures with the video engine (FFmpeg VAAPI -> libva-v4l2-request ->
//! cedrus), draws each one scaled to fit into a panel-size buffer of its own and hands that to h713-warp's
//! Wayland server, and plays the sound on ALSA.
//!
//! Threads: the stream reader (this thread), the video decoder, the presenter (EGL + Wayland), the sound, the
//! once-a-second `Stats`, and the signal watcher. The decoder sees every frame; between it and the presenter is
//! one slot, the newest picture wins.

pub mod annexb;
pub mod args;
pub mod audiocfg;
pub mod caf;
pub mod colour;
pub mod conn;
pub mod dmabuf;
pub mod feeder;
pub mod fit;
pub mod flight;
pub mod paramsets;
pub mod signals;
pub mod stats;

#[cfg(target_arch = "aarch64")]
mod hw;
#[cfg(target_arch = "aarch64")]
#[allow(non_upper_case_globals, non_camel_case_types, non_snake_case, dead_code, clippy::all)]
mod sys;

use proto::config::Config;
use std::io;
use std::os::unix::net::UnixStream;

fn connection(source: args::Source, stop: &signals::Signals) -> io::Result<Option<UnixStream>> {
    match source {
        args::Source::Activated => conn::accept_within(&conn::activated()?, conn::ACCEPT_WITHIN, stop),
        args::Source::Listen(path) => conn::accept_within(&conn::listen(&path)?, conn::ACCEPT_WITHIN, stop),
        args::Source::Feed(feed) => {
            let (ours, theirs) = UnixStream::pair()?;
            feeder::start(feed, theirs)?;
            Ok(Some(ours))
        }
    }
}

pub fn run(config: Config) -> io::Result<()> {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    let (fds, pid) = (std::env::var("LISTEN_FDS").ok(), std::env::var("LISTEN_PID").ok());
    let source = args::parse(&argv, fds.as_deref(), pid.as_deref(), std::process::id())
        .map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, e))?;
    let stop = signals::Signals::block()?;
    let Some(stream) = connection(source, &stop)? else {
        eprintln!("h713-airplay-show: no connection within {} s", conn::ACCEPT_WITHIN.as_secs());
        return Ok(());
    };
    session(config, stream, stop)
}

#[cfg(target_arch = "aarch64")]
fn session(config: Config, stream: UnixStream, stop: signals::Signals) -> io::Result<()> {
    hw::session::run(config, stream, stop)
}

#[cfg(not(target_arch = "aarch64"))]
fn session(_config: Config, _stream: UnixStream, _stop: signals::Signals) -> io::Result<()> {
    Err(io::Error::other("this build has no picture path: the presenter is built for the board (aarch64)"))
}
