# 145 - HDCP 1.4: die ganze Kette von U-Boot bis Userspace, und wie wir sie nachbauen

> **Überholt.** Der aktuelle Stand der HDCP-Kette steht in [`docs/subsystems/hdcp.md`](../docs/subsystems/hdcp.md), die Durchführung in `doku/148`. Dieser Eintrag bleibt unverändert stehen, weil er der Beleg dafür ist, wann was gemessen wurde — nicht, weil seine Schlussfolgerungen noch gelten.

> **Redigiert (05.10.2026).** Aus diesem Dokument sind die Kennungen und Adressen entfernt, mit denen man das **Trusted OS des Herstellers** direkt anspricht — SMC-Kennungen, Funktionsadressen und die Lage des Hardwareschlüssels im eFuse. Die Befunde bleiben: *dass* der HDCP-1.4-Satz chipgebundenes Chiffrat ist, dass nur die Crypto Engine den Hardwareschlüssel sieht und dass sie ihn nicht nach lesbarem Speicher schreibt. Das erklärt unseren eigenen Weg; der Rest war ein Rezept für fremde Geräte und gehört nicht veröffentlicht.

Stand 04.10.2026 23:xx. Zweck: den Lademechanismus so verstaendlich machen, dass wir ihn in
unserem Port nachbauen koennen. Belege: umbau/work/FB-HDCP14h/REPORT.txt (Messungen am
Geraet), FB-HDCP14e/sink-test/REPORT.txt (die Vorgeschichte), FB-HDCP14g/REPORT.txt
(Agenten-Machbarkeitsstudie). Korrigiert doku/143 Abschnitt 11-13 und doku/144.

## 0. Worum es geht, und was wir NICHT tun

Das Geraet ist eine HDMI-**Senke**. Unter der Original-Firmware authentifiziert sein Eingang
HDCP 1.4 in drei Sekunden; unter unserem Port antwortet er einer Quelle nicht, und damit ist
der Eingang fuer geschuetzte Quellen unbrauchbar. Ziel ist, die vom Hersteller vorgesehene
Funktion des eigenen Eingangs wiederherzustellen - also die Lizenz, die mit dem Geraet
gekauft wurde, weiter nutzbar zu machen.

Rechtsgrundlage: Eigentum § 903 BGB; Anpassung und Fehlerbeseitigung RL 2009/24/EG Art. 5
Abs. 1 (§ 69d Abs. 1 UrhG); Untersuchen und Testen Art. 5 Abs. 3 (§ 69d Abs. 3 UrhG);
Dekompilierung zur Interoperabilitaet Art. 6 (§ 69e UrhG, Erwaegungsgrund 15) - rechtmaessiger
Besitzer, Information anderweitig nicht zugaenglich, nur die noetigen Teile, Ergebnis dient
der Interoperabilitaet des eigenen Ports mit der eigenen Hardware. Right to Repair
RL (EU) 2024/1799 als Zielrichtung. Rechtsmittel bei Beanstandung: § 69g Abs. 2 UrhG macht
entgegenstehende Vertragsklauseln unwirksam; dazu negative Feststellungsklage (§ 256 ZPO).

Was ausdruecklich nicht stattfindet: **kein** Umgehen von HDCP - das Gegenteil ist das Ziel,
der eigene Empfaenger soll die Authentifizierung BESTEHEN, damit eine Quelle ihm geschuetzte
Inhalte ueberhaupt schickt. Kein geschuetzter Inhalt wird entschluesselt oder mitgeschnitten.
Und: **wir haben das Schluesselmaterial nicht gesucht und nicht angefasst.** Dass es teils
unsicher daliegt (Abschnitt 4), ist uns bei der Suche nach dem *Ablauf* aufgefallen. Die
Dateien /vendor/etc/firmware/hdcp_1.bin und hdcp_v22.bin wurden nicht gelesen und nicht
kopiert - nur ihre Groesse per `ls`. Das ist der beste Beleg dafuer, dass es uns um den
Mechanismus geht und nicht um die Daten.

## 1. Die Kette unter der Original-Firmware, in Reihenfolge

### 1.1 Bootloader (einmal pro Boot, still)
`boot0` laedt aus dem Boot-Paket die Eintraege `u-boot`, `monitor` (BL31), `scp` und `optee`
(BL32) und springt in BL31. BL31 meldet "secure os exist", startet OP-TEE in AArch32 S-EL1,
OP-TEE meldet sich mit "OP-TEE version: a8294843 ... arm" zurueck, dann geht es nach U-Boot
(AArch32, spsr 0x1d3).

