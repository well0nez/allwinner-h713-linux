# Plan 114 - Crypto Engine (H713): Entscheidung, Befundabgleich mit cstenger, und der eine Grund sie anzufassen

**Stand 11.09.2026.** Auftrag von Marco: „den hy310 board mgr nehmen wir jetzt mit und die crypto engine auch …
cstenger hat irgendwas gemacht - guck mal ob der irgendwie probleme hatte die wir garnicht haben oder ob der was
besser hat". Dieser Plan beantwortet das und legt fest, was wir tun.

Belege: cstengers Zweig `origin/wip/crypto-ce-tooling` (Commits `bb44dc8`, `1c187ff`) und unser eigenes
[`nachtlog/S49-hdcp14-schluesselpfad.md`](nachtlog/S49-hdcp14-schluesselpfad.md) (rein statische RE aus OP-TEE).
Der Umsetzungsauftrag für HDCP 1.4 bleibt [`112`](112-plan-hdcp14-crypto-engine.md); dieser Plan ist die
Entscheidungsgrundlage darunter.

## 1. Die Kurzfassung

Es sind **zwei verschiedene Fragen**, die bisher unter einem Namen liefen:

| | Frage | Antwort |
|---|---|---|
| **A** | Soll die CE den Kernel-Krypto-Stack beschleunigen (AES/SHA/RNG über `sun8i-ce`)? | **Nein. Endgültig abgeschlossen.** cstengers Befund wird unverändert übernommen. |
| **B** | Brauchen wir die CE für den **RSSK** (HDCP-1.4-Schlüssel)? | **Ja, und es gibt keinen Ersatz.** Software-Krypto hilft hier prinzipiell nicht. |

cstenger hat A zu Ende untersucht und richtig entschieden. Sein Schlusssatz - „Reopening means descriptor-level RE
of the vendor `allwinner,sunxi-ce` driver (source unavailable) for zero gain" - trifft aber nur auf A zu, und **die
Klammer stimmt bei uns nicht mehr**: wir haben das Deskriptorformat, nur aus einer anderen Quelle als der, die er
gesucht hat.

## 2. Was cstenger gemacht hat (`bb44dc8`)

Er hat `CONFIG_CRYPTO_DEV_SUN8I_CE` eingeschaltet und am Gerät durchgemessen. Ergebnis, in seiner Reihenfolge:

1. **Kein Geschwindigkeitsgewinn.** Die vier A53 haben die ARMv8-Krypto-Erweiterungen (`aes pmull sha1 sha2`);
   Software-AES/SHA laufen im Kern bei ~2 GB/s, also 10-50× über dem, was eMMC und WLAN dieses Geräts je brauchen.
   Die CE zu betreiben wäre eine Vollständigkeitsfrage, keine Leistungsfrage.
2. **Mit echten Selbsttests (`CRYPTO_SELFTESTS=y`) fällt jeder Algorithmus durch.** Das frühere
   `/proc/crypto: selftest: passed` war ein Vorgabewert ohne Test, kein KAT.
3. **Die CE hat zwei Interrupts (SPI 73 + 74), mainline fordert nur den ersten an** → die erste Operation hing.
   **Den zweiten mitzuverdrahten behebt die Fertigmeldung** - Operationen liefern danach Status.
4. **Der Status ist dann vernichtend:** Chiffren melden `address invalid` samt aller Fehlerbits, Hashes melden
   `algorithm not supported` - für *Standard*-AES und *Standard*-SHA. Das passiert nur, wenn die Maschine eine
   unsinnige Algorithmus-ID und unsinnige Pufferadressen aus dem Deskriptor liest: **anderes Deskriptorformat**
   (der Vendor-Block mit zwei Registerbänken), nicht Interrupt, nicht Takt, nicht Byte-statt-Wort-Adressierung.
5. **Keine CE-TRNG.** Sie meldet `algorithm not supported`; mit `HW_RANDOM` pollt der hwrng-Kern sie nur sinnlos voll.

Fazit bei ihm: `# CONFIG_CRYPTO_DEV_SUN8I_CE is not set`, `HW_RANDOM` aus, CE-Knoten bleibt im DTS aber inert.

**Das ist sauber gearbeitet und wir übernehmen es.** Unser `hy200_qz713df_a1_defconfig` hat beide Schalter ohnehin
schon aus (`# CONFIG_HW_RANDOM is not set`, `# CONFIG_CRYPTO_DEV_SUN8I_CE is not set`) - wir
waren also zufällig schon am richtigen Punkt, jetzt wissen wir auch warum. **Frage A ist geschlossen.**

