// SPDX-License-Identifier: GPL-3.0-only
//! The counters every thread adds to, and the one-second windows `Stats` reports.

use proto::ipc::Stats;
use std::sync::atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering::Relaxed};
use std::sync::Mutex;

#[derive(Default)]
pub struct Mean {
    sum: u64,
    n: u64,
}

impl Mean {
    pub fn add(&mut self, v: u64) {
        self.sum += v;
        self.n += 1;
    }

    /// The mean since the last take, 0 when nothing came; starts the next window.
    pub fn take(&mut self) -> u32 {
        let m = if self.n == 0 { 0 } else { self.sum / self.n };
        *self = Mean::default();
        m.min(u64::from(u32::MAX)) as u32
    }
}

/// Events per second times 100 over a window of `elapsed_us`.
pub fn rate_x100(events: u64, elapsed_us: u64) -> u32 {
    if elapsed_us == 0 {
        return 0;
    }
    (events.saturating_mul(100_000_000) / elapsed_us).min(u64::from(u32::MAX)) as u32
}

#[derive(Default)]
pub struct Counters {
    pub decoded: AtomicU64,
    pub presented: AtomicU64,
    pub dropped: AtomicU64,
    pub decode_errors: AtomicU64,
    pub hw_decode: AtomicBool,
    pub audio_frames: AtomicU64,
    pub audio_dropped: AtomicU64,
    pub audio_underruns: AtomicU64,
    pub audio_delay_ms: AtomicU32,
    pub decode_us: Mutex<Mean>,
    pub latency_us: Mutex<Mean>,
}

pub fn add(c: &AtomicU64) {
    c.fetch_add(1, Relaxed);
}

/// The window of the last report: the presented count and when it was taken.
#[derive(Default)]
pub struct Window {
    presented: u64,
    at_us: u64,
}

impl Counters {
    pub fn report(&self, window: &mut Window, now_us: u64) -> Stats {
        let presented = self.presented.load(Relaxed);
        let fps_x100 = if window.at_us == 0 { 0 } else { rate_x100(presented - window.presented, now_us - window.at_us) };
        *window = Window { presented, at_us: now_us };
        Stats {
            decoded: self.decoded.load(Relaxed),
            presented,
            dropped: self.dropped.load(Relaxed),
            decode_errors: self.decode_errors.load(Relaxed),
            fps_x100,
            decode_us_avg: self.decode_us.lock().unwrap_or_else(|e| e.into_inner()).take(),
            latency_us_avg: self.latency_us.lock().unwrap_or_else(|e| e.into_inner()).take(),
            hw_decode: self.hw_decode.load(Relaxed),
            audio_frames: self.audio_frames.load(Relaxed),
            audio_dropped: self.audio_dropped.load(Relaxed),
            audio_underruns: self.audio_underruns.load(Relaxed),
            audio_delay_ms: self.audio_delay_ms.load(Relaxed),
        }
    }

    pub fn mean(m: &Mutex<Mean>, v: u64) {
        m.lock().unwrap_or_else(|e| e.into_inner()).add(v);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_mean_covers_one_window_only() {
        let mut m = Mean::default();
        assert_eq!(m.take(), 0);
        [10, 20, 33].into_iter().for_each(|v| m.add(v));
        assert_eq!(m.take(), 21);
        m.add(5);
        assert_eq!(m.take(), 5);
    }

    #[test]
    fn the_rate_is_per_second_times_100() {
        assert_eq!(rate_x100(60, 1_000_000), 6000);
        assert_eq!(rate_x100(59, 1_000_500), 5897);
        assert_eq!(rate_x100(5, 0), 0);
    }

    #[test]
    fn a_report_gives_the_rate_since_the_one_before() {
        let c = Counters::default();
        let mut w = Window::default();
        c.presented.store(100, Relaxed);
        assert_eq!(c.report(&mut w, 1_000_000).fps_x100, 0, "no window before the first report");
        c.presented.store(160, Relaxed);
        Counters::mean(&c.latency_us, 30_000);
        let s = c.report(&mut w, 2_000_000);
        assert_eq!((s.presented, s.fps_x100, s.latency_us_avg), (160, 6000, 30_000));
        assert_eq!(c.report(&mut w, 3_000_000).latency_us_avg, 0);
    }
}
