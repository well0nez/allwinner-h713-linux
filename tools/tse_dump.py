#!/usr/bin/env python3
"""tse_dump.py - Parser fuer die TSE-Registerdatenbank des H713-MIPS-Displayprozessors.

Format rekonstruiert aus display.bin (MIPS32 LE, Basis 0x8B100000):
  Dateiheader (26 B)  : LoadTSEBody 0x8B190428   ("TSE read data_header: type[%d] version[0x%08x] ...")
  Gruppe              : TFDGroup::Load  0x8B197310 ("load group: %s, module count %d")
  Modul               : TFDModule::Load 0x8B1983CC (Plugin-Factory 0x8B1980EC, IDs 0x90007..0x90054, 0x9101F)
  State               : TFDState::Load  0x8B1989C0, Attributliste TFDAttrProp::Load 0x8B19537C
  Filter-Match        : TFDAttrProp 0x8B19506C   (jedes State-Attribut muss im Filter enthalten sein)
  RegTableFW-Blob     : Load 0x8B192A0C, Execute 0x8B192EE4 -> Entry-Writer 0x8B18C904,
                        Typ-6-Writer 0x8B18B3A0 (WR8/16/32) / 0x8B18B894 (RMW8/16/32), Basis 0x8B18B328
  EquTable-Blob       : Load 0x8B18DD20 (Felder: 2=Reg, 8=State, 9=Attr; Factory 0x8B18DC70)
  MemoryFW-Blob       : Load 0x8B1916E4;  PolyScalarFW-Blob: Load 0x8B191D4C
  Quellen-Mapping     : kSourceId -> attr1 : Tabelle 0x8B1F2158 (Mapper 0x8B12C490)

Aufruf:
  tse_dump.py [--dir analyse/tse/board] [--project 0x0030] [--all] [--hdmi] [--source 3] [--signal 0x20003]
              [--attr TYPE=VAL ...] [--json out.json]
"""
import argparse, json, os, struct, sys
from collections import Counter, defaultdict

# ----------------------------------------------------------------------------- Konstanten
FILE_TYPES = {0: 'database', 1: 'database-part2', 2: 'ProjectID', 3: 'table-type3(AttrProp?)',
              4: 'table-type4', 5: 'pq_custom', 6: 'projecttable'}
GROUP_TYPES = {0: 'db', 1: 'db2', 2: 'project', 3: 'pq'}
PLUGIN = {  # Modul-ID -> Plugin-Klasse (Jump-Table 0x8B20478C, Index = ID-0x90007; Typeinfo-Namen)
    0x90007: 'RegTableFW', 0x90009: 'GammaFW', 0x9000d: 'DCIFW', 0x90011: 'ScalarFW', 0x90013: 'MemoryFW',
    0x90015: 'AcrFW', 0x90017: 'EquTable', 0x90021: 'ColorManagementFW', 0x90033: 'PolyScalarFW',
    0x90035: 'DPAFW', 0x90038: 'DPAFW', 0x90049: 'SharpnessFW', 0x90050: 'SSR1FW', 0x90051: 'BlackExtensionFW',
    0x90053: 'TNRFW', 0x90054: 'SNRFW', 0x9101f: 'FeatureFW',
}
def plugin_name(mid):
    if mid in PLUGIN: return PLUGIN[mid]
    if 0x90007 <= mid < 0x90055:
        # Jump-Table: 11 IDs -> DCIFW (0x9000d, 0x90034, 0x9003e..0x90046), Rest CustomFW (Raw-Blob)
        if mid in (0x9000d, 0x90034) or 0x9003e <= mid <= 0x90046: return 'DCIFW'
        return 'CustomFW'
    return 'CustomFW'

