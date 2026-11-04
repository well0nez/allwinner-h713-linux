// SPDX-License-Identifier: GPL-3.0-only
//! The sender's side of the stream keys, written apart from the receiver's so a test of one against the other
//! can fail: AES-128-CTR for the mirror stream, AES-128-CBC per audio packet.

use aes::cipher::{generic_array::GenericArray, BlockEncrypt, KeyInit, KeyIvInit, StreamCipher};
use aes::Aes128;
use sha2::{Digest, Sha512};

pub struct MirrorCipher(ctr::Ctr128BE<Aes128>);

fn derive(label: &str, id: u64, key: &[u8; 16]) -> [u8; 16] {
    let mut h = Sha512::new();
    h.update(format!("{label}{id}").as_bytes());
    h.update(key);
    let full = h.finalize();
    let mut out = [0u8; 16];
    out.copy_from_slice(&full[..16]);
    out
}

impl MirrorCipher {
    pub fn new(key: &[u8; 16], stream_connection_id: u64) -> MirrorCipher {
        let k = derive("AirPlayStreamKey", stream_connection_id, key);
        let iv = derive("AirPlayStreamIV", stream_connection_id, key);
        MirrorCipher(ctr::Ctr128BE::new(&k.into(), &iv.into()))
    }
    pub fn encrypt(&mut self, data: &mut [u8]) {
        self.0.apply_keystream(data);
    }
}

pub fn audio_encrypt(key: &[u8; 16], iv: &[u8; 16], data: &mut [u8]) {
    let aes = Aes128::new(key.into());
    let mut prev = *iv;
    for block in data.chunks_exact_mut(16) {
        for (b, p) in block.iter_mut().zip(prev) {
            *b ^= p;
        }
        aes.encrypt_block(GenericArray::from_mut_slice(block));
        prev.copy_from_slice(block);
    }
}

pub fn random<const N: usize>() -> [u8; N] {
    let mut b = [0u8; N];
    getrandom::getrandom(&mut b).expect("the kernel's random numbers");
    b
}
