# 194 - Handoff 11.10.2026 früh: Fernbedienung und Einblendungen sind in `main` (nicht gepusht); als Nächstes dieselben Prüfstufen am HY300PRO-G-EU

Einstieg für die nächste Sitzung, auch ohne jeden Kontext. Löst `doku/189` ab. Diese Sitzung steht in vier Einträgen:
`doku/190` (Aus über crust am HY310), `doku/191` (Kaltstart-Gate über crust), `doku/192` (Einblendung über Kanal 2, aus
Fables OSD-A-Paket, und der Gesamtplan) und `doku/193` (Tasten und Einblendungen, alle Messungen). Die eine Aufgabenliste
ist `TODO.md`. Die Arbeitsregeln (lokal, nicht im Repo) stehen in `referenz/arbeitsregeln.md`, die Geräteadressen in
`referenz/geraete.md`, die Messwerkzeuge in `referenz/werkzeuge.md` (neu: "Einblendungen und Tasten").

**Marco, 11.10. früh:** "in main committen ja - aber nichts pushen - dann testen wir jetzt mit dem HY300 - genau dieselben
Verifikationsstufen" (Abschnitt 3).

## 1 Was diese Sitzung erreicht hat (10.10. abends bis 11.10. früh)

| Was | Ergebnis | Beleg |
|---|---|---|
| Aus über crust am HY310 | drei FEL-Läufe bestanden (Timer, Taste, IR weckt) | `doku/190` |
| Kaltstart-Gate über crust | U-Boot `0101`, am G-EU per FEL gemessen (0,3-0,6 W), auf Marcos Wort in `main` vor dem Netzstecker-Test | `doku/191` |
| Einblendung über dem Video | Stock nutzt OSD-A nicht; Kanal 2 über dem Video mit Alpha je Bildpunkt (Kernel `0251`, Fables Paket) | `doku/192` |
| Geräteabzüge, Arbeitsordner | 18 GB alter Abzüge weg (je Gerät bleiben Original-Android voll und klein, `referenz/artefakte.md`), integrierte Worktrees und Klone entfernt | `referenz/artefakte.md`, `pakete.md` |
| Fernbedienung per IR | Kernel `0252`-`0254`: 8 MHz statt 24 (die Ursache), Keymap `rc-h713-fd02`; alle 14 Tasten am HY310 | `doku/193` §2 |
| Tasten wirken | `h713-keys`: Lautstärke/Stumm über h713-tv, Fokus 20 Schritte, Bluetooth und IR | `doku/193` §4 |
| Einblendungen | `h713-osd` + `libh713osd` + `libh713geom` + Kanal in `h713-tv`: Pille unten mittig, vorverzerrt über dem Warp, 7-15 ms, 0 verlorene Warp-Bilder, Signalverlust und Standby sauber, gerades Alpha | `doku/193` §5-6 |
| Abbild | h713-keys und h713-osd in `install-projekt.sh` (5i) und im Gesamtbau (Schritt 6) - **ein Abbild damit ist noch nicht gebaut** | `doku/193` §7 |

## 2 Stand

- **`main`** = dieser Commit (davor `5e50e50`), Tore grün, auch `tor.sh --tests` (427 + 61 + 19 Tests). **Nichts gepusht** in
  dieser Sitzung - weder `main` noch die Forks (U-Boot `0101` = `h713-hy310` `61ea018`, crust `h713` `54e4a08`, TF-A
  `1dd03734`). Die Reihenfolge beim Push steht in `TODO.md` §1 (Forks vor `main`). Der lokale Stand von `origin/main` ist
  `79afae3`; nicht neu abgefragt.
- **Zweige:** `versuch/einblendungen` (Beleg, in `main` vorgespult). Worktree entfernt. Paket `arbeit/einblendungen-20261011/`:
  `PLAN.md`, `BERICHT.md` (jede Messung mit Uhrzeit), `patches/` (11 Patches, `BASIS.txt`), `werkzeuge/`, `laeufe/`, `bilder/`
  (Mock-ups, Entwürfe), `bau/` (Messbinaries, `LIESMICH.txt`), `ir-patches/` (Git-Quelle von 0252-0254, gleicht `main` auf
  den Baum genau).