## 3. Was er nicht hatte - und wir haben

Sein Blocker ist wörtlich: *descriptor-level RE of the vendor `allwinner,sunxi-ce` driver (source unavailable)*.
Er hat die Quelle beim **Vendor-Kernel-Treiber** gesucht, und da gibt es sie tatsächlich nicht.

[`S49`](nachtlog/S49-hdcp14-schluesselpfad.md) hat sie an einer anderen Stelle gefunden: in **OP-TEE**
(`sunxi_load_hdcp_key`, `0x4860caf0`, disassembliert in `analyse/release/arbeit/r0-fel/s49-dis/`). Dort baut der
Hersteller denselben Deskriptor, nur für den sicheren Kanal. S49 §„Task-Deskriptor" hat ihn feldweise mit
Adressbelegen:

| Feld | Wert | Beleg |
|---|---|---|
| `chan_id` +0x00 | 0 | |
| `comm_ctl` +0x04 | `0x80000100` = INT(31) ∣ decrypt(8) ∣ ALG_AES(0) | 0x4860c5e6-ec |
| `sym_ctl` +0x08 | `0x00300000` = Key-Select 3 (RSSK), AES-128, ECB | 0x4860c5ee-f2 |
| `src`/`dst` | **5-Byte-Adressfelder (40 Bit)**, nicht 4 | 0x4860c61c-622 |
| CE_S `0x03040800` TDA/ICR/TLR/ISR/ESR | +0x00/+0x08/+0x10/+0x0c/+0x18 | 0x4860c334/2ac/2d0/3a8/348 |

Die **5-Byte-Adressfelder** und der **zwei-Bank-Aufbau** sind genau die Abweichung, die cstengers `address invalid`
erklärt: mainline schreibt 32-Bit-Adressen an Offsets, an denen die H713-CE 40-Bit-Felder erwartet, also liest sie
Müll. Sein Fehlerbild und unsere RE sagen **dasselbe**, von zwei Seiten. Das ist die stärkste Bestätigung, die S49
bisher hat - und sie kostet uns keinen Stromzyklus.

## 4. Was uns seine Messungen konkret sparen

Drei Dinge, die S49 §„Was ein Linux-Treiber tun müsste" noch als offen führt, sind durch ihn **belegt**:

- **Der zweite Interrupt ist real und nötig.** S49 hat SPI 73/74 nur aus dem Vendor-DT gelesen; er hat gemessen,
  dass ohne den zweiten die Operation hängt und mit ihm durchläuft. Unser mainline-DT mappt bisher nur
  `0x03040000` mit 0x1000 und den ersten Interrupt - das muss der RSSK-Pfad mitbringen.
- **Der Non-Secure-Kanal ist aus Linux erreichbar.** Unter unserem mainline-TF-A (ohne OP-TEE) hat die CE
  NS-Registerschreibvorgänge angenommen, gearbeitet und **Statusbits zurückgegeben** - kein Bus-Abort, kein Trap.
  S49 Schritt 2 wollte genau das herausfinden. Damit bleibt von der offenen Frage nur noch der schmalere Rest:
  **darf NS den Key-Select 3 (RSSK) benutzen, und ist CE_S `0x03040800` aus NS überhaupt sichtbar?**
- **Wir haben ein Fehlerorakel.** `address invalid` / `algorithm not supported` sind die bekannte Signatur des
  *falschen* Formats. Wenn unser Deskriptor im Vendorformat ein sauberes ESR liefert, ist das positiver Beleg für
  das Format - mit einer gemessenen Gegenprobe daneben, nicht nur „kein Fehler".

Und ein Negativbefund, der Arbeit spart: **keine TRNG** - `HW_RANDOM` bleibt aus, wir jagen das nicht.

## 5. Sein Werkzeug (`1c187ff`) - was davon brauchbar ist

