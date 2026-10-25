# h713-mic: Python, no build step. `make test` runs the host tests; `make install DESTDIR=...` (not in the image yet).
PREFIX ?= /usr/local
test:
	python3 -m unittest discover -s tests -v
install:
	install -D -m 0755 h713-mic $(DESTDIR)$(PREFIX)/bin/h713-mic
	install -D -m 0644 README.md $(DESTDIR)$(PREFIX)/share/doc/h713-mic/README.md
.PHONY: test install