- **HY310:** läuft den Stand von `main` per Schnell-Deploy - FIT `32ceb273…` (der Kernel aus `main`, die IR-Teile sind
  eingebaut; die Module von `8b663b8` + `0251` sind dieselben), `h713-tv`, `h713-osd`, `h713-keys` **bitgleich** mit dem Bau
  aus `main` (am Ende geprüft); h713-osd und h713-keys als Dienste aktiv; `osd-show` (Testwerkzeug) in `/usr/local/bin`. eMMC
  sonst `r2test4`. Sicherung und Rückweg: `/root/sicherung-einblendungen/` (alter FIT, altes h713-tv), Skript
  `arbeit/einblendungen-20261011/skripte/rueckweg-p0.sh`. Bluetooth-Fernbedienung neu gekoppelt (11.10.). Zuletzt nicht
  erreichbar (Marco hat ihn vermutlich ausgeschaltet).
- **HY300PRO-G-EU:** aus seit 10.10. abends; zuletzt `geumain1` (`main` `4767f6f`) bzw. die Stände in `referenz/geraete.md` -
  **vor dem Test lesen, nicht aus dem Gedächtnis**. Ihm fehlen Kernel `0251`-`0254` und alles aus Abschnitt 1 ab Zeile 5.

## 3 Als Nächstes: dieselben Prüfstufen am HY300PRO-G-EU (Marco 11.10.)

Ein neues Paket `arbeit/einblendungen-geu-<datum>/` mit `BERICHT.md`; Werkzeuge aus `arbeit/einblendungen-20261011/werkzeuge/`
(Pfade als Argument). Der G-EU ist `boards/hy200-qz713df-a1`, Panel **1280x720** - die erste Messung der Einblendungen auf
720p (am Rechner gerendert, gleiche Proportionen). Sein Gerätebaum bindet den des HY310 ein (`0181`), die Keymap kommt also
mit (im DTB nachgelesen: `rc-h713-fd02` ist drin).

| Stufe | Am HY310 (`doku/193`) | Am G-EU zu tun | Achtung |
|---|---|---|---|
| 0 Vorbereitung | - | Marco schaltet ein; Zustand **lesen** (uname, FIT-Prüfsumme, `h713-tv`/`h713-warp` Version, `warp.conf`, `power.conf`, `/etc/h713/features`); Sicherung nach `/root/sicherung-einblendungen/` | UART-ESP `.105`: Port 2001 nur lesen, 2000 nie ohne Frage (Marco nutzt die Weboberfläche) |
| 1 Bauen und aufspielen | FIT + Userspace | Kernel aus `main` (`BOARD=hy200-qz713df-a1 build/build.sh kernel`), FIT mit dem G-EU-DTB; **Module mitnehmen** (anders als am HY310: der G-EU hat kein `0251`, also ein anderes `sun50i-h713-afbd.ko`) samt aic8800 (`extra/`) - Vorlage `arbeit/skripte/deploy-test.sh`; dazu `h713-tv`, `h713-osd`, `h713-keys` (Binaries wie am HY310) | Schnell-Deploy nur mit Sicherung und aic8800 (sonst kein Netz, 05.10.); `h713-tv` liegt in `/usr/local/sbin` |
| 2 IR | 14/14 Tasten, Maus/Mikro `0x66` | dmesg `rc-h713-fd02`, `rc0` `[nec]`; Marco drückt alle Tasten, `journalctl -u h713-keys` (eine Zeile je Aktion), dazu `ir-mitschnitt.py` | **die Fernbedienung darf nicht per Bluetooth an einer anderen Box hängen** (HY310 aus lassen), sonst kommt kein IR |
| 3 Bluetooth | gekoppelt, Mikro-Tonstrom, Maus | koppeln (LINKS+RECHTS), die Tasten über Bluetooth (`listening on /dev/input/eventN`), Halten von Fokus | 2.49 (HCI-Fehler) im Blick behalten |
| 4 Einblendung | Pille unten, Stumm in der Bildecke, Fokus rot | `h713-osd ctl volume 40`, `mute on 40`, `focus up edge`; der Claim muss `1280 720` sagen; Lage und Größe auf 720p ansehen; bei Trapez die Vorverzerrung | `osd-show` braucht `systemctl stop h713-osd` (ein Claim) |
| 5 Last | 81 Wechsel, 0 Bilder verloren | dieselbe Serie (`h713-osd ctl volume` in 50-ms-Schritten), Warp-Zähler vorher/nachher | - |
| 6 Rohbild | copy 0,1 ms | `h713-warp ctl off`, Einblendungen, `ctl on` | - |
| 7 Signal weg/zurück | Konsole ohne Zeichen, Zeichen von selbst zurück | Quelle am G-EU klären (der ThinkPad hängt am HY310) | Marco fragen |
| 8 Standby | aufgewacht, neu verbunden | G-EU: `power.conf` steht auf `short = poweroff` (seine Vorgabe, `doku/188`) - ob `s3-act.py` dort einschläft, erst lesen (`standby_refusal`) | ein Standby mit RTC-Wecker am G-EU lief schon über `g2-standby.sh` (`doku/184`) |
| 9 Alpha | gerades Alpha | `osd-show --alpha2` (auf 720p), Marco schaut | - |
| 10 Zeiten | 7-15 ms | `laeufe/messe-osd.sh` auf dem G-EU | - |

