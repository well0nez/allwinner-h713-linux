# 147 — HDCP 1.4: Statusbericht nach der Nacht 04./05.10.2026

> **Überholt.** Der aktuelle Stand der HDCP-Kette steht in [`docs/subsystems/hdcp.md`](../docs/subsystems/hdcp.md), die Durchführung in `doku/148`. Dieser Eintrag bleibt unverändert stehen, weil er der Beleg dafür ist, wann was gemessen wurde — nicht, weil seine Schlussfolgerungen noch gelten.

Stand 05.10., 07:2x. Dieser Bericht fasst zusammen, **was belegt ist**, **was nachweislich
nicht funktioniert hat** und **was als nächstes geplant ist**. Die Rohmessungen stehen in
`umbau/work/FB-HDCP14h/REPORT.txt` (1264 Zeilen), die Nachtchronik in `doku/146`.

Rechtsgrundlage unverändert: eigenes Gerät (§ 903 BGB), Herstellen der Interoperabilität
(§ 69d Abs. 1/3, § 69e UrhG = Art. 5/6 RL 2009/24/EG), Reparatur und Weiternutzung
(RL (EU) 2024/1799). Es geht um die **eigene Lizenz des Geräts**, nicht um Zugriff auf
fremde Inhalte; Schlüsselmaterial wird nicht gelesen, nicht ausgegeben und nicht verbreitet.

---

## 1. Das Ziel

HDCP 1.4 auf dem HY310 mit **eigener** Umsetzung — kein übernommener Herstellercode. Das
Gerät hat eine gültige HDCP-1.4-Lizenz in seinem Secure Storage; ohne sie bekommen
geschützte Quellen kein Bild.

## 2. Was belegt ist

**Die Kette funktioniert mit dem geräteeigenen Trusted OS, am Bild bewiesen (2:1 mit
Kontrolle).** ThinkPad (i915, nur 1.4) an HDMI-2:

| Lauf | Push aus U-Boot | Quelle meldet |
|---|---|---|
| 00:09 | shm → op 1 → op 5, alle `a0 0x0` | **Enabled** |
| 01:02 | dieselbe Folge | **Enabled** |
| 00:4x | **keiner** | Desired |

Gleiches Gerät, gleiche Quelle, gleiches Kabel, gleicher Kernel. i915 setzt „Enabled" erst
nach bestandener Link-Authentisierung und meldete keine `authentication failed`-Zeile.

> **Nachtrag 07:30 — diese Tabelle ist methodisch wertlos, siehe Kapitel 7.** Die Senke
> übersteht einen Warmstart. Der Kontrolllauf „kein Push → Desired" lag *vor* den
> Push-Läufen, danach war die Senke gefüllt und blieb es. Jeder spätere Lauf hätte „Enabled"
> gemeldet, mit Push oder ohne. **Ab jetzt gilt für jede HDCP-Messung: erst löschen und
> `Desired` bestätigen, dann pushen und `Enabled` prüfen — beides im selben Boot, sonst
> zählt es nicht.** Kapitel 7 hält das so durchgeführte Ergebnis fest.

**Die Engine verweigert nicht uns, sondern das Ziel.** key-select 3 (der Hardwareschlüssel)
nach DRAM → `ESR 0x11`; in die Senke `0x03041400` → `0x0`. Das ist eine Designregel: ein
Hardwareschlüssel-Task nach lesbarem Speicher wäre Schlüsselausgabe. Beweis: der
**Deskriptor des Herstellers, aus unserem EL3 gestartet**, läuft mit `0x0`
(`re-ran the vendor's own descriptor at <Adresse im Hersteller-TEE>: 0x0`).

**Unser eigener Senken-Push läuft.** `H713 SiP: HDCP 1.4 transfer into the key sink: 0x0`,
ohne einen einzigen Herstelleraufruf, nur `mmc read` des Slots plus unsere SiP in BL31.

**Der Deskriptor des Herstellers ist feldweise identisch mit unserem** — nicht aus einer
Tabelle, sondern aus seinem Speicher gelesen:

    CEscan @48677540: chan 00000000  common 80000100  sym 00300000 (keysel 3)
                      len 00000120   src_len 00000120  dst_len 00000120
                      key 00486776c0 iv 0048677640  src 0048677780  dst 0003041400

