// SPDX-License-Identifier: GPL-3.0-only
//! The receiver's control socket ([`crate::paths::ctl_socket`]): a Unix stream socket, one command line per
//! connection, the answer's first word `ok` or `error` (as `h713-warp ctl` and `h713-osd ctl`).
//!
//! | command | answer |
//! |---|---|
//! | `status` | `ok status`, then one `key value` line per [`Status`] field |
//! | `wait STATE [MS]` | `ok STATE` as soon as the receiver is in STATE (at once if it is), `error timeout NOW` after MS (default 10000) |
//! | `watch` | `ok watch`, then `state STATE` at every change (the first line is the state now) until the client closes |
//! | `disconnect` | `ok` after the current session was ended (`ok idle` when there was none) |
//!
//! `wait` and `watch` are how tests and the waiting page follow the receiver without polling.

use std::io::{self, BufRead, BufReader, Read, Write};
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::time::Duration;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum State {
    /// Advertised, no sender.
    Idle,
    /// A sender talks RTSP (info, fp-setup, pairing) but has set up no stream.
    Connected,
    /// The mirror stream is set up and the presenter is starting.
    Starting,
    /// Frames go to the presenter, which is up.
    Streaming,
}

impl State {
    pub fn as_str(self) -> &'static str {
        match self {
            State::Idle => "idle",
            State::Connected => "connected",
            State::Starting => "starting",
            State::Streaming => "streaming",
        }
    }
    pub fn parse(s: &str) -> Option<State> {
        Some(match s {
            "idle" => State::Idle,
            "connected" => State::Connected,
            "starting" => State::Starting,
            "streaming" => State::Streaming,
            _ => return None,
        })
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum Command {
    Status,
    Wait { state: State, timeout_ms: u64 },
    Watch,
    Disconnect,
}

pub fn parse_command(line: &str) -> Result<Command, String> {
    let w: Vec<&str> = line.split_whitespace().collect();
    match w.as_slice() {
        ["status"] => Ok(Command::Status),
        ["watch"] => Ok(Command::Watch),
        ["disconnect"] => Ok(Command::Disconnect),
        ["wait", s] | ["wait", s, _] => {
            let state = State::parse(s).ok_or_else(|| format!("unknown state {s}"))?;
            let timeout_ms = match w.get(2) {
                Some(t) => t.parse().map_err(|_| format!("not milliseconds: {t}"))?,
                None => 10_000,
            };
            Ok(Command::Wait { state, timeout_ms })
        }
        _ => Err(format!("usage: status | wait STATE [MS] | watch | disconnect (got {line:?})")),
    }
}

/// The sender that is connected.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Client {
    pub addr: String,
    pub name: String,
    pub model: String,
}

/// What `status` reports. Free-text fields stay one line each.
#[derive(Clone, Debug, PartialEq)]
pub struct Status {
    pub state: State,
    pub name: String,
    /// `published` with the interfaces it answers on, or `error ...`.
    pub mdns: String,
    /// The receiver's IPv4 addresses with their interfaces, `192.168.4.1@wlan0`.
    pub addrs: Vec<String>,
    /// The Wi-Fi network(s) a sender has to be on (SSID per interface, `h713@wlan0`).
    pub wifi: Vec<String>,
    pub client: Option<Client>,
    /// `h264 1920x1080 frames N bytes N` or `-`.
    pub video: String,
    /// `aac-eld 44100 frames N` or `-`.
    pub audio: String,
    /// `none`, `starting`, or `ready decoded N presented N dropped N fps F hw yes|no latency-ms L`.
    pub presenter: String,
    pub sessions: u64,
}

impl Default for Status {
    fn default() -> Self {
        Status {
            state: State::Idle,
            name: String::new(),
            mdns: "off".into(),
            addrs: Vec::new(),
            wifi: Vec::new(),
            client: None,
            video: "-".into(),
            audio: "-".into(),
            presenter: "none".into(),
            sessions: 0,
        }
    }
}

fn one_line(s: &str) -> String {
    s.replace(['\n', '\r'], " ")
}

