# 210 - Entflechtung des Subtrees: cstengers Dateien ohne Lizenz sind aus dem Baum, was sie ersetzt (13.10.2026)

**Kurz:** Marcos Regel vom 13.10.: was wir so nicht verwenden dürfen, wird umgeschrieben (wenn wir es brauchen) oder entfernt
(wenn nicht). cstengers Repository hat keine LICENSE; außer seinen Kernelpatches und neun C-Dateien mit `SPDX-License-Identifier:
GPL-2.0` sagt keine seiner Dateien, unter welchen Bedingungen man sie weitergeben darf, und er hat bisher nicht geantwortet.
Dieser Eintrag beschreibt, was daraufhin aus `mainline/` genommen und was an seine Stelle gesetzt wurde. Grundlage:
`arbeit/lizenzen-20261013/BERICHT.md` §1.5, §2.2; Plan und Bericht der Arbeit: `arbeit/lizenz-entflechtung-20261013/`.
Gearbeitet wurde im Zweig `versuch/entflechtung`, **ohne Push**; die Dateien sind in diesem Zweig weg, in `main` erst nach der
Übernahme.

## 1 Was entfernt, ersetzt, behalten wurde

| | Dateien | Wohin / warum |
|---|---:|---|
| entfernt | 68 | niemand im Bau, in den Tests oder in den Toren braucht sie; nur Querverweise, Kommentare und Journalzitate zeigten auf sie |
| entfernt und ersetzt | 2 | `mainline/docs/reference/cpu-comm-call-table.md` -> Abschnitt "The routine table" in `docs/subsystems/cpu-comm.md`; `mainline/.gitignore` -> drei Zeilen in der Wurzel-`.gitignore` |
| neu geschrieben | 2 | `mainline/README.md`, `mainline/tools/README.md` (aus dem heutigen Stand des Baums, kein Satz übernommen: 0 gemeinsame Fünfwortfolgen mit den alten Dateien) |
| bleibt | 11 | seine neun Dateien mit SPDX-Zeile (`tools/display/drm-flip.c`, `tools/video/{decd-client,gles-nv12,gles-play,gles-probe,gles-scanout,gles-tear,gputest,h713-present}.c`) und zwei eigene (`build/uboot-prove-fragments.sh`, `tools/or1k-toolchain/build-or1k-toolchain.sh`) |
| nicht angefasst | 4 | `build/build.sh`, `build/uboot-build.sh`, `config/versions.env`, `config/toolchain.md`: gehören dem Neuschrieb (`arbeit/lizenz-umbau-20261013/`) |
| nicht angefasst | 8 | die "Lückendateien" (PLAN §1.2: `series`, Defconfig, drei Kernel-Fragmente, zwei READMEs, `patches/aic8800/series`) - eigene Entscheidung, Schritt E5 |

Aus dem Baum verschwinden damit **70** Dateien. Die Kernelpatches wurden nicht berührt; ihre Kommentare auf seine Dokumente bleiben
als Herkunftsangabe stehen (`0024`, `0033`, `0042`, `0055`, `0092`, `0101`, `0187`, `uboot-h713/0005`, `0051` und andere).

Dazu ein neues Tor: Regel 9 in `release/sperr-scan.py` meldet eine Quelldatei (`.c .h .S .py .sh .dts .dtsi`) unter `mainline/` ohne
SPDX-Zeile im Kopf als harten Fund (frei: `external/`, `modules/aic8800/`, `build/`, `tools/or1k-toolchain/`); Test `installer/tests/test_sperrscan_spdx.py`
(Fund, Nicht-Fund, freie Stellen). Gegenprobe am echten Baum: eine unverfolgte `mainline/tools/zz-probe.c` ohne Kopf wurde gemeldet, der Baum selbst ist sauber.

## 2 Wo die entfernten Dateien liegen

* **In seinem Repository** `github.com/cstenger/allwinner-h713-mainline` @`8860991`: derselbe Pfad **ohne** das führende `mainline/`
  (`mainline/docs/status.md` heißt dort `docs/status.md`). Alle 70 sind dort geprüft (`git ls-tree -r 8860991`).
