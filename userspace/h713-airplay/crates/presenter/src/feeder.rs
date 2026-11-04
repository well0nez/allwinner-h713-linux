// SPDX-License-Identifier: GPL-3.0-only
//! `--feed`: plays an Annex B file (and an ALAC CAF file) through the stream a receiver would send, paced at
//! `--fps`, and prints what the presenter answers. The parameter sets go into `VideoConfig` records and out of the
//! frames, as a sender's mirror stream carries them.

use crate::annexb::{is_parameter_set, is_random_access, nal_type, AccessUnits};
use crate::args::Feed;
use crate::paramsets::{build_avcc, build_hvcc};
use proto::ipc::{self, AudioCodec, Msg, VideoCodec};
use std::fs::File;
use std::io::{self, BufReader, Read, Write};
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

fn codec_of(path: &Path) -> VideoCodec {
    match path.extension().and_then(|e| e.to_str()) {
        Some("h265" | "265" | "hevc") => VideoCodec::H265,
        _ => VideoCodec::H264,
    }
}

fn send<W: Write>(out: &Mutex<W>, msg: &Msg) -> io::Result<()> {
    ipc::write_msg(&mut *out.lock().unwrap_or_else(|e| e.into_inner()), msg)
}

fn record(codec: VideoCodec, sets: &[Vec<u8>]) -> Vec<u8> {
    let of = |t: u8| sets.iter().filter(|n| nal_type(codec, n) == t).cloned().collect::<Vec<_>>();
    match codec {
        VideoCodec::H264 => build_avcc(&of(7), &of(8)),
        VideoCodec::H265 => build_hvcc(&of(32), &of(33), &of(34)),
    }
}

/// Sends every access unit of `r`; `pace(i)` is called before frame `i`. Returns the number of frames.
pub fn play_video<R: Read, W: Write>(codec: VideoCodec, r: R, out: &Mutex<W>, mut pace: impl FnMut(u64)) -> io::Result<u64> {
    let mut units = AccessUnits::new(codec, r);
    let mut sets: Vec<Vec<u8>> = Vec::new();
    let mut n = 0;
    let aud = match codec {
        VideoCodec::H264 => 9,
        VideoCodec::H265 => 35,
    };
    while let Some(unit) = units.next_unit()? {
        let (params, rest): (Vec<_>, Vec<_>) = unit.into_iter().partition(|nal| is_parameter_set(codec, nal_type(codec, nal)));
        if !params.is_empty() && params != sets {
            sets = params;
            send(out, &Msg::VideoConfig { codec, width: 0, height: 0, config: record(codec, &sets) })?;
        }
        let keyframe = rest.iter().any(|nal| is_random_access(codec, nal_type(codec, nal)));
        let mut data = Vec::with_capacity(rest.iter().map(|x| x.len() + 4).sum());
        for nal in rest.iter().filter(|nal| nal_type(codec, nal) != aud) {
            data.extend_from_slice(&(nal.len() as u32).to_be_bytes());
            data.extend_from_slice(nal);
        }
        if data.is_empty() {
            continue;
        }
        pace(n);
        send(out, &Msg::VideoFrame { ntp: n, keyframe, data })?;
        n += 1;
    }
    Ok(n)
}

fn sleep_until(t: Instant) {
    let now = Instant::now();
    if t > now {
        std::thread::sleep(t - now);
    }
}

fn play_audio(path: &Path, out: &Mutex<UnixStream>, t0: Instant) -> io::Result<()> {
    let caf = crate::caf::parse(&std::fs::read(path)?).map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e.to_string()))?;
    let frame_len = caf.frames_per_packet.max(1);
    send(out, &Msg::AudioConfig { codec: AudioCodec::Alac, sample_rate: caf.sample_rate, channels: caf.channels, frame_len, config: caf.cookie })?;
    let rate = u64::from(caf.sample_rate.max(1));
    for (i, data) in caf.packets.into_iter().enumerate() {
        let samples = i as u64 * u64::from(frame_len);
        sleep_until(t0 + Duration::from_micros(samples * 1_000_000 / rate));
        send(out, &Msg::AudioFrame { rtp: samples as u32, seq: i as u16, data })?;
    }
    Ok(())
}

