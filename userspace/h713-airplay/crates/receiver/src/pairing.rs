// SPDX-License-Identifier: GPL-3.0-only
//! Legacy AirPlay pairing (raop_handlers.h L451-542, pairing.c): `/pair-setup` hands out the Ed25519 key,
//! `/pair-verify` is an X25519 exchange whose signatures travel AES-128-CTR encrypted with keys from the
//! shared secret. Only senders that insist (doubletake) use it: iOS skips it while feature bit 27 is off.

use crate::crypto::Ctr;
use ed25519_dalek::{Signature, Signer, SigningKey, Verifier, VerifyingKey};
use sha2::{Digest, Sha512};
use x25519_dalek::{PublicKey, StaticSecret};

#[derive(Default)]
pub struct Pairing {
    verify: Option<Verify>,
    pub verified: bool,
}

struct Verify {
    ours: [u8; 32],
    theirs: [u8; 32],
    their_ed: [u8; 32],
    secret: [u8; 32],
}

fn cipher(secret: &[u8; 32]) -> Ctr {
    use aes::cipher::KeyIvInit;
    let derive = |salt: &[u8]| -> [u8; 16] {
        let mut h = Sha512::new();
        h.update(salt);
        h.update(secret);
        h.finalize()[..16].try_into().expect("16")
    };
    Ctr::new(&derive(b"Pair-Verify-AES-Key").into(), &derive(b"Pair-Verify-AES-IV").into())
}

pub enum Error {
    BadRequest(&'static str),
    BadSignature,
}

impl Pairing {
    /// The X25519 secret once step 1 ran: SETUP mixes it into the FairPlay key (UxPlay does from step 1 on).
    pub fn ecdh_secret(&self) -> Option<&[u8; 32]> {
        self.verify.as_ref().map(|v| &v.secret)
    }

    pub fn setup(&self, key: &SigningKey, body: &[u8]) -> Result<Vec<u8>, Error> {
        if body.len() != 32 {
            return Err(Error::BadRequest("pair-setup wants a 32-byte Ed25519 key"));
        }
        Ok(key.verifying_key().to_bytes().to_vec())
    }

    pub fn verify(&mut self, key: &SigningKey, body: &[u8]) -> Result<Vec<u8>, Error> {
        use aes::cipher::StreamCipher;
        match (body.first(), body.len()) {
            (Some(1), 68) => {
                let mut seed = [0u8; 32];
                getrandom::getrandom(&mut seed).map_err(|_| Error::BadRequest("no randomness"))?;
                let ours_secret = StaticSecret::from(seed);
                let ours = PublicKey::from(&ours_secret).to_bytes();
                let theirs: [u8; 32] = body[4..36].try_into().expect("32");
                let their_ed: [u8; 32] = body[36..68].try_into().expect("32");
                let secret = ours_secret.diffie_hellman(&PublicKey::from(theirs)).to_bytes();
                let mut msg = [0u8; 64];
                msg[..32].copy_from_slice(&ours);
                msg[32..].copy_from_slice(&theirs);
                let mut sig = key.sign(&msg).to_bytes();
                cipher(&secret).apply_keystream(&mut sig);
                self.verify = Some(Verify { ours, theirs, their_ed, secret });
                self.verified = false;
                let mut out = ours.to_vec();
                out.extend_from_slice(&sig);
                Ok(out)
            }
            (Some(0), 68) => {
                let v = self.verify.as_ref().ok_or(Error::BadRequest("pair-verify step 2 before step 1"))?;
                let mut c = cipher(&v.secret);
                let mut skip = [0u8; 64];
                c.apply_keystream(&mut skip);
                let mut sig: [u8; 64] = body[4..68].try_into().expect("64");
                c.apply_keystream(&mut sig);
                let mut msg = [0u8; 64];
                msg[..32].copy_from_slice(&v.theirs);
                msg[32..].copy_from_slice(&v.ours);
                let their_key = VerifyingKey::from_bytes(&v.their_ed).map_err(|_| Error::BadSignature)?;
                their_key.verify(&msg, &Signature::from_bytes(&sig)).map_err(|_| Error::BadSignature)?;
                self.verified = true;
                Ok(Vec::new())
            }
            _ => Err(Error::BadRequest("pair-verify wants 68 bytes, flag 1 or 0")),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use aes::cipher::StreamCipher;

    #[test]
    fn a_client_that_follows_the_protocol_verifies_and_a_wrong_signature_does_not() {
        let server = SigningKey::from_bytes(&[3; 32]);
        let client = SigningKey::from_bytes(&[4; 32]);
        let client_x = StaticSecret::from([5u8; 32]);
        let client_xpub = PublicKey::from(&client_x).to_bytes();
        let mut p = Pairing::default();
        let mut v1 = vec![1, 0, 0, 0];
        v1.extend_from_slice(&client_xpub);
        v1.extend_from_slice(&client.verifying_key().to_bytes());
        let Ok(v2) = p.verify(&server, &v1) else { panic!("step 1") };
        let server_xpub: [u8; 32] = v2[..32].try_into().unwrap();
        let secret = client_x.diffie_hellman(&PublicKey::from(server_xpub)).to_bytes();
        assert_eq!(p.ecdh_secret(), Some(&secret));

        let mut server_sig: [u8; 64] = v2[32..].try_into().unwrap();
        let mut c = cipher(&secret);
        c.apply_keystream(&mut server_sig);
        let mut msg = [0u8; 64];
        msg[..32].copy_from_slice(&server_xpub);
        msg[32..].copy_from_slice(&client_xpub);
        server.verifying_key().verify(&msg, &Signature::from_bytes(&server_sig)).unwrap();

        msg[..32].copy_from_slice(&client_xpub);
        msg[32..].copy_from_slice(&server_xpub);
        let mut sig = client.sign(&msg).to_bytes();
        c.apply_keystream(&mut sig);
        let mut v3 = vec![0u8; 4];
        v3.extend_from_slice(&sig);
        let mut tampered = v3.clone();
        tampered[10] ^= 1;
        assert!(matches!(p.verify(&server, &tampered), Err(Error::BadSignature)));
        assert!(p.verify(&server, &v3).is_ok());
        assert!(p.verified);
    }
}