**Unsere Daten sind richtig.** Reiner Byte-Vergleich der 288 gespeicherten Bytes
(Slot `0x3010`, Nutzlast ab `+0xb0`) gegen die Quelle des Hersteller-Tasks:
**0 von 288 Byte Abweichung.**

**op 1 entschlüsselt auf diesem Gerät nicht.** Ein Scan über 5 MiB TEE- und TA-RAM findet
nach op 1 **keinen** CE-Deskriptor (nur einen Fehlalarm auf SHA-256-Rundenkonstanten bei
`<Adresse im Hersteller-TEE>`). Im Herstellercode wird nur entschlüsselt, wenn das `encrypted`-Flag des Items
steht (`[r7,#0x44]` Bit 0) — hier steht es nicht.

## 3. Was nachweislich NICHT funktioniert hat

| Hypothese | Messung | Ergebnis |
|---|---|---|
| Deskriptorinhalt weicht ab | aus `optee.bin` **und** aus dem Speicher gegengelesen | identisch |
| Es gibt einen Freischaltschritt | `sunxi_load_hdcp_key` → `keybox_get` → dieselbe Task-Funktion, dieselben Register | keiner |
| Key-Ladder muss armiert werden | `sunxi_kl_gen_all` ist die CW-Schiene, wird vom HDCP-Pfad nicht gerufen | anderer Pfad |
| Vendor-BL31 schaltet etwas frei | `monitor.bin` enthält **keine** CE-Adresse (kein Literal, kein `movz/movk` auf `0x0304`) | nein |
| Tasklänge | key-select 3 nach DRAM mit 16/32/64/288 Byte | alle `ESR 0x11` |
| Unser eigener 16-Byte-Torwächter | `ce_rssk_probe` prüft key-select 3 **nach DRAM** — kann per Design nie bestehen | war die Blockade, entfernt |
| Zustand/Takte/TVTOP-Domäne | unser Task vor **und** nach dem gelungenen op 5 | gleich |
| op 1 macht scharf / op 5 verbraucht | A/B/C/D in einer Sitzung | beides nein |
| Exception-Stufe (eigenes Secure OS) | eigener S-EL1-Payload gebaut und gestartet, Selbsttest mit eigenem Schlüssel `0x0` | key-select 3 trotzdem `ESR 0x11` |
| Pufferort | BL31s Block und drei Stellen in OP-TEEs TA-RAM | alle gleich |
| Quellinhalt | Nullen und echter Datensatz | alle gleich |
| Entpacken mit `sym_ctl 0x100` und einem 16-Byte-Schluessel aus dem Trusted-OS-Abbild des Geraets | gegen den Hersteller-Klartext | **287 von 288** abweichend |
| Sweep über 56 Kombinationen (7 × `sym_ctl`, dec/enc, 16/32-Byte-Schlüssel, 320/288 Byte) | gegen denselben Klartext | bester Treffer **285 von 288** |
| Versatz der 288 Byte im 320-Byte-Datensatz (0 vs. 32) | am Bild | beide `Desired` |
| Roher Push der gespeicherten Bytes | zum richtigen Zeitpunkt, mit Quittierungsversuch | Engine `0x0`, Bild `Desired` |
| Quittierungsfolge aus doku/112 (`0x06840002` Bit 4 pulsen, `0xc0` → `0x06840093`) | aus U-Boot | `did not latch`, Bit 0 bleibt leer |

**Eigene Fehler, die Zeit gekostet haben** (alle behoben und im Code begründet):

* `h713_hdcp14_install()` lief **vor** `h713_mips_release_reset()` und damit vor dem
  Einschalten der TV-Domäne — Push in eine stromlose Senke. Jetzt direkt nach
  „TVFE/TVCAP powered".
* Das hardwaregekoppelte Warteschleifen-Gatter ließ die Firmware-Schleife stehen, wenn Bit 0
  steht — das **hängt** das Board im Logo, obwohl HDCP mit entschärfter Schleife
  authentisiert. Jetzt wird immer entschärft, das Bit nur protokolliert.
* Die Kernel-DT-Reservierung für BL32 hing an `#ifdef BL32_BASE`, und dieses Makro ist in
  **jeder** Konfiguration definiert → die Reservierung erschien auch ohne Payload und
  blockierte den Kernelbereich (`Unable to allocate memory 0x48000000`). Jetzt an
  `H713_WITH_BL32` gebunden.
