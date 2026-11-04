// SPDX-License-Identifier: GPL-3.0-only
//! `h713-airplay sendtest` and `h713-airplay probe` (README.md, "Work packages", B).

mod annexb;
mod audio;
mod keys;
mod negotiate;
mod probe;
mod rtsp;
mod session;
mod sps;

pub use annexb::{access_units, avcc_record, parameter_sets, Codec};
pub use audio::{alac_frames, tone};
pub use probe::probe as probe_text;
pub use session::{run, Audio, Report, SendTest};

use std::path::PathBuf;

const SENDTEST_USAGE: &str =
    "usage: h713-airplay sendtest --target HOST[:PORT] --video FILE.h264|FILE.h265 [--fps 60] [--audio FILE.wav|tone|none] [--seconds N] [--bare-teardown]";

fn parse_sendtest(args: &[String]) -> Result<SendTest, String> {
    let mut target = None;
    let mut video = None;
    let mut fps = 60;
    let mut audio = Audio::None;
    let mut seconds = None;
    let mut bare_teardown = false;
    let mut it = args.iter();
    while let Some(a) = it.next() {
        let mut value = || it.next().cloned().ok_or_else(|| format!("{a} needs a value"));
        match a.as_str() {
            "--target" => target = Some(rtsp::resolve(&value()?).map_err(|e| e.to_string())?),
            "--video" => video = Some(PathBuf::from(value()?)),
            "--fps" => fps = value()?.parse().ok().filter(|f| (1..=240).contains(f)).ok_or("--fps 1..240")?,
            "--audio" => {
                audio = match value()?.as_str() {
                    "none" => Audio::None,
                    "tone" => Audio::Tone,
                    path => Audio::Wav(path.into()),
                }
            }
            "--seconds" => seconds = Some(value()?.parse::<f64>().ok().filter(|s| *s > 0.0).ok_or("--seconds > 0")?),
            "--bare-teardown" => bare_teardown = true,
            other => return Err(format!("unknown argument {other}")),
        }
    }
    Ok(SendTest {
        target: target.ok_or("--target is missing")?,
        video: video.ok_or("--video is missing")?,
        fps,
        audio,
        seconds,
        bare_teardown,
    })
}

pub fn sendtest(args: &[String]) -> i32 {
    let t = match parse_sendtest(args) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("h713-airplay sendtest: {e}\n{SENDTEST_USAGE}");
            return 2;
        }
    };
    match run(&t) {
        Ok(r) => {
            let secs = r.elapsed.as_secs_f64().max(1e-9);
            println!(
                "sendtest: {:?} {}x{}, {} frames ({} bytes) in {secs:.2} s = {:.2} fps, audio {} packets",
                r.codec,
                r.width,
                r.height,
                r.frames,
                r.bytes,
                r.frames as f64 / secs,
                r.audio_packets
            );
            0
        }
        Err(e) => {
            eprintln!("h713-airplay sendtest: {e}");
            1
        }
    }
}

pub fn probe(args: &[String]) -> i32 {
    let target = args.first().map_or("127.0.0.1:7000", String::as_str);
    match probe::probe(target) {
        Ok(text) => {
            print!("{text}");
            0
        }
        Err(e) => {
            eprintln!("h713-airplay probe: {target}: {e}");
            1
        }
    }
}
