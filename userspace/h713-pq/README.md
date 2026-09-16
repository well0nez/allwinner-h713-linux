# h713-pq - read the stock PQ data and convert it into kernel interfaces

`h713-pq` reads the picture quality data of the HY310's stock firmware and computes from it the values our
kernel interfaces need: the **argument of the PQ RPCs** (saturation, contrast, ...) and the 512-entry LUT in
DE2 format for gamma (package G of the night plan `doku/78-nachtplan-hdmi-switch.md`).

> **Correction of 07.09.2026.** The first version computed the saturation into a **register value**
> (user value -> factory curve -> gain byte) and printed `0x4C` for `standard`. The measurement on the device
> (`doku/nachtlog/K5-board-verifikation.md` section f) refuted that: the firmware takes an
> **RPC argument 0..100** and computes the gain itself as `floor(argument x 1.28)`; `0x4C` belongs to
> `SetSaturation 60`, not to 50. Since then `h713-pq` prints the RPC argument, and the register value is only
> a control output. The story: `doku/nachtlog/G-korrektur-saettigung.md`.

**The tool computes and prints.** It opens no `/dev/mem`, writes no register, talks to no board and starts no
service. Where a write path makes sense it is printed as a **command line** or written as a **file**; the
writing is the business of the kernel (package H/I) or of a board script.

Data model and derivation: [`doku/81-pq-datenmodell.md`](../../doku/81-pq-datenmodell.md).

## Calls

```bash
./h713-pq list                                   # inputs, modes, factory curves, data state
./h713-pq show HDMI1 vivid                       # the whole chain for one picture mode
./h713-pq show HDMI1 standard --lut gamma.bin    # plus the LUT of that mode
./h713-pq saturation HDMI1 cinema                # saturation of a mode -> RPC argument
./h713-pq saturation HDMI1 72                    # saturation as a user value 0..100
./h713-pq gamma 2.2 --lut out.bin                # DE2 LUT from a gamma exponent
./h713-pq gamma 2.2 --kanal all --lut rgb.bin    # R, G and B bank in a row
./h713-pq show HDMI1 standard --json --lut g.bin # machine readable, for h713-tv (see below)
```

`--daten DIRECTORY` sets the tvconfig directory. Without it the search goes, in order:
`$H713_TVCONFIG`, `/etc/h713/tvconfig`, then `re/vendor/HY310/extracted/vendor_a/etc/tvconfig` in the work tree.

**The option names `--daten` and `--kanal` keep their German spelling.** They are the interface to `h713-tv`,
which starts this program at every boot with exactly that command line (`main.c`, `pq_start()`); the JSON field
names below are the same kind of interface. Both sides are renamed in one later step, together.

It needs only the Python standard library (tested with 3.12), no package, no installation.

## Machine readable output: `show ... --json`

Since 11.09.2026 `h713-tv` calls this program once **at start** and applies what comes back (plan 113 §A.3,
way (a): one source of truth instead of the same computation twice). That is what `--json` is for:

```bash
h713-pq --daten /etc/h713/tvconfig show HDMI1 standard --json --lut /run/h713-tv/gamma-laufzeit.bin
```

**On `stdout` there is then exactly one JSON object and nothing else**; every message - including the one about
the written LUT - goes to `stderr`. The exit code is 0 or 2 as everywhere else.

The field names are the interface and stay as they are, German words included:

| Field | Meaning |
|---|---|
| `version` | version of the record (`1`). The reader discards what it does not know |
| `erzeuger`, `daten` | who computed and out of which directory |
| `eingang`, `preset`, `quelle` | what was asked for and which file the row came from |
| `modus`, `modus_eigen` | picture mode number for `THal_Vp_SetPictureMode`; `modus_eigen: false` means "the firmware has no mode of its own for this name" (`energy_saving`, `custom` -> standard) |
| `regler` | the nine values sent after the mode, under the column names of the vendor INI: `brightness contrast saturation hue sharpness tnr snr dci blackextension` |
| `weitere` | `colortemperature`, `gamma`, `backlight`, `dynamic_backlight` - the four columns for which there is no control today |
| `gamma_index`, `gamma_exponent` | level 0..4 and the exponent belonging to it |
| `lut`, `lut_bytes`, `lut_sha256` | the file written with `--lut`; without `--lut` all three `null`/`0` |
| `presets` | **all** picture modes of this input, each with `name`, `modus`, `regler`, `weitere`, `gamma_*` |
| `fehlende_dateien` | what was not read, with the reason |

