// SPDX-License-Identifier: GPL-3.0-only
//! One sender's RTSP connection (raop.c L189-500): dispatch, the session claim, and the small handlers.
//! A connection that only asks `GET /info` or `OPTIONS` (a probe, a sender looking) claims nothing; the first
//! pairing, fp-setup or SETUP request claims the session (a second sender then takes over or gets 409).

use crate::pairing::{self, Pairing};
use crate::rtsp::{read_request, write_response, Request, Response};
use crate::shared::{Claim, Shared};
use fairplay::FairPlay;
use plist::Value;
use proto::ipc::Msg;
use std::io::BufReader;
use std::net::{IpAddr, TcpStream};
use std::sync::Arc;

pub enum After {
    Continue,
    /// TEARDOWN: end once the frames the sender already sent have reached the presenter.
    EndAfterMirror(&'static str),
}

const TEARDOWN_GRACE: std::time::Duration = std::time::Duration::from_secs(1);

pub struct Conn {
    pub sh: Arc<Shared>,
    pub id: u64,
    pub peer: IpAddr,
    pub stream: TcpStream,
    pub fairplay: FairPlay,
    pub pairing: Pairing,
    pub session: Option<u64>,
}

pub fn serve(sh: Arc<Shared>, stream: TcpStream) {
    let Ok(peer) = stream.peer_addr() else { return };
    crate::net::keepalive(&stream);
    let Ok(read_half) = stream.try_clone() else { return };
    let mut reader = BufReader::new(read_half);
    let id = sh.conn_id();
    let mut c = Conn { sh, id, peer: peer.ip(), stream, fairplay: FairPlay::new(), pairing: Pairing::default(), session: None };
    let end = loop {
        let req = match read_request(&mut reader) {
            Ok(Some(r)) => r,
            Ok(None) => break "sender closed the connection",
            Err(_) => break "sender connection lost",
        };
        let cseq = req.header("CSeq").map(str::to_string);
        let (resp, after) = match cseq {
            Some(_) if req.protocol == "RTSP/1.0" => c.dispatch(&req),
            _ if req.protocol == "RTSP/1.0" && (req.url.contains("txtAirPlay") || req.url.contains("txtRAOP")) => {
                (c.info(&req), After::Continue)
            }
            _ => (Response::new(400), After::Continue),
        };
        let resp = if req.method != "RECORD" { resp.header("Audio-Jack-Status", "connected; type=digital") } else { resp };
        if write_response(&mut &c.stream, &req.protocol, cseq.as_deref(), &resp).is_err() {
            break "sender connection lost";
        }
        match after {
            After::Continue => {}
            After::EndAfterMirror(reason) => {
                if let Some(sid) = c.session {
                    c.sh.end_after_mirror(sid, reason, TEARDOWN_GRACE);
                }
                break reason;
            }
        }
    };
    if let Some(sid) = c.session {
        c.sh.end(sid, end);
    }
}

impl Conn {
    fn dispatch(&mut self, req: &Request) -> (Response, After) {
        let cont = |r| (r, After::Continue);
        match (req.method.as_str(), req.path()) {
            ("GET", p) if p.starts_with("/info") => cont(self.info(req)),
            ("OPTIONS", _) => cont(Response::ok().header(
                "Public",
                "SETUP, RECORD, FLUSH, TEARDOWN, OPTIONS, GET_PARAMETER, SET_PARAMETER",
            )),
            ("POST", "/pair-setup") => cont(self.claimed(req, |c| c.pair(req, true))),
            ("POST", "/pair-verify") => cont(self.claimed(req, |c| c.pair(req, false))),
            ("POST", "/fp-setup") => cont(self.claimed(req, |c| c.fp_setup(req))),
            ("POST", "/feedback" | "/audioMode") => cont(Response::ok()),
            ("SETUP", _) => cont(self.claimed(req, |c| c.setup(req))),
            ("RECORD", _) => cont(self.claimed(req, |_| {
                Response::ok().header("Audio-Latency", "11025").header("Audio-Jack-Status", "connected; type=analog")
            })),
            ("GET_PARAMETER", _) => cont(self.get_parameter(req)),
            ("SET_PARAMETER", _) => cont(self.set_parameter(req)),
            ("FLUSH", _) => {
                self.to_presenter(Msg::Flush);
                cont(Response::ok())
            }
            ("TEARDOWN", _) => self.teardown(req),
            ("POST" | "GET", _) => cont(Response::new(404)),
            _ => cont(Response::new(501)),
        }
    }

