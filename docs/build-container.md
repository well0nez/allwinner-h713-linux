# The build container

`release/build-all.sh` builds nothing on your host. It drives a container named **`h713-build`** that has
the toolchain, and it derives the in-container path of this repository from the container's own mounts -
so the repository can sit anywhere, as long as it is mounted.

This page is the recipe. It is a one-time setup; after that `release/build-all.sh` is the only command
you need ([BUILDING.md](../BUILDING.md)).

## Create it

Rootless podman, Ubuntu 24.04, this repository mounted at `/work`, `--userns=keep-id` so every file the
build writes stays owned by you:

```bash
podman run -d --name h713-build --userns=keep-id \
  -v "$PWD":/work docker.io/library/ubuntu:24.04 sleep infinity
```

## Toolchain

```bash
podman exec -u root h713-build apt-get update
podman exec -u root h713-build apt-get install -y --no-install-recommends \
  clang lld llvm device-tree-compiler swig flex bison u-boot-tools \
  build-essential bc kmod libssl-dev libelf-dev python3-dev git curl \
  ca-certificates xz-utils cpio rsync libgnutls28-dev uuid-dev \
  libncurses-dev pkg-config libusb-1.0-0-dev libfdt-dev python3-capstone \
  python3-setuptools python3-pyelftools \
  mmdebstrap e2fsprogs zstd \
  meson ninja-build python3-mako python3-yaml python3-packaging \
  libwayland-bin libwayland-dev libfreetype-dev
```

