# SPDX-License-Identifier: GPL-2.0-only
# Out-of-tree build against a kernel tree configured with CONFIG_RUST=y (the release tree since 7.3.1, build.sh
# kernel), in the h713-build container:
#   make -C /work/mainline/tools/rshim-demo KDIR=/work/mainline/build/linux-7.3.1-<hash>
KDIR ?= $(error KDIR=<kernel tree built with CONFIG_RUST=y> is required)

all:
	$(MAKE) -C $(KDIR) ARCH=arm64 LLVM=1 M=$(CURDIR) modules

clean:
	$(MAKE) -C $(KDIR) ARCH=arm64 LLVM=1 M=$(CURDIR) clean

.PHONY: all clean
