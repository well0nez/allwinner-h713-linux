// SPDX-License-Identifier: GPL-3.0-only
fn main() {
    let path = proto::paths::config();
    let (config, warnings) = proto::config::load(&path);
    for w in warnings {
        eprintln!("h713-airplay-show: {}: {w}", path.display());
    }
    if let Err(e) = presenter::run(config) {
        eprintln!("h713-airplay-show: {e}");
        std::process::exit(1);
    }
}
