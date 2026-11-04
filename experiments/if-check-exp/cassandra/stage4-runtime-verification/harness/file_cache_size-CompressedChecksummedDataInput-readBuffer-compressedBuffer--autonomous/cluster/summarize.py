#!/usr/bin/env python3
"""summarize.py <sampler.csv> <phase-start-epoch-ms> [<phase-end-epoch-ms>] -> summary lines (peaks inside the window, baseline = first sample)"""
import sys, csv
rows = [r for r in csv.reader(open(sys.argv[1]))][1:]
rows = [r for r in rows if len(r) > 3 and r[1] != "ERR"]
t0 = int(sys.argv[2]); t1 = int(sys.argv[3]) if len(sys.argv) > 3 else 1 << 62
cols = ["epoch_ms","capacity","size","used","overflow","pooled","direct_used","direct_count","rss_anon","heap_used","net_size","net_overflow"]
data = [dict(zip(cols, map(int, r))) for r in rows]
base = data[0]
win = [d for d in data if t0 <= d["epoch_ms"] <= t1] or data
print(f"samples_total={len(data)} samples_in_window={len(win)}")
print("baseline " + " ".join(f"{k}={base[k]}" for k in cols[1:]))
for k in cols[1:]:
    print(f"peak_{k}={max(d[k] for d in win)} min_{k}={min(d[k] for d in win)} last_{k}={win[-1][k]}")
pre = [d for d in data if d["epoch_ms"] < t0]
pre = pre[-1] if pre else base
print("pre_window " + " ".join(f"{k}={pre[k]}" for k in cols[1:]))
print(f"peak_direct_minus_pre={max(d['direct_used'] for d in win) - pre['direct_used']}")
print(f"peak_overflow_minus_pre={max(d['overflow'] for d in win) - pre['overflow']}")
print(f"peak_direct_minus_baseline={max(d['direct_used'] for d in win) - base['direct_used']}")
print(f"peak_overflow_minus_baseline={max(d['overflow'] for d in win) - base['overflow']}")
