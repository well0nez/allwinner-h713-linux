# CPU_COMM call table (board B, project 0x33)

Dumped 2026-08-04 from a live firmware with `h713_disp calltable 0`, after
`h713_disp mips-test 0x33`. 82 populated entries of 1224 slots, all named.

The table is only populated after **application readiness**, so it must follow a
run that proves it. `h713_disp mips-test 0x33` does; `h713_disp test` does not
(it passes `prove_ready=false` and patches `source_id` to 2, which makes the
firmware abandon init).

## Entry layout

| offset | contents |
| --- | --- |
| `+0x00` | `0x00010000`, version/flags |
| `+0x04` | pid -- `0x8b8f32b0` for every entry so far |
| `+0x08` | routine id, what `commcall` takes |
| `+0x0c` | ASCII name, NUL-terminated (`THal_Vp_Deinit_1_000`) |
| `+0x50` | handler VA |
| `+0x5c` | `0xffffffff` free sentinel |

Stride `0x60`. Ids are **not** derivable from the name: crc32, ~crc32, djb2,
djb2-xor, sdbm, FNV-1, FNV-1a and ELF hash all fail against
`THal_Vp_GetImageBufferAddr -> 0x2f02f7dd`. Read them from the table.

Invocation form, known good:

```
h713_disp commcall 2f02f7dd chan=0 pid=8b8f32b0
```

## Display state -- the teardown set

| id | handler | routine |
| --- | --- | --- |
| `a30d4c6b` | `8b10a0e8` | `THal_Vp_EnableBlackScreen` |
| `b66041d8` | `8b10a110` | `THal_Vp_DisableBlackScreen` |
| `2fdcdc6f` | `8b10a138` | `THal_Vp_EnableVideoFreeze` |
| `3ab1d1dc` | `8b10a160` | `THal_Vp_DisableVideoFreeze` |
| `0152f134` | `8b10a188` | `THal_Vp_EnableScreenCover` |
| `143ffc87` | `8b10a1ec` | `THal_Vp_DisableScreenCover` |
| `1c6ff747` | `8b109f04` | `THal_Vp_Init` |
| **`eaaa24c9`** | `8b10a0e0` | **`THal_Vp_Deinit`** |

## Backlight

| id | handler | routine |
| --- | --- | --- |
| `4d80db0e` | `8b10a410` | `THal_Vp_SetBacklightWorkMode` |
| `b46ce545` | `8b10a444` | `Thal_Vp_SetBacklightPwmInfo` |
| `51ad877e` | `8b10a4c8` | `Thal_Vp_SetBacklightLevel` |

Note the lower-case `Thal_` on two of the three -- the vendor is inconsistent
and the name must match the table exactly if it is ever looked up by string.

## Source and image buffer

| id | handler | routine |
| --- | --- | --- |
| `eaf13de5` | `8b10a218` | `THal_Vp_SetSource` |
| `24efc7c9` | `8b10a244` | `THal_Vp_GetSource` |
| `2f02f7dd` | `8b10adb0` | `THal_Vp_GetImageBufferAddr` |
| `396f16bf` | `8b10ada8` | `THal_Vp_SetImageBufferAddr` |
| `24b17fb7` | `8b109b40` | `THal_Vp_GetSignalInfo` |

## Window / geometry

| id | handler | routine |
| --- | --- | --- |
| `3356c54b` | `8b109d54` | `THal_Vp_Wce_SetWindow` |
| `fd483f67` | `8b109dc0` | `THal_Vp_Wce_GetWindow` |
| `7bbd5772` | `8b109e2c` | `THal_Vp_Wce_GetActiveWindow` |
| `09ffc6eb` | `8b109d20` | `THal_Vp_Wce_SetMirrorMode` |
| `8f8a9581` | `8b109e88` | `THal_Vp_Wce_EnablePixel2PixelMode` |
| `ea7ffef5` | `8b109edc` | `THal_Vp_Wce_DisablePixel2PixelMode` |
| `cb6d765f` | `8b109cd0` | `THal_Vp_SeamlessEnable` |
| `c5429d4a` | `8b109cf8` | `THal_Vp_SeamlessDisable` |

## Picture quality

`7221d017` SetBrightness, `880be6ff` GetBrightness, `023c4033` SetContrast,
`6665fe81` GetContrast, `a84983c3` SetSaturation, `5263b52b` GetSaturation,
`5b2c62d5` SetHue, `5432b456` GetHue, `7335ebb5` SetSharpness, `563e60ab`
GetSharpness, `1a116843` SetGamma, `f6a798d3` SetDCI, `f9b94e50` GetDCI,
`c0da6a8e` SetSNR, `cfc4bc0d` GetSNR, `a4bb0747` SetTNR, `aba5d1c4` GetTNR,
`5c135587` SetBlackExtension, `5d3d7258` GetBlackExtension, `fc42fe0c`
SetWhiteBalance, `f00ca77d` SetColorManagement, `e661461f` GetColorManagement,
`83a878bf` SetPictureMode, `2d8338c3` GetPictureMode, `9817a1c1` SetVideoRange,
`623d9729` GetVideoRange, `c201c220` SetLowLatencyMode, `c32fe5ff`
GetLowLatencyMode, `434567b0` GetDisplayLatency.

## HDMI, ATV, VBI, callbacks

`9ce74c48` HDMI_SetPortMap, `cbf83247` HDMI_GetPortStatus, `6eb4c96a`
HDMI_SetHPDTimeInterval, `449effe8` HDMI_ReloadHdcp14Key, `50817813`
SetHDCP22Key, `fa085aaa` SetHDCP22Pkf, `ba3e5a70` SetHDMIHotPlugByPortCallback,
`93965d14` TurnOnARCAudioPath, `e9b4464d` SwitchARCTXPath.

`a16b7c24` AtvSetRegion, `a138c8fe` AtvChannelChange, `39d6eec4`
AtvChannelScanStart, `9558d223` AtvChannelScanEnd, `80e56656` AtvSetSignalStd,
`6e857547` AtvEnableSnowScreen, `71a4c888` AtvIsFastSyncLock, `24f44438`
CvbsSetPedestalMode.

`0fe1790c` StartVBI, `8a0d26cb` StopVBI, `9c91450e` ResetVBI, `096b60b1`
GetVBIData, `ec2ca0b4` GetVBIOffset, `8f5859c2` GetVBIAddr, `96046e19`
GetVBISize, `f3772724` EnableVBILine.

`671ceca6` RegisterSignalChangeCallback, `2692bdbe`
UnregisterSignalChangeCallback, `87a96488`
RegisterCallbackOfDisplayLatencyChange, `72341984`
UnregisterCallbackOfDisplayLatencyChange.

## What is NOT here

There is **no panel power routine** -- nothing for panel VCC, reset, or the
PF6/PH16 GPIOs. Those stay ARM-side, in `h713_disp_stock_panel_power`. So a
complete teardown is two halves: the firmware's own `Deinit`, and our GPIO
power-down using `PanelOffTiming0/1/2 = 20/250/75`.
