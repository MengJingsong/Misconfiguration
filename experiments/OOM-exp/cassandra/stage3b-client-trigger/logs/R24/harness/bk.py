#!/usr/bin/env python3
# R24: decode RfpJmx "recent=i:n ..." bucket indices of ReplicaFilteringProtectionRowsCachedPerQuery (DecayingEstimatedHistogramReservoir,
# considerZeroes = true: EstimatedHistogram.newOffsets(164, true)) into the bucket's upper value (K rounded up).   bk.py <rfpk.txt>
import re, sys
off = [0, 1]; last = 1
while len(off) < 165:
    nx = round(last * 1.2)
    if nx == last: nx += 1
    off.append(nx); last = nx
for line in open(sys.argv[1]):
    m = re.search(r'recent=(\S.*)$', line.strip())
    dec = ' '.join(f'{off[int(i)]}x{n}' for i, n in (p.split(':') for p in m.group(1).split())) if m and m.group(1) != '-' else '-'
    print(line.rstrip(), '| K buckets(value x count):', dec)