# Attribut-Typen (Namen teils geraten; Belege: Mapper 0x8B12Bxxx/0x8B12Cxxx, Filter-Builder 0x8B1078EC)
ATTR_NAMES = {
    0x0000: 'always(attr0)', 0x0001: 'source', 0x0002: 'signal', 0x0003: 'frame_rate', 0x0005: 'attr5(panel?)',
    0x0006: 'attr6(output/panel-timing?)', 0x000a: 'input_format', 0x0014: 'attr14(mirror/mode?)',
    0x0018: 'attr18(21:9 scaler)', 0x0019: 'attr19(panel)', 0x001d: 'colorspace', 0x0022: 'attr22(yuv/pc mode?)',
    0x0028: 'compress', 0x0032: 'attr32(panel)', 0x0035: 'attr35(bool)', 0x003a: 'attr3a(bool)', 0x003f: 'attr3f',
    0x0041: 'attr41(output timing)', 0x0044: 'project/picmode', 0x004a: 'deint_format', 0x004e: 'attr4e',
    0x0061: 'attr61', 0x0065: 'icsc_mode', 0x0066: 'csc1_mode', 0x0067: 'icsc2_mode', 0x0068: 'csc_dpa_mode',
    0x0069: 'dither', 0x006a: 'ntsc_pedestal', 0x3001: 'attr3001(picture mode)', 0x3003: 'gamma_sel',
    0x3008: 'advpicture', 0x300b: 'hdmi_mode_index', 0x3013: 'tnr_level', 0x3014: 'snr_level', 0x3015: 'blackext_level',
}
# kSourceId -> attr1 (Tabelle 0x8B1F2158): 1 VideoDec,2 Image,3..6 HDMI1..4,7..9 CVBS,10 ATV
SOURCE_ATTR = {1: 0x10000, 2: 0x10012, 3: 0x10011, 4: 0x10013, 5: 0x10014, 6: 0x10015,
               7: 0x10006, 8: 0x10007, 9: 0x10008, 10: 0x10005}
HDMI_ATTR1 = {SOURCE_ATTR[s] for s in (3, 4, 5, 6)}

# Adressbereiche fuer Markierungen
def region(addr):
    if 0x05000000 <= addr <= 0x06FFFFFF: return None
    for lo, hi, n in ((0x03010000, 0x0302FFFF, 'GIC'), (0x03003000, 0x03003FFF, 'MSGBOX'), (0x03000000, 0x03000FFF, 'SYS_CFG'),
                      (0x02010000, 0x0201FFFF, 'IOMMU'), (0x02000000, 0x0200FFFF, 'PIO/CCU'), (0x03060000, 0x0306FFFF, 'blk0306'),
                      (0x40000000, 0x7FFFFFFF, 'DRAM')):
        if lo <= addr <= hi: return n
    return 'other'

def looks_like_mem(val):
    if 0x40000000 <= val <= 0x7FFFFFFF:
        return 'DRAM-addr' + ('' if 0x4B100000 <= val <= 0x4E7FFFFF else ' OUTSIDE 0x4B100000-0x4E7FFFFF')
    return None

DMA_KEYWORDS = ('WB', 'BUF', 'CAPTURE', 'RDBACK', 'MEMORY', 'DBUS', 'RDB', 'READ_BACK', 'WAGT', 'COMPRESS', 'PFU')

# ----------------------------------------------------------------------------- Stream
class S:
    def __init__(s, d, p=0): s.d, s.p = d, p
    def rd(s, n):
        if s.p + n > len(s.d): raise EOFError(f'read {n} at {s.p:#x}')
        b = s.d[s.p:s.p + n]; s.p += n; return b
    def u8(s): return s.rd(1)[0]
    def u16(s): return struct.unpack('<H', s.rd(2))[0]
    def u32(s): return struct.unpack('<I', s.rd(4))[0]

def parse_attrs(st):
    """TFDAttrProp::Load 0x8B19537C: u16 tag; (tag-2) B hdr; u32 n; n x {u16 type, u32 cnt, u32 vals[cnt]}"""
    tag = st.u16(); hdr = st.rd(tag - 2)
    n = st.u32(); out = []
    for _ in range(n):
        t = st.u16(); c = st.u32()
        if c >= 0x2000: raise ValueError('attr count too large')
        out.append((t, [st.u32() for _ in range(c)]))
    return hdr, out

def parse_state(st):
    """TFDState::Load 0x8B1989C0: u16 tag; (tag-2) B hdr (6 B: u16 1, u16 state_id, u16 x); Attributliste"""
    tag = st.u16(); hdr = st.rd(tag - 2)
    sid = struct.unpack_from('<H', hdr, 2)[0] if len(hdr) >= 4 else None
    ah, attrs = parse_attrs(st)
    return dict(hdr=hdr.hex(), state_id=sid, attrs=attrs)

