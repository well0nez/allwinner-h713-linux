# 195 - Einblendungen und Tasten am HY300PRO-G-EU: dieselben zehn Prüfstufen, ein Fix in h713-osd (11.10.2026)

**Kurz:** Die Fernbedienung und die Einblendungen aus `doku/193` laufen auch am HY300PRO-G-EU (`boards/hy200-qz713df-a1`,
Panel 1280x720): alle 13 IR-Tasten (ohne Power) und `0x66`, Bluetooth mit Maus und Mikro-Ton, die Einblendungen auf 720p
vorverzerrt über einem Trapez, 5-13 ms je Einblendung, kein verlorenes Warp-Bild durch sie, Standby, gerades Alpha. Stufe 7
(Signal weg und zurück) deckte einen Fehler auf, den der HY310 nur zufällig nicht zeigte: das Stumm-Zeichen blieb unverzerrt
über dem verzerrten Bild, wenn der Warp erst nach dem Ring zurückkam. **Fix in h713-osd** (`a71860b` auf
`versuch/einblendungen-geu`): solange etwas zu sehen ist und ein Trapez gilt, fragt es h713-tv alle 250 ms nach der Unterlage
und zeichnet neu, wenn sie sich geändert hat. Paket `arbeit/einblendungen-geu-20261011/` (BERICHT mit jeder Messung,
Mitschnitte, Deploy- und Rückwegskript). Plan `doku/194` §3.

## 1 Aufbau

Kernel aus `main` `8f2c992` mit `BOARD=hy200-qz713df-a1` (EXIT 0, keine Warnung): FIT mit dem G-EU-DTB, der den des HY310
einbindet - Keymap `rc-h713-fd02` und Empfänger ohne `clock-frequency` kommen mit, kein Zusatzpatch. Schnell-Deploy mit
Sicherung (`/root/sicherung-einblendungen/` am Gerät): FIT, alle Module dieses Baus plus `extra/` (aic8800), h713-tv, h713-osd,
h713-keys aus `main`. h713-warp blieb: das Binary am Gerät hat dieselben Code- und Datenabschnitte wie der Bau aus `main`. Der
G-EU hat keinen Fokusmotor - `h713-focus` endet mit 7, h713-keys meldet das einmal, die Fokustasten tun dort nichts.

## 2 Ergebnisse

| Stufe | Was | Ergebnis |
|---|---|---|
| 1 | Bau, Aufspielen, Neustart | `Registered IR keymap rc-h713-fd02`, `rc0` `[nec]`, WLAN da, alle Dienste aktiv |
| 2 | IR (Bluetooth am G-EU aus) | 13/13 Tasten + `0x66`, 46 Rahmen, 46 dekodiert; eine Journalzeile je Aktion |
| 3 | Bluetooth | erst **keine Verbindung**: die Fernbedienung war um 01:38 für den Test am HY310 gekoppelt worden, der Bund des G-EU veraltet; nach `forget` + `pair` (Links+Rechts): alle Tasten, Maus (455 Berichte), Mikro (543 Tonpakete) |
| 4 | Einblendungen über einem Test-Trapez | Marco: sitzen gerade zum verzerrten Bild; Claim `1280x720` |
| 5 | 81 Wechsel in 4,65 s | Warp 51,4 fps gegen 52,1 fps in Ruhe, 0 busy, 0 refused - die Einblendungen kosten nichts |
| 6 | Warp aus/an | Kopie 0,1 ms über dem Rohbild, Vorverzerren 3,4 ms danach |
| 7 | Signal weg und zurück | **erst nicht bestanden** (Abschnitt 3), mit Fix bestanden - beide Reihenfolgen, Journal und Marcos Auge |
| 8 | Standby (RTC 30 s) | geschlafen 29,7 s, Bild nach 6,5 s, h713-osd von selbst neu verbunden |
| 9 | Alpha (`osd-show --alpha2`) | "rechts weiß, links grau durchsichtig" - gerades Alpha wie am HY310 |
| 10 | Zeiten | Lautstärke 9,3, Stumm 13,4, Fokus 6,3, Eingang 5,4 ms (HY310: 13/15/8/7 ms, stärkeres Trapez) |