`tools/crypto-rng-validate.sh` (174 Zeilen) prüft `/proc/crypto`, die debugfs-Zähler des Treibers und `/dev/hwrng`.
Er schreibt selbst in die Commit-Nachricht, dass es so **nicht taugt** („it must use a real known-answer test, not
the `/proc/crypto` selftest field"). Für uns kommt dazu: es setzt den gebundenen `sun8i-ce` voraus, den wir
bewusst nicht laden. **Direkt wiederverwendbar ist es nicht.**

Brauchbar sind zwei Nebensachen:
- die Rootfs-Zutaten aus `tools/rootfs/customize.sh` (`kcapi-tools` für AF_ALG-KATs, `openssl`) - falls wir je
  einen Software-gegen-Hardware-Vergleich brauchen;
- der Aufbau „binden → registrieren → KAT → hat die Hardware wirklich bedient" als Gliederung für unseren eigenen
  Test, der aber auf ESR und Zielregister schaut, nicht auf `/proc/crypto`.

## 6. Warum Frage B trotzdem offen ist - und nicht durch Software zu ersetzen

Der HDCP-1.4-Schlüssel liegt als **chipgebundenes Chiffrat** im Secure Storage (Item `hdcpkey`, 288 Byte
Nutzdaten). Entschlüsselt wird er mit dem **RSSK**, einem 128-Bit-Efuse-Schlüssel, den **ausschließlich die CE
lesen kann** (Key-Select 3). Es gibt keinen Registerpfad, der ihn in die CPU bringt, und das Ergebnis geht per DMA
direkt nach `0x03041400`, nie in DRAM (S49 §„Nicht versuchen").

Deshalb greift cstengers „zero gain" hier **nicht**: es geht nicht um 2 GB/s gegen 200 MB/s, sondern um einen
Schlüssel, den Software bei beliebiger Geschwindigkeit nicht hat. Die CE ist für genau diese eine Operation der
einzige Weg - und sie muss genau **einmal pro Einschalten und einmal pro Resume der TV-Domäne** laufen, nicht im
Datenpfad.

## 7. Was wir daraus machen

**Nicht** `sun8i-ce` wieder einschalten. Stattdessen ein enger, eigener Pfad für die eine Operation:

1. **`CONFIG_CRYPTO_DEV_SUN8I_CE` bleibt aus**, `HW_RANDOM` bleibt aus. In `doku/` und im defconfig-Kommentar
   festhalten **warum** (Verweis auf diesen Plan), damit es niemand aus Versehen „vervollständigt".
2. **DT:** der `crypto@3040000`-Knoten bekommt das **zweite Registerfenster** (`0x03040800`, 0xa0) und den
   **zweiten Interrupt** (SPI 74). Bindungsdokument dazu schreiben; der Knoten bleibt ohne Treiber inert, solange
   Schritt 4 nicht steht.
3. **Messschritt zuerst, ein Stromzyklus** (Marco vorher ansagen, S49 Schritt 2 in der verengten Fassung):
   ein Deskriptor im **Vendorformat**, AES-128-ECB, **Key-Select 0 mit bekanntem Softwareschlüssel**, Ziel **DRAM**,
   16 Byte. Gegen OpenSSL vergleichen. Das ist ein echter KAT und fasst **kein Schlüsselmaterial und keine
   Schlüsselsenke** an. Ergebnis:
   - läuft und stimmt → Format bestätigt, NS darf die CE, weiter mit 4a;
   - ESR-Fehler → Format oder Kanal falsch, gegen cstengers bekannte Signatur abgleichen;
   - Bus-Abort → NS darf nicht, weiter mit 4b.
   Danach dasselbe mit **Key-Select 3, Ziel DRAM** (S49 Schritt 2): liefert es 16 Byte irgendetwas, darf NS den
   RSSK; liefert es ESR-Fehler, muss der Pfad nach EL3.
4. **Einbauort** (erst nach 3 entscheiden, nicht vorher festlegen):
   a) **Linux**, wenn NS darf: kleiner Treiber am CE-Knoten oder Teil von `h713-hdmirx`, der den Task vor dem
      ersten `SetSource` und in jedem Resume der HDMI-RX-Domäne absetzt.
   b) **TF-A**, sonst: SiP-SMC „HDCP14-Load(phys, len)", der CE_S aus EL3 programmiert - das ist die
      Stock-Architektur ohne OP-TEE.
5. **Erst dann** Plan [`112`](112-plan-hdcp14-crypto-engine.md) abarbeiten (Chiffrat vom Gerät lesen wie
   `h713-hdcp-key` es für HDCP 2.2 tut, Ziel `0x03041400`, Verifikation über `0x06840093` Bit 0).

**Reihenfolge ist wichtig:** Schritt 3 ist ein KAT gegen DRAM mit Software-Schlüssel und damit gefahrlos und
aussagekräftig. Erst wenn der steht, wird überhaupt auf die Schlüsselsenke gezielt. Ein falscher Deskriptor mit
`dst = 0x03041400` schreibt per DMA in die Key-Ladder - das will man nicht blind probieren.

