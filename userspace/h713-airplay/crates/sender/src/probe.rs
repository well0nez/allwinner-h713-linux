// SPDX-License-Identifier: GPL-3.0-only
//! `probe [HOST[:PORT]]`: `GET /info` and `OPTIONS` as a sender asks them, the answers decoded.

use crate::rtsp::{resolve, Client};
use plist::Value;
use std::fmt::Write as _;
use std::io;

fn show(v: &Value, out: &mut String) {
    match v {
        Value::Dictionary(d) => {
            out.push('{');
            for (i, (k, v)) in d.iter().enumerate() {
                if i > 0 {
                    out.push_str(", ");
                }
                let _ = write!(out, "{k}: ");
                show(v, out);
            }
            out.push('}');
        }
        Value::Array(a) => {
            out.push('[');
            for (i, v) in a.iter().enumerate() {
                if i > 0 {
                    out.push_str(", ");
                }
                show(v, out);
            }
            out.push(']');
        }
        Value::Data(d) => {
            let hex: String = d.iter().take(32).map(|b| format!("{b:02x}")).collect();
            let more = if d.len() > 32 { "..." } else { "" };
            let _ = write!(out, "<{} bytes {hex}{more}>", d.len());
        }
        Value::Integer(i) => match i.as_unsigned() {
            Some(u) if u > 0xffff => {
                let _ = write!(out, "{u:#x}");
            }
            _ => {
                let _ = write!(out, "{i}");
            }
        },
        Value::String(s) => {
            let _ = write!(out, "{s:?}");
        }
        Value::Boolean(b) => {
            let _ = write!(out, "{b}");
        }
        Value::Real(r) => {
            let _ = write!(out, "{r}");
        }
        other => {
            let _ = write!(out, "{other:?}");
        }
    }
}

pub fn probe(target: &str) -> io::Result<String> {
    let mut c = Client::connect(resolve(target)?)?;
    let mut out = String::new();
    let info = c.request("GET", "/info", None, &[])?;
    let _ = writeln!(out, "GET /info: {}", info.status_line);
    if info.status == 200 {
        for (k, v) in info.plist()? {
            let mut line = String::new();
            show(&v, &mut line);
            let _ = writeln!(out, "  {k}: {line}");
        }
    }
    let options = c.request("OPTIONS", "*", None, &[])?;
    let _ = writeln!(out, "OPTIONS: {}", options.status_line);
    let _ = writeln!(out, "  Public: {}", options.header("Public").unwrap_or("-"));
    Ok(out)
}
