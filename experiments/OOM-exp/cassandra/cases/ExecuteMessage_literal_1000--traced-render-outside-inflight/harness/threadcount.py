#!/usr/bin/env python3
"""Read `jcmd <pid> Thread.print` on stdin; print: ntr ntr_trace in_hex in_string_init in_concat ntr_runnable
ntr = Native-Transport-Requests threads; ntr_trace = those with ExecuteMessage.traceQuery in the stack;
in_hex / in_string_init / in_concat = of those, the top-most matching frame is Hex.bytesToHex /
String.<init> or StringUTF16.compress / StringConcatHelper (or the concat bootstrap)."""
import sys
blocks = sys.stdin.read().split('\n\n')
ntr = tr = hx = si = cc = run = 0
for b in blocks:
    if not b.startswith('"Native-Transport-Requests'): continue
    ntr += 1
    if 'java.lang.Thread.State: RUNNABLE' in b: run += 1
    if 'ExecuteMessage.traceQuery' not in b: continue
    tr += 1
    for line in b.splitlines():
        line = line.strip()
        if not line.startswith('at '): continue
        if 'Hex.bytesToHex' in line: hx += 1; break
        if 'java.lang.String.<init>' in line or 'StringUTF16.compress' in line or 'Hex.wrapCharArray' in line: si += 1; break
        if 'StringConcatHelper' in line or 'StringConcatFactory' in line: cc += 1; break
        if 'ExecuteMessage.traceQuery' in line: break
print(ntr, tr, hx, si, cc, run)
