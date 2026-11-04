// SPDX-License-Identifier: GPL-3.0-only
//! The stream between receiver and presenter. One frame per message: `u32 LE length | u8 kind | payload`,
//! length = 1 + payload length, at most [`MAX_FRAME`]. In the payload integers are little-endian, strings and
//! byte strings `u32 LE length | bytes`. The receiver opens the connection when a sender sets up its stream and
//! sends [`Msg::Hello`] first; the presenter answers [`Msg::Ready`] once its picture path is up and then
//! [`Msg::Stats`] once a second. Either side ends the session by closing (the presenter after [`Msg::Bye`],
//! the receiver after [`Msg::End`]); EOF is an end too.
//!
//! Video payloads are what the sender's mirror stream carries after decryption: length-prefixed NAL units
//! (4-byte big-endian lengths, AVCC/HVCC framing). [`Msg::VideoConfig`] carries the raw payload of the
//! sender's codec packet (type 1): an avcC record for H.264 (option `16 01`), an hvcC record for H.265
//! (`1e 01`), sent again whenever the sender changes resolution or codec.

use std::io::{self, Read, Write};

pub const VERSION: u16 = 1;
pub const MAX_FRAME: usize = 16 << 20;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum VideoCodec {
    H264 = 1,
    H265 = 2,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum AudioCodec {
    AacEld = 1,
    Alac = 2,
    AacLc = 3,
    Pcm = 4,
}

/// The presenter's counters, sent once a second; the receiver shows them in `ctl status`.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Stats {
    pub decoded: u64,
    pub presented: u64,
    /// Decoded but never shown: a newer picture came before the panel took this one.
    pub dropped: u64,
    pub decode_errors: u64,
    /// Pictures on the panel per second over the last second, times 100.
    pub fps_x100: u32,
    /// Mean time from a frame's arrival at the presenter to its picture out of the decoder, last second.
    pub decode_us_avg: u32,
    /// Mean time from a frame's arrival at the presenter to its presentation (wp_presentation), last second.
    pub latency_us_avg: u32,
    pub hw_decode: bool,
    pub audio_frames: u64,
    pub audio_dropped: u64,
    pub audio_underruns: u64,
    pub audio_delay_ms: u32,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Msg {
    Hello { version: u16, session: u64, client_name: String, client_model: String, peer: String },
    VideoConfig { codec: VideoCodec, width: u32, height: u32, config: Vec<u8> },
    VideoFrame { ntp: u64, keyframe: bool, data: Vec<u8> },
    AudioConfig { codec: AudioCodec, sample_rate: u32, channels: u8, frame_len: u32, config: Vec<u8> },
    AudioFrame { rtp: u32, seq: u16, data: Vec<u8> },
    /// AirPlay volume in dB, -30..0, and -144 for mute.
    Volume { db: f32 },
    /// The sender flushed: drop what is queued, keep the decoder.
    Flush,
    End { reason: String },
    Ready { width: u32, height: u32, hw_decode: bool },
    Stats(Stats),
    Bye { reason: String },
}

const HELLO: u8 = 0x01;
const VIDEO_CONFIG: u8 = 0x02;
const VIDEO_FRAME: u8 = 0x03;
const AUDIO_CONFIG: u8 = 0x04;
const AUDIO_FRAME: u8 = 0x05;
const VOLUME: u8 = 0x06;
const FLUSH: u8 = 0x07;
const END: u8 = 0x08;
const READY: u8 = 0x81;
const STATS: u8 = 0x82;
const BYE: u8 = 0x83;

struct Out(Vec<u8>);

impl Out {
    fn u8(&mut self, v: u8) {
        self.0.push(v);
    }
    fn u16(&mut self, v: u16) {
        self.0.extend_from_slice(&v.to_le_bytes());
    }
    fn u32(&mut self, v: u32) {
        self.0.extend_from_slice(&v.to_le_bytes());
    }
    fn u64(&mut self, v: u64) {
        self.0.extend_from_slice(&v.to_le_bytes());
    }
    fn bytes(&mut self, v: &[u8]) {
        self.u32(v.len() as u32);
        self.0.extend_from_slice(v);
    }
}

struct In<'a>(&'a [u8]);

fn bad(what: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, format!("ipc: {what}"))
}

