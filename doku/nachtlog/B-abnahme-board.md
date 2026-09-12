# B — Board-Abnahme des ARISC-Treibers (Hauptsitzung, 23:32–00:05)

Kernel mit der vollständigen integrierten Serie (71 Patches). Prep **ohne** Schritt 1 und ohne das alte
Modul (`/root/prep_ohne_arisc.sh`, erzeugt per `sed` aus `prep_after_boot.sh`).

## Zwei fehlende Dateien — der erste Fehlschlag war banal

```
sun50i-h713-arisc 100000.arisc: Direct firmware load for h713-arisc.bin failed with error -2
sun50i-h713-arisc 100000.arisc: "hy310-edid.bin" ist 256 Byte statt 512 -- ignoriert
```

`/lib/firmware/h713-arisc.bin` gab es **gar nicht**, und die vorhandene `hy310-edid.bin` war die alte
256-Byte-Fassung (nur der 1.4-Block). Beide nachgelegt (`analyse/arisc/scp.bin` → `h713-arisc.bin`,
`analyse/arisc/hy310-edid.bin` → 512 B). Paket B hatte genau das in seinem Log angekündigt.

**Danach sofort grün:**

```
sun50i-h713-arisc 100000.arisc: ARISC-Startup-Notify quittiert:
    rojector-tv303-android11-v1.3-3-g293ff69
```

debugfs `status`: `startup_notify: acked`, `arisc: running`, `edid_firmware: hy310-edid.bin loaded`.
**Das ist Paket Bs Kernkriterium** — Firmware laden, Reset lösen, Notify lesen und quittieren, alles im
Treiber, ohne `arisc_load.py` und ohne Doorbell-Puls.

## Der eigentliche Fehler — offline vorhergesagt, am Gerät bestätigt, in zwei Schritten behoben

`echo edid > /sys/kernel/debug/h713-arisc/cmd` lieferte **`portmap 0,1,2 rc=-110`** — Zeitüberschreitung im
**zweiten** Schritt der Sequenz. Der Prüfagent des Integrations-Workflows hatte das mit Disassembly-Beleg
vorhergesagt: `arisc_wait_handler()` nahm an, der `0x11`-Gruppenhandler kopiere **immer** alle 65 Nutzlastbytes
in den Scratch `0x117320`. Tatsächlich **nullt** er ihn unbedingt (`memset(0x17320, 0, 0x41)` bei `0x11550`)
und schreibt danach je nach `sub_cmd_hi` unterschiedlich viel — bei `HostHDMIMAP` (hi = 0) **gar nichts**.
Der Treiber wartete also auf einen Zustand, den die Firmware nie herstellt.

**Fix Schritt 1:** Erwartungswert aus `sub_cmd_hi` ableiten (`arisc_expected_scratch()`), und die Vorbelegung
auf das Komplement **des erwarteten** Inhalts umstellen — sonst ginge „unverändert" bei den Befehlen, deren
Erwartung „alles null" ist, als „bearbeitet" durch. Dazu ein `dev_dbg`, das das erste abweichende Byte nennt.

Damit kam die Sequenz bis **`set-edid rc=-110`** — also bis `UpdateEDID`, dem Hochladen der acht Fragmente.

**Fix Schritt 2 — und hier hat das Gerät den Prüfer korrigiert.** Die Debug-Zeile sagte:

```
scratch mismatch at byte 64: got 0x2c, want 0x00
```

Der Prüfer hatte aus der Disassembly gelesen, `UpdateEDID` kopiere `0x40` = 64 Bytes und Byte 64 bleibe aus
dem `memset` null. Das Gerät sagt: Byte 64 trägt `0x2c` — und `0x2c` ist genau `EDID[63]` von Fragment 0 in
`analyse/arisc/hy310-edid.bin`. Die Firmware kopiert also **65** Bytes. Für `hi == 1` gilt damit die
ursprüngliche Annahme des Treibers; falsch war sie nur für alle **anderen** Unterbefehle.

Das ist der Grund, warum der Fix die Fallunterscheidung braucht und nicht einfach „mehr" oder „weniger"
kopieren darf — und ein gutes Beispiel dafür, warum eine Disassembly-Lesart eine Messung nicht ersetzt.
Die Begründung steht jetzt im Quelltext an der Fallunterscheidung, mit dem gemessenen Wert.

## Stand

- Handshake und Firmware-Laden: **abgenommen**.
- EDID-/HPD-Sequenz aus dem Kernel: nach Fix 2 im Bau; Ergebnis siehe unten bzw. `79`.
- Der Doorbell-Puls ist in diesem Treiber **nicht** enthalten, und der Handshake lief trotzdem — damit ist
  auch die Restunsicherheit aus `B-puls-messung.md` erledigt: der Beweis hing genau daran, dass ein Lauf
  **ohne** jeden Puls durchkommt.