Über Bluetooth gemessen (HID Consumer Page): OK kommt als `0xc0041` "Menu Pick" → **`KEY_SELECT` (353)**, nicht `KEY_OK` wie
per IR; Fokus hoch `0xc00de` → F4; gehaltene Tasten wiederholen alle **~40 ms** (per IR ~130 ms) - die Lautstärke läuft beim
Halten von 100 auf 15 in 1,6 s. Der Mikro-Ton kam mit ~125 Paketen/s (≈7,5 kB/s), am HY310 waren es ~63/s - Ursache nicht
untersucht. Keine HCI-UART-Fehler in diesem Boot (am HY310 18, TODO 2.49).

## 3 Der Fehler in Stufe 7

h713-osd fragte h713-tv nur beim Zeichnen, was unter der Einblendung liegt (`osd picture`: `warped`, `ring`, `none`). Kommt
das Signal zurück, zeigt h713-tv erst das Rohbild über den Ring und übergibt etwa eine Sekunde später an den Warp. Ein
Stumm-Zeichen, das während des Verlusts gesetzt wurde, war für "keine Unterlage" gerade gezeichnet - und blieb so, als der Warp
übernahm, denn ein stehendes Zeichen bekommt kein neues Ereignis. Marco: "jetzt ist das Mute-Zeichen außerhalb deines Warps".
Am HY310 (`doku/193`) war das Zeichen vor dem Verlust gesetzt und damit vorverzerrt; es saß über dem Warp zufällig richtig.

Fix: solange etwas zu sehen ist und die Matrix nicht die Identität ist, fragt h713-osd alle 250 ms nach und zeichnet neu, wenn
die Antwort nicht zur Zeichnung passt - eine Journalzeile "the picture under the overlay is warped|straight now -- drawn
again". Ohne Trapez wird nichts gefragt. Gemessen: neu gezeichnet 1-53 ms nach dem Ring und 90-142 ms nach der
Warp-Übernahme. Zwei neue Rechner-Tests; der erste scheitert mit dem alten Code. Dabei die Statuszeile `matrix` berichtigt
("pre-distorted while the picture under it is warped" statt "over the warp", das auch bei `warp = off` stand).

## 4 Nebenbefunde

- **Warp-Bildrate am G-EU:** nach dem Start aus dem Bypass (Trapez zur Laufzeit gesetzt) lief der Warp mit ~50-56 fps und
  7-9 verspäteten Bildern je Sekunde, ohne Wärmedrosselung (58 °C, Kühlstufen 0, Lüfter dreht); Momentaufnahme CPU 1104 von
  1296 MHz, GPU 600 von 696 MHz, `sugov:0` 13 % eines Kerns. Nach einem Aus/An des Warps: 59,3 fps, 4 verspätete Bilder in 10 s,
  GPU 696 MHz. Verdacht: der GPU-Regler bleibt unten hängen - nicht gemessen, gehört zu TODO 2.47.
- **Kopplung:** `h713-remote-pair watch` verbindet einen bekannten Bund nur neu; ist er veraltet (die Fernbedienung an einer
  anderen Box gekoppelt), hilft Links+Rechts nicht - Marco: "sollte die nicht dauerhaft so bereit sein, dass ich mich jederzeit
  neu koppeln kann?" Stock tut das. TODO 2.54.
- **Konsole nach dem Schlaf:** auf beiden Geräten stehen danach viele Sonderzeichen im Login-Feld (Marco). Verdacht, nicht
  geprüft: die Fernbedienung ist für den Kernel auch eine Tastatur; Pfeile, F4/F5/F6 landen als Escape-Folgen im versteckten
  getty auf tty1 und werden sichtbar, wenn die Konsole erscheint. TODO 2.55.

## 5 Was auf dem G-EU bleibt

Kernel `main` `8f2c992` (FIT `25301ba1…`), dessen Module mit aic8800, h713-tv und h713-keys aus `main`, h713-osd mit dem Fix;
`warp.conf` und `power.conf` wieder wie vorher (Bypass, `short = poweroff`); die Fernbedienung ist jetzt am G-EU gekoppelt, nicht
mehr am HY310. Rückweg: `skripte/rueckweg-geu.sh` im Paket, dann Neustart.
