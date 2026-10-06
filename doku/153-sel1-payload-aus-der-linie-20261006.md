# 153 - Der S-EL1-Testpayload verlässt die TF-A-Linie (06.10.2026)

**Kurz:** Patch 7 des TF-A-Forks (`824eb0bd`, "our own secure payload at S-EL1 - kept as evidence, not
shipped") war nie Teil eines Artefakts und ist seit heute auch nicht mehr Teil der Linie. HDCP 1.4 läuft
unverändert über den EL3-Dienst (Patch 6, `4c1bd8c6`). Anlass: Marco, 06.10.: "EL1 ist nicht in Nutzung
und war nur ein Test - EL1 weg, Hauptsache HDCP funktioniert."

## 1 Was der Patch war

Vor dem EL3-Weg war der Plan, den HDCP-Schlüsseltransfer in einen eigenen Secure Payload bei S-EL1 zu
legen (TF-A-Testpayload mit unserem Code, über den TSP-Dispatcher). Das funktionierte, war aber unnötig,
weil BL31 den Transfer selbst machen kann; das ist seit dem 05.10. der ausgelieferte Weg (`doku/142`, HDCP-Paar). Der Patch blieb
im Fork wegen dreier Befunde (execute-never bei pauschaler RW-Abbildung, generischer Timer bei S-EL1
unbrauchbar, Rückgabekonvention `SMC_RET3` vs. `SMC_RET1`). Diese Befunde stehen weiter in
`referenz/irrwege.md` und in diesem Eintrag; der Code liegt lokal auf dem Fork-Branch `beleg/sel1-payload`.

## 2 Messung: das Artefakt kennt den Patch nicht

BL31 im Bau-Container zweimal gebaut, identischer Befehl wie `mainline/build/build.sh bl31`
(`PLAT=sun50i_h713 DEBUG=0 BL31_IN_DRAM=1`, LLVM), dazu `BUILD_STRING` und `BUILD_MESSAGE_TIMESTAMP`
festgesetzt, damit nur der Code zählt; `build/sun50i_h713` vor jedem Lauf gelöscht (Messregel: TF-A verfolgt
Flag-Änderungen nicht).

| Fork-Kopf | bl31.bin | sha256 (Anfang) |
|---|---|---|
| `824eb0bd` (mit Patch 7) | 49 276 B | `146777bca50500c1f…` |
| `4c1bd8c6` (ohne Patch 7) | 49 276 B | `146777bca50500c1f…` |

`cmp` ohne Abweichung: **bytegleich.** Erwartbar - die Quellen des Payloads werden nur mit `SPD=tspd`
übersetzt, und das setzt kein Bauweg - aber jetzt gemessen statt angenommen.

## 3 Was geändert wurde

- TF-A-Fork: `sun50i-h713` steht auf `4c1bd8c6`; `824eb0bd` bleibt als lokaler Branch `beleg/sel1-payload`
  (wird weder gepusht noch gemerged, wie `versuch/plopp-pb5-pl3-vor-reset`).
- Spiegel `tfa-h713/`: neu erzeugt, **6 Patches**, `SERIES.txt` nennt Basis `347d1c16` und Kopf `4c1bd8c6`.
  Prüfung: Serie auf die Basis angewendet ergibt Baum `36727c0708625abb2a09c2882d8ab470eca94f20`, derselbe
  wie der Fork-Kopf.
- Submodul-Zeiger in `main` auf `4c1bd8c6`.
- Ohne Wirkung auf das Gerät: das installierte BL31 (v0.96-beta, 05.10.) ist dasselbe Binary.

## 4 Was damit für den Push gilt (TODO 1.6)

GitHub `well0nez/arm-trusted-firmware` steht auf `dfa9fab4`; der Push bringt genau einen Commit, den
EL3-HDCP-Dienst. Der Rechtsrahmen dafür steht in `AGENTS.md` §0; Schlüsselmaterial enthält er nicht
(`installer/tests/no_key_material.py`, `release/check-hdcp-artifacts.sh`).
