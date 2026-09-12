# SPDX-License-Identifier: GPL-2.0
#
# h713-tv -- HDMI-Eingang auf die Video-Plane, Konsole bei Signalverlust.
#
#   make                 nativ bauen (auf dem Board: gcc-14, pkg-config, libdrm,
#                        libasound2-dev -- der Ton spricht die ALSA-Control-API)
#   make cross           quer bauen auf dem Arbeitsrechner gegen das Board-Root
#   make install         das NATIVE Binaerprogramm installieren (auf dem Board)
#   make install-cross   das QUER gebaute Binaerprogramm installieren
#                        (vom Arbeitsrechner, mit DESTDIR=/srv/h713-rootfs)
#   make clean
#
# Der Kernel wird ausschliesslich ueber build/build.sh im Container gebaut
# (doku/78 Regel 2). Dieses Programm ist Userspace: der Container sieht das
# Board-Root nicht (er hat nur /opt/Projekte/h713 -> /work, mit
# `podman inspect h713-build` am 07.09. erneut geprueft: genau ein Mount, /srv
# ist im Container leer) und hat weder libdrm noch einen arm64-Sysroot,
# deshalb baut `cross` mit dem Host-Clang gegen /srv/h713-rootfs -- nur
# lesend. Begruendung siehe README.

CC        ?= cc
PKG_CONFIG ?= pkg-config
CFLAGS    ?= -O2 -g
CFLAGS    += -Wall -Wextra -Wshadow -Wvla
CPPFLAGS  += $(shell $(PKG_CONFIG) --cflags libdrm alsa)
LDLIBS    += $(shell $(PKG_CONFIG) --libs libdrm alsa)

PREFIX    ?= /usr/local
SBINDIR   ?= $(PREFIX)/sbin
UNITDIR   ?= /etc/systemd/system
UDEVDIR   ?= /etc/udev/rules.d
DOCDIR    ?= $(PREFIX)/share/doc/h713-tv
DATADIR   ?= $(PREFIX)/share/h713-tv

# Querbau: Board-Root als Sysroot, Host-Clang als Cross-Compiler. Header und
# Linkernamen (libdrm-dev, libasound2-dev) muessen im Board-Root installiert
# sein -- `apt install libasound2-dev` auf dem Board, das Root ist dasselbe.
SYSROOT   ?= /srv/h713-rootfs
TARGET    ?= aarch64-linux-gnu
CROSS_CC  ?= clang

all: h713-tv

h713-tv: main.c
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) -o $@ $< $(LDLIBS)

cross: h713-tv.$(TARGET)

h713-tv.$(TARGET): main.c
	$(CROSS_CC) --target=$(TARGET) --sysroot=$(SYSROOT) -fuse-ld=lld \
	    $(CFLAGS) $(LDFLAGS) -isystem $(SYSROOT)/usr/include/libdrm \
	    -L$(SYSROOT)/usr/lib/$(TARGET) -o $@ $< -ldrm -lasound

install: h713-tv
	install -D -m 0755 h713-tv $(DESTDIR)$(SBINDIR)/h713-tv
	$(MAKE) install-data

# Vom Arbeitsrechner aus: das quer gebaute arm64-Programm ins Board-Root legen.
# `install` wuerde hier das x86-Binaerprogramm einspielen -- deshalb ein
# eigenes Ziel statt einer Fussnote.
install-cross: h713-tv.$(TARGET)
	install -D -m 0755 h713-tv.$(TARGET) $(DESTDIR)$(SBINDIR)/h713-tv
	$(MAKE) install-data

install-data:
	install -D -m 0644 h713-tv@.service $(DESTDIR)$(UNITDIR)/h713-tv@.service
	rm -f $(DESTDIR)$(UNITDIR)/h713-tv.service
	install -D -m 0644 99-h713-tv.rules $(DESTDIR)$(UDEVDIR)/99-h713-tv.rules
	install -D -m 0644 README.md $(DESTDIR)$(DOCDIR)/README.md
	install -D -m 0644 gamma-standard.bin $(DESTDIR)$(DATADIR)/gamma-standard.bin

clean:
	rm -f h713-tv h713-tv.$(TARGET)

.PHONY: all cross install install-cross install-data clean
