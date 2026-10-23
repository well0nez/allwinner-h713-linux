# 214 - Das Nebenprojekt Medien: Bluetooth nach dem Neustart, der Launcher beim Start, der Warp übernimmt das Signal sofort (17.10.2026)

**Kurz:** Fortsetzung von `doku/213`. Am HY310 mit Marco an der Box (17.10.2026, 10:07-10:45 UTC, Zweig `medien` a70bd6f bis 9adb7fc,
Kernel 6.18.38): (§1) Die Fernbedienung verbindet nach einem Neustart wieder, sobald ihre Kopplung frisch ist - **3 von 3 Warmstarts**;
der Fehler vom 16.10. war die veraltete Kopplung. Der dafür gebaute Fix (Kopplungsbitte über IR) ist **verworfen**: seine Annahme ist
falsch. (§2) Der Launcher steht beim Start vor dem HDMI-Bild statt 1,3 s danach. (§3) Der Warp übernimmt das Bild 0,2 s nach dem Signal
statt 1,1 s, und eine deckende Seite wird für die Wand gezeichnet, auch wenn darunter kurz der gerade Ring liegt: der Launcher springt
nicht mehr. **Nur am HY310 gemessen**; der HY300PRO-G-EU ist in keinem Punkt nachgemessen (`TODO.md` 2.94).

## 1 Bluetooth: die veraltete Kopplung, frisch gekoppelt, drei Warmstarts

Aufbau: HY300PRO-G-EU aus (die Fernbedienung war dort zuletzt gekoppelt), am HY310 je Schritt ein HCI-Mitschnitt (`btmon -w`, 60-90 s),
davor und danach `bluetoothctl info`, die Summe der `sunxi-ir`-Interrupts aus `/proc/interrupts` und das Journal von h713-keys,
h713-remote-pair und bluetoothd. Auf der Box lief der Fix 392bf41 (siehe unten) als Einzel-Deploy.

| Schritt (UTC) | Marco tut | gemessen |
|---|---|---|
| 10:12:20-10:13:22, Kopplung vom 11.10. (aus Sicherungen zurückgespielt) | Lauter, mehrmals | IR-Interrupts 2 -> 43, `Connected: no` davor und danach; im Mitschnitt **0** Advertising-Reports, ein Verbindungsversuch des HY310 endet `MGMT Connect Failed`, Status `Disconnected (0x0e)`; h713-remote-pair: "reconnect ...: no answer". Alle Tasten kamen über IR |
| 10:16:22 | (Taste) | eine kurze Verbindung: bluetoothd liest die GATT-Dienste, jeder Lesezugriff scheitert ("Request attribute has encountered an unlikely error"), dann getrennt - passt zu einem Schlüssel, der nicht mehr stimmt |
| 10:19:56-10:21:26 | LINKS+RECHTS (Kopplung, wie immer) bei vorhandener alter Kopplung | `Connected: no` (10:20:14); h713-remote-pair koppelt nicht, weil ein Bund existiert |
| 10:21:24 | - | `h713-remote-pair forget` auf dem HY310 |
| 10:21:28-10:22:58 | LINKS+RECHTS | 10:21:41 `found`, 10:21:44 `ok paired ... (trusted, bluez reconnects it)`, 10:21:46 h713-keys liest `/dev/input/event2` |
| Warmstart 1 (Boot 654f0d6b) | Lauter, 3 s, Lauter | erster Druck über IR (53,27 s), verbunden 55,00 s (**1,7 s** danach), zweiter Druck über Bluetooth; IR-Interrupts 2 -> 9 |
| Warmstart 2 (Boot 1d79b050) | Lauter, 3 s, Lauter | erster Druck 62,63 s, verbunden 63,60 s (**1,0 s**), zweiter über Bluetooth; IR 3 -> 11 |
| Warmstart 3 (Boot 60aa30a0) | Lauter, 3 s, Lauter | verbunden 23,70 s, **IR-Interrupts unverändert** (3 -> 3) |

