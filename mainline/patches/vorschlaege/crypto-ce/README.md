# crypto-ce — ein Messlauf am Deskriptorformat der H713-Crypto-Engine

**Vorschlag, noch nicht in der Serie.** Vier Patchdateien plus Bauprotokoll. Zusammenführen macht Marco;
`mainline/patches/kernel/series` ist unangetastet.

Das hier ist **Plan [114](../../../../doku/114-plan-crypto-engine.md) §7 Schritt 2 und 3** in Code: der Gerätebaum
beschreibt die CE endlich so, wie der Hersteller sie beschreibt, und ein Messmodul setzt **genau einen** Task im
Vendor-Deskriptorformat ab, als echter Known-Answer-Test. Es beantwortet eine einzige Frage:

> Liest die Crypto Engine des H713 den Task-Deskriptor so, wie wir ihn aus OP-TEE rekonstruiert haben?

Die Belegkette dahinter ist [`S49`](../../../../doku/nachtlog/S49-hdcp14-schluesselpfad.md) (statische RE aus OP-TEE 3.7)
und cstengers Messreihe am Gerät (`git -C mainline show bb44dc8`). Der Umsetzungsauftrag für HDCP 1.4 selbst bleibt
[`112`](../../../../doku/112-plan-hdcp14-crypto-engine.md) und ist zurückgestellt.

**Es fasst kein Schlüsselmaterial an.** Key-Select 3 (RSSK) kommt nicht vor, die Schlüsselsenke `0x03041400` kommt
nicht vor, der Secure Storage wird nicht gelesen und nicht beschrieben.

---

## Die vier Patches

### 0001 — `dt-bindings: crypto: die Crypto Engine des H713 beschreiben`

Neues Bindungsdokument `allwinner,sun50i-h713-crypto.yaml`. Eigenes `compatible`, **ausdrücklich ohne H6-Rückfall**:
mit Rückfall würde sich `sun8i-ce` anbinden, sobald jemand den Treiber einschaltet, und wieder Deskriptoren im falschen
Format absetzen. Beschreibt zwei Registerbänke (je `0xa0`), zwei Interrupts, vier Takte (`bus`, `mod`, `ram`, optional
`sys`) und zwei Resets (`bus`, optional `sys`).

### 0002 — `arm64: dts: h713: beide CE-Bänke und beide Interrupts abbilden`

Der Knoten `crypto@3040000` beschrieb bisher **ein** Fenster (`0x03040000`, `0x1000`) und **einen** Interrupt (SPI 73).
Jetzt: zwei Fenster (`0x03040000` und `0x03040800`, je `0xa0`), zwei Interrupts (SPI 73 und 74), vier Takte, zwei Resets.
Die Größe des ersten Fensters muss dabei von `0x1000` auf `0xa0` sinken — `0x03040000 + 0x1000` hätte die zweite Bank
überdeckt, und überlappende Fenster nimmt kein Treiber entgegen.

Solange kein Treiber das neue `compatible` führt, bleibt der Knoten **inert** — genau wie vorher, nur richtig beschrieben.

### 0003 — `crypto: allwinner: h713-ce-test — ein Task im Vendor-Deskriptorformat`

Das Messmodul, 959 Zeilen. **Kein Krypto-Treiber:** es registriert nichts beim Krypto-Kern, ersetzt `sun8i-ce` nicht
und läuft nicht von allein. Es baut einen `struct h713_ce_task` (0x100 Byte, 64-Byte-ausgerichtet, genullt,
Adressfelder im 5-Byte-Raster), setzt ihn über TDA/ICR/TLR ab, pollt das ISR, liest das ESR und vergleicht 16 Byte
Chiffretext gegen FIPS-197 Anhang C.1. Beide Registerbänke sind gemappt, beide Interrupts angefordert; der
Interruptbehandler zählt nur und maskiert seine Leitung, die Fertigmeldung kommt aus dem gepollten ISR.

### 0004 — `build: das CE-Messmodul im Board-defconfig bauen`

**REPO-Datei, nicht Kernelbaum** — mit `-p1` aus `mainline/` anwenden. Eine Zeile `CONFIG_H713_CE_TEST=m` plus
Kommentar. `CONFIG_CRYPTO_DEV_SUN8I_CE` bleibt aus, `CONFIG_HW_RANDOM` bleibt aus (Plan 114 Frage A, cstengers Befund).
Als Modul, nicht fest: ein Messlauf soll eine Entscheidung bleiben. Für ein Release kann die Zeile wieder raus, dann
bleibt nur der Gerätebaum-Knoten, und der ist ohne Treiber inert.

