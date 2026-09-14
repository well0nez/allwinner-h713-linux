# Plan 112 — HDCP 1.4 über die Crypto Engine: Auftrag für einen späteren Agenten

**Status: ZURÜCKGESTELLT (Marco, 11.09.2026).** Nicht für Release v0.1. Wird angefasst, wenn das Release draußen ist.
**Dieser Auftrag ist so geschrieben, dass ein Agent ohne Gesprächsverlauf damit anfangen kann.** Der Beleg dahinter ist
[`nachtlog/S49-hdcp14-schluesselpfad.md`](nachtlog/S49-hdcp14-schluesselpfad.md) (rein statische RE, 326 Zeilen,
Disassemblate in `analyse/release/arbeit/r0-fel/s49-dis/`). Lies S49 ganz, bevor du eine Zeile Code schreibst.

## 0. Regeln, die über allem stehen

1. **Schlüsselmaterial wird nie gelesen, kopiert, zitiert oder ins Repo gelegt.** Die Dateien in `analyse/hdcp-keys/`
   und `re/device-dumps/` öffnest du nicht. Du brauchst sie nicht: das Chiffrat liest dein Code **auf dem Gerät** aus
   dem Secure Storage, genau wie [`h713-hdcp-key`](../rootfs/overlay/usr/local/sbin/h713-hdcp-key)
   es für HDCP 2.2 tut. Auch Logausgaben dürfen keine Schlüsselbytes enthalten, auch nicht „nur zum Debuggen".
2. **Der Secure Storage bei LBA 12288…14335 wird nie beschrieben.** Nur gelesen.
3. **Bauen nur im Container `h713-build`**, nie auf dem Host. Kernel-Patches gehören in `mainline/patches/kernel/series`,
   sonst wirken sie nicht am Gerät.
4. **Am Gerät nur mit Marcos Freigabe und in kleinen Schritten.** Jeder Schritt mit Rückweg. Ein Test in diesem Auftrag
   kostet einen Stromzyklus und kann den Bus aufhängen — vorher ansagen.
5. **Nichts von hier ist Wissen aus einem Datenblatt.** Alles ist aus Hersteller-Code rekonstruiert. Wo S49 „Analogie"
   oder „Vermutung" sagt, musst du messen, nicht glauben.

## 0a. Nachtrag 11.09. — gemessene Vorarbeit von cstenger

Bevor du S49 liest, nimm diese vier am Gerät gemessenen Tatsachen mit (Zweig `origin/wip/crypto-ce-tooling`,
Commit `bb44dc8`; Einordnung in [`114`](114-plan-crypto-engine.md)). Sie ersparen dir Stromzyklen:

1. **Die CE hat zwei Interrupts (SPI 73 + 74); mainline fordert nur den ersten an, und ohne den zweiten hängt die
   erste Operation.** Mit dem zweiten läuft sie durch. Unser mainline-DT mappt bisher nur `0x03040000` und den
   ersten Interrupt — dein Pfad muss beides mitbringen.
2. **Der Non-Secure-Kanal ist aus Linux erreichbar**: die CE nimmt NS-Registerschreibvorgänge an, arbeitet und gibt
   Status zurück — kein Bus-Abort. S49 Schritt 2 ist damit zur Hälfte beantwortet; offen bleibt nur noch, ob NS den
   **Key-Select 3 (RSSK)** benutzen darf und ob CE_S `0x03040800` aus NS sichtbar ist.
3. **Du hast ein Fehlerorakel.** Mit mainline-Deskriptoren meldet die CE `address invalid` (Chiffren) bzw.
   `algorithm not supported` (Hashes) — für Standard-AES/SHA. Das ist die bekannte Signatur des *falschen*
   Deskriptorformats und passt exakt zu den 5-Byte-Adressfeldern aus S49. Miss dagegen, statt nur „kein Fehler".
4. **Es gibt keine CE-TRNG.** `HW_RANDOM` bleibt aus, jage das nicht.

**Und die Reihenfolge:** mach den KAT aus [`114`](114-plan-crypto-engine.md) §7 Schritt 3 (Vendordeskriptor,
Key-Select **0**, Softwareschlüssel, Ziel **DRAM**, gegen OpenSSL) *bevor* du das erste Mal auf `0x03041400` zielst.
Ein falscher Deskriptor mit `dst = 0x03041400` schreibt per DMA in die Key-Ladder.

## 1. Was das Problem ist

