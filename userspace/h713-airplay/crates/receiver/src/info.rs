// SPDX-License-Identifier: GPL-3.0-only
//! What the receiver says about itself: the feature bits, the two TXT records (dnssd.c, dnssdint.h) and
//! `GET /info` (raop_handlers.h L37-243).

use crate::shared::Shared;
use plist::{Dictionary, Value};

pub const MODEL: &str = "AppleTV3,2";
pub const SOURCE_VERSION: &str = "220.68";
const DISPLAY_UUID: &str = "e0ff8a27-6738-3d56-8a16-cc53aacee925";

/// UxPlay's default low word: bit 27 (legacy pairing) off, so iOS pairs not and FairPlay's key is used as is.
const FEATURES_LOW: u32 = 0x527F_FEE6;
/// Bit 42, SupportsScreenMultiCodec: iOS 27 sends an empty codec packet without it (UxPlay issue #535).
const FEATURES_HEVC_HIGH: u32 = 0x400;

pub fn features(hevc: bool) -> u64 {
    let high = if hevc { FEATURES_HEVC_HIGH } else { 0 };
    (u64::from(high) << 32) | u64::from(FEATURES_LOW)
}

pub fn features_txt(hevc: bool) -> String {
    if hevc {
        format!("0x{FEATURES_LOW:X},0x{FEATURES_HEVC_HIGH:X}")
    } else {
        format!("0x{FEATURES_LOW:X}")
    }
}

pub fn raop_txt(sh: &Shared) -> Vec<(&'static str, String)> {
    let ft = features_txt(sh.config.hevc);
    [
        ("ch", "2"),
        ("cn", "0,1,2,3"),
        ("da", "true"),
        ("et", "0,3,5"),
        ("vv", "2"),
        ("ft", &ft),
        ("am", MODEL),
        ("md", "0,1,2"),
        ("rhd", "5.6.0.0"),
        ("pw", "false"),
        ("sf", "0x4"),
        ("sr", "44100"),
        ("ss", "16"),
        ("sv", "false"),
        ("tp", "UDP"),
        ("txtvers", "1"),
        ("vs", SOURCE_VERSION),
        ("vn", "65537"),
    ]
    .into_iter()
    .map(|(k, v)| (k, v.to_string()))
    .chain([("pk", sh.identity.public_key_hex())])
    .collect()
}

pub fn airplay_txt(sh: &Shared) -> Vec<(&'static str, String)> {
    vec![
        ("deviceid", sh.identity.device_id()),
        ("features", features_txt(sh.config.hevc)),
        ("pw", "false".into()),
        ("flags", "0x4".into()),
        ("model", MODEL.into()),
        ("pk", sh.identity.public_key_hex()),
        ("pi", sh.identity.pi.clone()),
        ("srcvers", SOURCE_VERSION.into()),
        ("vv", "2".into()),
    ]
}

/// A TXT record's wire form: one length-prefixed `key=value` string per entry.
pub fn txt_wire(txt: &[(&str, String)]) -> Vec<u8> {
    let mut out = Vec::new();
    for (k, v) in txt {
        let entry = format!("{k}={v}");
        out.push(entry.len().min(255) as u8);
        out.extend_from_slice(&entry.as_bytes()[..entry.len().min(255)]);
    }
    out
}

fn dict(entries: Vec<(&str, Value)>) -> Value {
    Value::Dictionary(entries.into_iter().map(|(k, v)| (k.to_string(), v)).collect::<Dictionary>())
}

fn uint(v: u64) -> Value {
    Value::Integer(v.into())
}

/// The answer to a `GET /info` with a binary plist body: only the TXT records its `qualifier` names.
pub fn txt_info(sh: &Shared, qualifier: &[String]) -> Value {
    let mut d = Dictionary::new();
    if qualifier.iter().any(|q| q == "txtAirPlay") {
        d.insert("txtAirPlay".into(), Value::Data(txt_wire(&airplay_txt(sh))));
    }
    if qualifier.iter().any(|q| q == "txtRAOP") {
        d.insert("txtRAOP".into(), Value::Data(txt_wire(&raop_txt(sh))));
    }
    Value::Dictionary(d)
}

fn latencies() -> Value {
    let one = |t: u64| {
        dict(vec![
            ("type", uint(t)),
            ("inputLatencyMicros", uint(0)),
            ("audioType", Value::String("default".into())),
            ("outputLatencyMicros", Value::Boolean(false)),
        ])
    };
    Value::Array(vec![one(100), one(101)])
}

fn formats() -> Value {
    let one = |t: u64| {
        dict(vec![
            ("audioOutputFormats", uint(0x3ff_fffc)),
            ("type", uint(t)),
            ("audioInputFormats", uint(0x3ff_fffc)),
        ])
    };
    Value::Array(vec![one(100), one(101)])
}

pub fn full_info(sh: &Shared, volume_db: f32) -> Value {
    let c = &sh.config;
    let display = dict(vec![
        ("uuid", Value::String(DISPLAY_UUID.into())),
        ("widthPhysical", uint(0)),
        ("heightPhysical", uint(0)),
        ("width", uint(c.width.into())),
        ("height", uint(c.height.into())),
        ("widthPixels", uint(c.width.into())),
        ("heightPixels", uint(c.height.into())),
        ("rotation", Value::Boolean(false)),
        ("refreshRate", Value::Real(1.0 / f64::from(c.fps.max(1)))),
        ("maxFPS", uint(c.fps.into())),
        ("overscanned", Value::Boolean(false)),
        ("features", uint(14)),
    ]);
    dict(vec![
        ("deviceID", Value::String(sh.identity.device_id())),
        ("macAddress", Value::String(sh.identity.device_id())),
        ("pk", Value::Data(sh.identity.public_key().to_vec())),
        ("features", uint(features(c.hevc))),
        ("name", Value::String(c.name.clone())),
        ("pi", Value::String(sh.identity.pi.clone())),
        ("vv", uint(2)),
        ("statusFlags", uint(68)),
        ("keepAliveLowPower", uint(1)),
        ("sourceVersion", Value::String(SOURCE_VERSION.into())),
        ("keepAliveSendStatsAsBody", Value::Boolean(true)),
        ("model", Value::String(MODEL.into())),
        ("initialVolume", Value::Real(f64::from(volume_db))),
        ("audioLatencies", latencies()),
        ("audioFormats", formats()),
        ("displays", Value::Array(vec![display])),
    ])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn features_carry_bit_42_only_with_hevc_and_never_bit_27() {
        assert_eq!(features(true), 0x400_527F_FEE6);
        assert_eq!(features(false) >> 32, 0);
        assert_eq!(features(true) & (1 << 27), 0);
        assert_eq!(features_txt(true), "0x527FFEE6,0x400");
    }

    #[test]
    fn txt_wire_is_length_prefixed_entries() {
        assert_eq!(txt_wire(&[("a", "1".into()), ("bb", "".into())]), b"\x03a=1\x03bb=".to_vec());
    }
}
