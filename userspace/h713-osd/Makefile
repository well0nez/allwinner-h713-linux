# SPDX-License-Identifier: GPL-2.0
#
# h713-osd -- the overlays over the picture (README.md). One C file plus the two libraries, compiled in:
# ../libh713osd (the drawing, and the text: FreeType, linked statically for the board - the base image has no FreeType
# package, only the `desktop` profile has the font) and ../libh713geom (the keystone matrix, warp.conf, the way back).
#
#   make cross          h713-osd.$(TARGET) for the board, with clang against the board root (SYSROOT; FT = where libfreetype-dev
#                       and its static libraries are, default SYSROOT), as
#                       h713-tv and h713-warp are built; `make` alone does the same
#   make host           h713-osd for the host (in the container h713-build), for the tests
#   make test           the host tests (tests/test_osd.py: a fake h713-tv, memfds instead of dma-bufs)
#   make install DESTDIR=...   the cross-built binary, the unit, osd.conf
#   make clean
CFLAGS  ?= -O2 -g
CFLAGS  += -std=gnu11 -Wall -Wextra -Wshadow -Wvla
OSD      = ../libh713osd
GEOM     = ../libh713geom
SRC      = main.c $(OSD)/osd.c $(OSD)/text.c $(GEOM)/matrix.c $(GEOM)/config.c $(GEOM)/inverse.c
HDR      = $(OSD)/osd.h $(GEOM)/geom.h
INC      = -I$(OSD) -I$(GEOM)
SYSROOT ?= /srv/h713-rootfs
FT      ?= $(SYSROOT)
TARGET  ?= aarch64-linux-gnu
CROSS_CC ?= clang
HOST_CC ?= cc
PREFIX  ?= /usr/local
REPRO_CFLAGS = -ffile-prefix-map=$(abspath .)=. -ffile-prefix-map=$(abspath ..)=.. \
               -ffile-prefix-map=$(abspath $(SYSROOT))=/sysroot

cross: h713-osd.$(TARGET)

h713-osd.$(TARGET): $(SRC) $(HDR)
	$(CROSS_CC) --target=$(TARGET) --sysroot=$(SYSROOT) -fuse-ld=lld $(CFLAGS) $(REPRO_CFLAGS) $(INC) \
	    -isystem $(FT)/usr/include/freetype2 -o $@ $(SRC) -L$(FT)/usr/lib/aarch64-linux-gnu \
	    -Wl,-Bstatic -lfreetype -lpng16 -lbz2 -lbrotlidec -lbrotlicommon -lz -Wl,-Bdynamic -lm -pthread

host: h713-osd

h713-osd: $(SRC) $(HDR)
	$(HOST_CC) $(CFLAGS) $(INC) $$(pkg-config --cflags freetype2) -o $@ $(SRC) $$(pkg-config --libs freetype2) -lm -pthread

test: h713-osd
	python3 -m unittest discover -s tests -v

install: h713-osd.$(TARGET)
	install -D -m 0755 h713-osd.$(TARGET) $(DESTDIR)$(PREFIX)/sbin/h713-osd
	install -D -m 0644 h713-osd.service $(DESTDIR)/etc/systemd/system/h713-osd.service
	install -D -m 0644 osd.conf $(DESTDIR)/etc/h713/osd.conf

clean:
	rm -f h713-osd h713-osd.$(TARGET)

.PHONY: cross host test install clean
