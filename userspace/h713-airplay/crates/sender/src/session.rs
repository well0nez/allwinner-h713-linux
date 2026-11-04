// SPDX-License-Identifier: GPL-3.0-only
//! sendtest's session, the way iOS talks to a receiver without feature bit 27: `GET /info`, two `/fp-setup`
//! (a known `fairplay::fixtures` handshake), SETUP with `ekey`/`eiv`, SETUP of the mirror stream (110) and of
//! screen audio (96), RECORD, the paced stream, TEARDOWN. No pairing, so the FairPlay key is the session key.

use crate::annexb::{self, AccessUnit, Codec};
use crate::keys::{self, MirrorCipher};
use crate::negotiate::{setup, Local, Streams};
use crate::rtsp::{ok, plist_body, Client};
use plist::{Dictionary, Value};
use std::io::{self, Write};
use std::net::{SocketAddr, UdpSocket};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

pub enum Audio {
    None,
    Wav(PathBuf),
    Tone,
}

pub struct SendTest {
    pub target: SocketAddr,
    pub video: PathBuf,
    pub fps: u32,
    pub audio: Audio,
    /// Loop the file until this many seconds have passed; without it the file is sent once.
    pub seconds: Option<f64>,
    /// TEARDOWN without a stream list, as iOS 27 ends mirroring.
    pub bare_teardown: bool,
}

#[derive(Debug)]
pub struct Report {
    pub codec: Codec,
    pub width: u32,
    pub height: u32,
    pub frames: u64,
    pub bytes: u64,
    pub audio_packets: u64,
    pub elapsed: Duration,
}

pub const BINARY_PLIST: Option<&str> = Some("application/x-apple-binary-plist");

pub fn dict(entries: Vec<(&str, Value)>) -> Value {
    Value::Dictionary(entries.into_iter().map(|(k, v)| (k.to_string(), v)).collect::<Dictionary>())
}

pub fn int(v: u64) -> Value {
    Value::Integer(v.into())
}


fn now_ntp() -> u64 {
    let d = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default();
    ((d.as_secs() + 2_208_988_800) << 32) | ((u64::from(d.subsec_nanos()) << 32) / 1_000_000_000)
}

fn timing_responder(sock: UdpSocket, stop: Arc<AtomicBool>) {
    let _ = sock.set_read_timeout(Some(Duration::from_millis(200)));
    let mut buf = [0u8; 128];
    while !stop.load(Ordering::Relaxed) {
        let Ok((n, from)) = sock.recv_from(&mut buf) else { continue };
        if n < 32 || buf[1] & 0x7f != 0x52 {
            continue;
        }
        let mut a = [0u8; 32];
        a[0] = 0x80;
        a[1] = 0xd3;
        a[2..4].copy_from_slice(&buf[2..4]);
        a[8..16].copy_from_slice(&buf[24..32]);
        a[16..24].copy_from_slice(&now_ntp().to_be_bytes());
        a[24..32].copy_from_slice(&now_ntp().to_be_bytes());
        let _ = sock.send_to(&a, from);
    }
}

fn header(size: usize, kind: [u8; 2], option: [u8; 2]) -> [u8; 128] {
    let mut h = [0u8; 128];
    h[0..4].copy_from_slice(&(size as u32).to_le_bytes());
    h[4..6].copy_from_slice(&kind);
    h[6..8].copy_from_slice(&option);
    h[8..16].copy_from_slice(&now_ntp().to_le_bytes());
    h
}

struct CodecPacket {
    packet: Vec<u8>,
    width: u32,
    height: u32,
}

fn codec_packet(codec: Codec, au: &AccessUnit) -> Option<CodecPacket> {
    let ps = annexb::parameter_sets(codec, &au.params)?;
    let (config, (width, height), option) = match codec {
        Codec::H264 => (annexb::avcc_record(ps[0], ps[1]), crate::sps::h264(ps[0]), [0x16, 0x01]),
        Codec::H265 => {
            let i = crate::sps::h265(ps[1]);
            (annexb::hvcc_record(ps[0], ps[1], ps[2]), (i.width, i.height), [0x1e, 0x01])
        }
    };
    let mut h = header(config.len(), [0x01, 0x00], option);
    for at in [16, 40, 56] {
        h[at..at + 4].copy_from_slice(&(width as f32).to_le_bytes());
        h[at + 4..at + 8].copy_from_slice(&(height as f32).to_le_bytes());
    }
    let mut packet = h.to_vec();
    packet.extend_from_slice(&config);
    Some(CodecPacket { packet, width, height })
}

pub fn codec_of(path: &std::path::Path) -> io::Result<Codec> {
    match path.extension().and_then(|e| e.to_str()).map(str::to_ascii_lowercase).as_deref() {
        Some("h264" | "264" | "avc") => Ok(Codec::H264),
        Some("h265" | "265" | "hevc") => Ok(Codec::H265),
        _ => Err(io::Error::new(io::ErrorKind::InvalidInput, format!("{}: want .h264 or .h265", path.display()))),
    }
}

/// The media of one run and the key it is encrypted with.
struct Media<'a> {
    codec: Codec,
    units: &'a [AccessUnit<'a>],
    audio: Vec<Vec<u8>>,
    key: [u8; 16],
    eiv: [u8; 16],
}