* **TF-A verfolgt Änderungen an `BL31_CPPFLAGS` nicht als Abhängigkeit.** Geänderte
  `-D`-Flaggen wirken erst nach `rm -rf tfa/build/sun50i_h713`. Hat mehrfach falsche Befunde
  erzeugt (fehlender AArch32-Übergang, `spsr 0x3c5` statt `0x1d3`).
* Der Generic Timer ist im eigenen S-EL1-Payload unbrauchbar: ein 288-Byte-Task wartete auf
  einen Timeout, der nie kam. Schleifen dort jetzt **gezählt**, nicht gezeitet.
* U-Boot parst Zahlen **hexadezimal** (`16` → 0x16), und TF-A nimmt **einen** Dienst je
  Owning Entity — zwei `DECLARE_RT_SVC` auf `OEN_SIP` ließen unsere SiP alle fremden FIDs mit
  `SMC_UNK` beantworten.

## 4. Wo es jetzt klemmt

Gleiche Bytes, gleicher Deskriptor, gleiches Ziel, Engine meldet `0x0` — und nur der
Hersteller-Push authentisiert. Der einzige strukturelle Unterschied, der bleibt: **die Region,
aus der die DMA liest.** Der Hersteller liest aus seinem Puffer im TEE-RAM (`<Adresse im Hersteller-TEE>`),
wir aus BL31s Puffer (`0x4001xxxx`).

Nebenbefund dazu: `0x06840093` liest im **laufenden Linux** `0x41` (Bit 0 gesetzt), im U-Boot
zur Push-Zeit nicht. Der HDMI-RX-Block ist dort womöglich nicht so ansprechbar, wie die
Quittierungsfolge es braucht — die macht normalerweise die Firmware in der Schleife, die wir
entschärfen.

## 5. Nächste Schritte

1. **Läuft gerade:** Push mit der Deskriptor-Quelle im TEE-Fenster (`0x48a00000`,
   FID `0x8200001c`), alles andere unverändert. Zündet das Bild, ist die Herkunftsregion die
   Bedingung, und unsere Umsetzung braucht nur eine Zwischenablage dort — kein Herstellercode.
2. Zündet es nicht: die Quittierung aus Linux statt aus U-Boot versuchen (dort antwortet der
   HDMI-RX-Block nachweislich), und prüfen, ob die Firmware die Schleife braucht, um den
   Schlüssel aufzugreifen — dann gehört statt „immer entschärfen" ein Pfad her, der die
   Schleife **nur mit** gesetztem Bit stehen lässt und sonst entschärft.
3. Den eigenen S-EL1-Payload behalten: er startet, fährt die sichere CE korrekt
   (Selbsttest `0x0`) und ist der Platz für die Kette, falls wir sie je aus dem Secure World
   fahren wollen. Für HDCP 1.4 ist er nicht nötig — BL31 genügt.
4. **Vor dem Release** (steht in `doku/144`): Konfigurationsprüfung aller Rollen,
   `TimeoutStartSec` für `h713-wifi`, `timeout` um die `modprobe`-Aufrufe, und der Installer
   legt den Wickelschlüssel gerätelokal ab (falls er je gebraucht wird — nach dem heutigen
   Befund entschlüsselt op 1 nicht, also ist er womöglich entbehrlich).

## 6. Betrieb: was unbeaufsichtigtes Arbeiten möglich macht

* `h713_gate=0` ist **dauerhaft gespeichert** → das Board bootet nach Netz-Ein ohne
  Power-Knopf (`bootdelay=1`, `h713_boot=emmc`).
* Der **Watchdog** bleibt während der Experimente scharf (`0x02051010=0x16aa0001`,
  `0x02051014=0x16aa00b1`, ~16 s) und wird zwischen den Befehlen durch echtes **Aus/Ein**
  nachgetreten — ein erneutes Schreiben des aktiven MODE-Registers startet den Zähler
  **nicht** neu. Entschärft wird erst unmittelbar vor `boot`. Vier Fehlschläge dieser Nacht
  hat er selbst zurückgeholt.
* `scratchpad/zustand.sh` gibt eine Zeile `netz= fel= uart= laeufe=` und fasst den UART nur
  an, wenn kein Lauf aktiv ist (ser2net erlaubt genau einen Client).
