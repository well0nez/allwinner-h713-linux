> **Archiv.** Dies war `doku/00-STATUS.md` bis zum 08.09.2026, 10:50 (Schichtung aus dated Kopfblöcken über einem Rumpf vom 07.09.). Der aktuelle Einstieg ist [`../00-STATUS.md`](../00-STATUS.md).

# H713-Projekt — Status

> **08.09.2026, 10:20 — Restpunkte erledigt: 1366×768, 5:4 mit Balken, Bildmodus-Menü + Presets, Template-Unit; Plan/Ergebnisse [`99`](../99-plan-restpunkte-20260908.md), Protokoll [`S13`](S13-restpunkte.md).**
> Serie **102 Patches** (`0130`–`0133`), guter Stand `GUT-a3097ce7`; `hy310-tv` `00460d4a` als `hy310-tv@video1`
> (`BindsTo`), neu `hy310-tv ctl preset NAME` und `ctl aspect NAME`. Befunde: der Ring hat Zeilenabstand
> rowbyte·16 (`0x924`), nicht „Breite" (`0131`); 5:4 steuert allein Descriptor-Wort 35 (`0133`, [`S15`](S15-re-aspect-regel.md));
> `SetPictureMode` ändert keinen Regler, `Get*` sind Stubs ([`S14`](S14-re-picture-mode.md)). Fehlfall der
> ersten Freigabe provoziert (Journal-Trigger), Wartepfad `0130` greift. **10:25:** `hy310-tv` sendet beim Start
> `preset standard` und die Stock-Gammakurve 2,2 (`-p`/`-g`); Sichtprüfung der Kurve durch Marco offen.

