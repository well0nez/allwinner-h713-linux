# Plan: die drei offenen Punkte des Umschalters

> **Erledigt (Stand 08.09.2026):** dieser Plan ist abgearbeitet und am Gerät abgenommen; was davon abweicht und was übrig blieb, steht in [`00-STATUS.md`](00-STATUS.md) §4 und [`60-offen.md`](60-offen.md). Das Dokument bleibt als Planungsstand und Begründung.

**Stand 07.09.2026, 15:00. Dieser Plan ist ab jetzt der maßgebliche.**

Er löst `doku/78-nachtplan-hdmi-switch.md` nicht ab — der Nachtplan hat die Pakete A bis L gebaut,
und die sind fertig. Er tritt an die Stelle von dessen Abschnitt A.6, soweit die drei Punkte unten
reichen.

## Der Auftrag, eng gefasst

Marcos Abgrenzung vom 07.09.: **es geht um die Funktionalität des Umschaltens, und darum, dass sie
stock-konform funktioniert.**

Ausdrücklich **nicht** dazu gehören: Audio des HDMI-Eingangs · HDCP (vorerst) · dass alles über
Netz läuft (Kernel per TFTP, Wurzel per NFS — in Ordnung so) · ein Autostart für `hy310-tv`.

**Stock-konform** heißt: die Stock-Firmware ist der Maßstab. Wo sie etwas kann, das wir nicht
können, ist das eine Lücke. Wo wir etwas tun, das sie nicht tut, ist die Beweislast bei uns. Und
das ist prüfbar, nicht nur nachlesbar: beide Bootloader liegen parallel auf der eMMC, ein
Schreibvorgang auf LBA 16 schaltet um, in beide Richtungen (`doku/90-stock-referenz.md`).

## Was läuft, damit klar ist, worauf das aufsetzt

Vom Kaltstart bis zum Bild ist kein Handgriff nötig. Signal weg → Konsole, Signal zurück → Bild,
dreimal hintereinander mit praktisch identischen Zahlen. Neun Bildregler am `/dev/video1`. Belege
in [`nachtlog/STAND-JETZT.md`](nachtlog/STAND-JETZT.md).

---

# Reihenfolge

Die drei Punkte sind **nicht** unabhängig. Diese Reihenfolge ist begründet, nicht gewählt:

| | | Grund |
|---|---|---|
| **1.** | Punkt 1 — RPC-Verlust | Der einzige, der das Umschalten kaputtmacht. Sein Fix liegt in `cpu_comm`, das alle anderen benutzen. Und **jede längere Messreihe für Punkt 2 oder 3 kann heute den RPC-Kanal für den ganzen Boot erschöpfen** (C3) — solange das so ist, misst man auf Sand. |
| **2.** | Punkt 3 — Chroma-Gain | Der Gain-Schreibzugriff steht **außerhalb** des Einschaltzweigs (`sun50i-h713-afbd.c:915-917` gegen `if (!h->video_active)` bei `:844`), und `hy310-tv` fährt bei **jedem** `SOURCE_CHANGE` `display_hide()`+`display_show()` (`userspace/hy310-tv/main.c:956,975,980`). Jeder Auslöser, den Punkt 2 baut, zerstört also die über V4L2 gesetzte Sättigung. Punkt 3 muss vorher landen, sonst wird Punkt 2 auf einem System abgenommen, das Punkt 3 gerade verschärft. |
| **3.** | Punkt 2 — Auflösungswechsel | Der teuerste, und der einzige, dessen Kern nicht bei uns liegt: die Firmware macht ihren Teil schon. |

---

# Punkt 1 — Der verlorene RETURN — **gelöst 07.09., 19:15**

Ursache gefunden, an der Wurzel behoben, abgenommen. Vollständig in
[`nachtlog/C5-rpc-ursache-behoben.md`](nachtlog/C5-rpc-ursache-behoben.md); der Weg dahin in
[`C3`](nachtlog/C3-rpc-verlust-reproduziert.md) (reproduziert), [`C4`](nachtlog/C4-rpc-verlust-flanke.md)
(ARM-Seite ausgeschöpft) und dem MIPS-Disassemblat
(`mainline/patches/vorschlaege/mips-return/BEFUND.md`).

