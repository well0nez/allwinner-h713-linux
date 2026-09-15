# Stand jetzt - 08.09.2026, 01:30

> **Veraltet - Stand 08.09.2026, 01:30.** Der aktuelle operative Stand steht in [`../00-STATUS.md`](../00-STATUS.md) (Bedienung, Stände) und [`../97-handoff-20260908.md`](../97-handoff-20260908.md) (Betriebswissen, Rückwege). Diese Seite bleibt als Protokoll der Nacht 07./08.09.

Diese Seite ist bewusst kurz und operativ: was läuft, was nicht, was als Nächstes, und wo die
Rückwege liegen. Die Belege stehen in [79-nachtlog](../79-nachtlog-20260907.md) und den Teillogs
daneben.

## Was am Gerät läuft

**Der gesamte Bildpfad aus dem Kernel, und das Umschalten dazu.** Alles mit Kriterien abgenommen,
die hätten scheitern können.

| | Beleg |
|---|---|
| **A** | Kernel bootet, Konsole auf der Wand, Plane `video-0` (ID 38) gelistet |
| **B** | ARISC/EDID/HPD vollständig aus dem Kernel. Wächter **falsifizierbar** (Vorbelegung `0xff` → vergiftet meldet debugfs `255,255,255`) |
| **C** | `cpu_comm`-Kernel-API, `SetSource` aus dem Kernel, `/dev/cpu_comm` weiter nutzbar |
| **D** | NV16-Plane: fünf Abnahmeteile inkl. Fehlerfall; `0x05600044` aus **jedem** Vorzustand `0x0F00` |
| **E** | `/dev/video1`, 60 von 60 Bildern NV16M, rekonstruiertes Bild = **pixelgenauer Screenshot** |
| **G** | `hy310-pq`, Gamma-LUT bitgleich zum Legacy-Rechner |
| **H** | invertierte LUT: 100,00 % auf der Konsole, **86,56 %** auf dem Video-Pfad |
| **F** | `hy310-tv` läuft, Bild kommt, fällt bei Signalverlust auf die Konsole zurück |
| **I** | neun V4L2-Controls am `/dev/video1`, jeder Schreibweg gegen sein Register geprüft |

**Vom Kaltstart bis zum Bild ist kein Handgriff mehr nötig.** Der Treiber gibt die Capture selbst
frei; `hy310-tv` startet und zeigt.

**Umschalten, dreimal hintereinander gemessen** (Zuspieler-Ausgang aus/an):

| | aus | an |
|---|---|---|
| Zyklus 1 | mean 135,4 · std 12,3 | mean 177,9 · std 45,6 · p95 254 |
| Zyklus 2 | mean 137,1 · std 12,3 | mean 177,3 · std 45,6 · p95 254 |
| Zyklus 3 | mean 137,1 · std 12,2 | mean 177,8 · std 45,5 · p95 254 |

## Was heute Vormittag gefunden und behoben wurde

1. **Callback-Rücknahme `0098`** - der erste Anlauf hatte die E-Probe zerlegt; chirurgisch
   zurückgenommen, `afbd.c` unberührt.
2. **Hotplug-Rennen in `0091`** ([B3](B3-hpd-rennen.md)) - der Wächter verwechselte „ein Puls ist
   unterwegs" (~50 ms) mit „die Firmware hängt". Jetzt `arisc_wait_hpd_idle()` mit der schon
   gemessenen Frist. Am Gerät: „202 ms auf das Landen eines Hotplug-Pulses gewartet".
3. **Die Capture wurde nie wieder freigegeben** ([E2](E2-freigabe.md), Patch `0099`) - das Schreiben
   des Descriptors schaltet sie ab, niemand schaltete sie an. Jetzt meldet der Anzeigetreiber die
   Veröffentlichung auf einer eigenen Kette, der Aufnahmetreiber antwortet mit einem Quellenwechsel
   weg-und-zurück. Ein einzelner `SetSource(HDMI-1)` reicht **nicht** (dreimal nichts).
4. **Die Callback-Lücke ist zu** (BEFUND (`../../mainline/patches/vorschlaege/callback2/BEFUND.md`),
   Patch `0100`) - Anmeldung wandert ins `open()` von `/dev/video1`. `handlers 2`, `rx_calls` zählt,
   `SOURCE_CHANGE` feuert, F fällt auf die Konsole zurück.
5. **Paket I** ([I1](I1-get-routinen.md), Patch `0101`) - neun Controls. Die Rückfrage an die
   Firmware ist rausgeflogen: alle `THal_Vp_Get*` liefern konstant 0, auch direkt nach einem
   erfolgreichen Schreibvorgang.
6. **Helligkeit wirkt doch** ([I0](I0-helligkeit-nachgemessen.md)) - Stellbereich **0…100** gemessen.

## Drei Dinge, die dabei nebenbei belegt wurden

