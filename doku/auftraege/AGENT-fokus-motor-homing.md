# Auftrag: Fokus + Motor-Homing auf unseren Kernel portieren - mit Ursachenklärung am Endschalter

Diese Datei ist der vollständige Auftrag. Du bekommst keinen weiteren Kontext. Lies sie ganz,
bevor du etwas anfasst.

---

## 1. Worum es geht

Das Projekt unter `/opt/Projekte/h713` portiert Linux-Mainline auf einen Allwinner-H713-Projektor
(Modell HY310). Der Beamer hat Schrittmotoren für **Keystone** und **Fokus**. Die Stock-Firmware
(Android/BSP-Kernel, ARM 32 Bit) fährt beide korrekt, unser Mainline-Port bisher nicht.

Es gibt zwei Aufgaben, und die erste ist die wichtigere:

### Aufgabe A - den Endschalter-Fehler an der Wurzel beheben

In unserem Treiber `drivers/misc/hy310-keystone-motor.c` (im Patch
`mainline/patches/kernel/0009-misc-add-hy310-keystone-motor.patch`) **findet die Homing-Routine den
Endschalter nie**. Der Pin PH14 liest immer LOW. Unsere eigene Notiz
`re/notes/motor.md` schließt daraus auf einen **Hardwaredefekt** am Testgerät und baut einen
Workaround ein: eine Schrittzahl-Obergrenze im Homing.

**Diese Schlussfolgerung ist widerlegt.** Unter der Stock-Firmware wird derselbe Schalter am
selben Gerät **gefunden**. Die Hardware ist also in Ordnung - **unser Treiber ist falsch**. Und der
Workaround ist nicht harmlos: weil das Homing nie ein Signal bekommt, fährt der Motor in den
mechanischen Anschlag und **nimmt Schaden**. Der Workaround ist Teil des Problems, nicht seine
Milderung.

Deine Aufgabe: **herausfinden, was Stock beim Lesen dieses Schalters anders macht**, und unseren
Treiber so korrigieren, dass er den Schalter genauso zuverlässig findet. Danach fliegt die
Schrittzahl-Obergrenze als *Sicherheitsnetz* nicht zwingend raus - aber sie darf nicht länger der
Mechanismus sein, auf dem das Homing beruht.

Behandle jede Aussage in `re/notes/motor.md` als **Hypothese, nicht als Befund**. Sie wurde unter
der falschen Annahme „Hardware kaputt" geschrieben. Das betrifft ausdrücklich auch: die Pinnummer
PH14, die Behauptung „active HIGH", die Behauptung „H713 PH11+ EINT ist kaputt, deshalb Polling",
und die Phasentabellen. Prüfe jede davon gegen Stock nach.

### Aufgabe B - den Fokus*motor* ansteuern (nicht den Autofokus)

Der Beamer hat neben dem Keystone-Motor einen **Fokusmotor**. Der soll auf unserem Kernel
ansteuerbar werden - manuell, über sysfs, so wie der Keystone-Motor. Aller Wahrscheinlichkeit nach
ist das dieselbe Treiberfamilie: gleiche `motor_ctr`-Bindung, gleiche Phasenlogik, gleiche
Endschalterfrage. Kläre und belege, wie der Fokusmotor in DTB und Stock-Treiber auftaucht - eigener
Knoten, zweite Instanz, anderer Pinsatz - und portiere ihn.

**Ausdrücklich NICHT dein Auftrag: der Autofokus.** Das Gerät hat eine Kamera, und Stock löst den
Fokus darüber automatisch aus; daher stammen die Symbole `autofocus`, `shake_for_vafocus` und
`camera_auto_focus_range` in `kallsyms.txt`. Dieser Regelkreis hängt an drei weiteren Baustellen
(Kamerasensor/MIPI-CSI, für den es in unserem Port noch gar keinen Pfad gibt; die Entscheidungslogik,
die vermutlich in einer Android-App liegt und eigenes APK-RE braucht). Das ist bewusst
zurückgestellt.

