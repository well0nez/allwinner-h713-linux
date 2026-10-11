
## 12.09.2026 (P1, doku/116): zwei Waisen aus patches/kernel/

- `0050-asoc-sunxi-add-the-h713-internal-audio-codec.patch` -- stand nie in der `series`, ueberholt durch
  den Audio-Block 0134-0139 (Codec-I2S-Pfad + MSP-DSP). Die drei defconfig-Zeilen
  `CONFIG_SND_SOC_SUNXI_H713_{CODEC,CPUDAI,MACHINE}=m` verweisen auf Symbole, die es nur in diesem Patch
  gibt -- tot, Kconfig ueberliest sie. Aufraeumen bei der naechsten defconfig-Aenderung (61-todo D).
- `0090-soc-sunxi-add-arisc-hdmi-hpd.patch` -- das alte HPD-Diagnosemodul, ersetzt durch den ARISC-Treiber 0091
  (doku/82).

## 15.09.2026 (doku/124): cstengers 0040

- `0040-media-cedrus-halt-ve-before-freeing-dma-buffers.patch` -- cstenger hat es am 23.08.2026 aus seiner Serie
  genommen (Kopfvermerk im Patch seines Zweigs): ein Reset ist geraeteweit, mit einem zweiten m2m-Kontext mitten im
  Job bleibt dessen STREAMOFF fuer immer in `v4l2_m2m_cancel_job()` (D-Zustand, kein SIGKILL). A/B im selben Boot ueber
  `sunxi_cedrus.stop_reset`: N gibt 9/9 bitexakt bei drei Clients, Y verklemmt in Runde 1. Sein Daseinsgrund, die
  Speicherkorruption unter Last, war der 1416-MHz-Betriebspunkt, den `0055` entfernt. Unser Exemplar war byteidentisch
  mit seinem; kein eigener Geraetetest, der Fehlermodus ist Kontextlogik, nicht Panelgeometrie.

## 11.10.2026 (TODO 5.22): 0011, seit dem 22.09. aus der Serie, lag noch in patches/kernel/

- `0011-misc-add-sunxi-nsi.patch` -- seit dem 22.09.2026 nicht mehr in der `series` (der Vermerk Q1 dort sagt warum:
  `drivers/misc/sunxi-nsi.c` ist kein NSI-Treiber, er erfindet eine Registerkarte fuer `nsi-controller@2020000`). Die
  Datei lag weiter neben der Serie; jetzt hier. Am Bau aendert das nichts: der Kernelbaum wird nur aus der `series`
  gebaut, ihr Hash ist gleich.
