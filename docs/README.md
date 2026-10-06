# Documentation index

Every page under `docs/`, so none is reachable only from inside another one. The project's entry point is [../README.md](../README.md).

**Read first:** [architecture](architecture.md) - three processors and who owns what · [hardware](hardware.md) · [known issues](known-issues.md) ·
[dead ends](dead-ends.md) · [services](services.md) · [the first hour on a device](usage/first-hour.md) · [kernel patches](kernel-patches.md) · [the build container](build-container.md)

**Subsystems:** [display](subsystems/display.md) - panel, the descriptor's window words, the zoom model · [MIPS](subsystems/mips.md) ·
[HDMI input](subsystems/hdmi-in.md) · [audio](subsystems/audio.md) · [video](subsystems/video.md) · [picture quality](subsystems/pq.md) ·
[cpu_comm](subsystems/cpu-comm.md) · [ARISC](subsystems/arisc.md) - hot plug, EDID and the block mask · [Wi-Fi](subsystems/wifi.md) ·
[focus motor](subsystems/focus-motor.md) · [board manager](subsystems/board-mgr.md) · [crypto engine](subsystems/crypto-engine.md) · [HDCP](subsystems/hdcp.md) - 1.4 from the boot loader, 2.2 from a service, both device-local ·
[eMMC layout](subsystems/emmc-layout.md)

**Guides:** [the settings page](guides/settings-page.md) · [keystone](guides/keystone.md) · [autofocus](guides/autofocus.md)

**Tools on the device:** [h713-tv](tools/h713-tv.md) · [h713-focus](tools/h713-focus.md) · [h713-autofocus](tools/h713-autofocus.md) ·
[h713-cam](tools/h713-cam.md) · [h713-wifi](tools/h713-wifi.md) · [h713-pq](tools/h713-pq.md) · [h713-fel](tools/h713-fel.md) ·
[h713-warp](tools/h713-warp.md) - the keystone on the GPU · [h713-keystone](tools/h713-keystone.md) · [h713-panel](tools/h713-panel.md) - the automatic one.
[h713-features](tools/h713-features.md) says which optional hardware - camera, accelerometer, focus motor - the board has.
**On your PC:** [h713-install](tools/h713-install.md) · [h713-extract](tools/h713-extract.md) · [h713-mkimage](tools/h713-mkimage.md) · [h713-hdcpkey](tools/h713-hdcpkey.md) · [h713-probe](tools/h713-probe.md)

**U-Boot:** [boot chain and defconfig matrix](uboot/README.md) · [the `h713_*` commands, with the register readback at the
prompt](uboot/commands.md) · [environment](uboot/environment.md) · [power-on gate](uboot/power-gate.md)

---

Alles hier ist auf Vollständigkeit und Aktualität geschrieben. Wer wissen will, **woher** eine Aussage kommt, findet den Beleg im datierten Arbeitsjournal: [`doku/README.md`](../doku/README.md) erklärt es, [`doku/INDEX.md`](../doku/INDEX.md) §1 nennt zu jedem Dokument hier die Einträge, auf denen es ruht.
