# SPDX-License-Identifier: GPL-2.0
#
# The host test of h713-warp (AP2d test plan T1a, T1b): the shaders. It needs
# no device, no dma-buf and no h713-tv, but a GLES driver of any kind
# (llvmpipe, Intel, AMD, or panfrost when this is run on the board). The matrix
# and warp.conf tests (T2, T3) moved with the code to ../../libh713geom/tests.
#
#   make run     build and run it
#   make clean
#
# On a host without the EGL/GLES development files, point CPPFLAGS at the mesa
# 25.0.7 headers that were unpacked for the build (this is how Claude runs it,
# from working journal `KS4/tests`):
#
#   make run HOST_CPPFLAGS="-I../tmp/hostinc -I/usr/include/drm" \
#            HOST_LDLIBS="-l:libEGL.so.1 -l:libGLESv2.so.2"
#
# (-I/usr/include/drm is only for drm_fourcc.h, the one uapi header gl.c needs;
# on a host with libdrm-dev it is -I/usr/include/libdrm instead.)

CFLAGS        ?= -O2 -g
CFLAGS        += -std=c11 -Wall -Wextra -Wshadow -Wvla
HOST_CC       ?= cc
HOST_CPPFLAGS ?= $(shell pkg-config --cflags egl glesv2 2>/dev/null)
HOST_LDLIBS   ?= $(shell pkg-config --libs egl glesv2 2>/dev/null || echo "-lEGL -lGLESv2")
WARP           = ..
GEOM           = ../../libh713geom

all: test_wayland server_stub test_peer

test_gl: test_gl.c $(WARP)/gl.c $(GEOM)/matrix.c $(WARP)/warp.h $(GEOM)/geom.h
	$(HOST_CC) $(HOST_CPPFLAGS) $(CFLAGS) -I$(GEOM) $(LDFLAGS) -o $@ test_gl.c \
	    $(WARP)/gl.c $(GEOM)/matrix.c $(HOST_LDLIBS) -lm

# The Wayland server against a client: wayland.c with the GPU and the loop stubbed. Needs only
# libwayland-dev and the protocol code the parent Makefile generates into ../gen ("make test" there).
WL_CFLAGS = -I$(WARP) -I$(WARP)/gen -I$(GEOM) -I/usr/include/drm -I/usr/include/libdrm
PROTO_C   = $(wildcard $(WARP)/gen/*-protocol.c)

server_stub: server_stub.c $(WARP)/wayland.c $(WARP)/warp.h $(PROTO_C)
	$(HOST_CC) $(CFLAGS) $(WL_CFLAGS) $(LDFLAGS) -o $@ server_stub.c $(WARP)/wayland.c $(PROTO_C) -lwayland-server

# The peer link to h713-tv (peer.c) against a scripted h713-tv: claim, frames, "warp switch", the unasked "note source".
test_peer: test_peer.c $(WARP)/peer.c $(WARP)/warp.h
	$(HOST_CC) $(CFLAGS) -I$(WARP) -I$(GEOM) $(LDFLAGS) -o $@ test_peer.c $(WARP)/peer.c

test_wayland: test_wayland.c $(PROTO_C)
	$(HOST_CC) $(CFLAGS) $(WL_CFLAGS) $(LDFLAGS) -o $@ test_wayland.c $(PROTO_C) -lwayland-client

# T1a/T1b need EGL/GLES development files and a GLES driver: neither is in the build container, so they are
# built only where pkg-config finds egl (they are not run in the container)
run: all
	@./test_wayland ./server_stub
	@./test_peer
	@if pkg-config --exists egl glesv2 2>/dev/null || [ -n "$(HOST_LDLIBS_GL)" ]; then \
	   $(MAKE) test_gl && { ./test_gl; rc=$$?; test $$rc -ne 77 || echo "     (T1a/T1b skipped)"; \
	   test $$rc -eq 0 -o $$rc -eq 77; }; \
	 else echo "     (T1a/T1b not built: no EGL/GLES development files here)"; fi

clean:
	rm -f test_gl test_wayland server_stub test_peer

.PHONY: all run clean