The last two lines are for mesa (`rootfs/mesa/build-mesa.sh`, cross-built with the same clang against the arm64
sysroot; the sysroot carries `libstdc++-14-dev` for mesa's C++ parts, and `libwayland-dev`,
`libwayland-egl-backend-dev`, `wayland-protocols` and `libglvnd-dev` for its Wayland platform and glvnd).
`libwayland-bin` brings `wayland-scanner`, which runs on the build machine; `libwayland-dev` its pkg-config file.
`libfreetype-dev` is for the host tests of the overlay text (`userspace/libh713osd`, `userspace/h713-osd`; the board gets FreeType
linked statically from the sysroot's own `libfreetype-dev`).

`python3-setuptools` is needed by U-Boot's in-tree `pylibfdt`; `mmdebstrap` and `e2fsprogs` build the
root filesystem and its ext4 images; `libusb-1.0-0-dev` builds `sunxi-fel`.

## LLVM 20 - not optional

Ubuntu 24.04 ships LLVM 18, and `llvm-objcopy` learned SREC output in 19. Without this step the U-Boot
build dies at `u-boot.srec`, which is a confusing place to find out:

```bash
podman exec -u root h713-build bash -c '
  curl -fsSL https://apt.llvm.org/llvm-snapshot.gpg.key -o /usr/share/keyrings/llvm.asc
  echo "deb [signed-by=/usr/share/keyrings/llvm.asc] http://apt.llvm.org/noble/ llvm-toolchain-noble-20 main" \
      > /etc/apt/sources.list.d/llvm20.list
  apt-get update -qq && apt-get install -y clang-20 lld-20 llvm-20
  for t in clang ld.lld llvm-objcopy llvm-ar llvm-nm llvm-objdump llvm-readelf llvm-strip; do
      ln -sf /usr/bin/$t-20 /usr/local/bin/$t; done'
```

Repeat this whenever you recreate the container. A fresh container has LLVM 18 again.

## Rust for the kernel

Only for kernels built with the developer fragment `KERNEL_CONFIG=rust` (CONFIG_RUST, [kernel-rust.md](kernel-rust.md));
the release build does not use it. Pinned: rustup-init 1.28.2 (checked against its SHA-256), the toolchain 1.89.0 with
`rust-src` (the kernel compiles `core` itself from it), `rustfmt` and `clippy`, and `bindgen-cli` 0.72.1 from crates.io
with its own `Cargo.lock`. rustc 1.89 is built on LLVM 20, the same major version as the clang above; bindgen loads that
clang's `libclang-20` at run time. Kernel 6.18 asks for rustc >= 1.78 and bindgen >= 0.65.1
(`scripts/min-tool-version.sh`). Everything goes into `/opt/rust`; the links in `/usr/local/bin` point at the toolchain's
own binaries, not at rustup's proxies, so the unprivileged build user needs no `RUSTUP_HOME`:

```bash
podman exec -u root h713-build bash -c '
  set -e
  export RUSTUP_HOME=/opt/rust/rustup CARGO_HOME=/opt/rust/cargo
  curl -fsSL https://static.rust-lang.org/rustup/archive/1.28.2/x86_64-unknown-linux-gnu/rustup-init -o /tmp/rustup-init
  echo "20a06e644b0d9bd2fbdbfd52d42540bdde820ea7df86e92e533c073da0cdd43c  /tmp/rustup-init" | sha256sum -c -
  chmod +x /tmp/rustup-init
  /tmp/rustup-init -y --no-modify-path --profile minimal --default-toolchain 1.89.0 -c rust-src,rustfmt,clippy
  rm /tmp/rustup-init
  /opt/rust/cargo/bin/cargo install --locked --root /opt/rust/cargo bindgen-cli --version 0.72.1
  tc=/opt/rust/rustup/toolchains/1.89.0-x86_64-unknown-linux-gnu/bin
  for t in rustc rustdoc rustfmt cargo clippy-driver; do ln -sf $tc/$t /usr/local/bin/$t; done
  ln -sf /opt/rust/cargo/bin/bindgen /usr/local/bin/bindgen
  chmod -R a+rX /opt/rust'
```

Check, in any prepared kernel tree: `make ARCH=arm64 LLVM=1 rustavailable` says `Rust is available!`. Without this
step a `KERNEL_CONFIG=rust` build stops after olddefconfig ("dropped what the fragments ask for: CONFIG_RUST=y").
With it, a build without the fragment gains only the informational `CONFIG_RUSTC_*` / `CONFIG_RUST_IS_AVAILABLE`
lines in its `.config`; no C source or C Makefile reads them (CONFIG_RUST stays off).

## Rust for h713-airplay (the desktop profile)

`--profile desktop` cross-builds the AirPlay receiver and presenter (`userspace/h713-airplay`, Rust; step 6e of
`release/build-all.sh`, 05.11.2026). It uses the toolchain of the section above and adds the board's target to it, once, as root:

```bash
podman exec -u root h713-build bash -c '
  export RUSTUP_HOME=/opt/rust/rustup CARGO_HOME=/opt/rust/cargo
  /opt/rust/cargo/bin/rustup target add --toolchain 1.89.0 aarch64-unknown-linux-gnu
  chmod -R a+rX /opt/rust'
```

Check: `podman exec h713-build bash -lc 'ls "$(rustc --print target-libdir --target aarch64-unknown-linux-gnu)"'` lists the target's
libraries. `release/build-all.sh` tests the same directory in its step 0 for a desktop build and stops there without it, not half an
hour later. Nothing else is installed for it: the container's clang links the two programs, with lld, against a sysroot of their own -
Debian 13's arm64 libraries (glibc 2.41, FFmpeg 7.1, ALSA, EGL/GLES, GBM, libva, Wayland, and `libgcc-14-dev` for the link), which
`userspace/h713-airplay/tools/make-sysroot.py` fetches from deb.debian.org and security.debian.org (each package checked against the
archive's SHA-256) into `mainline/build/sysroot-airplay-arm64/`, and fetches again only when that script changes. So the step needs the
network: for that sysroot, and for the crates of `Cargo.lock`, which cargo takes from crates.io into the build user's `~/.cargo` in the
container. The crate pins rustc 1.88.0 in its `rust-toolchain.toml` for a host with rustup; the container's `cargo` is the toolchain's
own binary, not rustup's proxy, and builds it with 1.89.0 (the workspace asks for 1.88 or newer).

## The OpenRISC compiler for crust

crust, the firmware of the SoC's small OR1K core ([ARISC](subsystems/arisc.md)), needs an `or1k-elf` GCC,
and Ubuntu does not package one. `release/build-all.sh` builds it the first time a board names a crust
(`CRUST_DEFCONFIG` in its `board.env`): `mainline/tools/or1k-toolchain/build-or1k-toolchain.sh` runs in
this container, fetches binutils 2.42 and gcc 13.3.0 from ftp.gnu.org, refuses them unless their SHA-256
match the pinned values, lets gcc's own `contrib/download_prerequisites` fetch GMP, MPFR, MPC and ISL
(checked against the SHA-512 list inside the pinned gcc tarball) and installs C and libgcc only into
`mainline/build/toolchain/or1k/`. About 6 minutes on 8 cores, once; after that the compiler is kept -
as long as its stamp `.h713-or1k-toolchain`, which the script writes last, names the pinned sources. An
unfinished build or a compiler copied in from elsewhere has no such stamp and is built again.
Nothing beyond the package list above is needed (bison brings `m4` for GMP). Without network, put the six
tarballs into `mainline/build/cache/or1k/` beforehand: a tarball already there is not fetched, only
checked. By hand:

```bash
podman exec h713-build /work/mainline/tools/or1k-toolchain/build-or1k-toolchain.sh
```

## Check it

```bash
podman exec h713-build bash -lc 'clang --version | head -1; command -v mmdebstrap mke2fs depmod dtc'
```

`release/build-all.sh` runs the same check as its step 0 and refuses to start if anything is missing.
It also starts the container for you if it exists but is stopped - after a reboot, `podman ps -a` shows
it as `Created`, which is normal.

## Building the root filesystem needs root inside the container

`mmdebstrap` runs as root there (`podman exec -u root`), which is why the build script has two exec
helpers. Files it writes under `installer/tmp/` end up owned by the container's root; the build script
creates that directory as you beforehand so later steps can still write next to them. If you ever have to
remove such a directory by hand: `podman unshare rm -rf <path>`.
