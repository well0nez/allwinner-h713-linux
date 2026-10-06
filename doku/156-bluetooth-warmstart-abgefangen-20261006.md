# 156 - Bluetooth nach warmem Reboot: abgefangen, Ursache vertagt (06.10.2026)

**Kurz:** TODO 2.3 ist geschlossen, die Ursache nicht gefunden (Marco: "vorerst schließen, nach dem Release noch
einmal ansehen" -> TODO 9.12).

## Stand

- Ohne Gegenmaßnahme blieb nach einem warmen Reboot der erste HCI-Befehl (`0x1003`) manchmal unbeantwortet: UART
  tx:4 rx:0 bei freiem CTS, `hci0` danach bis zum nächsten Boot DOWN. 03.10. mit der alten Unit 2 von 5 (18:43 ok,
  19:15 ok, 20:28 aus, 20:46 aus, 21:01 ok). Ausgeschlossen im Agentenlauf FB-BTRESET (lokaler Bericht
  `FB-BTRESET/REPORT.txt`): hängender BT-Kern (der Chip wird beim Boot über `wlan_regon` neu bestromt und gepatcht),
  ein halbes Paket, `lpm` (0).
- Seit 03.10. (`9971078`, in v0.96) schickt `h713-bt-reset` vor `hciattach` ein HCI_Reset als rohes H4 auf die UART,
  und die Unit zählt erst, wenn `hci0` UP ist (sonst Neustart nach 5 s).
- Mit dem Helfer 7 warme Reboots, 0 Ausfälle: 4 im Agentenlauf (03.10.), 2 im Großtest (04.10., `142` Zeile 4a-12),
  1 heute (18:28 Ortszeit, für das afbd-Modul aus `155`): `reset answered on try 1 (status 0x00) after 154 ms`,
  `hci0 UP after 0 ms`, Unit gestartet bei 10,4 s. Jedes Mal Versuch 1, nie ein Neustart der Unit.
- Bei 2 von 5 wären 7 Treffer ohne Ausfall eine Sache von etwa 3 %: der Reset vorab verhindert den Fehler
  wahrscheinlich, statt ihn nur aufzufangen. Warum, ist nicht gemessen.

## Vertagt (TODO 9.12)

Verdacht: `hciattach any` öffnet die UART mit 115200 und schaltet dann auf 1500000; seit dem Helfer öffnet sie
zuerst `h713-bt-reset`, direkt mit 1500000. Messung: 10 warme Reboots mit der alten Unit, dann 10 mit
`hciattach -s 1500000`, je mit btmon ab Boot. Der Zeitpunkt des ersten Befehls (etwa 2,2 s nach dem Patch) war bei
Ausfall und Erfolg gleich und unterscheidet nichts.
