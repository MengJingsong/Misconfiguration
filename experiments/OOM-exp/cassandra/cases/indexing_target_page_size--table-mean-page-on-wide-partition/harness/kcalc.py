#!/usr/bin/env python3
"""B20 offline K: kcalc.py <sstablemetadata output file> [...]  (one file per canonical sstable of ks.t)
Re-implements ColumnFamilyStore.getMeanPartitionSize / getMeanEstimatedCellPerPartitionCount (:3110-3134) and
SecondaryIndexManager.calculateIndexingPageSize (:1149-1170) from the 'Partition Size' and 'Column Count'
histograms printed by tools/bin/sstablemetadata (bucket offset | count). EstimatedHistogram.mean() = ceil of the
count-weighted mean of bucket offsets. regularColumns = 1 (v)."""
import math, re, sys
ROW = re.compile(r'^\s+(\d+)\b[^|]*\|\s+(\d+)\s+\(')
def hist(lines, start, stop):
    out = []; on = False
    for l in lines:
        if l.startswith(start): on = True; continue
        if on and l.startswith(stop): break
        if on:
            m = ROW.match(l)
            if m: out.append((int(m.group(1)), int(m.group(2))))
    return out
def mean(h):
    n = sum(c for _, c in h); return (math.ceil(sum(o * c for o, c in h) / n) if n else 0), n
sum_p = 0; cnt_p = 0; sum_c = 0; cnt_c = 0
for f in sys.argv[1:]:
    L = open(f, errors='replace').read().splitlines()
    ps = hist(L, 'Partition Size', 'Column Count'); cc = hist(L, 'Column Count', 'Local token space coverage')
    mp, np_ = mean(ps); mc, nc = mean(cc)
    print(f'{f}: partitions={np_} meanPartitionSize(ceil)={mp} cellHistCount={nc} meanCells(ceil)={mc} '
          f'psBuckets={ps} ccBuckets={cc}')
    sum_p += mp * np_; cnt_p += np_; sum_c += mc * nc; cnt_c += nc
meanPartitionSize = sum_p * 1.0 / cnt_p if cnt_p else 0
meanCells = int(sum_c // cnt_c) if cnt_c else 0
cols = 1
if meanPartitionSize <= 0 or meanCells <= 0:
    K = 10000; mrp = None; mrs = None
else:
    mrp = meanCells // cols
    mrs = meanPartitionSize / mrp
    K = int(max(1, min(10000, 32 * 1024 * 1024 / mrs)))
print(f'RESULT meanPartitionSize={meanPartitionSize:.3f} meanCells={meanCells} meanRowsPerPartition={mrp} '
      f'meanRowSize={mrs} K={K}')
