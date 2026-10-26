# h713-panel - the settings as a web page

`h713-panel` is the projector's web page: opened on a phone over the projector's Wi-Fi or in a browser
over the LAN, it carries the entries of the vendor's "Projection Settings" and "Display settings" - in our
own style, not a copy. One dependency-free Python 3 script plus the page beside it, no framework, no build
step, nothing fetched from the internet. The settings page on the wall, driven by the remote, is
[h713-settings](h713-settings.md); both call the same tools.

**Nothing is decided in the page.** Every button is one command this project already has, and the first
`ok`/`error` line of that command's answer is what appears at the bottom of the screen. The browser never
names a command: it names a verb out of a fixed table, the arguments are checked against their ranges, and
the argument vector goes to `subprocess` without a shell.

```
h713-panel [--port 8080] [--address ADDR] [--tools DIR] [--page PATH] [--keystone-conf PATH]
           [--password-file /etc/h713/panel.env] [--no-auth] [--show-password]
```

## How to reach it

After `systemctl enable --now h713-panel`: `http://<the projector>:8080/`, over the access point `h713` or
over the projector's LAN address (`ip -4 addr`). The page reads its state every three seconds (`h713-warp ctl status`, `h713-tv ctl status brief`, `h713-keystone status`; the `brief` matters, the full status asks the firmware and would hold the warp's frames) - three
`ctl status` calls per interval, and nothing else while it sits open.

## What is on it

**Status**: one dense strip at the top - signal, whether the picture is the console, the video plane or the
warp, warp on/off, whether the mask is up, whether the keystone standing in the warp is the automatic's or a
hand's, which reference the automatic corrects against (`ref ideal`, `ref set` or `ref refused`), the GPU's
frames per second and every thermal zone. The eight values are in the diagram below it.

**Projection.** The keystone is a **diagram**, not a list of numbers: the panel as a dashed rectangle with
the quadrilateral the eight values make inside it, and the four corners as round handles with their names, and under the drawing one button per corner carrying
`x VALUE/MAX  y VALUE/MAX`. Tap a handle to pick it (it turns amber and, if the mask is up, is marked on the
wall with `h713-warp ctl test mask CORNER`); **drag** it and the corner follows the finger, clamped the way
`h713-warp` clamps it and sent as `ctl keystone set CORNER AXIS VALUE` - at most ten times a second while
the drag runs, and once more when it ends. Beside it a pad of four arrows for the picked corner with a step
of 1, 10 or 50 per-mille (`ctl keystone nudge`). Under it: mask on/off, auto keystone now
(`h713-keystone once --apply`), reset, screen zoom 50..100 % in steps of 5 (`h713-warp ctl zoom`, below 100 with `ctl on` if the warp is off), the
projection mode - front, rear, ceiling or rear-ceiling (`h713-warp ctl mode`; the corners keep their wall
names in every mode, the warp flips underneath and re-sorts the values so the correction stays with the housing), after a
move - off, keystone or keystone+focus (written into `/etc/h713/keystone.conf`, then `h713-keystone-auto`
restarted), focus by 5 and 20 msteps, level reference, autofocus now, warp on/off. A control whose hardware the
board does not have (`h713-features status`: camera, accelerometer, focus motor) is hidden, one line says
which, and `after_move` refuses a choice that needs it; without an answer from `h713-features` all stay.

**Picture.** The vendor presets (the one that is on is highlighted), **Gamma** (1.8, 2.0, 2.1, 2.2, 2.4: one button each, `gamma N` is `ctl set gamma N` with N = 0..4, a sentence under the buttons says what the stop does), brightness, contrast, saturation, hue and sharpness as sliders over the
range `h713-tv ctl list` reports, the aspect fit, the firmware's zoom is not on the page any more (23.09.: `out` cropped, the DE only enlarges; the projection area is the warp's zoom under Keystone), and save.

**Colour temperature** (top of the Colour tab, in the White balance card): Auto, Warm, Normal, Cool, one button each; one tap is one command (`colour_temperature NAME` is `ctl set colour_temperature NAME`) and the state is read again afterwards, so the buttons show what the projector holds. Auto follows the picture mode (Cinema and HDR warm, Vivid cool, the others normal) and the line under the buttons says what it comes to ("Warm, from the Cinema preset"); a temperature set by hand stays when the preset changes, and Auto gives it back to the preset. Warm, Normal and Cool are curves the maker measured for this panel; the fine tuning below sits on top of them. On a board that has no warm or cool curve the line says which one is used instead. The tabs read their state with `look` (`ctl get gamma`, `ctl get colour_temperature` and the preset out of `ctl status brief`; no lock, it only reads). Where `ctl get gamma` says `is not available` (a board whose curves h713-tv could not read) the Gamma and Colour temperature controls are hidden; the Colour tab stays for the white balance and the colour when the firmware has them, and the other way round. "Reset white balance" gives the neutral white balance back and sets the colour temperature to Auto (two commands, `wb_reset` and `colour_temperature auto`), as Reset does on the projector's own page. "Save picture settings" (`ctl save`) takes gamma and colour temperature along.

