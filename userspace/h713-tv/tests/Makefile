# SPDX-License-Identifier: GPL-2.0
#
# The host tests of h713-tv: main.c compiled natively into each test, every libdrm and ALSA function stubbed with an
# abort() (the stubs are made from the object's undefined symbols; the tests call none of them). No device, no DRM, no
# capture: evaluate() itself is not run. color.c (the firmware's colour) and gamma.c (its gamma curve) are linked as objects
# into the tests that only need them to link, and compiled into test_color and test_gamma themselves, which reach their statics.
#
#   test_want   the want link and the straight ring's wait for the warp's claim (P3 of the media side project): what
#               want_hold() asks, h713-warp's side over a socketpair
#   test_edid   the EDID without Deep Colour: edid_strip_dc() on made-up EDIDs, with edid_prune() in both orders
#   test_nosig  the page without a signal (P5): what h713-osd is told, when the last picture stands for the page, the way back
#   test_hold   the wall held black over a restart of the picture path (TODO 2.96): the holder's file, the way out with and
#               without a holder, the start after it, the console's framebuffer written down; a page that goes before the ring
#   test_wall   the wall black between a client's release and the straight ring (TODO 2.124): one commit to black, the ring's
#               commit takes it, the console's framebuffer first when nothing comes, the black one never removed while shown
#   test_color  the firmware's white balance and colour management (bm-wb2): the registers a value gives, all six words every
#               time, the colour management as a step on the board's own value, the firmware that forgets, the slots, the file werte
#   test_gamma  the gamma curve and the colour temperature: the arithmetic of the display firmware's library against checksums
#               made by an independent description (gamma-vectors.txt), the file of raw curves, the two controls, the picture
#               mode's colour temperature, the file werte
#
#   make run SYSROOT=PATH   PATH: a board root with libdrm-dev and libasound2-dev, for their headers only (the build
#                           container has neither natively); release/build-all.sh makes one in mainline/build/sysroot-arm64
#   make clean

SYSROOT ?= /srv/h713-rootfs
CC      ?= cc
CFLAGS  ?= -O0 -g
CFLAGS  += -std=gnu11 -Wall -Wextra -Wno-format-truncation -Wno-unused-function
# gamma.c repeats the vendor library's arithmetic operation by operation: no multiply-add may be fused (the Makefile of the
# program says why); the tests are built the same way
CFLAGS  += -ffp-contract=off
INC      = -idirafter $(SYSROOT)/usr/include -idirafter $(SYSROOT)/usr/include/libdrm
TESTS    = test_want test_edid test_nosig test_hold test_wall test_color test_gamma

all: $(TESTS)

color.o: ../color.c ../color.h
	$(CC) $(CFLAGS) -c -o $@ ../color.c

gamma.o: ../gamma.c ../gamma.h ../color.h
	$(CC) $(CFLAGS) -c -o $@ ../gamma.c

test_want test_edid test_nosig test_hold test_wall: color.o gamma.o
test_color: gamma.o
test_gamma: color.o

$(TESTS): %: %.c ../main.c ../color.c ../color.h ../gamma.c ../gamma.h
	$(CC) $(CFLAGS) $(INC) -c -o $@.o $@.c
	{ echo '#include <stdlib.h>'; nm -u $@.o | awk '$$2 ~ /^(drm|snd)/ { print "void " $$2 "(void); void " $$2 "(void) { abort(); }" }'; } > $@-stubs.c
	$(CC) $(CFLAGS) -c -o $@-stubs.o $@-stubs.c
	$(CC) -o $@ $@.o $@-stubs.o $(if $(filter test_color,$@),,color.o) $(if $(filter test_gamma,$@),,gamma.o) -lm

run: $(TESTS)
	./test_want
	./test_edid
	./test_nosig
	./test_hold
	./test_wall
	./test_color
	./test_gamma

clean:
	rm -f $(TESTS) $(TESTS:%=%.o) $(TESTS:%=%-stubs.c) $(TESTS:%=%-stubs.o) stubs.c stubs.o

.PHONY: all run clean
