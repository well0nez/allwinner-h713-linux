// SPDX-License-Identifier: GPL-3.0-only
//! A small RTSP/1.0 client: one request at a time on one TCP connection, CSeq counted.

use std::io::{self, BufRead, BufReader, Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::time::Duration;

pub struct Reply {
    pub status: u16,
    pub status_line: String,
    pub headers: Vec<(String, String)>,
    pub body: Vec<u8>,
}

impl Reply {
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers.iter().find(|(k, _)| k.eq_ignore_ascii_case(name)).map(|(_, v)| v.as_str())
    }
    pub fn plist(&self) -> io::Result<plist::Dictionary> {
        plist::Value::from_reader(io::Cursor::new(&self.body))
            .ok()
            .and_then(plist::Value::into_dictionary)
            .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "answer is not a plist dictionary"))
    }
}

pub struct Client {
    stream: TcpStream,
    reader: BufReader<TcpStream>,
    cseq: u32,
}

pub fn plist_body(v: &plist::Value) -> Vec<u8> {
    let mut out = Vec::new();
    v.to_writer_binary(&mut out).expect("a plist in memory");
    out
}

impl Client {
    pub fn connect(addr: SocketAddr) -> io::Result<Client> {
        let stream = TcpStream::connect_timeout(&addr, Duration::from_secs(5))?;
        stream.set_read_timeout(Some(Duration::from_secs(10)))?;
        stream.set_nodelay(true)?;
        let reader = BufReader::new(stream.try_clone()?);
        Ok(Client { stream, reader, cseq: 0 })
    }

    pub fn local_ip(&self) -> io::Result<std::net::IpAddr> {
        Ok(self.stream.local_addr()?.ip())
    }

    pub fn request(&mut self, method: &str, url: &str, content_type: Option<&str>, body: &[u8]) -> io::Result<Reply> {
        self.cseq += 1;
        let mut head = format!("{method} {url} RTSP/1.0\r\nCSeq: {}\r\nUser-Agent: AirPlay/381.13\r\n", self.cseq);
        if let Some(ct) = content_type {
            head.push_str(&format!("Content-Type: {ct}\r\n"));
        }
        head.push_str(&format!("Content-Length: {}\r\n\r\n", body.len()));
        let mut out = head.into_bytes();
        out.extend_from_slice(body);
        self.stream.write_all(&out)?;
        self.read_reply()
    }

    fn read_reply(&mut self) -> io::Result<Reply> {
        let mut line = String::new();
        if self.reader.read_line(&mut line)? == 0 {
            return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "the receiver closed the connection"));
        }
        let status_line = line.trim_end().to_string();
        let status = status_line
            .split(' ')
            .nth(1)
            .and_then(|s| s.parse().ok())
            .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, format!("status line {status_line:?}")))?;
        let mut headers = Vec::new();
        loop {
            line.clear();
            self.reader.read_line(&mut line)?;
            let l = line.trim_end();
            if l.is_empty() {
                break;
            }
            if let Some((k, v)) = l.split_once(':') {
                headers.push((k.trim().to_string(), v.trim().to_string()));
            }
        }
        let mut reply = Reply { status, status_line, headers, body: Vec::new() };
        let len: usize = reply.header("Content-Length").and_then(|v| v.parse().ok()).unwrap_or(0);
        reply.body = vec![0; len];
        self.reader.read_exact(&mut reply.body)?;
        Ok(reply)
    }

}

/// Anything but 200 is an error naming the step.
pub fn ok(step: &str, r: Reply) -> io::Result<Reply> {
    if r.status != 200 {
        return Err(io::Error::other(format!("{step}: {}", r.status_line)));
    }
    Ok(r)
}

/// `HOST`, `HOST:PORT` or an IPv4 address; the port defaults to 7000.
pub fn resolve(target: &str) -> io::Result<SocketAddr> {
    use std::net::ToSocketAddrs;
    let with_port = if target.contains(':') { target.to_string() } else { format!("{target}:7000") };
    with_port
        .to_socket_addrs()?
        .find(SocketAddr::is_ipv4)
        .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, format!("{target}: no IPv4 address")))
}
