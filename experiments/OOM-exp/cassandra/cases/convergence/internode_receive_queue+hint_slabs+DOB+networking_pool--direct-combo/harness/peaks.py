#!/usr/bin/env python3
# Summarise an arm's samples.csv: baseline (first 3 good samples before load), peaks of U (direct), K, etc.
import sys, csv, os
R = sys.argv[1]; MiB = 1048576.0
rows = [r for r in csv.DictReader(open(os.path.join(R, 'samples.csv')))]
def f(r, k):
    try: v = float(r[k]); return v if v >= 0 else None
    except: return None
good = [r for r in rows if f(r, 'direct_used') is not None]
if not good: print("no samples"); sys.exit()
base = min(f(r, 'direct_used') for r in good[:4])
pk = lambda k: max((f(r, k) or 0) for r in rows)
ku = [(f(r, 'K_using'), f(r, 'direct_used'), r) for r in rows if f(r, 'K_using') is not None and f(r, 'direct_used') is not None]
kmax = max(ku, key=lambda x: x[0]) if ku else None
first = rows[0]; last_ok = [r for r in rows if f(r, 'received') is not None]
d = lambda k: (f(last_ok[-1], k) - f(last_ok[0], k)) if len(last_ok) > 1 else 0
dead = next((r['epoch_ms'] for r in rows if r['direct_used'] == 'NA'), None)
print("base_direct=%.0f U_peak=%.0f K_peak=%.0f (U_at_Kpeak=%.0f) reserve_peak=%.0f peers_using_max=%d max_peer=%.1f heap_peak=%.0f mutpend_peak=%.0f netpool_peak=%.0f overflow_peak=%.0f MiB | d_received=%d d_processed=%d d_expired=%d d_throttled=%d%s" % (
    base / MiB, pk('direct_used') / MiB, pk('K_using') / MiB, (kmax[1] / MiB if kmax else -1), pk('K_reserve') / MiB,
    int(pk('peers_using')), pk('max_peer_using') / MiB, pk('heap_used') / MiB, pk('mut_pending'), pk('net_pool_size') / MiB,
    pk('net_pool_overflow') / MiB, d('received'), d('processed'), d('expired'), d('throttled'),
    (" first_NA_ms=%s" % dead) if dead else ""))