## Fix 2 wirkt — und der Fehler wandert weiter nach hinten

Nach der Korrektur auf 65 Bytes für `hi == 1`: `set-edid rc=-71` statt `-110`, **keine** `scratch mismatch`-
Zeile mehr. Die Scratch-Prüfung geht also für **alle** Unterbefehle durch, einschließlich der acht
EDID-Fragmente. Der Fehler liegt jetzt am Ende der Sequenz, bei der Statusabfrage:

```
sun50i-h713-arisc 100000.arisc: Antwort auf 0x0215: 4 Woerter, 2 uebernommen
sun50i-h713-arisc 100000.arisc: CheckEDIDUpdateStatus antwortet a5 00 01 08 00 00 00 00
                                statt ff f8 01 01 ...
```

**Zum Vergleich, was das Userspace-Skript in derselben Nacht auf ARM-RX ch1 gesehen hat** (aus dem Lauf um
22:04):

```
ARM-RX ch1 (8 W): a5 01 01 48 00 00 00 00 ff f8 02 41 00 00 ff ff ff ff ff ff 00 5e 78 43 48 21 03 ...
```

Dort steht `a5 01 01 48` als **Rahmenkopf** und die Nutzlast `ff f8 02 41 …` **dahinter**. Der Treiber
vergleicht dagegen ab Wort 0 — er nimmt den Kopf für Nutzlast. Beim Treiberlauf ist die Nutzlast zudem
**null**, beim Skript nicht.

Damit sind zwei Dinge zu klären, und beide gehören zusammen untersucht, nicht geraten:
1. **Rahmenversatz:** vergleicht der Treiber ab dem falschen Wort? Der Kopf `a5 .. 01 ..` sieht in beiden
   Läufen gleich strukturiert aus, die Nutzlast beginnt beim Skript erst bei Wort 2.
2. **Leere Nutzlast:** selbst mit richtigem Versatz stünde beim Treiberlauf nichts da. Das deutet darauf hin,
   dass die Firmware das EDID **nicht übernommen** hat — die bestandene Scratch-Prüfung belegt nur, dass der
   Handler die Nutzlast gesehen hat, nicht dass er sie gespeichert hat. Der Nachtplan nennt dafür eine
   Eigenheit (Stufe 4): „die Firmware gibt das EDID **erst nach Fragment 7** aus (`[0x1723E]`, danach Gate
   `[0x1723F]`)". Diese beiden Bytes wären als Nächstes zu lesen.

## Bewertung

Paket B ist **deutlich weiter als am Abend**, aber **nicht abgenommen**:

| Teil | Stand |
|---|---|
| Firmware laden, Reset lösen, Notify quittieren | **grün**, ohne `arisc_load.py`, ohne Doorbell-Puls |
| `ResetEDIDModule`, `HostHDMIMAP`, `SetEDIDVersion` | **grün** (nach Fix 1) |
| acht `UpdateEDID`-Fragmente | **grün** (nach Fix 2) |
| `CheckEDIDUpdateStatus` | **rot** — `-EPROTO`, Antwort `a5 00 01 08 …` |
| `RequestEDID`, `SetEDIDAudioMode`, `SET5VFlag`, HPD | nicht erreicht |

Der Weg dorthin war in beiden Schritten derselbe: eine belegte Vorhersage, eine Messung, die sie prüft, und
eine Messung, die sie an einer Stelle **widerlegt**. Genau dafür ist der `dev_dbg` mit dem ersten
abweichenden Byte da — ohne ihn hätte Fix 2 nicht in einem Anlauf gefunden werden können.

---

## Korrektur 08:45 — was die Abnahme vom 08:27 wirklich zeigt

Die Gegenprüfung des Rest-Workflows hat zwei meiner Schlüsse widerlegt. Beide Korrekturen stehen hier,
weil die Abnahme sonst mehr behauptet, als sie trägt.

**1. `portmap: 0,1,2` ist kein Beleg für den Fix.** Die ROM-Vorgabe der Karte bei `0x15edc` ist
byteweise `01 10 00 01 | 02 20 01 02 | 04 30 02 04` — Pin 0/1/2, also **die Identität**, und damit
genau das, was `HostHDMIMAP 0,1,2` schreibt (selbst nachgeschlagen in
`analyse/arisc-frame/full-disasm.txt`). Eine Karte, die `0,1,2` zeigt, kann also ebensogut nie
beschrieben worden sein. Als Abnahmekriterium taugt sie nicht.