    fn claimed(&mut self, req: &Request, f: impl FnOnce(&mut Self) -> Response) -> Response {
        if let Some(sid) = self.session {
            if self.sh.current() != Some(sid) {
                return Response::new(454);
            }
            return f(self);
        }
        let name = req.header("X-Apple-Client-Name").unwrap_or("");
        match self.sh.claim(self.id, &self.stream, self.peer, name) {
            Claim::Owner(sid) => {
                self.session = Some(sid);
                f(self)
            }
            Claim::Conflict => Response::new(409),
        }
    }

    pub fn info(&self, req: &Request) -> Response {
        let bplist = req.header("Content-Type").is_some_and(|t| t.contains("application/x-apple-binary-plist"));
        if bplist {
            let qualifier: Vec<String> = Value::from_reader(std::io::Cursor::new(&req.body))
                .ok()
                .and_then(|v| v.into_dictionary())
                .and_then(|mut d| d.remove("qualifier"))
                .and_then(|q| q.into_array())
                .map(|a| a.into_iter().filter_map(|v| v.into_string()).collect())
                .unwrap_or_default();
            return Response::ok().plist(&crate::info::txt_info(&self.sh, &qualifier));
        }
        if req.header("CSeq").is_none() {
            let q: Vec<String> = ["txtAirPlay", "txtRAOP"].iter().filter(|q| req.url.contains(*q)).map(|q| q.to_string()).collect();
            return Response::ok().plist(&crate::info::txt_info(&self.sh, &q));
        }
        Response::ok().plist(&crate::info::full_info(&self.sh, self.volume()))
    }

    fn pair(&mut self, req: &Request, setup: bool) -> Response {
        let key = &self.sh.identity.key;
        let answer = if setup { self.pairing.setup(key, &req.body) } else { self.pairing.verify(key, &req.body) };
        match answer {
            Ok(body) => {
                if !setup && self.pairing.verified {
                    eprintln!("h713-airplay: {} pair-verify ok (legacy pairing)", self.peer);
                }
                Response::ok().body("application/octet-stream", body)
            }
            Err(pairing::Error::BadRequest(why)) => {
                eprintln!("h713-airplay: {} {}: {why}", self.peer, req.path());
                Response::new(400)
            }
            Err(pairing::Error::BadSignature) => {
                eprintln!("h713-airplay: {} pair-verify: wrong signature", self.peer);
                Response::new(470)
            }
        }
    }

    fn fp_setup(&mut self, req: &Request) -> Response {
        match self.fairplay.setup(&req.body) {
            Ok(body) => Response::ok().body("application/octet-stream", body),
            Err(e) => {
                eprintln!("h713-airplay: {} fp-setup ({} bytes): {e}", self.peer, req.body.len());
                Response::new(400)
            }
        }
    }

    fn volume(&self) -> f32 {
        *self.sh.volume.lock().unwrap()
    }

    fn get_parameter(&self, req: &Request) -> Response {
        match req.header("Content-Type") {
            None => Response::new(451),
            Some("text/parameters") if req.body.starts_with(b"volume") => {
                Response::ok().body("text/parameters", format!("volume: {:.6}\r\n", self.volume()).into_bytes())
            }
            Some(_) => Response::ok(),
        }
    }

    fn set_parameter(&self, req: &Request) -> Response {
        let Some(ct) = req.header("Content-Type") else { return Response::new(451) };
        if ct == "text/parameters" {
            let text = String::from_utf8_lossy(&req.body);
            if let Some(db) = text.trim().strip_prefix("volume:").and_then(|v| v.trim().parse::<f32>().ok()) {
                *self.sh.volume.lock().unwrap() = db;
                self.to_presenter(Msg::Volume { db });
            }
        }
        Response::ok()
    }

    pub fn to_presenter(&self, msg: Msg) {
        let Some(sid) = self.session else { return };
        let inner = self.sh.lock();
        if let Some(link) = inner.session.as_ref().filter(|s| s.id == sid).and_then(|s| s.link.clone()) {
            drop(inner);
            link.push_control(msg);
        }
    }
}