`presets` comes along so that the reader can answer `ctl preset energy_saving` without starting a second
Python process; the requested row stands in the record flat as well. Both come out of `model._preset_record`
and therefore cannot drift apart (test `test_flat_fields_and_list_are_the_same`).

**The picture mode number stands in none of the eight vendor files.** `tvpq.db` keeps a counting of its own
(0 standard, 1 cinema, 2 vivid ...), the ARM library a third; for the RPC only the MIPS firmware counts
(0 Vivid, 1 Standard, 3 Game, 6 Computer, 7 Cinema, 12 HDR). The table stands with its evidence in
`model.FIRMWARE_MODE`, origin
[`doku/nachtlog/S14`](../../doku/nachtlog/S14-re-picture-mode.md) §1.2 - it belongs here because it was the
last quantity the sentence "input x picture mode -> what has to be sent" was still missing.

**`--json` reads less.** For the record only `pq_picturemode.ini`, `tvpq.db` and
`pqcontrol_config_setting.xml` are needed (`sources.FILES_FOR_RECORD`). `pq_factory_extern.ini` is 592 kB and
worth 85 ms on its own - measured on the device - and since the correction of 07.09. it is no longer on the
computation path. Every other output shows everything and therefore reads everything. What was skipped stands
in `fehlende_dateien` with the note "not requested"; no output pretends it had seen the file.

**An unreadable file is not fatal.** Since h713-tv reads along at start, an abort while reading would be one
picture less: `sources.load` catches read errors per file and notes them. A wrecked `tvpq.db` then costs the
cross-check and the mode `custom`, not the presets. What is really missing after that shows up while
computing - with the name in question.

## Data sources

Every file is **only read and never copied** - vendor binary data stay under `re/vendor/...`.

| File | What is used from it |
|---|---|
| `pq_picturemode.ini` | picture mode presets per **named** input (ATV, DTV, HDMI1-3, VGA1-3, CVBS, VIDEODEC): 13 user values per mode |
| `pq_factory_extern.ini` | `[PICTURE_CURVE_<group>]` - factory curves brightness/contrast/saturation/hue/sharpness with five sample points at 0/25/50/75/100; `[PQ_ENABLE]` - switches |
| `pq_colortemp.ini` | `[COLOR_TEMP_<group>]` - white balance (gain 0..1023, offset +-512) per colour temperature |
| `tvpq.db` | `Picture_Mode` (25 rows), `White_Balance_Mode` (20), `Gamma_Point` (33) - as a **cross-check** against the INI |
| `pqcontrol_config_setting.xml` | `<transform name="gamma">` - gamma index 0..4 -> exponent 1.8/2.0/2.1/2.2/2.4; default values |
| `pqcontrol_custom_setting.xml` | the values last set on stock, the active source and mode per input |
| `portmap.cfg` | port - source ID - name (HDMI1=1 ... ATV=6) |

Not evaluated, because they are not part of the PQ chain: `pq_overscan_config.ini` (geometry/overscan),
`atsc_system.xml`, `dvb_system.xml`, `tv_scan_list.xml` (tuner/demodulator, channel search),
`panel_config/panel_config.ini` (panel timing), `HDMI_EDID_14/20.bin`.

## The chain

```
input x picture mode                    pq_picturemode.ini  (names), tvpq.db (cross-check)
   -> user value 0..100                 proven: vendor file
   -> RPC argument 0..100               NOT measured - passed through 1:1, see below
   -> register                          computed by the firmware, not by us
```

The **factory curve** from `pq_factory_extern.ini` deliberately no longer stands in this chain. It stays in
the output as a vendor datum, its consumer is open - see below.

## What is proven and what is not