* **In unserer Historie:** der Import ist der Merge `657ce79` (13.09.2026, zweiter Elternteil `8860991`). Solange die Historie seine
  Commits trägt, liefert `git show 8860991:docs/status.md` jede Datei; jeder Commit vor dem Entfernen hat sie ebenfalls
  (`git log --diff-filter=D -- mainline/docs/status.md` findet den Commit, der sie entfernt).
* **Die Historie selbst ist nicht angefasst.** Ob sie so bleibt, ist Marcos Entscheidung (PLAN §6, Schritt E6), nicht Teil dieser Arbeit.

## 3 So sind ältere Einträge zu lesen

Pfade der Form `mainline/docs/...`, `mainline/tools/...`, `mainline/README.md`, `mainline/PROVENANCE.md`,
`mainline/patches/libva-v4l2-request/...` in den Einträgen bis `doku/209` und in den Nachtlogs meinen **seinen** Baum, wie er war
(Zuordnung oben). Sie werden nicht umgeschrieben (`PROVENANCE.md`: das Journal ist Beleg). Der einzige Pfad, den wir als Quelle geführt
haben, `mainline/docs/reference/cpu-comm-call-table.md`, lebt als Abschnitt "The routine table" in `docs/subsystems/cpu-comm.md` weiter:
Fakten nach seiner Aufnahme, Gliederung und Wortlaut eigen, die IDs neu gerechnet (§5). Die Berichtigung in `doku/83` und `doku/nachtlog/C-cpu-comm`
("IDs sind aus dem Namen ableitbar") gilt unverändert.

## 4 Die 70 Pfade (relativ zu `mainline/`)

* `docs/` (20): `backlight-investigation`, `board-bringup-sequence`, `bringup-notes`, `bringup-readiness`, `build`,
  `claude-display-handoff`, `flash`, `handoff-2026-08-17`, `handoff-wifi-sdio-2026-08-17`, `iommu-port`, `kernel-bump`, `kms-display`,
  `mips-display-recovery`, `roadmap`, `rootfs`, `standalone-boot`, `status`, `vaapi-scope`, `video-decode`, `wifi-failure-2026-08-17` (alle `.md`)
* `docs/reference/` (11): `cpu-comm-call-table.md` (ersetzt), `expA-720p-cma128.log`, `expB-736p-cma128.log`, `expC-720p-cma256.log`,
  `expE-no-vaapi-still-crashes.log`, `expH-reset-disabled-crashes.log`, `expI-display-only-no-ve-crashes.log`,
  `h713-drm-sched-panfrost-oops.log`, `h713-fel-notes.md`, `soak-iommu-fix-on-still-crashes.log`, `wifi-baseline-2024-driver.txt`
* `tools/` (29): `boot-switch.sh`, `cpufreq-thermal-validate.sh`, `flash-standalone.sh`; `display/{devmem32.c,edge-measure.py,handoff-check.sh,make-bundle.py,tear-measure.py}`;
  `rootfs/{build.sh,customize.sh,hotspot.conf.example,verify-video-tooling.sh}`;
  `serial/{acm,boot_kernel,console,h713_tty,load_fit,reboot-to-uboot,send_file,soak-capture,sysrq,ymodem_send}.py`;
  `video/{m1-decode-test.sh,make-test-streams.sh,soak-display-only.sh,va-decode-test.sh,vedump.py}`; `wifi/{sta-connect.sh,wifi-baseline.sh}`
* `patches/libva-v4l2-request/` (5): `0001-h264-include-utils.h-...`, `0002-Build-H.264-only-...`, `0003-Create-the-bitstream-buffer-...`, `README.md`, `series`
  (Patche auf bootlins MIT-Code; in `main` hat sie kein Bauschritt angewendet)
* Wurzel von `mainline/` (5): `.gitignore` (ersetzt), `.gitmodules` (wirkungslos, git liest nur die der Wurzel), `PROVENANCE.md` (die Wurzel-`PROVENANCE.md` führt Forks, Toolchain und Serien),
  `baseline-2024-driver.txt`, `patches/README.md` (`docs/kernel-patches.md` ist der Serienindex)

## 5 Gemessen (Stand dieses Eintrags)

