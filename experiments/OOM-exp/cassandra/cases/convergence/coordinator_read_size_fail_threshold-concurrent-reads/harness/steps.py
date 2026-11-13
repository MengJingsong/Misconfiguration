#!/usr/bin/env python3
# Per-step summary of a C2 lifetime: client.csv (per second) joined with samples.csv (1 s JMX) by time.
#   steps.py <logs/LABEL>
import csv, sys, collections
d = sys.argv[1]
c = [r for r in csv.DictReader(open(d + '/client.csv')) if r['t'][:1].isdigit()]
s = [r for r in csv.DictReader(open(d + '/samples.csv')) if r.get('heap_used') and r['heap_used'].lstrip('-').isdigit()]
steps = collections.OrderedDict()
for r in c: steps.setdefault(r['step_N'], []).append(r)
for n, rows in steps.items():
    t0 = int(rows[0]['t']) - 1000; t1 = int(rows[-1]['t'])
    ss = [x for x in s if t0 <= int(x['t_ms']) <= t1]
    if not ss: print(f'N={n} no samples'); continue
    dur = (t1 - t0) / 1000
    ok = sum(int(r['ok_s']) for r in rows); mb = sum(float(r['MBps']) for r in rows); err = int(rows[-1]['err']) - (int(rows[0]['err']) if rows else 0)
    infl = sorted(int(r['inflight']) for r in rows)
    act = sorted(int(x['ntr_active']) for x in ss); pen = sorted(int(x['ntr_pending']) for x in ss)
    heap = [int(x['heap_used']) / 2**20 for x in ss]; post = [int(x['old_postgc']) / 2**20 for x in ss]
    oldms = int(ss[-1]['old_ms']) - int(ss[0]['old_ms']); yms = int(ss[-1]['young_ms']) - int(ss[0]['young_ms'])
    p50 = sorted(float(r['p50ms']) for r in rows)[len(rows) // 2]; p99 = sorted(float(r['p99ms']) for r in rows)[len(rows) // 2]
    print(f"N={n:>5} {dur:4.0f}s reads/s={ok/dur:5.0f} MB/s={mb/dur:5.0f} err={err} client_inflight med={infl[len(infl)//2]} "
          f"NTR active med/max={act[len(act)//2]}/{act[-1]} pending med/max={pen[len(pen)//2]}/{pen[-1]} heap max={max(heap):.0f} "
          f"old-postGC max={max(post):.0f} GC% young={yms/dur/10:.1f} full={oldms/dur/10:.1f} lat p50/p99={p50}/{p99} ms")
