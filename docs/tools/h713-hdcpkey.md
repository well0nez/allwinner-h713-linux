# h713-hdcpkey

`h713-hdcpkey` says which HDCP key material a device has, and where it sits. Point it at a raw eMMC dump,
at a secure-storage region file, or at a backup directory. It **searches** the items by their own
structure instead of assuming the region's position - on a board nobody has measured, "no key set at
LBA 12288" would only mean we looked in the wrong place.

It prints structure and fingerprints (SHA-256, one-way), never key bytes. The key set is a DRM secret
and stays on the device it belongs to; `installer/tests/no_key_material.py` keeps it out of this
repository ([hdcp](../subsystems/hdcp.md)).

```
installer/h713-hdcpkey emmc-full.img                    # a raw dump: searched end to end
installer/h713-hdcpkey --limit=0x4000000 emmc-full.img  # only the first 64 MiB
installer/h713-hdcpkey dump/secure-storage.bin          # the region file a dump keeps
installer/h713-hdcpkey ./h713-dump                      # a backup directory: its secure-storage.bin
```

A dump made as root is readable by root only; run the tool the same way, or it says `Permission denied`.

## What it prints

A synthetic region from the tool's tests (`installer/tests/test_hdcpkey.py`), whose made-up key sets
nobody has recorded:

```
secure-storage items in region.bin
  6 item(s), region start(s) at LBA 0
  LBA 16       slot@0x2000      snum               outer=16    inner=-
  LBA 24       slot@0x3000      snum               outer=16    inner=-
  LBA 32       slot@0x4000      hdcpkey            outer=396   inner=320    UNKNOWN key set
  LBA 40       slot@0x5000      hdcpkey            outer=396   inner=320    UNKNOWN key set
  LBA 48       slot@0x6000      hdcpkeyV22         outer=988   inner=912    UNKNOWN key set
  LBA 56       slot@0x7000      hdcpkeyV22         outer=988   inner=912    UNKNOWN key set

  Not seen before. To record them, add to KNOWN_SETS in installer/h713/hdcpitems.py:
      "<sha256>":
          "hdcpkey key set of <board>",
      ...
  and to KNOWN in installer/tests/no_key_material.py, so the guard knows them too.
```

One line per item - every item is stored twice, so each name appears twice. `outer` is the slot's
payload length, `inner` the record inside a key item: 320 bytes for HDCP 1.4 (the 288-byte key set and
its trailer), 912 for HDCP 2.2. The end of the line is the verdict; on a device of ours it reads
`the known vendor HDCP 1.4 key set` and `the HDCP 2.2 key set of the reference HY310` (or `HY300 Pro`):

| Verdict | Meaning |
|---|---|
| a known set's name | the fingerprint is in `KNOWN_SETS` (`installer/h713/hdcpitems.py`) |
| `UNKNOWN key set` | a well-formed item nobody has recorded; the report ends with the two lines to paste into `KNOWN_SETS` and into `no_key_material.py` |
| `!! ...` | a damaged item: a payload length out of range, or an inner record that does not fit its slot (a slot without the magic is not an item at all) |

`none found` means the board keeps its items elsewhere, or the file does not cover them - an
`*-filled` image does not: the region lies in a gap between partitions and is zeroed there.

Measured on an HY310 and an HY300 Pro with different serial numbers: the **HDCP 1.4** set is the same
on both (one set for the product line), the **HDCP 2.2** set differs (bound to the device). That is why
a secure-storage region must never be copied onto another device: it would overwrite that device's own
2.2 set, its serial number and its MAC addresses. `h713-install` compares the region byte for byte after
writing and stops if it changed.

## Exit status

`0` a known key set and nothing odd · `1` nothing found, unknown, damaged or unreadable · `2` usage.

The installer runs the same check (`hdcpitems`) on the device it installs to and prints the verdict
(`known vendor set`); this tool is the stand-alone form for a dump on your PC.
