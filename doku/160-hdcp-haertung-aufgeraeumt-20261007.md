# 160 - §6 HDCP-Härtung aufgeräumt, S-EL1-Reste gelöscht, der Warteschalter vorbereitet (07.10.2026)

**Kurz:** Marco will S-EL1 nicht, weder in TF-A noch in U-Boot, und keine Belege als Branches oder Klone. Die Reste
sind gelöscht; in der Linie und auf dem Gerät ändert das nichts (`doku/153`: BL31 mit und ohne S-EL1 bytegleich).
TODO §6: 6.3, 6.4 gestrichen, 6.7 beantwortet, 6.8 gelöscht, 6.6 als Patch vorbereitet, 6.1/6.2/6.5 bleiben als ein
Härtungspaket nach dem Release.

## 1 Gelöscht (00:3x)

- TF-A-Fork: `beleg/sel1-payload` (`824eb0bd`, S-EL1-Testpayload) und `versuch/plopp-pb5-pl3-vor-reset` (`0c380aca`,
  die widerlegte Plopp-Hypothese aus `152` §2.10). Beide nie gepusht.
- U-Boot-Fork: der Worktree `umbau/work/FB-HDCP14h/uboot` mit dem unversionierten BL32-Versuch (Hersteller-Trusted-OS
  als BL32, `h713_tee.c`).
- Nicht gelöscht: der Klon `umbau/work/FB-HDCP14h/tfa` (S-EL1-Stand `7fd3eda4`; geprüft: jeder Commit darin ist auch im
  Submodul, nichts Einzigartiges). Der Sicherheitscheck lässt das Löschen eines Verzeichnisses, das gerade
  Arbeitsverzeichnis war, nur einem Menschen; Marco löscht ihn selbst.
- Nachher geprüft: TF-A nur `sun50i-h713` @ `4c1bd8c6`, U-Boot nur `h713-hy310` @ `4913742a`, sunxi-tools `h713` @
  `269dfa22`, Submodul-Zeiger unverändert, Repo sauber.

## 2 §6 Punkt für Punkt

- 6.1/6.2/6.5 (TEE-2/3/5): bleiben als ein Paket nach dem Release - reine Härtung; heute kann Root höchstens einen
  falschen Schlüssel laden (dann kein HDCP), auslesen nicht.
- 6.3 (S-EL1): gestrichen. 6.4 (32-Byte-Anhang): gestrichen.
- 6.6: der Schalter `h713_hdcp14_wait` fällt; U-Boot-Patch und Gegenstück für `check-hdcp-artifacts.sh` gebaut und
  geprüft (`arbeit/hdcp-wait-env-20261007/`), Einbau mit dem Release-Neubau (TODO 1.1a).
- 6.7: der Warteschleifen-Patch bleibt. Gemessen am 05.10. (Kommentar in `h713_mips.c`): HDCP 1.4 authentisiert mit
  entschärfter Schleife, mit scharfer hängt die Box auch mit Schlüssel in der Senke. Marcos „muss am Ende weg" vom 14.09.
  ist damit widerlegt.
- 6.8: gelöscht (siehe 1).
