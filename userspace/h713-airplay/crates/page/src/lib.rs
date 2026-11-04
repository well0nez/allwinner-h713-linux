// SPDX-License-Identifier: GPL-3.0-only
//! `h713-airplay page`, the waiting screen. Work package D2 (README.md, "Work packages").

use proto::config::Config;

/// The exit status is h713-settings' convention (README.md, "The waiting page").
pub fn run(config: &Config) -> i32 {
    let _ = config;
    eprintln!("h713-airplay page: not implemented yet (work package D2)");
    14
}
