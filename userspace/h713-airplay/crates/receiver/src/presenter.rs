// SPDX-License-Identifier: GPL-3.0-only
//! The link to the presenter (proto::ipc over `paths::show_socket()`): a writer thread fed by a bounded queue and
//! a reader thread for Ready/Stats/Bye. The queue keeps video from the last key frame on (at most 8 s or
//! 32 MiB) until the presenter reads, and audio for at most 120 ms (the oldest goes first).

use proto::ipc::{self, Msg};
use std::collections::VecDeque;
use std::io;
use std::os::unix::net::UnixStream;
use std::sync::{Arc, Condvar, Mutex};
use std::time::{Duration, Instant};

const VIDEO_SPAN: Duration = Duration::from_secs(8);
const VIDEO_BYTES: usize = 32 << 20;
const AUDIO_SPAN_US: u64 = 120_000;
const END_GRACE: Duration = Duration::from_secs(1);

enum Kind {
    Control,
    Video { at: Instant, len: usize },
    Audio,
}

struct Item {
    msg: Msg,
    kind: Kind,
}

#[derive(Default)]
struct Queue {
    items: VecDeque<Item>,
    video_bytes: usize,
    audio_items: usize,
    /// Video was dropped: wait for the next key frame before queueing frames again.
    await_key: bool,
    closing: bool,
    done: bool,
    dropped_video: u64,
    dropped_audio: u64,
}

impl Queue {
    fn drop_video(&mut self) {
        let before = self.items.len();
        self.items.retain(|i| !matches!(i.kind, Kind::Video { .. }));
        self.dropped_video += (before - self.items.len()) as u64;
        self.video_bytes = 0;
    }
}

pub struct Link {
    stream: UnixStream,
    q: Mutex<Queue>,
    cv: Condvar,
    /// Microseconds of audio per queued frame (spf / sample rate), 0 before AudioConfig.
    audio_frame_us: Mutex<u64>,
}

pub enum Event {
    Ready { width: u32, height: u32, hw_decode: bool },
    Stats(ipc::Stats),
    Gone(String),
}

impl Link {
    /// Connects and starts both threads; `on_event` runs on the reader thread.
    pub fn connect(hello: Msg, on_event: impl Fn(Event) + Send + 'static) -> io::Result<Arc<Link>> {
        let stream = UnixStream::connect(proto::paths::show_socket())?;
        let reader = stream.try_clone()?;
        let link = Arc::new(Link { stream, q: Mutex::default(), cv: Condvar::new(), audio_frame_us: Mutex::new(0) });
        link.push_control(hello);
        let w = link.clone();
        std::thread::Builder::new().name("presenter-tx".into()).spawn(move || w.write_loop())?;
        std::thread::Builder::new().name("presenter-rx".into()).spawn(move || read_loop(reader, on_event))?;
        Ok(link)
    }

    fn push(&self, item: Item) {
        let mut q = self.q.lock().unwrap();
        if q.closing {
            return;
        }
        q.items.push_back(item);
        self.cv.notify_one();
    }

    pub fn push_control(&self, msg: Msg) {
        if let Msg::AudioConfig { sample_rate, frame_len, .. } = &msg {
            *self.audio_frame_us.lock().unwrap() = u64::from(*frame_len) * 1_000_000 / u64::from((*sample_rate).max(1));
        }
        if matches!(msg, Msg::Flush) {
            let mut q = self.q.lock().unwrap();
            let before = q.items.len();
            q.items.retain(|i| !matches!(i.kind, Kind::Audio));
            q.dropped_audio += (before - q.items.len()) as u64;
            q.audio_items = 0;
        }
        self.push(Item { msg, kind: Kind::Control });
    }

    pub fn push_video(&self, msg: Msg, keyframe: bool) {
        let len = match &msg {
            Msg::VideoFrame { data, .. } => data.len(),
            _ => 0,
        };
        let now = Instant::now();
        let mut q = self.q.lock().unwrap();
        if q.closing {
            return;
        }
        if keyframe {
            q.drop_video();
            q.await_key = false;
        } else if q.await_key {
            q.dropped_video += 1;
            return;
        }
        let oldest = q.items.iter().find_map(|i| match i.kind {
            Kind::Video { at, .. } => Some(at),
            _ => None,
        });
        if q.video_bytes + len > VIDEO_BYTES || oldest.is_some_and(|t| now.duration_since(t) > VIDEO_SPAN) {
            q.drop_video();
            if !keyframe {
                q.await_key = true;
                q.dropped_video += 1;
                return;
            }
        }
        q.video_bytes += len;
        q.items.push_back(Item { msg, kind: Kind::Video { at: now, len } });
        self.cv.notify_one();
    }

    pub fn push_audio(&self, msg: Msg) {
        let frame_us = *self.audio_frame_us.lock().unwrap();
        let mut q = self.q.lock().unwrap();
        if q.closing {
            return;
        }
        q.items.push_back(Item { msg, kind: Kind::Audio });
        q.audio_items += 1;
        while frame_us > 0 && q.audio_items as u64 * frame_us > AUDIO_SPAN_US {
            let Some(pos) = q.items.iter().position(|i| matches!(i.kind, Kind::Audio)) else { break };
            q.items.remove(pos);
            q.audio_items -= 1;
            q.dropped_audio += 1;
        }
        self.cv.notify_one();
    }

    pub fn dropped(&self) -> (u64, u64) {
        let q = self.q.lock().unwrap();
        (q.dropped_video, q.dropped_audio)
    }

    fn write_loop(&self) {
        let mut out = &self.stream;
        loop {
            let item = {
                let mut q = self.q.lock().unwrap();
                loop {
                    if let Some(item) = q.items.pop_front() {
                        match item.kind {
                            Kind::Video { len, .. } => q.video_bytes -= len,
                            Kind::Audio => q.audio_items -= 1,
                            Kind::Control => {}
                        }
                        break Some(item);
                    }
                    if q.closing {
                        break None;
                    }
                    q = self.cv.wait(q).unwrap();
                }
            };
            let Some(item) = item else { break };
            if ipc::write_msg(&mut out, &item.msg).is_err() {
                break;
            }
        }
        let _ = self.stream.shutdown(std::net::Shutdown::Write);
        self.q.lock().unwrap().done = true;
        self.cv.notify_all();
    }

    /// Ends the link: what is queued goes out, then `End`, then the socket closes (after at most 1 s).
    pub fn finish(&self, reason: &str) {
        let mut q = self.q.lock().unwrap();
        if !q.closing {
            q.items.push_back(Item { msg: Msg::End { reason: reason.into() }, kind: Kind::Control });
            q.closing = true;
            self.cv.notify_all();
        }
        let (q, _) = self.cv.wait_timeout_while(q, END_GRACE, |q| !q.done).unwrap();
        drop(q);
        let _ = self.stream.shutdown(std::net::Shutdown::Both);
    }
}

fn read_loop(mut stream: UnixStream, on_event: impl Fn(Event)) {
    let reason = loop {
        match ipc::read_msg(&mut stream) {
            Ok(Some(Msg::Ready { width, height, hw_decode })) => on_event(Event::Ready { width, height, hw_decode }),
            Ok(Some(Msg::Stats(s))) => on_event(Event::Stats(s)),
            Ok(Some(Msg::Bye { reason })) => break format!("presenter bye: {reason}"),
            Ok(Some(_)) => {}
            Ok(None) => break "presenter closed".to_string(),
            Err(e) => break format!("presenter: {e}"),
        }
    };
    on_event(Event::Gone(reason));
}
