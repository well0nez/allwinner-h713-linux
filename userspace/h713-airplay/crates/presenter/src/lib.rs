// SPDX-License-Identifier: GPL-3.0-only
//! The presenter (`h713-airplay-show`). Work package C (README.md, "Work packages").

use proto::config::Config;
use std::io;

pub fn run(config: Config) -> io::Result<()> {
    let _ = config;
    Err(io::Error::other("the presenter is not implemented yet (work package C)"))
}
