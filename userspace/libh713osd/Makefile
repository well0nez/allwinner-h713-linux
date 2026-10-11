# SPDX-License-Identifier: GPL-2.0
#
# libh713osd -- the overlay pictures (osd.c): a static library for h713-osd and, later, a desktop.
#
#   make cross          libh713osd.$(TARGET).a and the test tool osd-show.$(TARGET) for the board, with clang
#                       against the board root (SYSROOT), as h713-warp and h713-autofocus are built; `make` alone
#                       does the same. osd-show puts one overlay on the panel through h713-tv (osd-show.c)
#   make host           osd-mockup for the host (in the container h713-build)
#   make mockup DIR=... every place, look and case as a PAM picture (osd-mockup.c), to choose a look
#   make clean
#
# Only libc and libm: no DRM, no fonts, no files - the library draws, the caller decides where it goes.
CFLAGS  ?= -O2 -g
CFLAGS  += -std=gnu11 -Wall -Wextra -Wshadow -Wvla
SYSROOT ?= /srv/h713-rootfs
TARGET  ?= aarch64-linux-gnu
CROSS_CC ?= clang
HOST_CC ?= cc
REPRO_CFLAGS = -ffile-prefix-map=$(abspath .)=. -ffile-prefix-map=$(abspath $(SYSROOT))=/sysroot

cross: libh713osd.$(TARGET).a osd-show.$(TARGET)

libh713osd.$(TARGET).a: osd.c osd.h
	$(CROSS_CC) --target=$(TARGET) --sysroot=$(SYSROOT) $(CFLAGS) $(REPRO_CFLAGS) -c osd.c -o osd.$(TARGET).o
	llvm-ar rcs $@ osd.$(TARGET).o

osd-show.$(TARGET): osd-show.c osd.c osd.h
	$(CROSS_CC) --target=$(TARGET) --sysroot=$(SYSROOT) -fuse-ld=lld $(CFLAGS) $(REPRO_CFLAGS) \
	    -o $@ osd-show.c osd.c -lm

host: osd-mockup

osd-mockup: osd-mockup.c osd.c osd.h
	$(HOST_CC) $(CFLAGS) -o $@ osd-mockup.c osd.c -lm

mockup: osd-mockup
	mkdir -p $(DIR) && ./osd-mockup $(DIR)

clean:
	rm -f *.o *.a osd-mockup osd-show.$(TARGET)

.PHONY: cross host mockup clean
