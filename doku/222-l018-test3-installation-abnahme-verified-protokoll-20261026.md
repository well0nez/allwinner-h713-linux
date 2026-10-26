# 222 Der L018 aus einem Abbild: test3 gebaut, über unser Layout installiert, abgenommen - verified - Protokoll

Datum: 26.10.2026. Gerät: L018 (Marcos eigener, Stock-Firmware `Projector05141211`), lief seit 25.10. unser System aus Schnell-
Deploys (`doku/220`). Marco an Gerät, Kabel, Wand und Ohr. Paket und Belege (lokal): `arbeit/l018-test3-20261026/` (`ABNAHME.md`,
`build-all-test3.log`, `stufe-*.log`, `install-test3.sh`). TODO 4.9f, 5.24, 5.25.

## 1 Warum ein Abbild

Alles am L018 war gemessen, aber nur per Schnell-Deploy. Der Weg über ein Abbild war nie gelaufen: die Board-Schlüssel der
`board.env` (`KEYSTONE`, `VOLUME_CURVE`, `FOCUS_HOMING`, `FOCUS_STEPS`) in den Konfigurationsdateien des Abbilds, die 45. Herstellerdatei
`audio_config.ini` durch den Installer, die Profile `media,desktop` im Abbild. Ohne Abnahme eines Abbilds kein `STATUS=verified`.

## 2 Bau

`release/build-all.sh --version v0.97-test3 --board l018 --test-image --profile media,desktop --vendor <Auszug des Stock-Abbilds>` aus
einer frischen Kopie von `main` (`725ebbc5`): 30 min, Schritt 10 grün, Selbsttest mit den Herstellerdateien ALL GREEN. Im Rootfs
gelesen: `tv.conf` `volume_curve = vendor`, `keys.conf` `focus_steps = 13`, `keystone.conf` `lsm6dsv_accel` +z/+y/-x 1.1501,
`/etc/modprobe.d/h713-focus.conf` `homing=0`, der Launcher mit HDMI/Kodi/Browser/Desktop/Einstellungen, Kodi, der VA-Treiber,
`h713-lamp` mit Unit, `tvconfig` leer. **Fund:** `/etc/h713/features` trug nur `lamp-modes` - der Eintrag vom 24.10. („the rest not
driven yet"). Korrigiert (`camera accelerometer focus-motor lamp-modes`) und neu gebaut (19 min; der Stempel sagt „reproducible: no",
weil fünf Schritte mit gleichen Eingaben aus dem ersten Bau übernommen wurden - für ein Release von vorn bauen).

## 3 Installation über unser Layout

| Schritt | Ergebnis |
|---|---|
| Sicherung | 29 Besitzer-Dateien per ssh (WLAN, Lampe, Fokus-Bereich, Hostschlüssel, BT-Bund, Bildwerte), nur lokal |
| Probelauf `--no-write` | **abgelehnt**: über unserem Layout hängt ein Probelauf das Rootfs nicht ein, liest `/etc/h713/board` also nicht; das Board bleibt unbekannt, und ein Testabbild wird verweigert. Abhilfe: der Vollabzug vom 25.10. als `h713-dump/emmc-full.img` (Verweis, nur lesend) nennt das Board -> L018 erkannt, 45 Dateien, nichts geschrieben |
| Schreiben (Marcos Ja) | 4 min; zurückgelesen, Secure Storage byte-gleich gegen den Abzug, HDCP-1.4-Satz vorhanden; der Installer übernahm `/etc/h713` (Fokus-Bereich, Keystone, Lampe, Panel, Warp, WLAN), die Hostschlüssel, die BT-Kopplung und den h713-tv-Zustand selbst |
| Start | Kabel raus, Strom aus/an, Power-Taste: Taste rot, dann blau (Marco), keine fehlgeschlagene Unit |

## 4 Abnahme

| Punkt | Ergebnis |
|---|---|
| Board-Werte im installierten System | wie in §2; `h713-features`: alle vier vorhanden; h713-tv meldet „the device's own curve" |
| Profile | Kodi-Start bis Bild 4,4 s |
| BT-Fernbedienung | ohne neues Koppeln; Fokus 13 Schritte, Launcher -> Kodi (Marco: „scheint alles zu klappen") |
| Lampe, Lüfter | low 2880, std 3210 U/min |
| Keystone | pitch 19,3°, angewendet; Gitter von vorn gerade (Marco) |
| Autofokus | HDMI-Bild und offener Launcher: Ende 0, Pegel 52938 (Untergrenze 3227), Launcher danach wieder da |
| Video in Hardware | 300 VE-Interrupts für 300 Bilder |
| HDMI-Ton | 440 Hz, 10 s bei Lautstärke 50 (-12,5 dB): Marco „mäßig laut ok" |
| HDCP 1.4 | Paar der Messregel: gelöscht -> Desired, normal -> Enabled |
| Lüfter-Notabschaltung | aus `doku/220` (dieselbe Unit, derselbe Board-Manager), nicht wiederholt |
| **nicht getestet** | Kopfhörer, HDCP 2.2; **nicht gemessen:** Wärmemodus über 41 °C, Abschalten bei 51 °C |

Zwei Messfehler von mir, beide erkannt: Die Meldung „Kodi zeigt nach 30 s nichts" kam von meinem Testgitter (`h713-warp ctl test
grid`), das noch statt Kodis Bild auf der Wand lag; nach `test off` 4,4 s. Ein Ton bei Lautstärke 20 blieb stumm, weil Kodi lief - der
HDMI-Ton ist unter einem Programm absichtlich aus.

## 5 Ergebnis

Marco: „trag den L018 als verified ein (mit den nicht getesteten Punkten im Board-README)". `STATUS=verified`,
`VERIFIED_BY="well0nez, L018 (Projector05141211), v0.97-test3, 26.10.2026"` - gilt für diese Stock-Firmware; die Referenzfahrt des
Fokus bleibt auf jedem L018 aus, bis eine Unit mit funktionierendem Endschalter gemessen ist. Ein Release-Abbild ist damit möglich,
aber nicht gebaut (von vorn bauen, Release-Schritte TODO §1).
