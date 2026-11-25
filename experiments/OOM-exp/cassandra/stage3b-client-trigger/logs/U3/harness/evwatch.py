#!/usr/bin/env python3
"""U3 3-b confirm (2026-11-24): evwatch.py <node.out> <out> <pid>: timestamps (epoch ms, local clock) every node.out line that
mentions OutOfMemoryError, a heap dump or the shipped kill -9, as it appears; polls every 0.2 s until <pid> is gone, then 5 s more."""
import os, re, sys, time
src, dst, pid = sys.argv[1], sys.argv[2], int(sys.argv[3])
pat = re.compile(r'OutOfMemoryError|Dumping heap|Heap dump file created|Executing /bin/sh|OnOutOfMemoryError')
out = open(dst, 'a', buffering=1); pos = 0; buf = b''; gone_at = None
def alive(p):
    try:
        os.kill(p, 0); return True
    except OSError:
        return False
while True:
    try:
        with open(src, 'rb') as f:
            f.seek(pos); data = f.read(); pos += len(data)
    except FileNotFoundError:
        data = b''
    buf += data
    *lines, buf = buf.split(b'\n')
    now = int(time.time() * 1000)
    for l in lines:
        s = l.decode('utf-8', 'replace')
        if pat.search(s) and 'CompileCommand' not in s:
            out.write('%d %s\n' % (now, s[:300]))
    if gone_at is None and not alive(pid):
        gone_at = time.time(); out.write('%d # pid %d gone\n' % (now, pid))
    if gone_at is not None and time.time() - gone_at > 5:
        break
    time.sleep(0.2)
