// SPDX-License-Identifier: GPL-3.0-only
//! Where the stream comes from: systemd's socket (`LISTEN_FDS=1`, fd 3), `--listen PATH`, or `--feed FILE` (an
//! Annex B file played through the same path by a feeder in this process, for tests without a receiver).

use std::path::PathBuf;

#[derive(Debug, PartialEq)]
pub struct Feed {
    pub video: PathBuf,
    pub fps: u32,
    pub audio: Option<PathBuf>,
}

#[derive(Debug, PartialEq)]
pub enum Source {
    Activated,
    Listen(PathBuf),
    Feed(Feed),
}

pub const USAGE: &str = "usage: h713-airplay-show [--listen PATH | --feed FILE.h264|.h265 [--fps N] [--audio FILE.caf]]";

/// `listen_fds` and `listen_pid` are the environment's, `pid` this process's.
pub fn parse(args: &[String], listen_fds: Option<&str>, listen_pid: Option<&str>, pid: u32) -> Result<Source, String> {
    let mut listen = None;
    let mut feed: Option<Feed> = None;
    let mut fps = 60;
    let mut audio = None;
    let mut it = args.iter();
    while let Some(a) = it.next() {
        let mut value = || it.next().cloned().ok_or_else(|| format!("{a} needs a value\n{USAGE}"));
        match a.as_str() {
            "--listen" => listen = Some(PathBuf::from(value()?)),
            "--feed" => feed = Some(Feed { video: PathBuf::from(value()?), fps: 60, audio: None }),
            "--fps" => fps = value()?.parse().ok().filter(|n| (1..=240).contains(n)).ok_or(format!("--fps 1..240\n{USAGE}"))?,
            "--audio" => audio = Some(PathBuf::from(value()?)),
            "-h" | "--help" => return Err(USAGE.into()),
            _ => return Err(format!("unknown argument {a}\n{USAGE}")),
        }
    }
    match (listen, feed) {
        (Some(_), Some(_)) => Err(format!("--listen or --feed, not both\n{USAGE}")),
        (Some(p), None) => Ok(Source::Listen(p)),
        (None, Some(f)) => Ok(Source::Feed(Feed { fps, audio, ..f })),
        (None, None) if audio.is_some() => Err(format!("--audio goes with --feed\n{USAGE}")),
        (None, None) => {
            let for_us = listen_pid.is_none_or(|p| p.parse() == Ok(pid));
            match listen_fds {
                Some("1") if for_us => Ok(Source::Activated),
                _ => Err(format!("no socket from systemd (LISTEN_FDS=1) and no --listen or --feed\n{USAGE}")),
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(s: &str) -> Vec<String> {
        s.split_whitespace().map(String::from).collect()
    }

    #[test]
    fn systemds_socket_is_taken_only_when_it_is_meant_for_this_process() {
        assert_eq!(parse(&[], Some("1"), Some("42"), 42), Ok(Source::Activated));
        assert_eq!(parse(&[], Some("1"), None, 42), Ok(Source::Activated));
        assert!(parse(&[], Some("1"), Some("41"), 42).is_err());
        assert!(parse(&[], Some("2"), Some("42"), 42).is_err());
        assert!(parse(&[], None, None, 42).is_err());
    }

    #[test]
    fn the_test_modes_parse() {
        assert_eq!(parse(&args("--listen /tmp/s"), None, None, 1), Ok(Source::Listen("/tmp/s".into())));
        let f = parse(&args("--feed a.h265 --fps 30 --audio b.caf"), Some("1"), None, 1);
        assert_eq!(f, Ok(Source::Feed(Feed { video: "a.h265".into(), fps: 30, audio: Some("b.caf".into()) })));
        assert!(parse(&args("--feed a.h264 --fps 0"), None, None, 1).is_err());
        assert!(parse(&args("--listen x --feed y"), None, None, 1).is_err());
        assert!(parse(&args("--feed"), None, None, 1).is_err());
    }
}
