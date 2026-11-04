// SPDX-License-Identifier: GPL-3.0-only
//! A session's presenter link: connected at the mirror stream's SETUP, Hello first, then the audio format if
//! audio is already set up; the presenter's Ready makes the session `streaming`, its end ends the session.

use crate::presenter::{Event, Link};
use crate::rtsp::Response;
use crate::shared::{AudioSetup, Shared};
use proto::ctl::State;
use proto::ipc::{AudioCodec, Msg};
use std::sync::Arc;

pub fn audio_config(a: &AudioSetup) -> Msg {
    let config = match a.codec {
        AudioCodec::Alac => {
            let mut c = a.spf.to_be_bytes().to_vec();
            c.extend_from_slice(&[0, 16, 40, 10, 14, 2]);
            c.extend_from_slice(&255u16.to_be_bytes());
            c.extend_from_slice(&[0; 8]);
            c.extend_from_slice(&a.sample_rate.to_be_bytes());
            c
        }
        AudioCodec::AacEld => vec![0xf8, 0xe8, 0x50, 0x00],
        AudioCodec::AacLc => vec![0x12, 0x10],
        AudioCodec::Pcm => Vec::new(),
    };
    Msg::AudioConfig { codec: a.codec, sample_rate: a.sample_rate, channels: 2, frame_len: a.spf, config }
}

fn on_presenter(sh: &Shared, sid: u64, ev: Event) {
    let yn = |b: bool| if b { "yes" } else { "no" };
    match ev {
        Event::Ready { width, height, hw_decode } => {
            let mut inner = sh.lock();
            let Some(s) = inner.session.as_mut().filter(|s| s.id == sid) else { return };
            s.presenter = format!("ready decoded 0 presented 0 dropped 0 fps 0.00 hw {} latency-ms 0", yn(hw_decode));
            eprintln!("h713-airplay: session {sid} presenter ready {width}x{height} hw {}", yn(hw_decode));
            sh.set_state(&mut inner, State::Streaming);
        }
        Event::Stats(st) => {
            let mut inner = sh.lock();
            if let Some(s) = inner.session.as_mut().filter(|s| s.id == sid && s.presenter.starts_with("ready")) {
                s.presenter = format!(
                    "ready decoded {} presented {} dropped {} fps {}.{:02} hw {} latency-ms {}",
                    st.decoded,
                    st.presented,
                    st.dropped,
                    st.fps_x100 / 100,
                    st.fps_x100 % 100,
                    yn(st.hw_decode),
                    st.latency_us_avg / 1000
                );
            }
        }
        Event::Gone(reason) => {
            sh.end(sid, &reason);
        }
    }
}

pub fn attach(shared: &Arc<Shared>, sid: u64, hello: Msg) -> Result<(), Response> {
    let sh = shared.clone();
    let link = Link::connect(hello, move |ev| on_presenter(&sh, sid, ev)).map_err(|e| {
        eprintln!("h713-airplay: session {sid} presenter {}: {e}", proto::paths::show_socket().display());
        let mut inner = shared.lock();
        if let Some(s) = inner.session.as_mut().filter(|s| s.id == sid) {
            s.presenter = "none".into();
            shared.set_state(&mut inner, State::Connected);
        }
        Response::new(500)
    })?;
    let mut inner = shared.lock();
    match inner.session.as_mut().filter(|s| s.id == sid) {
        Some(s) => {
            if let Some(a) = &s.audio {
                link.push_control(audio_config(a));
            }
            s.link = Some(link);
            Ok(())
        }
        None => {
            drop(inner);
            link.finish("session ended");
            Err(Response::new(454))
        }
    }
}