impl<'a> In<'a> {
    fn take(&mut self, n: usize) -> io::Result<&'a [u8]> {
        if self.0.len() < n {
            return Err(bad("short frame"));
        }
        let (a, b) = self.0.split_at(n);
        self.0 = b;
        Ok(a)
    }
    fn u8(&mut self) -> io::Result<u8> {
        Ok(self.take(1)?[0])
    }
    fn u16(&mut self) -> io::Result<u16> {
        Ok(u16::from_le_bytes(self.take(2)?.try_into().unwrap()))
    }
    fn u32(&mut self) -> io::Result<u32> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }
    fn u64(&mut self) -> io::Result<u64> {
        Ok(u64::from_le_bytes(self.take(8)?.try_into().unwrap()))
    }
    fn bytes(&mut self) -> io::Result<Vec<u8>> {
        let n = self.u32()? as usize;
        Ok(self.take(n)?.to_vec())
    }
    fn string(&mut self) -> io::Result<String> {
        String::from_utf8(self.bytes()?).map_err(|_| bad("string is not UTF-8"))
    }
}

fn video_codec(v: u8) -> io::Result<VideoCodec> {
    match v {
        1 => Ok(VideoCodec::H264),
        2 => Ok(VideoCodec::H265),
        _ => Err(bad("unknown video codec")),
    }
}

fn audio_codec(v: u8) -> io::Result<AudioCodec> {
    match v {
        1 => Ok(AudioCodec::AacEld),
        2 => Ok(AudioCodec::Alac),
        3 => Ok(AudioCodec::AacLc),
        4 => Ok(AudioCodec::Pcm),
        _ => Err(bad("unknown audio codec")),
    }
}

/// One whole frame, length prefix included, ready for a single `write_all`.
pub fn encode(msg: &Msg) -> Vec<u8> {
    let mut o = Out(vec![0, 0, 0, 0]);
    match msg {
        Msg::Hello { version, session, client_name, client_model, peer } => {
            o.u8(HELLO);
            o.u16(*version);
            o.u64(*session);
            o.bytes(client_name.as_bytes());
            o.bytes(client_model.as_bytes());
            o.bytes(peer.as_bytes());
        }
        Msg::VideoConfig { codec, width, height, config } => {
            o.u8(VIDEO_CONFIG);
            o.u8(*codec as u8);
            o.u32(*width);
            o.u32(*height);
            o.bytes(config);
        }
        Msg::VideoFrame { ntp, keyframe, data } => {
            o.u8(VIDEO_FRAME);
            o.u64(*ntp);
            o.u8(*keyframe as u8);
            o.bytes(data);
        }
        Msg::AudioConfig { codec, sample_rate, channels, frame_len, config } => {
            o.u8(AUDIO_CONFIG);
            o.u8(*codec as u8);
            o.u32(*sample_rate);
            o.u8(*channels);
            o.u32(*frame_len);
            o.bytes(config);
        }
        Msg::AudioFrame { rtp, seq, data } => {
            o.u8(AUDIO_FRAME);
            o.u32(*rtp);
            o.u16(*seq);
            o.bytes(data);
        }
        Msg::Volume { db } => {
            o.u8(VOLUME);
            o.u32(db.to_bits());
        }
        Msg::Flush => o.u8(FLUSH),
        Msg::End { reason } => {
            o.u8(END);
            o.bytes(reason.as_bytes());
        }
        Msg::Ready { width, height, hw_decode } => {
            o.u8(READY);
            o.u32(*width);
            o.u32(*height);
            o.u8(*hw_decode as u8);
        }
        Msg::Stats(s) => {
            o.u8(STATS);
            for v in [s.decoded, s.presented, s.dropped, s.decode_errors] {
                o.u64(v);
            }
            for v in [s.fps_x100, s.decode_us_avg, s.latency_us_avg] {
                o.u32(v);
            }
            o.u8(s.hw_decode as u8);
            for v in [s.audio_frames, s.audio_dropped, s.audio_underruns] {
                o.u64(v);
            }
            o.u32(s.audio_delay_ms);
        }
        Msg::Bye { reason } => {
            o.u8(BYE);
            o.bytes(reason.as_bytes());
        }
    }
    let len = (o.0.len() - 4) as u32;
    o.0[..4].copy_from_slice(&len.to_le_bytes());
    o.0
}

