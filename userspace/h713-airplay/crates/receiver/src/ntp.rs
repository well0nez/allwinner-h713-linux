// SPDX-License-Identifier: GPL-3.0-only
//! NTP towards the sender (raop_ntp.c): while a session lives, a 32-byte request (`80 d2`) goes to the sender's
//! timing port every 3 s from the receiver's timing socket; the sender's answers (`80 d3`) come back there. A
//! sender that asks the receiver (doubletake's probes) gets an answer too.

use std::net::{SocketAddr, UdpSocket};
use std::sync::mpsc::{self, RecvTimeoutError, Sender};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

const INTERVAL: Duration = Duration::from_secs(3);
const SECONDS_1900_TO_1970: u64 = 2_208_988_800;

fn now_ntp() -> u64 {
    let d = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default();
    let frac = (u64::from(d.subsec_nanos()) << 32) / 1_000_000_000;
    ((d.as_secs() + SECONDS_1900_TO_1970) << 32) | frac
}

pub fn serve(sock: UdpSocket) {
    let mut buf = [0u8; 128];
    loop {
        let Ok((n, from)) = sock.recv_from(&mut buf) else { continue };
        if n < 32 || buf[1] & 0x7f != 0x52 {
            continue;
        }
        let received = now_ntp();
        let mut answer = [0u8; 32];
        answer[0] = 0x80;
        answer[1] = 0xd3;
        answer[2..4].copy_from_slice(&buf[2..4]);
        answer[8..16].copy_from_slice(&buf[24..32]);
        answer[16..24].copy_from_slice(&received.to_be_bytes());
        answer[24..32].copy_from_slice(&now_ntp().to_be_bytes());
        let _ = sock.send_to(&answer, from);
    }
}

/// Starts the requests to `peer`; dropping the returned sender stops them.
pub fn start(timing: &UdpSocket, peer: SocketAddr) -> Option<Sender<()>> {
    let sock = timing.try_clone().ok()?;
    let (stop, stopped) = mpsc::channel::<()>();
    std::thread::Builder::new()
        .name("ntp".into())
        .spawn(move || {
            let mut request = [0u8; 32];
            request[0] = 0x80;
            request[1] = 0xd2;
            request[3] = 0x07;
            loop {
                request[24..32].copy_from_slice(&now_ntp().to_be_bytes());
                let _ = sock.send_to(&request, peer);
                match stopped.recv_timeout(INTERVAL) {
                    Err(RecvTimeoutError::Timeout) => {}
                    _ => break,
                }
            }
        })
        .ok()?;
    Some(stop)
}