Was am G-EU anders sein kann: 720p (alle Größen über die Panelhöhe, nie gemessen), der Lüfter/PB5 (`doku/185`), die
Panel-Pins (PF6, `0247`/`0248`). Wenn eine Stufe scheitert: im Bericht festhalten, nicht drumherum arbeiten.

Danach laut Plan **2.47 Warp sparsamer** (eigenes Paket, erst messen).

## 4 Offen (TODO.md)

- **1.1a** Release-Neubau: das erste Abbild mit h713-keys und h713-osd - `build-all.sh` baut h713-osd jetzt in Schritt 6, ganz
  durchgelaufen ist es damit noch nicht; danach Gerätetest wie `doku/142`.
- **2.47** Warp sparsamer; **2.49** Bluetooth-HCI-Fehler; **2.42** Netzteil-Fiepen im Aus gegen Stock; **2.40** R_WDOG-Warnung.
- **2.51** Mikrofon hörbar machen (Codec unbekannt), **2.52** Eingangstaste, Fokusrichtung, BLE-Halten, **2.53** Feinschliff
  (Ausblenden in Stufen, Stumm-Zeichen in gestauchten Ecken), **9.0b** Stumm über den Standby (optional, nach dem Release).

## 5 Was man wissen muss (neu)

- Eine Fernbedienung, die per Bluetooth an einer **anderen** Box hängt, sendet kein IR - die Tastendrücke landen dort.
- Ein Dienst ohne Journalzeile je Aktion ist keine Messung: "nur OK kam an" war falsch begründet, weil h713-keys behandelte
  Tasten nicht protokollierte (jetzt eine Zeile je Aktion; `h713-osd ctl status` zeigt die Zeiten der letzten Einblendung).
- Die Kamera der Box sieht die Wand nicht (Y = 4 auch bei Belichtung 5000/Gain 255) - an der Wand urteilt Marco.
- `release/tor.sh` in einem Worktree prüft seit diesem Stand nur, was Git kennt (`.git` ist dort eine Datei; vorher
  203 459 "Funde" in der Bauausgabe). `build.sh` nimmt `MKIMAGE=` (Worktree ohne U-Boot-Submodul).
- Kreuzbau der Userspace-Teile im Container: `make -B cross SYSROOT=/work/repo-neu/mainline/build/sysroot-arm64`; h713-warp
  dazu `MESA_PREFIX=/work/repo-neu/mainline/build/mesa-stage/usr/local`.
- Beim Prüfen mit `grep` in einer `&&`-Kette: kein Treffer heißt Exit 1, die Kette bricht ab (passiert beim Aufspielen).
  `pkill -f MUSTER` trifft auch die eigene Shell, die das Muster in ihrer Befehlszeile trägt.
- h713-tv vergisst die Stummschaltung bei jedem Standby (es startet neu) - h713-osd folgt dem richtig, das Zeichen ist dann weg.
- Die Anzeige mischt gerades Alpha (zwei Testbilder, `osd-show --alpha`/`--alpha2`).
- Mock-ups: `make -C userspace/libh713osd host && ./osd-mockup DIR [W H]`, über Fotos mit `werkzeuge/mockup-bogen.py`;
  Nachstellen einer Einblendung mit der `warp.conf` eines Geräts: `werkzeuge/sim-osd.py`.
