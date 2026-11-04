// SPDX-License-Identifier: GPL-3.0-only
//! The network around the receiver: its IPv4 addresses, the Wi-Fi a sender has to join, TCP keepalive.

use std::net::TcpStream;
use std::os::fd::AsRawFd;
use std::path::Path;

pub const WIFI_ENV: &str = "/etc/h713/wifi.env";

/// A dead sender (out of range, battery) is noticed after about 25 s instead of never.
pub fn keepalive(s: &TcpStream) {
    let fd = s.as_raw_fd();
    for (level, name, value) in [
        (libc::SOL_SOCKET, libc::SO_KEEPALIVE, 1),
        (libc::IPPROTO_TCP, libc::TCP_KEEPIDLE, 10),
        (libc::IPPROTO_TCP, libc::TCP_KEEPINTVL, 5),
        (libc::IPPROTO_TCP, libc::TCP_KEEPCNT, 3),
    ] {
        let v: libc::c_int = value;
        // SAFETY: fd is a live socket owned by `s`; the option value is a c_int of the size given.
        unsafe {
            libc::setsockopt(fd, level, name, (&v as *const libc::c_int).cast(), size_of::<libc::c_int>() as libc::socklen_t);
        }
    }
}

/// `192.168.4.1@wlan0` for every IPv4 address that is not loopback (only `interfaces` when given).
pub fn addrs(interfaces: &[String]) -> Vec<String> {
    let mut out: Vec<String> = if_addrs::get_if_addrs()
        .unwrap_or_default()
        .into_iter()
        .filter(|i| !i.is_loopback() && i.ip().is_ipv4())
        .filter(|i| interfaces.is_empty() || interfaces.contains(&i.name))
        .map(|i| format!("{}@{}", i.ip(), i.name))
        .collect();
    out.sort();
    out.dedup();
    out
}

pub fn interface_names(addrs: &[String]) -> Vec<String> {
    let mut names: Vec<String> = addrs.iter().filter_map(|a| a.split_once('@').map(|(_, n)| n.to_string())).collect();
    names.sort();
    names.dedup();
    names
}

/// The fallback when nl80211 reports nothing: wlan0's network from wifi.env, if this user may read it (0600 root
/// on the device). Only its `mode=` and `ssid=` lines are looked at, nothing else.
pub fn wifi(path: &Path) -> Vec<String> {
    let Ok(text) = std::fs::read_to_string(path) else { return Vec::new() };
    let (mut mode, mut ssid) = (None, None);
    for line in text.lines() {
        let line = line.trim();
        if let Some(v) = line.strip_prefix("mode=") {
            mode = Some(v.trim().trim_matches('"').to_string());
        } else if let Some(v) = line.strip_prefix("ssid=") {
            ssid = Some(v.trim().trim_matches('"').to_string());
        }
    }
    match (mode.as_deref(), ssid) {
        (Some("ap" | "sta"), Some(s)) if !s.is_empty() => vec![format!("{}@wlan0", s.replace(' ', "_"))],
        _ => Vec::new(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wifi_names_the_ssid_and_never_more() {
        let dir = std::env::temp_dir().join(format!("h713-airplay-wifi-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let f = dir.join("wifi.env");
        std::fs::write(&f, "# x\nmode=sta\nssid=test-net\npassword=hunter2\n").unwrap();
        assert_eq!(wifi(&f), vec!["test-net@wlan0"]);
        std::fs::write(&f, "mode=off\nssid=h713\n").unwrap();
        assert!(wifi(&f).is_empty());
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
