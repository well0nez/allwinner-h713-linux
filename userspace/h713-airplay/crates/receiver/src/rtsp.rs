// SPDX-License-Identifier: GPL-3.0-only
//! RTSP/1.0 framing on the sender's control connection: a request line, headers, a `Content-Length` body.

use std::io::{self, BufRead, Read, Write};

const MAX_HEADER_LINES: usize = 40;
const MAX_LINE: usize = 4096;
const MAX_BODY: usize = 1 << 20;

pub struct Request {
    pub method: String,
    pub url: String,
    pub protocol: String,
    pub headers: Vec<(String, String)>,
    pub body: Vec<u8>,
}

impl Request {
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers.iter().find(|(k, _)| k.eq_ignore_ascii_case(name)).map(|(_, v)| v.as_str())
    }
    pub fn path(&self) -> &str {
        let u = self.url.strip_prefix("rtsp://").map(|r| r.find('/').map_or("/", |i| &r[i..])).unwrap_or(&self.url);
        u.split('?').next().unwrap_or(u)
    }
}

fn bad(what: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, format!("rtsp: {what}"))
}

fn line(r: &mut impl BufRead) -> io::Result<Option<String>> {
    let mut buf = Vec::new();
    let n = r.take(MAX_LINE as u64 + 1).read_until(b'\n', &mut buf)?;
    if n == 0 {
        return Ok(None);
    }
    if buf.last() != Some(&b'\n') {
        return Err(bad("line too long or cut"));
    }
    while matches!(buf.last(), Some(b'\n' | b'\r')) {
        buf.pop();
    }
    String::from_utf8(buf).map(Some).map_err(|_| bad("header is not UTF-8"))
}

/// The next request; `Ok(None)` when the sender closed between requests.
pub fn read_request(r: &mut impl BufRead) -> io::Result<Option<Request>> {
    let first = loop {
        match line(r)? {
            None => return Ok(None),
            Some(l) if l.is_empty() => continue,
            Some(l) => break l,
        }
    };
    let mut parts = first.split(' ');
    let (Some(method), Some(url), Some(protocol)) = (parts.next(), parts.next(), parts.next()) else {
        return Err(bad("not a request line"));
    };
    let mut headers = Vec::new();
    loop {
        let l = line(r)?.ok_or_else(|| bad("EOF inside the headers"))?;
        if l.is_empty() {
            break;
        }
        if headers.len() == MAX_HEADER_LINES {
            return Err(bad("too many headers"));
        }
        let (k, v) = l.split_once(':').ok_or_else(|| bad("header without a colon"))?;
        headers.push((k.trim().to_string(), v.trim().to_string()));
    }
    let mut req = Request { method: method.into(), url: url.into(), protocol: protocol.into(), headers, body: Vec::new() };
    let len: usize = match req.header("Content-Length") {
        Some(v) => v.parse().map_err(|_| bad("Content-Length"))?,
        None => 0,
    };
    if len > MAX_BODY {
        return Err(bad("body too large"));
    }
    req.body = vec![0; len];
    r.read_exact(&mut req.body)?;
    Ok(Some(req))
}

pub struct Response {
    pub status: u16,
    pub headers: Vec<(&'static str, String)>,
    pub body: Vec<u8>,
}

impl Response {
    pub fn new(status: u16) -> Response {
        Response { status, headers: Vec::new(), body: Vec::new() }
    }
    pub fn ok() -> Response {
        Response::new(200)
    }
    pub fn header(mut self, k: &'static str, v: impl Into<String>) -> Response {
        self.headers.push((k, v.into()));
        self
    }
    pub fn body(mut self, content_type: &'static str, body: Vec<u8>) -> Response {
        self.headers.push(("Content-Type", content_type.into()));
        self.body = body;
        self
    }
    pub fn plist(self, v: &plist::Value) -> Response {
        let mut out = Vec::new();
        v.to_writer_binary(&mut out).expect("a plist in memory");
        self.body("application/x-apple-binary-plist", out)
    }
}

fn reason(status: u16) -> &'static str {
    match status {
        200 => "OK",
        400 => "Bad Request",
        404 => "Not Found",
        409 => "Conflict",
        451 => "Parameter Not Understood",
        454 => "Session Not Found",
        470 => "Connection Authorization Required",
        500 => "Internal Server Error",
        501 => "Not Implemented",
        _ => "Error",
    }
}

pub fn write_response(w: &mut impl Write, protocol: &str, cseq: Option<&str>, resp: &Response) -> io::Result<()> {
    let mut head = format!("{protocol} {} {}\r\n", resp.status, reason(resp.status));
    for (k, v) in &resp.headers {
        head.push_str(&format!("{k}: {v}\r\n"));
    }
    if let Some(c) = cseq {
        head.push_str(&format!("CSeq: {c}\r\n"));
    }
    head.push_str(&format!("Server: AirTunes/{}\r\nContent-Length: {}\r\n\r\n", crate::info::SOURCE_VERSION, resp.body.len()));
    let mut out = head.into_bytes();
    out.extend_from_slice(&resp.body);
    w.write_all(&out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn requests_parse_with_bodies_and_a_clean_eof_is_none() {
        let wire = b"GET /info RTSP/1.0\r\nCSeq: 3\r\n\r\nSETUP rtsp://1.2.3.4/123 RTSP/1.0\r\ncontent-length: 2\r\nCSeq: 4\r\n\r\nab";
        let mut r = io::BufReader::new(&wire[..]);
        let a = read_request(&mut r).unwrap().unwrap();
        assert_eq!((a.method.as_str(), a.path(), a.header("cseq")), ("GET", "/info", Some("3")));
        let b = read_request(&mut r).unwrap().unwrap();
        assert_eq!((b.path(), b.body.as_slice()), ("/123", &b"ab"[..]));
        assert!(read_request(&mut r).unwrap().is_none());
        assert!(read_request(&mut io::BufReader::new(&b"GET /info RTSP/1.0\r\nCSeq"[..])).is_err());
    }
}
