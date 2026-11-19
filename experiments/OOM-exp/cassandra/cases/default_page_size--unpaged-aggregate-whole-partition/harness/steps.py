#!/usr/bin/env python3
# Per-step summary of a U10 lifetime: client.csv (per second) joined with samples.csv (1 s JMX).   steps.py <run dir>
import csv, sys, collections
d = sys.argv[1]
c = [r for r in csv.DictReader(l for l in open(d + '/client.csv') if l[:1] in 't0123456789') if r['t'][:1].isdigit()]
s = [r for r in csv.DictReader(open(d + '/samples.csv')) if r.get('heap_used') and r['heap_used'].lstrip('-').isdigit() and int(r['heap_used']) >= 0]
steps = collections.OrderedDict()
for r in c: steps.setdefault((r['step_c'], r['step_n']), []).append(r)
lastS = int(s[-1]['t_ms']) if s else 0
for (cc, n), rows in steps.items():
    t0 = int(rows[0]['t']) - 1000; t1 = int(rows[-1]['t'])
    ss = [x for x in s if t0 <= int(x['t_ms']) <= t1]
    if not ss: print(f'c={cc} n={n} no samples (victim gone)'); continue
    dur = (min(t1, lastS) - t0) / 1000 or 1
    alive = [r for r in rows if int(r['t']) <= lastS]
    ok = sum(int(r['ok_s']) for r in alive); cor = sum(int(r['correct_s']) for r in alive)
    rt = sum(int(r['err_rt_s']) for r in rows); rf = sum(int(r['err_rf_s']) for r in rows); ot = sum(int(r['err_other_s']) for r in rows)
    infl = sorted(int(r['inflight']) for r in rows)
    lat = [float(r['mean_ms']) for r in alive if float(r['mean_ms']) >= 0]
    act = sorted(int(x['ntr_active']) for x in ss); rs = sorted(int(x['rs_active']) for x in ss)
    heap = [int(x['heap_used']) / 2**20 for x in ss]; post = [int(x['old_postgc']) / 2**20 for x in ss]
    dirm = [int(x['direct_used']) / 2**20 for x in ss]
    oldms = int(ss[-1]['old_ms']) - int(ss[0]['old_ms']); yms = int(ss[-1]['young_ms']) - int(ss[0]['young_ms'])
    print(f"c={cc:>3} n={n:>6} {dur:4.0f}s ok={ok} correct={cor} q/s={ok/dur:5.2f} err rt/rf/other={rt}/{rf}/{ot} inflight med={infl[len(infl)//2]} "
          f"lat mean~{(sum(lat)/len(lat) if lat else -1):.0f}ms NTR act med/max={act[len(act)//2]}/{act[-1]} RS act max={rs[-1]} heap max={max(heap):.0f} "
          f"old-postGC max={max(post):.0f} direct max={max(dirm):.0f} GC% young={yms/dur/10:.1f} full={oldms/dur/10:.1f}")