Beim Start meldet die MIPS-Anzeigefirmware dreimal
`E/hdmi_driver (THDMIRx_TV303_Driver.cpp 358) HdmiRx_HDCP14_LoadKey(), time out!`.
Grund: die Firmware wartet in `Rx_HDCP14_LoadKey` darauf, dass HDMI-RX-Register `0x06840093` Bit 0 „Schlüssel geladen"
meldet. Bei Stock steht das Bit, bevor der MIPS startet. Bei uns nicht, weil niemand den Schlüssel lädt. Unser U-Boot
entschärft nur die Warteschleife (`arch/arm/mach-sunxi/h713_mips.c` um Zeile 3735, „HDCP key-load wait defeated"),
damit die Firmware nicht hängt. Folge: **HDCP-1.4-Quellen bekommen kein Bild** (unbestätigt, muss gemessen werden;
vgl. `60-offen` „HDCP-Status messen").

HDCP 2.2 ist davon **getrennt** und seit 11.09. gelöst: die 912 Byte gehen roh per RPC an den MIPS
(`h713-hdcp-key.service`). HDCP 1.4 geht einen anderen Weg, und der ist Hardware-Krypto.

## 2. Was bekannt ist (aus S49, belegt)

**Der Stock-Ablauf:**
1. U-Boot liest das Secure-Storage-Item `hdcpkey` (Block 2 bei LBA 12288, `store_object_t`, `actual_len` 396, davon
   Nutzdaten 320 Byte ab Item-Offset `0x4c`; Aufbau in `68` und im Kopf von `h713-hdcp-key`).
2. U-Boot legt es in OP-TEEs Keybox: **SMC `0xb2000210`, op 1**.
3. U-Boot ruft **op 5** (`a3 = 0x120`). OP-TEE (`sunxi_load_hdcp_key`, `0x4860caf0`) programmiert die **Crypto Engine
   über den sicheren Kanal CE_S (`0x03040800`)**: AES-128-ECB, **Key-Select 3 = RSSK** (128-Bit-Efuse-Schlüssel, nur der CE
   zugänglich), 288 Byte, **Ziel per DMA `0x03041400`** — eine Schlüsselsenke im CE-/Key-Ladder-Adressraum, kein DRAM.
4. Danach ist `0x06840093` Bit 0 = 1. Der MIPS nimmt in `Rx_HDCP14_LoadKey` den Zweig „schon geladen".
5. Der Vendor-Kernel wiederholt op 5 (`a3 = 0`) in `sunxi_tvtop_complete` nach jedem Resume: **die Senke ist flüchtig
   mit der TV-Domäne.**

**Der Task-Deskriptor**, den OP-TEE baut (0x100 Byte, 64-Byte-aligned, genullt, Adressfelder 5 Byte = 40 Bit):

| Feld | Wert |
|---|---|
| `chan_id` (+0x00) | 0 |
| `comm_ctl` (+0x04) | `0x80000100` = INT ∣ decrypt ∣ AES |
| `sym_ctl` (+0x08) | `0x00300000` = Key-Select 3, AES-128, ECB |
| `key_addr` (+0x10) | phys(64 Byte Nullen), bei HW-Key unbenutzt |
| `iv_addr` (+0x15) | phys(16 Byte Nullen), ECB: egal |
| `data_len` (+0x20) | `0x120` = 288 |
| `src_addr` (+0x24) | phys(Chiffrat), Cache vorher clean |
| `dst_addr` (+0x29) | **`0x03041400`**, keine Cache-Ops |
| `src_len`/`dst_len` (+0x30/+0x34) | `0x120` / `0x120` |

Start: TDA `0x03040800` := phys(desc); ICR `0x03040808` ∣= 1; TLR `0x03040810`: warten bis Bit 0 = 0, dann ∣= 1;
ISR `0x0304080c` Bits[1:0] pollen und quittieren; ESR `0x03040818` & 0xff ist der Fehlerstatus.

**Klartextformat in der Senke** (nur zur Einordnung, nie zu sehen): Byte 0…279 = 40 Gerätekeys à 7 Byte, Byte 280…284 =
KSV (am Ende), Byte 285…287 = Füllung. **Das Chiffrat im Secure Storage ist chipgebunden:** ohne die RSSK dieses Chips
ist es wertlos, und in Software ist es nicht entschlüsselbar.

**Der MIPS-Nachlade-Pfad** (falls Bit 0 nach dem Laden nicht steht): `0x06840002` Bit 4 pulsen (1, dann 0), dann
`0xc0` nach `0x06840093`, Bit 0 pollen (`display.bin` `0x8b13d168…0x8b13d19c`).

## 3. Was NICHT bekannt ist — das musst du messen

| Frage | Warum sie zählt | Wie messen |
|---|---|---|
| **Darf die Non-Secure-Welt CE_S (`0x03040800`) und Key-Select 3 benutzen?** | entscheidet Linux-Treiber gegen TF-A-SMC | §4 Schritt 2 |
| **Was ist `0x03041400` genau?** | belegt ist nur: DMA-Ziel außerhalb DRAM mit Sonderbehandlung; Nachbar `0x03041000` Key-Ladder-Status, `0x03041030` „exported CW" | nach erfolgreichem Transfer `0x06840093` lesen |
| **Wer setzt `0x06840093` Bit 0?** | DMA selbst oder HDCP-Block automatisch | Bit vor/nach dem Transfer lesen |
| **Muss die HDMI-RX-/TVTOP-Domäne beim Transfer an sein?** | Vendor lädt nach Resume nach; bei stromloser Domäne: Fehler, Hänger oder stilles Verpuffen? | erst mit laufender Domäne (Stock-Reihenfolge), dann ohne |
| **Ist die RSSK gebrannt?** | sonst Nullschlüssel; ändert am Weg nichts, aber an der Deutung | SID `0x03006240` Bit 17 lesen (nur am Gerät) |
| **Key-Select-Kodierung und ECB-Bits** | aus CE-Layout und Funktionsnamen geschlossen, kein Datenblatt | ESR nach dem Transfer |

## 4. Der Weg, in Schritten

1. **Lesen:** S49 ganz. Dann `mainline/patches/kernel/0094-media-sun50i-h713-hdmirx.patch` (die Init-Sequenz, Schritt 20
   `THal_Vp_SetHDCP22Key` als Vorbild für „ARM gibt dem MIPS etwas vor dem Start"), `h713-hdcp-key` (wie das Item vom
   Gerät gelesen wird), und den mainline-Treiber `drivers/crypto/allwinner/sun8i-ce/` (Deskriptorformat, Takte, Reset).
2. **Vorab-Test (ein Stromzyklus, Marcos Freigabe):** aus Linux mit dem `sun8i-ce`-Deskriptorformat einen Task mit
   `sym_ctl` Key-Select 3 auf 16 Nullbytes **nach DRAM** absetzen — einmal über den NS-Kanal `0x03040000`, einmal über
   CE_S `0x03040800`. Ergebnis ESR-Fehler oder Bus-Abort → NS darf nicht → Weg 6b. Läuft es durch → Weg 6a.
   **Vorher ansagen, dass der Bus hängen kann.** `0x05000000` niemals lesen (H616-UART, hängt den Bus).
3. **Voraussetzungen im Zielcode:** CE-Takte und Reset wie in `sun8i-ce`; TVTOP-/HDMI-RX-Domäne und Takte an.
4. **Der Transfer:** Deskriptor wie §2, `src` = phys(288 Byte Chiffrat aus dem Item, Cache clean), `dst = 0x03041400`.
   Starten, ISR pollen, ESR prüfen.
5. **Verifikation:** `0x06840093` Bit 0 muss 1 sein. Bleibt es 0: MIPS-Nachlade-Pfad aus §2 nachbilden.
6. **Einbauort:**
   - **a) Linux**, wenn NS darf: kleiner Treiber am `crypto@3040000`-Knoten oder Teil von `h713-hdmirx` (0094). Laden
     **vor dem ersten `SetSource`**, wiederholen in jedem Runtime-Resume der HDMI-RX-Domäne. Das Chiffrat kommt vom
     Gerät (Item `hdcpkey`), analog zu `h713-hdcp-key` — **nicht als Firmware-Datei ausliefern**.
   - **b) TF-A**, sonst: ein SiP-SMC „HDCP14-Load(phys, len)", der CE_S aus EL3 programmiert. Das ist die
     Stock-Architektur ohne OP-TEE. Aufruf aus U-Boot vor dem MIPS-Start und aus Linux nach Resume.
