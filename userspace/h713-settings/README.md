# h713-settings - the settings page of the box

The page, the rows and what each one sends: [`docs/tools/h713-settings.md`](../../docs/tools/h713-settings.md). This
directory is the source.

```
main.c      the keys and the page's state machine; --test is the sink for the host tests
ui.c        the page drawn into an ARGB canvas (the mockup's S1), a row alone when only it changed
rows.c      the areas and their rows: what each reads from a tool and the one command it sends back
backend.c   the ways to the tools: a ctl socket, a program run or started, a "key = value" file changed in place
input.c     the remote's devices, held alone while the page is open
page.c      h713-osd's page channel: one memfd to draw into, "page show X Y W H"
tests/      test_settings.py: 43 host tests
```

## Building and testing

In the container `h713-build`, against libh713osd (shapes and `osd_text`; `OSD=` names where it lives):

```
make host              # the host binary
make test              # tests/test_settings.py: fake h713-tv, h713-warp and h713-osd page channel on Unix sockets,
                       # stand-in tools, FIFOs for the remote, a temporary /etc/h713; H713_TEST_FONT names a font
make cross SYSROOT=/work/repo-neu/mainline/build/sysroot-arm64 FT=<a root with FreeType's static libraries>
```

The tests read what a row sends from the fakes' logs and what it keeps from the files; one renders the page and checks where
the pill, its outline and the slider land. Environment overrides for the tests: `H713_SETTINGS_TV`, `_WARP`, `_ETC`, `_BIN`
(the tools' directory), `_OSD`, `_INPUT` (files in place of the remote's devices), `_POWER`, `_SYS`, `_DEV`, `_FONT`, `_IDLE`,
`_TIMES` (one journal line per drawing: the milliseconds it took and its size), `_SNAP` (a directory: the canvas after every drawing, as PAM), `_PATIENCE`.
