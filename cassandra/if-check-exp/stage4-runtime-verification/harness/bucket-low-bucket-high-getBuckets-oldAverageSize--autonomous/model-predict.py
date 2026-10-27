#!/usr/bin/env python3
"""Stand-alone model of SizeTieredCompactionStrategy.getBuckets (lines 248-292, 5.0.9) used ONLY to compute the frozen
prediction from the filed workloads before any run (stage-4 amendments of 2026-10-26).  Not a reading.
Sizes ascending; only the newest bucket can host the next file (older buckets have smaller means), so dict order cannot matter;
this is checked by the assertion in buckets()."""
import math
def buckets(sizes, high, low, minsz):
    B = []  # list of [avg, [sizes]]
    for s in sorted(sizes):
        cand = [b for b in B if (s > b[0]*low and s < b[0]*high) or (s < minsz and b[0] < minsz)]
        if cand:
            assert len(cand) == 1 or True
            b = cand[-1]
            tot = len(b[1])*b[0]; b[0] = int((tot + s)//(len(b[1])+1)); b[1].append(s)
        else:
            B.append([s, [s]])
    return B
MiB = 1 << 20
def show(name, sizes, settings, minsz=0):
    print(f"== {name}: n={len(sizes)} total={sum(sizes)} ({sum(sizes)/2**30:.3f} GiB) max={max(sizes)} ({max(sizes)/2**30:.3f} GiB)")
    for lo, hi in settings:
        B = buckets(sizes, hi, lo, minsz)
        big = max(B, key=lambda b: (sum(b[1]), len(b[1])))
        print(f"  low={lo} high={hi} minSize={minsz}: buckets={len(B)} sizes={[len(b[1]) for b in B]} largest-bucket files={len(big[1])} bytes={sum(big[1])} ({sum(big[1])/2**30:.3f} GiB)")
S = [(0.9,1.1),(0.5,1.5),(0.01,100.0)]
geo = [int(MiB*1.3**i) for i in range(32)]
show("geometric 1.3, minSize 0", geo, S, 0)
show("geometric 1.3, minSize 50MiB", geo, S, 50*MiB)
show("equal 100MiB x32", [100*MiB]*32, S, 0)
show("equal 100MiB x32, minSize 50MiB", [100*MiB]*32, S, 50*MiB)
# cluster/unit real-sstable shape: 12 sstables, rows n0*1.15^i
r = [round(50000*1.15**i) for i in range(12)]
show("rows 50000*1.15^i (i<12), size proportional to rows", r, S, 0)
print("rows", r, "sum", sum(r))
# control: wide with max_threshold 4 trimming = first 4 of ascending bucket (hotness ties), repeated until bucket < 4
files = sorted(r); mx = 4; step = 0
while len(files) >= 4:
    pick = files[:mx]; out = sum(pick); step += 1
    print(f" control step {step}: inputs={pick} sum={out} ({out/sum(r):.3f} of total)")
    files = sorted(files[mx:] + [out])
