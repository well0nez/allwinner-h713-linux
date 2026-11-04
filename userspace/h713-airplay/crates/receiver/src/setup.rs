// SPDX-License-Identifier: GPL-3.0-only
//! SETUP and TEARDOWN (raop_handlers.h L596-1000, L1270-1320): the session keys, the mirror stream (type 110)
//! with the presenter link, screen audio (type 96), and the end of the stream.

use crate::conn::{After, Conn};
use crate::crypto;
use crate::rtsp::{Request, Response};
use crate::link::audio_config;
use crate::shared::{AudioSetup, Keys, MirrorSetup};
use plist::{Dictionary, Value};
use proto::ctl::State;
use proto::ipc::{AudioCodec, Msg};
use std::net::{Shutdown, SocketAddr};

fn parse(body: &[u8]) -> Option<Dictionary> {
    if body.is_empty() {
        return Some(Dictionary::new());
    }
    Value::from_reader(std::io::Cursor::new(body)).ok()?.into_dictionary()
}

/// Senders write 64-bit ids as signed or unsigned plist integers; the key derivation wants the unsigned value.
pub fn uint(v: Option<&Value>) -> Option<u64> {
    match v? {
        Value::Integer(i) => i.as_unsigned().or_else(|| i.as_signed().map(|s| s as u64)),
        Value::Real(r) => Some(*r as u64),
        _ => None,
    }
}

fn text(d: &Dictionary, k: &str) -> String {
    d.get(k).and_then(Value::as_string).unwrap_or("").to_string()
}

fn stream(entries: &[(&str, u64)]) -> Value {
    Value::Dictionary(entries.iter().map(|(k, v)| (k.to_string(), Value::Integer((*v).into()))).collect())
}

impl Conn {
    fn sid(&self) -> u64 {
        self.session.expect("SETUP runs claimed")
    }

    pub fn setup(&mut self, req: &Request) -> Response {
        let Some(body) = parse(&req.body) else { return Response::new(400) };
        let mut answer = Dictionary::new();
        if let (Some(Value::Data(ekey)), Some(Value::Data(eiv))) = (body.get("ekey"), body.get("eiv")) {
            if let Err(r) = self.setup_session(req, &body, ekey, eiv) {
                return r;
            }
            answer.insert("timingPort".into(), Value::Integer(self.sh.ports.timing.into()));
            answer.insert("eventPort".into(), Value::Integer(0u64.into()));
        }
        if let Some(Value::Array(streams)) = body.get("streams") {
            let mut out = Vec::new();
            for s in streams {
                let Some(d) = s.as_dictionary() else { return Response::new(400) };
                let r = match uint(d.get("type")) {
                    Some(110) => self.setup_mirror(d),
                    Some(96) => self.setup_audio(d),
                    t => {
                        eprintln!("h713-airplay: session {} SETUP of stream type {t:?} refused", self.sid());
                        Err(Response::new(400))
                    }
                };
                match r {
                    Ok(v) => out.push(v),
                    Err(resp) => return resp,
                }
            }
            answer.insert("streams".into(), Value::Array(out));
        }
        Response::ok().plist(&Value::Dictionary(answer))
    }

    fn setup_session(&mut self, req: &Request, body: &Dictionary, ekey: &[u8], eiv: &[u8]) -> Result<(), Response> {
        let sid = self.sid();
        let Ok(iv) = <[u8; 16]>::try_from(eiv) else { return Err(Response::new(400)) };
        let fp = self.fairplay.decrypt_key(ekey).map_err(|e| {
            eprintln!("h713-airplay: session {sid} SETUP: {e}");
            Response::new(400)
        })?;
        let user_agent = req.header("User-Agent").unwrap_or("");
        let ecdh = if user_agent.contains("AirMyPC") { None } else { self.pairing.ecdh_secret() };
        let keys = Keys { key: crypto::session_key(fp, ecdh), iv };
        let timing_port = uint(body.get("timingPort")).unwrap_or(0) as u16;
        let mut inner = self.sh.lock();
        let s = inner.session.as_mut().filter(|s| s.id == sid).ok_or(Response::new(454))?;
        s.keys = Some(keys);
        let (name, model) = (text(body, "name"), text(body, "model"));
        if !name.is_empty() {
            s.client.name = name;
        }
        if !model.is_empty() {
            s.client.model = model;
        }
        if timing_port > 0 && s.ntp_stop.is_none() {
            let peer = SocketAddr::new(self.peer, timing_port);
            s.timing_peer = Some(peer);
            s.ntp_stop = crate::ntp::start(&self.sh.timing, peer);
        }
        let how = if ecdh.is_some() { "mixed with the pair-verify secret" } else { "unhashed" };
        eprintln!("h713-airplay: session {sid} keys from FairPlay ({how}), {} {}", s.client.model, s.client.name);
        Ok(())
    }

