// SPDX-License-Identifier: GPL-3.0-only
//! FairPlay SAP v2.5 (`POST /fp-setup`) on the receiver's side. Work package A (README.md, "Work packages").

use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Error(pub String);

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "fairplay: {}", self.0)
    }
}

impl std::error::Error for Error {}

/// One sender's handshake: phase 1 (16 bytes in, 142 out), phase 2 (164 bytes in, 32 out), then the key.
#[derive(Default)]
pub struct FairPlay {
    message3: Option<Vec<u8>>,
}

impl FairPlay {
    pub fn new() -> Self {
        Self::default()
    }

    /// The answer to one `/fp-setup` body.
    pub fn setup(&mut self, request: &[u8]) -> Result<Vec<u8>, Error> {
        let _ = (&mut self.message3, request);
        Err(Error("not implemented yet (work package A)".into()))
    }

    /// The AES key that SETUP's 72-byte `ekey` wraps; needs phase 2 first.
    pub fn decrypt_key(&self, ekey: &[u8]) -> Result<[u8; 16], Error> {
        let _ = ekey;
        Err(Error("not implemented yet (work package A)".into()))
    }
}