fn sleep_until(t: Instant) {
    let now = Instant::now();
    if t > now {
        std::thread::sleep(t - now);
    }
}

fn stream(t: &SendTest, m: &Media, s: &Streams) -> io::Result<Report> {
    let mut report =
        Report { codec: m.codec, width: 0, height: 0, frames: 0, bytes: 0, audio_packets: 0, elapsed: Duration::ZERO };
    let mut cipher = MirrorCipher::new(&m.key, s.stream_id);
    let mut out = &s.mirror;
    let frame_dt = Duration::from_secs_f64(1.0 / f64::from(t.fps.max(1)));
    let audio_dt = Duration::from_secs_f64(crate::audio::SPF as f64 / f64::from(crate::audio::SAMPLE_RATE));
    let limit = t.seconds.map(Duration::from_secs_f64);
    let ssrc = u32::from_be_bytes(keys::random::<4>());
    let mut last_config: Option<Vec<u8>> = None;
    let (mut vi, mut ai) = (0u64, 0u64);
    let start = Instant::now();
    loop {
        let tv = frame_dt.mul_f64(vi as f64);
        let ta = (s.audio.is_some() && !m.audio.is_empty()).then(|| audio_dt.mul_f64(ai as f64));
        let (due, video) = match ta {
            Some(a) if a < tv => (a, false),
            _ => (tv, true),
        };
        match limit {
            Some(l) if due >= l => break,
            None if video && vi as usize >= m.units.len() => break,
            _ => {}
        }
        sleep_until(start + due);
        if video {
            let au = &m.units[vi as usize % m.units.len()];
            if au.key {
                let cp = codec_packet(m.codec, au)
                    .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "a key frame without parameter sets"))?;
                if last_config.as_deref() != Some(&cp.packet[128..]) {
                    out.write_all(&cp.packet)?;
                    (report.width, report.height) = (cp.width, cp.height);
                    last_config = Some(cp.packet[128..].to_vec());
                }
            }
            let mut payload = au.avcc();
            cipher.encrypt(&mut payload);
            let mut packet = header(payload.len(), [0x00, if au.key { 0x10 } else { 0x00 }], [0, 0]).to_vec();
            packet.extend_from_slice(&payload);
            out.write_all(&packet)?;
            report.frames += 1;
            report.bytes += payload.len() as u64;
            vi += 1;
        } else if let Some((sock, to)) = &s.audio {
            let mut payload = m.audio[ai as usize % m.audio.len()].clone();
            keys::audio_encrypt(&m.key, &m.eiv, &mut payload);
            let mut packet = crate::audio::rtp_header(ai as u16, (ai * crate::audio::SPF as u64) as u32, ssrc, ai == 0).to_vec();
            packet.extend_from_slice(&payload);
            sock.send_to(&packet, to)?;
            report.audio_packets += 1;
            ai += 1;
        }
    }
    report.elapsed = start.elapsed();
    Ok(report)
}

fn teardown(c: &mut Client, s: &Streams, bare: bool) -> io::Result<()> {
    let body = if bare {
        Vec::new()
    } else {
        let mut list = vec![dict(vec![("type", int(110))])];
        if s.audio.is_some() {
            list.insert(0, dict(vec![("type", int(96))]));
        }
        plist_body(&dict(vec![("streams", Value::Array(list))]))
    };
    let ct = if bare { None } else { BINARY_PLIST };
    ok("TEARDOWN", c.request("TEARDOWN", &s.url, ct, &body)?).map(drop)
}

pub fn run(t: &SendTest) -> io::Result<Report> {
    let codec = codec_of(&t.video)?;
    let data = std::fs::read(&t.video).map_err(|e| io::Error::new(e.kind(), format!("{}: {e}", t.video.display())))?;
    let units = annexb::access_units(codec, &data);
    let first_key = units
        .iter()
        .position(|u| u.key)
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, format!("{}: no key frame", t.video.display())))?;
    let audio = match &t.audio {
        Audio::None => Vec::new(),
        Audio::Wav(p) => crate::audio::alac_frames(&crate::audio::read_wav(p)?),
        Audio::Tone => crate::audio::alac_frames(&crate::audio::tone(1.0)),
    };
    let mut c = Client::connect(t.target)?;
    let timing = UdpSocket::bind("0.0.0.0:0")?;
    let stop = Arc::new(AtomicBool::new(false));
    let responder = {
        let (sock, stop) = (timing.try_clone()?, stop.clone());
        std::thread::spawn(move || timing_responder(sock, stop))
    };
    let local = Local { timing_port: timing.local_addr()?.port(), eiv: keys::random::<16>(), audio: !audio.is_empty() };
    let result = setup(&mut c, t.target, &local).and_then(|s| {
        let media = Media { codec, units: &units[first_key..], audio, key: fairplay::fixtures::HANDSHAKES[0].key, eiv: local.eiv };
        let report = stream(t, &media, &s)?;
        teardown(&mut c, &s, t.bare_teardown)?;
        Ok(report)
    });
    stop.store(true, Ordering::Relaxed);
    let _ = responder.join();
    result
}