**Die Ursache:** `cpu_comm_proto.c:602` rückte den Lesezeiger der **NewCall-FIFO des MIPS**
(`share_seq_w + 32`) vor, direkt nach dem Aufwachen aus der CALL_ACK-Semaphore. Diese FIFO hat einen
Schreiber (MIPS-ISR) und einen Leser (MIPS-BG-Thread); der ARM war der zweite Leser. Kam sein `rd++`
zuerst, sah der BG-Thread den Ring leer → kein Handler, kein RETURN, kein `Comm_ReleaseFreeCall`
(→ Slot-Leck), kein elog. Das war „RPC-Verlust", „Slot-Leck", „fehlendes RETURN", „elog-Stille" und
„braucht einen Settle" in einem — **dieselbe Zeile**. Die alte Begründung („KSEG0 cache … Without
this: -EBUSY at 19") war umgedreht: die gestohlenen Rufe hinderten den MIPS am Abarbeiten, dadurch
lief der FreeCall-Pool leer.

**Der Fix (`0105`):** die Zeile ersatzlos entfernt — kein Delay, kein Workaround, keine Frist. An
ihre Stelle ein reiner Lesezähler `newcall … beim CALL_ACK noch ungelesen` als falsifizierbarer
Zeuge.

**Abnahme:** 100 dichte Rufe, Konsole stumm: **0 Fehler** (vorher 32/100), `newcall 96` (genau die
Rufe, die die alte Zeile gestohlen hätte), Pool stabil. Switcher drei Zyklen sauber. Bild farbig.

**`0106`:** weil der Wettlauf an der Wurzel weg ist, sind alle Per-Ruf-`pr_info` auf `pr_debug` —
der ~120-ms-Settle je RPC ist zurückgeholt, der Treiberpfad ist still, Probe 15,78 s. 0 Fehler auch
bei normaler Konsole.

# Punkt 2 — Der Auflösungswechsel — **Erkennung gelöst, DE-Scaler offen (07.09., 20:15)**

Voll aufgeklärt und zum größeren Teil gelöst; ein klar umrissener RE-Rest bleibt. Vollständig in
[`nachtlog/E6-aufloesung-erkennung-und-scaler.md`](nachtlog/E6-aufloesung-erkennung-und-scaler.md),
Vorarbeit in [`E3`](nachtlog/E3-geometrie-im-register.md)/[`E4`](nachtlog/E4-geometrie-vollstaendig.md)/[`E5`](nachtlog/E5-signalchange-feuert-bei-geometrie.md).

**Gelöst (Patch `0107`, am Gerät abgenommen):**
- `SignalChange` feuert bei reinem Geometriewechsel (E5, M1). `A6-4`s „0 mal" war der fehlende
  Callback vor `0100`.
- `QUERY_DV_TIMINGS` ist ehrlich: Geometrie aus dem Signal-Info-Record (`args[1]`, Layout M5
  bestätigt) + Totale aus INCAP `0x548` + gerechneter Pixeltakt. Kein fest verdrahteter Wert mehr.
- Die Plane nimmt die Quellgeometrie an; Y/C-Stride bei 720p korrekt (`0x500`/`0x0A00`, M3), kein
  Descriptor-Neuschreiben. `mode_config.min_width` war auf Panelgröße (AddFB2-EINVAL) — behoben.

**Offen — M2, der DE-Scaler:** die DE-Composition skaliert 1280×720 nicht auf das Panel
(`0x05000174` bleibt 1:1), das Bild käme links oben mit Umbruch. Stock zieht die Composition über
`UpdateWce` mit; unsere Kette adoptiert die DE beim Probe und fasst den Scaler nie an — wir müssten
ihn programmieren (`0x05000174/0x224/0x844` + Koeffizientenbänke, `doku/89`, von Stock abschaubar
über den A/B-Umschalter). Das ist der eine nächste Schritt.

**Endzustand jetzt (korrekt und definiert):** `hy310-tv` zeigt Panel-Quellen voll, jede andere
Quelle fällt auf die Konsole zurück (klare Logzeile) statt ein verzerrtes Bild. 1080p → 720p →
1080p am Gerät: Bild / Konsole / Bild, `0 ohne Antwort` durchweg. Der Rebuild-Pfad im Kernel steht
bereit; wenn der Scaler da ist, entfällt nur die Konsolen-Sperre in `hy310-tv`.