/// A frame's body (kind and payload, without the length prefix).
pub fn decode(body: &[u8]) -> io::Result<Msg> {
    let mut i = In(body);
    let msg = match i.u8()? {
        HELLO => Msg::Hello {
            version: i.u16()?,
            session: i.u64()?,
            client_name: i.string()?,
            client_model: i.string()?,
            peer: i.string()?,
        },
        VIDEO_CONFIG => Msg::VideoConfig {
            codec: video_codec(i.u8()?)?,
            width: i.u32()?,
            height: i.u32()?,
            config: i.bytes()?,
        },
        VIDEO_FRAME => Msg::VideoFrame { ntp: i.u64()?, keyframe: i.u8()? != 0, data: i.bytes()? },
        AUDIO_CONFIG => Msg::AudioConfig {
            codec: audio_codec(i.u8()?)?,
            sample_rate: i.u32()?,
            channels: i.u8()?,
            frame_len: i.u32()?,
            config: i.bytes()?,
        },
        AUDIO_FRAME => Msg::AudioFrame { rtp: i.u32()?, seq: i.u16()?, data: i.bytes()? },
        VOLUME => Msg::Volume { db: f32::from_bits(i.u32()?) },
        FLUSH => Msg::Flush,
        END => Msg::End { reason: i.string()? },
        READY => Msg::Ready { width: i.u32()?, height: i.u32()?, hw_decode: i.u8()? != 0 },
        STATS => Msg::Stats(Stats {
            decoded: i.u64()?,
            presented: i.u64()?,
            dropped: i.u64()?,
            decode_errors: i.u64()?,
            fps_x100: i.u32()?,
            decode_us_avg: i.u32()?,
            latency_us_avg: i.u32()?,
            hw_decode: i.u8()? != 0,
            audio_frames: i.u64()?,
            audio_dropped: i.u64()?,
            audio_underruns: i.u64()?,
            audio_delay_ms: i.u32()?,
        }),
        BYE => Msg::Bye { reason: i.string()? },
        _ => return Err(bad("unknown kind")),
    };
    if !i.0.is_empty() {
        return Err(bad("trailing bytes"));
    }
    Ok(msg)
}

pub fn write_msg(w: &mut impl Write, msg: &Msg) -> io::Result<()> {
    w.write_all(&encode(msg))
}

/// The next message; `Ok(None)` at a clean EOF between frames.
pub fn read_msg(r: &mut impl Read) -> io::Result<Option<Msg>> {
    let mut len = [0u8; 4];
    let mut got = 0;
    while got < 4 {
        match r.read(&mut len[got..]) {
            Ok(0) if got == 0 => return Ok(None),
            Ok(0) => return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "ipc: EOF inside a length")),
            Ok(n) => got += n,
            Err(e) if e.kind() == io::ErrorKind::Interrupted => {}
            Err(e) => return Err(e),
        }
    }
    let len = u32::from_le_bytes(len) as usize;
    if len == 0 || len > MAX_FRAME {
        return Err(bad("frame length out of range"));
    }
    let mut body = vec![0u8; len];
    r.read_exact(&mut body)?;
    decode(&body).map(Some)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn all() -> Vec<Msg> {
        vec![
            Msg::Hello { version: VERSION, session: 7, client_name: "iPhone".into(), client_model: "iPhone17,1".into(), peer: "192.168.4.23".into() },
            Msg::VideoConfig { codec: VideoCodec::H265, width: 1920, height: 886, config: vec![1, 2, 3] },
            Msg::VideoFrame { ntp: u64::MAX - 1, keyframe: true, data: vec![0, 0, 0, 1, 0x65] },
            Msg::AudioConfig { codec: AudioCodec::AacEld, sample_rate: 44100, channels: 2, frame_len: 480, config: vec![0xf8, 0xe8, 0x50, 0] },
            Msg::AudioFrame { rtp: 1234, seq: 65535, data: vec![9; 300] },
            Msg::Volume { db: -144.0 },
            Msg::Flush,
            Msg::End { reason: "teardown".into() },
            Msg::Ready { width: 1920, height: 1080, hw_decode: true },
            Msg::Stats(Stats { decoded: 1, presented: 2, dropped: 3, decode_errors: 4, fps_x100: 5999, decode_us_avg: 6, latency_us_avg: 7, hw_decode: true, audio_frames: 8, audio_dropped: 9, audio_underruns: 10, audio_delay_ms: 11 }),
            Msg::Bye { reason: "stopped".into() },
        ]
    }

    #[test]
    fn every_message_survives_a_stream_round_trip() {
        let mut wire = Vec::new();
        for m in all() {
            write_msg(&mut wire, &m).unwrap();
        }
        let mut r = &wire[..];
        for m in all() {
            assert_eq!(read_msg(&mut r).unwrap(), Some(m));
        }
        assert_eq!(read_msg(&mut r).unwrap(), None);
    }

    #[test]
    fn a_truncated_or_oversized_frame_is_an_error() {
        let wire = encode(&Msg::VideoFrame { ntp: 1, keyframe: false, data: vec![1; 64] });
        assert!(read_msg(&mut &wire[..wire.len() - 1]).is_err());
        assert!(read_msg(&mut &((MAX_FRAME as u32 + 1).to_le_bytes())[..]).is_err());
        assert!(decode(&[0x55]).is_err());
    }
}
