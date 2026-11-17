#!/usr/bin/env python3
# Summarise an arm's samples.csv (U1Sample): baseline (min of first 4 good samples, before load), peaks, deltas.
import sys, csv, os
R = sys.argv[1]; MiB = 1048576.0
rows = list(csv.DictReader(open(os.path.join(R, 'samples.csv'))))
def f(r, k):
    try: v = float(r[k]); return v if v >= 0 else None
    except: return None
good = [r for r in rows if f(r, 'direct_used') is not None]
if not good: print("no samples"); sys.exit()
base = min(f(r, 'direct_used') for r in good[:4])
pk = lambda k: max((f(r, k) or 0) for r in rows)
d = lambda k: ((f(good[-1], k) or 0) - (f(good[0], k) or 0))
dead = next((r['epoch_ms'] for r in rows[len(good) and rows.index(good[0]):] if r['direct_used'] == 'NA'), None)
print("base_direct=%.0f U_peak=%.0f heap_peak=%.0f mut_active_peak=%d mut_pending_peak=%d memtable_peak=%.0f MiB | d_mut_completed=%d d_write_timeouts=%d d_dropped=%d d_cl_wait_seg=%d d_cl_wait_commit=%d%s" % (
    base / MiB, pk('direct_used') / MiB, pk('heap_used') / MiB, pk('mut_active'), pk('mut_pending'), pk('memtable_onheap') / MiB,
    d('mut_completed'), d('write_timeouts'), d('dropped_mut'), d('cl_wait_seg_count'), d('cl_wait_commit_count'),
    (" first_NA_ms=%s" % dead) if dead else ""))
