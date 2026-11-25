#!/usr/bin/env python3
"""Endpoint per §2.7 with amendments A1/A2 (applied as in T2): OOM if the daemon died with OutOfMemoryError and oom_kill 0, OR the
first OutOfMemoryError (hprof creation) came inside the window with oom_kill 0 (death by the shipped kill -9 after the window).
usage: a2.py <analysis.txt> [window-s]"""
import re, sys
t = open(sys.argv[1]).read(); win = float(sys.argv[2]) if len(sys.argv) > 2 else 180.0
oomk = re.search(r'oom_kill=(\S+)', t); oomk = oomk.group(1) if oomk else '?'
m = re.search(r'OOM_INSTANT hprof created at t=([\d.]+) s', t)
msg = re.search(r"OOMMSG \['([^']+)'", t)
if t.startswith('RUN') and re.search(r'^OUTCOME OOM', t, re.M):
    print('A2OUTCOME OOM (daemon death in window)')
elif m and float(m.group(1)) < win and oomk == '0' and msg:
    print('A2OUTCOME OOM (first OutOfMemoryError at %s s, in window; %s)' % (m.group(1), msg.group(1)))
elif re.search(r'^OUTCOME invalid', t, re.M):
    print('A2OUTCOME invalid')
else:
    print('A2OUTCOME survived')