---

## Was belegt ist und was geraten

### Belegt

| Sache | Beleg |
|---|---|
| Deskriptor 0x100 Byte, 64-Byte-ausgerichtet, genullt | S49 „Registersequenz“, Vorspann; OP-TEE `0x4860c58c` (`bic #0x3f`), `0x4860c5ac` (`memset 0x100`) |
| Feldlage `chan_id` +0x00, `comm_ctl` +0x04, `sym_ctl` +0x08 | S49-Tabelle Zeilen 1–3; `0x4860c578`, `0x4860c5ec`, `0x4860c5f2` |
| `key_addr` +0x10, `iv_addr` +0x15 | S49-Tabelle Zeilen 4–5; `0x4860c5f8`, `0x4860c60a` |
| `data_len` +0x20, `src_addr` +0x24, `dst_addr` +0x29, `src_len` +0x30, `dst_len` +0x34 | S49-Tabelle Zeilen 6–9; `0x4860c616`, `0x4860c618`, `0x4860c61c`, `0x4860c620`, `0x4860c626` |
| **5 Byte Abstand** zwischen den Adressfeldern | die krummen Offsets selbst: OP-TEE schreibt `iv_addr` und `dst_addr` mit `memcpy` auf 0x15 und 0x29 — ein Wortzugriff ginge dort gar nicht |
| `comm_ctl` = INT(31) ∣ decrypt(8) ∣ ALG_AES(0) | S49-Tabelle Zeile 2; `0x4860c5e6`–`0x4860c5ec` |
| Registeroffsets TDA 0x00, ICR 0x08, ISR 0x0c, TLR 0x10, ESR 0x18 | S49-Tabelle Zeilen 10–14; `0x4860c334`, `0x4860c2ac`, `0x4860c360`, `0x4860c2d0`, `0x4860c348` |
| Startfolge TDA → ICR → TLR, dann ISR pollen, quittieren, ESR lesen | `0x4860c6a6`–`0x4860c6d4` in genau dieser Reihenfolge |
| ISR belegt zwei Bits je Kanal (fertig / Fehler) | `0x4860c376` vergleicht die maskierten Bits mit 2 |
| **`sym_ctl` = (key_type ≪ 20) ∣ (aes_mode ≪ 8) ∣ Schlüssellänge[1:0]** | `sunxi_aes_do_crypt` `0x4860c79c`–`0x4860c7a8`, OP-TEEs eigener Debug-Text nennt es „alg_cfg“ |
| **Key-Select 0 = Schlüssel aus `key_addr`** | `0x48626214` ruft `sunxi_aes_with_hardware` mit echtem 16-Byte-Schlüssel, Länge 0x10, mode 0x100 — key_type ist dort 0 |
| Zwei Registerbänke, je 0xa0; zwei Interrupts SPI 73/74 | Vendor-DT `re/vendor/HY310/hy310_factory.dts` Zeile 1881–1890 |
| **Der zweite Interrupt ist nötig** | cstenger, am Gerät gemessen: mit nur SPI 73 hängt die erste Operation, mit beiden läuft sie durch (`bb44dc8`) |
| **NS-Kanal ist aus Linux erreichbar** | cstenger: die CE nimmt NS-Schreibzugriffe an, arbeitet und gibt Status zurück, kein Bus-Abort |
| **Falsches Format ⇒ `address invalid`** | cstenger: mainline-Deskriptoren, Standard-AES, ESR-Bit 5 samt aller Fehlerbits |
| Der Bootloader schaltet **zwei** Gates und **zwei** Resets | Stock-U-Boot `0x4a028848`: CCU `0x680`, dann `0x68c \|= 3` (`0x4a028898`) und `0x68c \|= 0x30000` (`0x4a0288ba`) |
| Der Referenzvektor | FIPS-197 Anhang C.1 (= SP 800-38A F.1.1, erster ECB-Block); zweimal unabhängig nachgerechnet, siehe Bauprotokoll §9 l |

### Geraten — steht so auch im Quelltext, mit „Vermutung“ bzw. „Analogie“ daneben

