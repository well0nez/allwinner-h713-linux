# SPDX-License-Identifier: GPL-2.0
#
# libh713osd -- the overlay pictures (osd.c): a static library for h713-osd and, later, a desktop.
#
#   make cross          libh713osd.$(TARGET).a and the test tool osd-show.$(TARGET) for the board, with clang
#                       against the board root (SYSROOT), as h713-warp and h713-autofocus are built; `make` alone
#                       does the same. osd-show puts one overlay on the panel through h713-tv (osd-show.c)
#   make host           osd-mockup for the host (in the container h713-build)
#   make test           test-text and test-menu for the host: the text, the launcher's bands (OSD_TEST_FONT=..., else OSD_FONT;
#                       without a font: skipped)
#   make mockup DIR=... every place, look and case, and the launcher, as a PAM picture (osd-mockup.c; OSD_FONT=... for the
#                       launcher), to choose a look
#   make clean
#
# libc and libm for the shapes - no DRM, no files; the text (text.c) is FreeType's and wants a font file the caller opens.
# FreeType comes from FT (default SYSROOT: libfreetype-dev there, and its png/bz2/brotli/zlib, linked statically so that
# nothing but the font file is needed on the board) and, for the host, from pkg-config. osd.c draws the menu's rows
# and hint with it, so every program that links osd.c links text.c and FreeType.
CFLAGS  ?= -O2 -g
CFLAGS  += -std=gnu11 -Wall -Wextra -Wshadow -Wvla
SYSROOT ?= /srv/h713-rootfs
FT      ?= $(SYSROOT)
FT_INC  = -isystem $(FT)/usr/include/freetype2
FT_LIBS = -L$(FT)/usr/lib/aarch64-linux-gnu -Wl,-Bstatic -lfreetype -lpng16 -lbz2 -lbrotlidec -lbrotlicommon -lz -Wl,-Bdynamic
TARGET  ?= aarch64-linux-gnu
CROSS_CC ?= clang
HOST_CC ?= cc
REPRO_CFLAGS = -ffile-prefix-map=$(abspath .)=. -ffile-prefix-map=$(abspath $(SYSROOT))=/sysroot

cross: libh713osd.$(TARGET).a osd-show.$(TARGET)

libh713osd.$(TARGET).a: osd.c text.c osd.h
	$(CROSS_CC) --target=$(TARGET) --sysroot=$(SYSROOT) $(CFLAGS) $(REPRO_CFLAGS) -c osd.c -o osd.$(TARGET).o
	$(CROSS_CC) --target=$(TARGET) --sysroot=$(SYSROOT) $(CFLAGS) $(REPRO_CFLAGS) $(FT_INC) -c text.c -o text.$(TARGET).o
	llvm-ar rcs $@ osd.$(TARGET).o text.$(TARGET).o

osd-show.$(TARGET): osd-show.c osd.c text.c osd.h
	$(CROSS_CC) --target=$(TARGET) --sysroot=$(SYSROOT) -fuse-ld=lld $(CFLAGS) $(REPRO_CFLAGS) $(FT_INC) \
	    -o $@ osd-show.c osd.c text.c $(FT_LIBS) -lm

host: osd-mockup test-text test-menu

test-text: test-text.c text.c osd.c osd.h
	$(HOST_CC) $(CFLAGS) $$(pkg-config --cflags freetype2) -o $@ test-text.c text.c osd.c $$(pkg-config --libs freetype2) -lm

test-menu: test-menu.c text.c osd.c osd.h
	$(HOST_CC) $(CFLAGS) $$(pkg-config --cflags freetype2) -o $@ test-menu.c text.c osd.c $$(pkg-config --libs freetype2) -lm

test: test-text test-menu
	./test-text || [ $$? -eq 77 ]
	./test-menu || [ $$? -eq 77 ]

osd-mockup: osd-mockup.c osd.c text.c osd.h
	$(HOST_CC) $(CFLAGS) $$(pkg-config --cflags freetype2) -o $@ osd-mockup.c osd.c text.c $$(pkg-config --libs freetype2) -lm

mockup: osd-mockup
	mkdir -p $(DIR) && ./osd-mockup $(DIR)

clean:
	rm -f *.o *.a osd-mockup test-text test-menu osd-show.$(TARGET)

.PHONY: cross host test mockup clean
