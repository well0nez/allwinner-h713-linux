# HDCP 1.4 im Stock-System: Wie der Schlüssel in die HDMI-RX-Hardware kommt

Statische Analyse (11.09.2026) von Stock-U-Boot, OP-TEE, BL31, Vendor-Kernel und
MIPS-Firmware des HY310 (Allwinner H713 / sun50iw12p1). Kein Gerätezugriff, kein
Schlüsselmaterial geöffnet. Alle Disassemblate liegen unter `dis/`, die
untersuchten Binaries unter `bin/` (Kopien aus `update.img` bzw. `boot_package.fex`).

## Die Antworten

**1. Welche HDMI-RX-Register bekommen den Schlüssel?** Keine — von keiner CPU.
Weder U-Boot noch OP-TEE noch der MIPS schreiben Schlüsselbytes in den Bereich
`0x0684xxxx`. Der Schlüssel wird von der **Crypto Engine (CE) per DMA** in eine
Hardware-Senke an der physischen Adresse **`0x03041400`** geschrieben (CE-/Key-
Ladder-Adressraum, nicht DRAM). Das löst U-Boot per SMC aus, ausgeführt wird es in
**OP-TEE** (`sunxi_load_hdcp_key`), das die CE im sicheren Kanal (`0x03040800`)
programmiert: AES-128-ECB-**Entschlüsselung** mit dem Hardware-Schlüssel **RSSK**
(Key-Select 3), Quelle = 288 Byte Chiffrat aus dem Keybox-Eintrag `hdcpkey`, Ziel =
`0x03041400`. Danach steht `0x06840093` Bit 0 auf 1, **bevor** der MIPS startet —
die MIPS-Firmware nimmt bei Stock den Zweig „HDCP1.4 key has been loaded!" und
kommt gar nicht in die Warteschleife. Der ARISC ist nicht beteiligt.
*Sicherheit: hoch für U-Boot→SMC→OP-TEE→CE→`0x03041400` (Code gelesen); mittel
für „`0x03041400` ist die Schlüsselsenke des HDMI-RX-HDCP-Blocks" (Analogieschluss,
kein Datenblatt).*

