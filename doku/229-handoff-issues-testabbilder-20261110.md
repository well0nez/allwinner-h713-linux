# 229 - Handoff 10.11.2026: die Issue-Runde (#4 bis #10), drei TEST-Abbilder, was offen ist

Stand nach der Sitzung vom 30.10. bis 10.11.2026 (davor: `doku/209`, Handoff 13.10.; Messung 0336: `doku/228`). Alles in `main`
bis `b3540556` ist gepusht; der Zweig `versuch/t08-fw20250221` (`e9a64d86`) ist lokal. Aufgabenliste: `TODO.md` 4.16 bis 4.19, 2.150.

## 1 Was wann wo passiert ist

| Datum | Was | Wo |
|---|---|---|
| 30.10.-01.11. | jo-- (#4, HY300 Pro Plus): Variante `projector09220931` verifiziert (`43d83c47`) | `arbeit/issue4-hy300-pro-plus-20261030/` |
| 31.10.-04.11. | minpeter (#5/#6): Extractor-Fix (`3b50b4cf`), HY320 als partial (`1dbbfe8c`, PR #6 geschlossen), **0336 DDC-Tabelle** auf HY310 und G-EU gemessen und mit h713-tv/h713-mode gemergt (`fc20eb31`, `doku/228`), Dank in #5 | `arbeit/issue5-hy320-20261031/`, `arbeit/schritt3-messung-20261103/` |
| 03.-04.11. | smj-0712 (#7, HY300 T08): Profil mit Varianten, Kernel 0349, U-Boot `hy300_t08_defconfig`, TEST-Abbild **`hy300-t08-test1`**. Sein Lauf: Launcher, Fernbedienung, **kein WLAN** (AIC8801); USB-2.0-Hub nötig | `arbeit/t08-20261103/`, `arbeit/issue7-hy300-t08-20261031/` |
| 05.11. | erfrizzera (#8, HY300 mit 2023-Firmware): Profil `hy300_2023`, Board, Kernel 0350, U-Boot `hy300_2023_defconfig` (Fork `212454b3952`, Spiegel 112), TEST-Abbild **`hy300-2023-test1`** | `arbeit/hy300-2023-20261105/`, `arbeit/issue8-hy300-20261102/` |
| 10.11. | erfrizzera: Install verweigert, weil zwei Profil-Hashes aus seinem vertippten 1. Kommentar stammten; Fix `f31c372a`, Tag **`hy300-2023-test1b`** (nur Installer), Antwort | dito, `melder-20261110/` |
| 10.11. | tgiorgio (#10, T08 mit dritter Firmware, eMMC 14 942 208 Sektoren): Variante `fw20250221`, `SECTORS_KNOWN` + 1, Commit `e9a64d86` auf `versuch/t08-fw20250221`; TEST-Abbild `v0.97.2-t08fw2025test1` im Bau | `arbeit/t08-fw20250221-20261110/`, `arbeit/issue10-hy300-20250221-20261110/` |

Geräte: HY310 und G-EU laufen `v0.97.2-mess0336` (0336 drin, Messung bestanden). UART-Brücke `.224` tot seit 03.11. (kein Ping);
Resets am HY310 von Hand. Nichts von uns ist auf T08, HY300-2023 oder dem #10-Gerät gelaufen außer smj-0712s Lauf bis zum Launcher.

## 2 Wie ein Melder-Board gemacht wird (das Muster, dreimal benutzt)

1. Paket `arbeit/issue<N>-<board>-<datum>/` mit `melder-<datum>/` (Rohdaten), `BEWERTUNG.md`, `ANTWORT<n>-ENTWURF.md` -> nach dem Posten `-TEXT.md`.
2. Worktree `arbeit/<thema>-<datum>/repo` auf `versuch/<thema>` (Submodule: `git -c protocol.file.allow=always submodule update --init`).
3. Profil (`installer/h713/profiles/`, Varianten-Schema `SCHEMA.md`), `boards/<id>/` (`board.env`, `variants/*/variant.env`, README), Kernel-DTS-Patch
   (Include des nächsten Baums), U-Boot-Fork-Zweig (Firmware-Zeile `h713_mips_fw_revs[]`, Defconfig **mit den `# ... is not set`-Zeilen**, dts),
   `uboot-prove-fragments.sh`-Matrix, `docs/kernel-patches.md`, `boards/README.md`, TODO.
4. Prüfen: `installer/tests/run.sh` (528), `bash boards/check.sh`, `python3 release/doku-index.py` dann `release/tor.sh && git commit`.
5. Fork pushen (Marcos Ja), Spiegel `uboot-h713/` per `git format-patch --no-signature 8fe568cdfc46..<kopf>` und `git am`-Baumhash prüfen, Gitlink.
6. Bau: `release/build-all.sh --version <v> --board <id> [--variant <v>] --test-image --profile media,desktop` (~30 min, `bau.sh` + `bau.log` + `bau.rc`).
7. Assets: drei `.img.zst` (`zstd -19 --long=27`), Tabelle, `.sha256`, BUILD, README, `u-boot-installer.bin`, `sunxi-fel`, `SHA256SUMS.zst.txt` in `release-<tag>/`.
8. Marcos Ja je Push/Tag/Release/Post: `git push`, `git tag -a`, `gh release create --prerelease --notes-file`, `gh issue comment --body-file`.
   Vorher E-Mail-Prüfung: `git log --format='%ae %ce'` und `git for-each-ref --format='%(taggeremail)' refs/tags` nur noreply.
Lehre vom 10.11.: ein in ein Issue getippter Hash wird gegen eine Lesung (`identify`-Zeile, `h713-extract`) geprüft, nie abgetippt übernommen.

## 3 Offen (Reihenfolge = Vorschlag)

1. **#10 tgiorgio**: Bau abwarten (`arbeit/t08-fw20250221-20261110/bau.log`, `bau.rc`), Assets packen, Merge `versuch/t08-fw20250221` nach `main`,
   Push, Tag `hy300-t08-fw20250221-test1`, Pre-Release, Antwort (Schritt 0 hat er; sein `dd` ist der Rückweg; Item-Größen per `h713-extract`
   erbitten; Hub-Hinweis; Fernbedienung). Jedes davon nur auf Marcos Ja.
2. **#8 erfrizzera**: wartet auf seinen Install mit `hy300-2023-test1b`. Erste Lauf-Risiken: DRAM-Block aus unserem SPL, Display-Firmware-Revision
   (schwarze Wand nach Logo = AFBD-Übergabeworte), AIC8801.
3. **#7 smj-0712**: WLAN-Diagnose erbeten (Settings > Wi-Fi, Terminal-Befehle), keine Antwort seit 04.11. Hub-Befund in die Docs (FLASHING) noch nicht geschrieben.
4. **PR #9 minpeter** (Kernel 7.3.1 + Rust): Marco: jetzt kein Kernelwechsel; erst besprechen, dann antworten. Unbeantwortet.
5. **TODO 2.150**: HDMI-Ton unter dem Launcher hörbar (HY310, Quelle `auto`). **4.16**: G-EU-Variante im Profil noch profile-only (Marcos Entscheidung).
   G-EU-Boot "no lock"-Zeilen mit gesteckter Quelle (`doku/228`). UART-Brücke `.224` tot. cosmonet-fr (#3) still seit 25.10.
6. Aufräumen (Marco): Worktrees `arbeit/*/repo` und `uboot/` (je ~2 GB): `schritt3-messung-20261103`, `t08-20261103`, `hy300-2023-20261105`,
   `t08-fw20250221-20261110`; `git worktree prune` danach. `referenz/pakete.md` führt alle Pakete mit "Entfernen: Marco".

## 4 Wo was liegt

Antworten und Release-Texte: `arbeit/issue*/ANTWORT*-TEXT.md`, `arbeit/*/RELEASE-NOTES-*.md`. Berichte: `arbeit/*/BERICHT.md`. Register: `referenz/pakete.md`.
Forks: `well0nez/u-boot` Zweig `h713-hy310` (`212454b3952`), `well0nez/crust` Zweig `h713`. Releases: `hy300-t08-test1`, `hy300-2023-test1` (+ Tag `-test1b`).
