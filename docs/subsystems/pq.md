# Picture quality: from stock files to registers

Picture quality on the HY310 is computed, not baked in: `h713-pq` turns the same configuration files
that shipped in the vendor Android image (`pq_picturemode.ini`, `tvpq.db`, gamma tables, …) into the
numbers the driver actually writes, and `h713-tv` applies them at every start. Nothing about a colour or
a curve is hand-picked in this repo; it all traces back to a file on the device.

## What the vendor files carry

| File | Carries | On the chain? |
|---|---|---|
| `pq_picturemode.ini` | eight presets per input; each carries the nine controls from `hdmi-in.md` plus a gamma index and a couple of fields not wired up here (backlight, colour temperature) | yes — the starting value |
| `pqcontrol_config_setting.xml` | gamma index (0..4) → exponent (1.8..2.4) | yes |
| `pq_colortemp.ini` | white-balance gain/offset per channel | yes, currently all-neutral on this device |
| `tvpq.db` (SQLite) | the same presets, differently indexed | cross-check only, see below |
| `pq_factory_extern.ini` | a five-point factory curve per control | **not on this chain** — see "What stays open" |

The `tvpq.db` index (`tvin` 0..4) cannot be mapped onto named inputs from the shipped data alone; every
value it carries matches the named `.ini` sections exactly, so the ambiguity is harmless in practice, not
resolved.

## From a preset to a register

```
input × preset            pq_picturemode.ini                       [vendor file]
      -> user value 0..100 (one per control)
      -> RPC argument 0..100, unchanged                             [pass-through, not measured]
      -> register, block ARM 0x05001000-0x050015FC, one field per control, value = argument, 1:1
```

Every field of that block that has been measured on the device carries the RPC argument completely
unchanged — no scaling step in this block: brightness, contrast and saturation (07.09.2026), hue and
sharpness (11.09.2026) all read back exactly what was sent (`doku/85`). Saturation is the one exception
with a second effect: the same call also writes a chroma-gain register downstream,
`floor(argument × 1.28)`, confirmed against five measured points including the one place (59 vs. 60) that
would have caught a rounding error the other way (`doku/81` §3.1). The step from a user's 0..100 to that
RPC argument is passed straight through and has never itself been measured — it is **unverified**, and
harmless today only because no value in a shipped preset would tell the two apart.

## Gamma and white balance

The gamma curve is computed, not read from a file — the vendor's own 33 sample points are all zero in
the shipped data. For the exponent that the current preset selects (every shipped preset uses 2.2), the
same 33→1024-point curve as the legacy calculator produces, packed two 12-bit samples per 32-bit word,
512 words per colour bank. `display.md` covers how that LUT and the CTM matrix reach the CRTC as ordinary
KMS properties; a white-balance gain lands on the CTM diagonal, but the KMS property has no offset term —
harmless here only because every offset in the vendor data is zero.

## Runtime and persistence

`h713-tv` computes presets and gamma from `/etc/h713/tvconfig/` at every start rather than using a
compiled-in table — eight presets instead of six, ~400 ms added to startup, byte-identical LUT confirmed
against `h713-pq`'s own output (`doku/113`, checked on the device 11.09.2026). If the vendor data are
missing or `h713-pq` fails, a compiled-in fallback keeps a picture on screen; nothing refuses to start
over it. A control change is **not** written to disk on every move: someone hunting for the right value
drives through many of them, and saving each one would instead remember whichever setting happened to be
live if the power cut out mid-search. Only `h713-tv ctl save` commits the current values to
`/var/lib/h713-tv/werte`; without it, a restart reverts to the last saved state, and `ctl preset NAME`
discards any unsaved tweak outright.

## What stays open

The factory curve (`pq_factory_extern.ini`) is read and shown by `h713-pq` but its consumer is
**unverified** — its value range (up to 3588 for contrast) rules out both the position before and after
the RPC step that is actually measured, and no vendor tool that might use it is in this repo. Whether
contrast and brightness have a second, downstream register the way saturation does is likewise
unverified; only saturation's PROC-block counterpart has been measured.

Details: doku/81-pq-datenmodell.md, doku/85-re-pq-register.md, doku/87-gamma-ctm-kms.md,
doku/113-plan-pq-laufzeit-und-speichern.md
