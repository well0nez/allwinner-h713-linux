# SPDX-License-Identifier: GPL-3.0-only
#
# h713-airplay (README.md)
#
#   make sysroot        tools/make-sysroot.py: the board's libraries and headers (Debian 13 arm64) in SYSROOT
#   make cross          both programs for the board, linked against SYSROOT:
#                       h713-airplay.aarch64-linux-gnu, h713-airplay-show.aarch64-linux-gnu
#   make test           the host tests of every crate
#   make notices        THIRD-PARTY.md: the crates linked into the two programs and their licences
#   make install-cross  install the cross-built programs (DESTDIR=...)
#   make clean

SYSROOT ?= /srv/h713/sysroot-trixie-arm64
TARGET  ?= aarch64-unknown-linux-gnu
PREFIX  ?= /usr/local
BINDIR  ?= $(PREFIX)/bin
CARGO   ?= cargo

export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER ?= aarch64-linux-gnu-gcc
export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_RUSTFLAGS ?= -C link-arg=--sysroot=$(SYSROOT)

OUT = target/$(TARGET)/release

.PHONY: cross test sysroot notices install-cross clean

cross:
	$(CARGO) build --release --locked --target $(TARGET) --workspace
	cp $(OUT)/h713-airplay h713-airplay.aarch64-linux-gnu
	cp $(OUT)/h713-airplay-show h713-airplay-show.aarch64-linux-gnu

test:
	$(CARGO) test --locked --workspace

sysroot:
	tools/make-sysroot.py $(SYSROOT)

notices:
	tools/third-party.py

install-cross:
	install -D -m 0755 h713-airplay.aarch64-linux-gnu $(DESTDIR)$(BINDIR)/h713-airplay
	install -D -m 0755 h713-airplay-show.aarch64-linux-gnu $(DESTDIR)$(BINDIR)/h713-airplay-show

clean:
	$(CARGO) clean
	rm -f h713-airplay.aarch64-linux-gnu h713-airplay-show.aarch64-linux-gnu
