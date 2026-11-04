// SPDX-License-Identifier: GPL-3.0-only
//! The decoder's extradata for the AudioConfig a receiver sends: the AudioSpecificConfig for AAC, the 36-byte
//! `alac` atom FFmpeg's ALAC decoder reads.

use proto::ipc::AudioCodec;

/// AAC-ELD, 44.1 kHz, stereo, 480 samples a frame: what an iPhone's screen audio is.
pub const ELD_44100_STEREO: [u8; 4] = [0xf8, 0xe8, 0x50, 0x00];
/// AAC-LC, 44.1 kHz, stereo.
pub const LC_44100_STEREO: [u8; 2] = [0x12, 0x10];

/// ALACSpecificConfig of AirPlay's `96 352 0 16 40 10 14 2 255 0 0 44100` with this frame length, rate and channels.
fn alac_specific(frame_len: u32, sample_rate: u32, channels: u8) -> [u8; 24] {
    let mut c = [0u8; 24];
    c[0..4].copy_from_slice(&frame_len.to_be_bytes());
    c[4..10].copy_from_slice(&[0, 16, 40, 10, 14, channels]);
    c[10..12].copy_from_slice(&255u16.to_be_bytes());
    c[20..24].copy_from_slice(&sample_rate.to_be_bytes());
    c
}

/// The 24-byte ALACSpecificConfig inside a cookie: bare, behind an `alac` atom header, or behind `frma` + `alac`.
pub fn alac_config(cookie: &[u8]) -> Option<[u8; 24]> {
    if cookie.len() == 24 {
        return cookie.try_into().ok();
    }
    let at = cookie.windows(8).position(|w| w[..4] == 36u32.to_be_bytes() && &w[4..] == b"alac")?;
    cookie.get(at + 12..at + 36)?.try_into().ok()
}

pub fn extradata(codec: AudioCodec, config: &[u8], sample_rate: u32, channels: u8, frame_len: u32) -> Vec<u8> {
    match codec {
        AudioCodec::AacEld if config.is_empty() => ELD_44100_STEREO.to_vec(),
        AudioCodec::AacLc if config.is_empty() => LC_44100_STEREO.to_vec(),
        AudioCodec::AacEld | AudioCodec::AacLc => config.to_vec(),
        AudioCodec::Alac => {
            let specific = alac_config(config).unwrap_or_else(|| alac_specific(frame_len.max(1), sample_rate, channels));
            [&36u32.to_be_bytes()[..], b"alac", &[0; 4], &specific].concat()
        }
        AudioCodec::Pcm => Vec::new(),
    }
}

/// The AirPlay volume, -30..0 dB and -144 for mute, as a linear factor.
pub fn gain(db: f32) -> f32 {
    if db <= -144.0 { 0.0 } else { 10f32.powf(db.clamp(-30.0, 0.0) / 20.0) }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_airplay_volume_is_a_gain_from_0_to_1() {
        assert_eq!(gain(0.0), 1.0);
        assert_eq!(gain(-144.0), 0.0);
        assert!((gain(-20.0) - 0.1).abs() < 1e-6);
        assert!((gain(-60.0) - gain(-30.0)).abs() < 1e-9, "below -30 dB is -30 dB (mute is -144)");
    }

    #[test]
    fn alac_without_a_cookie_gets_airplays_default() {
        let x = extradata(AudioCodec::Alac, &[], 44100, 2, 352);
        assert_eq!(x.len(), 36);
        assert_eq!(&x[4..8], b"alac");
        assert_eq!(&x[12..16], &352u32.to_be_bytes());
        assert_eq!(x[17], 16, "bit depth");
        assert_eq!(x[21], 2, "channels");
        assert_eq!(&x[32..36], &44100u32.to_be_bytes());
    }

    #[test]
    fn every_cookie_form_gives_the_same_config() {
        let bare = alac_specific(4096, 44100, 2);
        let atom = [&36u32.to_be_bytes()[..], b"alac", &[0; 4], &bare].concat();
        let caf = [&12u32.to_be_bytes()[..], b"frma", b"alac", &atom, &[0, 0, 0, 8, 0, 0, 0, 0]].concat();
        for cookie in [&bare[..], &atom, &caf] {
            assert_eq!(alac_config(cookie), Some(bare));
            assert_eq!(&extradata(AudioCodec::Alac, cookie, 0, 0, 0)[12..], &bare);
        }
        assert_eq!(alac_config(b"nothing here"), None);
    }

    #[test]
    fn aac_takes_the_senders_config_or_the_mirror_default() {
        assert_eq!(extradata(AudioCodec::AacEld, &[], 44100, 2, 480), ELD_44100_STEREO);
        assert_eq!(extradata(AudioCodec::AacEld, &[0x11, 0x90], 48000, 2, 480), [0x11, 0x90]);
        assert_eq!(extradata(AudioCodec::AacLc, &[], 44100, 2, 1024), LC_44100_STEREO);
    }
}
