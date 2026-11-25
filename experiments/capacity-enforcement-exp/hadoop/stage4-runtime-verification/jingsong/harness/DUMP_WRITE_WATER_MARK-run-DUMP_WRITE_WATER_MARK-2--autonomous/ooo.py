#!/usr/bin/env python3
"""B3c workload: out-of-order gap data G at offsets [1 MiB, 1 MiB + G), fsync, hold 60 s, then fill [0, 1 MiB).
Usage: ooo.py <file-on-nfs-mount> <G bytes> <reference-copy path>. Content is a deterministic per-block pattern."""
import os, sys, time, random
path, G, ref = sys.argv[1], int(sys.argv[2]), sys.argv[3]
B = 1 << 20
def block(k, n):            # deterministic content of the block that starts at offset k*B
    return random.Random(k).randbytes(n)
def log(*a): print(time.strftime('%F %T'), *a, flush=True)
fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o644)
rf = open(ref, 'wb')
off, k = B, 1
while off < B + G:
    n = min(B, B + G - off)
    d = block(k, n)
    assert os.pwrite(fd, d, off) == n
    rf.seek(off); rf.write(d)
    off += n; k += 1
log('PWRITES-DONE', k - 1, 'blocks', G, 'bytes from offset', B)
os.fsync(fd)
log('GAP-SENT')
time.sleep(60)
d = block(0, B)
assert os.pwrite(fd, d, 0) == B
rf.seek(0); rf.write(d); rf.close()
os.fsync(fd)
os.close(fd)
log('FILLED-CLOSED total', B + G)
