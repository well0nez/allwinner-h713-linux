# SPDX-License-Identifier: GPL-2.0
#
# The host tests of h713-warp (AP2d test plan T1a, T1b, T2). None of them
# needs a device, a dma-buf or h713-tv; T1a and T1b need a GLES driver of any
# kind (llvmpipe, Intel, AMD, or panfrost when this is run on the board).
#
#   make run     build and run all three
#   make clean
#
# On a host without the EGL/GLES development files, point CPPFLAGS at the mesa
# 25.0.7 headers that were unpacked for the build (this is how Claude runs it,
# from umbau/work/KS4/tests):
#
#   make run HOST_CPPFLAGS="-I../tmp/hostinc -I/usr/include/drm" \
#            HOST_LDLIBS="-l:libEGL.so.1 -l:libGLESv2.so.2"
#
# (-I/usr/include/drm is only for drm_fourcc.h, the one uapi header gl.c needs;
# on a host with libdrm-dev it is -I/usr/include/libdrm instead.)
#
# T2 reads its vectors from the AP2f reference model, which is why python3 is
# in the loop: matrix_ref.py imports umbau/work/AP2f/model/keystone_matrix.py
# and prints what h713-warp/matrix.c has to reproduce.

CFLAGS        ?= -O2 -g
CFLAGS        += -std=c11 -Wall -Wextra -Wshadow -Wvla
HOST_CC       ?= cc
HOST_CPPFLAGS ?= $(shell pkg-config --cflags egl glesv2 2>/dev/null)
HOST_LDLIBS   ?= $(shell pkg-config --libs egl glesv2 2>/dev/null || echo "-lEGL -lGLESv2")
PYTHON        ?= python3
WARP           = ..

all: test_matrix test_gl

test_matrix: test_matrix.c $(WARP)/matrix.c $(WARP)/warp.h
	$(HOST_CC) $(HOST_CPPFLAGS) $(CFLAGS) $(LDFLAGS) -o $@ test_matrix.c \
	    $(WARP)/matrix.c -lm

test_gl: test_gl.c $(WARP)/gl.c $(WARP)/matrix.c $(WARP)/warp.h
	$(HOST_CC) $(HOST_CPPFLAGS) $(CFLAGS) $(LDFLAGS) -o $@ test_gl.c \
	    $(WARP)/gl.c $(WARP)/matrix.c $(HOST_LDLIBS) -lm

run: all
	@$(PYTHON) matrix_ref.py > vectors.txt
	@./test_matrix < vectors.txt
	@./test_gl; rc=$$?; test $$rc -ne 77 || echo "     (T1a/T1b skipped)"; \
	 test $$rc -eq 0 -o $$rc -eq 77

clean:
	rm -f test_matrix test_gl vectors.txt

.PHONY: all run clean