**2. `arisc_wait_portmap()` kann den Fehlerfall nicht erkennen.** Aus demselben Grund: die Funktion
wartet darauf, dass die drei Sätze Pin und `1 << Pin` tragen — und das tun sie schon vor dem Befehl.
Sie kehrt in der ersten Runde zurück, ohne je zu warten. Der Wächter ist in dieser Fassung
**unfalsifizierbar**; er meldet Erfolg, ob der Handler gelaufen ist oder nicht.

**Was die Abnahme trotzdem trägt:** der beobachtbare Ausgang. Mit dem alten `0091` blieb der
Zuspieler nach der Treiber-Sequenz reproduzierbar `disconnected`; mit dem neuen ist er
**`connected`, 1920x1080**, das EDID gültig, die Sequenz nach 28,8 s abgeschlossen — ohne Skript.
Das ist neu und gemessen. **Ungeklärt bleibt, wodurch.** Die Ursachenanalyse aus der Disassembly ist
schlüssig, aber der Wächter, der sie am Gerät nachweisen sollte, weist nichts nach.

**Zu tun, bevor `0091` als fertig gilt:** den Wächter falsifizierbar machen — die drei Sätze vor
`arisc_send()` mit einem Wert belegen, der das Ziel nicht sein kann, so dass ein Treffer beweist,
dass der Handler geschrieben hat. Erst dann trennt die Prüfung „gewonnen" von „war ohnehin schon so".

---

## Abnahme 09:02–09:10 — **B ist abgenommen**, und der Nachweis trägt jetzt

Kernel mit dem falsifizierbaren Wächter und `HPD_DOWN_MS 200`, Kaltstart 09:02:16.

### Der Ablauf aus dem Kernel

```
[16.60] hdmirx: Init-Sequenz vollstaendig (22 Aufrufe)
[17.08] arisc:  EDID uebernommen, Status ff f8 01 01 01 00 07 fe, Ausgabe-Gate [0x1723f]=1
[17.42] arisc:  EDID zurueckgelesen (64 B): 00 ff ff ff ff ff ff 00 5e 78 43 48 21 03 00 00
[17.65] arisc:  EDID/HPD-Sequenz auf Port 0 abgeschlossen
[17.66] hdmirx: /dev/video1, Slot-Quelle: AFBD vsync notifier (GIC 142)
```

Zuspieler: **`connected`, 1920x1080**. `0x07091014 = 0x06` — Bit 0 gelöscht, der Stock-Wert.

**A2 am Gerät bestätigt:** mit `HPD_DOWN_MS 200` statt 10 000 ist die Sequenz nach **17,65 s** durch
statt nach 28,8 s — elf Sekunden gespart, EDID unverändert gültig, Quelle verbindet sich.

### Der Nachweis, der vorher fehlte

Die alte Prüfung war unfalsifizierbar (Korrektur 08:45). Die neue belegt drei Dinge, jedes einzeln
gemessen:

| Kontrolle | Ergebnis |
|---|---|
| **A — schreibt sonst jemand in die Karte?** Satz 0 von Hand auf `0xff`, 5 s warten | `0x11724a = 0xFF`, `0x11724b = 0xFF` — **unverändert**. Niemand sonst schreibt dort. |
| **B — schreibt die Firmware wirklich?** Karte vorbelegt, dann `echo "portmap 0 1 2" > cmd` | `rc=0`; Satz 1 `Pin=1 Bit=2`, Satz 2 `Pin=2 Bit=4`. Der Übergang `0xff → {0,1,2}` ist für alles außer einem Firmware-Schreibzugriff unerreichbar. |
| **C — kann die Prüfung überhaupt scheitern?** alle drei Sätze von Hand vergiften, **ohne** Befehl | debugfs zeigt **`portmap: 255,255,255`**. Der Fehlerzustand ist sichtbar; danach stellt der Befehl `0,1,2` wieder her. |

Damit ist `portmap` **kein** Wert mehr, der gar nicht anders ausfallen könnte — genau der Mangel,
den die Gegenprüfung an der 08:27er Abnahme gefunden hatte.

### Ein eigener Lesefehler, damit er nicht wiederkommt

Beim Nachlesen der Karte habe ich `0x17248` als **Adresse** statt als **Offset** benutzt und
`0x00017248` gelesen — dort steht Null. Das sah nach einem Widerspruch zwischen debugfs und SRAM aus
und war keiner. Die Karte liegt bei **`0x00117248`** (ARISC-SRAM ab `0x00100000`). Die Einzellesungen
davor waren richtig, nur die Schleife nicht.

### Was offen bleibt

Der eine Lauf aus `B-hpd-luecke.md`, in dem `0x07091014 = 0x03` ein **verbundener** Zustand war, ist
weiterhin nicht erklärt. Der Registerwert allein bestimmt den Zustand nicht — das steht so auch in
`doku/82` §12.7 und bleibt richtig.
