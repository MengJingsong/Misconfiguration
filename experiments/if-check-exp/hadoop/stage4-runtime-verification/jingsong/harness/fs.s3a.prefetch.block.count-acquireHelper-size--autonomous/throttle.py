#!/usr/bin/env python3
"""Replacement for `pv -q -L <rate>M > /dev/null` (case-file A5c): read stdin in 1 MiB chunks, hold <MiB/s>, discard.
Prints the byte count and elapsed seconds on exit (stdout)."""
import sys, time
rate = float(sys.argv[1]) * 1048576.0
inp = sys.stdin.buffer
total = 0
t0 = time.monotonic()
while True:
    b = inp.read(1048576)
    if not b:
        break
    total += len(b)
    ahead = total / rate - (time.monotonic() - t0)
    if ahead > 0:
        time.sleep(ahead)
print(f"bytes={total} seconds={time.monotonic() - t0:.1f}")
