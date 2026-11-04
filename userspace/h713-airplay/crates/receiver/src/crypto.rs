// SPDX-License-Identifier: GPL-3.0-only
//! The stream keys (UxPlay raop_handlers.h L816-851, mirror_buffer.c L52-123, raop_buffer.c L117-137).

use aes::cipher::{generic_array::GenericArray, BlockDecrypt, KeyInit, KeyIvInit, StreamCipher};
use aes::Aes128;
use sha2::{Digest, Sha512};

pub type Ctr = ctr::Ctr128BE<Aes128>;

fn sha512_16(parts: &[&[u8]]) -> [u8; 16] {
    let mut h = Sha512::new();
    for p in parts {
        h.update(p);
    }
    h.finalize()[..16].try_into().expect("16 of 64")
}

/// The session key: FairPlay's key, mixed with the pair-verify secret when a pair-verify happened.
pub fn session_key(fairplay_key: [u8; 16], ecdh: Option<&[u8; 32]>) -> [u8; 16] {
    match ecdh {
        Some(secret) => sha512_16(&[&fairplay_key, secret]),
        None => fairplay_key,
    }
}

/// One keystream for the whole mirror stream; partial blocks carry over into the next packet.
pub fn mirror_cipher(session_key: &[u8; 16], stream_connection_id: u64) -> Ctr {
    let key = sha512_16(&[format!("AirPlayStreamKey{stream_connection_id}").as_bytes(), session_key]);
    let iv = sha512_16(&[format!("AirPlayStreamIV{stream_connection_id}").as_bytes(), session_key]);
    Ctr::new(&key.into(), &iv.into())
}

pub fn mirror_decrypt(cipher: &mut Ctr, payload: &mut [u8]) {
    cipher.apply_keystream(payload);
}

/// AES-128-CBC restarted at `iv` for every packet, over the whole 16-byte blocks; the rest is plain.
pub fn audio_decrypt(key: &[u8; 16], iv: &[u8; 16], payload: &mut [u8]) {
    let aes = Aes128::new(key.into());
    let mut prev = *iv;
    for block in payload.chunks_exact_mut(16) {
        let cipher_block: [u8; 16] = (&*block).try_into().expect("16");
        aes.decrypt_block(GenericArray::from_mut_slice(block));
        for (b, p) in block.iter_mut().zip(prev) {
            *b ^= p;
        }
        prev = cipher_block;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use aes::cipher::BlockEncrypt;

    #[test]
    fn the_mirror_keystream_continues_across_packets_of_any_length() {
        let key = [7u8; 16];
        let plain: Vec<u8> = (0..1000u32).map(|i| (i * 31 % 251) as u8).collect();
        let mut whole = plain.clone();
        mirror_decrypt(&mut mirror_cipher(&key, 42), &mut whole);
        let mut c = mirror_cipher(&key, 42);
        let mut pieces = plain.clone();
        let mut at = 0;
        for len in [5usize, 16, 3, 100, 1, 875] {
            mirror_decrypt(&mut c, &mut pieces[at..at + len]);
            at += len;
        }
        assert_eq!(pieces, whole);
        assert_ne!(whole, plain);
    }

    #[test]
    fn audio_decrypts_whole_blocks_and_leaves_the_tail_plain() {
        let (key, iv) = ([1u8; 16], [2u8; 16]);
        let plain: Vec<u8> = (0..37u8).collect();
        let aes = Aes128::new(&key.into());
        let mut wire = plain.clone();
        let mut prev = iv;
        for block in wire[..32].chunks_exact_mut(16) {
            for (b, p) in block.iter_mut().zip(prev) {
                *b ^= p;
            }
            aes.encrypt_block(GenericArray::from_mut_slice(block));
            prev = block.try_into().unwrap();
        }
        assert_eq!(wire[32..], plain[32..]);
        audio_decrypt(&key, &iv, &mut wire);
        assert_eq!(wire, plain);
    }
}
