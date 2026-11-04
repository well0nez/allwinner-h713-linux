// SPDX-License-Identifier: GPL-3.0-only
//! One session: the threads, `Ready` once the decoder and the toplevel are up, `Stats` once a second, `Bye` on a
//! stop, and the end within two seconds whatever a thread does.

use super::audio::{self, Queue};
use super::decode::{Decoder, HwDevice};
use super::present::{self, Ended};
use super::slot::Slot;
use crate::signals::Signals;
use crate::stats::{add, Counters, Window};
use proto::config::Config;
use proto::ipc::{self, Msg, VideoCodec};
use std::io::{self, BufReader};
use std::net::Shutdown;
use std::os::unix::net::UnixStream;
use std::sync::atomic::Ordering::Relaxed;
use std::sync::mpsc::{sync_channel, Receiver};
use std::sync::{Arc, Condvar, Mutex};
use std::thread;
use std::time::Duration;

const STOP_WITHIN: Duration = Duration::from_millis(1800);

enum Video {
    Config(VideoCodec, Vec<u8>),
    Frame(Vec<u8>, bool, u64),
}

#[derive(Default)]
struct Up {
    picture: Option<(u32, u32)>,
    decoder: Option<bool>,
    sent: bool,
    failed: Option<String>,
    done: bool,
}

struct Shared {
    out: Mutex<UnixStream>,
    stream: UnixStream,
    counters: Counters,
    slot: Slot,
    audio: Queue,
    up: Mutex<Up>,
    tick: Condvar,
}

impl Shared {
    fn send(&self, msg: &Msg) {
        let _ = ipc::write_msg(&mut *self.out.lock().unwrap_or_else(|e| e.into_inner()), msg);
    }

    fn update(&self, f: impl FnOnce(&mut Up)) {
        let mut up = self.up.lock().unwrap_or_else(|e| e.into_inner());
        f(&mut up);
        if let (false, Some((width, height)), Some(hw_decode)) = (up.sent, up.picture, up.decoder) {
            up.sent = true;
            self.send(&Msg::Ready { width, height, hw_decode });
        }
        self.tick.notify_all();
    }

    /// Says Bye and closes the stream; the reader sees the end and the session goes down.
    fn end(&self, reason: &str, failed: bool) {
        eprintln!("h713-airplay-show: {reason}");
        self.update(|u| u.failed = failed.then(|| reason.to_string()).or(u.failed.take()));
        self.send(&Msg::Bye { reason: reason.into() });
        let _ = self.stream.shutdown(Shutdown::Both);
    }
}

fn decoder_thread(s: &Shared, rx: Receiver<Video>) {
    let hw = HwDevice::open().inspect_err(|e| eprintln!("h713-airplay-show: {e}; software decoding")).ok();
    let mut dec: Option<Decoder> = None;
    for item in rx {
        if s.slot.quitting() {
            return;
        }
        match item {
            Video::Config(codec, record) => {
                if dec.as_ref().is_some_and(|d| d.is_for(codec, &record)) {
                    continue;
                }
                drop(dec.take());
                match Decoder::open(codec, &record, hw.as_ref()) {
                    Ok(d) => {
                        dec = Some(d);
                        s.counters.hw_decode.store(hw.is_some(), Relaxed);
                        s.update(|u| u.decoder = Some(hw.is_some()));
                    }
                    Err(e) => return s.end(&format!("the video decoder: {e}"), true),
                }
            }
            Video::Frame(data, keyframe, arrival) => {
                let Some(d) = dec.as_mut() else {
                    add(&s.counters.decode_errors);
                    continue;
                };
                let mut out = |f: super::slot::Frame| {
                    add(&s.counters.decoded);
                    s.counters.hw_decode.store(f.is_hw(), Relaxed);
                    Counters::mean(&s.counters.decode_us, super::now_us().saturating_sub(f.arrival_us()));
                    if s.slot.put(f) {
                        add(&s.counters.dropped);
                    }
                };
                if let Err(e) = d.decode(data, keyframe, arrival, &mut out) {
                    if s.counters.decode_errors.fetch_add(1, Relaxed) < 10 {
                        eprintln!("h713-airplay-show: {e}");
                    }
                }
            }
        }
    }
}

fn presenter_thread(s: &Shared) {
    let up = |w, h, what: String| {
        eprintln!("h713-airplay-show: on h713-warp: {w}x{h}, {what}");
        s.update(|u| u.picture = Some((w, h)));
    };
    match present::run(&s.slot, &s.counters, &up) {
        Ok(Ended::Quit) => {}
        Ok(Ended::Closed) => s.end("h713-warp closed the window", false),
        Err(e) => s.end(&format!("the picture path: {e}"), true),
    }
}

