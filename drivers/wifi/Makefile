CONFIG_AIC8800_BTLPM_SUPPORT := m
CONFIG_AIC8800_WLAN_SUPPORT := m
CONFIG_AIC_WLAN_SUPPORT := m

obj-$(CONFIG_AIC8800_BTLPM_SUPPORT) += aic8800_btlpm/
obj-$(CONFIG_AIC8800_WLAN_SUPPORT) += aic8800_fdrv/
obj-$(CONFIG_AIC_WLAN_SUPPORT) += aic8800_bsp/


# Platform support list
CONFIG_PLATFORM_ROCKCHIP = n
CONFIG_PLATFORM_ROCKCHIP2 = n
CONFIG_PLATFORM_ALLWINNER = n
CONFIG_PLATFORM_MAINLINE_SUNXI = y
export CONFIG_PLATFORM_MAINLINE_SUNXI
CONFIG_PLATFORM_AMLOGIC = n
CONFIG_PLATFORM_UBUNTU = n


ifeq ($(CONFIG_PLATFORM_ROCKCHIP), y)
#KDIR = /opt/captcha/kernel/linux-6.16.7
#ARCH = arm
#CROSS_COMPILE = arm-linux-gnueabi-
KDIR = /opt/captcha/kernel/linux-6.16.7
ARCH = arm
CROSS_COMPILE = arm-linux-gnueabi-
#KDIR = /opt/captcha/kernel/linux-6.16.7
#ARCH = arm
#CROSS_COMPILE = arm-linux-gnueabi-
#ccflags-y += -DANDROID_PLATFORM
ccflags-y += -DCONFIG_PLATFORM_ROCKCHIP
endif

ifeq ($(CONFIG_PLATFORM_ROCKCHIP2), y)
ARCH = arm64
KDIR = /home/yaya/E/Rockchip/3566/firefly/Android11.0/Firefly-RK356X_Android11.0_git_20210824/RK356X_Android11.0/kernel
CROSS_COMPILE = /home/yaya/E/Rockchip/3566/firefly/Android11.0/Firefly-RK356X_Android11.0_git_20210824/RK356X_Android11.0/prebuilts/gcc/linux-x86/aarch64/gcc-linaro-6.3.1-2017.05-x86_64_aarch64-linux-gnu/bin/aarch64-linux-gnu-
#ccflags-y += -DANDROID_PLATFORM
ccflags-y += -DCONFIG_PLATFORM_ROCKCHIP2
endif


ifeq ($(CONFIG_PLATFORM_ALLWINNER), y)
KDIR = /opt/captcha/kernel/linux-6.16.7
ARCH = arm
CROSS_COMPILE = arm-linux-gnueabi-
#ccflags-y += -DANDROID_PLATFORM
endif

ifeq ($(CONFIG_PLATFORM_AMLOGIC), y)
#ccflags-y += -DANDROID_PLATFORM
ARCH = arm
CROSS_COMPILE = /home/yaya/D/Workspace/CyberQuantum/JinHaoYue/amls905x3/SDK/20191101-0tt-asop/android9.0/prebuilts/gcc/linux-x86/arm/arm-linux-androideabi-4.9/bin/arm-linux-androidkernel-
KDIR = /home/yaya/D/Workspace/CyberQuantum/JinHaoYue/amls905x3/SDK/20191101-0tt-asop/android9.0/out/target/product/u202/obj/KERNEL_OBJ/

endif

ifeq ($(CONFIG_PLATFORM_UBUNTU), y)
KVER := $(or $(KVER), $(kernelver), $(KERNELRELEASE), $(shell uname -r))
KDIR ?= /lib/modules/$(KVER)/build
PWD  ?= $(shell pwd)
MODDESTDIR ?= /lib/modules/$(KVER)/kernel/drivers/net/wireless/aic8800
ARCH ?= $(shell uname -m | sed -e s/i.86/i386/ -e s/armv.l/arm/ -e s/aarch64/arm64/)
CROSS_COMPILE ?= aarch64-linux-gnu-
endif

ifeq ($(CONFIG_PLATFORM_MAINLINE_SUNXI), y)
ccflags-$(CONFIG_PLATFORM_MAINLINE_SUNXI) += -DCONFIG_PLATFORM_MAINLINE_SUNXI
KDIR  ?= /opt/captcha/kernel/linux-6.16.7
PWD   ?= $(shell pwd)
KVER  ?= $(shell uname -r)
MODDESTDIR ?= /lib/modules/$(KVER)/kernel/drivers/net/wireless/
ARCH  ?= arm
CROSS_COMPILE ?= arm-linux-gnueabi-
endif

all: modules
modules:
	$(MAKE) -C $(KDIR) M=$(PWD) ARCH=$(ARCH) CROSS_COMPILE=$(CROSS_COMPILE) modules

install:
	mkdir -p $(MODDESTDIR)
	install -p -m 644 aic8800_bsp/aic8800_bsp.ko  $(MODDESTDIR)/
	install -p -m 644 aic8800_fdrv/aic8800_fdrv.ko  $(MODDESTDIR)/
	install -p -m 644 aic8800_btlpm/aic8800_btlpm.ko  $(MODDESTDIR)/
	/sbin/depmod -a ${KVER}

uninstall:
	rm -rfv $(MODDESTDIR)/aic8800_bsp.ko
	rm -rfv $(MODDESTDIR)/aic8800_fdrv.ko
	rm -rfv $(MODDESTDIR)/aic8800_btlpm.ko
	/sbin/depmod -a ${KVER}

clean:
	cd aic8800_bsp/;make clean;cd ..
	cd aic8800_fdrv/;make clean;cd ..
	cd aic8800_btlpm/;make clean;cd ..
	rm -rf modules.order Module.symvers .tmp_versions/