## 7a. ERGEBNIS des Messlaufs (11.09.2026, am Gerät)

**Schritt 3 ist bestanden.** Das Messmodul (`0148` - `0150`, Quelle und README in
[`patches/vorschlaege/crypto-ce/`](../mainline/patches/vorschlaege/crypto-ce/README.md)) hat am Gerät einen Task im
**Vendor-Deskriptorformat** abgesetzt: AES-128-ECB, Key-Select 0, Schlüssel aus dem Speicher, 16 Byte, Ziel DRAM,
Vergleich gegen den FIPS-197-Vektor. Kein Gerätschlüssel, keine Schlüsselsenke.

```
ERGEBNIS: bestanden. Vendor-Deskriptorformat auf NS-Kanal 0x03040000 bestaetigt
(aes_mode 0 (ECB, wie der RSSK-Pfad 0x300000)), ESR sauber, KAT stimmt (65 us).
IRQ 329: 1x, IRQ 330: 0x.
```

**Was damit belegt ist:**

1. **Die CE liest den Deskriptor genau so, wie [`S49`](nachtlog/S49-hdcp14-schluesselpfad.md) ihn aus OP-TEE
   rekonstruiert hat** - 0x100 Byte, 64-Byte-aligned, **5-Byte-Adressfelder**, `comm_ctl`/`sym_ctl` wie in der
   Tabelle. Die Rekonstruktion war rein statisch; jetzt ist sie am Silizium bestätigt.
2. **cstengers Sackgasse lag wirklich nur am Deskriptorformat**, nicht an der Hardware, nicht an Takten, nicht an
   Interrupts. Mit dem richtigen Format läuft derselbe Block in 65 µs sauber durch.
3. **Der NS-Kanal ist aus Linux nutzbar** - nicht nur erreichbar (das war cstengers Befund), sondern er führt einen
   vollständigen Task korrekt aus.
4. **Nur die erste Interruptleitung feuerte** (IRQ 329 einmal, IRQ 330 nie). Der zweite Interrupt gehört zur zweiten
   Bank; für den NS-Kanal wird er nicht gebraucht.
5. Nebenbefund aus dem Probe: **`RST_BUS_CE_SYS` war beim Laden schon aufgehoben** - unser Bootloader löst den
   zweiten Reset also bereits; `bus_ce_sys` lief.

**Was NICHT beantwortet ist** und bewusst nicht angefasst wurde: ob die Non-Secure-Welt **Key-Select 3 (RSSK)**
benutzen darf, ob **CE_S `0x03040800`** aus NS sichtbar ist, und was hinter `0x03041400` liegt. Der CE_S-Lauf
(`echo s > …/starten`) steht aus - er kann den Bus aufhängen und braucht einen angesagten Stromzyklus.

**Nächster Schritt** nach Plan §7: Key-Select 3 mit Ziel **DRAM** (nicht die Senke) über den NS-Kanal. Liefert er
16 Byte irgendetwas, darf NS den RSSK und der Einbauort ist 4a (Linux); gibt es einen ESR-Fehler, muss der Pfad
nach EL3 (4b, TF-A).

## 8. Aufwand und Einordnung

Schritt 1 ist Dokumentation. Schritt 2 ist eine DT-Zeile plus Bindung. Schritt 3 ist ein kleines Testmodul und
**ein** Stromzyklus. Schritt 4-5 ist der eigentliche Treiber und hängt am Ergebnis von 3.

**Nicht für v0.1.** Plan 112 ist von Marco am 11.09. zurückgestellt; dieser Plan ändert daran nichts, er macht nur
den Weg dahin belastbar. Was jetzt schon passiert: Schritt 1 (Festschreiben der Entscheidung) und Schritt 2 (DT),
beides ohne Geräterisiko.

## 9. Rückmeldung an cstenger

Gehört in das Paket R6 (PRs/Rückmeldungen). Inhalt: sein CE-Befund ist bestätigt und wir übernehmen die
Abschaltung; sein einziger Blocker - das fehlende Deskriptorformat - ist aus **OP-TEE** rekonstruiert, nicht aus
dem Vendor-Kerneltreiber, und sein `address invalid` passt exakt zu den 5-Byte-Adressfeldern. Für seinen Zweck
(generische Krypto) bleibt die Schlussfolgerung „kein Gewinn" richtig; interessant wird das Format nur für den
RSSK. Verweis auf S49 und diesen Plan.