fn stats_thread(s: &Shared) {
    let mut window = Window::default();
    let mut up = s.up.lock().unwrap_or_else(|e| e.into_inner());
    while !up.done {
        let (next, timeout) = s.tick.wait_timeout(up, Duration::from_secs(1)).unwrap_or_else(|e| e.into_inner());
        up = next;
        if timeout.timed_out() && !up.done {
            drop(up);
            s.send(&Msg::Stats(s.counters.report(&mut window, super::now_us())));
            up = s.up.lock().unwrap_or_else(|e| e.into_inner());
        }
    }
}

fn read(s: &Shared, video: &std::sync::mpsc::SyncSender<Video>, audio_on: bool) -> io::Result<()> {
    let mut r = BufReader::with_capacity(1 << 20, s.stream.try_clone()?);
    loop {
        let Some(msg) = ipc::read_msg(&mut r)? else { return Ok(()) };
        let sent = match msg {
            Msg::Hello { version, client_name, client_model, peer, .. } => {
                eprintln!("h713-airplay-show: {client_name} ({client_model}, {peer}), protocol {version}");
                Ok(())
            }
            Msg::VideoConfig { codec, width, height, config } => {
                eprintln!("h713-airplay-show: {codec:?} {width}x{height}");
                video.send(Video::Config(codec, config))
            }
            Msg::VideoFrame { keyframe, data, .. } => video.send(Video::Frame(data, keyframe, super::now_us())),
            Msg::AudioConfig { codec, sample_rate, channels, frame_len, config } if audio_on => {
                s.audio.config(audio::Config { codec, sample_rate, channels, frame_len, config });
                Ok(())
            }
            Msg::AudioFrame { data, .. } if audio_on => {
                s.audio.frame(data, &s.counters);
                Ok(())
            }
            Msg::Volume { db } => {
                s.audio.volume(db);
                Ok(())
            }
            Msg::Flush => {
                s.audio.flush();
                Ok(())
            }
            Msg::End { reason } => {
                eprintln!("h713-airplay-show: the receiver ended the session: {reason}");
                return Ok(());
            }
            _ => Ok(()),
        };
        if sent.is_err() {
            return Ok(());
        }
    }
}

pub fn run(config: Config, stream: UnixStream, stop: Signals) -> io::Result<()> {
    let s = Arc::new(Shared {
        out: Mutex::new(stream.try_clone()?),
        stream,
        counters: Counters::default(),
        slot: Slot::new()?,
        audio: Queue::new(),
        up: Mutex::new(Up::default()),
        tick: Condvar::new(),
    });
    let (vtx, vrx) = sync_channel::<Video>(64);
    let spawn = |name: &str, f: Box<dyn FnOnce() + Send>| thread::Builder::new().name(name.into()).spawn(f);
    let threads = [
        spawn("decode", Box::new({ let s = s.clone(); move || decoder_thread(&s, vrx) }))?,
        spawn("present", Box::new({ let s = s.clone(); move || presenter_thread(&s) }))?,
        spawn("audio", Box::new({ let s = s.clone(); let dev = config.audio_device.clone(); move || audio::run(&s.audio, &dev, &s.counters) }))?,
        spawn("stats", Box::new({ let s = s.clone(); move || stats_thread(&s) }))?,
    ];
    spawn("signals", Box::new({
        let s = s.clone();
        move || {
            if let Ok(n) = stop.wait() {
                s.end(&format!("stopped by signal {n}"), false);
            }
        }
    }))?;
    let read = read(&s, &vtx, config.audio);
    spawn("deadline", Box::new(|| {
        thread::sleep(STOP_WITHIN);
        eprintln!("h713-airplay-show: the threads did not end within {} ms; exiting", STOP_WITHIN.as_millis());
        // SAFETY: ends the process at once; nothing of ours needs to run after this.
        unsafe { libc::_exit(0) };
    }))?;
    drop(vtx);
    s.slot.quit();
    s.audio.quit();
    s.update(|u| u.done = true);
    threads.into_iter().for_each(|t| drop(t.join()));
    let st = s.counters.report(&mut Window::default(), super::now_us());
    eprintln!("h713-airplay-show: decoded {} presented {} dropped {} errors {} audio {} underruns {}", st.decoded, st.presented, st.dropped, st.decode_errors, st.audio_frames, st.audio_underruns);
    let failed = s.up.lock().unwrap_or_else(|e| e.into_inner()).failed.take();
    match (failed, read) {
        (Some(reason), _) => Err(io::Error::other(reason)),
        (None, Err(e)) if e.kind() != io::ErrorKind::UnexpectedEof && e.kind() != io::ErrorKind::ConnectionReset => Err(e),
        _ => Ok(()),
    }
}
