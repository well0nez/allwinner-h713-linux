// SPDX-License-Identifier: GPL-3.0-only
//! FairPlay SAP v2.5 (`POST /fp-setup`) on the receiver's side. Work package A (README.md, "Work packages").
//!
//! The cipher is fcast's `apple-fairplay` (https://github.com/futo-org/fcast, crates/apple-fairplay,
//! commit ea3982b31d751957e3cb6a114ee65504c7b91105, GPL-3.0-only), a Rust port of playfair; see NOTICE.
//! The handshake follows UxPlay's lib/fairplay_playfair.c (v1.73.7): phase 1 answers one of four fixed
//! 142-byte replies chosen by the request's mode byte, phase 2 keeps the 164-byte message and echoes its
//! last 20 bytes, and the 72-byte `ekey` is unwrapped with that message.

use std::fmt;

mod garble;
mod md5;
mod playfair;

#[cfg(feature = "test-sender")]
pub mod fixtures;

use playfair::tables::{FP_HEADER, REPLY_MESSAGE};

/// Phase 1 request: `FPLY` 03 01 01 ..., 16 bytes; byte 14 is the mode.
pub const MESSAGE1_LEN: usize = 16;
/// Phase 1 reply.
pub const REPLY1_LEN: usize = 142;
/// Phase 2 request (message 3): `FPLY` 03 01 03 ..., 164 bytes; byte 12 is the mode.
pub const MESSAGE3_LEN: usize = 164;
/// Phase 2 reply.
pub const REPLY2_LEN: usize = 32;
/// SETUP's wrapped key.
pub const EKEY_LEN: usize = 72;

/// Number of modes playfair has tables for.
const MODES: u8 = 4;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Error(pub String);

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "fairplay: {}", self.0)
    }
}

impl std::error::Error for Error {}

#[derive(Default)]
enum State {
    #[default]
    Fresh,
    Phase1,
    Done(Box<[u8; MESSAGE3_LEN]>),
}

/// One sender's handshake: phase 1 (16 bytes in, 142 out), phase 2 (164 bytes in, 32 out), then the key.
#[derive(Default)]
pub struct FairPlay {
    state: State,
}

impl FairPlay {
    pub fn new() -> Self {
        Self::default()
    }

    /// The answer to one `/fp-setup` body. A phase 1 request starts over (as UxPlay does); a phase 2
    /// request is accepted only right after phase 1.
    pub fn setup(&mut self, request: &[u8]) -> Result<Vec<u8>, Error> {
        if request.len() > 4 && request[4] != 0x03 {
            return Err(Error(format!("unsupported FairPlay version {}", request[4])));
        }
        match request.len() {
            MESSAGE1_LEN => {
                let mode = request[14];
                if mode >= MODES {
                    return Err(Error(format!("unsupported mode {mode} in phase 1")));
                }
                let start = usize::from(mode) * REPLY1_LEN;
                self.state = State::Phase1;
                Ok(REPLY_MESSAGE[start..start + REPLY1_LEN].to_vec())
            }
            MESSAGE3_LEN => {
                if !matches!(self.state, State::Phase1) {
                    return Err(Error("phase 2 request without a phase 1 before it".into()));
                }
                // playfair indexes its per-mode tables with byte 12; past 3 it would read beyond them.
                let mode = request[12];
                if mode >= MODES {
                    return Err(Error(format!("unsupported mode {mode} in phase 2")));
                }
                let mut message3 = Box::new([0u8; MESSAGE3_LEN]);
                message3.copy_from_slice(request);
                let mut reply = Vec::with_capacity(REPLY2_LEN);
                reply.extend_from_slice(FP_HEADER);
                reply.extend_from_slice(&request[144..MESSAGE3_LEN]);
                self.state = State::Done(message3);
                Ok(reply)
            }
            n => Err(Error(format!("fp-setup body of {n} bytes (want {MESSAGE1_LEN} or {MESSAGE3_LEN})"))),
        }
    }

    /// The AES key that SETUP's 72-byte `ekey` wraps; needs phase 2 first.
    pub fn decrypt_key(&self, ekey: &[u8]) -> Result<[u8; 16], Error> {
        let State::Done(message3) = &self.state else {
            return Err(Error("ekey before the fp-setup handshake finished".into()));
        };
        if ekey.len() != EKEY_LEN {
            return Err(Error(format!("ekey of {} bytes (want {EKEY_LEN})", ekey.len())));
        }
        let mut key = [0u8; 16];
        playfair::playfair_decrypt(&message3[..], ekey, &mut key);
        Ok(key)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn message1(mode: u8) -> [u8; 16] {
        [0x46, 0x50, 0x4c, 0x59, 0x03, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x04, 0x02, 0x00, mode, 0xbb]
    }

    fn message3(mode: u8) -> Vec<u8> {
        let mut m = vec![0x46, 0x50, 0x4c, 0x59, 0x03, 0x01, 0x03, 0x00, 0x00, 0x00, 0x00, 0x98, mode];
        m.extend((13..MESSAGE3_LEN).map(|i| (i * 3) as u8));
        m
    }

    // From fcast's fp_setup_reply_selects_mode.
    #[test]
    fn phase1_reply_selects_mode() {
        let mut fp = FairPlay::new();
        let res = fp.setup(&message1(2)).unwrap();
        assert_eq!(&res[..], &REPLY_MESSAGE[2 * 142..3 * 142]);
        assert_eq!(&res[12..14], &[0x02, 0x02]);
    }

    // From fcast's fp_handshake_echoes_tail.
    #[test]
    fn phase2_echoes_tail() {
        let mut fp = FairPlay::new();
        fp.setup(&message1(1)).unwrap();
        let req = message3(1);
        let res = fp.setup(&req).unwrap();
        assert_eq!(&res[..12], FP_HEADER);
        assert_eq!(&res[12..32], &req[144..164]);
        assert!(fp.decrypt_key(&[0u8; 72]).is_ok());
    }

    #[test]
    fn rejects_wrong_sizes_and_order() {
        let mut fp = FairPlay::new();
        assert!(fp.decrypt_key(&[0u8; 72]).is_err(), "ekey before any phase");
        assert!(fp.setup(&message3(0)).is_err(), "phase 2 before phase 1");
        assert!(fp.setup(&[]).is_err());
        assert!(fp.setup(&message1(0)[..15]).is_err());
        assert!(fp.setup(&message3(0)[..163]).is_err());
        let mut v2 = message1(0);
        v2[4] = 0x02;
        assert!(fp.setup(&v2).is_err(), "version byte");
        assert!(fp.setup(&message1(4)).is_err(), "phase 1 mode");
        fp.setup(&message1(0)).unwrap();
        assert!(fp.decrypt_key(&[0u8; 72]).is_err(), "ekey after phase 1 only");
        assert!(fp.setup(&message3(4)).is_err(), "phase 2 mode");
        fp.setup(&message3(0)).unwrap();
        assert!(fp.setup(&message3(0)).is_err(), "phase 2 twice");
        assert!(fp.decrypt_key(&[0u8; 71]).is_err());
        assert!(fp.decrypt_key(&[0u8; 73]).is_err());
        assert!(fp.decrypt_key(&[0u8; 72]).is_ok(), "a failed phase 2 keeps the finished handshake");
        fp.setup(&message1(3)).unwrap();
        assert!(fp.decrypt_key(&[0u8; 72]).is_err(), "phase 1 starts over");
    }
}
