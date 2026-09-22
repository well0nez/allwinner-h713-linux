# SPDX-License-Identifier: GPL-2.0
#
# h713-afmetric -- the C helper beside h713-autofocus. The tool itself is
# Python and needs no build; this is only the metric, the one part of a pass
# that is ours rather than the motor's or the camera's.
#
#   make                 build natively (on the board, or on the host for the
#                        golden test, which compiles it the same way)
#   make cross           cross-build on the workstation against the board root
#   make install         install the NATIVE binary (on the board)
#   make install-cross   install the CROSS-built binary (from the workstation,
#                        with DESTDIR=/srv/h713-rootfs)
#   make clean
#
# The cross recipe is h713-tv's, for its reasons (see that Makefile): the build
# container sees only /opt/Projekte/h713, so a cross build happens on the host
# with clang against the board root, read-only. This one needs no library at
# all, so it has no pkg-config line and no -l.

CC        ?= cc
CFLAGS    ?= -O2 -g
CFLAGS    += -Wall -Wextra -Wshadow -Wvla

PREFIX    ?= /usr/local
BINDIR    ?= $(PREFIX)/bin

SYSROOT   ?= /srv/h713-rootfs
TARGET    ?= aarch64-linux-gnu
CROSS_CC  ?= clang

all: h713-afmetric

h713-afmetric: afmetric.c
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) -o $@ $<

cross: h713-afmetric.$(TARGET)

h713-afmetric.$(TARGET): afmetric.c
	$(CROSS_CC) --target=$(TARGET) --sysroot=$(SYSROOT) -fuse-ld=lld \
	    $(CFLAGS) $(LDFLAGS) -o $@ $<

install: h713-afmetric
	install -D -m 0755 h713-afmetric $(DESTDIR)$(BINDIR)/h713-afmetric

# From the workstation: put the cross-built arm64 program into the board root.
# `install` would put the x86 one there -- hence a target of its own.
install-cross: h713-afmetric.$(TARGET)
	install -D -m 0755 h713-afmetric.$(TARGET) \
	    $(DESTDIR)$(BINDIR)/h713-afmetric

clean:
	rm -f h713-afmetric h713-afmetric.$(TARGET)

.PHONY: all cross install install-cross clean
