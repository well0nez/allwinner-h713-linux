#!/usr/bin/env python3
"""mips-dis.py -- Mini-Dekoder fuer display.bin (MIPS32, im File wortweise
little-endian abgelegt, Basis 0x8B100000). Ersatz fuer das in doku/67 genannte,
nie vorhandene tools/mips/disasm.py. Kein IDA noetig.

  tools/mips-dis.py dis   0x8b19f7e8 40        Instruktionen ab Adresse
  tools/mips-dis.py refs  0x8b1f7afc ...       lui/addiu-Paare, die die Adresse bilden (+ Funktionsanfang)
  tools/mips-dis.py words 0x8b22d1c0 24        rohe Woerter
  tools/mips-dis.py callers 0x8b13d044         direkte jal-Aufrufer

Stock-Firmware: re/ida/IDA_hy310/display.bin.bak (md5 0d2191ca). Der Pfad ist
per --bin aenderbar. Sieht nur direkte lui/jal; vtable-Aufrufe nicht.
"""
import struct, sys, argparse

BASE = 0x8B100000
DEFAULT_BIN = '/opt/Projekte/h713/re/ida/IDA_hy310/display.bin.bak'
R = {0:'zero',1:'at',2:'v0',3:'v1',4:'a0',5:'a1',6:'a2',7:'a3',8:'t0',9:'t1',10:'t2',11:'t3',12:'t4',13:'t5',14:'t6',15:'t7',16:'s0',17:'s1',18:'s2',19:'s3',20:'s4',21:'s5',22:'s6',23:'s7',24:'t8',25:'t9',26:'k0',27:'k1',28:'gp',29:'sp',30:'fp',31:'ra'}

def load(path):
    b = open(path, 'rb').read()
    return [struct.unpack('<I', b[i:i+4])[0] for i in range(0, len(b)-3, 4)]

def d(a, w):
    op=w>>26; rs=(w>>21)&31; rt=(w>>16)&31; rd=(w>>11)&31; sa=(w>>6)&31; fn=w&63; imm=w&0xffff; s=imm-0x10000 if imm&0x8000 else imm
    br=lambda: hex(a+4+s*4)
    if op==0:
        if w==0: return 'nop'
        m={0x08:f'jr {R[rs]}',0x09:f'jalr {R[rs]}',0x21:f'addu {R[rd]},{R[rs]},{R[rt]}',0x23:f'subu {R[rd]},{R[rs]},{R[rt]}',0x25:(f'move {R[rd]},{R[rs]}' if rt==0 else f'or {R[rd]},{R[rs]},{R[rt]}'),0x24:f'and {R[rd]},{R[rs]},{R[rt]}',0x26:f'xor {R[rd]},{R[rs]},{R[rt]}',0x00:f'sll {R[rd]},{R[rt]},{sa}',0x02:f'srl {R[rd]},{R[rt]},{sa}',0x03:f'sra {R[rd]},{R[rt]},{sa}',0x2a:f'slt {R[rd]},{R[rs]},{R[rt]}',0x2b:f'sltu {R[rd]},{R[rs]},{R[rt]}',0x0a:f'movz {R[rd]},{R[rs]},{R[rt]}',0x0b:f'movn {R[rd]},{R[rs]},{R[rt]}',0x04:f'sllv {R[rd]},{R[rt]},{R[rs]}',0x06:f'srlv {R[rd]},{R[rt]},{R[rs]}',0x27:f'nor {R[rd]},{R[rs]},{R[rt]}'}
        return m.get(fn, f'special fn={fn:#x}')
    if op==0x1c: return {2:f'mul {R[rd]},{R[rs]},{R[rt]}'}.get(fn, f'special2 fn={fn:#x}')
    if op==0x1f:
        msb=rd; lsb=sa
        if fn==0: return f'ext {R[rt]},{R[rs]},{lsb},{msb+1}'
        if fn==4: return f'ins {R[rt]},{R[rs]},{lsb},{msb-lsb+1}'
        if fn==0x20: return {0x10:f'seb {R[rd]},{R[rt]}',0x18:f'seh {R[rd]},{R[rt]}'}.get(sa,'bshfl')
        return f'special3 fn={fn:#x}'
    if op==1: return {0:f'bltz {R[rs]},{br()}',1:f'bgez {R[rs]},{br()}',0x11:f'bgezal {R[rs]},{br()}'}.get(rt, f'regimm {rt}')
    m={0x02:f'j {hex(((w&0x3ffffff)<<2)|(a&0xf0000000))}',0x03:f'jal {hex(((w&0x3ffffff)<<2)|(a&0xf0000000))}',0x04:f'beq {R[rs]},{R[rt]},{br()}',0x05:f'bne {R[rs]},{R[rt]},{br()}',0x06:f'blez {R[rs]},{br()}',0x07:f'bgtz {R[rs]},{br()}',0x08:f'addi {R[rt]},{R[rs]},{s:#x}',0x09:(f'li {R[rt]},{s:#x}' if rs==0 else f'addiu {R[rt]},{R[rs]},{s:#x}'),0x0a:f'slti {R[rt]},{R[rs]},{s:#x}',0x0b:f'sltiu {R[rt]},{R[rs]},{imm:#x}',0x0c:f'andi {R[rt]},{R[rs]},{imm:#x}',0x0d:f'ori {R[rt]},{R[rs]},{imm:#x}',0x0e:f'xori {R[rt]},{R[rs]},{imm:#x}',0x0f:f'lui {R[rt]},{imm:#x}',0x14:f'beql {R[rs]},{R[rt]},{br()}',0x15:f'bnel {R[rs]},{R[rt]},{br()}',0x20:f'lb {R[rt]},{s:#x}({R[rs]})',0x21:f'lh {R[rt]},{s:#x}({R[rs]})',0x23:f'lw {R[rt]},{s:#x}({R[rs]})',0x24:f'lbu {R[rt]},{s:#x}({R[rs]})',0x25:f'lhu {R[rt]},{s:#x}({R[rs]})',0x28:f'sb {R[rt]},{s:#x}({R[rs]})',0x29:f'sh {R[rt]},{s:#x}({R[rs]})',0x2b:f'sw {R[rt]},{s:#x}({R[rs]})'}
    return m.get(op, f'op {op:#x}')