impl Status {
    pub fn to_text(&self) -> String {
        let client = match &self.client {
            Some(c) => format!("{} {} {}", one_line(&c.addr), one_line(&c.model).replace(' ', "_"), one_line(&c.name)),
            None => "-".into(),
        };
        let list = |v: &[String]| if v.is_empty() { "-".to_string() } else { v.join(" ") };
        format!(
            "ok status\nstate {}\nname {}\nmdns {}\naddrs {}\nwifi {}\nclient {}\nvideo {}\naudio {}\npresenter {}\nsessions {}\n",
            self.state.as_str(),
            one_line(&self.name),
            one_line(&self.mdns),
            list(&self.addrs),
            list(&self.wifi),
            client,
            one_line(&self.video),
            one_line(&self.audio),
            one_line(&self.presenter),
            self.sessions
        )
    }

    pub fn from_text(text: &str) -> Result<Status, String> {
        let mut lines = text.lines();
        if lines.next() != Some("ok status") {
            return Err(format!("not a status answer: {:?}", text.lines().next()));
        }
        let mut s = Status::default();
        for l in lines {
            let (k, v) = l.split_once(' ').unwrap_or((l, ""));
            let list = |v: &str| if v == "-" { Vec::new() } else { v.split(' ').map(str::to_string).collect() };
            match k {
                "state" => s.state = State::parse(v).ok_or_else(|| format!("unknown state {v}"))?,
                "name" => s.name = v.into(),
                "mdns" => s.mdns = v.into(),
                "addrs" => s.addrs = list(v),
                "wifi" => s.wifi = list(v),
                "client" if v != "-" => {
                    let mut p = v.splitn(3, ' ');
                    s.client = Some(Client {
                        addr: p.next().unwrap_or("").into(),
                        model: p.next().unwrap_or("").replace('_', " "),
                        name: p.next().unwrap_or("").into(),
                    });
                }
                "client" => s.client = None,
                "video" => s.video = v.into(),
                "audio" => s.audio = v.into(),
                "presenter" => s.presenter = v.into(),
                "sessions" => s.sessions = v.parse().map_err(|_| format!("sessions {v}"))?,
                _ => {}
            }
        }
        Ok(s)
    }
}

/// Send one command and read the whole answer (until the server closes).
pub fn request(path: &Path, line: &str, timeout: Option<Duration>) -> io::Result<String> {
    let mut s = UnixStream::connect(path)?;
    s.set_read_timeout(timeout)?;
    s.write_all(line.trim_end().as_bytes())?;
    s.write_all(b"\n")?;
    s.shutdown(std::net::Shutdown::Write)?;
    let mut out = String::new();
    s.read_to_string(&mut out)?;
    Ok(out)
}

/// Follow `watch`: call `f` with every state until it returns false or the receiver closes.
pub fn watch(path: &Path, mut f: impl FnMut(State) -> bool) -> io::Result<()> {
    let mut s = UnixStream::connect(path)?;
    s.write_all(b"watch\n")?;
    let mut r = BufReader::new(s);
    let mut line = String::new();
    r.read_line(&mut line)?;
    if line.trim_end() != "ok watch" {
        return Err(io::Error::new(io::ErrorKind::InvalidData, format!("watch answered {line:?}")));
    }
    loop {
        line.clear();
        if r.read_line(&mut line)? == 0 {
            return Ok(());
        }
        if let Some(st) = line.trim_end().strip_prefix("state ").and_then(State::parse) {
            if !f(st) {
                return Ok(());
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn status_text_round_trips() {
        let s = Status {
            state: State::Streaming,
            name: "HY320".into(),
            mdns: "published wlan0".into(),
            addrs: vec!["192.168.4.1@wlan0".into()],
            wifi: vec!["h713@wlan0".into()],
            client: Some(Client { addr: "192.168.4.23".into(), name: "Peter's iPhone".into(), model: "iPhone17,1".into() }),
            video: "h265 1920x886 frames 10 bytes 100".into(),
            audio: "aac-eld 44100 frames 5".into(),
            presenter: "ready decoded 10 presented 9 dropped 1 fps 59.90 hw yes latency-ms 31".into(),
            sessions: 3,
        };
        assert_eq!(Status::from_text(&s.to_text()).unwrap(), s);
    }

    #[test]
    fn commands_parse_with_their_defaults() {
        assert_eq!(parse_command("wait streaming").unwrap(), Command::Wait { state: State::Streaming, timeout_ms: 10_000 });
        assert_eq!(parse_command("wait idle 250").unwrap(), Command::Wait { state: State::Idle, timeout_ms: 250 });
        assert!(parse_command("wait nowhere").is_err());
        assert_eq!(parse_command(" status ").unwrap(), Command::Status);
    }
}
