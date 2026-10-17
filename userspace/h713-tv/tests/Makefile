# SPDX-License-Identifier: GPL-2.0
#
# The host test of h713-tv's want link and of the straight ring's wait for the warp's claim (P3 of the media side
# project): main.c compiled natively into the test, every libdrm and ALSA function stubbed with an abort() (the stubs
# are made from the object's undefined symbols; the test calls none of them), h713-warp's side over a socketpair. No
# device, no DRM, no capture: evaluate() itself is not run - what it asks (want_hold()) is.
#
#   make run SYSROOT=PATH   PATH: a board root with libdrm-dev and libasound2-dev, for their headers only (the build
#                           container has neither natively); release/build-all.sh makes one in mainline/build/sysroot-arm64
#   make clean

SYSROOT ?= /srv/h713-rootfs
CC      ?= cc
CFLAGS  ?= -O0 -g
CFLAGS  += -std=gnu11 -Wall -Wextra -Wno-format-truncation -Wno-unused-function
INC      = -idirafter $(SYSROOT)/usr/include -idirafter $(SYSROOT)/usr/include/libdrm

all: test_want

test_want: test_want.c ../main.c
	$(CC) $(CFLAGS) $(INC) -c -o test_want.o test_want.c
	{ echo '#include <stdlib.h>'; nm -u test_want.o | awk '$$2 ~ /^(drm|snd)/ { print "void " $$2 "(void); void " $$2 "(void) { abort(); }" }'; } > stubs.c
	$(CC) $(CFLAGS) -c -o stubs.o stubs.c
	$(CC) -o $@ test_want.o stubs.o

run: test_want
	./test_want

clean:
	rm -f test_want test_want.o stubs.c stubs.o

.PHONY: all run clean