* **`0x06940928[15:0]` trägt die Zeilenzahl** des eingerasteten Signals, Bit 31 sagt, ob eingerastet
  ist ([E3](E3-geometrie-im-register.md)). Das ist der Auslöser, nach dem A6-4 gesucht hat - ohne
  Callback, durch Lesen. Die Breite fehlt noch.
* **Der HPD-Zyklus gibt die Capture nicht frei** ([M4-Nachprüfung](M4-nachpruefung.md)) - 20 s, Bit 31
  bleibt aus. „Zwei belegte Freigabewege" ist nicht haltbar.
* **`-110` heißt zwingend „quittiert, aber keine Antwort"** - ein fehlender ACK wäre `-ETIME` (−62).
  *Korrektur 14:00: das gilt **nur für den `cpu_comm`-Pfad**. Der ARISC-Treiber hat sechs eigene
  `-ETIMEDOUT`-Rückgaben mit anderer Bedeutung, und daraus ist schon `-110` gemessen worden
  (`B-abnahme-board.md:30`). Schärfer außerdem: `-110` setzt **drei** Bedingungen voraus - fehlt das
  Warteobjekt, kommt `-ENODATA` (−61). Und: dass die drei Vorfälle vom 07.09. wirklich `-110` im
  `cpu_comm`-Sinn waren, ist **nicht belegt** - die dmesg dazu existiert nicht mehr.*

## Der Plan für das, was offen ist

**[`doku/91-plan-drei-punkte.md`](../91-plan-drei-punkte.md) ist ab 07.09. 15:00 der maßgebliche
Plan** für die drei offenen Punkte. Er tritt an die Stelle von `doku/78` Abschnitt A.6, soweit
diese drei reichen; die Pakete A-L des Nachtplans sind fertig.

Reihenfolge dort begründet: **1.** RPC-Verlust · **2.** Chroma-Gain · **3.** Auflösungswechsel.

## Nachmittag: der RPC-Verlust, bis zur Grenze der ARM-Seite aufgebrochen

[`C3`](C3-rpc-verlust-reproduziert.md) hat ihn reproduziert, [`C4`](C4-rpc-verlust-flanke.md) hat
alles widerlegt, was von unserer Seite aus zu ändern war. Belegt: der MIPS quittiert und schreibt den
RETURN nicht; der Slot kommt nie zurück und gehört dem MIPS; **einziger Hebel ist Zeit auf dem
Aufrufer nach dem Türklopfer** (1000 µs → 0/40). Die Konsolenzeilen waren dieser Settle.

**Die Serie steht deshalb wieder auf dem Stand von heute Mittag** (funktioniert, ~120 ms je RPC),
plus `0102` als reine Instrumentierung. Zwei Patches wurden gebaut, gefahren, widerlegt und
**entfernt**. Die Entscheidung A/B/C steht in `doku/91` Punkt 1 und gehört Marco.

## Punkt 3 erledigt (18:05)

[`I3`](I3-gain-null-ist-grau.md): Gain `0x00` ist grau - der Ersatz musste vor dem Löschen stehen.
[`I4`](I4-chroma-gain-abnahme.md): Patch `0104`, der Chroma-Gain hat einen Eigentümer (den RPC),
A4 bestanden - `saturation=30` überlebt Signalverlust/-rückkehr, Register und `G_CTRL` gleich.

## Punkt 1 GELÖST (19:15) - an der Wurzel, kein Workaround

[`C5`](C5-rpc-ursache-behoben.md): `cpu_comm_proto.c:602` rückte den Lesezeiger der **MIPS-eigenen**
NewCall-FIFO vor und stahl dem MIPS-BG-Thread den Ruf - daher kein RETURN, kein Slot zurück, kein
elog, der „Settle"-Bedarf. Patch `0105` entfernt die Zeile ersatzlos. **100 dichte Rufe stumm: 0
Fehler** (vorher 32/100), Zähler `newcall 96` bestätigt den Mechanismus. `0106` dreht die
Per-Ruf-Logs auf `pr_debug` - die ~120 ms/RPC sind zurück, Treiberpfad still.

**Damit sind alle drei Punkte des Plans erledigt** (1: `0105`/`0106` · 2: Vorschlag von einem Agenten
in Arbeit · 3: `0104`). Serie 79, Rückfallpunkt `GUT-56ef014a`.

## Punkt 2 - Erkennung gelöst, DE-Scaler offen (20:15)

[`E5`](E5-signalchange-feuert-bei-geometrie.md)+[`E6`](E6-aufloesung-erkennung-und-scaler.md), Patch
`0107`: `QUERY_DV_TIMINGS` ist ehrlich (Record `args[1]` + INCAP), die Plane nimmt die Quellgeometrie
an, Y/C-Stride bei 720p korrekt, `mode_config.min_width`-Bug (AddFB2-EINVAL) behoben. **Offen:** die
DE-Composition skaliert Sub-Panel-Quellen nicht (`0x05000174` bleibt 1:1) - der DE-Scaler ist der eine
verbliebene RE-Schritt (`doku/89`, von Stock abschaubar). Bis dahin: `hy310-tv` zeigt Panel-Quellen
voll, andere fallen definiert auf die Konsole (kein verzerrtes Bild). 1080p→720p→1080p am Gerät:
Bild / Konsole / Bild.

