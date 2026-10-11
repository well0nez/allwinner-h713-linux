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

all: test_gl

test_gl: test_gl.c $(WARP)/gl.c $(GEOM)/matrix.c $(WARP)/warp.h $(GEOM)/geom.h
	$(HOST_CC) $(HOST_CPPFLAGS) $(CFLAGS) -I$(GEOM) $(LDFLAGS) -o $@ test_gl.c \
	    $(WARP)/gl.c $(GEOM)/matrix.c $(HOST_LDLIBS) -lm

run: all
	@./test_gl; rc=$$?; test $$rc -ne 77 || echo "     (T1a/T1b skipped)"; \
	 test $$rc -eq 0 -o $$rc -eq 77

clean:
	rm -f test_gl

.PHONY: all run clean