* **IDs:** alle 82 Routinen-IDs der Tabelle aus ihren Namen mit der crc32-Regel von `docs/subsystems/cpu-comm.md` neu gerechnet: 82 von 82 stimmen
  (Skript `arbeit/lizenz-entflechtung-20261013/hilfen/rechne-ids.py`, Gegenprobe `pruefe-tabelle.py` gegen die alte Tabelle: gleiche 82 IDs, die 24 Handleradressen der alten
  Tabelle unverändert). Neu: drei Namen mit dem Herstellertippfehler `Thal_` statt `THal_`, nicht zwei - `Thal_Vp_AtvIsFastSyncLock` kommt zu den zwei
  Backlight-Einträgen. 58 der 82 Namen standen in seiner Seite ohne das Präfix `THal_Vp_`; die ID entscheidet es. Handleradressen: 6 stimmen mit unserer statischen
  Lesung von `display.bin` überein (`doku/85` §A.2), 19 stehen nur in seiner Aufnahme (nicht nachgemessen), für 57 Einträge ist keine Adresse festgehalten.
* **Nach dem Entfernen:** `git ls-files mainline | wc -l` 586 -> 516 (586 - 70); 26 490 Zeilen gelöscht; `mainline/build/build.sh` vorhanden (Wurzelmarker
  für `rootfs/`, `installer/`); `git diff main --stat` über die gehashten Pfade des Kernelbaus (`patches/kernel/series`, `board/`, alle
  `patches/kernel/0*.patch`, `patches/aic8800/series` und `*.patch`) leer, der Eingabe-Hash ändert sich damit nicht (am Diff gemessen, nicht durch einen Bau).
  Die 16 Pfade unter `mainline/`, die im Arbeitsbaum von `main` heute ignoriert sind, liegen alle unter `mainline/build/` und sind auch nach dem Entfernen von
  `mainline/.gitignore` ignoriert (`git check-ignore --no-index`); deren Typmuster (`*.bin`, `*.fit`, `*.dtb`, `*.tar`, `Image*`, `*.swp`, `.DS_Store`) sind
  nicht in die Wurzeldatei übernommen.
* **Tore:** `release/tor.sh --tests` grün (Installer-Tests 449 nach E3 und 452 mit den drei der neuen Regel, davon 54 übersprungen wie vorher; `h713-power` 83, `h713-keys` 22), `bash boards/check.sh` grün,
  `tools/check-links.py` ohne tote Links und Waisen. Danach verweist außerhalb von Journal, Patchtexten, `TODO.md` und den vier Dateien im Neuschrieb nur noch
  das auf die entfernten Pfade, was dieser Eintrag in §6 nennt.

## 6 Nicht gemacht

* kein Push, kein Merge nach `main`, die Historie nicht angefasst (§2);
* `build.sh`, `uboot-build.sh`, `versions.env`, `toolchain.md` nicht angefasst - sie verweisen noch auf Entferntes (`patches/README.md`, `docs/flash.md`, `docs/kernel-bump.md`,
  `tools/rootfs/`, `docs/build.md`, `docs/bringup-notes.md`, libva-Pins); der Neuschrieb tilgt das;
* die acht Lückendateien nicht angefasst; `patches/kernel/README.md` (Z. 17, 135, 195), `patches/aic8800/README.md` (Z. 60, 65), `patches/kernel/series` (Z. 11),
  `patches/kernel/board/{hy200_qz713df_a1_defconfig,kasan.config,builtin-drivers.config}` (Kommentare) zeigen deshalb noch auf Entferntes; die ersten beiden sind Markdown-Verweise,
  die kein Tor prüft;
* Kommentare in seinen neun C-Dateien (`drm-flip.c`, `gles-tear.c`, `h713-present.c`) nennen `docs/kms-display.md` und `tools/display/tear-measure.py`; die Dateien tragen seine
  SPDX-Zeile und sind unverändert; `mainline/tools/README.md` sagt es;
* `patches/vorschlaege/_erledigt/I/ENTWURF.md` (Z. 81) nennt `mainline/docs/reference/cpu-comm-call-table.md`; ein Entwurf von 2026-09, wie ein Journaleintrag nicht umgeschrieben;
* kein Bau, kein Kernelbau, kein Gerät; "der Eingabe-Hash des Kernels bleibt unverändert" ist am Diff der gehashten Pfade geprüft (Bericht), nicht durch einen Bau.
