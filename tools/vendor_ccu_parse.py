from elftools.elf.elffile import ELFFile
import struct,sys
f=open('/opt/archive/HY310/extracted/vmlinux.elf','rb'); e=ELFFile(f)
secs=[(s['sh_addr'],s['sh_size'],s['sh_offset'],s.name) for s in e.iter_sections() if s['sh_type']!='SHT_NOBITS' and s['sh_addr']]
def rd(va,n):
    for a,sz,off,nm in secs:
        if a<=va<a+sz:
            f.seek(off+va-a); return f.read(n)
    return None
def u32(va): return struct.unpack('<I',rd(va,4))[0]
def u16(va): return struct.unpack('<H',rd(va,2))[0]
def u8(va): return rd(va,1)[0]
def cstr(va):
    d=rd(va,64); return d.split(b'\0')[0].decode()
syms={}; rsyms={}
for l in open('/tmp/claude-1000/-opt-Projekte-h713/9d98dd00-4e0a-4da0-a529-d30239b5945f/scratchpad/kallsyms.utf8'):
    p=l.split()
    if len(p)>=3: syms[p[2]]=int(p[0],16); rsyms.setdefault(int(p[0],16),p[2])
ops={syms[n]:n for n in ['ccu_gate_ops','ccu_mux_ops','ccu_mp_ops','ccu_div_ops','ccu_nm_ops','ccu_nk_ops','ccu_nkm_ops','ccu_nkmp_ops','ccu_phase_ops','clk_fixed_rate_ops','clk_fixed_factor_ops','ccu_mp_mmc_ops']}
# common: base0 reg4 lockreg6 prediv8 features12 lock16 ?20 hw24(core,clk,init32)
ENABLE_OFF={'ccu_gate_ops':-8,'ccu_mux_ops':-28,'ccu_mp_ops':-72,'ccu_div_ops':-48}
def parse_common(c):
    init=u32(c+32); name=cstr(u32(init)); op=u32(init+4); opn=ops.get(op,hex(op))
    reg=u16(c+4); lockreg=u16(c+6); prediv=u32(c+8); feat=u32(c+12)
    npar=u8(init+20); pn=u32(init+8); pd=u32(init+12); ph=u32(init+16); flags=u32(init+24)
    parents=[]
    for i in range(npar):
        if pn: parents.append(cstr(u32(pn+4*i)))
        elif pd:
            # clk_parent_data{index(4) name fw_name hw}? 5.4: {const struct clk_hw *hw; const char *fw_name; const char *name; int index}
            hw=u32(pd+16*i); fw=u32(pd+16*i+4); nm=u32(pd+16*i+8)
            parents.append(cstr(fw) if fw else (cstr(nm) if nm else ('hw@%x'%hw)))
        elif ph:
            hwp=u32(ph+4*i); parents.append(cstr(u32(u32(hwp+8))))
    d={'name':name,'ops':opn,'reg':reg,'lock_reg':lockreg,'prediv':prediv,'feat':feat,'parents':parents,'flags':flags,'addr':c}
    eo=ENABLE_OFF.get(opn)
    if eo is not None: d['enable']=u32(c+eo)
    s=c+eo if eo is not None else c
    if opn=='ccu_mux_ops':
        d['mux']=(u8(c-24),u8(c-23))  # mux internal at common-24
    if opn=='ccu_mp_ops':
        d['m']=(u8(c-68),u8(c-67)); d['p']=(u8(c-48),u8(c-47)); d['mux']=(u8(c-28),u8(c-27)); d['post']=u32(c-4)
    if opn=='ccu_div_ops':
        d['div']=(u8(c-44),u8(c-43),u32(c-40)); d['mux']=(u8(c-24),u8(c-23))
    if opn=='clk_fixed_rate_ops':
        pass
    return d
def parse_desc(dname):
    da=syms[dname]; clks=u32(da); n=u32(da+4); hwc=u32(da+8); rst=u32(da+12); nr=u32(da+16)
    print('==',dname,'@%x clks=%x n=%d hw_clks=%x resets=%x nresets=%d'%(da,clks,n,hwc,rst,nr))
    byaddr={}
    for i in range(n):
        c=u32(clks+4*i); d=parse_common(c); byaddr[c+24]=d
        ex=''
        if 'enable' in d: ex+=' enable=0x%08x'%d['enable']
        for k in ('mux','m','p','div','post'):
            if k in d: ex+=' %s=%s'%(k,d[k])
        print('  [%2d] %-22s %-18s reg=0x%03x%s parents=%s flags=0x%x feat=0x%x sym=%s'%(i,d['name'],d['ops'],d['reg'],ex,d['parents'],d['flags'],d['feat'],rsyms.get(c+ENABLE_OFF.get(d['ops'],0),'?')))
    if hwc:
        num=u32(hwc); print('  hw_clks num=%d'%num)
        for i in range(num):
            h=u32(hwc+4+4*i)
            if h==0: print('    idx %2d: <none>'%i); continue
            if h in byaddr: print('    idx %2d: %s'%(i,byaddr[h]['name']))
            else:
                init=u32(h+8); print('    idx %2d: %s (non-ccu, ops=%s, hw@%x)'%(i,cstr(u32(init)),ops.get(u32(init+4),hex(u32(init+4))),h))
    if rst:
        for i in range(nr):
            print('    reset %2d: reg=0x%03x bit=0x%08x'%(i,u16(rst+8*i),u32(rst+8*i+4)))
for d in sys.argv[1:]: parse_desc(d)
