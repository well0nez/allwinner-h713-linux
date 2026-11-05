// SPDX-License-Identifier: GPL-3.0-only
//! The contract between the programs of h713-airplay.
//!
//! * [`ipc`]: the one stream between the receiver (`h713-airplay run`) and the presenter (`h713-airplay-show`),
//!   a Unix stream socket that systemd hands to the presenter (socket activation, `paths::SHOW_SOCKET`).
//! * [`ctl`]: the receiver's control socket, one command per connection, answer's first word `ok` or `error`
//!   (the convention of `h713-warp ctl` and `h713-osd ctl`).
//! * [`config`]: `/etc/h713/airplay.conf`.
//! * [`paths`]: the places, each with an environment override for host tests.

pub mod config;
pub mod ctl;
pub mod ipc;
pub mod paths;
