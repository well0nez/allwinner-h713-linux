# installer/tests — the behaviour contract of the PC tools

Golden tests frozen on 2026-09-14 against the stand-alone tools of v0.5-beta (`hy310-install.py`,
`hy310-mkimage.py`, `h713-extract`), plus a fake eMMC (`fakedisk.py`: a sparse regular file that the
tools accept as a device on Linux). Run from this directory:

    python3 -m unittest discover -s . -v

Environment:

| variable | meaning | default |
|---|---|---|
| `H713_TOOLS_DIR` | directory of the tools under test | `installer/` (next to this directory) |
| `H713_EXTRACT_PATH` | the extractor alone | `$H713_TOOLS_DIR/h713-extract` |
| `H713_FIXTURES` | repository fixtures (partition tables, environment, JSON facts) | `tests/fixtures` |
| `H713_FIXTURES_LOCAL` | vendor bytes that never enter the repository (stock bootloader partition, `.fex` files); tests needing them skip when unset | `tests/fixtures-local` |
| `H713_IMAGE_DIR` | the vendor firmware images (`update.img`, HY300 T08, HY350); tests needing them skip when absent | `~/Downloads` |
| `H713_SLOW_TESTS=1` | run the extractor over the full images | off |
| `H713_BUILD_OUT`, `H713_VENDOR_OUT` | inputs of `mkimage-selbsttest.py`; the test skips when they are missing | `$H713_TOOLS_DIR/out`, `.../out/vendor` |

`fixtures/device/README.md` says where every byte comes from. Nothing under `fixtures/` is a vendor
file or a secret; the sperr-scan runs over this directory like over everything else.
