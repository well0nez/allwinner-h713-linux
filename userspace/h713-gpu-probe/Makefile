# SPDX-License-Identifier: GPL-2.0
#
# h713-gpu-probe -- the GPU foundation tool for keystone stages S1 and S2
# (umbau/plan/keystone/PLAN.md): GBM + EGL + GLES2 on the render node.
#
#   make cross           cross-build on the workstation with clang against the
#                        board root (SYSROOT) and the S0 mesa stage
#                        (MESA_PREFIX: headers in $(MESA_PREFIX)/include,
#                        libraries in $(MESA_PREFIX)/lib). The binary carries
#                        rpath /usr/local/lib, where that tree lives on the
#                        device. `make` alone does the same.
#   make host            build natively against the host's mesa: a syntax and
#                        logic check (HOST_CPPFLAGS / HOST_LDLIBS override
#                        the pkg-config lookup when the host has no -dev files)
#   make install-cross   install the CROSS-built binary (DESTDIR=...)
#   make clean
#
# The cross recipe is h713-autofocus'/h713-tv's: the build container does not
# see the board root, so the cross build runs on the host with clang, reading
# only. There is no native target for the board: it has no compiler.
# CRC32 is zlib's (zlib1g-dev in the sysroot, zlib1g on the device).

CFLAGS      ?= -O2 -g
CFLAGS      += -std=c11 -Wall -Wextra -Wshadow -Wvla
LIBS         = -lgbm -lEGL -lGLESv2 -lz

PREFIX      ?= /usr/local
BINDIR      ?= $(PREFIX)/bin

SYSROOT     ?= /srv/h713-rootfs
MESA_PREFIX ?= $(CURDIR)/../../mainline/build/mesa-stage/usr/local
TARGET      ?= aarch64-linux-gnu
CROSS_CC    ?= clang

HOST_CC       ?= cc
HOST_CPPFLAGS ?= $(shell pkg-config --cflags gbm egl glesv2 zlib 2>/dev/null)
HOST_LDLIBS   ?= $(shell pkg-config --libs gbm egl glesv2 zlib 2>/dev/null || echo "$(LIBS)")

cross: h713-gpu-probe.$(TARGET)

h713-gpu-probe.$(TARGET): probe.c
	$(CROSS_CC) --target=$(TARGET) --sysroot=$(SYSROOT) -fuse-ld=lld \
	    $(CFLAGS) $(LDFLAGS) -I$(MESA_PREFIX)/include \
	    -L$(MESA_PREFIX)/lib -L$(SYSROOT)/usr/lib/$(TARGET) \
	    -Wl,-rpath,/usr/local/lib -o $@ $< $(LIBS)

host: h713-gpu-probe

h713-gpu-probe: probe.c
	$(HOST_CC) $(HOST_CPPFLAGS) $(CFLAGS) $(LDFLAGS) -o $@ $< $(HOST_LDLIBS)

# From the workstation: put the cross-built arm64 program into the board root
# (DESTDIR=/srv/h713-rootfs) or a staging tree for scp.
install-cross: h713-gpu-probe.$(TARGET)
	install -D -m 0755 h713-gpu-probe.$(TARGET) \
	    $(DESTDIR)$(BINDIR)/h713-gpu-probe

clean:
	rm -f h713-gpu-probe h713-gpu-probe.$(TARGET)

.PHONY: cross host install-cross clean