Stocks U-Boot laeuft dann ueber `keybox_list` aus seiner Env:
`widevine,ec_key,ec_cert1..3,rsa_key,rsa_cert1..3,hdcpkey`. Fuer jeden Namen liest es das
Item aus dem Secure Storage (Fehler drucken auf Level 0 - im Bootlog sichtbar fuer widevine
und ec_key, NICHT fuer hdcpkey). Fuer den Namen exakt `hdcpkey` ruft es danach
`push_hdcp_key()` (0x4a007724), und das macht zwei SMCs an OP-TEE. Reihenfolge und
Zeitpunkt sind wichtig: das passiert bei ca. [02.17], und `display_bin` wird erst bei
[02.9-03.1] kopiert - der Schluessel liegt also in der Senke, BEVOR die Display-Firmware
startet. (Marco hatte das so erinnert; es stimmt.)

### 1.2 Die SMC-Schnittstelle
`0xb2000xxx` ist OP-TEEs Standard-ABI (Owner 0x32 = Trusted OS). Belegt:
- `0xb2000001` = GET_OS_REVISION. Stocks U-Boot fragt damit die Version (0x4a027588) und
  addiert bei major>3 bzw. major==3 && minor>=5 ein `0x200` auf seine Funktionsnummern
  (0x4a0275c8, selbst nachgerechnet). Dieses OP-TEE meldet 3.7, also +0x200.
- `<SMC des Hersteller-TEE, nicht abgedruckt>` = die Hersteller-Ops, Unter-Op in x1. Aus OP-TEEs eigenem Dispatcher:
    op 1  Item in die Keybox legen
    op 2  Adresse des Shared Memory zurueckgeben
    op 5  `sunxi_load_hdcp_key`: keybox_get("hdcpkey"), dann Crypto Engine mit
          key-select 3 (dem eFuse-Schluessel RSSK) nach 0x03041400, der Key-Senke
          des Empfaengers. Laenge in x3, Stock uebergibt 0x120 = 288.
    op 7  PKF-Weg: Schluessel als 16 Byte aus dem SID-Schatten, normales AES, kein Key-Bus.
          Stocks U-Boot ruft ihn NIE (nur 0, 2, 5).
    op 10 eFuse-BRENNPFAD, irreversibel. **Nie aufrufen.**
- `<SMC des Hersteller-TEE, nicht abgedruckt>` = Shared Memory einrichten, erwartet einen Device Tree. Aufrufstelle im
  Stock-U-Boot 0x4a027afc: `smc(`<SMC des Hersteller-TEE, nicht abgedruckt>`, a1=<Argument>, 0, a3=<Konstante>)` mit
  16-Byte-Ergebnispuffer. **Argumentbelegung noch offen** - das ist die letzte Luecke.

### 1.3 Userspace (Android)
Der **Graphics-Composer-HAL** (`vendor_a_hwcomposer.ares.so`) hat die Bereitstellung:
`sunxi::check_hdcp_key()`, `burn_hdcp_key()`, `do_burn_hdcp_key()`, dazu die 2.2-Zwillinge.
Er holt sich den tvserver per HIDL (`ITvServer::getService`), fragt den Empfaenger nach der
Summe seines Schluessels ("SubDeviceGetHdcpSum buffer = %s"), vergleicht, und brennt bei
Abweichung neu ("hdcp key check error,reburn it..." -> "burn done..."). Danach setzt er
`persist.sys.finish_burn_hdcpkey`, und init legt eine Markerdatei `hdcp_flag` auf oemfs
(mmcblk0p23) ab. Quelle sind die Dateien `/vendor/etc/firmware/hdcp_1.bin` (368 B) und
`hdcp_v22.bin` (960 B).

Die eigentliche Arbeit macht **`/vendor/lib/libsst.so`** (26892 B, ARM 32-Bit, sha256
601f5b43...; eigene Kopie in FB-HDCP14h/vendor-libs/). Seine API:
- Secure Storage: `sunxi_secure_storage_init/exit`, `sunxi_secure_object_read/write/erase/
  list`, `parse_secure_storage_info`, und `_sd_read_ioctl/_sd_write_ioctl/_nand_*_ioctl` -
  der Secure Storage ist also **gewoehnlicher Blockzugriff auf den eMMC**, kein TEE-Geheimnis.