**Alle drei Punkte des Plans bearbeitet:** 1 gelöst (`0105`/`0106`), 3 gelöst (`0104`), 2 zum
größeren Teil gelöst, DE-Scaler als klar umrissener Rest. Serie 80, Rückfallpunkt `GUT-56ef014a`.

## Skalierung: 720p laeuft, zwei offene Punkte (08.09., 01:30)

**Die Skalierung funktioniert** - 720p wird korrekt aufs Panel hochskaliert
(`0x05180008 = 0x3200AAAA`, PROC 1280x720 -> 1920x1080), mit Bildbeleg. Vier Patches: `0117`
(Descriptor neu veroeffentlichen), `0120` (Fensterwoerter aufs Panel), `0121` (Aufnahme direkt
freigeben), `0122` (nachfassen bis es haelt).

**Offen:** ein **Gruenstich** ab dem ersten Wechsel (sichtbar an der Taskleiste; Ursache trotz
breiter Suche nicht gefunden, unter Stock tritt er nicht auf) und ein **Kippen nach vier bis fuenf
Wechseln** (Signal weg, Scaler haengt). Einstieg:
[`../97-handoff-20260908.md`](../97-handoff-20260908.md), Details
[`S8`](S8-skalierung-laeuft-und-der-gruenstich.md).

**Werkzeug neu:** die Firmware-Shell (`analyse/hdmi-seq/mipsshell.py`) mit vollstaendigem
Befehlsindex in [`../98-mips-shell.md`](../98-mips-shell.md).

## Was offen ist

* **Ein sporadischer Verlust des RETURN.** Einmal am Vormittag beim Probe-Quellenwechsel
  (`SetSource(HDMI-1) fehlgeschlagen: -110`). `0099` fängt das jetzt mit drei Anläufen ab, aber die
  **Ursache** ist nicht gefunden. Verdächtig ist SW-Spinlock 2 der Routinentabelle, den der MIPS
  ohne Frist nimmt (BEFUND §4). Der isolierte Test dazu lief 40 von 40 fehlerfrei - er widerlegt
  „reproduzierbar", nicht „gelegentlich".
* **Auflösungswechsel** bleibt nicht unterstützt: die Firmware zieht mit, die Anzeigeseite nicht
  (Ring-Zeilenabstand, Zuschnitt, Descriptor bleiben auf 1080p). Erkennbar wäre er jetzt.
* **Echtes Kabelziehen** (K4) kann nur Marco.
* **Audio** des HDMI-Eingangs: nicht angefasst.

## Rückwege

1. **Aktueller guter Stand:** `tftp/h713-kernel-netboot.fit.GUT-56ef014a` +
   `mainline/build/modroot.GUT-56ef014a/` (26 Module). Stand 13:00, alles oben Genannte drin.
2. **Ganz zurück:** `tftp/h713-kernel-netboot.fit.GUT-e39777bf` + `mainline/build/modroot.GUT/`.
   Kostet jede heutige Korrektur - nur als letzter Halt.

**Vor dem Zurückrollen immer erst nachsehen, was es gibt:**
`ls tftp/*.GUT-* mainline/build/modroot.GUT-*` - heute sind drei Zwischenstände entstanden und
wieder gelöscht worden.

**Momentaufnahmen der Patchdateien** (`mainline/patches-snapshots/`, jeweils vor dem genannten
Eingriff): `20260907-103813-vor-hpd-race` · `20260907-110457-vor-freigabe` ·
`20260907-111924-vor-kommentar` · `20260907-112420-vor-0100` · `20260907-113107-vor-0101` ·
`20260907-114252-vor-retry`.

## Regeln, die diese Sitzung teuer gelernt hat

1. **Was am Gerät wirkt, steht in der Patch-Serie** (Nachtplan 0a). Zweimal zugeschnappt.
2. **Ein Kriterium, das nicht scheitern kann, prüft nichts** - und sein Spiegelbild, eines das nicht
   gelingen kann. Fälle: `portmap: 0,1,2` · `QUERY_DV_TIMINGS` (Übersetzungszeit-Konstante) · F's
   `strcmp` gegen ein 16-Byte-Feld · Helligkeit gegen eine weiße Seite · `hue` in Graustufen
   gemessen. **Für Farbregler ist `wandcheck.py` kein Nachweis.**
3. **Agenten schreiben nicht in `mainline/patches/kernel/`.** Vorschläge nach
   `mainline/patches/vorschlaege/<paket>/`; die Aufnahme macht die Hauptsitzung nach Momentaufnahme,
   `diff`, Serienprüfung und **Bau** - die Agenten dürfen nicht bauen, `0101` hätte sonst zweimal
   nicht übersetzt.
4. **Drei Fehlschläge sind nicht ein Muster.** Die drei Callback-Läufe hatten zwei verschiedene
   Ursachen und einen Zufall.
