# SPDX-License-Identifier: GPL-2.0
#
# The host tests of h713-tv: main.c compiled natively into each test, every libdrm and ALSA function stubbed with an
# abort() (the stubs are made from the object's undefined symbols; the tests call none of them). No device, no DRM, no
# capture: evaluate() itself is not run.
#
#   test_want   the want link and the straight ring's wait for the warp's claim (P3 of the media side project): what
#               want_hold() asks, h713-warp's side over a socketpair
#   test_edid   the EDID without Deep Colour: edid_strip_dc() on made-up EDIDs, with edid_prune() in both orders
#   test_nosig  the page without a signal (P5): what h713-osd is told, when the last picture stands for the page, the way back
#
#   make run SYSROOT=PATH   PATH: a board root with libdrm-dev and libasound2-dev, for their headers only (the build
#                           container has neither natively); release/build-all.sh makes one in mainline/build/sysroot-arm64
#   make clean

SYSROOT ?= /srv/h713-rootfs
CC      ?= cc
CFLAGS  ?= -O0 -g
CFLAGS  += -std=gnu11 -Wall -Wextra -Wno-format-truncation -Wno-unused-function
INC      = -idirafter $(SYSROOT)/usr/include -idirafter $(SYSROOT)/usr/include/libdrm
TESTS    = test_want test_edid test_nosig

all: $(TESTS)

$(TESTS): %: %.c ../main.c
	$(CC) $(CFLAGS) $(INC) -c -o $@.o $<
	{ echo '#include <stdlib.h>'; nm -u $@.o | awk '$$2 ~ /^(drm|snd)/ { print "void " $$2 "(void); void " $$2 "(void) { abort(); }" }'; } > $@-stubs.c
	$(CC) $(CFLAGS) -c -o $@-stubs.o $@-stubs.c
	$(CC) -o $@ $@.o $@-stubs.o

run: $(TESTS)
	./test_want
	./test_edid
	./test_nosig

clean:
	rm -f $(TESTS) $(TESTS:%=%.o) $(TESTS:%=%-stubs.c) $(TESTS:%=%-stubs.o) stubs.c stubs.o

.PHONY: all run clean
