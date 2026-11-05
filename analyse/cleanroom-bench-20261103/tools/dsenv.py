#!/usr/bin/env python3
"""dsenv.py: drop variables whose name contains a space (left by a wrong fw_setenv -s format), then set the switch
environment with fw_setenv NAME VALUE (one argv each). Spec side, 2026-11-04."""
import subprocess
cur = subprocess.run(["fw_printenv"], capture_output=True, text=True).stdout.splitlines()
for l in cur:
    k = l.partition("=")[0]
    if " " in k:
        subprocess.run(["fw_setenv", k], check=True); print("dropped", repr(k[:40]))
vals = {
 "bootcmd": 'if test "${h713_display}" = clean; then h713_disp init ${h713_project} noboot logo; setenv h713_display_args "h713.display=clean module_blacklist=hy310_cpu_comm,sun50i_h713_hdmirx,sun50i_h713_mips,sun50i_h713_msp,sun50i_h713_afbd"; else h713_disp init ${h713_project} logo; setenv h713_display_args "module_blacklist=h713_drm"; fi; h713_conlog 0x45000000; mmc dev 1; mmc write 0x45000000 0x2800 0x400; run boot_${h713_boot}; run boot_net',
 "boot_emmc": 'if ext4load mmc 1:5 0x60000000 h713-kernel-7.3.fit; then setenv bootargs "${bootargs_base} loglevel=4 root=PARTLABEL=hy310-rootfs rw ${h713_display_args}"; bootm 0x60000000; fi',
 "boot_net": 'dhcp; setenv bootargs "${bootargs_base} earlycon root=/dev/nfs rw nfsroot=${serverip}:${nfsroot},vers=3,tcp ip=dhcp ${h713_display_args}"; tftpboot 0x60000000 ${serverip}:${bootfile}; bootm 0x60000000',
 "h713_display": "vendor",
}
for k, v in vals.items():
    subprocess.run(["fw_setenv", k, v], check=True)
    back = subprocess.run(["fw_printenv", k], capture_output=True, text=True).stdout.rstrip("\n")
    print(k, "OK" if back == f"{k}={v}" else f"MISMATCH: {back}")
