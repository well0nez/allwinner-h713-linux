// SPDX-License-Identifier: GPL-3.0-only
// The sysroot (tools/make-sysroot.py) holds the libraries this binary links against, not everything they need in
// turn (libavcodec's codecs, glvnd's libGLdispatch): those are on the board. So a reference that one of those
// libraries leaves open is not an error of this link; the binary's own references still are.
fn main() {
    if std::env::var("CARGO_CFG_TARGET_ARCH").as_deref() == Ok("aarch64") {
        println!("cargo:rustc-link-arg-bins=-Wl,--allow-shlib-undefined");
    }
}