def parse_module(st):
    """TFDModule::Load 0x8B1983CC"""
    tag = st.u16(); hdr = st.rd(tag - 2)
    n_states_hdr, handle = struct.unpack_from('<II', hdr, 2)
    flag_always = hdr[10] if len(hdr) > 10 else None
    nl = st.u8(); name = st.rd(nl).rstrip(b'\0').decode('latin1')
    ns = st.u32(); states = [parse_state(st) for _ in range(ns)]
    mid = st.u32(); nb = st.u32(); blobs = []
    for _ in range(nb):
        t = st.u32(); sz = st.u32(); blobs.append((t, st.rd(sz)))
    mh, mattrs = parse_attrs(st)
    return dict(name=name, hdr=hdr.hex(), n_states_hdr=n_states_hdr, handle=handle, flag_always=flag_always,
                states=states, plugin_id=mid, plugin=plugin_name(mid), blobs=blobs, attrs=mattrs)

def parse_group(st):
    """TFDGroup::Load 0x8B197310: u16 tag; (tag-2) B hdr (15 B: u16 1, u32 nmod, u32 gid, u8 type, u16 project, ..);
       u8 namelen; name; u32 nmod; Module"""
    tag = st.u16(); hdr = st.rd(tag - 2)
    nmod_hdr, gid = struct.unpack_from('<II', hdr, 2)
    gtype = hdr[10]; proj = struct.unpack_from('<H', hdr, 11)[0]
    nl = st.u8(); name = st.rd(nl).rstrip(b'\0').decode('latin1')
    nm = st.u32()
    mods = [parse_module(st) for _ in range(nm)]
    return dict(name=name, hdr=hdr.hex(), gid=gid, gtype=gtype, project=proj, nmod_hdr=nmod_hdr, mods=mods)

def parse_all(mem, base_va=0x4BE41000):
    files = []; st = S(mem)
    while st.p + 26 <= len(mem):
        start = st.p; h = st.rd(26)
        if h[:3] != b'TSE':
            if h[:3] == b'END' or not any(h): break
            files.append(dict(offset=start, error='no TSE magic')); break
        typ = h[3]; hl, ver = struct.unpack_from('<HI', h, 4); ts = struct.unpack_from('<I', h, 10)[0]
        pid, pad, ln, chk = struct.unpack_from('<HHII', h, 14)
        f = dict(offset=start, va=base_va + start, type=typ, typename=FILE_TYPES.get(typ, '?'), hdrlen=hl, version=ver,
                 timestamp=ts, project_id=pid, padding=pad, length=ln, checksum=chk, groups=[], raw=None)
        if hl != 0x1a: f['error'] = 'header len != 26'
        try:
            if typ in (0, 1, 2, 5):
                ng = st.u32()
                for _ in range(ng): f['groups'].append(parse_group(st))
                f['end_ok'] = (st.p == start + ln - pad) or (st.p == start + ln)
                f['parsed_end'] = st.p
            else:
                f['raw'] = mem[st.p:start + ln]
        except Exception as e:
            f['error'] = f'{type(e).__name__}: {e} at {st.p:#x}'
        files.append(f)
        if ln == 0: break
        st.p = start + ln
    return files

# ----------------------------------------------------------------------------- Plugin-Blobs
FULLMASK = {1: 0xff, 2: 0xffff, 3: 0xffffff, 4: 0xffffffff}

def decode_regtable(blob, nstates_mod):
    """TTFDRegTableFW::Load 0x8B192A0C. Rueckgabe: dict(mode,nstates,entries=[{...}])"""
    s = S(blob); mode = s.u32(); nst = s.u32(); ne = s.u32()
    entries = []
    for _ in range(ne):
        hd = s.rd(13)
        etype, asz, vsz = hd[0], hd[1], hd[2]
        base = (hd[3] << 24) | (hd[4] << 16) | (hd[5] << 8)   # pre-hook 0x8B18B328
        n = struct.unpack_from('<I', hd, 9)[0]
        addrs = s.rd(asz * n)
        nmask = n * (nst if mode == 1 else 1)
        masks = s.rd(vsz * nmask)
        vals = s.rd(vsz * n * nst)
        regs = []
        for i in range(n):
            a = int.from_bytes(addrs[i * asz:(i + 1) * asz], 'little')  # addr byte(s); writer nutzt lbu (1 Byte)
            addr = base + a * vsz                                       # Writer: base + idx*width
            per_state = []
            for sidx in range(nst):
                mi = (i * nst + sidx) if mode == 1 else i
                m = int.from_bytes(masks[mi * vsz:(mi + 1) * vsz], 'big')
                v = int.from_bytes(vals[(i * nst + sidx) * vsz:(i * nst + sidx + 1) * vsz], 'big')
                per_state.append((m, v))
            regs.append(dict(addr=addr, idx=a, per_state=per_state))
        entries.append(dict(etype=etype, asz=asz, vsz=vsz, base=base, hdr=hd.hex(), n=n, regs=regs))
    return dict(mode=mode, nstates=nst, entries=entries, consumed=s.p, size=len(blob))

