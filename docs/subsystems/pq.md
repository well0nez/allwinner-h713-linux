# Picture quality: from stock files to registers

Picture quality on the HY310 is computed, not baked in: `h713-pq` turns the same configuration files
that shipped in the vendor Android image (`pq_picturemode.ini`, `tvpq.db`, gamma tables, …) into the
numbers the driver actually writes, and `h713-tv` applies them at every start. Nothing about a colour or
a curve is hand-picked in this repo; it all traces back to a file on the device.

## What the vendor files carry

| File | Carries | On the chain? |
|---|---|---|
| `pq_picturemode.ini` | eight presets per input; each carries the nine controls from `hdmi-in.md` plus a gamma index and a couple of fields not wired up here (backlight, colour temperature) | yes - the starting value |
| `pqcontrol_config_setting.xml` | gamma index (0..4) → exponent (1.8..2.4) | yes |
| `pq_colortemp.ini` | white-balance gain/offset per channel | yes, currently all-neutral on this device |
| `tvpq.db` (SQLite) | the same presets, differently indexed | cross-check only, see below |
| `pq_factory_extern.ini` | a five-point factory curve per control | the OSD-to-register mapping of the *direct* path, not of ours |
| `pq_custom.TSE` | the firmware's own OSD-to-register curves plus the register and bit field per parameter | `h713-pq curves --source tse` |
| `ProjectID_0x00NN.TSE` | nine measured gamma curves, 3 x 1024 samples of 12 bit | `h713-pq gamma --source tse`, off by default |

The `tvpq.db` index `tvin` is **TvSourceType**: 0 HDMI, 1 CVBS, 2 ATV, 3 DTV, 4 VIDEODEC, 5 VGA. Two
proofs in AP3d section 2 - `UpdateDataManager::UpdateDataManager@0x2D99C` builds that map and
`getCurrentMode@0x30924` reads the index out of `current_source_type/tvin`, and the device's own XML has
`tvin="4"` next to `mode_videodec`. The database is what a **factory reset** falls back to; the live source
is `pq_picturemode.ini`, which `PQPictureMode::getPictureMode@0x3485C` reads at run time. The picture mode
`custom` is a node per source in `pqcontrol_custom_setting.xml` (`custom_hdmi1`, `custom_cvbs`, ...), not a
row of the database (AP3d section 3).

## Which file decides which control

| Control | Truth source | Field | Register |
|---|---|---|---|
| brightness | `pq_picturemode.ini` -> RPC `SetBrightness` | PQ block | `0x05001234[15:0]`; direct path `0x051405BC[17:8]` |
| contrast | ditto, `SetContrast` | PQ block | `0x05001234[31:16]`; direct `0x05140D34[27:16]`/`[11:0]` and `0x05140D38[11:0]` |
| saturation | ditto, `SetSaturation` | PQ block | `0x05001238[15:0]`, plus chroma gain `0x05140508[23:16]` |
| hue | ditto, `SetHue` | PQ block | `0x05001238[31:16]`; direct `0x05140508[9:0]` |
| sharpness | ditto, `SetSharpness` | PQ block | `0x05001228[23:8]`; direct `0x05140C4C[23:16]`, `[7:4]`, `[3:0]` |
| DCI / SNR | ditto, `SetDCI` / `SetSNR` | PQ block | `0x0500123C[7:0]` / `0x05001248[7:0]` |
| TNR / black extension | ditto, `SetTNR` / `SetBlackExtension` | no register of this block | through the PQ driver object only |
| gamma curve | `ProjectID_0x00NN.TSE` (vendor) or our exponent | DE2 LUT | `0x05208000` / `0x05208800` / `0x05209000`, control `0x051C00E8` |
| white balance | `pq_colortemp.ini` (neutral here); `pq_custom.TSE` names the registers | gain/offset | `0x051C00D4`/`D8`/`DC`/`E0` |
| colour management | `MP_CM_VPROC` of the ProjectID TSE, 108 register writes per state | 12 axes | `0x05140300`..`0x05140440`, enable `0x0514045C` |
| backlight | RPC `SetBacklightLevel` **and** `/sys/class/backlight/tv/brightness` | - | the MIPS owns the PWM |

Sources: AP3 section 3 (which control goes where, `tables/pq-controls.csv`), AP3d sections 5 and 6,
AP3f 1.5, AP3p 1.3 and 1.5, AP3r section 3.

## Controls the vendor has and we do not

Five, all with an RPC id we already carry, all one argument word (AP3 D2). They are "not yet", not
"impossible"; the kernel side is one V4L2 control each in `0101`.

| Control | RPC | id |
|---|---|---|
| video range | `THal_Vp_SetVideoRange` | `9817a1c1` |
| backlight level | `Thal_Vp_SetBacklightLevel` | `51ad877e` |
| dynamic backlight | `THal_Vp_SetBacklightWorkMode` | `4d80db0e` |
| low latency | `THal_Vp_SetLowLatencyMode` | `c201c220` |
| test pattern | `THal_Vp_EnableScreenCover` | `0152f134` |

Their `Get` routines answer zero for everything, so they would stay write-only like the other nine.

## From a preset to a register