| Sache | Warum es nur geraten ist | Wo es steht |
|---|---|---|
| `aes_mode` 0 = ECB, 1 = CBC | OP-TEE benutzt 0 nur mit Hardwareschlüssel und 1 nur mit Softwareschlüssel, nennt die Modi nie. `sun8i-ce.h` kodiert es so. S49 „Was dagegen spricht“: „**ECB** (Bits 11:8 = 0) … geschlossen, nicht aus einem Datenblatt“ | `AES_MODE_ECB`/`AES_MODE_CBC` im Modul |
| ESR-Bitbedeutungen (0 Algo, 1 Datenlänge, 2 Key-SRAM, 5 Adresse, 6 Key-Ladder) | aus `sun8i-ce.h` (Variante ESR_H6) übernommen; dass sie für den H713 gelten, ist nicht belegt. cstengers Bit 5 passt dazu | `CE_ERR_*` im Modul |
| `ctr_addr` bei +0x1a | OP-TEE beschreibt das Feld **nie**; die Lage folgt nur aus der Lücke zwischen `iv_addr` und `data_len`. Bleibt null | Feldkommentar „VERMUTUNG“ |
| `bus_ce_sys` / `RST_BUS_CE_SYS` versorgen die sichere Bank | Belegt ist nur, dass der Bootloader sie einschaltet. Der Vendor-DT nennt das Gate nicht, OP-TEE fasst die CCU nie an | `clock-names = "sys"`, im Treiber optional |
| Key-Select-Feld liegt bei [23:20] | S49: „Die Zuordnung ‚Feld [23:20] = Key-Select, 1 = SSK, 3 = RSSK‘ ist ein Analogieschluss aus Allwinners CE-Registerlayout plus der Funktionsnamen.“ Die **Aufteilung** ist inzwischen belegt (siehe oben), die **Bedeutung der Werte 1 und 3** nicht | `CE_SYM_KEYSEL` |
| CE_S `0x03040800` ist aus der Non-Secure-Welt sichtbar | S49 „Was dagegen spricht“: „rein statisch nicht bestimmbar“. **Genau das soll der zweite Durchlauf klären** | Warnung vor dem `s`-Lauf |
| Interrupttyp Pegel statt Flanke | Der Vendor-DT gibt für beide Leitungen Typ 1 (steigende Flanke) an; wir bleiben bei Typ 4 (Pegel), weil cstenger damit Fertigmeldungen bekommen hat | Begründung in 0002 |

---

## Der Gerätetest

**Kostet einen Stromzyklus und kann den Bus aufhängen.** Vorher ansagen. Das Modul ist bisher **nie geladen worden** —
alles oben ist gebaut und statisch geprüft, nicht gemessen.

### Vorbereitung

Die vier Patches zusammenführen, Kernel und DTB bauen, aufs Gerät bringen. `CONFIG_DEBUG_FS=y` steht im defconfig
(Zeile 261), `debugfs` muss gemountet sein (`mount -t debugfs none /sys/kernel/debug`, bei Debian ohnehin da).

Das Modul lädt beim Start über den Gerätebaum-Knoten **von allein** (udev, das `compatible` passt), **misst aber nicht**.
Nach dem Laden steht im Kernlog:

```
h713-ce-test 3040000.crypto: Takte an: bus ... Hz, mod 300000000 Hz, ram ... Hz; bus_ce_sys an, RST_BUS_CE_SYS ...
h713-ce-test 3040000.crypto: bereit. Baenke 0x03040000 (IRQ ..) und 0x03040800 (IRQ ..), Puffer bei 0x...
h713-ce-test 3040000.crypto: kein Lauf. Starten mit: echo ns > /sys/kernel/debug/h713-ce-test/starten
```

Die Zeile „RST_BUS_CE_SYS war noch gesetzt / war schon aufgehoben“ ist selbst ein Messergebnis: sie sagt, ob unser
Bootloader den zweiten Reset schon aufgehoben hatte.

### Reihenfolge — NS-Kanal zuerst, immer

```sh
# 1. Vorzustand festhalten
dmesg -w &                                  # oder: journalctl -kf
cat /sys/kernel/debug/h713-ce-test/ergebnis

# 2. NS-Kanal, ECB. DAS ZUERST.
echo ns > /sys/kernel/debug/h713-ce-test/starten
cat /sys/kernel/debug/h713-ce-test/ergebnis

# 3. Nur falls Schritt 2 "Algorithmus nicht unterstuetzt" (ESR-Bit 0) meldet:
#    derselbe Task mit OP-TEEs eigener Softwareschluessel-Konfiguration
#    (aes_mode 1, CBC mit IV 0 -- gleicher Erwartungswert).
echo "ns cbc" > /sys/kernel/debug/h713-ce-test/starten
cat /sys/kernel/debug/h713-ce-test/ergebnis

# 4. ERST DANN CE_S. Kann den Bus aufhaengen.
echo s > /sys/kernel/debug/h713-ce-test/starten
cat /sys/kernel/debug/h713-ce-test/ergebnis
```

