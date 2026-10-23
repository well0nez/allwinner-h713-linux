# 146 - Handoff HDCP 1.4 und Plan, Stand 05.10.2026 00:3x

> **Überholt.** Der aktuelle Stand der HDCP-Kette steht in [`docs/subsystems/hdcp.md`](../docs/subsystems/hdcp.md), die Durchführung in `doku/148`. Dieser Eintrag bleibt unverändert stehen, weil er der Beleg dafür ist, wann was gemessen wurde — nicht, weil seine Schlussfolgerungen noch gelten.

> **Redigiert (05.10.2026).** Aus diesem Dokument sind die Kennungen und Adressen entfernt, mit denen man das **Trusted OS des Herstellers** direkt anspricht — SMC-Kennungen, Funktionsadressen und die Lage des Hardwareschlüssels im eFuse. Die Befunde bleiben: *dass* der HDCP-1.4-Satz chipgebundenes Chiffrat ist, dass nur die Crypto Engine den Hardwareschlüssel sieht und dass sie ihn nicht nach lesbarem Speicher schreibt. Das erklärt unseren eigenen Weg; der Rest war ein Rezept für fremde Geräte und gehört nicht veröffentlicht.

Fuer eine neue Sitzung ohne Gespraechsverlauf. Leseordnung: diese Datei, dann doku/145 (die
ganze Kette von U-Boot bis Userspace), dann umbau/work/FB-HDCP14h/REPORT.txt (alle Messungen,
507 Zeilen) und dessen INDEX.txt (welche Datei was ist). Fuer alles ausser HDCP gilt weiter
doku/143 - mit den Korrekturen aus Abschnitt 2 hier.

## 1. Zustand der Geraete (beide regulaer, nichts geschrieben)

| | |
|---|---|
| HY310, *geschwärzt am 23.10.2026: Heimnetz-Adresse* | v0.96-beta, Kernel 6.18.38, 0 failed, 5 Dienste aktiv, hci0 UP, Proper md5 872251fd72c89fe06f17c71dc0f274d7, kein BL32. HDMI-Kabel und UART-Bruecke haengen hier. |
| HY300PRO-G-EU, *geschwärzt am 23.10.2026: Heimnetz-Adresse* | Stock-Android mit Magisk-Root, Root ueber `/debug_ramdisk/su -c`, FEL per `adb reboot efex`. Env GEPATCHT: bootdelay=5, loglevel=8, debug_mode=8. |
| ThinkPad, *geschwärzt am 23.10.2026: Heimnetz-Adresse* | Quelle. ssh ohne Hostname, nur per IP; fuer xrandr `DISPLAY=:0` und `XAUTHORITY=<geschwaerzt 23.10.2026: lokaler Pfad>` setzen, sonst liefert es nichts. |

Rueckweg fuer die HY300-Env: `umbau/work/FB-HDCP14h/env/env_a-original.bin` (md5
5cd0ea9703d76d2399dd040722c59e5c, CRC ok) per adb pushen und mit dd auf
`/dev/block/by-name/env_a` schreiben. Der Installer hat ohnehin ein Backup.
Alle Geraetelaeufe dieser Sitzung waren FLUECHTIG (FEL); kein eMMC wurde beschrieben ausser
der HY300-Env, von Marco freigegeben.

## 2. Was an doku/143 und doku/144 ueberholt ist

- doku/143 Abschnitt 11 (Eintraege 18:0x und 18:5x), Abschnitt 12 und 13.A: ueberholt. Zeiger
  stehen dort; die Korrektur ist doku/143 Abschnitt 14, die vollstaendige Kette doku/145.
- doku/144: der 19:00-Nachtrag ist ueberholt (Nachtrag 19:xx dort). HDCP steht jetzt in
  Abschnitt 7 als "nach dem offiziellen Release", nicht release-blockierend (Marco 04.10.).
- Der Satz "Stock laedt gar keinen 1.4-Schluessel" war falsch. Stock tut es, still, im
  Bootloader, vor dem MIPS-Start.
- Die Deutung "Bit 21 = HDCP-2.2-Flag" und der ganze Streit um die eFuse-Flags ist fuer die
  Praxis erledigt: key-select 3 FUNKTIONIERT, die Flags sind administrativ.

## 3. Was erreicht ist

