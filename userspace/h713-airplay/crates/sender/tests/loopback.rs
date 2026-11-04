// SPDX-License-Identifier: GPL-3.0-only
//! sendtest against the receiver over loopback, with a fake presenter on the show socket and every path in a
//! temporary directory. No sleeps: the test follows the presenter's messages and `ctl wait`.

use proto::config::Config;
use proto::ipc::{self, AudioCodec, Msg, VideoCodec};
use sender::{Audio, SendTest};
use std::net::SocketAddr;
use std::os::unix::net::UnixListener;
use std::path::{Path, PathBuf};
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::{Arc, Mutex};
use std::time::Duration;

const SPS: &str = "67f4000d919b28283f6022000003000200000300781e28532c";
const PPS: &str = "68ebe3c44844";
const TIMEOUT: Duration = Duration::from_secs(20);

fn hex(s: &str) -> Vec<u8> {
    (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap()).collect()
}

/// 30 access units, key frames at 0 and 15; returns the Annex B file and each unit's AVCC payload.
fn stream(dir: &Path) -> (PathBuf, Vec<Vec<u8>>) {
    let (mut file, mut expected) = (Vec::new(), Vec::new());
    for i in 0..30u32 {
        let key = i % 15 == 0;
        let slice: Vec<u8> = [if key { 0x65 } else { 0x41 }, 0x88].into_iter().chain((0..(37 + i * 13)).map(|j| (j * 7 + i) as u8 | 1)).collect();
        let second: Vec<u8> = [if key { 0x65 } else { 0x41 }, 0x08, i as u8 | 1].to_vec();
        if key {
            for ps in [hex(SPS), hex(PPS)] {
                file.extend_from_slice(&[0, 0, 0, 1]);
                file.extend_from_slice(&ps);
            }
        }
        let mut avcc = Vec::new();
        for nal in [&slice, &second] {
            file.extend_from_slice(&[0, 0, 1]);
            file.extend_from_slice(nal);
            avcc.extend_from_slice(&(nal.len() as u32).to_be_bytes());
            avcc.extend_from_slice(nal);
        }
        expected.push(avcc);
    }
    let path = dir.join("test.h264");
    std::fs::write(&path, file).unwrap();
    (path, expected)
}

fn wav(dir: &Path, pcm: &[i16]) -> PathBuf {
    let data: Vec<u8> = pcm.iter().flat_map(|s| s.to_le_bytes()).collect();
    let mut w = b"RIFF".to_vec();
    w.extend_from_slice(&(36 + data.len() as u32).to_le_bytes());
    w.extend_from_slice(b"WAVEfmt ");
    for v in [16u32, 0x0002_0001, 44100, 44100 * 4, 0x0010_0004] {
        w.extend_from_slice(&v.to_le_bytes());
    }
    w.extend_from_slice(b"data");
    w.extend_from_slice(&(data.len() as u32).to_le_bytes());
    w.extend_from_slice(&data);
    let path = dir.join("test.wav");
    std::fs::write(&path, w).unwrap();
    path
}

#[derive(Debug, PartialEq)]
enum Seen {
    Video,
    Audio,
    Closed,
    Other,
}

type Log = Arc<Mutex<Vec<Vec<Msg>>>>;

/// Accepts the receiver's connections like the presenter: answers Hello with Ready, keeps every message.
fn fake_presenter(path: &Path) -> (Log, Receiver<(usize, Seen)>) {
    let listener = UnixListener::bind(path).unwrap();
    let log: Log = Arc::default();
    let (tx, rx) = mpsc::channel();
    let l = log.clone();
    std::thread::spawn(move || {
        for (n, conn) in listener.incoming().enumerate() {
            let mut conn = conn.unwrap();
            l.lock().unwrap().push(Vec::new());
            let (l, tx): (Log, Sender<_>) = (l.clone(), tx.clone());
            std::thread::spawn(move || {
                while let Ok(Some(m)) = ipc::read_msg(&mut conn) {
                    if matches!(m, Msg::Hello { .. }) {
                        ipc::write_msg(&mut conn, &Msg::Ready { width: 1920, height: 1080, hw_decode: false }).unwrap();
                    }
                    let seen = match m {
                        Msg::VideoFrame { .. } => Seen::Video,
                        Msg::AudioFrame { .. } => Seen::Audio,
                        _ => Seen::Other,
                    };
                    l.lock().unwrap()[n].push(m);
                    let _ = tx.send((n, seen));
                }
                let _ = tx.send((n, Seen::Closed));
            });
        }
    });
    (log, rx)
}

