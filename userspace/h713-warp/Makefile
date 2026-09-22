# SPDX-License-Identifier: GPL-2.0
#
# h713-warp -- the keystone warp daemon (plan stage S5).
#
#   make cross          cross-build for the board with clang against the board
#                       root (SYSROOT) and the S0 mesa stage (MESA_PREFIX:
#                       headers in $(MESA_PREFIX)/include, libraries in
#                       $(MESA_PREFIX)/lib). The binary carries rpath
#                       /usr/local/lib, where that tree lives on the device.
#                       `make` alone does the same.
#   make host           build natively against the host's mesa: a syntax and
#                       logic check. HOST_CPPFLAGS / HOST_LDLIBS override the
#                       pkg-config lookup when the host has no -dev files, e.g.
#                         make host HOST_CPPFLAGS="-I../tmp/hostinc -I/usr/include/drm" \
#                                   HOST_LDLIBS="-l:libEGL.so.1 -l:libGLESv2.so.2"
#   make test           build and run the host tests of ../tests (T1a, T1b, T2)
#   make install-cross  install the CROSS-built binary (DESTDIR=...)
#   make clean
#
# The cross recipe is h713-autofocus'/h713-gpu-probe's: the build container
# does not see the board root, so the cross build runs on the host with clang,
# reading only. There is no native target for the board: it has no compiler.
#
# NO -ldrm AND NO -lgbm, on purpose. h713-warp calls not one libdrm function:
# h713-tv owns card1 and does every commit, and the dma-bufs arrive as file
# descriptors (SCM_RIGHTS from h713-tv, VIDIOC_EXPBUF from the capture). All
# that is needed of libdrm is the uapi header drm_fourcc.h for the four
# fourccs. GBM is not needed either: the render node is taken through
# EGL_EXT_platform_device, and where that is absent through
# EGL_PLATFORM_SURFACELESS_MESA (gl.c). h713-gpu-probe used GBM because it also
# held a KMS node.

CFLAGS      ?= -O2 -g
CFLAGS      += -std=c11 -Wall -Wextra -Wshadow -Wvla
LIBS         = -lEGL -lGLESv2 -lm

PREFIX      ?= /usr/local
BINDIR      ?= $(PREFIX)/bin
UNITDIR     ?= /etc/systemd/system

SYSROOT     ?= /srv/h713-rootfs
MESA_PREFIX ?= $(CURDIR)/../../../src/mainline/build/mesa-stage/usr/local
TARGET      ?= aarch64-linux-gnu
CROSS_CC    ?= clang

HOST_CC       ?= cc
HOST_CPPFLAGS ?= $(shell pkg-config --cflags egl glesv2 libdrm 2>/dev/null)
HOST_LDLIBS   ?= $(shell pkg-config --libs egl glesv2 2>/dev/null || echo "$(LIBS)")

SRC = main.c config.c ctl.c peer.c capture.c gl.c matrix.c loop.c
HDR = warp.h

cross: h713-warp.$(TARGET)

h713-warp.$(TARGET): $(SRC) $(HDR)
	$(CROSS_CC) --target=$(TARGET) --sysroot=$(SYSROOT) -fuse-ld=lld \
	    $(CFLAGS) $(LDFLAGS) -I$(MESA_PREFIX)/include \
	    -I$(SYSROOT)/usr/include/libdrm \
	    -L$(MESA_PREFIX)/lib -L$(SYSROOT)/usr/lib/$(TARGET) \
	    -Wl,-rpath,/usr/local/lib -o $@ $(SRC) $(LIBS)

host: h713-warp

h713-warp: $(SRC) $(HDR)
	$(HOST_CC) $(HOST_CPPFLAGS) $(CFLAGS) $(LDFLAGS) -o $@ $(SRC) $(HOST_LDLIBS) -lm

test:
	$(MAKE) -C ../tests HOST_CPPFLAGS="$(HOST_CPPFLAGS)" HOST_LDLIBS="$(HOST_LDLIBS)" run

install-cross: h713-warp.$(TARGET)
	install -D -m 0755 h713-warp.$(TARGET) $(DESTDIR)$(BINDIR)/h713-warp
	install -D -m 0644 h713-warp.service $(DESTDIR)$(UNITDIR)/h713-warp.service
	install -D -m 0644 warp.conf.example $(DESTDIR)/usr/local/share/h713-warp/warp.conf.example

clean:
	rm -f h713-warp h713-warp.$(TARGET)
	$(MAKE) -C ../tests clean

.PHONY: cross host test install-cross clean
