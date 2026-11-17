#!/usr/bin/env python3
# Summarise a U1 run-2 arm's samples.csv (U1R2Sample, 1 s): baseline (min of first 4 good samples, before load),
# peaks, MutationStage saturation during the load window, receive-queue K, deltas. Load window from args.txt.
import sys, csv, os, re
R = sys.argv[1]; MiB = 1048576.0
rows = list(csv.DictReader(open(os.path.join(R, 'samples.csv'))))
def f(r, k):
    try: v = float(r[k]); return v if v >= 0 else None
    except: return None
good = [r for r in rows if f(r, 'direct_used') is not None]
if not good: print("no samples"); sys.exit()
a = open(os.path.join(R, 'args.txt')).read()
ls = int((re.search(r'(\d+) load start', a) or re.search(r'()', '')).group(1) or 0)
le = int((re.search(r'(\d+) load end', a) or re.search(r'()', '')).group(1) or 0) or 10**15
base = min(f(r, 'direct_used') for r in good[:4])
pk = lambda k, rs=rows: max([(f(r, k) or 0) for r in rs] or [0])
win = [r for r in good if ls <= int(r['epoch_ms']) <= le]
d = lambda k: ((f(good[-1], k) or 0) - (f(good[0], k) or 0))
sat = sum(1 for r in win if (f(r, 'mut_active') or 0) >= 32); ge24 = sum(1 for r in win if (f(r, 'mut_active') or 0) >= 24)
dead = next((int(r['epoch_ms']) for r in rows if r['direct_used'] == 'NA' and int(r['epoch_ms']) > ls), None) if ls else None
upk = max(good, key=lambda r: f(r, 'direct_used'))
print("base_direct=%.0f U_peak=%.0f K_at_Upeak=%.0f K_peak=%.0f heap_peak=%.0f mut_active_peak=%d active32=%d/%d active>=24=%d/%d mut_pending_peak=%d memtable_peak=%.0f MiB | d_local_writes=%d d_dropped_mut=%d d_cl_wait_seg=%d d_cl_wait_commit=%d%s" % (
    base / MiB, f(upk, 'direct_used') / MiB, (f(upk, 'K_using') or 0) / MiB, pk('K_using') / MiB, pk('heap_used') / MiB, pk('mut_active'), sat, len(win), ge24, len(win),
    pk('mut_pending'), pk('memtable_onheap') / MiB, d('local_writes'), d('dropped_mut'), d('cl_wait_seg_count'), d('cl_wait_commit_count'),
    (" death_after_load_start_s=%.0f" % ((dead - ls) / 1000.0)) if dead else ""))