**Proven - the registers of the five PQ controls.** From the static RE of the `UIvalueMapping` table
(`doku/85-re-pq-register.md` §A.1) and the board acceptance (`doku/nachtlog/K5-board-verifikation.md` c/e/f):

| Control | RPC | Item | Register | Field | Register content | State |
|---|---|---|---|---|---|---|
| brightness | `SetBrightness` | 3 | `0x05001234` | `[15:0]` | = argument | measured, effective (dark material: std 12.6->22.7, `nachtlog/I0`) |
| contrast | `SetContrast` | 4 | `0x05001234` | `[31:16]` | = argument | measured, effective (0->100 = 12.16 % of the pixels) |
| saturation | `SetSaturation` | 5 | `0x05001238` | `[15:0]` | = argument | measured, effective |
| hue | `SetHue` | 6 | `0x05001238` | `[31:16]` | = argument | measured 11.09., effective (0 magenta, 100 green) |
| sharpness | `SetSharpness` | 7 | `0x05001228` | `[23:8]` | = argument | measured 11.09.; effect on the picture not measured separately |

**All five fields of this block hold the RPC argument unchanged - 1:1, without a factor.** The three
additions of 11.09.2026 (brightness does work after all, hue and sharpness measured) stand with their origin
in `doku/81-pq-datenmodell.md` §7 points 3 and 4; plan 113 §A.6 asked for them. The state column says what
this table knows: "measured" means the register was read back on the device, "effective" means the change was
seen on the picture as well. The older reading "measured, no effect" at brightness was refuted on 07.09.
against dark material (`nachtlog/I0`) and is gone.

**Proven - the special case saturation.** `SetSaturation` is the only one of the three measured RPCs that
writes a **second** register, the chroma gain `0x05140508` bits [23:16] in the PROC block:

```
SetSaturation(N)  ->  0x05001238 [15:0]  = N
                  ->  0x05140508 [23:16] = floor(N x 1.28)
```

Measured at `N` = 0 / 50 / 59 / 60 / 100 -> `0x00` / `0x40` / `0x4B` / `0x4C` / `0x80`. The neighbouring
points 59 and 60 decide the kind of rounding: 59 x 1.28 = 75.52, measured is 75 - so **round down**. The
factor therefore does **not** sit between RPC and PQ block (there it is 1:1) but on this second, downstream
write. The firmware's idle value `0x144C0000` (`0x4C` = 76) is exactly `SetSaturation 60`;
`prep_after_boot.sh` does not call `SetSaturation` at all. The field range the RPC scale 0..100 reaches is
thus `0x00..0x80` - `0xFF` (cstenger: oversaturated) cannot be reached through the RPC.

**Open - does contrast/brightness have such a second register too?** Unknown, and not guessed. The board
acceptance dumped only the PQ block `0x05001xxx` for contrast and brightness, not the PROC block; and
`doku/85` §A.7 records that for `0x05140508` **no** static writer exists in the image (the access is register
indirect). How to measure it: repeat the measurement from the K5 acceptance (c)/(e) and dump
`0x05140000...0x051405FC` along with it.

**Open - the step user value -> RPC argument.** It is not measured. Proven is only what stands left and right
of it: the vendor presets run 0..100, and the RPC takes 0..100 (`SetContrast 20/80/100`,
`SetSaturation 0/50/100`). `h713-pq` therefore passes the user value through unchanged and writes that at
every point of output.

**Open - who consumes the factory curve?** The curve **cannot** be this step: its values run up to 192
(saturation) and 3588 (contrast), the argument demonstrably only up to 100, and the register content is the
argument, not the curve value. Laying the curve over it anyway (normalized onto 0..100), the result would be
identical for **every** saturation value of these vendor data: the only deviation in the whole range sits at
user value 75 (-> 76), and 75 occurs in no preset (values that occur: 45, 50, 60). So the open step changes
nothing today - that is the reason why it may stay open instead of being guessed. A test locks exactly that
down (`test_open_step_changes_nothing_today`).