**2. Klartext oder Chiffrat?** Der Inhalt des Secure-Storage-Items `hdcpkey` (320
Byte Nutzdaten) ist **Chiffrat, gebunden an den Chip**: AES-128-ECB unter der RSSK
(128-Bit-Efuse-Schlüssel bei SID-Offset `0xb0`, nur der CE zugänglich). Es wird
**nicht** per SMC in Software entschlüsselt: OP-TEE kopiert das Item beim
`keybox_store` für den Namen `hdcpkey` **unverändert** in seine Keybox (die
Meldung „Do secure storage decrypted !!" gilt nur für die *anderen* Keybox-Namen),
und die einzige „Entschlüsselung" ist die CE-Operation mit Ziel `0x03041400` — der
Klartext taucht in keinem CPU-adressierbaren Speicher auf. Die 320 Byte sind 288
Byte Nutzlast, beim Einbrennen auf 64 Byte aufgerundet; geladen werden nur die
ersten 288 (`0x120`). Das 2.2-Item `hdcpkeyV22` steht **nicht** in der Stock-
`keybox_list`, geht also nie durch diesen Pfad; es wird von Android/MIPS
behandelt, und da die PKF-Efuse auf diesem Gerät leer ist (MIPS-Log „read pkf: 0x0"),
liegen die 912 Byte unverschlüsselt vor — konsistent mit der Messung in doku/68.
*Sicherheit: hoch (drei unabhängige Code-Stellen: OP-TEE keybox_store, OP-TEE
load, OP-TEE Provisionierung; dazu die Efuse-Tabelle im BL31).*

**3. SMC-Schnittstelle.** Function-ID **`0xb2000210`** (OP-TEE-Fast-Call; das
`0x200` kommt aus der Versionsprüfung „OP-TEE ≥ 3.5", hier 3.7 — ältere Builds
hätten `0xb2000010`). `a1` = Operationsnummer, `a2`/`a3`… = Argumente. Für HDCP 1.4:
`a1 = 5`, `a3 = 0x120` (U-Boot) bzw. `a3 = 0` → Default `0x120` (Vendor-Kernel
`sunxi_smc_refresh_hdcp`, aufgerufen in `sunxi_tvtop_complete` nach jedem Resume).
OP-TEE: `sunxi_load_hdcp_key(len)` → Keybox-Eintrag `hdcpkey` (max. `len` Byte)
→ `sunxi_aes_with_hardware(dst=0x03041400, src, len, key=NULL, 0, mode=0x300000,
decrypt=1)`. Vorher: `a1 = 1` (`keybox_store`) mit dem 4-KiB-Secure-Object im
Shared-Memory, dessen Basis `a1 = 2` liefert.
*Sicherheit: hoch.*

## Der Stock-Ablauf im Ganzen

```
U-Boot init_sequence_r (0x4a080de0 → 0x4a0029d8 → 0x4a005220 "sunxi_keybox_init")
  für jeden Namen in env keybox_list = widevine,…,rsa_cert3,hdcpkey:
    0x4a005070: sunxi_secure_object_read(name, buf 4 KiB)          <- eMMC 0x600000ff.
               smc_tee_keybox_store(name, buf)  = SMC 0xb2000210 op 1  (Item inkl. Kopf name/len/encrypt/wp)
    nur für "hdcpkey":  0x4a007724 → 0x4a0276f0 = SMC 0xb2000210 op 5, a3 = 0x120
                                                    ("push hdcp key failed" bei Fehler)
OP-TEE (optee 3.7, Basis 0x48600000)
  tee_entry_fast 0x48609434: 0xb2000210 → 0x4860b874 (Plattform-Ops, tbb auf a1)
    op 1 → 0x4860beb8 sunxi_keybox_store: "hdcpkey" → memcpy roh, KEINE Entschlüsselung
    op 5 → 0x4860caf0 sunxi_load_hdcp_key(0x120):
             0x4860c1a4 keybox_get("hdcpkey", buf, 0x120)   -> 288 Byte Chiffrat
             0x4860c578 sunxi_aes_with_hardware(0x03041400, buf, 0x120, NULL, 0, 0x300000, 1)
               = CE-Task: AES-128, ECB, Key-Select 3 (RSSK), decrypt, DMA-Ziel 0x03041400
danach: U-Boot main_loop → Befehl sunxi_mips → MIPS startet
  MIPS HdmiRx_HDCP14_LoadKey (0x8b13d044): liest 0x06840093, Bit 0 = 1 → "HDCP1.4 key has been loaded!"
Linux (Vendor): sunxi_tvtop_complete() → sunxi_smc_refresh_hdcp() = SMC 0xb2000210 op 5, a3 = 0
```

## Registersequenz für HDCP 1.4

Es gibt keine HDMI-RX-Registersequenz mit Schlüsselbytes. Die reale Sequenz ist die
CE-Programmierung in OP-TEE (`sunxi_aes_with_hardware`, `0x4860c578`, Task-Deskriptor
0x100 Byte, 64-Byte-aligned, genullt; Adressfelder sind 5 Byte breit / 40 Bit):

| Adresse / Feld | Breite | Wert / Quelle | Zweck | Fundstelle |
|---|---|---|---|---|
| desc+0x00 `chan_id` | u32 | 0 | CE-Kanal 0 | 0x4860c578 (memset) |
| desc+0x04 `comm_ctl` | u32 | `0x80000100` = INT(31) \| decrypt(8) \| ALG_AES(0) | Richtung/Algorithmus | 0x4860c5e6–0x4860c5ec |
| desc+0x08 `sym_ctl` | u32 | `0x00300000` = Key-Select 3 (RSSK), AES-128, ECB | Hardware-Schlüssel | 0x4860c5ee–0x4860c5f2; Aufrufer 0x4860cb34–0x4860cb40 |
| desc+0x10 `key_addr` | 5 B | phys(64 Byte Nullen) | unbenutzt bei HW-Key | 0x4860c5f4–0x4860c5f8 |
| desc+0x15 `iv_addr` | 5 B | phys(16 Byte Nullen) | IV (ECB: irrelevant) | 0x4860c5fa–0x4860c60e |
| desc+0x20 `data_len` | u32 | `0x120` | 288 Byte = 18 AES-Blöcke | 0x4860c616 |
| desc+0x24 `src_addr` | 5 B | phys(Chiffrat aus Keybox) | Quelle | 0x4860c618 |
| desc+0x29 `dst_addr` | 5 B | **`0x03041400`** (kein DRAM; phys_to_virt und Cache-Ops werden dafür übersprungen) | Schlüsselsenke | 0x4860c61c–0x4860c622, Sonderfall 0x4860c642/0x4860c690/0x4860c700 |
| desc+0x30 / +0x34 | u32 | `0x120` / `0x120` | src_len / dst_len | 0x4860c620, 0x4860c626 |
| `0x03040800` CE_S TDA | u32 | phys(desc) | Deskriptor laden | 0x4860c334 |
| `0x03040808` CE_S ICR | u32 | \|= 1<<0 | IRQ-Enable Kanal 0 | 0x4860c2ac |
| `0x03040810` CE_S TLR | u32 | warten bis Bit 0 = 0, dann \|= 1 | Task starten | 0x4860c2d0 |
| `0x0304080c` CE_S ISR | u32 | pollen Bits[1:0], danach quittieren | Fertig/Fehler | 0x4860c3a8, 0x4860c360 |
| `0x03040818` CE_S ESR | u32 | & 0xff → „SS %s fail 0x%x" | Fehlerstatus | 0x4860c348 |
| `0x06840093` (HDMI-RX) | u8 | **gelesen** vom MIPS; Bit 0 = 1 „key loaded" | Statusbit, das Stock bereits gesetzt vorfindet | display.bin.bak 0x8b13d044–0x8b13d064 |
| `0x06840093` | u8 | `0xc0` **nur** wenn Bit 0 = 0 (Nachlade-Anstoß) | MIPS-Fallback / `ReloadKey` | 0x8b13d068–0x8b13d070, 0x8b13d19c |
| `0x06840002` | u8 | Bit 4 pulsen (1, dann 0) vor `0xc0` | HDCP-Reset im Reload-Pfad | 0x8b13d168–0x8b13d18c |

**Format des Klartexts, den die CE in die Senke schreibt** (aus dem Einbrennpfad
`sunxi_deal_hdcp_key`, Typ 0, 0x4860d88a–0x4860d8ac): Byte 0…279 = die 40
Gerätekeys à 7 Byte in Dateireihenfolge, Byte 280…284 = **KSV (5 Byte, am Ende, nicht
zuerst)**, Byte 285…287 = 3 Füllbytes. Byte-Strom per DMA, keine Wortsemantik
erkennbar; die Bitreihenfolge innerhalb der 7-Byte-Keys ist die der Tool-Datei
(nicht bestimmbar). Das Chiffrat im Secure Storage ist genau dieser 288-Byte-Block
(plus 32 Byte Aufrundung), AES-128-ECB unter RSSK.

## Klartext / Chiffrat — der Code-Beleg

**Wo gelesen wird.** U-Boot `0x4a005070` (Default-Ladecallback der Keybox):
```
4a00508e  bl 0x4a056fbc      ; sunxi_secure_object_read(name, buf, 0x1000)  -> "secure storage read %s fail with:%d"
4a0050b6  bl 0x4a0278b4      ; smc_tee_keybox_store(name, buf, 0x1000)     -> "key install %s fail with:%d"
```
`0x4a0278b4` druckt `len=[buf+0x40]`, `encrypt=[buf+0x44]`, `write_protect=[buf+0x48]`
— das ist exakt der innere Kopf aus doku/68 (`name[64] + len + 0x10000001 + 1`) —,
prüft `strcmp(name, buf)`, kopiert 4 KiB ins TEE-Shared-Memory (Basis via op 2) und ruft
op 1 (`0x4a027992`).

**Wo NICHT entschlüsselt wird (OP-TEE `sunxi_keybox_store`, 0x4860beb8).** Für die
Namen `widevine, ec_key, rsa_key, ec_cert1-3, rsa_cert1-3` läuft der SSK-Pfad mit
„Do secure storage decrypted !!" (0x4860c024). Für alle anderen Namen:
```
4860c0bc  ldr r1, ="hdcpkey"
4860c0c0  bl  strcmp(lname, "hdcpkey")
4860c0c4  cbz r0, 0x4860c0d0            ; gleich  -> roh kopieren
4860c0c6  ldr r1, ="verify-boot"
4860c0ca  bl  strcmp
4860c0ce  cbnz r0, 0x4860c10c           ; sonst   -> SSK-Entschluesselung ("Do secure storage decrypted !!")
4860c0d0  mov r2, sl                    ; obj->len
4860c0d2  add.w r1, r7, #0x4c           ; obj->data
4860c0d6  mov r0, sb                    ; entry->data (malloc(obj->len))
4860c0d8  bl  memcpy                    ; <- hdcpkey: Bytes 1:1 in die Keybox
```
Die Bytes des Items landen also unverändert in OP-TEEs Keybox (16 Einträge à 0x50 bei
`0x48643bbc`: name, valid+0x40, len+0x44, wp+0x48, data+0x4c).

**Wo „entschlüsselt" wird (OP-TEE `sunxi_load_hdcp_key`, 0x4860caf0).**
```
4860caf2  cmp r0,#0 ; it eq ; mov.w r5,#0x120     ; len==0 -> 0x120 (Kernel-Aufruf)
4860cb02  ldr r0, ="hdcpkey"
4860cb0e  bl  0x4860c1a4                          ; keybox_get(name, buf, len): min(entry->len, len) Bytes
4860cb16  ldr r3, ="loadhdcp key fail\n"           ; bei Fehler
4860cb34  ldr r0, =0x03041400                     ; dst
4860cb38  mov.w r2, #0x300000 ; str r2,[sp,#4]    ; mode: Key-Select 3
4860cb2e  movs r2,#1 ; str r2,[sp,#8]             ; decrypt
4860cb40  bl  0x4860c578                          ; sunxi_aes_with_hardware
```
Die Entschlüsselung geschieht in der CE mit einem Schlüssel, den die CPU nie sieht,
und das Ergebnis geht per DMA nach `0x03041400`, nicht in RAM. Es gibt keinen Pfad,
auf dem der Klartext an U-Boot, den Kernel oder den MIPS zurückfließt (U-Boot liest
nach op 5 nichts aus dem Shared-Memory; `0x4a0276f0` gibt nur `res.a0` zurück).

**Wo eingebrannt wird (Gegenrichtung, zwei Pfade):**
- OP-TEE op 0xa `sunxi_deal_hdcp_key` (0x4860d5f0, Typ 0): Tool-Datei prüfen (Magic
  `0x5aa5a55a`, crc32 über 0x16c Byte, AES mit Datei-Schlüssel bei +0xc über 0x140 Byte
  ab +0x1c), Hash prüfen, Umordnung ins HW-Format (0x4860d896–0x4860d8ac), dann
  `sunxi_deal_rssk_key("rssk", 0x11)` und **`sunxi_aes_encrypt_with_hardware_rssk(out, buf, 0x120)`**
  (0x4860d8e6–0x4860d8ee → 0x4862626c → `0x4860c578(..., mode 0x300000, encrypt)`).
  U-Boot-Seite: `0x4a0075c0` („down hdcp 1.4") schreibt das Ergebnis mit Länge `0x120`
  als `hdcpkey`; `0x4a056e74` kopiert hdcpkey/hdcpkeyV22 dabei **ohne** zusätzliche
  SSK-Verschlüsselung (0x4a056ebc–0x4a056f04), andere Namen bekommen SSK.
- OP-TEE PTA `sunxi_utils.ta` → `secure_object_down` (0x4860fc98): für den Namen
  `hdcpkey` (0x4860fcf6) wird die Länge auf 64 aufgerundet (0x4860fd24–0x4860fd26:
  `adds r4,#0x3f; bics r4,r4,#0x3f`) und **`sunxi_aes_encrypt_with_hardware_rssk`**
  aufgerufen (0x4860fd7c). 288 → **320 Byte** — genau die Länge des Items auf diesem
  Gerät. Dieses Gerät wurde also über den PTA-Pfad provisioniert (dazu passen
  `encrypt = 0x10000001`, `write_protect = 1` und die 6-stellige Hash-Datei; der
  U-Boot-Burn-Callback hätte 288 Byte, `encrypt = 1`, `wp = 0` und 12 Hex-Zeichen
  geschrieben).

**Der Schlüssel der Chiffre (RSSK).** BL31 (`monitor.bin`, Efuse-Namenstabelle bei
Datei-Offset 0x10000, Einträge à 0x40): `rssk` Offset `0xb0`, 128 Bit, Burned-Flag Bit 17;
`ssk` `0x90`/256 Bit/Bit 16; `hdcppkf` `0xe4`/128 Bit/Bit 21; `rotpk` `0x70`. OP-TEE
`sunxi_random_and_deal_key` (0x4860d4d4) liest das Flag-Wort `0x03006240`
(0x48626282), brennt bei Bedarf 16 Zufallsbytes (`sunxi_trng_gen`, `sunxi_efuse_write`),
meldet sonst „%s already burned". Der SSK-Pfad benutzt `sym_ctl = 0x00100002` (Key-Select 1,
AES-256), der RSSK-Pfad `0x00300000` (Key-Select 3, AES-128) — konsistent mit den
Efuse-Breiten 256/128 Bit. Die Zuordnung „Feld [23:20] = Key-Select, 1 = SSK, 3 = RSSK"
ist ein Analogieschluss aus Allwinners CE-Registerlayout plus der Funktionsnamen.

## Die SMC-Schnittstelle im Detail

Aufrufer U-Boot `0x4a019a9c` (ARM-Mode): `r0–r3 = a0–a3`, `[sp..sp+0xc] = a4–a7`,
`[sp+0x10]` = Zeiger auf `res[4]`. Function-ID = `0xb2000010 | flag`, `flag` aus
`0x4a0275b0` (OP-TEE-Version: major > 3 oder 3.≥5 → `0x200`), abgelegt in
`0x4a0814ec`. Vendor-Kernel identisch: `sunxi_smc_call_offset` (c0598f6c) → 0x200.

| a1 | OP-TEE-Handler | Bedeutung | Argumente |
|---|---|---|---|
| 0 | 0x4860c848 | AES-Encrypt mit SSK | a2 = shm (shm[0]=dst, shm[1]=src), a3 = len |
| 1 | 0x4860beb8 | `sunxi_keybox_store` | a2 = shm mit 4-KiB-Secure-Object |
| 2 | 0x4860b982 | Shared-Memory-Basis holen | → `res[1]` = phys. Basis |
| 3 | 0x4860c860 | AES-Decrypt mit SSK | wie 0 |
| 4, 6 | 0x4862626c/0x4862622c | Efuse-/RSSK-Hilfsoperationen | nicht verfolgt |
| **5** | **0x4860caf0** | **`sunxi_load_hdcp_key(a3)`** | a3 = Länge (0 → 0x120); a2 ignoriert |
| 7 | 0x4860cb5c | AES-Encrypt mit `hdcppkf` | shm[0], shm[1], a3 |
| 8, 9 | 0x4860c730 | generische AES-Tasks | Schlüsselstruktur im shm |
| 0xa | 0x4860d5f0 | `sunxi_deal_hdcp_key` (Einbrennen) | shm[1]=src, a3=inlen, shm[0]=dst, a4=outlen, a5=Typ (0 = 1.4, 1 = 2.2), shm[2]=Keyinfo |

U-Boot-Seite zu op 5 (`0x4a0276f0`, Datei-Offset `0x276f0` in `u-boot.fex`):
```
4a02771e  blx smc(fid, 2, 0,0,0,0,0,0, &res)      ; probe shm -> r5 = res[1]
4a027742  str r3,[r5,#4] / 4a027748 str r3,[r5]   ; shm[1]=shm+0x100, shm[0]=shm+0x1100 (ungenutztes Erbe)
4a02775a  movs r1,#5
4a027760  mov.w r3,#0x120                          ; a3 = 288
4a027768  mov r2,r4 (=0) ; a4..a7 = 0
4a02776e  blx smc                                  ; -> res[0] != 0: "smc tee decrypt with ssk failed with: %ld" (kopierter Fehlertext)
```
Vendor-Kernel `sunxi_smc_refresh_hdcp` (vmlinux.elf c05990f0): `arm_smccc_smc(0xb2000000 | (offset|0x10), 5, 0, 0, 0,0,0,0, &res)`; Rückgabe `res.a0`.
Aufrufer: `sunxi_tvtop_complete` (Modul sunxi_tvtop, bf014084) — also nach jedem
Resume des TV-Blocks wird die Senke neu befüllt.

## Gegenprobe MIPS

`HdmiRx_HDCP14_LoadKey` (display.bin.bak, 0x8b13d044, Datei-Offset 0x3d044):
```
0x8b13d04c  addiu s0,a0,0x93        ; base 0x06840000 + 0x93
0x8b13d058  jal read8 ; andi v0,v0,1
0x8b13d064  bne v0,zero,0x8b13d100  ; Bit 0 gesetzt -> Zeile 347 "HDCP1.4 key has been loaded!"
0x8b13d068  li a1,0xc0 ; jal write8 ; sonst: 0xc0 schreiben, dann Bit 0 pollen (0x33 Ticks) -> Zeile 358 "time out!"
```
Der Stock-elog (`re/captures/weltneuheit/stock-live-norm.txt`, 30 Treffer in den
Mitschnitten) zeigt **Zeile 347**, d. h. Bit 0 war beim Aufruf schon 1. Die
Firmware liest nach dem Laden nichts weiter als dieses Statusbit; sie kennt weder
Schlüsselbytes noch die Senke. Der Reload-Pfad (0x8b13d160, Ziel des RPC
`ReloadHdcp14Key`) pulst `0x06840002` Bit 4 und schreibt `0xc0` nach `0x06840093`
— ein Anstoß, die Senke erneut zu übernehmen, kein Schlüsseltransport.
Damit ist auch die offene Frage aus doku/40 beantwortet („Der Vendor-Bootloader hat
das Problem offenbar nicht"): bei Stock wird die Warteschleife nie betreten, weil
der Schlüssel vor dem MIPS-Start geladen ist; das Tick-Problem bleibt latent.

## Was dagegen spricht oder unklar bleibt

- **Semantik von `0x03041400`.** Belegt ist nur: physisches DMA-Ziel der CE, außerhalb
  DRAM, mit Sonderbehandlung im Code; benachbart liegt der Key-Ladder-Block
  (`0x03041000` Status, `0x03041030` „exported CW"). Dass dahinter der Schlüsselspeicher
  des HDMI-RX-HDCP-Blocks hängt, ist Analogieschluss (Vendor-DT: CE nur `0x03040000`/
  `0x03040800` je 0xa0; kein Datenblatt; MIPS-Whitelist erlaubt `0x03040000–0x03041FFF`,
  referenziert die Adresse aber nirgends).
- **Wer setzt `0x06840093` Bit 0 genau?** Entweder die DMA in die Senke selbst oder ein
  automatisches Übernehmen durch den HDCP-Block. Statisch nicht entscheidbar; beide
  Varianten sind mit dem Stock-Log verträglich.
- **Muss die HDMI-RX-/TVTOP-Domäne beim CE-Transfer an sein?** Der Vendor-Kernel lädt
  nach Resume nach, also geht der Inhalt mit der Domäne verloren; ob die Schreibung bei
  stromloser Domäne fehlschlägt, hängt oder still verpufft, ist offen. Ob der Stock-U-Boot
  die Domäne vor `init_sequence_r` einschaltet, habe ich nicht verfolgt.
- **Ist die RSSK auf diesem Gerät gebrannt?** Nicht belegt (Bit 17 in `0x03006240`,
  nur am Gerät lesbar). Der PTA-Pfad ruft `sunxi_deal_rssk_key` nicht vor dem
  Verschlüsseln auf. Wäre die Efuse leer, wäre das Item AES-128-ECB unter einem
  Nullschlüssel — offline prüfbar (KSV muss genau 20 gesetzte Bits haben), ich habe
  es nicht getan (Schlüsselmaterial nicht angefasst). Für die Hardware-Senke ändert
  das nichts: ein MMIO-Weg für Schlüsselbytes ist nirgends zu sehen.
- **Key-Select-Kodierung** (3 = RSSK, Bits 23:20) und **ECB** (Bits 11:8 = 0) sind aus
  Allwinners CE-Layout und den Funktionsnamen geschlossen, nicht aus einem Datenblatt.
- **Ob die Non-Secure-Welt** CE_S (`0x03040800`) oder Key-Select 3 benutzen darf
  (SPC-/TZPC-Konfiguration unter unserem mainline-TF-A), ist rein statisch nicht
  bestimmbar.

## Was ein Linux-Treiber (oder U-Boot/TF-A) tun müsste

Ohne Schlüsseldaten, als Schritte:

1. **Chiffrat bereitstellen.** Die ersten 288 Byte der Nutzdaten des Items `hdcpkey`
   (Item-Offset `0x4c`, das Projekt hat sie als 320-Byte-Datei) als privates
   Firmware-Blob, analog zu `hy310-hdcp22.bin`. Es ist chipgebundenes Chiffrat, keine
   Klartextkopie — trotzdem privat halten.
2. **Vorab-Test am Gerät (ein Stromzyklus):** aus Linux mit dem mainline `sun8i-ce`
   einen Task mit `sym_ctl` Key-Select 3 auf 16 Nullbytes nach DRAM absetzen, einmal
   über den NS-Kanal (`0x03040000`), einmal über CE_S (`0x03040800`). Ergebnis: ESR-Fehler
   oder Bus-Abort → NS darf nicht → Schritt 6b (TF-A). Läuft es, Schritt 6a.
3. **Voraussetzungen:** CE-Takte/Reset wie im `sun8i-ce`-Treiber; TVTOP-/HDMI-RX-
   Power-Domain und Takte an (Stock lädt nach Resume nach, also die Senke bei
   laufender Domäne beschreiben).
4. **Task-Deskriptor** wie in der Tabelle oben: `comm_ctl 0x80000100`, `sym_ctl
   0x00300000`, IV = 16 Nullbytes, `data_len = src_len = dst_len = 0x120`, `src` =
   phys(Chiffrat, cache-clean), **`dst = 0x03041400`**, keine Cache-Invalidierung des
   Ziels. Starten über TDA/ICR/TLR, ISR pollen, ESR prüfen.
5. **Verifikation:** Byte `0x06840093` lesen, Bit 0 erwartet 1. Bleibt es 0: `0x06840002`
   Bit 4 pulsen, `0xc0` nach `0x06840093`, Bit 0 pollen (der MIPS-Reload-Pfad).
6. **Einbauort:**
   a) Linux, wenn NS erlaubt ist: kleiner Treiber am `crypto@3040000`-Knoten oder als
   Teil von `h713-hdmirx` (Patch 0094): Laden vor dem ersten `SetSource`, Wiederholen in
   jedem Runtime-Resume der HDMI-RX-Domäne.
   b) Sonst TF-A: ein SiP-SMC „HDCP14-Load(phys, len)", der CE_S aus EL3 programmiert —
   das ist die Stock-Architektur ohne OP-TEE; aufgerufen aus U-Boot vor dem MIPS-Start
   und aus Linux nach Resume.
7. **U-Boot-Reihenfolge:** Erfolgt das Laden vor `sunxi_mips`/dem MIPS-Start, nimmt
   `HdmiRx_HDCP14_LoadKey` den Zweig „has been loaded", und der Patch
   „HDCP key-load wait defeated" (`h713_mips.c` um 3735) kann zurückgenommen werden.
8. **Nicht versuchen:** den Schlüssel in Software zu entschlüsseln (RSSK nur für die CE
   lesbar) oder Klartext in `0x0684xxxx` zu schreiben (kein solcher Registerpfad bekannt).

## Nebenbefunde

- `keybox_list` in der Stock-Umgebung (`env.fex`):
  `widevine,ec_key,ec_cert1,ec_cert2,ec_cert3,rsa_key,rsa_cert1,rsa_cert2,rsa_cert3,hdcpkey`.
  `hdcpkeyV22` fehlt → wird beim Booten nie an OP-TEE gegeben.
- HDCP 2.2 im Stock: der MIPS liest die PKF-Efuse selbst (`0x030062e4…f4`, Funktion
  0x8b13e074, „read efuse pkf U32: 0x0"), das Ladeprogramm `HdmiRx_HDCP22_LoadKey`
  (0x8b13d5e4) verlangt Länge `0x390` und zerlegt den Block feldweise (u. a. 5 Byte
  Receiver-ID bei +0x28, 0x180 Byte Signatur bei +0xb2, 0x140 Byte privater Schlüssel bei
  +0x232). Im OP-TEE-Einbrennpfad Typ 1 werden nur die ersten `0x140` Byte mit der PKF
  verschlüsselt — auf diesem Gerät entfällt das (PKF leer). Die Messung „912 Byte
  angenommen" aus doku/68 ist damit auch strukturell plausibel.
- Die Zeichenkette `smc_tee_hdcp_key_encrypt: failed` gehört zum Burn-Callback
  (`0x4a0075c0`), der eigentliche SMC-Wrapper (`0x4a027794`, op 0xa) meldet Fehler mit
  dem kopierten Text „smc tee decrypt with ssk failed". `Do secure storage decrypted !!`
  und `sunxi_keybox_store` stehen nicht im U-Boot, sondern im OP-TEE-Blob
  (update.img-Offset 1983954 = boot_package 0x111552).
- OP-TEE ist Version 3.7 (Header `optee.bin` +0x1c), 32-Bit, Ladeadresse `0x48600000`
  = Datei-Offset 0; Code ab +0x1000; BL31 ist AArch64 bei `0x48000000`.
- U-Boot-Einbrennpfad schreibt zusätzlich `hdcpkeyV14_hash` = 12 Hex-Zeichen aus den
  Bytes 26…31 der SHA-256 der Rohdaten (`0x4a007684`); das Gerät hat 6 Zeichen → auch
  das spricht für den PTA-/TEE-Provisionierungspfad (`sunxi_hash_install`).
- Der ARISC-Blob (`scp.bin`, entspiegelt) enthält nichts zu HDCP.
- Vendor-DT `ce@03040000`: zwei Registerfenster (`0x03040000`, `0x03040800`, je 0xa0) und
  zwei Interrupts (73, 74). Unser mainline-DT mappt `0x03040000` mit 0x1000.

## Dateien

- `bin/` — `u-boot.fex`, `boot_package.fex`, daraus `u-boot.bin`, `monitor.bin`,
  `scp.bin` (+ `scp-unswapped.bin`), `optee.bin`, `dtb.bin`.
- `dis/` — alle zitierten Disassemblate (U-Boot Thumb-2 Basis 0x4a000000, OP-TEE Thumb-2
  Basis 0x48600000, BL31 A64, Vendor-Kernel, MIPS).
- `d.py`, `xref.py`, `litref.py`, `movwscan.py` — Helfer (capstone).
- `imagewty-table.txt` — Dateitabelle des `update.img`.