```
input × preset            pq_picturemode.ini                       [vendor file]
      -> user value 0..100 (one per control)
      -> RPC argument 0..100, unchanged                             [pass-through, not measured]
      -> register, block ARM 0x05001000-0x050015FC, one field per control, value = argument, 1:1
```

Every field of that block that has been measured on the device carries the RPC argument completely
unchanged - no scaling step in this block: brightness, contrast and saturation (07.09.2026), hue and
sharpness (11.09.2026) all read back exactly what was sent (`doku/85`). Saturation is the one exception
with a second effect: the same call also writes a chroma-gain register downstream,
`floor(argument × 1.28)`, confirmed against five measured points including the one place (59 vs. 60) that
would have caught a rounding error the other way (`doku/81` §3.1). The step from a user's 0..100 to that
RPC argument is passed straight through and has never itself been measured - it is **unverified**, and
harmless today only because no value in a shipped preset would tell the two apart.

## Gamma and white balance

We compute the gamma curve; **the vendor does not**. The 33 sample points of `tvpq.db::Gamma_Point` are
indeed all zero, but the curve is not missing - it is in the board's own `ProjectID_0x00NN.TSE`, nine
measured curves of 3 x 1024 samples of 12 bit, one per colour temperature, and the firmware hands all nine
to the ARM at start (AP3p 1.5, AP3r 1.2). `CalculateGamma@0xBC48` then lays one exponent on the slot the
colour temperature picks, per channel and keeping the end point:
`out[c][x] = (unsigned)(pow(in[c][x]/end[c], g) * end[c])` with `g = (dword_4A50[index]/100)/2.2`, the
five levels `1.8 .. 2.4` divided by 2.2 (AP3t 2.2). Level 2.2 is neutral, so at first picture the vendor
shows the raw TSE curve of the state `UI_ColourTemp_Normal` - slot 0 on both boards.

Two consequences. **Nothing programs the LUT before Android does**: the firmware's own gamma path is dead
code (AP3r 1.3) and the ARM side refuses to write until both a gamma factor and a colour temperature have
arrived (AP3t 2.1). And on the HY300 Pro the end points are per channel (4087/3863/3459 warm,
3308/3639/4087 cool, 3800/4087/4071 normal): that board keeps its **white balance in the gamma LUT**, so a
curve identical on all three channels - ours - discards it, and KMS clearing `GAMMA_LUT` to the identity
ramp is a visible colour change there and not on a HY310 (AP3r 1.4, AP3t D4). `h713-pq gamma --source tse`
produces the vendor's curve instead; it is off by default until a device test says otherwise.

`display.md` covers how that LUT and the CTM matrix reach the CRTC as ordinary KMS properties; a
white-balance gain lands on the CTM diagonal, but the KMS property has no offset term - harmless here only
because every offset in the vendor data is zero. Kernel patch `0095` is confirmed register for register
from the firmware side, `DBUF_FLIP` included: both write the inverse of the bit read before the transfer,
alternating the buffer on every write (AP3p 1.5, checked against the tree in the Q4 review). The one
difference is ours: `0095` clears `COMMIT` before the flip, the firmware does not - unmeasured.

## Runtime and persistence

`h713-tv` computes presets and gamma from `/etc/h713/tvconfig/` at every start rather than using a
compiled-in table - eight presets instead of six, ~400 ms added to startup, byte-identical LUT confirmed
against `h713-pq`'s own output (`doku/113`, checked on the device 11.09.2026). If the vendor data are
missing or `h713-pq` fails, a compiled-in fallback keeps a picture on screen; nothing refuses to start
over it. A control change is **not** written to disk on every move: someone hunting for the right value
drives through many of them, and saving each one would instead remember whichever setting happened to be
live if the power cut out mid-search. Only `h713-tv ctl save` commits the current values to
`/var/lib/h713-tv/werte`; without it, a restart reverts to the last saved state, and `ctl preset NAME`
discards any unsaved tweak outright.

## What stays open

The factory curve's consumer is **no longer open**: `PQNonLinearCurve::UserValueToMappedValue@0x3AEE8`
interpolates its five points in four segments with `roundf` and `PQNonLinearCurve::getConfig@0x3B224`
reads the file - that is the vendor's *direct* write path through `/sys/class/sunxi_dump/write`, and it is
the default on stock (AP3 3.3). Ours is the RPC path, which hands 0..100 to the firmware, which is why
nothing we measured ever agreed with that curve. `pq_custom.TSE` carries a **second** OSD-to-register
curve, the one the firmware itself applies, and the two do not agree everywhere: contrast at 75 % is 3010
in the ini and 2990 in the TSE (AP3f 1.5). `h713-pq curves --source tse` prints both side by side.

What stays open: which of the two a board actually shows depends on the flag at `PQNonLinearCurve+56`,
and `PICTURE_PARAM_TSE_ENABLE` in `[PQ_ENABLE]` decides whether the ARM side reads the register back or
the ini (AP3f 1.1) - neither has been observed on a projector. The step from a user's 0..100 to the RPC
argument is still unmeasured. And the 18-byte colour-manager profile of the ProjectID TSE is decoded as a
container but not as meaning: that needs one device experiment (AP3r 3.4).

Details: doku/81-pq-datenmodell.md, doku/85-re-pq-register.md, doku/87-gamma-ctm-kms.md,
doku/113-plan-pq-laufzeit-und-speichern.md
