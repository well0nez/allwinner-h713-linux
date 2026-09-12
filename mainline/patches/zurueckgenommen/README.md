
## 12.09.2026 (P1, doku/116): zwei Waisen aus patches/kernel/

- `0050-asoc-sunxi-add-the-h713-internal-audio-codec.patch` -- stand nie in der `series`, ueberholt durch
  den Audio-Block 0134-0139 (Codec-I2S-Pfad + MSP-DSP). Die drei defconfig-Zeilen
  `CONFIG_SND_SOC_SUNXI_H713_{CODEC,CPUDAI,MACHINE}=m` verweisen auf Symbole, die es nur in diesem Patch
  gibt -- tot, Kconfig ueberliest sie. Aufraeumen bei der naechsten defconfig-Aenderung (61-todo D).
- `0090-soc-sunxi-add-arisc-hdmi-hpd.patch` -- das alte HPD-Diagnosemodul, ersetzt durch den ARISC-Treiber 0091
  (doku/82).
