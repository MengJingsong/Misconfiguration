#!/usr/bin/env python3
"""C9: D1 attribution at the direct-memory peak of each run (design §2.6): D1 = dMemoryUsed - d(chunk-cache pool size),
compared with dCount (java.nio direct buffer Count). usage: c9_d1.py <rundir>..."""
import csv, sys
M = 2 ** 20
for r in sys.argv[1:]:
    t = int(open(r + '/t_load.txt').read())
    rows = []
    for x in csv.DictReader(open(r + '/samples.csv')):
        try:
            rows.append({k: int(v) for k, v in x.items()})
        except (ValueError, TypeError):
            pass
    b = [x for x in rows if t - 10000 <= x['ms'] < t][-1]
    ld = [x for x in rows if x['ms'] >= t and x['direct_count'] >= 0]
    p = max(ld, key=lambda x: x['direct_used'])
    dpool = p['cc_size'] - b['cc_size']
    d1 = p['direct_used'] - b['direct_used'] - dpool
    name = r.rstrip('/').split('/')[-1]
    print(f"{name}: peak at load+{(p['ms'] - t) / 1000:.1f}s MemoryUsed {p['direct_used'] / M:.0f} MiB (TotalCapacity {p['direct_cap'] / M:.0f}) "
          f"dCount {p['direct_count'] - b['direct_count']}; pool size {p['cc_size'] / M:.0f} MiB (+{dpool / M:.0f}, overflow {p['cc_overflow'] / M:.0f}); "
          f"D1 = dUsed - dPool = {d1 / M:.0f} MiB = {d1 / 262144:.0f} x 256 KiB; A {p['read_active']} pending {p['read_pending']}; heap {p['heap_used'] / M:.0f} MiB")
