// SPDX-License-Identifier: GPL-3.0-only
//! The port against UxPlay's C (v1.73.7, https://github.com/FDH2/UxPlay commit
//! df67c212a433cf6dda3676dd40c097900d24e645), which real iOS 17/18/26 senders work with.
//!
//! playfair_vectors.txt is uxplay_driver.c's output for 32 cases per mode (`./driver 32 0x48373133`).
//! The large run builds the driver against a UxPlay checkout and compares every case:
//!
//!   git clone https://github.com/FDH2/UxPlay /tmp/uxplay && git -C /tmp/uxplay checkout df67c212a433
//!   UXPLAY_PLAYFAIR_DIR=/tmp/uxplay UXPLAY_CASES=1000 \
//!     cargo test -p h713-airplay-fairplay --test differential -- --ignored --nocapture

use fairplay::FairPlay;

fn unhex(s: &str) -> Vec<u8> {
    assert!(s.len() % 2 == 0, "odd hex length");
    (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i + 2], 16).expect("hex")).collect()
}

/// Checks every line of the driver's output; returns the number of cases per mode.
fn check(vectors: &str) -> [usize; 4] {
    let mut message1: [Option<Vec<u8>>; 4] = Default::default();
    let mut counts = [0usize; 4];
    for (n, line) in vectors.lines().enumerate() {
        let f: Vec<&str> = line.split_whitespace().collect();
        let mode: usize = f[1].parse().expect("mode");
        match f[0] {
            "p1" => {
                let m1 = unhex(f[2]);
                let reply = FairPlay::new().setup(&m1).expect("phase 1");
                assert_eq!(reply, unhex(f[3]), "line {}: phase 1 reply, mode {mode}", n + 1);
                message1[mode] = Some(m1);
            }
            "case" => {
                let m1 = message1[mode].as_ref().expect("p1 line before the cases");
                let mut fp = FairPlay::new();
                fp.setup(m1).expect("phase 1");
                let reply2 = fp.setup(&unhex(f[2])).expect("phase 2");
                assert_eq!(reply2, unhex(f[3]), "line {}: phase 2 reply, mode {mode}", n + 1);
                let key = fp.decrypt_key(&unhex(f[4])).expect("ekey");
                assert_eq!(key.to_vec(), unhex(f[5]), "line {}: key, mode {mode}", n + 1);
                counts[mode] += 1;
            }
            other => panic!("line {}: unknown record {other:?}", n + 1),
        }
    }
    counts
}

#[test]
fn matches_uxplay_fixture() {
    assert_eq!(check(include_str!("playfair_vectors.txt")), [32; 4]);
}

#[test]
#[ignore = "needs a UxPlay checkout in UXPLAY_PLAYFAIR_DIR and a C compiler"]
fn matches_uxplay_live() {
    use std::process::Command;
    let uxplay = std::path::PathBuf::from(std::env::var("UXPLAY_PLAYFAIR_DIR").expect("UXPLAY_PLAYFAIR_DIR"));
    let cases: usize = std::env::var("UXPLAY_CASES").map_or(1000, |v| v.parse().expect("UXPLAY_CASES"));
    let seed = std::env::var("UXPLAY_SEED").unwrap_or_else(|_| "0x5eed".into());
    let lib = uxplay.join("lib");
    let out = std::env::temp_dir().join(format!("fairplay-uxplay-driver-{}", std::process::id()));
    let mut cc = Command::new(std::env::var("CC").unwrap_or_else(|_| "cc".into()));
    cc.arg("-O2").arg("-I").arg(&lib).arg("-o").arg(&out);
    cc.arg(concat!(env!("CARGO_MANIFEST_DIR"), "/tests/uxplay_driver.c")).arg(lib.join("fairplay_playfair.c"));
    for c in ["hand_garble.c", "modified_md5.c", "omg_hax.c", "playfair.c", "sap_hash.c"] {
        cc.arg(lib.join("playfair").join(c));
    }
    let status = cc.arg("-lm").status().expect("run cc");
    assert!(status.success(), "building the UxPlay driver failed");
    let run = Command::new(&out).arg(cases.to_string()).arg(&seed).output().expect("run the driver");
    std::fs::remove_file(&out).expect("remove the driver");
    assert!(run.status.success(), "driver: {}", String::from_utf8_lossy(&run.stderr));
    let counts = check(std::str::from_utf8(&run.stdout).expect("utf-8"));
    println!("uxplay differential: seed {seed}, cases per mode {counts:?}, 0 mismatches");
    assert_eq!(counts, [cases; 4]);
}
