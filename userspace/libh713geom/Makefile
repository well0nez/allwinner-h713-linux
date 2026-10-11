# SPDX-License-Identifier: GPL-2.0
#
# libh713geom -- the keystone geometry, a source library: h713-warp compiles matrix.c and config.c into
# itself, h713-osd will add inverse.c. Nothing to build here but the host tests.
#
#   make test    T2 the matrix against the reference model (h713-keystone/model), T3 warp.conf,
#                T4 the way back - in the container h713-build, no GLES needed
#   make clean
CFLAGS  ?= -O2 -g
CFLAGS  += -std=c11 -Wall -Wextra -Wshadow -Wvla
HOST_CC ?= cc
PYTHON  ?= python3
TESTS    = tests/test_matrix tests/test_conf tests/test_inverse

test: $(TESTS)
	@cd tests && $(PYTHON) matrix_ref.py > vectors.txt && ./test_matrix < vectors.txt && ./test_conf && ./test_inverse

tests/test_matrix: tests/test_matrix.c matrix.c geom.h
	$(HOST_CC) $(CFLAGS) -o $@ tests/test_matrix.c matrix.c -lm

tests/test_conf: tests/test_conf.c config.c matrix.c geom.h
	$(HOST_CC) $(CFLAGS) -o $@ tests/test_conf.c config.c matrix.c -lm

tests/test_inverse: tests/test_inverse.c inverse.c matrix.c geom.h
	$(HOST_CC) $(CFLAGS) -o $@ tests/test_inverse.c inverse.c matrix.c -lm

clean:
	rm -f $(TESTS) tests/vectors.txt

.PHONY: test clean
