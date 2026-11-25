#!/usr/bin/env python3
# B3c workload, as written in the case file, with flushed progress lines.
# Usage: ooo_write.py <path> <C> <N> <hold_seconds>
import os, sys, mmap, time
path, C, N, hold = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
buf = mmap.mmap(-1, C); buf.write(os.urandom(C))           # page-aligned buffer
fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_DIRECT, 0o644)
t0 = time.time()
print("START %.3f" % t0, flush=True)
for k, i in enumerate(range(N, 0, -1), 1):               # offsets N*C down to C: all out of order
    assert os.pwrite(fd, buf, i * C) == C
    if k % 500 == 0:
        print("PROGRESS %d writes %.1fs" % (k, time.time() - t0), flush=True)
print("HOLD after %d writes, %.1fs at %.3f" % (N, time.time() - t0, time.time()), flush=True)
time.sleep(hold)                                          # measure here; hole [0,C) still open
assert os.pwrite(fd, buf, 0) == C                         # fill the hole: write-back starts
os.close(fd)
print("DONE %.1fs at %.3f" % (time.time() - t0, time.time()), flush=True)