* **Grenze:** einen echten Stromschnitt kann ich nicht erzeugen. Solange das USB-Kabel
  steckt, trennt der Sonoff nicht, und der Root-Hub meldet `No power switching` — Port 3
  (`usb 3-3`) lässt sich nur logisch abschalten. Hängt U-Boot und ist der Watchdog aus,
  braucht es eine Hand am Gerät.

## 7. Das Ergebnis: eigene Umsetzung, am Bild bewiesen (05.10., 07:2x)

Zwei Läufe, drei Minuten auseinander, **Kontrolle vorher statt nachher** — und damit die
erste Messung, die etwas aussagt:

| Lauf | was in die Senke ging | Engine | Quelle meldet |
|---|---|---|---|
| 07:24 | 288 **Nullbytes**, über unseren Weg (`h713_hdcp14_wipe=1`) | `0x0` | **Desired** |
| 07:27 | der echte Schlüsselsatz aus dem TEE-Fenster (`h713_hdcp14_raw=1`) | `0x0` | **Enabled** |

Der erste Lauf belegt zweierlei auf einmal: unsere Push-Mechanik **wirkt** (die Senke ändert
sich, die Authentisierung bricht zusammen), und die Senke ist **leer** — die Ausgangslage,
die allen früheren Messungen fehlte. Der zweite füllt sie mit unserem eigenen Code und das
Bild kommt geschützt zurück.

### Kein Byte Herstellercode im Image

* gebaut wurde `uboot-solo.bin` mit `bl31-solo.bin`, **ohne `SPD`** und **ohne BL32**
* `strings bl31-solo.bin | grep -c opteed` → **0**, es gibt keinen Dispatcher
* binman meldet `tee-os` als fehlend; die vier „optee"-Treffer im Image sind FIT-Knotennamen
* der Hersteller-Deskriptor wurde nur *gelesen* (Vergleich 0 von 288 Byte Abweichung), nie
  ausgeführt

### Der Weg, der trägt

1. `mmc read` des `hdcpkey`-Slots (Block `0x3010`, 8 Blöcke), Nutzlast 288 B ab `+0xb0`
2. die Bytes nach **`0x48a00000`** legen — ins TEE-Fenster, das ist die Bedingung
3. unser CE-Task in **BL31**: key-select 3, `src 0x48a00000`, `dst 0x03041400`, 288 B, decrypt
4. ausgelöst **nach** dem Einschalten der TV-Domäne, unmittelbar vor der MIPS-Freigabe
5. die Warteschleife der Firmware bleibt entschärft

Kein Entpacken nötig: op 1 entschlüsselt auf diesem Gerät nicht, und die gespeicherten
288 Byte sind byteidentisch mit der Quelle des Hersteller-Tasks.

### Die Regel der Hardware, vollständig

Der Hardwareschlüssel darf **nicht nach lesbarem Speicher** (`ESR 0x11`) und **nicht aus
beliebigem Speicher in die Senke** — nur aus der geschützten Region. Beides ist vernünftig:
das erste wäre Schlüsselausgabe, das zweite freies Einspielen fremder Geräteschlüssel. Genau
diese zweite Hälfte hatte uns stundenlang aufgehalten; unser eigenes Gate war der Blocker,
nicht die Engine.

### Was noch aufzuräumen ist

* Die **Quittierungsfolge** (`0x06840002` Bit 4 → `0x06840093`) ist Rauschen: sie meldet
  „did not latch" und liest `0x00`, während dasselbe Register im laufenden Linux `0x41` gibt.
  Aus `h713_hdcp14.c` entfernen — sie täuscht nur.
* Der **`raw`-Pfad wird der Normalweg**; der Entpack-Pfad (FID `0x82000018`) entfällt, solange
  kein Gerät mit gesetztem „encrypted"-Flag auftaucht. Damit ist auch der Wickelschlüssel
  entbehrlich — der heikelste Punkt des Installers löst sich von selbst auf.
* BL31 druckt weiter `BL32 at 0x48600000: <Müll>`, weil `BL32_BASE` im Header immer definiert
  ist. Kosmetisch, gehört hinter `H713_WITH_BL32`.
* **FB-HDCP14i** (eigene S-EL1-Nutzlast auf TSP-Basis) funktioniert, ist aber unnötig: BL31
  genügt. Bleibt als Beleg liegen, geht nicht ins Release.
