#!/usr/bin/env python3
"""Read `jcmd <pid> Thread.print` on stdin; print (B11's six fields, then R12's):
ntr ntr_trace in_hex in_string_init in_concat ntr_runnable st_phase aw_phase
ntr = Native-Transport-Requests threads; ntr_trace = those with ExecuteMessage.traceQuery in the stack;
in_hex / in_string_init / in_concat = of those, the top-most matching frame is Hex.bytesToHex /
String.<init> or StringUTF16.compress / StringConcatHelper (or the concat bootstrap).
st_phase = the ScheduledTasks thread running MonitoringTask: pop-hex | pop-fmt | pop (popOperations, top frame in
Hex.bytesToHex / String.format or other) | msg (getLogMessage) | log (logback call) | mon (other MonitoringTask) | idle.
aw_phase = AsyncAppender-Worker: layout | encode | write | idle."""
import sys
blocks = sys.stdin.read().split('\n\n')
ntr = tr = hx = si = cc = run = 0
st = 'idle'; aw = 'idle'
for b in blocks:
    if b.startswith('"ScheduledTasks') and 'MonitoringTask' in b:
        fr = [l.strip() for l in b.splitlines() if l.strip().startswith('at ')]
        top = ' '.join(fr[:12])
        if 'popOperations' in b:
            pre = ' '.join(fr[:[i for i, l in enumerate(fr) if 'popOperations' in l][0]])
            st = 'pop-hex' if 'Hex.bytesToHex' in pre else ('pop-fmt' if 'String.format' in pre or 'Formatter' in pre else 'pop')
        elif 'getLogMessage' in b: st = 'msg'
        elif 'ch.qos.logback' in b or 'slf4j' in b: st = 'log'
        else: st = 'mon'
        continue
    if b.startswith('"AsyncAppender-Worker'):
        if 'PatternLayout' in b or 'Layout' in b and 'doLayout' in b: aw = 'layout'
        elif 'encode' in b: aw = 'encode'
        elif 'FileOutputStream' in b or 'writeBytes' in b or 'ResilientOutputStreamBase' in b: aw = 'write'
        continue
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
print(ntr, tr, hx, si, cc, run, st, aw)