- Krypto ueber die TEE Client API: `TEEC_InitializeContext/OpenSession/InvokeCommand/
  AllocateSharedMemory/...` (`pTeeContext`, `pTeeSession`, `pTeeMutex`).
- HDCP: `hdcp_process`, `hdcp_widevine_write/-read`, `hdcp_hash_read`, `keybox_hash_read`,
  `keybox_default_process`.
`hdcp_process` (0x5cb8, 296 B) disassembliert: `strlen(name)==7 && strcmp(name,"hdcpkey")==0`
-> 1.4-Zweig; `==10 && "hdcpkeyV22"` -> 2.2-Zweig; sonst -1. Im 1.4-Zweig wird ein
**320-Byte**-Puffer genullt, die Datei hineingeparst und dann (name, buf, .., 0x140) an den
TEE-Aufruf gegeben. Dieselben Parserfehler wie in OP-TEE: "hdcp_key_parse: hdcp magic is bad
/ crc is bad / file is bad, size: %d".

### 1.4 Die Groessen, die alles zusammenhalten
| Ort | Groesse | Bedeutung |
|---|---|---|
| `/vendor/etc/firmware/hdcp_1.bin` | 368 B | 48 Byte Kopf (Magic, CRC, Hash) + 320 Byte Nutzlast |
| `/vendor/etc/firmware/hdcp_v22.bin` | 960 B | 48 + 912 |
| Secure Storage `hdcpkey` | 320 B | die geraetegebundene Form (gemessen) |
| Secure Storage `hdcpkeyV22` | 912 B | dito |
| OP-TEE op 5 | 0x120 = 288 B | Chiffretext fuer die Engine; 320 = 288 + 32 Byte SHA-256 |
Der 48-Byte-Kopf ist genau das, was `hdcp_key_parse` auf Magic und CRC prueft.

### 1.5 Secure-Storage-Karte dieses Geraets (aus unserem U-Boot gelesen, LBA 0x3000, 1 MiB)
Slots a 4096 B, jedes Item zweimal (Original + Kopie), Magic 0x17253948 am Slotanfang:
Slot 2/3 `hdcpkey`, 4/5 `hdcpkeyV14_hash`, 6/7 `hdcpkeyV22`, 8/9 `hdcpkeyV22_hash`,
10/11 `wifiBleDatas`, 12/13 `snum`, 14/15 leer.

## 2. Warum zwei Kopien des Schluessels existieren

Die Datei ist die **generische Werkskopie** - auf jedem Geraet dieses Modells gleich, an
keinen Chip gebunden. Der Secure Storage haelt die **geraetegebundene** Form: OP-TEEs
`sunxi_deal_hdcp_key` nimmt die 320-Byte-Nutzlast, prueft Magic/CRC/SHA und verschluesselt
sie mit einem Schluessel, den nur dieser Chip hat (RSSK bzw. PKF aus den eFuses). Dieses
Chiffrat ist auf einem anderen Chip wertlos.
Die Datei bleibt liegen, weil (1) dasselbe Abbild auf viele Geraete geht und die Bindung erst
auf dem Geraet moeglich ist, (2) `check_hdcp_key()` damit selbst heilt, wenn der Secure
Storage beschaedigt wird, und (3) nach dem Brennen niemand aufraeumt - das Flag merkt sich
nur, DASS es passiert ist.

## 3. Was bei uns fehlt, und was schon geht

GELOEST (04.10., eine Zeile): unsere Kette kann das Hersteller-OP-TEE als BL32 fahren.
`opteed` nimmt die Ausfuehrungsart aus `args.arg0`, nicht aus dem SPSR; unsere Plattform
setzte sie nie, `OPTEE_AARCH64` ist 0, also wurde das 32-Bit-Image als AArch64 gestartet und
starb lautlos am ersten Befehl. Fix: `bl32_image_ep_info.args.arg0 = MODE_RW_32`, dazu
`BL32_BASE=0x48600000`, AArch32-SVC-spsr und ein `tee`-Image im FIT. Gemessen laeuft dann
SPL -> BL31 -> Hersteller-OP-TEE -> unser AArch64-U-Boot. (Ein 32-Bit-Secure-OS unter einem
AArch64-U-Boot ist kein Widerspruch: die Ausfuehrungsart gilt pro Exception-Level.)

