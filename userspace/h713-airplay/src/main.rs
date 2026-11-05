// SPDX-License-Identifier: GPL-3.0-only
//! h713-airplay: the receiver and its tools (README.md).

use std::io::{self, Read, Write};
use std::os::unix::net::UnixStream;

const USAGE: &str = "usage: h713-airplay run | ctl status|wait STATE [MS]|watch|disconnect | page | sendtest ... | probe [HOST[:PORT]] | --version";

fn config() -> proto::config::Config {
    let path = proto::paths::config();
    let (config, warnings) = proto::config::load(&path);
    for w in warnings {
        eprintln!("h713-airplay: {}: {w}", path.display());
    }
    config
}

/// The answer as it comes (so `watch` streams), exit 0 on `ok`, 1 on `error`, 3 when the receiver is not there.
fn ctl(args: &[String]) -> i32 {
    if args.is_empty() {
        eprintln!("{USAGE}");
        return 2;
    }
    let path = proto::paths::ctl_socket();
    let mut s = match UnixStream::connect(&path) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("h713-airplay ctl: {}: {e}", path.display());
            return 3;
        }
    };
    if s.write_all(format!("{}\n", args.join(" ")).as_bytes()).is_err() {
        return 3;
    }
    let mut first = Vec::new();
    let mut buf = [0u8; 4096];
    let out = io::stdout();
    loop {
        match s.read(&mut buf) {
            Ok(0) => break,
            Ok(n) => {
                if first.len() < 8 {
                    first.extend_from_slice(&buf[..n.min(8)]);
                }
                let mut o = out.lock();
                let _ = o.write_all(&buf[..n]);
                let _ = o.flush();
            }
            Err(e) if e.kind() == io::ErrorKind::Interrupted => {}
            Err(_) => break,
        }
    }
    if first.starts_with(b"ok") { 0 } else { 1 }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let code = match args.get(1).map(String::as_str) {
        Some("run") => match receiver::run(config()) {
            Ok(()) => 0,
            Err(e) => {
                eprintln!("h713-airplay: {e}");
                1
            }
        },
        Some("ctl") => ctl(&args[2..]),
        Some("page") => page::run(&config()),
        Some("sendtest") => sender::sendtest(&args[2..]),
        Some("probe") => sender::probe(&args[2..]),
        Some("--version") => {
            println!("h713-airplay {}", env!("CARGO_PKG_VERSION"));
            0
        }
        _ => {
            eprintln!("{USAGE}");
            2
        }
    };
    std::process::exit(code);
}
