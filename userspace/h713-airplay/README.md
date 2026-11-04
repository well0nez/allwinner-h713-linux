# h713-airplay - AirPlay screen mirroring, in Rust

An iPhone, iPad or Mac in Control Center > **Screen Mirroring** lists the projector (`HY320`) as soon as it is on the
same Wi-Fi - its own access point `h713` or the network it joined - and mirrors onto the wall with the keystone, like
an Apple TV: no PIN, no app. When the phone stops (or the remote's Home/HDMI input takes the wall back) the projector
is where it was: the launcher. The launcher has a **Screen Mirroring** entry with a waiting screen that says what to do.

Status: in development (branch `feat/hy320-airplay`). GPL-3.0-only (`crates/fairplay` carries fcast's
`apple-fairplay`, a Rust port of playfair, GPL-3.0-only); a program of its own in a GPL-2.0 tree.

## Two programs, two units

| | runs | does |
|---|---|---|
| `h713-airplay run` | `h713-airplay.service`, always, user `h713-airplay` | mDNS (`_airplay._tcp`, `_raop._tcp`, a responder of its own, mdns-sd), RTSP on 7000, fp-setup, SETUP/RECORD/TEARDOWN, the encrypted mirror stream (TCP 7100) and screen audio (UDP 6000/6001), NTP towards the sender (UDP 7011 here), the control socket. Decrypts, decodes nothing. |
| `h713-airplay-show` | `h713-airplay-show.service`, a **mode unit** (like `h713-kodi.service`), started by systemd when the receiver connects to `h713-airplay-show.socket` | decodes H.264/H.265 with the video engine (FFmpeg 7.1 VAAPI -> libva-v4l2-request -> cedrus), puts the pictures through h713-warp's Wayland server (`/run/h713-warp/wayland`, keystone, overlays, h713-tv stays the master), decodes AAC-ELD/ALAC and plays it on ALSA `default` (the DSP bridge, S16 48 kHz) |

Why two: the receiver must be there all the time and cost nothing (idle 0.00 CPU: every thread blocked in a
syscall, no decoder, no GPU, no Wayland connection - voxl's rule); the presenter is a mode, so the launcher, the
remote, `h713-mode hdmi`, a standby and `Conflicts=` treat AirPlay exactly as they treat Kodi, with no special case.

### The session, start to end

1. `idle`: advertised, nothing else runs.
2. A sender connects: `GET /info`, `POST /fp-setup` (x2), optional pairing - `connected`.
3. SETUP of the mirror stream (type 110): the receiver connects to `/run/h713-airplay-show.sock`; systemd starts
   the presenter (its `Conflicts=` stop Kodi/Browser/Desktop first, `ExecStartPre=+h713-kodi-switch source` tells
   h713-tv a program is the mode) - `starting`. Frames that come before the presenter reads are kept from the last
   key frame on (bounded, 8 s), so the presenter decodes them all and shows the newest: no corruption, no backlog.
4. The presenter answers `Ready` - `streaming`. h713-keys sees a mode unit come up that it did not start and
   closes an open launcher or page, so the picture is on the wall at once.
5. The end, any of:
   - the sender stops (TEARDOWN, with or without a stream type - iOS 27 sends none; or its connection drops): the
     receiver sends `End`, the presenter exits 0, the unit ends by itself, h713-keys opens the launcher (HDMI
     input chosen), h713-warp gives the panel back to the ring two seconds after the last client is gone;
   - the remote: HDMI input in the launcher (`h713-mode hdmi`: the end is the user's, no launcher), another mode
     (Kodi: `Conflicts=`), Home opens the launcher over the stream as over Kodi;
   - a standby: `h713-mode sleep-pre` stops the unit; after the wake it is started again, finds no session and exits.
   The presenter's connection closing is the receiver's signal to end the session: the sender is told (its
   connections closed) and the state is `idle` again.
6. A second sender while one streams takes over (`takeover = on`, Apple TV's way); `off` answers 409.

### Latency and load (voxl's discipline)

- No jitter buffer: a frame is decrypted on arrival and decoded on arrival; the display queue holds one picture
  (the newest wins; older decoded ones count as `dropped`), the decoder sees every frame (references).
- Audio: bounded queue (drop the oldest past 120 ms), ALSA buffer ~60 ms; video and audio both play on arrival.
- Receiver-initiated NTP (UDP) only to keep the sender happy and to measure the sender's clock for `latency`.
- One thread per socket, blocking; no polling loops, no timers while idle.

## Files and sockets

| | |
|---|---|
| `/etc/h713/airplay.conf` | `name`, `port`, `width`, `height`, `fps`, `hevc`, `audio`, `audio_device`, `takeover`, `interfaces` (crates/proto/src/config.rs) |
| `/run/h713-airplay/ctl` | control socket (crates/proto/src/ctl.rs): `status`, `wait STATE [MS]`, `watch`, `disconnect`; `h713-airplay ctl ...` |
| `/run/h713-airplay-show.sock` | the presenter's socket (socket unit), the stream of crates/proto/src/ipc.rs |
| `/var/lib/h713-airplay/` | the receiver's Ed25519 key and device id (kept, so a sender sees the same receiver after a reboot) |

States (`ctl status`, `wait`, `watch`): `idle`, `connected`, `starting`, `streaming`.

## The launcher entry and the waiting page

`/etc/h713/launcher.d/15-airplay.conf` (profile desktop):

```
label  = Screen Mirroring
icon   = airplay
unit   = h713-airplay-show.service       # the mode: h713-mode ends it, h713-keys watches it, the header follows it
exec   = /usr/bin/systemd-run --quiet --collect --wait --unit=h713-airplay-page /usr/local/bin/h713-airplay page
return = launcher
active = /usr/bin/systemctl is-active --quiet h713-airplay-show.service
now    = AirPlay
```

An entry with both `unit` and `exec` (new in h713-keys): OK runs `exec` - the waiting page - while the unit is not
active, and only closes the launcher while it is (the stream is the mode on the wall). `on_start` does not take it.

**The waiting page** (`h713-airplay page`, crates/page): an opaque page through h713-osd's page channel, the
launcher's ground and face (Quicksand, `0xff0b0e0d`, the pill `0x1c2321`, 5 % safe margin), English like the
launcher:

```
Screen Mirroring
HY320                                     <- the AirPlay name, large
On your iPhone, iPad or Mac: open Control Center, tap Screen Mirroring, choose HY320.
Wi-Fi  h713          IP  192.168.4.1     <- from ctl status (wifi, addrs); every interface the receiver answers on
Ready                                     <- or "Connecting to Peter's iPhone..." / "AirPlay is not running"
BACK close
```

It follows the receiver with `watch` (no polling) and holds the remote like h713-settings (EVIOCGRAB). Exit status
(h713-settings' convention): 0 Back (the launcher comes back, Screen Mirroring chosen), 10 Home, 11 Power (handed to
h713-power as h713-settings does), 14 h713-osd gone, 15 a signal, **16 a stream took the wall** (the page goes and
the stream is on the wall).

## Building

```
make sysroot    # once: tools/make-sysroot.py -> /srv/h713/sysroot-trixie-arm64 (Debian 13 arm64 libraries, headers)
make cross      # h713-airplay.aarch64-linux-gnu, h713-airplay-show.aarch64-linux-gnu
make test       # cargo test --workspace on the host
```

Cross-linked with `aarch64-linux-gnu-gcc --sysroot` against the board's own glibc (2.41), not the host's
(2.43): see tools/make-sysroot.py.

## Work packages (development, 05.11.2026)

| | crate / files | owner |
|---|---|---|
| A | `crates/fairplay` | FairPlay SAP v2.5: fcast's apple-fairplay, differential tests against UxPlay's C playfair |
| B | `crates/receiver`, `crates/sender` | the protocol, mDNS, ctl; `sendtest`/`probe`; host E2E with doubletake as the sender |
| C | `crates/presenter` | VAAPI decode, EGL/GBM/Wayland to h713-warp, audio to ALSA |
| D1 | `userspace/h713-keys`, `userspace/libh713osd`, `userspace/h713-osd`, units, `rootfs/`, `docs/` | launcher semantics, the icon, installation, documentation |
| D2 | `crates/page` | the waiting page |
| - | `crates/proto`, this file, `Makefile`, `tools/` | the contract (lead of the lane) |