**Proven - the gamma LUT format.** DE2 banks `0x05208000` (R), `0x05208800` (G), `0x05209000` (B), each
512 x u32 with `u32[i] = (lut[2i+1] << 12) | lut[2i]`; control `0x051C00E8`, status `0x051C0174`, write
sequence in `legacy/userspace/hy310-pqd/BACKGROUND.md` §5.3. The sequence is carried out by **package H in the
kernel**, not by this tool. The relation gamma index -> exponent is proven three times over:
`pqcontrol_config_setting.xml` (`level0..level4` = 1.8/2.0/2.1/2.2/2.4), the comment header of
`pq_picturemode.ini` (`#gamma :0-1.8,1-2.0,2-2.1,3-2.2,4-2.4`) and the table `dword_4A50`
(180/200/210/220/240) from `libhaldisplay.so`.

**Open - the `tvin` numbering of `tvpq.db`.** The INI names its inputs, the database numbers them. From the
shipped files the number can only be narrowed down (`list` shows the candidates), not resolved. Therefore
`h713-pq` computes over the **named INI sections** and uses the database only as a cross-check over the column
`name`.

**Empty in the data.** `Gamma_Point` is zero throughout (unusable as a curve - stock computes the points at
run time, BACKGROUND.md §6.2), and the white balance is neutral everywhere (gain 512/512/512, offset 0). That
is why the three LUT banks are identical and `h713-pq gamma` works from the exponent alone.

## Layout

Three modules, strictly separated - one reads, one computes, one prints:

| File | Role |
|---|---|
| `h713_pq/sources.py` | reads SQLite, INI (its own parser), XML, `portmap.cfg`; computes nothing |
| `h713_pq/model.py` | RPC arguments and their target registers (`PQ_TARGETS`), chroma gain as a control value, factory curve, gamma sample points -> LUT -> DE2 packing; reads no files |
| `h713_pq/output.py` | tables, LUT file, board command lines |
| `h713_pq/cli.py` | command line |

The vendor INI dialect (values with a continuation `\`, indexed keys such as `PICTURE_CURVE_SETTINGS[3]`,
duplicate keys inside one section) does not agree with `configparser`; `sources.py` therefore brings its own,
very small reader.

## Tests

```bash
python3 tests/test_h713_pq.py            # 45 tests
```

The tests read the **real** vendor files at run time and skip themselves cleanly when the tvconfig directory
is missing. `tests/legacy_ref.cpp` is the comparison harness: it builds against
`legacy/userspace/hy310-pqd/src/pqgamma.cpp` and writes the same DE2 bank; the test `TestAgainstLegacy`
compares them byte by byte for the exponents 1.0/1.8/2.0/2.1/2.2/2.4 (if the legacy tree or `g++` is missing,
it is skipped). The legacy calculator and `h713-pq` are bit-identical.

The saturation tests check the **measured** points from the K5 acceptance (f) directly (`0/50/59/60/100` ->
`0x00/0x40/0x4B/0x4C/0x80`), no longer an intermediate computation. Where the correction changed an expected
value, the reason stands in the test itself.

## Writing - over the RPC, not into the register

`h713-pq` writes nothing. Since the correction, the write path it prints for the saturation is the **RPC**,
the way stock uses it:

```
ssh root@192.168.8.141 'python3 /root/pq_probe.py rpc SetSaturation 60'
```

Writing the gain byte into the register by hand (as `analyse/hdmi-seq/pq_saturation.py` does) bypasses the PQ
block `0x05001238` and everything that hangs on it. **`pq_saturation.py` also still carries the refuted
formula** `round(0x4C x curve(u) / curve(50))`; it is thus 12 gain steps off for `standard`. The script does
not belong to this package (and a copy lies on the board under `/root/`), which is why it was not touched
here - but it should be withdrawn or moved onto the RPC path.

## Running the tests without vendor data

The tests read a tvconfig directory at run time and skip themselves when there is none. A synthetic
one, built only from values this repository states in the open (no vendor byte), comes from
`tests/make_fixture.py`:

```bash
python3 tests/make_fixture.py /tmp/tvconfig
H713_TVCONFIG=/tmp/tvconfig python3 -m unittest discover -s tests -v   # 44 of 45 run
```