Konkret heißt das für dich: **verfolge diese Symbole nicht**, öffne keine APKs, portiere keinen
Kameratreiber. Wenn dir beim Reversen des Fokusmotors etwas über die Autofokus-Schnittstelle
auffällt - welche sysfs-Datei oder ioctl der Autofokus benutzt, um den Motor zu bewegen - dann
**notiere es in einem Absatz in deinem `BEFUND.md`** und arbeite weiter. Solche Notizen sind
wertvoll, weil der Autofokus später darauf aufsetzt. Aber der Motor muss so gebaut sein, dass er
ohne Kamera vollständig benutzbar ist.


---

## 2. Harte Regeln - Verstoß macht die Arbeit wertlos

**Kein Zugriff auf die Hardware.** Du fasst das Board **nicht** an. Konkret verboten:
`ssh root@192.168.8.141`, `ssh user@192.168.8.162`, `sonoff_ctl`, `tio`, `/dev/ttyACM0`, `scp` zum
Board, alles in `tftp/`. Der Grund ist nicht Bürokratie: an diesem Motor kann man mechanischen
Schaden anrichten, und es läuft parallel eine andere Sitzung auf demselben Gerät. Deine Arbeit ist
**Reverse Engineering und Code**. Der Hardwaretest passiert später und unter Aufsicht.

**Niemals in unseren Kernel bauen oder schreiben.** Verboten sind Schreibzugriffe auf:
`mainline/patches/kernel/`, `mainline/build/`, `tftp/`, `doku/78-*`, `doku/79-*`, sowie alles unter
`doku/nachtlog/`. Auch keine Memory-Dateien unter `~/.claude/`.

**Dein Ordner.** Du arbeitest ausschließlich in:

```
/opt/Projekte/h713/agenten/motor-fokus/
```

Den legst du selbst an. Dort gehört alles hin: deine idalib-Skripte, deine Notizen, dein
Kernel-Baum falls du einen brauchst, deine Bauartefakte. Lesen darfst du überall im Projekt.

**Abgabe als Vorschlag, nicht als Einbau.** Fertige Patches legst du in
`mainline/patches/vorschlaege/motor-fokus/` ab, zusammen mit einem `BEFUND.md`. Nur die
Hauptsitzung übernimmt Patches in die Serie. Das ist Projektkonvention und gilt ohne Ausnahme.

**Keine Commits, kein Push.** Nicht in diesem Repo, nicht in irgendeinem.

**Kein `sudo`.** Kein `apt` in laufenden Containern.

**Keine Workarounds.** Das ist die zentrale Projektregel. Wenn du eine Ursache nicht findest,
schreibst du das hin - du baust keine Umgehung, die die Symptome versteckt. Genau so ist der
aktuelle Motorfehler entstanden. Ein Patch mit falscher Begründung ist schlimmer als kein Patch.

**Belegen statt behaupten.** Jede technische Aussage in deinem Bericht bekommt ihre Quelle:
Funktionsadresse, Dateioffset, DTB-Property, Registerwert. „Vermutlich" und „sollte" sind keine
Befunde. Wenn du etwas nicht verifizieren konntest, schreib „nicht verifiziert" dran.

---

## 3. Werkzeug: idalib

IDA Pro 9.1 liegt unter `/opt/ida-pro-9.1`. Die Python-Anbindung ist eingerichtet und **getestet**:

```bash
~/.idapro/idalib-venv/bin/python -c "import idapro, ida_funcs, ida_name; print('OK')"
```

Falls das je fehlschlägt: die `.pth`-Datei in
`~/.idapro/idalib-venv/lib/python3.12/site-packages/idalib.pth` muss die zwei Zeilen
`/opt/ida-pro-9.1/idalib/python` und `/opt/ida-pro-9.1/python` enthalten.

Grundmuster:

```python
import idapro
idapro.open_database("/pfad/zur/datei", run_auto_analysis=True)
import ida_funcs, ida_name, ida_bytes, idautils, ida_hexrays
# ... arbeiten ...
idapro.close_database()
```

