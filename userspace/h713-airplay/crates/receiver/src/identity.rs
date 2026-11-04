// SPDX-License-Identifier: GPL-3.0-only
//! The receiver's identity, kept in `proto::paths::state_dir()` so a sender sees the same receiver after a
//! reboot: the Ed25519 key (`ed25519.key`, 32-byte seed, 0600), the device id (`device_id`, a MAC) and `pi`.

use ed25519_dalek::SigningKey;
use std::fs;
use std::io::{self, Write};
use std::os::unix::fs::OpenOptionsExt;
use std::path::Path;

pub struct Identity {
    pub key: SigningKey,
    pub mac: [u8; 6],
    pub pi: String,
}

impl Identity {
    /// `aa:bb:cc:dd:ee:ff`: deviceID, macAddress and the TXT `deviceid`.
    pub fn device_id(&self) -> String {
        self.mac.iter().map(|b| format!("{b:02x}")).collect::<Vec<_>>().join(":")
    }
    /// `AABBCCDDEEFF`: the `_raop._tcp` instance prefix.
    pub fn raop_prefix(&self) -> String {
        self.mac.iter().map(|b| format!("{b:02X}")).collect()
    }
    pub fn public_key(&self) -> [u8; 32] {
        self.key.verifying_key().to_bytes()
    }
    pub fn public_key_hex(&self) -> String {
        self.public_key().iter().map(|b| format!("{b:02x}")).collect()
    }
}

fn random<const N: usize>() -> io::Result<[u8; N]> {
    let mut b = [0u8; N];
    getrandom::getrandom(&mut b).map_err(io::Error::other)?;
    Ok(b)
}

fn write_private(path: &Path, data: &[u8]) -> io::Result<()> {
    let tmp = path.with_extension("new");
    let mut f = fs::OpenOptions::new().write(true).create(true).truncate(true).mode(0o600).open(&tmp)?;
    f.write_all(data)?;
    f.sync_all()?;
    fs::rename(&tmp, path)
}

fn parse_mac(s: &str) -> Option<[u8; 6]> {
    let parts: Vec<u8> = s.trim().split(':').map(|p| u8::from_str_radix(p, 16)).collect::<Result<_, _>>().ok()?;
    let mac: [u8; 6] = parts.try_into().ok()?;
    (mac != [0; 6]).then_some(mac)
}

/// wlan0's MAC, else the first other interface's (sorted by name, loopback skipped).
fn hardware_mac() -> Option<[u8; 6]> {
    let read = |name: &str| fs::read_to_string(format!("/sys/class/net/{name}/address")).ok().and_then(|s| parse_mac(&s));
    if let Some(mac) = read("wlan0") {
        return Some(mac);
    }
    let mut names: Vec<String> =
        fs::read_dir("/sys/class/net").ok()?.filter_map(|e| e.ok()?.file_name().into_string().ok()).collect();
    names.sort();
    names.iter().filter(|n| n.as_str() != "lo").find_map(|n| read(n))
}

fn load_key(dir: &Path) -> io::Result<SigningKey> {
    let path = dir.join("ed25519.key");
    match fs::read(&path) {
        Ok(seed) if seed.len() == 32 => Ok(SigningKey::from_bytes(&seed.try_into().expect("32 bytes"))),
        Ok(_) => Err(io::Error::new(io::ErrorKind::InvalidData, format!("{}: not a 32-byte seed", path.display()))),
        Err(e) if e.kind() == io::ErrorKind::NotFound => {
            let seed = random::<32>()?;
            write_private(&path, &seed)?;
            Ok(SigningKey::from_bytes(&seed))
        }
        Err(e) => Err(e),
    }
}

fn load_mac(dir: &Path) -> io::Result<[u8; 6]> {
    let path = dir.join("device_id");
    let stored = fs::read_to_string(&path).ok().and_then(|s| parse_mac(&s));
    let mac = match (hardware_mac(), stored) {
        (Some(hw), _) => hw,
        (None, Some(st)) => st,
        (None, None) => {
            let mut m = random::<6>()?;
            m[0] = (m[0] & 0xfc) | 0x02;
            m
        }
    };
    if stored != Some(mac) {
        let text = mac.iter().map(|b| format!("{b:02x}")).collect::<Vec<_>>().join(":");
        write_private(&path, format!("{text}\n").as_bytes())?;
    }
    Ok(mac)
}

fn load_pi(dir: &Path) -> io::Result<String> {
    let path = dir.join("pi");
    if let Ok(s) = fs::read_to_string(&path) {
        let s = s.trim().to_string();
        if s.len() == 36 {
            return Ok(s);
        }
    }
    let mut b = random::<16>()?;
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    let h: String = b.iter().map(|x| format!("{x:02x}")).collect();
    let pi = format!("{}-{}-{}-{}-{}", &h[0..8], &h[8..12], &h[12..16], &h[16..20], &h[20..32]);
    write_private(&path, format!("{pi}\n").as_bytes())?;
    Ok(pi)
}

pub fn load(dir: &Path) -> io::Result<Identity> {
    fs::create_dir_all(dir)?;
    let at = |e: io::Error| io::Error::new(e.kind(), format!("{}: {e}", dir.display()));
    Ok(Identity { key: load_key(dir).map_err(at)?, mac: load_mac(dir).map_err(at)?, pi: load_pi(dir).map_err(at)? })
}
