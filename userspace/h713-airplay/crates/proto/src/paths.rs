// SPDX-License-Identifier: GPL-3.0-only
use std::path::PathBuf;

/// The receiver's control socket (`RuntimeDirectory=h713-airplay`).
pub const CTL_SOCKET: &str = "/run/h713-airplay/ctl";
/// The presenter's socket: `h713-airplay-show.socket` listens, the receiver connects when a sender sets up a stream,
/// and systemd starts `h713-airplay-show.service` with the listening socket (fd 3, `LISTEN_FDS=1`).
pub const SHOW_SOCKET: &str = "/run/h713-airplay-show.sock";
pub const CONFIG: &str = "/etc/h713/airplay.conf";
/// The receiver's key pair and device id (`StateDirectory=h713-airplay`).
pub const STATE_DIR: &str = "/var/lib/h713-airplay";
/// h713-warp's Wayland server (docs/tools/h713-warp.md, "A Wayland client").
pub const WARP_WAYLAND: &str = "/run/h713-warp/wayland";
/// h713-osd's control socket: the page channel (docs/tools/h713-osd.md, "The page channel").
pub const OSD_CTL: &str = "/run/h713-osd/ctl";

fn over(var: &str, default: &str) -> PathBuf {
    std::env::var_os(var).map(PathBuf::from).unwrap_or_else(|| PathBuf::from(default))
}

pub fn ctl_socket() -> PathBuf {
    over("H713_AIRPLAY_CTL", CTL_SOCKET)
}
pub fn show_socket() -> PathBuf {
    over("H713_AIRPLAY_SHOW_SOCKET", SHOW_SOCKET)
}
pub fn config() -> PathBuf {
    over("H713_AIRPLAY_CONF", CONFIG)
}
pub fn state_dir() -> PathBuf {
    over("H713_AIRPLAY_STATE", STATE_DIR)
}
pub fn warp_wayland() -> PathBuf {
    over("WAYLAND_DISPLAY", WARP_WAYLAND)
}
pub fn osd_ctl() -> PathBuf {
    over("H713_OSD_CTL", OSD_CTL)
}