Für Dekompilat: `ida_hexrays.decompile(ea)`. Zum Auflösen von Namen: `ida_name.get_name_ea(0, "…")`.
Die MCP-Server für IDA sind derzeit tot - **nutze idalib direkt aus Python**, nicht die MCP-Tools.

Es gibt bereits fertig analysierte Datenbanken, die dir viel Zeit sparen:

- `re/ida/HY310/extracted/vmlinux.elf.i64` - **der Stock-Kernel**, hier steckt der Motortreiber
- `re/ida/HY310-DEV/display.bin` und `re/ida/IDA_hy310/display.bin` - die MIPS-Displayfirmware
  (für Aufgabe B evtl. relevant, für A eher nicht)

Öffne die `.i64` bevorzugt gegenüber dem Rohbinary - die Analyse ist schon gelaufen und Symbole
sind teils benannt.

---

## 4. Was wir schon wissen - dein Startmaterial

### Der Stock-Motortreiber

Die Symbole stehen in `re/vendor/HY310/extracted/kallsyms.txt` (32-Bit-ARM-Adressen). Der Treiber
heißt im Stock-Baum `motor-control.c`, Autor JingyanLiang @ Allwinner. Die für dich wichtigen:

| Adresse | Symbol | warum wichtig |
|---|---|---|
| `c05d6930` | **`motor_limiter_status`** | **liest den Endschalter - das ist die Schlüsselfunktion für Aufgabe A** |
| `c05d62c8` | `motor_control_fdt_parse` | liest die DTB-Werte, verrät die echten Pins und Pegel |
| `c05d6b6c` | `motor_run_up_mstep` | Fahrt aufwärts |
| `c05d6c90` | `motor_run_dn_mstep` | Fahrt abwärts |
| `c05d60a8` | `motor_mstep_work_handler` | die eigentliche Schrittschleife |
| `c05d5c7c` | `motor_set_phase` | Phasenausgabe |
| `c05d5c44` | `motor_set_stop` | Stopp |
| `c05d6048` | `motor_ctrl_no_limit_show` | es gibt einen „ohne Endschalter"-Modus - versteh, wann Stock den nutzt |
| `c05d5c1c` | `motor_limit_store` | |
| `c05d69d4` | `motor_limit_show` | |
| `c05d5f58` | `motor_back_step_store` | Rückschritte nach Anschlag |

Fang bei `motor_limiter_status` an und arbeite dich zu den Aufrufern vor.

### Die Stock-DTB

Der Knoten heißt **`motor_ctr`**. Ein früheres Skript zieht ihn heraus:
`re/work/HY310-DEV/extract_motor_dtb.py` (beachte: der Pfad darin ist ein alter Windows-Pfad, den
musst du anpassen). Die DTB-Blobs liegen unter `re/vendor/HY310/extracted/` als `.fex`-Dateien;
`dtbo.fex` und `config.fex` sind Kandidaten. **Prüf die Werte selbst nach** - die unten stehende
Liste stammt aus unserem Patchkopf und ist genau das, was möglicherweise falsch übernommen wurde:

```
motor-phase-num = 4, motor-step-num = 8, motor-cycle = 2
motor-phase-udelay = 1 (ms), motor-step-mdelay = 1 (ms)
active_level = 1 (active HIGH), motor_type = 0 (stepper)
CW:  01 09 08 0A 02 06 04 05
CCW: 05 04 06 02 0A 08 09 01
GPIO: PH4-PH7 (Phasen), PH14 (limiter-up)
```

Besonders verdächtig für den Endschalterfehler sind: **welcher Pin wirklich**, **welcher aktive
Pegel**, **ob ein Pull-up/Pull-down programmiert werden muss**, **welcher Pinmux-Modus** (Eingang
mit Pull ist nicht der Reset-Zustand), und ob Stock den Schalter über eine **andere GPIO-Bank**
(z. B. R_PIO) liest. Ein Pin ohne konfigurierten Pull liest gern konstant LOW - genau unser
Symptom. Aber verlass dich nicht auf meine Vermutung: hol den Befund aus `motor_control_fdt_parse`
und `motor_limiter_status`.

