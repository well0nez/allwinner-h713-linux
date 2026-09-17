# userspace/ - what runs on the board

| Directory | What | State |
|---|---|---|
| [`h713-tv/`](h713-tv/README.md) | **The HDMI input as a service.** C, one process: shows the capture ring on the KMS plane, and the console on signal loss; sends the preset and the gamma curve at the start; control channel `h713-tv ctl …` (controls, presets, aspect fit, picture on/off, a raw RPC). Runs as a template unit, one instance per capture device (`h713-tv@videoN`, started by udev, `BindsTo`; the number varies with probe order). | in service (08.09.2026) |
| [`h713-pq/`](h713-pq/README.md) | **The PQ calculator.** Python, reads the stock PQ data (`pq_picturemode.ini`, `tvpq.db`, …) and computes RPC arguments and DE2 gamma LUTs. Writes nothing to the device; `gamma-standard.bin` in `h713-tv/` comes from here. | finished, a tool |
| [`h713-focus/`](h713-focus/README.md) | **Driving the focus motor by hand.** One Python script, without dependencies. `status` / `up` / `down` / `flush` / `unlatch`; reads the range guard before and after every movement, has a hard upper bound per run, and never writes `motor_ctrl_no_limit`. Replaces `legacy/tools/focus`. | finished (12.09.2026) |
| [`h713-cam/`](h713-cam/README.md) | **The internal camera.** One Python script, without dependencies. `probe` / `controls` / `get` / `set` / `grab` (PNG); finds the node by its name instead of guessing `/dev/video2`; writes the exposure back once before the picture (the camera delivers black otherwise). Out of `analyse/beamer-cam/`. | in service (12.09.2026): node found by name, controls and `grab` verified on the device |

Building and installing: `doku/50-befehle.md`, the operation section. The old stock rebuilds `hy310-hdmird`
and `hy310-pqd` (C++ daemons with an RPC layer of their own) are left in `legacy/` for reference only; their
knowledge sits in the kernel drivers (`doku/77` §3).
