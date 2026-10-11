# h713-keys: Python, no build step. `make test` runs the host tests; `make install DESTDIR=...` for the image.
PREFIX ?= /usr/local
test:
	python3 -m unittest discover -s tests -v
install:
	install -D -m 0755 h713-keys $(DESTDIR)$(PREFIX)/sbin/h713-keys
	install -D -m 0644 h713-keys.service $(DESTDIR)/etc/systemd/system/h713-keys.service
	install -D -m 0644 keys.conf $(DESTDIR)/etc/h713/keys.conf
	install -D -m 0644 README.md $(DESTDIR)$(PREFIX)/share/doc/h713-keys/README.md
.PHONY: test install
