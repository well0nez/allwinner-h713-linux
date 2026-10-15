# `rootfs/libva/` - the VA-API driver for the hardware decoders

`build-libva.sh` cross-builds one module, `usr/local/lib/dri/v4l2_request_drv_video.so` (about 140 KiB, links libc only), the
VA-API driver that lets stock ffmpeg, mpv, GStreamer `va*dec` and Kodi decode on the SoC: H.264, HEVC, MPEG-2, VP8, VP9 on the
video engine (cedrus) and AV1 on its own core (hantro). The decoders themselves are kernel drivers; this module is the part
that sits between libva and their V4L2 stateless interface.

| | |
|---|---|
| base | `libva-v4l2_request` v1.2 + one README commit, `cac6ece0e23ac1f944dd3af266680aff0c3184df`, <https://xff.cz/git/libva-v4l2_request/> (Ondrej Jirman, GPL-3.0-or-later). Fetched at build time and pinned by that commit; nothing of it is in this repository |
| patches | `patches/`, in the order of `patches/series`. `0001`-`0009` are Christopher Stenger's, made on the same base; each keeps his `From:` and carries an `Origin:` line naming his file, and apart from that line they are his files byte for byte. `0010` on are this project's (GPL-3.0-or-later like the code they change): `0010` gives a surface exported before its first decode the layout of the context that will decode into it (GStreamer `vaav1dec` into GL was green: the AV1 core appends its motion vectors to every buffer), `0011` offers NV12 only for HEVC Main10 when the decoder writes 8-bit samples (cedrus; FFmpeg picked P010 and every download failed). `0014` backs a bare 10-bit surface with NV12 when no decoder writes P010 or PL10 (cedrus alone): its export failed, so Kodi's interop probe said "deepColor no" and played HEVC Main10 in software. They fix what 1.2 as released gets wrong on this SoC (AV1 crashes, a resolution change crashes, GStreamer's dma-buf export shows green) and add the H713 specifics: the AV1 core's 10 bit layout (`PL10`), the decode-time scaler (`V4L2_REQUEST_SCALE`, `V4L2_REQUEST_CROP`), an opt-in linear P010 export for GL (`V4L2_REQUEST_LSB10_LINEAR`). Each patch's own message says what and why |
| licence | GPL-3.0-or-later for the module. The tarball carries `COPYING` and a `SOURCE` note (commit, patch list) under `usr/local/share/doc/libva-v4l2-request/` |
| build | `rootfs/libva/build-libva.sh` in the build container, against the arm64 sysroot of `release/build-all.sh` step 6 (`libva-dev` is in its package list). Writes `libva-v4l2-request-1.2.tar` to `mainline/build/out/` (or `$OUT`). Same inputs give the same bytes |
| use | `rootfs/build-rootfs.sh --profile media` or `--profile desktop` lays the tarball in (`--libva`), together with `rootfs/overlay-va/`: `/etc/environment.d/h713-media.conf` names the driver (`LIBVA_DRIVER_NAME=v4l2_request`, `LIBVA_DRIVERS_PATH=/usr/local/lib/dri`) and `/usr/local/share/h713/systemd/h713-media-env.conf` hands the same file to a system unit (`EnvironmentFile=`). The base image carries neither |

The kernel side (the cedrus changes and VP9 of package B, the AV1 core and `PL10` of package C) is in `mainline/patches/kernel/`; without it the module finds no decoder
and libva reports no profiles.