Der Lademechanismus ist nachgebaut und auf BEIDEN Geraeten reproduziert:
```
`<SMC des Hersteller-TEE, nicht abgedruckt>` mit /firmware/optee-Knoten   -> a0 0x0      Shared Memory angemeldet
h713_tee 2                              -> a0 0x0, a1 0x48b00000
h713_tee 1 <slot+0x64>                  -> a0 0x0      Keybox gefuellt
h713_tee 5                              -> a0 0x0      Schluessel in der Key-Senke
```
Voraussetzung dafuer war eine Zeile in unserer TF-A: `bl32_image_ep_info.args.arg0 =
MODE_RW_32`. opteed nimmt die Ausfuehrungsart aus args.arg0, NICHT aus dem SPSR; unsere
Plattform setzte sie nie, OPTEE_AARCH64 ist 0, also wurde das 32-Bit-OP-TEE des Herstellers
als AArch64 gestartet und starb lautlos am ersten Befehl.
Damit ist bewiesen: alles, was FB-HDCP14/14b/14c/14d/14e an der Crypto Engine versucht hat,
scheiterte nicht an der Engine, den eFuses, dem SPC, den Takten oder dem Ziel - sondern daran,
dass der Schluessel nie in der Keybox lag.

## 4. Die sechs Fallen, die es gekostet hat (alle vermeidbar beim naechsten Mal)

1. **args.arg0** - siehe oben. Das Agentenpaket FB-HDCP14g hatte darauf hingewiesen; ich hatte
   es mit Verweis auf opteed_main.c:202 abgetan, die Zeile gilt aber nur im TRANSFER_LIST-Zweig.
2. **CACHES.** Alles, was OP-TEE lesen soll, muss wirklich im DRAM stehen. Mit `cp.b`
   geschriebene Daten sieht es nicht. Am Prompt half ein 8-MiB-Kopiervorgang zum Verdraengen
   (`cp.b 0x60000000 0x68000000 0x800000`); im endgueltigen Code gehoert dort ein
   flush_dcache_range hin.
3. **Der DTB muss nach dem Bearbeiten an eine FRISCHE Adresse kopiert werden** - in-place
   bearbeitet gibt OP-TEE FDT_ERR_BADSTRUCTURE. Und die Adresse kommt aus `bdinfo`
   (fdt_blob), NICHT aus BL31s Meldung: U-Boot verschiebt sich samt DTB.
4. **Der Puffer fuer op 1 muss im angemeldeten Shared Memory liegen** - sonst paniert OP-TEE
   mit einem Nullzeiger, und die Panic nimmt U-Boot mit.
5. **Der Zeiger fuer op 1 ist Slot + 0x64** (der Datenbereich des store_object_t, beginnt mit
   dem 64-Byte-Namen). Slotanfang gibt 0xffffffff, die Nutzlast bei +0xb0 bringt OP-TEE zum
   Absturz ("sunxi_keybox_store:252 sunxi keybox fail to malloc memory").
6. **`\r` ist am ser2net kein Zeilenende** - Befehle mit `\n` senden, sonst kommen sie als
   eine Zeile an. Und jeden Lauf in eine EIGENE Logdatei schreiben; zwei Laeufe in derselben
   Datei haben mich einmal eine Stunde gekostet.
Dazu: das Marker-Verfahren in scripts/mark_optee.py hat NICHT funktioniert (Kontrolllauf auf
dem ersten Befehl blieb stumm). Vor Wiederverwendung erst am Stub nachweisen, dass er ausgibt.

## 5. Wo alles liegt

- `doku/145` - die Kette von U-Boot bis Userspace, mit Rechtsgrundlage und Nachbauplan.
- `umbau/work/FB-HDCP14h/` - REPORT.txt (Messungen), PLAN.txt, INDEX.txt (Wegweiser),
  `patches/0001-tf-a-bl32-and-bringup.diff` (142 Zeilen, enthaelt args.arg0 + BL32_BASE +
  spsr + Diagnose), `patches/0002-u-boot-tee-in-fit-and-h713_tee.diff` (206 Zeilen:
  CONFIG_SUNXI_TEE, tee-Image im FIT, Kommando h713_tee, Schalter h713_hdcp14_wait),
  `scripts/` (11 Werkzeuge), `tools/sunxi_env_patcher.py`, `env/`, `vendor-libs/libsst.so`,
  `uart-*.log` (die beweisenden Mitschnitte sind in INDEX.txt benannt).
