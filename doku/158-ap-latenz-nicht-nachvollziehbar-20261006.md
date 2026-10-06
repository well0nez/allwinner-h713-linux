# 158 - AP-Latenzspitzen: mit dem heutigen Abbild nicht nachvollziehbar (06.10.2026)

**Kurz:** TODO 2.12. Am 12.09. sprangen die Ping-Zeiten im AP-Modus zwischen 3 ms und 2 s (ein Client bei −50 dBm,
Durchsatz 5,7 MB/s). Heute, gleiche Konfiguration, kein Ausreißer über 124 ms. Punkt geschlossen; `known-issues.md`
führt ihn nicht mehr, `docs/subsystems/wifi.md` hat die neue Messung und die alte als überholt.

## Messung (HY310, 17:33-17:37 UTC)

- Weg: `wifi.env` nach `/root/sicherung-ap-latenz/` gesichert, Rückfall-Timer (`systemd-run --on-active=20min`, spielt
  die Sicherung zurück), dann die ausgelieferte `rootfs/overlay/etc/h713/wifi.env` (AP `h713`, 2,4 GHz, Kanal 6, DE,
  192.168.4.1) und `systemctl restart h713-wifi`, zeitversetzt per `systemd-run`, weil ssh über das WLAN lief.
- Client: der Arbeitsrechner über seine sonst freie WLAN-Karte (Heimnetz über Kabel), 192.168.4.89 per DHCP.
  Box: `station dump` −47 dBm, tx 72,2 MBit/s MCS 7, rx 65 MBit/s; `iw dev wlan0 get power_save`: on (wie ausgeliefert).
  Bluetooth lief dabei (am 12.09. noch nicht).
- 100 Pings alle 0,2 s: 1,2 / 9,4 / 124 ms (min/avg/max), 0 % Verlust.
- 60 Pings jede Sekunde: 2,6 / 4,5 / 14,4 ms, Median 3,4 ms, 0 % Verlust.
- Zum Vergleich im Station-Modus im Heimnetz (−39 dBm, power_save on): 30 Pings 1,1-59 ms.
- Rückweg: `wifi.env` zurück (md5 gleich der Sicherung), Box nach 30 s wieder unter ihrer alten Adresse, Timer gestoppt,
  das AP-Profil am Rechner gelöscht.

## Nicht geklärt

Woher die 2-s-Spitzen am 12.09. kamen. Seitdem hat sich viel geändert (Kernel, aic8800-Patches, Bluetooth); der Client
von damals ist nicht notiert. Ein Telefon als Client ist nicht gemessen. Wieder aufmachen, wenn jemand die Spitzen sieht.