fn until(rx: &Receiver<(usize, Seen)>, mut done: impl FnMut(usize, &Seen) -> bool) {
    loop {
        let (n, s) = rx.recv_timeout(TIMEOUT).expect("the presenter heard nothing for 20 s");
        if done(n, &s) {
            return;
        }
    }
}

fn ctl(cmd: &str) -> String {
    proto::ctl::request(&proto::paths::ctl_socket(), cmd, Some(TIMEOUT)).unwrap()
}

fn frames(log: &Log, conn: usize) -> Vec<(bool, Vec<u8>)> {
    let l = log.lock().unwrap();
    l[conn].iter().filter_map(|m| match m {
        Msg::VideoFrame { keyframe, data, .. } => Some((*keyframe, data.clone())),
        _ => None,
    }).collect()
}

/// Checks the delivered frames against the sent ones (the file looped): in order and decrypted byte for byte,
/// and the only gaps are frames dropped right before a key frame (the queue keeps video from the last key frame
/// on). Returns how many sent frames the delivery accounts for.
fn check_frames(got: &[(bool, Vec<u8>)], expected: &[Vec<u8>]) -> usize {
    let mut pos = 0;
    for (i, (key, data)) in got.iter().enumerate() {
        let mut p = pos;
        while &expected[p % expected.len()] != data {
            p += 1;
            assert!(p - pos < expected.len(), "frame {i} is none of the frames sent");
        }
        assert!(p == pos || *key, "frame {i}: only frames before a key frame may be dropped");
        assert_eq!(*key, p % 15 == 0, "frame {i}");
        pos = p + 1;
    }
    pos
}

fn end_reason(log: &Log, conn: usize) -> Option<String> {
    log.lock().unwrap()[conn].iter().find_map(|m| match m {
        Msg::End { reason } => Some(reason.clone()),
        _ => None,
    })
}