> **08.09.2026, 02:00 — Grünstich und Kippen gelöst, `hy310-tv` als Dienst mit Steuerkanal, Handoff: [`97-handoff-20260908.md`](../97-handoff-20260908.md).**
> Serie **98 Patches** (`0123`–`0129`), guter Stand `GUT-e2f6be7c` (`tftp/` und `mainline/build/modroot.GUT-*`).
> `hy310-tv ctl status|off|auto|set …` ([`S12`](S12-hy310-tv-review.md)). VESA-Modi laufen mit 60 Hz (S11, Nachtrag 07:55).
> `0123`: der Eingangs-Farbwandler der Aufnahme (`0x06940824` Bit 31) wird nach jedem Descriptor-Neubau über
> `SetVideoRange` zurückgesetzt — vor der Freigabe, kein grüner Rahmen. `0124`: die Slots der MIPS→ARM-Rückrufe
> werden freigegeben — vorher hing die Firmware nach 19 Rückrufen („Kippen nach 4–5 Wechseln"). Abnahme: acht
> Auflösungswechsel, 27 Rückrufe, Ring und Wand sauber ([`nachtlog/S11`](S11-gruenstich-ursache-und-callback-slots.md)).
> Offen: Konsolen-Sperre/`H713_TV_SKALIERTEST` in `hy310-tv`, übrige Auflösungen.

> **08.09.2026 — Skalierung laeuft, Handoff: [`97-handoff-20260908.md`](../97-handoff-20260908.md).**
> 720p wird korrekt aufs Panel hochskaliert; offen sind ein Gruenstich und ein Kippen nach vier bis
> fuenf Wechseln. Neu erschlossen: die Firmware-Shell ([`98`](../98-mips-shell.md)) und die
> Gesamtdarstellung der Anzeigekette ([`96`](../96-anzeigekette.md)). Fokusmotor abgeschlossen und
> geparkt ([`94`](../94-fokusmotor-endschalter.md)).
**Einstiegspunkt.** Stand 2026-09-07, 12:00 — nach dem Nachtlauf 06./07.09. **und** den Board-Abnahmen
des Vormittags (zuletzt Kaltstart 11:42, Freigabe `0099`). Die Fassung von gestern 23:09 stammte von **vor** allen Abnahmen; die Stellen, die sich
dadurch geändert haben, sind unten als *korrigiert 07.09.* gekennzeichnet.

## Das Wichtigste zuerst: der Bildpfad läuft aus dem Kernel

Bis gestern kam das HDMI-Bild über Poke-Skripte (`viddec_descriptor.py`, `afbd_source0.py` auf `/dev/mem`).
Seit der Nacht steht es aus dem Treiber, und das ist am Gerät abgenommen:

* **Plane 38 (`video-0`) zeigt den Capture-Ring.** KMS, Format NV16, Betriebsart `hdmi-ring`; die Ring-Folge
  wandert (`0x05600070` läuft über die vier Slots, statt wie im Skript festgenagelt zu sein). Patch `0093`,
  [86-video-plane-nv16.md](../86-video-plane-nv16.md).
* **`/dev/video1` liefert Bilder.** `sun50i-h713-hdmirx` (`0094`): **60 von 60** Bildern NV16M, das
  rekonstruierte Bild ist ein **pixelgenauer Screenshot** der Quelle; Slot-Quelle ist der AFBD-Vsync-Notifier
  (GIC 142) mit 287 gezählten Ereignissen. [88-v4l2-hdmirx.md](../88-v4l2-hdmirx.md).
* **HPD/EDID kommen aus dem Kernel.** `sun50i-h713-arisc` (`0091`): Zuspieler meldet `connected, 1920x1080`,
  die Sequenz ist nach **17,65 s** durch — ohne `arisc_edid_init.sh`, ohne Doorbell-Puls.
  [82-arisc-treiber.md](../82-arisc-treiber.md).
* **Gamma/CTM sitzen am CRTC** (`0095`) und färben **beide** Pfade: Konsole und Video.
* **`hy310-tv` läuft am Gerät**, das Bild kommt: der Trockenlauf nennt `/dev/video1`, `card1`, CRTC 36,
  Plane 38, `hdmi-ring`, `signal vorhanden`, und die Wand **folgt der Quelle** — Zuspieler gedimmt,
  **48,16 %** der Bildpunkte geändert ([nachtlog/E2-freigabe.md](E2-freigabe.md)).
  *(Korrektur 07.09.: hier stand „Wand mean 131,2". Die Zahl trägt nicht — derselbe ROI misst für den
  **eingefrorenen** Rahmen nach `xrandr --off` mean 130,4, siehe [88-v4l2-hdmirx.md](../88-v4l2-hdmirx.md)
  Z. 496 und [nachtlog/F-abnahme-und-callback-luecke.md](F-abnahme-und-callback-luecke.md).)*

**Das Protokoll dazu ist [79-nachtlog-20260907.md](../79-nachtlog-20260907.md)** mit den Teillogs je Paket in
[`doku/nachtlog/`](./). Dort steht der jeweils genaue Messwert; diese Seite nennt nur das Ergebnis.
Die Fachseiten sind [81](../81-pq-datenmodell.md) bis [89](../89-composition-block.md).

## Stand je Paket

„Abgenommen" heißt hier: **am Gerät gemessen, mit einem Kriterium, das hätte scheitern können.**

| Paket | Stand | Beleg |
|---|---|---|
| **A** cstengers 17 Patches | **abgenommen** | Kernel bootet, Konsole auf der Wand, Plane `video-0` (ID 38) gelistet, Bild farbrichtig **und live**: Gamma-Reiz 7,26 % der Bildpunkte, Rückkehr 0,00 % — [nachtlog/A-abnahme-board.md](A-abnahme-board.md) |
| **B** ARISC-Treiber `0091` | **abgenommen** | Zuspieler `connected 1920x1080` aus dem Kernel, Sequenz nach 17,65 s. Der Wächter wurde dafür erst **falsifizierbar** gemacht (Vorbelegung `0xff`) — [nachtlog/B-abnahme-board.md](B-abnahme-board.md), [nachtlog/B-waechter-falsifizierbar.md](B-waechter-falsifizierbar.md) |
| **C** `cpu_comm`-Kernel-API `0092` | **abgenommen, mit einem Vorbehalt** | `THal_Vp_SetSource 3` aus dem Kernel über debugfs → `ok`; `/dev/cpu_comm` bleibt daneben nutzbar — [83-cpu-comm-api.md](../83-cpu-comm-api.md). **Vorbehalt:** die C-Vorschrift nennt **drei** Zwecke ([nachtlog/C-cpu-comm.md](C-cpu-comm.md) Z. 350), der dritte — `SignalChange` **im Kernel-Handler** — ist **nicht** belegt; er ist genau das, was die Callback-Lücke betrifft |
| **D** Video-Plane NV16 `0093` | **abgenommen** | fünf Abnahmeteile, darunter der **reproduzierte Fehlerfall** und die Markenmessung: `0x05600044` geht aus jedem Vorzustand auf `0x0F00`, beim Abschalten zurück auf `0x0780`. Vorgeschichte und Vorschrift: [nachtlog/D-abnahme-board.md](D-abnahme-board.md), [nachtlog/D-cstride-befund.md](D-cstride-befund.md), [nachtlog/D-cstride-fix.md](D-cstride-fix.md) §4; die Nachabnahme selbst stammt aus der Board-Sitzung vom Vormittag, ihr Teillog entsteht noch |
| **E** V4L2 `0094` | **abgenommen** | 60/60 Bilder, rekonstruiertes Bild pixelgenau, 287 Vsync-Ereignisse — [nachtlog/E-v4l2.md](E-v4l2.md), [nachtlog/DE-vsync-notifier.md](DE-vsync-notifier.md). *(Der zwischenzeitliche Rückschritt „probt nicht mehr" ist behoben — Hotplug-Rennen in `0091`, [nachtlog/B3-hpd-rennen.md](B3-hpd-rennen.md); Kaltstart 11:42 ohne Handgriff.)* |
| **F** `hy310-tv` | **läuft am Gerät**, Bild kommt | ein echter Fehler dabei gefunden, der nur durchs Ausführen zu finden war (siehe unten) — [nachtlog/F-abnahme-und-callback-luecke.md](F-abnahme-und-callback-luecke.md) |
| **G** `hy310-pq` | **fertig** | Gamma-LUT **bitgleich** zum Legacy-Rechner — [nachtlog/G-pq.md](G-pq.md) |
| **H** Gamma/CTM `0095` | **abgenommen** | invertierte LUT: **100,00 %** der Bildpunkte auf der Konsole, Rückkehr **0,00 %**; und **86,56 %** auf dem **Video**-Pfad — damit ist die in `H-gamma.md` offen gelassene Frage beantwortet: **ja, beide Pfade** — [nachtlog/H-abnahme-board.md](H-abnahme-board.md) |
| **I** PQ-Controls (V4L2) | **nicht begonnen** | Grundlage steht (K5 am Gerät); `V4L2_CID_BRIGHTNESS` **anbieten, Bereich 0…100** — gemessen, siehe unten |

`series` hat **75 Zeilen** (Stand 07.09., 11:31 — die Zahl wächst gerade, bitte gegen
`mainline/patches/kernel/series` prüfen). Die Patches der Nacht: `0091` ARISC, `0092` `cpu_comm`-Kernel-API,
`0093` NV16-Plane, `0094` `sun50i-h713-hdmirx`, `0095` Gamma/CTM, dazu `0096` (DT-Knoten `tvcap@50c0000`) und
`0097` (`cpu_comm`-ABI-Korrekturen) als Nachtrag zweier Handänderungen. Vom Vormittag: `0098` (Rücknahme der
Callback-Anmeldung) und `0099` (Freigabe der Capture nach dem Descriptor) — beide am Gerät gelaufen; dazu seit
11:31 `0100` (Callback-Anmeldung, **zweiter Anlauf** — Registrierung weg vom Bring-up-Pfad) und `0101`
(PQ-Controls, Paket I), **beide offline entstanden und noch nicht am Gerät**
([`nachtlog/STAND-JETZT.md`](STAND-JETZT.md), `mainline/patches/vorschlaege/`).
Bauen **nur** im Container `h713-build` ([50-befehle.md](../50-befehle.md)).

## Was gerade offen ist

**Woran gerade gearbeitet wird: die Callback-Lücke.** Alles andere unten ist notiert, nicht in Arbeit.

**Die Callback-Lücke — der Rückschritt daraus ist behoben, die Lücke selbst nicht.** Die Firmware feuert `CallbackOfSignalChange` /
`NotifySignalChange` (im elog belegt), die **Kernel-Handler zählen 0**. Ursache gefunden:
`cpu_comm_register_callback()` trug den Handler nur in eine treiberinterne Tabelle ein und meldete die Routine
nie in der **Routinentabelle im Shared Memory** an — die Firmware sucht dort, findet nichts und schickt gar
nicht erst ab ([nachtlog/CALLBACK-luecke.md](CALLBACK-luecke.md)). Der Fix ist gebaut (`0092`, `0094`)
und **am Gerät durchgefallen** — E probte danach nicht mehr. Er ist mit `0098` **zurückgenommen**
(chirurgisch: nur `cpu_comm_api.c`, `sun50i-h713-hdmirx.c`, `h713-cpu-comm.h`; die Regel-1-Korrekturen in
`0093`/`0095` bleiben). *Korrektur 07.09. vormittags:* von den drei Fehlschlägen gehörte **einer nicht dazu** —
Lauf 2 (`-EBUSY` in der EDID-Folge) war ein davon unabhängiges Hotplug-Rennen in `0091` und ist behoben
([nachtlog/B3-hpd-rennen.md](B3-hpd-rennen.md)). **E probt wieder**, vom Kaltstart an und ohne
Handgriff (11:42, [nachtlog/E2-freigabe.md](E2-freigabe.md)). Übrig bleiben zwei echte Fehlschläge
(`SetPortMap -110`, `THal_Vp_DisableBlackScreen -110`); der Callback-Fix hat damit **einen** sauberen Versuch
verdient. **Die Lücke selbst ist offen**, und daran hängt:

* **F fällt bei Signalverlust nicht auf die Konsole zurück** (die Wand behält das eingefrorene Bild).
* **`V4L2_EVENT_SOURCE_CHANGE` feuert nie** — in *allen* Läufen von `hdmirx_test`, auch dort, wo das Signal
  nachweislich weg war.
* **Ein Auflösungswechsel der Quelle ist über V4L2 nicht bemerkbar.** Er erzeugt **kein** `SOURCE_CHANGE`,
  und der Ring enthält dann zerrissenen Inhalt (720p dreifach nebeneinander über altem 1080p-Inhalt).
  Der Rückweg auf 1920×1080 ist sauber, ohne Zutun — [nachtlog/A6-4-aufloesungswechsel.md](A6-4-aufloesungswechsel.md).
  **Neu am 07.09., 12:20:** *erkennbar* wäre er inzwischen ohne Callback — `0x06940928` trägt in den unteren
  16 Bit die Zeilenzahl des eingerasteten Signals (`0x438` = 1080, `0x2D0` = 720) und in Bit 31, ob die
  Firmware überhaupt einrastet. Ein Quellenwechsel als Rettungsweg trägt aber **nicht**: die Firmware zieht
  mit, die Anzeigeseite (Ring-Zeilenabstand, Zuschnitt, Descriptor) bleibt auf 1080p, das Bild bleibt
  zerrissen — [nachtlog/E3-geometrie-im-register.md](E3-geometrie-im-register.md).
* Da die Init-Sequenz und der EDID/HPD-Anstoß **am Probe von `0094`** hängen (doku/88 §2/§3), betrifft ein
  ausfallender Probe mehr als nur `/dev/video1`.

**Zwei Rückwege liegen fertig daneben** ([nachtlog/STAND-JETZT.md](STAND-JETZT.md)), nichts muss neu
gebaut werden.

> **Die Namen wechseln mit jedem guten Bau.** Der gute Stand heißt `tftp/h713-kernel-netboot.fit.GUT-<hash>`
> **und** `mainline/build/modroot.GUT-<hash>/` mit demselben Hash; ältere Paare werden weggeräumt. **Immer
> zuerst nachsehen, welches Paar wirklich dasteht** (`ls tftp/*.GUT-* mainline/build/modroot.GUT-*`) — im
> Lauf des 07.09. sind schon drei Hashes durch die Dokumente gewandert, und zwei davon gibt es nicht mehr.

* **Bevorzugt, aktueller guter Stand (11:26–11:30):** `tftp/h713-kernel-netboot.fit.GUT-e40c7e8e` +
  `mainline/build/modroot.GUT-e40c7e8e/` (26 Module) — mit `0098`, dem Hotplug-Fix und der Freigabe `0099`.
* **Ganz zurück (letzter Halt):** `tftp/h713-kernel-netboot.fit.GUT-e39777bf` +
  `mainline/build/modroot.GUT/` (26 Module) — kostet die Regel-1-Korrekturen, den Hotplug-Fix **und** die
  Freigabe.

Als Patch liegt die Rücknahme zusätzlich unter
`mainline/patches/vorschlaege/rueckweg/0098-revert-cpu-comm-kernel-callback-registration.patch` (in `series`
ist sie als `0098` bereits aufgenommen). Momentaufnahme aller 73 Patchdateien:
`patches-snapshots/20260907-100635/`.

**Weitere offene Punkte:**

* ~~**`SetBrightness` wirkt nicht.**~~ **Erledigt 07.09., 11:25 — die Aussage war falsch.**
  `SetBrightness` **wirkt**: std im ROI 12,6 → 22,7, p95 151 → 185, monoton von 0 bis 100 und darüber exakt
  flach; drei Werte je zweimal angefahren, jedes Mal dieselben Kennzahlen
  ([nachtlog/I0-helligkeit-nachgemessen.md](I0-helligkeit-nachgemessen.md)).
  **Der Stellbereich ist 0…100, nicht 0…255** — gemessen, nicht erschlossen. Für **Paket I** heißt das:
  `V4L2_CID_BRIGHTNESS` mit Bereich 0…100 **anbieten**. Die alten „0,00 %" waren eine ungültige Messung: sie
  lief gegen eine fast weiße Vorlage, und Helligkeit wirkt im Schwarzbereich — das Kriterium konnte nicht
  anschlagen. `mp_dci_data is NULL` nennt das DCI- und das Gamma-Modul, nicht die Helligkeit; als Erklärung
  hat es nie getragen.
* **Ein Lauf, in dem `0x07091014 = 0x03` ein *verbundener* Zustand war, ist unerklärt.** Der Registerwert
  allein bestimmt den Zustand nicht (doku/82 §12.7).
* **Zwei Altfehler in `cpu_comm`** sind benannt und **bewusst liegen gelassen**: `RemovePidRoutines()` liest
  die pid bei `+28` statt `+4` (räumt also nichts ab), und die Kanalprüfung in `Comm_Add2NewCallFifo()` trägt
  nur für pids < 4096. Beides gehört in eine eigene, messbare Sitzung.
* **`hy310-pq` gibt heute den Registerwert aus, nicht das RPC-Argument.** Die Firmware rechnet
  `Gain = floor(Argument × 1,28)` selbst; Sättigung 60 ergibt am Gerät `0x4C`, nicht `0x5C`.
* `CTM` gegen Stock ist **nicht** geprüft — es gibt keinen Vendor-Fall zum Vergleichen.

## So kommt heute ein Bild an die Wand *(Rezept geändert 07.09.)*

0. **Voraussetzung, sonst scheitert `0091` still:** `/lib/firmware/h713-arisc.bin` (aus
   `analyse/arisc/scp.bin`) und `/lib/firmware/hy310-edid.bin` **mit 512 Byte** (die alte 256-B-Fassung
   ignoriert der Treiber und sagt es laut). Ein frisch gebautes Rootfs kommt ohne beide hoch, und **kein
   Rezept legt sie an** — genau daran ist der erste Abnahmeversuch gescheitert
   ([60-offen.md](../60-offen.md), „Zwei Dateien liegen nur von Hand auf dem Board").
1. Kaltstart (`sonoff_ctl restart --host 192.168.8.179`), Uptime prüfen.
2. **`prep_clean.sh` statt `prep_after_boot.sh`.** Mit `0091` im Kernel lädt und quittiert der Treiber die
   ARISC selbst; das alte Rezept lädt den Blob ein zweites Mal und schickt eine zweite Quittung.
   `prep_clean.sh` **erkennt den Kerneltreiber** und lässt die Alt-Schritte dann weg (eine Fallunterscheidung
   in einem Skript — nicht die handgeschnittene Zweitfassung `prep_ohne_arisc.sh`, die nur auf dem Board lag).
3. `SetSource(3)`; EDID/HPD kommen aus dem Kernel.
4. Plane starten (`hdmi_plane_test`) — der Descriptor gehört dem Treiber, `viddec_descriptor.py` **nicht**
   mehr von Hand aufrufen.
5. **Freigabe nach dem Descriptor — entfällt seit `0099`.** Das Schreiben des Descriptors *schaltet die
   Capture ab* (`0x06940928` Bit 31 → 0). Das macht jetzt **der Kernel selbst** wieder gut: der
   Anzeigetreiber meldet die Veröffentlichung des Descriptors auf einer eigenen Benachrichtigungskette
   (getrennt von der Flip-Kette), der Aufnahmetreiber antwortet mit einem Quellenwechsel weg **und zurück**.
   Belegt am Kaltstart 11:42 ohne einen einzigen Handgriff: `0x928 = 0xE0020438`, `HDMI-1: ok`, nach
   `hy310-tv` „Capture laeuft wieder nach 25 ms", Zuspieler gedimmt → **48,16 %** der Bildpunkte geändert
   ([nachtlog/E2-freigabe.md](E2-freigabe.md)).
   *Der frühere Handgriff aus dem Userspace ist ersatzlos weg.* Zur Messgeschichte: ein **einzelner**
   `SetSource(HDMI-1)` reicht **nicht** (dreimal nichts), weg und zurück wirkt immer, und die Freigabe kommt
   erst 536–544 ms nach der Antwort der Firmware — wer sofort danach liest, liest zu früh.
   **Achtung, die frühere Formel „zwei belegte Freigabewege" ist nicht mehr haltbar** (Nachprüfung 11:55,
   [nachtlog/M4-nachpruefung.md](M4-nachpruefung.md)): der **HPD-Zyklus** hat aus dem geprüften
   Zustand (aktive Quelle VideoDec) die Capture in 20 s **nicht** freigegeben, während ein `SetSource(3)`
   danach sofort wirkte. M4s eigener Ausgangszustand ist seit `0099` nicht mehr herstellbar, also weder
   bestätigt noch widerlegt — als Betriebsweg **nicht verwenden**. Belegt bleibt allein der Quellenwechsel
   ([nachtlog/B2-quellenwechsel.md](B2-quellenwechsel.md), Reiz an der Quelle;
   [nachtlog/M4-hpd-dauer.md](M4-hpd-dauer.md) trägt nur das Freigabebit).

Registerbild ziehen: `analyse/hdmi-seq/dump_state.py` (liegt jetzt **im Repo**, nicht nur auf dem Board, und
erfasst zusätzlich den Composition-Block bis `0x05000FFC` und den PQ-Block ab `0x05001000`).
`pq_saturation.py` ist **zurückgezogen** (widerlegte Formel, `/dev/mem`-Poke im Betriebspfad).

`hdmi_plane_test` immer so starten, dass die SSH-Sitzung ihn nicht mitreißt:
`setsid sh -c "nohup ./hdmi_plane_test -t 150 > /root/plane.out 2>&1 &"`.

## Drei Regeln, die diese Nacht teuer waren

### 1. Was am Gerät wirkt, steht in `series`

Dieselbe Falle ist zweimal zugeschnappt: **eine Handänderung in einem Baubaum überlebt keinen Neubau.**
Betroffen waren der DT-Knoten `tvcap@50c0000` — ohne ihn bindet `h713-tvcap` nie, TVFE/TVCAP bleiben stromlos,
der **gesamte INCAP-Block liest `0x00000000`** und die Wand zeigt gleichmäßiges Grün — und drei
`cpu_comm`-Korrekturen. Beides stand in **keinem** Patch der Serie und ist als `0096` bzw. `0097` nachgetragen.

**Regel:** Was am Gerät wirkt, gehört in `mainline/patches/kernel/` **und** in `series`. Wer eine Datei im
Baubaum ändert, hat noch nichts geliefert. Vor jeder Abnahme die entscheidende Zeile im **Patch** prüfen, nicht
im Baum. Herleitung: [78](../78-nachtplan-hdmi-switch.md) Abschnitt 0a, Belege in
[`nachtlog/A-abnahme-board.md`](A-abnahme-board.md) und [`nachtlog/00-koordination.md`](00-koordination.md).

### 2. Ein Kriterium, das nicht scheitern kann, prüft nichts *(neu 07.09.)*

Und sein Spiegelbild: ein Kriterium, das nicht **gelingen** kann, ebenso. Beides ist in dieser Sitzung
vorgekommen, jedes Mal an einer Stelle, an der etwas als „belegt" geführt wurde:

* **`portmap: 0,1,2` ist kein Beleg.** Die ROM-Vorgabe bei `0x15edc` ist die Identität — genau der Wert, den
  `HostHDMIMAP 0,1,2` schreibt. Der Wächter kehrte in der ersten Runde zurück und meldete Erfolg, ob der
  Handler gelaufen war oder nicht. Erst die Vorbelegung mit `0xff` trennt „gewonnen" von „war ohnehin so".
* **`QUERY_DV_TIMINGS: 1920x1080p` ist kein Beleg.** Der Wert ist in `0094` eine
  Übersetzungszeit-Konstante (`V4L2_DV_BT_CEA_1920X1080P60`), die Fähigkeitsgrenzen klemmen `min == max`.
  Er wird bei **jeder** Quellauflösung gedruckt.
* **Das Spiegelbild in `hy310-tv`:** die Gerätebestätigung verglich `vcap.driver` per `strcmp()` gegen
  `"sun50i-h713-hdmirx"` — `struct v4l2_capability` hat aber `__u8 driver[16]`, der Kernel meldet
  `sun50i-h713-hdm`. Der Vergleich konnte auf **keinem** Board zutreffen.
* **Und ein Instrument, das gar nicht lief:** die ersten „0,00 %" beim Gamma auf dem Video-Pfad kamen daher,
  dass `gamma_test` keinen DRM-Master bekam. Erst prüfen, ob das Instrument einen Positivbefund zeigen kann.

**Wer eine Zahl als Beleg führt, fragt sich: hätte sie anders ausfallen können?**

### 3. Ein Agent ändert keine Datei unter `mainline/patches/kernel/` *(neu 07.09., 10:06)*

Vorschläge gehen nach `mainline/patches/vorschlaege/<paket>/`; die Aufnahme macht die Hauptsitzung — und
zwar erst nach Momentaufnahme (`patches-snapshots/<zeitstempel>/`), `diff -u` gegen den Ist-Stand und
Serienprüfung (alle Zeilen der `series`, kein `.rej`). Ausnahme: ein ausdrücklicher Implementierungsauftrag, der den Agenten
namentlich für eine bestimmte Patchdatei freigibt — auch dann erst nach einer Momentaufnahme.
**Anlass:** beim Callback-Fix überschrieb ein Agent `0092` und `0094`; sein Stand fiel am Gerät durch, und
die Fassung, mit der A–H grün waren, existierte als Patch nicht mehr. Nur weil der Baubaum noch dalag, ließ
sich eine bootfähige FIT rekonstruieren — darauf darf man sich nicht verlassen.
Begründung: [`nachtlog/00-koordination.md`](00-koordination.md), Nachtrag 10:06.

## Worum es geht

Christopher Stenger (`cstenger`) hat einen eigenen Mainline-Stack für den
Allwinner H713 gebaut: offene Boot-Chain (U-Boot SPL → TF-A BL31 → U-Boot →
Linux) und arm64-Debian, auf Basis der Treiber-Serie aus
`well0nez/allwinner-h713-linux`, die er mit Namensnennung übernimmt.

Wir bringen diesen Stack auf **unser** Board — eine dritte Variante, die er
nicht kennt — und geben die dabei gefundenen Fehler an ihn zurück.

## Wo was liegt

```
/opt/Projekte/h713/
├── doku/           diese Dokumentation
├── mainline/       Klon von cstenger/allwinner-h713-mainline (+ Submodule)
├── legacy/         Klon von well0nez/allwinner-h713-linux (unser arm32-Port)
├── re/             das gesamte RE-Material, dedupliziert und verifiziert
└── uboot-h713/     unsere U-Boot-Änderungen als Patch, außerhalb des Submoduls
```

Dazu `/opt/archive/` mit den vier Originalquellen des RE-Materials,
unangetastet.

## Was läuft

| | |
|---|---|
| Boot-Chain | SPL → BL31 → U-Boot proper, vom eMMC |
| DRAM | DDR3 792 MHz, 1 GiB, trainiert stabil |
| eMMC | HS400, 26 Partitionen |
| USB-Host | alle sechs Controller, Stick an der Buchse lesbar |
| arm64-Linux | 6.18.38, vier Kerne bei EL2, bootet über Netz durch |
| FEL | über die USB-A-Buchse, mit selbstgebautem A-auf-A-Kabel |
| MIPS-Display | Firmware läuft, `cpu_comm` **4/4 Ready** (`/proc/cpu_comm/status` hat genau vier `Ready:`-Zeilen; `prep_clean.sh` druckt `Ready-Flags: %s/4`, alle Abnahmelogs melden 4/4) |
| **Bootlogo** | **steht hell und vollständig auf der Wand** |
| **Netboot** | Kernel per TFTP, Wurzelverzeichnis per NFS — auf dem Gerät liegt nur U-Boot |
| **Debian 13 arm64** | bootet bis zum Login-Prompt, systemd durch |
| **KMS-Treiber** | übernimmt **1920×1080**, stride 7680 |
| **Vblank** | **läuft** — `GICv2 142` zählt, keine Timeouts mehr, `fb0` in 20 ms statt 33 s |
| **Bild unter Linux** | **Konsole steht auf der Wand**, Testbild und Bewegtbild über `/dev/fb0` bestätigt |
| **VE / Cedrus** | H.264 und HEVC **bit-exakt**, v01–v05 und h01/h02, bis 1920×1080 |
| **Videowiedergabe** | **59,4 fps bei 1920×1080**, zero-copy VE→dma-buf→GPU→Scanout, doppelt gepuffert |
| Panel | **1920×1080**, eigene Config aus dem Stock-Vergleich, Auswahl über die ProjectID |
| **MIPS-Quellenwechsel** | **`SetSource(HDMI)` läuft durch** (07.09.): U-Boot legt den SMM-Heap vor dem MIPS-Start an; Firmware allokiert `sgp_hal_signal_info` selbst. Serienmodul `hy310_cpu_comm` lädt automatisch |
| **HDMI-Eingang** | *korrigiert 07.09.:* **HPD/EDID, Capture, Plane und `/dev/video1` laufen aus dem Kernel und sind abgenommen** (`0091`, `0093`, `0094`, `0095`). Offen ist die Zustellung der Firmware-Callbacks — siehe „Was gerade offen ist" |
| **Video-Plane** | *korrigiert 07.09.:* `video-0`, **Plane-ID 38** (Overlay) neben der Primary 34 am CRTC 36; der AFBD-Anzeigetreiber ist **`card1`**, `card0` ist Panfrost (nur Render-Knoten). Mit `0093` **in Betrieb und abgenommen** |
| **Bildqualität (PQ)** | Registerblock `0x05001000…0x050015FC` erschlossen und am Gerät bestätigt — er war in keinem unserer Abzüge enthalten. `SetContrast` → `0x05001234[31:16]`, wirkt messbar (12,16 %); `SetBrightness` → `[15:0]`, **wirkt ebenfalls, Stellbereich 0…100** (*korrigiert 07.09., 11:25:* hier stand „wirkt nicht" — die Messung dahinter lief gegen eine fast weiße Vorlage und konnte nicht anschlagen, [nachtlog/I0-helligkeit-nachgemessen.md](I0-helligkeit-nachgemessen.md)); `SetSaturation` und der Chroma-Gain `0x05140508` sind **derselbe** Regler (`Gain = floor(Argument × 1,28)`, Vorgabe `0x4C` = `SetSaturation 60`). [81](../81-pq-datenmodell.md), [85](../85-re-pq-register.md), [nachtlog/K5-board-verifikation.md](K5-board-verifikation.md) |

## Eingereicht

- **[PR #1](https://github.com/cstenger/u-boot/pull/1)** — USB-Host, sechs Commits
- **[PR #2](https://github.com/cstenger/u-boot/pull/2)** — der Display-Pfad, zehn
  Commits, auf PR #1 aufgesetzt ohne ihn anzufassen

## Was nicht läuft

- **Kein Rootfs auf dem Gerät.** Der Kernel paniert bei
  `root=/dev/mmcblk0p26`, da liegt nichts; über Netboot läuft Debian 13.
  Sein `tools/rootfs/build.sh` baut ein signiertes Debian 13.
- **Keine gepufferte Uhr.** Der RTC zählt bei jedem Kaltstart ab
  `1970-01-02`, systemd setzt seine Epoche `2026-04-13`. Solange die Uhr
  Monate zurückliegt, schlägt jede TLS-Prüfung mit
  `certificate verify failed` fehl — das Zertifikat ist dann *noch nicht
  gültig*, nicht abgelaufen. Behelf: `date -u -s ...`.
- **Kein Gadget-Modus** mehr, seit die Buchse auf Host steht. `ums` und
  Fastboot fallen damit weg, FEL bleibt.

**Gelöst am 31.08.:** `[CRTC:36:crtc-0] vblank wait timed out` — in den
Netboot-`bootargs` fehlten `clk_ignore_unused` und `pd_ignore_unused`,
worauf Linux dem laufenden Panel PLL_VIDEO2 und den MIPS abschaltete. Der
komplette Beweisgang steht in [61-plan-vblank.md](../61-plan-vblank.md).

## Der rote Faden

Alle bisherigen Stolpersteine hatten dieselbe Ursache: sein Code ist auf
**ein** Board und **einen** Ablauf geschrieben, und jede Abweichung fällt
einzeln auf. Fünf davon haben wir behoben, siehe
[30-uboot-aenderungen.md](../30-uboot-aenderungen.md).

## Weiter

- [nachtlog/STAND-JETZT.md](STAND-JETZT.md) — **was gerade läuft, was gerade klemmt, und wo die Rückwege liegen (11:50).**
- [79-nachtlog-20260907.md](../79-nachtlog-20260907.md) — **das Protokoll der Nacht mit den Teillogs.** Die Einzelmessungen stehen dort; die **Kopftabelle** ist der Stand von 08:57 und bei B, E und F vom Vormittag überholt — der aktuelle Paketstand steht oben auf dieser Seite.
- [10-hardware.md](../10-hardware.md) — was auf dem Board sitzt, alles gemessen
- [20-flashen-und-recovery.md](../20-flashen-und-recovery.md) — Layout, Flash-Wege, FEL
- [30-uboot-aenderungen.md](../30-uboot-aenderungen.md) — unsere Patches und ihre Belege
- [40-display.md](../40-display.md) — der MIPS-Display-Pfad
- [50-befehle.md](../50-befehle.md) — Befehlssammlung
- [60-offen.md](../60-offen.md) — offene Punkte

## Die übrigen Dateien

- [10-hardware.md](../10-hardware.md) — Board, SoC, Panel, GPIO-Warnungen
- [20-flashen-und-recovery.md](../20-flashen-und-recovery.md) — Flash-Rezept, FEL
- [30-uboot-aenderungen.md](../30-uboot-aenderungen.md) — unsere dreizehn Änderungen
- [40-display.md](../40-display.md) — MIPS-Firmware und Display-Pfad
- [50-befehle.md](../50-befehle.md) — alles zum Nachschlagen
- [60-offen.md](../60-offen.md) — offene Punkte
- [70-sackgassen.md](../70-sackgassen.md) — **ausgeschlossen, mit Beleg. Zuerst lesen.**
- [80-vergleich-baeume.md](../80-vergleich-baeume.md) — was cstenger portiert hat und was nicht
- [90-stock-referenz.md](../90-stock-referenz.md) — **der A/B-Umschalter gegen Stock. Das Werkzeug, das den Display-Pfad gelöst hat.**
- [95-netboot.md](../95-netboot.md) — **Netboot komplett: TFTP starten, NFS, Environment, UART-Flashen**
- [61-plan-vblank.md](../61-plan-vblank.md) — **der Vblank-Fehler, gelöst und belegt**
- [62-video.md](../62-video.md) — **VE-Dekodierung und Wiedergabe; fünf Defekte in seinem Video-Pfad**
- [64-afbd-quelle0.md](../64-afbd-quelle0.md) — **belegt: unser DRAM steht auf dem Panel. Das Latch-Orakel (bedient vs. konfiguriert), der Ring, und vier widerlegte Annahmen**
- [65-cpu-comm-abgleich.md](../65-cpu-comm-abgleich.md) — **die drei cpu_comm-Generationen, vollständig gediffed: sein Patch 0014 ist unser `Archived/`-Stand. Wer was hat, und die zwei U-Boot-Fallen**
- [66-cpu-comm-arm64-bringup.md](../66-cpu-comm-arm64-bringup.md) — **erster CPU_COMM-Round-Trip auf diesem Board, Session Z reproduziert; fünf behobene Fehler, und warum der MIPS aus Linux noch nicht abholt**
- [67-cpu-comm-linux.md](../67-cpu-comm-linux.md) — **CPU_COMM-Aufruf aus Linux läuft durch, mit Rückgabewert. Drei Ursachen: geparkter MIPS, `cc_ref` ohne `cc_deref`, 64-Bit-Laden auf 4-Byte-Grenze.**
- [68-stock-extraktion-arisc-hdcp.md](../68-stock-extraktion-arisc-hdcp.md) — **die HDCP-Keys und die ARISC-Firmware aus den Stock-Daten geholt; die vollstaendige ARISC-Ladesequenz aus dem Vendor-BL31, Ladeadresse `0x00100000`, Reset `0x07000400` Bit 0. `GIC_SPI 46` aus der Herstellerquelle belegt.**
- [69-handoff-20260905.md](../69-handoff-20260905.md) — Übergabe vom 05.09.: HDMI-Eingang bis kurz vors Signal. Enthält Zugang, Wiederherstellungsrezept und Sperren; **der Sachstand darin ist überholt**
- [71-tvtop-noetig.md](../71-tvtop-noetig.md) — **Antwort auf den Folgeauftrag aus 69: der ARM braucht `tvtop` fuer den HDMI-Eingang NICHT.** MIPS setzt INCAP selbst auf, Domains aus U-Boot an, Fabric-Routing aus U-Boot. Dazu: `reg`-Reihenfolge des tvtop-Knotens im DT ist gegen den Vendor vertauscht.
- [74-setsource-ursache-nullzeiger.md](../74-setsource-ursache-nullzeiger.md) — **`SetSource(HDMI)` tötet den SoC nicht mehr:** Nullzeiger `sgp_hal_signal_info`, Fix in U-Boot, A/B belegt; dazu die Bereinigung der Diagnose-Bausteine (11 Positionen)
- [75-handoff-20260907.md](../75-handoff-20260907.md) — die Übergabe vom Morgen des 07.09.; **chronologisch gewachsen, der Sachstand darin endet vor den Abnahmen** (die Seite markiert das selbst am Kopf)
- [76-plan-ch0-de.md](../76-plan-ch0-de.md), [77-plan-hdmi-integration.md](../77-plan-hdmi-integration.md) — die Pläne, aus denen die Patches entstanden sind
- `legacy/docs/known-issues.md` — die **Pflichtliste**, in Paket J überarbeitet: 17 Sachpunkte eingeordnet, 12 Behelfe im Quelltext benannt (W1–W12)

## Aus dem Nachtlauf 06./07.09.

- [78-nachtplan-hdmi-switch.md](../78-nachtplan-hdmi-switch.md) — die Aufträge; **Abschnitt 0a** (die Baubaum-Falle) und **Anhang A** (der Umschaltablauf in sieben Stufen, Fehlerbilder, offene Punkte) gelten weiter
- [79-nachtlog-20260907.md](../79-nachtlog-20260907.md) — **das Protokoll mit den Teillogs in [`nachtlog/`](./).** Die Einzelmessungen stehen dort; die Kopftabelle ist der Stand von **08:57** und bei B, E und F überholt. Der jüngste operative Stand: [`nachtlog/STAND-JETZT.md`](STAND-JETZT.md)
- [81-pq-datenmodell.md](../81-pq-datenmodell.md) — von der Stock-Datei bis zum Register: Bildmodus, Werkskurve, Sättigung, Gamma-LUT; Werkzeug `userspace/hy310-pq`
- [82-arisc-treiber.md](../82-arisc-treiber.md) — `sun50i-h713-arisc` (`0091`): Firmware laden, Startup-Handshake, EDID/HPD als Kernel-API, ohne Puls und ohne Rettungspfade
- [83-cpu-comm-api.md](../83-cpu-comm-api.md) — die In-Kernel-API von `cpu_comm` (`0092`); der Namens-Hash macht die Call-Tabelle entbehrlich
- [84-re-capture-ring.md](../84-re-capture-ring.md) — RE: die INCAP-Felder stehen in den TSE-Tabellen, nicht im Code; **es gibt auf dem ARM kein Capture-Ereignis** (Vsync-getaktetes Lesen der Flip-Zeiger statt Interrupt)
- [85-re-pq-register.md](../85-re-pq-register.md) — RE: der PQ-Registerblock `0x05001000…15FC` und eine Vorstudie zu Stocks Compositing (der exklusive Mux ist **unsere** Konfiguration, nicht die Hardware)
- [86-video-plane-nv16.md](../86-video-plane-nv16.md) — die Video-Plane auf dem Capture-Ring (`0093`): Registersatz mit Begründung je Wert, Ring-Folge, Descriptor
- [87-gamma-ctm-kms.md](../87-gamma-ctm-kms.md) — `GAMMA_LUT` und `CTM` am AFBD-CRTC (`0095`), Schreibsequenz nach BACKGROUND.md §5.3
- [88-v4l2-hdmirx.md](../88-v4l2-hdmirx.md) — `sun50i-h713-hdmirx` (`0094`): Probe-Sequenz, Puffermodell, `SOURCE_CHANGE` aus dem Firmware-Callback
- [89-composition-block.md](../89-composition-block.md) — der Composition-Block `0x05000000` an unserem Board gegengeprüft: 1920×1080, Skalierung 1:1. **Composition treibt das Panel, nicht AFBD**
