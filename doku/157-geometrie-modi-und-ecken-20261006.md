# 157 - Geometrie: die Projektionsmodi, die Kalibrierkarten und das Trapez beim Moduswechsel (06.10.2026)

**Kurz:** TODO 2.7. Die Kalibrierkarten (`f84c17c`, einen Tag nach dem Spiegel-Test vom 02.10.) stehen in allen vier
Modi in ihrer Ecke und lesen sich aufrecht. Beim Moduswechsel blieb das Trapez aber nicht am Gehäuse: die acht Werte
blieben stehen und drehten sich mit dem Bild auf die Gegenecken. `h713-warp ctl mode` sortiert sie jetzt um wie Stock
(`3e3a69f`); gemessen deckungsgleich in allen Modi. Die Konsole durch den Warp bleibt offen (TODO 2.7a).
Arbeitspaket lokal: `arbeit/geometrie-20261006/`.

## 1 Messweg

HY310, Beamer aufrecht auf dem Tisch, Quelle ThinkPad 1080p60, Trapez `tl 283,0 tr 112,263 bl 224,28 br 45,0`.
Box-Kamera (Belichtung 5000 / Gain 255). Marco: "ich muss den Beamer nicht umdrehen, dreh das Foto" - die Kamera
sitzt im Gehäuse, das Publikum der echten Montage sieht das Foto unter front so wie es ist, rear links-rechts
gespiegelt, ceiling 180° gedreht, rear-ceiling oben-unten gespiegelt.

Grenze des Wegs: die Kamera sitzt neben dem Objektiv und sieht im Wesentlichen das Panel, nicht die Wand. Ob das
Bild an der Wand rechteckig ist, zeigt sie nicht; dass sich die Form auf dem Panel ändert oder gleich bleibt, schon.

## 2 Kalibrierkarten (16:54 UTC)

Je Modus `ctl test mask tl`: die Karten (`label_box`/`mask_labels` in `gl.c`) stehen nach dem Umrechnen in der Ecke
ihres Namens und sind lesbar - front `br x 45/776`, rear `br`, ceiling `tr x 112/7..`, rear-ceiling `tr x 112/717`,
dazu `zoom 100%` und `per-mille inward value/max`.

## 3 Das Trapez beim Moduswechsel

Marco im ceiling-Modus: "guck dir das an, wie verzogen alles ist - dreht sich das Warp nicht mit?" Der Warp rechnet
`F * K`: das Trapez in Wandecken, danach das ganze Bild gespiegelt. Die Werte blieben beim Wechsel stehen, also
landete die Korrektur gedreht an der Wand - auf dem Tisch doppelt verzogen. FB-MIRROR (27.09.) hatte das bewusst so
entschieden ("nothing is permuted"). Stock sortiert die gespeicherten Ecken beim Wechsel aber um, wenn eine Kamera da
ist (`ProjectActivity.updateProjectMode` -> `KeystoneUtils.setKeystoneNormalXY(alt, neu)`, dieselben vier Tabellen
wie `LocalService`), damit die Korrektur am Gehäuse bleibt.

Jetzt `warp_remount()`: die neue Ecke c bekommt die alten Werte der Ecke, die die Spiegelungen der beiden Modi aus c
machen (rear tauscht links/rechts, ceiling über Kreuz, rear-ceiling oben/unten). Die Automatik (`h713-keystone`,
`MODE_PERM`) permutiert schon je Modus; für dieselbe Lage ergibt das Umsortieren genau ihr Ergebnis.
`test_matrix`: 5 Trapeze x 16 Moduspaare, jede Quellecke landet dort, wo vorher ihr gespiegelter Partner lag (1e-5),
hin und zurück ist die Identität, der Clamp hält; ohne Umsortieren verschieben alle 12 Wechsel das Viereck.

Am Gerät (17:17-17:18 UTC, je Modus Bild und `ctl test border`): Werte rear `tl 112,263 tr 283,0 bl 45,0 br 224,28`,
ceiling `tl 45,0 tr 224,28 bl 112,263 br 283,0`, rear-ceiling `tl 224,28 tr 45,0 bl 283,0 br 112,263`, zurück auf
front die Ausgangswerte. Der Rahmen (das schräge Trapezviereck) liegt in rear, ceiling und rear-ceiling zu 100 % auf
dem von front (±3 px, beide Richtungen). Das Bild steht umgerechnet in allen vier Modi aufrecht. Marco hat den Wechsel
an der Wand gesehen; im Panel ist es die Zeile "Mode" unter dem Zoom.

## 4 Nicht gemessen, offen

- Die Automatik mit wirklich kopfüber liegendem Beschleunigungssensor - ein gedrehtes Foto zeigt das nicht.
- Konsole durch den Warp (TODO 2.7a): ohne Signal steht die Konsole im ceiling-Modus auf dem Kopf, ohne Trapez.
