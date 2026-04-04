obj-m += h713_drm.o

KDIR ?= /opt/captcha/kernel/linux-6.16.7

all:
	make -C $(KDIR) M=$(PWD) ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- modules

clean:
	make -C $(KDIR) M=$(PWD) ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- clean