**Colour.** The display firmware's own white balance and colour management (`h713-tv ctl wb` and `ctl cm`, [h713-tv](h713-tv.md)), operated the way the projector's own settings page does ([h713-settings](h713-settings.md)). *White balance* is two sliders, Warm - Cool and Green - Magenta (-50..+50 in steps of 2), the value written as a word (`warm 12`, `magenta 6`) so that the direction is never guessed. They only ever lower a gain (0.4 % per step: cool lowers red, warm lowers blue, magenta lowers green, green lowers red and blue), so white never clips. The page sends the two numbers (`wb_tune`), the tool passes them on as `ctl wb sliders COOL MAGENTA`; the gains are h713-tv's arithmetic (tested over all 101 x 101 positions in its `test_color`), offsets unchanged, and `colour` reads the positions off the answer of `ctl wb`. *Colour* is one of six primaries (Red, Yellow, Green, Cyan, Blue, Purple, a button each, with a dot on every one that is changed) and its Hue and Saturation (-100..+100 in steps of 5), a step on top of the value the picture mode itself puts there (`cm_set`, which is `ctl set cm_AXIS_hue|sat N`). A slider sends one command when it is let go. Each part has its reset (`ctl wb reset`, `ctl cm reset`; the second also resets colours this page does not offer). Nothing is kept until "Save picture settings" (`ctl save`, which takes the white balance and the colour steps along; the Colour tab has the same button). The tab reads its state with `colour` (`ctl wb` and `ctl cm`, no lock). Where `ctl wb` says `[not available: ...]` (another display firmware, or no `/dev/mem`), the tab is hidden, as the controls of absent hardware are; when the gains in force are not ones the two sliders can make (set by hand with `ctl wb R G B ...`), the sliders show 0 and a line under them says so. *Not offered since 20.10.2026:* the card of the primaries (hue and saturation) - the display firmware's colour manager has no visible effect on the HY310, measured with the camera; `controls` reports `colour-manager` false and the page hides the card, the verbs `cm_set` and `cm_reset` stay.

Measured on the HY310 (19.10.2026), the page driven by a script in a browser and `h713-tv ctl wb` and `ctl cm` read after every step: Warm - Cool 12 towards warm and Green - Magenta 6 towards magenta gave `512 500 487`, 12 towards cool gave `487 500 512`, 20 towards green `448 512 471`, and an offset set from the shell (520) stayed through the slider moves; red saturation +5, yellow hue +10 and saturation -15 showed as the matching `ctl cm` lines; the two resets gave 512 six times and `cm all neutral`; a page loaded afterwards showed what the projector held, including a yellow hue that had been set and kept from outside; "Save picture settings" wrote the six values and the colour steps into the kept file and changed nothing else in it. Each of these answers carried `registers read back`. Not measured: the wall (the colour of the picture), a phone, Firefox, a change of picture mode with the Colour tab open, the HY300PRO-G-EU.

**Sound.** Volume 0..100, mute on/off, audio auto/on/off.

## On a phone and on a desktop

The same page. Below 900 px it is one column with three group buttons and one group on the screen at a
time; from 900 px on the groups stand side by side under the status strip and the group buttons disappear.
Every control is a real `<button>` or `<input>` - Tab walks the page, Enter presses, and the corner handles
are in the tab order too: with the keyboard on one of them the arrow keys nudge that corner by the chosen
step (the first arrow after the focus has moved picks the corner instead).

## Installing it

```
install -d /usr/local/lib/h713-panel
install -m 755 h713-panel /usr/local/lib/h713-panel/h713-panel
install -m 644 page.html  /usr/local/lib/h713-panel/page.html
ln -sf /usr/local/lib/h713-panel/h713-panel /usr/local/bin/h713-panel
install -m 644 h713-panel.service /etc/systemd/system/h713-panel.service
systemctl daemon-reload && systemctl enable --now h713-panel
```

The page has to stay beside the real file (the tool follows its own symlink to find it), the same rule
`h713-keystone` has for its `model/`.

## What it does not do

- **One password (since 05.10.2026).** HTTP Basic Auth, any user name; the password is made at the
  first start and kept in `/etc/h713/panel.env` (root, 0600). `h713-panel --show-password` prints it,
  the journal shows it once when it was made. `--no-auth` serves an open page for a bench and says so.
  Plain HTTP: the password crosses the home network unencrypted, which is the level of the Wi-Fi
  password itself. A reinstall of the system makes a new one (TODO 1.2b).
- **No gamma points and no picture-mode tables.** (Superseded 19.10.2026: the page now sets the gamma level and the colour temperature, see Picture and Colour temperature above; before, it offered no gamma at all.) The 33 points of a gamma curve, the picture-mode tables and the per-board PQ data stay `h713-pq`'s and `h713-tv`'s; the Colour tab reaches the colour temperature, the firmware's white balance and colour management. It offers six of the firmware's twelve colour axes (not skin tone, lips or the in-between ones) and not the colour's value (brightness) step.
- **No installer, no updates, no file upload, no shell.** The verb table is the whole surface.
- **It decides nothing itself.** If a tool is missing or refuses, the page says which one and why, in that
  tool's own words, and changes nothing. The menu control `mode` is not a slider; presets set it.

`python3 -m unittest discover -s tests -v` runs the tests: the verb table, the ranges, the refusals, the
status parsing and the page's own verb list, against shell scripts that stand in for the five tools.

Details: docs/tools/h713-warp.md, h713-keystone.md, h713-tv.md, h713-focus.md, h713-autofocus.md.