def decode_equtable(blob):
    """TTFDEquTable::Load 0x8B18DD20"""
    s = S(blob); w0 = s.u32(); nrows = s.u32(); nfields = s.u32()
    fields = []
    for _ in range(nfields):
        kind = s.u8(); width = s.u16(); ln = s.u16()
        info = {}
        if kind == 2:      # TTFDFieldReg::Load 0x8B18D7C4: u8 n, n Bytes, u32, (u32?)
            n = s.u8(); info['reg'] = s.rd(n).hex(); info['w1'] = s.u32()
            # Restlaenge des Feldes: ln deckt Payload ab
        elif kind == 9:    # TTFDFieldAttr: u16 attr type
            info['attr_type'] = s.u16()
        elif kind == 8:    # TTFDFieldState: u32
            info['state'] = s.u32()
        fields.append(dict(kind=kind, width=width, len=ln, **info))
    rowlen = sum(f['width'] for f in fields)
    rows = [s.rd(rowlen) for _ in range(nrows)]
    return dict(w0=w0, nrows=nrows, fields=fields, rows=rows, consumed=s.p, size=len(blob))

def decode_memory(blob):
    """TTFDMemoryFW::Load 0x8B1916E4: u32 n; n x {u32 size, raw}. Apply 0x8B189814: Magic 'G', Header 16 B,
       dann 16-B-Deskriptoren {u16 id, u8 type, u8 x, u32 a, u32 b, u32 c} -> Puffer werden zur Laufzeit
       vom Memory-Manager (0x8BAC1A90) alloziert; c sieht nach kumulativem Offset|Flags aus (Einheit unsicher)."""
    s = S(blob); n = s.u32(); parts = []
    for _ in range(n):
        sz = s.u32(); raw = s.rd(sz); ents = []
        if sz >= 0x20 and raw[0] == 0x47:
            for o in range(0x10, sz - 15, 16):
                idv = int.from_bytes(raw[o:o + 2], 'big'); typ, x = raw[o + 2], raw[o + 3]
                a, b, c = struct.unpack_from('<III', raw, o + 4)
                ents.append(dict(id=idv, type=typ, x=x, a=a, b=b, c=c))
        parts.append(dict(raw=raw, ents=ents))
    return dict(parts=parts, consumed=s.p, size=len(blob))