Das Ergebnis steht an **zwei** Stellen, gleichlautend:

* im **Kernlog** als eine Zeile, die mit `ERGEBNIS:` beginnt (`dmesg | grep ERGEBNIS`),
* in **`/sys/kernel/debug/h713-ce-test/ergebnis`**, ausführlicher: ISR, ESR roh und maskiert mit Klartext, TSR, TLR,
  zurückgelesenes TDA, Zählerstand beider Interruptleitungen, und bei falschem Chiffretext die 16 Byte im Vergleich.

Ohne Anstoß misst nichts. `modprobe h713-ce-test autostart=1` (optional `bank=1`, `aes_mode=1`) tut dasselbe beim Laden
— für den ersten Lauf ist der debugfs-Weg der bessere, weil das Modul dann schon geladen und der Vorzustand sichtbar ist.

**Warum NS zuerst:** der NS-Kanal ist nach cstengers Messung aus Linux erreichbar, CE_S ist die offene Frage. Der
NS-Lauf zeigt, wie ein funktionierender Lauf auf dieser Hardware *aussieht* — welche Werte TDA, ISR und TSR annehmen,
welche Leitung feuert. Erst mit diesem Vergleichsbild ist der CE_S-Lauf deutbar. Ein CE_S-Lauf ohne NS-Vergleich kann
nicht zwischen „Bank nicht sichtbar“, „Block abgeschaltet“ und „Register nur schreibbar“ unterscheiden.

### Die drei möglichen Ausgänge

#### 1. Bestanden — `ERGEBNIS: bestanden. Vendor-Deskriptorformat auf ... bestaetigt, ESR sauber, KAT stimmt`

ESR ist 0 und die 16 Byte stimmen mit `69c4e0d8 6a7b0430 d8cdb780 70b4c55a` überein. **Das Deskriptorformat aus S49 ist
bestätigt** — und zwar durch einen echten KAT, nicht durch „kein Fehler“. Zusammen mit cstengers Gegenprobe (mainline-
Format ⇒ `address invalid`) ist das ein Beleg mit gemessenem Kontrast in beide Richtungen.

Sagt der Lauf das für **NS**: der Non-Secure-Kanal kann das Vendorformat fahren.
Sagt er es auch für **CE_S**: die sichere Bank ist aus der Non-Secure-Welt benutzbar.

→ **Weiter mit Plan 114 §7 Schritt 3 zweiter Teil**: derselbe Task mit **Key-Select 3, Ziel weiterhin DRAM**. Liefert er
16 Byte irgendetwas, darf NS den RSSK → Einbauort **4a (Linux)**. Liefert er ESR-Fehler, muss der Pfad nach EL3 → **4b
(TF-A-SiP-SMC)**. Erst danach, in Plan 112, wird überhaupt auf `0x03041400` gezielt.

#### 2. ESR-Fehler — `ERGEBNIS: ESR-Fehler 0x... : <Klartext>. Deskriptorformat oder Kanal falsch.`

Der Fehlerwert steht roh und maskiert da, die gesetzten Bits im Klartext. Zwei Fälle zählen besonders:

* **Bit 5, „Adresse ungueltig“** — das Modul sagt es ausdrücklich dazu: *„Bit 5 ist genau cstengers Signatur des
  falschen Formats.“* Dann liest die Maschine auch aus **diesem** Deskriptor Müll, und S49s Feldlage ist an mindestens
  einer Stelle falsch. Nächster Schritt wäre nicht ein weiterer Stromzyklus, sondern zurück ins Disassemblat: `ctr_addr`
  ist die einzige geratene Feldposition, und die Lücke bei +0x1f / +0x2e ist die einzige Stelle, an der sich etwas
  verschieben könnte.
* **Nur Bit 0, „Algorithmus nicht unterstuetzt“** — dann wurde das Format gelesen, aber der Modus nicht angenommen. Das
  Modul schlägt im Log selbst den nächsten Befehl vor: `echo ns cbc > starten`, also `aes_mode 1`, OP-TEEs eigene
  Softwareschlüssel-Konfiguration `0x100`. Das geht **im selben Stromzyklus** und kostet keinen weiteren.

→ **Plan 114 §7 Schritt 3, zweiter Spiegelstrich:** „Format oder Kanal falsch, gegen cstengers bekannte Signatur
abgleichen.“ Der Einbauort bleibt offen, Schritt 4 wird nicht entschieden.

#### 3. Bus-Abort oder Zeitüberschreitung