#[test]
fn sendtest_sessions_reach_the_presenter_decrypted_end_on_teardown_and_disconnect_and_hand_over() {
    let dir = std::env::temp_dir().join(format!("h713-airplay-loopback-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    std::env::set_var("H713_AIRPLAY_CTL", dir.join("ctl"));
    std::env::set_var("H713_AIRPLAY_SHOW_SOCKET", dir.join("show.sock"));
    std::env::set_var("H713_AIRPLAY_STATE", dir.join("state"));
    std::env::set_var("H713_WIFI_ENV", dir.join("wifi.env"));
    std::fs::write(dir.join("wifi.env"), "mode=ap\nssid=h713\npassword=not-for-status\n").unwrap();
    let (log, rx) = fake_presenter(&dir.join("show.sock"));
    let config = Config { name: "Loopback".into(), ..Config::default() };
    let handle = receiver::start(config, receiver::Options { ports: receiver::Ports::default(), mdns: false }).unwrap();
    let target = SocketAddr::from(([127, 0, 0, 1], handle.ports.rtsp));
    let (video, expected) = stream(&dir);
    let pcm = sender::tone(0.5);
    let audio_frames = sender::alac_frames(&pcm);
    let wav = wav(&dir, &pcm);
    let test = |seconds: Option<f64>, bare_teardown: bool| SendTest {
        target,
        video: video.clone(),
        fps: 240,
        audio: Audio::Wav(wav.clone()),
        seconds,
        bare_teardown,
    };

    let probe = sender::probe_text(&target.to_string()).unwrap();
    assert!(probe.contains("features: 0x400527ffee6"), "{probe}");
    assert!(probe.contains("Public: SETUP, RECORD, FLUSH, TEARDOWN, OPTIONS, GET_PARAMETER, SET_PARAMETER"), "{probe}");
    assert_eq!(ctl("status").lines().nth(1), Some("state idle"), "a probe claims no session");

    // Session 1: a looping sender; every frame and audio packet must arrive decrypted, then ctl disconnect ends it.
    let a = std::thread::spawn({
        let t = test(Some(60.0), false);
        move || sender::run(&t)
    });
    let (mut videos, mut audios) = (0, 0);
    until(&rx, |n, s| {
        assert_eq!(n, 0);
        match s {
            Seen::Video => videos += 1,
            Seen::Audio => audios += 1,
            _ => {}
        }
        videos >= 45 && audios >= 12
    });
    assert_eq!(ctl("wait streaming 5000"), "ok streaming\n");
    let status = proto::ctl::Status::from_text(&ctl("status")).unwrap();
    assert_eq!(status.client.as_ref().map(|c| c.name.as_str()), Some("h713-airplay sendtest"));
    assert!(status.video.starts_with("h264 320x240 frames "), "{}", status.video);
    assert!(status.audio.starts_with("alac 44100 frames "), "{}", status.audio);
    assert!(status.presenter.starts_with("ready "), "{}", status.presenter);
    assert_eq!(status.wifi, vec!["h713@wlan0"]);
    assert_eq!(ctl("disconnect"), "ok\n");
    assert!(a.join().unwrap().is_err(), "the receiver closed the sender's connections");
    assert_eq!(ctl("wait idle 2000"), "ok idle\n");
    until(&rx, |n, s| n == 0 && *s == Seen::Closed);
    {
        let l = log.lock().unwrap();
        let msgs = &l[0];
        assert!(matches!(&msgs[0], Msg::Hello { client_name, peer, .. } if client_name == "h713-airplay sendtest" && peer == "127.0.0.1"));
        let config = msgs.iter().find_map(|m| match m {
            Msg::VideoConfig { codec: VideoCodec::H264, width: 320, height: 240, config } => Some(config.clone()),
            _ => None,
        });
        assert_eq!(config, Some(sender::avcc_record(&hex(SPS), &hex(PPS))));
        assert!(msgs.iter().any(|m| matches!(m, Msg::AudioConfig { codec: AudioCodec::Alac, sample_rate: 44100, frame_len: 352, .. })));
        assert!(msgs.iter().any(|m| matches!(m, Msg::Volume { db } if *db == -15.0)));
        let audio: Vec<_> = msgs.iter().filter_map(|m| match m {
            Msg::AudioFrame { seq, data, .. } => Some((*seq, data.clone())),
            _ => None,
        }).collect();
        assert!(audio.len() >= 12);
        for (seq, data) in &audio {
            assert_eq!(data, &audio_frames[usize::from(*seq) % audio_frames.len()], "audio packet {seq}");
        }
    }
    assert!(check_frames(&frames(&log, 0), &expected) >= 45, "the keystream runs on across packets and file loops");
    assert_eq!(end_reason(&log, 0).as_deref(), Some("ctl disconnect"));

    // Session 2: the file once, TEARDOWN with stream types: all 30 frames, then End, then idle.
    let report = sender::run(&test(None, false)).unwrap();
    assert_eq!((report.frames, report.width, report.height), (30, 320, 240));
    assert_eq!(ctl("wait idle 2000"), "ok idle\n");
    until(&rx, |n, s| n == 1 && *s == Seen::Closed);
    assert_eq!(check_frames(&frames(&log, 1), &expected), 30, "every frame up to the last one arrived before End");
    assert_eq!(end_reason(&log, 1).as_deref(), Some("teardown"));

    // Sessions 3 and 4: a second sender takes over the first; iOS 27's TEARDOWN without types ends it.
    let c = std::thread::spawn({
        let t = test(Some(60.0), false);
        move || sender::run(&t)
    });
    until(&rx, |n, s| n == 2 && *s == Seen::Video);
    let report = sender::run(&test(None, true)).unwrap();
    assert_eq!(report.frames, 30);
    assert!(c.join().unwrap().is_err(), "the first sender was cut off");
    assert_eq!(ctl("wait idle 2000"), "ok idle\n");
    until(&rx, |n, s| n == 3 && *s == Seen::Closed);
    assert_eq!(end_reason(&log, 2).as_deref(), Some("taken over"));
    assert_eq!(check_frames(&frames(&log, 3), &expected), 30);
    assert_eq!(end_reason(&log, 3).as_deref(), Some("teardown"));
    let status = proto::ctl::Status::from_text(&ctl("status")).unwrap();
    assert_eq!((status.state, status.sessions), (proto::ctl::State::Idle, 4));
    std::fs::remove_dir_all(&dir).unwrap();
}