7. **U-Boot-Reihenfolge:** Wird vor dem MIPS-Start geladen, nimmt `HdmiRx_HDCP14_LoadKey` den Zweig „schon geladen",
   und der Warteschleifen-Patch in `h713_mips.c` kann zurückgenommen werden.
8. **Nicht versuchen:** den Schlüssel in Software zu entschlüsseln (RSSK nur für die CE lesbar) oder Klartext nach
   `0x0684xxxx` zu schreiben (kein solcher Registerpfad bekannt).

## 5. Abnahme

- Beim Start keine `HdmiRx_HDCP14_LoadKey(), time out!` mehr, ohne den Warteschleifen-Patch.
- Eine HDCP-1.4-pflichtige Quelle (alter Blu-ray-Player, Konsole mit 1.4) liefert Bild; eine HDCP-2.2-Quelle weiterhin.
- Nach Standby/Resume (Plan 103/104) bleibt es so.
- Kein Schlüsselbyte in dmesg, Journal, Debugfs oder Repo. `grep -rE "([0-9a-f]{2} ?){32,}"` über alle Berichte leer.
- Kaltstart-Serie 20/20 (`analyse/boot/kaltstart-serie.sh`) unverändert sauber.

## 6. Nebenbefunde aus S49, die du kennen solltest

- `hdcpkeyV22` steht **nicht** in der Stock-Keybox-Liste, geht nie durch den CE-Pfad — der MIPS liest die PKF-Efuse
  selbst (leer auf diesem Gerät). Das stützt, dass die 912 Byte für 2.2 Klartext sind.
- Die Zeichenkette „Do secure storage decrypted !!" gilt nur für die *anderen* Keybox-Namen; `hdcpkey` wird von
  `sunxi_keybox_store` (`0x4860c0bc…0x4860c0d8`) roh kopiert.
- Vendor-DT beschreibt die CE nur mit `0x03040000`/`0x03040800` je 0xa0; die MIPS-Whitelist erlaubt
  `0x03040000…0x03041FFF`, referenziert `0x03041400` aber nirgends.
- Die vier RTC-GP-Register (`0x07090100…`) haben mit HDCP nichts zu tun; nicht verwechseln mit dem FEL-Flag aus S48.