**Schluss:** Mit einer frischen Kopplung verbindet die Fernbedienung nach jedem Neustart wieder; der erste Druck weckt sie und kommt
noch über IR. Der Fehler vom 16.10. (`doku/213` §6) war allein die veraltete Kopplung des HY310.

**Verworfen:** Der Fix 392bf41 sollte die veraltete Kopplung lösen, indem h713-remote-pair auf den IR-Code `0x0266` (`PRJ_BRC_PAIR`) der
Maus- und der Mikrofontaste hin den Bund vergisst und neu koppelt. Seine Annahme, diese Tasten bäten um eine Kopplung, ist nach Marco
falsch (17.10.2026): **die Kopplung beginnt mit LINKS+RECHTS; Maus und Mikrofon sind kein Kopplungsweg.** Der Fix kommt nicht in den Zweig.
Offen bleibt der eigentliche Mangel: LINKS+RECHTS muss auch bei vorhandener, veralteter Kopplung neu koppeln (`TODO.md` 2.92).

## 2 Der Launcher beim Start: vor dem HDMI-Bild (c89234f)

Vorher (Boot 043c163b, 10:07 UTC, `on_start = launcher`): h713-keys versucht den Launcher alle 5 s. Erster Versuch 5,2 s - h713-tv startet
erst 5,6 s, h713-osd antwortet `ok unseen`; HDMI-Bild 9,5 s (`plane 38 on`); nächster Versuch, Launcher offen 10,8 s. Marco sah 1,3 s
HDMI, dann den Launcher. Nachher (h713-keys versucht alle 0,5 s, erst sobald der Socket von h713-tv da ist; Boot nach 10:31:49 UTC):
Launcher offen **8,2 s**, HDMI-Bild 9,1 s darunter, h713-tv schaltet die Videoebene unter der deckenden Seite ab (10,1 s). Marco: kein
HDMI mehr vor dem Launcher. Hosttests h713-keys 50 von 50.

## 3 Der Warp übernimmt sofort, der Launcher springt nicht mehr (8d22136, 47a29d9)

Vorher (gleicher Boot wie §2 nachher): der Launcher wurde dreimal gezeichnet - 8,29 s entzerrt über Schwarz, 9,11 s gerade ("the picture
under the overlay is straight now"), 10,16 s wieder entzerrt ("... warped now"). Ursache: das Signal stand 9,06 s, h713-tv legte den Ring
gerade auf die Ebene (9,11 s), h713-warp übernahm erst 10,14 s - es versucht ohne Claim einmal je Sekunde, und das Ereignis
`SOURCE_CHANGE` war erst nach dem Lesen eines Formats abonniert; h713-osd zeichnete die deckende Seite für den geraden Ring darunter.
Marco: "als ob der Warp zweimal gemacht wird".

Korrektur: h713-warp abonniert das Ereignis, sobald der Knoten offen ist, und die Schleife wartet darauf (`POLLPRI`); h713-osd zeichnet eine
deckende Seite bei `warp = on` auch über dem geraden Ring für die Wand. Nachher (Boot 1ee3ed4b, 10:41:49 UTC): Launcher 8,28 s, Signal
9,53 s, gerader Ring auf der Ebene 9,60 s, **Warp übernimmt 9,74 s (0,2 s nach dem Signal)**, keine Zeile "drawn again" - der Launcher
wird einmal gezeichnet. Hosttests h713-osd 46, 15 übersprungen (der bisherige Test, der das Nachzeichnen über dem geraden Ring festhielt,
gilt jetzt für `warp = off`; ein neuer hält fest, dass die Seite bei `warp = on` stehen bleibt). Marco: in Ordnung; **beim Initialisieren
ist weiter etwas Grünes zu sehen** (`TODO.md` 2.93, nicht untersucht).

## 4 Nicht gemessen

- Der Start mit `On start: HDMI input`: dort bleiben nach §3 rund 0,14 s gerader Ring sichtbar, bevor der Warp übernimmt (aus den Zeiten
  geschlossen, nicht angesehen).
- Das Grün beim Initialisieren (§3): weder Zeitpunkt noch Ebene bestimmt.
- Alles am HY300PRO-G-EU.