def decode_polyscalar(blob):
    s = S(blob); n = s.u32(); parts = []
    for _ in range(n):
        sz = s.u32(); mode = s.u8(); coef = s.rd(sz - 1)
        parts.append(dict(mode=mode, ncoef=len(coef) // 4, coef=coef))
    return dict(parts=parts, consumed=s.p, size=len(blob))

def words_in_mem_ranges(raw):
    hits = []
    for i in range(0, len(raw) - 3, 4):
        v = struct.unpack_from('<I', raw, i)[0]
        if 0x40000000 <= v <= 0x7FFFFFFF: hits.append((i, v))
    return hits

# ----------------------------------------------------------------------------- Ausgabe
def attr_str(t, vals):
    return f'{ATTR_NAMES.get(t, "attr_%x" % t)}={",".join("%#x" % v for v in vals)}'

def state_match(state, filt):
    """Nachbildung von TFDAttrProp::Match 0x8B19506C. filt: {type: set(values)}.
       Rueckgabe (ok, unknown_types). Attributtypen, die im Filter fehlen, gelten als 'unbekannt' (bedingt)."""
    unknown = []
    for t, vals in state['attrs']:
        if t == 0: continue
        if not vals: return False, unknown
        if t in filt:
            if not (set(vals) & filt[t]): return False, unknown
        else:
            unknown.append(t)
    return True, unknown

def dump_module_regs(m, sel_states, out, mark=True, stats=None):
    """sel_states: Liste (state_index, state) -> Registerliste fuer diese States"""
    for t, blob in m['blobs']:
        if m['plugin'] == 'RegTableFW':
            rt = decode_regtable(blob, len(m['states']))
            if rt['consumed'] != rt['size']: out.append(f'      !! RegTable-Blob nicht vollstaendig geparst ({rt["consumed"]}/{rt["size"]})')
            for e in rt['entries']:
                if e['etype'] != 6: out.append(f'      !! unbekannter Entry-Typ {e["etype"]} hdr={e["hdr"]}')
                for r in e['regs']:
                    for sidx, st_ in sel_states:
                        if sidx >= rt['nstates']: continue
                        mask, val = r['per_state'][sidx]
                        width = e['vsz'] * 8
                        op = 'WR' if mask == FULLMASK.get(e['vsz'], -1) else 'RMW'
                        marks = []
                        reg = region(r['addr'])
                        if reg: marks.append(f'ADDR-OUTSIDE({reg})')
                        lm = looks_like_mem(val)
                        if lm: marks.append(lm)
                        if stats is not None:
                            stats['addr'][(r['addr'] >> 24)] += 1; stats['n'] += 1
                        out.append(f'      st{sidx:<3d} {op}{width:<2d} {r["addr"]:#010x} mask={mask:#0{e["vsz"]*2+2}x} val={val:#0{e["vsz"]*2+2}x}'
                                   + (('   <-- ' + ' '.join(marks)) if marks else ''))
        elif m['plugin'] == 'EquTable':
            eq = decode_equtable(blob)
            out.append(f'      EquTable: rows={eq["nrows"]} fields={[(f["kind"], f["width"], f.get("attr_type"), f.get("reg")) for f in eq["fields"]]} '
                       f'parsed={eq["consumed"]}/{eq["size"]}')
            for i, row in enumerate(eq['rows'][:8]): out.append(f'        row{i}: {row.hex()}')
            if eq['nrows'] > 8: out.append(f'        ... ({eq["nrows"] - 8} weitere Zeilen)')
        elif m['plugin'] == 'MemoryFW':
            mm = decode_memory(blob)
            selidx = {i for i, _ in sel_states}
            for i, p in enumerate(mm['parts']):
                if i not in selidx: continue
                out.append(f'      st{i:<3d} MemoryFW Deskriptoren ({len(p["raw"])} B, {len(p["ents"])} Eintraege) '
                           f'<-- Pufferlayout (DMA); Adressen werden zur Laufzeit alloziert')
                for e in p['ents'][:40]:
                    out.append(f'        id={e["id"]:#06x} type={e["type"]} x={e["x"]:#04x} a={e["a"]:#010x} b={e["b"]:#010x} c={e["c"]:#010x}')
                if len(p['ents']) > 40: out.append(f'        ... ({len(p["ents"]) - 40} weitere)')
        elif m['plugin'] == 'PolyScalarFW':
            ps = decode_polyscalar(blob)
            out.append(f'      PolyScalar LUT: {[(p["mode"], p["ncoef"]) for p in ps["parts"]]} (Koeffizienten, kein direkter Registerwrite im Load)')
        else:
            hits = words_in_mem_ranges(blob)
            out.append(f'      {m["plugin"]} raw blob {len(blob)} B type={t:#x} head={blob[:16].hex()}'
                       + (f'   <-- enthaelt DRAM-aehnliche Worte {[hex(v) for _, v in hits][:8]}' if hits else ''))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=os.path.join(os.path.dirname(__file__), '..', 'analyse', 'tse', 'board'))
    ap.add_argument('--project', default='0x0030')
    ap.add_argument('--all', action='store_true', help='alles ausgeben (alle States, alle Register)')
    ap.add_argument('--hdmi', action='store_true', help='nur States, die zu einem HDMI-Filter passen')
    ap.add_argument('--source', type=int, default=None, help='kSourceId (3..6 = HDMI1..4); Default: alle vier')
    ap.add_argument('--signal', default='0x20003', help='attr2-Wert (Signal-ID), "" = offen lassen')
    ap.add_argument('--attr', action='append', default=[], help='zusaetzliches Filterattribut TYPE=VAL (hex)')
    ap.add_argument('--json', default=None)
    ap.add_argument('--files', default=None, help='Kommagetrennte Dateiliste statt Default-Reihenfolge')
    a = ap.parse_args()

    names = a.files.split(',') if a.files else ['database.TSE', 'pq_custom.TSE', 'projecttable.TSE', f'ProjectID_{a.project}.TSE']
    mem = b''; layout = []
    for n in names:
        d = open(os.path.join(a.dir, n), 'rb').read(); layout.append((n, 0x4BE41000 + len(mem), len(d))); mem += d
    files = parse_all(mem)

    out = []
    out.append('# TSE-Speicherabbild (konkateniert wie U-Boot):')
    for n, va, ln in layout: out.append(f'#   {n:24s} ARM-phys {va:#010x} (MIPS {va + 0x40000000:#010x}) {ln} B')
    filt = {}
    if a.hdmi:
        filt[1] = {SOURCE_ATTR[a.source]} if a.source else set(HDMI_ATTR1)
        if a.signal: filt[2] = {int(a.signal, 16)}
        for kv in a.attr:
            k, v = kv.split('='); filt.setdefault(int(k, 16), set()).add(int(v, 16))
        out.append('# HDMI-Filter: ' + ', '.join(f'{ATTR_NAMES.get(k, "attr_%x" % k)} in {sorted(map(hex, v))}' for k, v in filt.items()))
        out.append('# States mit Attributtypen ausserhalb des Filters werden als BEDINGT gelistet (Match haengt von Panel-/Projekt-/Modus-Attributen ab).')

    stats = dict(addr=Counter(), n=0); nmods = 0; nmods_hdr = 0
    for f in files:
        out.append(f'\n== Datei @{f["offset"]:#x} (ARM {f["va"]:#010x}) type={f["type"]} {f["typename"]} ver={f.get("version", 0):#x} '
                   f'ts={f.get("timestamp", 0):#x} pid={f.get("project_id", 0):#x} pad={f.get("padding")} len={f.get("length", 0):#x}'
                   + (f'  !! {f["error"]}' if f.get('error') else '') + ('' if f.get('end_ok', True) else '  !! Endposition passt nicht'))
        if f.get('raw') is not None:
            out.append(f'   (opaker Tabellentyp, {len(f["raw"])} B, head={f["raw"][:24].hex()})'); continue
        for g in f['groups']:
            nmods += len(g['mods']); nmods_hdr += g['nmod_hdr']
            out.append(f'-- Gruppe {g["name"]!r} id={g["gid"]:#x} type={g["gtype"]}({GROUP_TYPES.get(g["gtype"], "?")}) project={g["project"]:#x} '
                       f'module={len(g["mods"])} (hdr-feld2 {g["nmod_hdr"]})')
            for m in g['mods']:
                dma = any(k in m['name'].upper() for k in DMA_KEYWORDS)
                head = (f'   Modul {m["name"]!r} handle={m["handle"]:#x} plugin={m["plugin"]}({m["plugin_id"]:#x}) states={len(m["states"])} '
                        f'always={m["flag_always"]} blobs={[(hex(t), len(b)) for t, b in m["blobs"]]}'
                        + ('   <-- DMA/Puffer/Write-back-Modul (Name)' if dma else ''))
                if a.hdmi:
                    sel = []
                    for i, st_ in enumerate(m['states']):
                        ok, unk = state_match(st_, filt)
                        if ok: sel.append((i, st_, unk))
                    if not sel: continue
                    out.append(head)
                    for i, st_, unk in sel:
                        cond = (' BEDINGT[' + ','.join(ATTR_NAMES.get(t, 'attr_%x' % t) for t in unk) + ']') if unk else ''
                        out.append(f'     State {i} id={st_["state_id"]:#x}{cond}: ' + '; '.join(attr_str(t, v) for t, v in st_['attrs']))
                    dump_module_regs(m, [(i, s_) for i, s_, _ in sel], out, stats=stats)
                elif a.all:
                    out.append(head)
                    for i, st_ in enumerate(m['states']):
                        out.append(f'     State {i} id={st_["state_id"]:#x}: ' + '; '.join(attr_str(t, v) for t, v in st_['attrs']))
                    dump_module_regs(m, list(enumerate(m['states'])), out, stats=stats)
                else:
                    out.append(head)
    out.append(f'\n# Module gesamt: {nmods} (Header-Summe {nmods_hdr}); Registerwrites gelistet: {stats["n"]}; '
               f'Adress-Top-Bytes: {dict((hex(k), v) for k, v in sorted(stats["addr"].items()))}')
    print('\n'.join(out))
    if a.json:
        def conv(o):
            if isinstance(o, bytes): return o.hex()
            raise TypeError
        json.dump(files, open(a.json, 'w'), default=conv, indent=1)

if __name__ == '__main__':
    main()