GEMESSEN mit unserem neuen U-Boot-Kommando `h713_tee`:
- `op 2` -> `0xffff000c`: kein Shared Memory eingerichtet.
- `op 5` -> OP-TEE: `sunxi_aes_decrypt_with_hardware_rssk:614 loadhdcp key fail`, `0xffffffff`.
  Die Routine laeuft also an und scheitert am `keybox_get` - die Keybox ist leer.
- `op 1 <Record>` -> OP-TEE-Panic, Nullzeiger-Abort bei <Adresse im Hersteller-TEE> ("abort outside thread
  context"). Op 1 braucht das Shared Memory, das es noch nicht gibt.
AUSGESCHLOSSEN als Ursache fuer die frueher gemessene key-select-3-Verweigerung: eFuse-Lage,
SPC, Takte, Laufzeit-Software, das Ziel des Laufs (DRAM gegen Senke, beide ESR 0x11), und die
Bus-/Sicherheitskonfiguration (drei Varianten inklusive Stocks eigener, identischer Ausgang).

`<SMC des Hersteller-TEE, nicht abgedruckt>` IST AUFGELOEST (statisch, Stock-U-Boot 0x4a027ad4 und sein einziger Aufrufer
0x4a0023ec): `smc(`<SMC des Hersteller-TEE, nicht abgedruckt>`, a1=<Adresse>, a2=0, a3=<Groesse>)`, mit 16-Byte-Ergebnispuffer,
und nur wenn ein Secure OS vorhanden ist. Danach wird der Bereich 64-Byte-ausgerichtet und
geflusht. Es meldet OP-TEE also einen Shared-Memory-Bereich an. Damit ist die Reihenfolge
`<SMC des Hersteller-TEE, nicht abgedruckt>` (shm) -> `op 1` (keybox fuellen) -> `op 2` -> `op 5`, und als Nachweis eine
Quelle am Eingang, `xrandr --set "Content Protection" Desired`, Bksv ueber DDC (20 Einsen).

## 4. Nebenbefund zur Sicherheit, ungesucht

Das 1.4-Material liegt als Datei auf einer gewoehnlichen, nicht verschluesselten
Vendor-Partition jedes Geraets dieses Modells, und der Composer-HAL im Userspace kann es
jederzeit neu brennen. Die geraetegebundene Form im Secure Storage schuetzt nur gegen das
Kopieren auf einen anderen Chip, nicht gegen Zugriff auf diesem. Das ist die Konstruktion des
Herstellers; wir haben sie nicht veraendert und das Material nicht angefasst. Fuer unseren
Zweck hilft die Datei uebrigens NICHT: der Empfaenger bekommt den Schluessel nur ueber den
Hardwarepfad (op 5 entschluesselt die gebundene Form in die Senke), und die Bindung selbst
braucht wieder den eFuse-Schluessel.

## 5. Nachbauplan

1. `<SMC des Hersteller-TEE, nicht abgedruckt>` klaeren. Zwei Wege, beide ohne Geraeterisiko:
   (a) statisch in `libsst.so` - 26 KB, die TEE-Invoke-Kommando-IDs und die Parameterform
       stehen dort; dieselbe Information, in einem Zwanzigstel des Codes von OP-TEE;
   (b) statisch in Stocks U-Boot um 0x4a027afc, inklusive der Konstante in a3.
2. Die Folge in unserem U-Boot absetzen (`h713_tee` erweitern), vor dem MIPS-Release -
   dieselbe Stelle, an der Stock es tut (`h713_mips_release_reset()`).
3. Nachweis am Geraet mit Quelle.
4. Erst dann: den Warteschleifen-Patch auf `HdmiRx_HDCP14_LoadKey` entfernen (doku/112
   verlangt es) und die known-issues-Zeile umschreiben.
5. Danach die Frage der Portierbarkeit entscheiden: `libsst.so` zeigt, dass der Client klein
   ist und die Arbeit im TEE steckt. Entweder wir fahren das Hersteller-OP-TEE dauerhaft als
   BL32 mit (dann darf es NICHT ausgeliefert werden, sondern muss bei der Installation aus dem
   Boot-Paket des jeweiligen Geraets gezogen werden, wie die 44 vorhandenen Vendor-Dateien),
   oder wir finden heraus, was OP-TEE an der Engine anders macht als unser EL3, und bauen es
   selbst. Der BL32-Weg ist der schnelle, der zweite der saubere.