def dis(W, addr, n):
    i=(addr-BASE)//4
    for k in range(n):
        a=addr+4*k; w=W[i+k]; print(f'{a:#x}  {w:08x}  {d(a,w)}')

def fstart(W, addr):
    i=(addr-BASE)//4
    while i>0:
        w=W[i]
        if (w>>26)==9 and ((w>>21)&31)==29 and ((w>>16)&31)==29 and (w&0x8000): return BASE+4*i
        i-=1

def refs(W, target):
    hi=(target>>16)&0xffff; lo=target&0xffff
    hi_a=(hi+1)&0xffff if lo&0x8000 else hi
    out=[]
    for i,w in enumerate(W):
        op=w>>26
        if op in (9,0xd) and (w&0xffff)==lo:
            rs=(w>>21)&31; want = hi_a if op==9 else hi
            for k in range(1,12):
                if i-k<0: break
                p=W[i-k]
                if (p>>26)==0xf and ((p>>16)&31)==rs and (p&0xffff)==want: out.append(BASE+4*i); break
    return out

def callers(W, t):
    return [BASE+4*i for i,w in enumerate(W) if (w>>26)==3 and (((w&0x3ffffff)<<2)|0x80000000)==t]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--bin', default=DEFAULT_BIN)
    ap.add_argument('cmd'); ap.add_argument('args', nargs='*')
    a=ap.parse_args(); W=load(a.bin)
    if a.cmd=='dis': dis(W, int(a.args[0],16), int(a.args[1]) if len(a.args)>1 else 32)
    elif a.cmd=='refs':
        for t in a.args:
            rr=refs(W,int(t,16)); print(t,'refs:',[hex(x) for x in rr],'fstart:',[hex(fstart(W,x)) if fstart(W,x) else None for x in rr])
    elif a.cmd=='words':
        addr=int(a.args[0],16); n=int(a.args[1]) if len(a.args)>1 else 16; i=(addr-BASE)//4
        for k in range(n): print(f'{addr+4*k:#x}: {W[i+k]:08x}')
    elif a.cmd=='callers':
        for t in a.args: print(t,'callers:',[hex(x) for x in callers(W,int(t,16))])
    else: sys.exit('dis|refs|words|callers')

if __name__=='__main__': main()