- `umbau/work/FB-HDCP14g/` - Machbarkeitsstudie des Agenten (REPORT.txt, evidence.py).
- `umbau/work/FB-HDCP14e/sink-test/` - der Senken-Test, der das alte Gate aufdeckte.
- Arbeitsbaeume: `FB-HDCP14h/tfa` (Kopie), `FB-HDCP14h/uboot` (git worktree des Forks auf
  6fb736c). `umbau/src` und die Submodule sind SAUBER, nichts committet, nichts gepusht.

## 6. Der Warteschleifen-Patch - was er ist und wohin er gehoert

Unser U-Boot setzt die Schleifengrenze der Firmware-Routine `HdmiRx_HDCP14_LoadKey` auf Null
("HDCP key-load wait defeated", h713_mips.c, Instruktion 0x2c630033 -> 0x2c630000). Die
Routine ist genau die, die den Schluessel aus der Senke in den Empfaenger holt - mit dem Patch
laeuft sie sofort in den Timeout. Der Patch stammt NICHT von uns, sondern aus Commit
e5f68f4daf8 von Christopher Stenger ("sunxi: h713: drive the display from the board's own
vendor artifacts"); Begruendung damals: die Ticks, die die Schleife zaehlt, liefen beim
MIPS-Start nicht, die Schleife waere also nie fertig geworden (doku/112).
Ich habe ihn hinter eine Umgebungsvariable gelegt: `h713_hdcp14_wait=1` laesst die
Hersteller-Schleife stehen. Das ist ein Schalter zum MESSEN, kein Endzustand. Sobald 1.4
laeuft, kommt der Patch GANZ heraus (doku/112 verlangt es ohnehin) - dann braucht es die
Variable nicht mehr.
Offen und zu trennen: auf dem HY300 kam die Firmware mit intakter Schleife sauber hoch
("MIPS ready", "readiness proven"), gestartet per `h713_disp init`. Ueber den vollen Boot-Pfad
auf dem HY310 (`run boot_emmc`) ist unser Linux dagegen abgestuerzt - erster Oops ein
Alignment-Fault in `hy310_cpu_comm`. Zwei Kandidaten, siehe Plan Phase 3.

## 7. Plan

### Phase 1 - Minimaltest am HY310, lesend, kein Flash
Ziel: die Folge auf dem HY310 so weit fahren, dass eine Quelle den Schutz anfordern kann.
1. `h713-fel --yes` auf dem HY310 (schreibt die efex-Marke nach 0x07090108 und startet neu;
   keine Taste noetig, hat funktioniert) oder `run fel` am Prompt.
2. `sudo -n sunxi-fel uboot umbau/work/FB-HDCP14h/uboot-O-hy310dbg/u-boot-sunxi-with-spl.bin`
3. Am Prompt: Watchdog entschaerfen (`mw.l 0x02051014 0x16aa0000`), dann die Folge aus
   scripts/hy310_proof.py. Erfolgskriterium: op 1 und op 5 je `a0 0x0`.
4. NEU gegenueber heute: VOR dem Booten den Kernel-DT um die OP-TEE-Reservierung ergaenzen,
   sonst benutzt Linux OP-TEEs Speicher. tee_ram 0x48600000+0x100000 ist durch das Image
   festgelegt; ta_ram und shm kann man frei legen - am einfachsten in einen Bereich, den
   unser DTS schon reserviert (0x6c100000+0x1000000 ist ein Kandidat, vorher pruefen, wofuer
   er da ist). Dann bleibt nur 1 MiB nachzutragen.
5. Booten, und erst dann vom ThinkPad aus den Schutz anfordern:
   `DISPLAY=:0 XAUTHORITY=<geschwaerzt 23.10.2026: lokaler Pfad> xrandr --output HDMI-2 --set "Content
   Protection" Desired`, danach Bksv ueber DDC lesen (20 Einsen = gueltig) und auf "Enabled"
   warten. Gegenprobe unter Stock am HY300: geht, zweimal gemessen.

### Phase 1a - NEUER BEFUND (05.10. 00:5x): die Kernel-Ladeadresse kollidiert
`bootm loados` entpackt unseren Kernel nach 0x48000000 (ca. 32 MiB, der DT landet bei
0x49ff4000) - OP-TEE bei 0x48600000 liegt MITTEN DARIN und wird ueberschrieben, bevor Linux
startet. Das war die Ursache des Absturzes von 00:2x, nicht die fehlende DT-Reservierung
(gegen U-Boots eigenes Entpacken hilft reserved-memory nicht). OP-TEE ist positionsabhaengig
und laesst sich nicht verschieben. Fuer den BL32-Weg muesste also UNSERE Kernel-Ladeadresse
weichen - eine Aenderung an der Kernel-FIT und damit am Release-Abbild.
Zu pruefen: 0x40200000 (zwischen BL31 und dem MIPS-Block waeren 175 MiB frei) und ob
boot0/SPL dort nichts ablegt.
=> Damit wird Phase 2 klar vorzuziehen: gelingt sie, braucht es kein BL32, keine
Layoutaenderung und keinen Hersteller-Blob.

### Phase 2 - den Unterschied im CE-Task messen (der Weg ohne den Blob)
Ziel: herausfinden, was OP-TEE beim key-select-3-Task anders macht als unser EL3 - dann
brauchen wir weder Hersteller-Blob noch eigenes Secure OS, sondern machen beides direkt aus
BL31. Grundlage: OP-TEE fasst die Crypto Engine beim START NICHT an (alle Literale in
0x03040000-0x03042000 liegen in den AES-/Senken-Funktionen <Adresse im Hersteller-TEE>..<Adresse im Hersteller-TEE> und im
Key-Ladder-Pseudo-TA). Es fehlt uns also kein Init; der Unterschied steckt im Task.
1. Nach einem gelungenen op 5 den CE_S-Block und den Deskriptor auslesen (am U-Boot-Prompt
   per `md`, rein lesend) und gegen unseren gescheiterten EL3-Lauf stellen: Deskriptorinhalt,
   Quelladresse, sym_ctl, Speicherattribute. FB-HDCP14c behauptet "Vendor-Task byteidentisch" -
   irgendetwas muss trotzdem abweichen, und das ist jetzt messbar statt vermutet.
2. Wenn der Unterschied gefunden ist: in `umbau/work/FB-HDCP14d/src/.../sunxi_h713_sip.c`
   nachziehen, dort ist HDCP14_LOAD schon fast fertig (und das alte Gate `ce_rssk_probe()`
   gehoert ganz heraus - es prueft etwas, was eine Key-Ladder per Konstruktion verweigert).
3. Nur falls Phase 2 scheitert: ein minimales eigenes Secure-World-Modul mit genau zwei
   Operationen (Keybox entschluesseln, CE-Task in die Senke), AArch64, nach unserer eigenen
   Interpretation der Schnittstelle. OP-TEE ist BSD-2-Clause, Upstream darf also Grundlage
   sein; die Hersteller-Teile (plat-sun50iw12p1, die Ops, Keybox, HDCP) sind NICHT
   veroeffentlicht, es gibt dafuer also auch keinen Quellenanspruch.

### Phase 3 - Integration
1. Den Absturz von Phase 1 trennen: ist es die intakte Warteschleife oder die fehlende
   DT-Reservierung? Zwei Laeufe, je eine Variable.
2. Die Folge an die Stelle legen, an der Stock sie macht: vor dem MIPS-Release in
   `h713_mips_release_reset()`. Mit echtem Cache-Flush, nicht mit dem Verdraengungstrick.
3. Den Warteschleifen-Patch entfernen (Abschnitt 6), known-issues umschreiben, doku/112
   abschliessen.
4. Entscheiden, wie der Blob in die Installation kommt, falls Phase 2 scheitert: NICHT
   ausliefern, sondern bei der Installation aus dem Boot-Paket des Geraets ziehen, wie die 44
   vorhandenen Vendor-Dateien (h713-extract kann boot_package schon).
5. Erst danach 2.2 anfassen - oder gar nicht: 2.2 laeuft bei uns ueber h713-hdcp-key und den
   RPC THal_Vp_SetHDCP22Key und ist abgenommen. Kein Grund, daran zu ruehren.

### Was NICHT gemacht wird
- Op 10 ist der eFuse-Brennpfad und irreversibel. Nie aufrufen; das Kommando h713_tee
  verweigert ihn hart.
- Das Brennen des Schluessels nachbauen: unnoetig. `burn_hdcp_key()` im Composer-HAL laeuft
  nur, wenn `check_hdcp_key()` eine Abweichung findet, und jedes Geraet hatte einmal Stock
  laufen - die geraetegebundene Form ist da, bei beiden Geraeten gelesen.
- `/vendor/etc/firmware/hdcp_1.bin` (368 B) und `hdcp_v22.bin` (960 B) sind Schluesselmaterial.
  Nur die Groessen wurden per `ls` gelesen; der Inhalt nie. Dabei bleibt es.

---

## Nachtrag 05.10., 00:0x–00:3x — der Bildnachweis, und was er (noch nicht) beweist

**HDCP 1.4 war am Bild aktiv.** Nach der Hersteller-Folge aus U-Boot (shm → op 1 → op 5,
alle a0 0x0) und anschließendem `boot` meldete die Quelle:

```
ThinkPad <geschwaerzt 23.10.2026: Heimnetz-Adresse>, HDMI-2 → Beamer:  Content Protection: Enabled
```

i915 setzt diese Eigenschaft erst nach bestandener Link-Authentisierung; im `dmesg` stehen nur
die SRM-Ladeversuche (`display_hdcp_srm.bin -2`, unkritisch), **keine** `authentication
failed`-Zeile. Die Senke hat also authentisiert — und das kann sie nur mit einem Gerätekeyset.

**Was der Nachweis noch nicht trägt:** die Kausalität gegen einen Kaltstart. Der Lauf ging aus
einem vorher laufenden Linux *warm* ins FEL, die TV-Domäne war also vermutlich schon unter
Strom. Und doku/112 §2 Schritt 5 sagt: **die Senke ist flüchtig mit der TV-Domäne** (der
Vendor-Kernel wiederholt op 5 nach jedem Resume in `sunxi_tvtop_complete`). Ein Kontrolllauf
ohne Push fehlt noch — der erste Versuch ging verloren, weil das Gerät nach `systemctl reboot`
nicht zurückkam (Strom lag an, UART und Netz still; seitdem Kaltstarts per `sonoff_ctl restart`).

Nebenbefund aus demselben Boot: die Firmware meldete dreimal
`HdmiRx_HDCP14_LoadKey(), time out!`. Das ist **kein** Widerspruch, sondern cstengers
entschärfte Schleife — sie war aktiv, weil `h713_hdcp14_wait=1` nicht gesetzt war. Das
dokumentierte Erfolgskriterium aus doku/112 §5 ist genau umgekehrt: *keine* Timeout-Meldung
**ohne** den Patch.

### Der Deskriptor ist nicht der Unterschied

doku/112 §2 führt OP-TEEs Task-Deskriptor feldweise. Gegen unseren `ce_run` gestellt, stimmt
jedes Feld (comm_ctl 0x80000100, sym_ctl 0x00300000, key/iv/src/dst, 0x120, Startreihenfolge
TDA→ICR→TLR→ISR→ESR). FB-HDCP14cs „byteidentisch" ist richtig. Ebenso ausgeschieden:
„SRAM statt DRAM" (BL31 liegt auf H713 im DRAM, lmb `reserved[0]` 0x40000000+0x40000) und
„fehlender Init" (OP-TEE fasst die CE beim Start nicht an).

**Übrig bleibt der Zustand**, und doku/112 §3 stellt die Frage selbst, die nie beantwortet
wurde: *„Muss die HDMI-RX-/TVTOP-Domäne beim Transfer an sein?"* Unsere EL3-Versuche liefen
alle am U-Boot-Prompt, also **bevor** `h713_disp init` TVFE/TVCAP einschaltet (Bootlog Zeile 54:
„TVFE/TVCAP powered, capture clocks up before release"). Das ist der nächste Messpunkt.

### Das Warteschleifen-Gatter, neu (h713_mips.c)

Der Patch feuert nicht mehr blind. Er fragt die Hardware nach demselben Bit, das die Firmware
pollt — HDMI-RX `0x06840093` Bit 0, „Schlüssel geladen":

| Lage | Verhalten |
|---|---|
| Bit 0 gesetzt | Schleife **unangetastet** — die Firmware nimmt den Zweig „schon geladen", und genau der macht HDCP 1.4 überhaupt möglich |
| Bit 0 nicht gesetzt | Schleife entschärft wie bisher, damit das Bild auf einem Gerät ohne Schlüssel nicht hängt |
| `h713_hdcp14_wait=1` / `=0` | erzwingt beide Richtungen, zum Messen |

Damit ist cstengers Krücke auf den Fall reduziert, für den sie gedacht war. **Ungemessen** —
sie braucht einen Gerätelauf, bei dem der Push vor dem MIPS-Release passiert.

---

## Nachtrag 05.10., 00:3x–01:0x — der eigene EL3-Pfad: alles gemessen, nichts gefunden

Marcos Auftrag war, U-Boot vom proprietären Code unabhängig zu machen. **Das ist nicht
erreicht**, und zwar nicht aus Mangel an Versuchen. Der Stand, damit niemand dieselben Wege
zweimal geht:

**Unser EL3 kann die sichere Crypto Engine.** Der KAT auf CE_S besteht aus BL31 heraus —
encrypt 16, decrypt 16, **decrypt 288**, key-select 0. Deskriptor, Startreihenfolge,
Cachebehandlung und der 288-Byte-Durchlauf sind also korrekt.

**key-select 3 wird verweigert, ESR 0x11.** Reproduziert in vier Läufen. Und das ist
widerlegt, jedes Mal gemessen oder am Herstellerbinär gegengelesen:

| Hypothese | Befund |
|---|---|
| Deskriptor weicht ab | byteidentisch — aus `optee.bin` selbst verifiziert, nicht nur aus S49 |
| Es gibt einen Vorbereitungsschritt | nein. `sunxi_load_hdcp_key` → `keybox_get` → *dieselbe* Task-Funktion, dieselben Register (TDA/ICR/TLR/ISR/ESR), dieselbe Reihenfolge |
| Die Key-Ladder muss armiert werden | `sunxi_kl_gen_all` ist ein **anderer** Pfad (CW-Schiene), wird von `sunxi_load_hdcp_key` nicht aufgerufen |
| Die Tasklänge | 16 / 32 / 64 / 288 — alle gleich abgelehnt |
| Unser eigener 16-Byte-Torwächter | nicht die Ursache |
| Zustand, Takte, TVTOP-/HDMI-RX-Domäne | unser Task scheitert vor *und* nach dem gelungenen op 5 gleich |
| op 1 macht scharf / op 5 verbraucht | beides nein — A/B/C/D in einer Sitzung gemessen |
| SRAM statt DRAM | BL31 liegt auf H713 im DRAM |
| Geschützte DRAM-Region | 0x02001700er Block hat keine Basis/Grenze-Paare, nur Freigabebits |
| **Pufferort** | kein Unterschied — auch in OP-TEEs eigener TA-RAM-Fläche ESR 0x11 |

Übrig bleibt der nackte Befund: **derselbe Deskriptor, dieselbe Engine, Sekunden auseinander —
aus OP-TEEs S-EL1 läuft er, aus BL31s EL3 nicht.**

### Was als nächstes sinnvoll ist

1. **Vendor-BL31 (`monitor.bin`) durchsehen**, ob sie außerhalb der von uns gespiegelten
   SPC-Folge (0x48001430) noch etwas schreibt, das key-select 3 freigibt — etwa im eigenen
   SMC-Handler bei erster Benutzung. Das ist der einzige verbleibende Ort, denn OP-TEE selbst
   tut nachweislich nichts.
2. **ESR 0x11 verbindlich dekodieren** (Nibble-pro-Flow oder flach). Mainline `sun8i-ce`
   legt BIT(0) ALGO_NOTSUP und BIT(4) KEYLADDER nahe; entscheiden würde der Vendor-Kernel-
   treiber `sunxi_ce` oder ein Registerdatenblatt.
3. Bringt beides nichts, ist der ehrliche Schluss: dieser SoC bindet key-select 3 an das
   Hersteller-Trusted-OS. Dann bleibt der Weg, der in dieser Nacht **am Bild bewiesen** wurde
   — Push aus U-Boot über das geräteeigene OP-TEE, das wir nie ausliefern.

### Werkzeuge, die dabei entstanden sind (alle in FB-HDCP14h)

| FID | Zweck |
|---|---|
| 0x82000011 | HDCP14-Probe (KAT + RSSK), Puffer muss im statischen BL33-Fenster liegen |
| 0x82000012 | eFuse-Flags, nur Statusbits |
| 0x82000013 | ein key-select-3-Task der gegebenen Länge, nur Fehlercode zurück |
| 0x82000014 | derselbe Task mit Puffern an übergebener Adresse (ce_buf relozierbar) |
| 0x82000020 | CE-Dump: CE_S/CE_NS, ESR/TSR, Key-Ladder-Block, Sicherheitsregion, Deskriptor |

Zwei Fallen, die mich je einen Lauf gekostet haben und die im Baum dokumentiert sind:
**U-Boot parst Zahlen hexadezimal** (`16` wird 0x16), und **TF-A nimmt einen Dienst je
Owning Entity** — cedump und SiP hatten beide ein `DECLARE_RT_SVC` auf `OEN_SIP`, worauf die
SiP alle fremden FIDs mit `SMC_UNK` beantwortete. Außerdem: TF-A braucht `SPD=opteed`, sonst
überspringt BL31 BL32 stillschweigend und niemand antwortet auf die shm-Anmeldung.

---

## Nachtrag 05.10., 02:1x–02:3x — FB-HDCP14i: eine eigene Umsetzung

Marcos Auftrag: eine **eigene** Umsetzung, elegant, kein 1:1 übernommener Herstellercode, egal
auf welcher Ebene. Da aus EL3 alles Messbare widerlegt war, ist **S-EL1** der eine Kontext,
den es noch nie gab. Gebaut aus TF-As **eigenem** Secure Payload (`bl32/tsp`, BSD-3-Clause,
upstream) plus unserem Code — kein Byte aus `optee.bin`.

### Was entstanden ist

| Datei | Inhalt |
|---|---|
| `tfa/plat/allwinner/sun50i_h713/tsp/tsp-sun50i_h713.mk` | Plattform-Makefile des Payloads |
| `…/tsp/h713_tsp_setup.c` | Konsole, GIC, Zeitgeber, abschnittsweise Abbildung |
| `…/tsp/h713_tsp_hdcp.c` | unsere CE-Umsetzung an S-EL1, inklusive der **vollständigen Kette** |
| `uboot/arch/arm/mach-sunxi/h713_hdcp14.c` | Slot lesen, Payload rufen, Befehl `h713_hdcp14` |
| `uboot/arch/arm/mach-sunxi/h713_mips.c` | Installation **vor** der MIPS-Freigabe, dann das Gatter |

Die Kette im Payload, zwei Tasks, weil die Hardware so gebaut ist: die gespeicherte Form mit
key-select 3 in den eigenen Puffer entpacken, dann 288 Byte mit key-select 3 in die Senke. Der
Klartext lebt genau für die Dauer eines Aufrufs im Payload-Speicher, wird nie zurückgegeben und
vorher gelöscht. Nachgebaut ist die **Schnittstelle der Engine** (Deskriptorfelder,
Start-Handshake) — die ist von der Hardware vorgegeben, § 69e UrhG.

### Zwei Fehler, beide durch Lesen gefunden

1. `tsp_plat_arch_setup` bildete die ganze Payload-Fläche pauschal als `MT_MEMORY|MT_RW` ab —
   eine **Daten**-Abbildung, also execute-never. Mit MMU an scheitert der erste
   Instruktionsabruf, und stumm, weil der Banner erst danach kommt. Behoben: abschnittsweise
   wie BL31, plus eine Marke **vor** der MMU.
2. Der Push las aus dem Puffer des Aufrufers, den der Payload nicht abbildet → Fault. Behoben
   mit einem definierten Eingabefenster (`0x4c000000`, 2 MiB, `MT_NS`).

### Bereit, aber ungemessen

`FB-HDCP14h/uboot-tsp-bereit.bin` (1 036 800 B) enthält alles; der Lauf liegt als
`scratchpad/eigen.py`: Selbsttest → key-select 3 an S-EL1 (16 und 288 B) → `h713_hdcp14` →
booten → ThinkPad.

**Das Gerät ist seit 02:2x nicht mehr erreichbar** und braucht den Power-Knopf: der Sonoff
trennt bei gestecktem USB nicht wirklich, und `usb3-port*/disable` schaltet am Intel-Root-Hub
nur logisch ab. Mein Fehler dabei: ich habe wie in allen Läufen davor den Watchdog entschärft —
gerade der hätte den stillen Lauf nach 11 s zurückgeholt. Für unbeaufsichtigtes Arbeiten gilt
ab jetzt `NACHTREGEL.txt`: scharf lassen.
