// SPDX-License-Identifier: GPL-3.0-only
//! The receiver daemon (`h713-airplay run`). Work package B (README.md, "Work packages").

use proto::config::Config;
use std::io;

pub fn run(config: Config) -> io::Result<()> {
    let _ = config;
    Err(io::Error::other("the receiver is not implemented yet (work package B)"))
}