* **Bus-Abort** (synchroner externer Abort, Oops mit `SError`/`Synchronous External Abort` und der CE-Adresse in `FAR`):
  die Non-Secure-Welt darf diese Bank **nicht**. Bei einem `s`-Lauf ist das die Antwort auf S49s letzte offene Frage.
  Das Gerät ist danach in unbekanntem Zustand — neu starten.
* **Zeitüberschreitung** (`ERGEBNIS: Zeitueberschreitung, keine Fertigmeldung`): der Task wurde geladen, aber nie fertig.
  Die Diagnosezeile nennt ISR, ESR roh, TSR, das zurückgelesene TDA und beide Interruptzähler. Lesen sich dabei **alle
  Register leer und hat TDA den Wert nicht behalten** (und hatte der NS-Lauf ihn behalten), sagt das Modul es dazu: die
  Bank verwirft Schreibzugriffe, ist also aus der Non-Secure-Welt unsichtbar, ohne einen Abort auszulösen.
* Zwischenfall **TLR bleibt belegt** (`-EBUSY`): der Task wurde nie geladen — Takt, Reset oder falsche Bank; lauter
  Einsen heißt, die Bank antwortet gar nicht.

→ **Plan 114 §7 Schritt 3, dritter Spiegelstrich:** „Bus-Abort → NS darf nicht, weiter mit 4b“, also der
**TF-A-Weg**: ein SiP-SMC „HDCP14-Load(phys, len)“, der CE_S aus EL3 programmiert — die Stock-Architektur ohne OP-TEE.

---

## Was dieser Test **nicht** beantwortet

* **Ob NS den Key-Select 3 (RSSK) benutzen darf.** Der Test benutzt ausschließlich Key-Select 0 mit einem Schlüssel aus
  dem Arbeitsspeicher. Dass die Maschine einen Softwareschlüssel annimmt, sagt nichts darüber, ob sie aus der
  Non-Secure-Welt auch den Efuse-Schlüssel herausrückt. Das ist der **zweite Teil** von Plan 114 §7 Schritt 3 und
  braucht einen eigenen Lauf (Key-Select 3, Ziel weiterhin **DRAM**).
* **Was `0x03041400` ist.** Die Schlüsselsenke wird nirgends angefasst. S49 führt sie als Analogieschluss
  („mittel“ statt „hoch“): belegt ist nur, dass sie physisches DMA-Ziel außerhalb DRAM mit Sonderbehandlung im
  Code ist. Ob dahinter der Schlüsselspeicher des HDMI-RX-HDCP-Blocks hängt, klärt erst ein Transfer plus ein Blick
  auf `0x06840093` Bit 0 — das ist Plan 112, nicht dies hier.
* **Ob die RSSK auf diesem Gerät überhaupt gebrannt ist** (SID `0x03006240` Bit 17). Nur am Gerät lesbar, hier nicht
  angefasst.
* **Ob die TVTOP-/HDMI-RX-Domäne beim Transfer an sein muss.** Der Test schreibt nach DRAM; die Frage stellt sich erst
  bei der Senke.
* **Wer `0x06840093` Bit 0 setzt** und ob HDCP 1.4 danach wirklich funktioniert. Das ist die Abnahme von Plan 112.
* **Welche Interruptleitung zu welcher Bank gehört.** Das Modul *zählt* beide mit — das ist Rohmaterial für die Antwort,
  aber der Behandler fasst absichtlich kein CE-Register an, also lässt sich aus einem Lauf nur ablesen, *welche* feuert,
  nicht *warum*.
* **Ob `sun8i-ce` mit einem angepassten Deskriptorpfad die CE fahren könnte.** Interessiert uns nicht: Plan 114 Frage A
  ist geschlossen, die CE bringt gegenüber den ARMv8-Krypto-Erweiterungen der A53 keinen Gewinn. Es geht allein um den
  einen Schlüssel, den Software nicht hat.

---

## Dateien daneben

* `bauprotokoll.txt` — zwei Durchgänge. §1–7 der Erstbau, §8–14 die Prüfung und der Neubau, mit der vollständigen Liste
  der Korrekturen (§9) und dem Feld-für-Feld-Abgleich gegen die S49-Tabelle (§11).
* `agenten/crypto-ce/wegwerfbaum` — Kopie von `mainline/build/linux-6.18.38-61d37af9…`, in der gebaut wurde. Wegwerfbar.
* `agenten/crypto-ce/deskriptorpruefung.c` — prüft Feldlage **und** erzeugten Bytestrom gegen S49, außerhalb des Kernels.
* `agenten/crypto-ce/dtsprobe/beispiel.dts` — das `examples`-Stück der Bindung in einem Testgerüst, mit `dtc` übersetzt.