fn print_answers(mut r: UnixStream) {
    while let Ok(Some(msg)) = ipc::read_msg(&mut r) {
        match msg {
            Msg::Ready { width, height, hw_decode } => eprintln!("feed: ready {width}x{height} hw_decode={hw_decode}"),
            Msg::Stats(s) => eprintln!(
                "feed: stats decoded={} presented={} dropped={} errors={} fps={:.2} decode_us={} latency_us={} hw={} audio={} audio_dropped={} underruns={} audio_delay_ms={}",
                s.decoded, s.presented, s.dropped, s.decode_errors, f64::from(s.fps_x100) / 100.0, s.decode_us_avg,
                s.latency_us_avg, s.hw_decode, s.audio_frames, s.audio_dropped, s.audio_underruns, s.audio_delay_ms
            ),
            Msg::Bye { reason } => eprintln!("feed: bye: {reason}"),
            other => eprintln!("feed: unexpected {other:?}"),
        }
    }
}

/// The feeder's threads on one end of a socket pair; the session reads the other end.
pub fn start(feed: Feed, stream: UnixStream) -> io::Result<()> {
    let codec = codec_of(&feed.video);
    let file = File::open(&feed.video)?;
    let reader = stream.try_clone()?;
    let out = Arc::new(Mutex::new(stream));
    std::thread::Builder::new().name("feed-answers".into()).spawn(move || print_answers(reader))?;
    let t0 = Instant::now();
    if let Some(path) = feed.audio {
        let out = out.clone();
        std::thread::Builder::new().name("feed-audio".into()).spawn(move || {
            if let Err(e) = play_audio(&path, &out, t0) {
                eprintln!("feed: audio {}: {e}", path.display());
            }
        })?;
    }
    let frame = Duration::from_secs(1) / feed.fps;
    std::thread::Builder::new().name("feed-video".into()).spawn(move || {
        let hello = Msg::Hello { version: ipc::VERSION, session: 1, client_name: "feed".into(), client_model: "h713-airplay-show".into(), peer: "local".into() };
        let played = send(&out, &hello).and_then(|_| play_video(codec, BufReader::new(file), &out, |i| sleep_until(t0 + frame * i as u32)));
        match played {
            Ok(n) => eprintln!("feed: {n} frames sent"),
            Err(e) => eprintln!("feed: video: {e}"),
        }
        let _ = send(&out, &Msg::End { reason: "end of the feed".into() });
    })?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_file_becomes_a_record_and_frames_without_parameter_sets() {
        let slice = |first: u8| [0u8, 0, 0, 1, 0x09, 0x10, 0, 0, 1, first, 0x88, 0x80].to_vec();
        let file = [vec![0, 0, 0, 1, 0x67, 0x64, 0, 0x2a, 0, 0, 1, 0x68, 0xeb], slice(0x65), slice(0x41)].concat();
        let out = Mutex::new(Vec::new());
        let mut paced = Vec::new();
        assert_eq!(play_video(VideoCodec::H264, &file[..], &out, |i| paced.push(i)).unwrap(), 2);
        assert_eq!(paced, [0, 1]);
        let wire = out.into_inner().unwrap();
        let mut r = &wire[..];
        let Some(Msg::VideoConfig { codec, config, .. }) = ipc::read_msg(&mut r).unwrap() else { panic!("no config first") };
        assert_eq!(crate::paramsets::parse(codec, &config).unwrap(), vec![vec![0x67, 0x64, 0, 0x2a], vec![0x68, 0xeb]]);
        let frames: Vec<_> = std::iter::from_fn(|| ipc::read_msg(&mut r).unwrap()).collect();
        assert_eq!(
            frames,
            vec![
                Msg::VideoFrame { ntp: 0, keyframe: true, data: vec![0, 0, 0, 3, 0x65, 0x88, 0x80] },
                Msg::VideoFrame { ntp: 1, keyframe: false, data: vec![0, 0, 0, 3, 0x41, 0x88, 0x80] },
            ]
        );
    }
}