### Unser Treiber

`mainline/patches/kernel/0009-misc-add-hy310-keystone-motor.patch`, 925 Zeilen, legt
`drivers/misc/hy310-keystone-motor.c` an. Lies ihn ganz. Sein Kopfkommentar behauptet Dinge über
Stock („EINT kaputt", „udelay ist in Wahrheit ms"), die du gegen das Disassemblat prüfen sollst.

### Der Rest des Projekts

- `doku/10-hardware.md` - Hardwareübersicht
- `doku/50-befehle.md` - wie im Projekt gebaut wird (Container `h713-build`, `podman exec …
  build/build.sh kernel`). **Nutze diesen gemeinsamen Bau nicht**; leite dir daraus deinen eigenen,
  isolierten Bau in deinem Ordner ab.
- `re/notes/` - viele Handoff-Notizen aus der RE-Geschichte, unterschiedlich aktuell
- `doku/70-sackgassen.md` und `re/notes/DEAD-ENDS.md` - was schon widerlegt wurde. **Lies das**,
  bevor du eine Idee verfolgst; sie könnte dort schon beerdigt sein.

---

## 5. Vorgehen

1. **Erst reversen, dann coden.** Verstehe `motor_limiter_status` und `motor_control_fdt_parse`
   vollständig, inklusive der DTB-Werte, die sie tatsächlich lesen. Schreib auf, was Stock macht.
2. **Unterschied benennen.** Stell Stock und unseren Treiber Zeile für Zeile gegenüber an der
   Stelle, wo der Schalter gelesen wird. Der Fehler ist genau dort. Formuliere ihn in einem Satz.
3. **Gegenprobe.** Deine Erklärung muss beides erklären: warum Stock den Schalter findet **und**
   warum wir ihn nie finden. Erklärt sie nur eines von beidem, ist sie nicht fertig.
4. **Fix schreiben**, gegen die Ursache, nicht gegen das Symptom.
5. **Aufgabe B** angehen: den Fokus*motor* in DTB und Stock-Treiber belegen, dann portieren -
   ohne Kamera, ohne APK.
6. **Bauen** in deinem Ordner, gegen unsere Kernelversion, damit der Patch nachweislich übersetzt.
7. **Abgeben** nach `mainline/patches/vorschlaege/motor-fokus/`.

## 6. Abgabe

Nach `mainline/patches/vorschlaege/motor-fokus/`:

- **`BEFUND.md`** - auf Deutsch. Enthält: was Stock beim Endschalter tut (mit Adressen), was unser
  Treiber stattdessen tut, der Fehler in einem Satz, warum dein Fix beide Beobachtungen erklärt,
  was du zum Fokus*motor* herausgefunden hast, ein etwaiger Absatz zur Autofokus-Schnittstelle
  (nur als Notiz für später), und eine ehrliche Liste dessen, was du **nicht** verifizieren konntest.
- **die Patches**, im Stil der bestehenden Serie (unified diff gegen den Kernelbaum, sprechender
  Dateiname mit Nummernpräfix, aussagekräftiger Kopfkommentar **ohne** erfundene Begründungen).
- **`TESTPLAN.md`** - wie man am Gerät prüft, ob der Fix stimmt, in Schritten, mit dem jeweils
  erwarteten Ergebnis. Schreib dazu, an welcher Stelle der Motor Schaden nehmen könnte und wie man
  das im Test vermeidet. Diesen Test führst **du nicht** aus.

## 7. Wenn du nicht weiterkommst

Schreib den Zwischenstand in `BEFUND.md` mit dem, was du sicher weißt und wo genau es hakt. Ein
ehrlicher Teilbefund ist wertvoll. Eine erfundene Erklärung oder ein Workaround, der die Symptome
versteckt, richtet Schaden an - an diesem Gerät buchstäblich am Motor.
