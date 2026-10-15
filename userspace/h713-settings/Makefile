# SPDX-License-Identifier: GPL-2.0
#
# h713-settings -- the settings page of the box (README.md). Six C files plus libh713osd (the shapes' library, and
# its text: FreeType's).
#
#   make host           h713-settings for the host (in the container h713-build), for the tests
#   make test           the host tests (tests/test_settings.py: fake h713-tv and h713-warp, stand-in tools)
#   make cross          the board's binary, with clang against the board root (SYSROOT), FreeType (FT) linked in
#   make clean
#
# OSD is where libh713osd lives (osd.c, text.c, osd.h); FT_CFLAGS/FT_LIBS name FreeType.
CFLAGS  ?= -O2 -g
CFLAGS  += -std=gnu11 -Wall -Wextra -Wshadow -Wvla
OSD      = ../libh713osd
SRC      = main.c ui.c rows.c backend.c input.c page.c $(OSD)/osd.c $(OSD)/text.c
HDR      = settings.h ui.h $(OSD)/osd.h
INC      = -I$(OSD)
HOST_CC ?= cc
FT_CFLAGS ?= $(shell pkg-config --cflags freetype2)
FT_LIBS   ?= $(shell pkg-config --libs freetype2)
SYSROOT ?= /srv/h713-rootfs
FT      ?= $(SYSROOT)
TARGET  ?= aarch64-linux-gnu
CROSS_CC ?= clang
REPRO_CFLAGS = -ffile-prefix-map=$(abspath .)=. -ffile-prefix-map=$(abspath ..)=.. \
               -ffile-prefix-map=$(abspath $(SYSROOT))=/sysroot
# FreeType and what it needs are linked statically (as h713-osd's text is): the base image carries no FreeType package
STATIC  = -Wl,-Bstatic -lfreetype -lpng16 -lbz2 -lbrotlidec -lbrotlicommon -lz -Wl,-Bdynamic

cross: h713-settings.$(TARGET)

h713-settings.$(TARGET): $(SRC) $(HDR)
	$(CROSS_CC) --target=$(TARGET) --sysroot=$(SYSROOT) -fuse-ld=lld $(CFLAGS) $(REPRO_CFLAGS) $(INC) \
	    -isystem $(FT)/usr/include/freetype2 -o $@ $(SRC) -L$(FT)/usr/lib/$(TARGET) $(STATIC) -lm

host: h713-settings

h713-settings: $(SRC) $(HDR)
	$(HOST_CC) $(CFLAGS) $(INC) $(FT_CFLAGS) -o $@ $(SRC) $(FT_LIBS) -lm

test: h713-settings
	python3 -m unittest discover -s tests -v

clean:
	rm -f h713-settings h713-settings.aarch64-linux-gnu

.PHONY: host cross test clean