# Punkt 3 — Der Chroma-Gain — **erledigt 07.09., 18:05**

Patch `0104`, Abnahme in [`nachtlog/I4-chroma-gain-abnahme.md`](nachtlog/I4-chroma-gain-abnahme.md).

Entschieden durch zwei Messungen: `I2` (der Wert geht bei Plane aus/an verloren, `G_CTRL` lügt) und
`I3` (Gain `0x00` ist ein graues Bild — der Ersatz musste vor dem Löschen stehen). Der Regler hat
jetzt einen Eigentümer, den RPC: der Anzeigetreiber schreibt `+0x508` nicht mehr, die
Plane-Eigenschaft ist weg, `hy310-tv -s` ist weg, und der Aufnahmetreiber wendet beim
Plane-Einschalten den Control-Wert an (Vorgabe 60 = `0x4C`, das beobachtete Stock-Register).

A4 bestanden: `saturation=30` → Signalverlust → Rückkehr → Register `0x26` **und** `G_CTRL` 30.
Oberes Byte `0x04`, der DCTI-Zustand ist in sich stimmig.

Offen aus diesem Punkt: Kontrast/Helligkeit auf ein nachgelagertes Register prüfen (ein
PROC-Abzug); `doku/76:326` („bei Stock `0x144C0000`") berichtigen — die Stock-Abzüge enden bei
`0x051400FC`, die Aussage hat nichts hinter sich.

---

# Gesamtabnahme

Ein Lauf, ein Kernel, ein Kaltstart, alle drei Fixes drin. Jedes Kriterium mit Gegenprobe.

* **A0 Vorbedingung.** `h713-tvcap` steht in der Serie und im erzeugten Baum. *Scheitert*, wenn
  `grep -rn h713-tvcap drivers/` leer bleibt — heute liegt der Treiber out-of-tree in
  `analyse/tvcap/`, und `doku/60-offen.md` sagt dazu: „solange das offen ist, ist die Serie für sich
  genommen nicht abnahmefähig".
* **A1 (P1).** Konsole stumm, 500 Rufe ohne Pause, 0 Fehler, `FreeCall`-Abstand konstant.
  *Gegenprobe:* Frist auf 1 ms → **muss** ~100 % Fehler geben.
* **A2 (P1).** N Kaltstarts, je mit **Nenner** (Bring-up-RPCs) und Zähler. 0 × `-110`.
* **A3 (P2).** Der Auflösungsdurchgang oben, mit seiner Gegenprobe (d).
* **A4 (P3).** Der Sättigungsdurchgang oben, mit seiner Gegenprobe.
* **A5 Kreuzprobe.** Ein Lauf, in dem Plane-Hochlauf, Auflösungswechsel und Sättigungssetzen
  zusammenfallen, plus die D-Regression (`0x05600044` = `0x0F00` aus **jedem** Vorzustand) und F
  (dreimal Konsole und zurück). Alle drei Fixes fassen dieselben zwei Funktionen an
  (`atomic_update`, `video_stop`) — genau die Stelle, an der `D-cstride-befund.md` schon einmal eine
  Abnahme falsch bestehen ließ.
* **A6 Stille im Log.** `dmesg` ohne `refusing to rewrite`, `did not reprogram the chroma stride`,
  `no RETURN`, `blieb nach 3 Anlaeufen aus`, `wait not found for session`. Jede Zeile existiert im
  Quelltext, jede hätte fallen können.

**Kein Abnahmekriterium sind** (alle heute in Gebrauch): `signal: vorhanden` und „Bilder geliefert
10/10" (`h713_hdmirx_signal_present()` sieht nur die Flip-Zeiger — bei laufendem Ring kann es nicht
scheitern) · `QUERY_DV_TIMINGS`, solange es eine Konstante ist · „0 × `-110`" ohne Nenner ·
`wandcheck.py` für **jede** Farbaussage.

---

# Nebenbefunde: gefunden, nicht Teil der drei, gehören behoben

Sie sind bei der Aufarbeitung angefallen und alle im Quelltext belegt. Sie gehören **nicht** in die
drei Punkte, aber sie gehören notiert, bevor sie jemand ein zweites Mal findet.

