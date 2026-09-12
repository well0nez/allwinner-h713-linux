#!/bin/bash
# oops_resolve.sh SYMBOL+0xOFF [SYMBOL+0xOFF ...] -- Umgebung eines Oops-pc/lr im vmlinux disassemblieren.
# Kernelbaum: mainline/build/linux-6.18.38-102233d4... (laufender Kernel, Build Tue Sep 1 22:21:07 UTC 2026).
K=$(ls -d /opt/Projekte/h713/mainline/build/linux-6.18.38-102233d4*/ | head -1)
OD=$(which llvm-objdump llvm-objdump-18 aarch64-linux-gnu-objdump 2>/dev/null | head -1)
for spec in "$@"; do
  sym=${spec%%+*}; off=${spec#*+}; [ "$off" = "$spec" ] && off=0
  base=$(nm "$K/vmlinux" | awk -v s="$sym" '$3==s {print $1; exit}')
  [ -z "$base" ] && { echo "$sym: nicht im vmlinux"; continue; }
  addr=$(printf '%x' $((0x$base + off)))
  echo "== $spec -> 0x$addr (Basis 0x$base)"
  $OD -d --no-show-raw-insn --start-address=0x$(printf '%x' $((0x$addr - 0x40))) --stop-address=0x$(printf '%x' $((0x$addr + 0x30))) "$K/vmlinux" | sed "s/^ *$addr:/>>> $addr:/" | tail -n +7
done
