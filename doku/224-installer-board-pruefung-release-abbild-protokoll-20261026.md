# 224 Der Installer schreibt ein Release-Abbild nur auf sein Board - Protokoll

Datum: 26.10.2026 abends. Kein Gerät: gemessen auf den Fake-Platten der Testsuite. Paket (lokal): `arbeit/installer-board-20261026/`.
TODO 5.26, 5.27. Anlass: `doku/223` §6.

## 1 Befund

`h713-install` verglich vor dem Schreiben eines Release-Abbilds nur die eMMC-Größe (`_image_size_problem`); `test_for` gilt nur für
Testabbilder. L018 und HY310 haben dieselbe eMMC (15 269 888 Sektoren): das Abbild des einen ging auf den anderen, mit dessen
Gerätebaum (beim L018 etwa twi2 auf PH4/PH5, die Fokusphasen des HY310). Gelesen beim Veröffentlichen von `v0.97.1-beta`, nicht
ausprobiert; die Notizen dort warnen.

## 2 Die Änderung

- `h713-mkimage build --board` (übergibt `build-all.sh` seit jeher, bisher nur für die eMMC-Größe) schreibt den Schlüssel `board`
  in die Tabelle, in der Schreibweise des Installers (`l018`, `hy200_qz713df_a1/projector05061226`); `check` nennt ihn.
- `h713-install`: `table_board()` liest ihn vor dem Gerät; eine Tabelle ohne ihn (alle bis heute, auch `v0.97-beta` und
  `v0.97.1-beta`) nennt ihr Board im Abbildnamen `h713-<board>[-<variante>]-v<version>`, die längste passende Einheit gewinnt.
  `release_board_allowed()` vergleicht mit der Erkennung: Abweichung -> Abbruch vor dem Schreiben, auch im Probelauf, Exit 1;
  gleich -> eine OK-Zeile; Board des Geräts unlesbar (Installation mit einem Installer vor dem 22.09.2026, kein `/etc/h713/board`)
  -> Warnung, geschrieben wird wie bisher; `--skip-identify` -> eine Zeile, dass nichts vergleicht.
- Über unserem Layout: beim Schreiben zuerst `/etc/h713/board` des Geräts (wie bisher), fehlt es, der Vollabzug der
  Erstinstallation in `--dump`; im Probelauf (hängt nichts ein) der Vollabzug - wie seit dem 23.09. für Testabbilder. Damit kennt
  auch der Probelauf eines Release-Abbilds über unserem Layout das Board, wenn der Abzug da ist (vgl. TODO 5.25).

## 3 Gemessen

| Prüfung | Ergebnis |
|---|---|
| neue Tests `installer/tests/test_release_board.py` (17) mit den lokalen Fixtures | grün: Namen der veröffentlichten Tabellen -> `hy310`, `l018`, `hy200_qz713df_a1/projector05061226`; L018-Abbild auf der HY310-Stock-Platte Exit 1, nichts geschrieben; HY310-Abbild dort weiter; unser Layout ohne Abzug: „WOULD: compare"; mit dem Abzug der Erstinstallation (hy300-t08): eigenes Abbild weiter, L018-Abbild Exit 1; `mkimage` schreibt den Schlüssel an zweiter Stelle |
| `test_test_image` (Testabbilder) mit Fixtures | grün, unverändert |
| ganze Suite mit Fixtures (522) | 520 grün, 2 rot: `test_installer_dryrun` `test_backup_only`, `test_restore_stock` - **auf dem unveränderten Installer genauso** (geprüft im Worktree von `doku/223`), veraltete Golden-Digests -> TODO 5.27 |
| `release/tor.sh --tests` | siehe Commit |

**Nicht gemessen:** ein Lauf am Gerät. Der Weg, den der L018 am 26.10. mit `v0.97.1-beta` ging (unser Layout, Abzug als Verweis), ist
auf der Fake-Platte des hy300-t08 nachgestellt, nicht am L018 wiederholt.
