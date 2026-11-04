// SPDX-License-Identifier: GPL-3.0-only
//! sendtest's RTSP side before the stream: `GET /info`, `/fp-setup` with a known `fairplay::fixtures` handshake,
//! SETUP of the session (`ekey`, `eiv`, timing), of the mirror stream (110) and of screen audio (96), RECORD.

use crate::keys;
use crate::rtsp::{ok, plist_body, Client};
use crate::session::{dict, int, BINARY_PLIST};
use plist::{Dictionary, Value};
use std::io;
use std::net::{SocketAddr, TcpStream, UdpSocket};
use std::time::Duration;

const OCTETS: Option<&str> = Some("application/octet-stream");

fn stream_port(d: &Dictionary, key: &str) -> io::Result<u16> {
    d.get("streams")
        .and_then(Value::as_array)
        .and_then(|a| a.first())
        .and_then(Value::as_dictionary)
        .and_then(|s| s.get(key))
        .and_then(Value::as_unsigned_integer)
        .map(|p| p as u16)
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, format!("SETUP answer without {key}")))
}

pub struct Streams {
    pub url: String,
    pub stream_id: u64,
    pub mirror: TcpStream,
    pub audio: Option<(UdpSocket, SocketAddr)>,
}

/// What this end brings to SETUP: its timing port, the audio IV, whether screen audio is set up.
pub struct Local {
    pub timing_port: u16,
    pub eiv: [u8; 16],
    pub audio: bool,
}

pub fn setup(c: &mut Client, target: SocketAddr, local: &Local) -> io::Result<Streams> {
    let hs = &fairplay::fixtures::HANDSHAKES[0];
    let qualifier = dict(vec![("qualifier", Value::Array(vec![Value::String("txtAirPlay".into())]))]);
    ok("GET /info txtAirPlay", c.request("GET", "/info", BINARY_PLIST, &plist_body(&qualifier))?)?;
    ok("GET /info", c.request("GET", "/info", None, &[])?)?.plist()?;
    let m2 = ok("fp-setup 1", c.request("POST", "/fp-setup", OCTETS, &hs.message1)?)?;
    let m4 = ok("fp-setup 2", c.request("POST", "/fp-setup", OCTETS, &hs.message3)?)?;
    if m2.body.len() != fairplay::REPLY1_LEN || m4.body.len() != fairplay::REPLY2_LEN {
        return Err(io::Error::other(format!("fp-setup answers of {} and {} bytes", m2.body.len(), m4.body.len())));
    }
    let id = u64::from_be_bytes(keys::random::<8>());
    let url = format!("rtsp://{}/{id}", c.local_ip()?);
    let session = dict(vec![
        ("deviceID", Value::String("02:00:00:00:00:42".into())),
        ("macAddress", Value::String("02:00:00:00:00:42".into())),
        ("sessionUUID", Value::String(format!("{id:016X}"))),
        ("name", Value::String("h713-airplay sendtest".into())),
        ("model", Value::String("sendtest".into())),
        ("sourceVersion", Value::String("380.20.1".into())),
        ("isScreenMirroringSession", Value::Boolean(true)),
        ("timingProtocol", Value::String("NTP".into())),
        ("timingPort", int(local.timing_port.into())),
        ("et", int(32)),
        ("ekey", Value::Data(hs.ekey.to_vec())),
        ("eiv", Value::Data(local.eiv.to_vec())),
    ]);
    ok("SETUP session", c.request("SETUP", &url, BINARY_PLIST, &plist_body(&session))?)?;
    let stream_id = u64::from_be_bytes(keys::random::<8>()) | (1 << 63);
    let video = dict(vec![(
        "streams",
        Value::Array(vec![dict(vec![
            ("type", int(110)),
            ("streamConnectionID", int(stream_id)),
            ("latencyMs", int(90)),
            ("timestampInfo", Value::Array(Vec::new())),
        ])]),
    )]);
    let v = ok("SETUP mirror", c.request("SETUP", &url, BINARY_PLIST, &plist_body(&video))?)?.plist()?;
    let data = SocketAddr::new(target.ip(), stream_port(&v, "dataPort")?);
    let mirror = TcpStream::connect_timeout(&data, Duration::from_secs(5))?;
    mirror.set_nodelay(true)?;
    let audio = if local.audio {
        let sock = UdpSocket::bind("0.0.0.0:0")?;
        let audio = dict(vec![(
            "streams",
            Value::Array(vec![dict(vec![
                ("type", int(96)),
                ("ct", int(2)),
                ("spf", int(crate::audio::SPF as u64)),
                ("sr", int(crate::audio::SAMPLE_RATE.into())),
                ("audioFormat", int(0x40000)),
                ("controlPort", int(sock.local_addr()?.port().into())),
                ("usingScreen", Value::Boolean(true)),
                ("isMedia", Value::Boolean(true)),
                ("audioMode", Value::String("default".into())),
            ])]),
        )]);
        let a = ok("SETUP audio", c.request("SETUP", &url, BINARY_PLIST, &plist_body(&audio))?)?.plist()?;
        Some((sock, SocketAddr::new(target.ip(), stream_port(&a, "dataPort")?)))
    } else {
        None
    };
    ok("RECORD", c.request("RECORD", &url, None, &[])?)?;
    ok("SET_PARAMETER", c.request("SET_PARAMETER", &url, Some("text/parameters"), b"volume: -15.000000\r\n")?)?;
    Ok(Streams { url, stream_id, mirror, audio })
}