1. **`seq_idx == 20` zeigt in den Nachbar-`share_seq`.** Schranke ist `FIFO_DEFAULT_CAP` = 21,
   es gibt aber nur 20 Einträge; der Ruhewert ist 20. `getShareSeqR(1,1)` + 2440 =
   `getShareSeqW(1,0)` — die Sequenz jedes ausgehenden Rufs. Ein Treffer zerstört den Boot dauerhaft.
   Sagt `-ENODATA` (−61) voraus, nicht `-110`.
2. **`comm_InitSpinLock()` schreibt 36 Byte in einen 12-Byte-Eintrag** (`cpu_comm_hw.c:757-767`),
   also in die zwei folgenden hinein. Der Pfad wird bei `cpu_comm_shmem_adopted` übersprungen —
   eine Vorhersage, die scheitern kann, und ein Einzeiler zu prüfen.
3. **Drei Semaphor-Lecks auf Fehlerpfaden** (`cpu_comm_channel.c:829-831`, `:679-681`, `:922-924`).
   Jedes macht aus einem Diagnoselauf ein hängendes Gerät.
4. **Eine Schleife ohne Schranke:** `do { GetFreeWaitComm(...); schedule(); } while (!wait_ptr)`
   (`cpu_comm_proto.c:464-470`). Läuft der 20-Platz-Vorrat leer, hängt der Aufrufer für immer, ohne
   Logzeile.
5. **`0099`, erster Ruf.** Er wird nicht wiederholt, und seine Meldung behauptet „die Quelle steht
   unveraendert". Bei `-110` ist das die falsche Annahme: quittiert heißt wahrscheinlich ausgeführt,
   die Quelle steht dann auf VideoDec. Außerdem wird der Rückgabewert von
   `h713_hdmirx_switch_source()` am Probe-Ende weggeworfen (`sun50i-h713-hdmirx.c:2405`) — eine Zeile.
6. **Die Begründung der Wiederholung in `0099` stimmt nicht.** „SetSource is idempotent" steht im
   Widerspruch zum Kern derselben Funktion: die Firmware reagiert auf den **Wechsel**. Hat der erste
   Ruf den Handler erreicht und nur die Antwort verloren, ist der zweite ein Nullbefehl, der mit 0
   zurückkommt.
7. **Unbegrenzte Spinschleife im Hard-IRQ** im Kohärenz-Tor (`cpu_comm_proto.c:746`, aus
   `cpu_comm_hw.c:241`), dazu ein unbedingtes `pr_info` je empfangenem Wort.
8. **`SEND_TIMEOUT_JIFFIES 500`** trägt den Kommentar „~5 seconds at HZ=100", der Bau hat
   `CONFIG_HZ=250` — die ACK-Frist ist **2 s**, nicht 5.
9. **`BEFUND` §4 ist widerlegt.** „Der MIPS hängt fristlos in Lock 2, weil der ARM ihn hält" trägt
   nicht: MIPS und ARM benutzen **verschiedene Bytes** desselben 12-Byte-Eintrags (MIPS Byte 0/1,
   ARM Byte 3). Der ARM kann den MIPS über Lock 2 nicht anhalten. Der bisherige Hauptverdacht des
   Projekts ist damit erledigt.

---

# Was dieser Plan nicht beantwortet

* Warum ein dicht folgender RPC die Antwort verliert (Punkt 1, nach 1.1 nicht mehr dringend).
* Ob die drei Vorfälle vom 07.09. die in C3 gefundene Ursache hatten — die dmesg fehlt.
* Ob unser Umschalten insgesamt stock-konform ist. **Wir haben es nie gegen laufendes Stock
  gehalten**, obwohl der A/B-Umschalter dafür da ist. Jede „stock-konform"-Aussage in diesem Plan
  ist aus Mitschnitten und Disassemblaten erschlossen. Eine Stock-Sitzung — Stock booten, dieselben
  Umschaltvorgänge fahren, elog und Register mitschreiben — beantwortet auf einen Schlag mehrere
  Fragen aus allen drei Punkten. **Das ist der einzelne Board-Slot mit dem höchsten Ertrag im
  ganzen Plan.**