    fn setup_mirror(&mut self, d: &Dictionary) -> Result<Value, Response> {
        let sid = self.sid();
        let stream_id = uint(d.get("streamConnectionID")).ok_or(Response::new(400))?;
        let hello = {
            let mut inner = self.sh.lock();
            let s = inner.session.as_mut().filter(|s| s.id == sid).ok_or(Response::new(454))?;
            if s.keys.is_none() {
                eprintln!("h713-airplay: session {sid} mirror SETUP before the keys");
                return Err(Response::new(400));
            }
            if let Some(old) = s.mirror.replace(MirrorSetup { stream_id, conn: None, serial: 0 }).and_then(|m| m.conn) {
                let _ = old.shutdown(Shutdown::Both);
            }
            eprintln!("h713-airplay: session {sid} mirror stream {stream_id}");
            if s.link.is_some() {
                None
            } else {
                s.presenter = "starting".into();
                let hello = Msg::Hello {
                    version: proto::ipc::VERSION,
                    session: sid,
                    client_name: s.client.name.clone(),
                    client_model: s.client.model.clone(),
                    peer: s.peer.to_string(),
                };
                self.sh.set_state(&mut inner, State::Starting);
                Some(hello)
            }
        };
        if let Some(hello) = hello {
            crate::link::attach(&self.sh, sid, hello)?;
        }
        Ok(stream(&[("type", 110), ("dataPort", self.sh.ports.mirror.into())]))
    }

    fn setup_audio(&mut self, d: &Dictionary) -> Result<Value, Response> {
        let sid = self.sid();
        let ct = uint(d.get("ct")).unwrap_or(0);
        let format = uint(d.get("audioFormat")).unwrap_or(0);
        let codec = match (ct, format) {
            (2, _) | (_, 0x40000) => AudioCodec::Alac,
            (8, _) | (_, 0x100_0000) => AudioCodec::AacEld,
            (4, _) | (_, 0x40_0000) => AudioCodec::AacLc,
            (1, _) => AudioCodec::Pcm,
            _ => {
                eprintln!("h713-airplay: session {sid} audio SETUP ct {ct} audioFormat {format:#x} refused");
                return Err(Response::new(400));
            }
        };
        let default_spf = if codec == AudioCodec::AacEld { 480 } else { 352 };
        let spf = uint(d.get("spf")).filter(|v| *v > 0).unwrap_or(default_spf) as u32;
        let sample_rate = uint(d.get("sr")).filter(|v| *v > 0).unwrap_or(44100) as u32;
        let mut inner = self.sh.lock();
        let s = inner.session.as_mut().filter(|s| s.id == sid).ok_or(Response::new(454))?;
        let Some(keys) = s.keys else {
            eprintln!("h713-airplay: session {sid} audio SETUP before the keys");
            return Err(Response::new(400));
        };
        let a = AudioSetup { codec, sample_rate, spf, keys };
        if let Some(link) = &s.link {
            link.push_control(audio_config(&a));
        }
        eprintln!("h713-airplay: session {sid} audio {codec:?} {sample_rate} Hz, {spf} samples per frame");
        s.audio = Some(a);
        let p = self.sh.ports;
        Ok(stream(&[("type", 96), ("dataPort", p.audio_data.into()), ("controlPort", p.audio_control.into())]))
    }

    pub fn teardown(&mut self, req: &Request) -> (Response, After) {
        let types: Vec<u64> = parse(&req.body)
            .and_then(|mut d| d.remove("streams"))
            .and_then(Value::into_array)
            .map(|a| a.iter().filter_map(|s| uint(s.as_dictionary()?.get("type"))).collect())
            .unwrap_or_default();
        if !types.is_empty() && types.iter().all(|t| *t == 96) {
            if let Some(sid) = self.session {
                let mut inner = self.sh.lock();
                if let Some(s) = inner.session.as_mut().filter(|s| s.id == sid) {
                    s.audio = None;
                    eprintln!("h713-airplay: session {sid} audio stopped");
                }
            }
            self.to_presenter(Msg::Flush);
            return (Response::ok(), After::Continue);
        }
        if let Some(sid) = self.session {
            if let Some(s) = self.sh.lock().session.as_mut().filter(|s| s.id == sid) {
                s.ending = Some("teardown");
            }
        }
        (Response::ok().header("Connection", "close"), After::EndAfterMirror("teardown"))
    }
}
