# SPDX-License-Identifier: GPL-2.0
#
# h713-tv -- the HDMI input on the video plane, the console on signal loss.
#
#   make                 build natively (on the board: gcc-14, pkg-config,
#                        libdrm, libasound2-dev -- the audio part speaks the
#                        ALSA control API)
#   make cross           cross-build on the workstation against the board root
#   make install         install the NATIVE binary (on the board)
#   make install-cross   install the CROSS-built binary (from the
#                        workstation, with DESTDIR=/srv/h713-rootfs)
#   make test            the host test of the want link (tests/, SYSROOT=
#                        a board root, for the libdrm and ALSA headers)
#   make clean
#
# The kernel is built through build/build.sh in the container and nowhere
# else (doku/78 rule 2). This program is userspace: the container does not
# see the board root (it has only /opt/Projekte/h713 -> /work, checked again
# with `podman inspect h713-build` on 07.09.: exactly one mount, /srv is
# empty inside the container) and has neither libdrm nor an arm64 sysroot,
# so `cross` builds with the host clang against /srv/h713-rootfs -- reading
# only. The reasoning is in the README.

CC        ?= cc
PKG_CONFIG ?= pkg-config
CFLAGS    ?= -O2 -g
CFLAGS    += -Wall -Wextra -Wshadow -Wvla
CPPFLAGS  += $(shell $(PKG_CONFIG) --cflags libdrm alsa)
LDLIBS    += $(shell $(PKG_CONFIG) --libs libdrm alsa)

PREFIX    ?= /usr/local
SBINDIR   ?= $(PREFIX)/sbin
UNITDIR   ?= /etc/systemd/system
UDEVDIR   ?= /etc/udev/rules.d
DOCDIR    ?= $(PREFIX)/share/doc/h713-tv
DATADIR   ?= $(PREFIX)/share/h713-tv

# Cross-build: the board root as the sysroot, the host clang as the cross
# compiler. Headers and linker names (libdrm-dev, libasound2-dev) have to be
# installed in the board root -- `apt install libasound2-dev` on the board,
# the root is the same one.
SYSROOT   ?= /srv/h713-rootfs
TARGET    ?= aarch64-linux-gnu
CROSS_CC  ?= clang

# main.c is the program; color.c is the display firmware's white balance and colour management (interface: color.h)
SRCS      = main.c color.c

all: h713-tv

h713-tv: $(SRCS) color.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) -o $@ $(SRCS) $(LDLIBS)

cross: h713-tv.$(TARGET)

# The cross build is part of a reproducible image: the absolute paths of this
# directory and of the sysroot must not end up in the DWARF info (-g), or two
# clones of the same commit give two different binaries (E1 of v0.96-beta).
REPRO_CFLAGS = -ffile-prefix-map=$(abspath .)=. -ffile-prefix-map=$(abspath $(SYSROOT))=/sysroot

h713-tv.$(TARGET): $(SRCS) color.h
	$(CROSS_CC) --target=$(TARGET) --sysroot=$(SYSROOT) -fuse-ld=lld \
	    $(CFLAGS) $(REPRO_CFLAGS) $(LDFLAGS) -isystem $(SYSROOT)/usr/include/libdrm \
	    -L$(SYSROOT)/usr/lib/$(TARGET) -o $@ $(SRCS) -ldrm -lasound

install: h713-tv
	install -D -m 0755 h713-tv $(DESTDIR)$(SBINDIR)/h713-tv
	$(MAKE) install-data

# From the workstation: put the cross-built arm64 program into the board
# root. `install` would put the x86 binary there -- hence a target of its
# own instead of a footnote.
install-cross: h713-tv.$(TARGET)
	install -D -m 0755 h713-tv.$(TARGET) $(DESTDIR)$(SBINDIR)/h713-tv
	$(MAKE) install-data

install-data:
	install -D -m 0644 h713-tv@.service $(DESTDIR)$(UNITDIR)/h713-tv@.service
	rm -f $(DESTDIR)$(UNITDIR)/h713-tv.service
	install -D -m 0644 99-h713-tv.rules $(DESTDIR)$(UDEVDIR)/99-h713-tv.rules
	install -D -m 0644 README.md $(DESTDIR)$(DOCDIR)/README.md
	install -D -m 0644 gamma-standard.bin $(DESTDIR)$(DATADIR)/gamma-standard.bin

# the host test of the want link and the straight ring's wait (tests/Makefile): needs only the board root's headers
test:
	$(MAKE) -C tests run SYSROOT=$(SYSROOT)

clean:
	rm -f h713-tv h713-tv.$(TARGET)
	$(MAKE) -C tests clean

.PHONY: all cross install install-cross install-data test clean
