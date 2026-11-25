#!/usr/bin/env python3
# R24 (2026-11-24), from B22's steps.py: per-step summary of a lifetime: client.csv (per second) joined with samples.csv (1 s JMX);
# adds bad pages and the short-read protection request count (srp) delta per step.   steps.py <logs/LABEL>
import csv, sys, collections
d = sys.argv[1]
c = [r for r in csv.DictReader(open(d + '/client.csv')) if r['t'][:1].isdigit()]
s = [r for r in csv.DictReader(open(d + '/samples.csv')) if r.get('heap_used') and r['heap_used'].isdigit()]
steps = collections.OrderedDict()
for r in c: steps.setdefault(r['step_N'], []).append(r)
lastS = int(s[-1]['t_ms']) if s else 0
for n, rows in steps.items():
    t0 = int(rows[0]['t']) - 1000; t1 = int(rows[-1]['t'])
    ss = [x for x in s if t0 <= int(x['t_ms']) <= t1]
    if not ss: print(f'c={n} no samples (victim gone)'); continue
    dur = (min(t1, lastS) - t0) / 1000 or 1
    alive = [r for r in rows if int(r['t']) <= lastS]
    ok = sum(int(r['ok_s']) for r in alive); mb = sum(float(r['MBps']) for r in alive)
    err = int(rows[-1]['err']) - int(rows[0]['err'])
    infl = sorted(int(r['inflight']) for r in rows)
    act = sorted(int(x['ntr_active']) for x in ss); rs = sorted(int(x['rs_active']) for x in ss)
    heap = [int(x['heap_used']) / 2**20 for x in ss]; post = [int(x['old_postgc']) / 2**20 for x in ss]
    dirm = [int(x['direct_used']) / 2**20 for x in ss]
    oldms = int(ss[-1]['old_ms']) - int(ss[0]['old_ms']); yms = int(ss[-1]['young_ms']) - int(ss[0]['young_ms'])
    rl = sorted(set(r['rowsLastRead'] for r in alive))
    ov = int(rows[-1]['overloaded']) - int(rows[0]['overloaded']); to = int(rows[-1]['timeouts']) - int(rows[0]['timeouts'])
    bad = int(rows[-1]['badpages']) - int(rows[0]['badpages'])
    kw = max(int(x['rfpK_wide_max']) for x in ss); ksm = max(int(x['rfpK_small_max']) for x in ss)
    rq = max(int(x['rfp_req_wide']) for x in ss)
    srp = int(ss[-1]['srp_wide']) - int(ss[0]['srp_wide'])  # 3-b R24: ST = WT = w2k (no s2k table), so only the wide column
    print(f"c={n:>3} {dur:4.0f}s pages/s={ok/dur:5.2f} MB/s={mb/dur:6.0f} err={err} inflight med={infl[len(infl)//2]} "
          f"NTR active med/max={act[len(act)//2]}/{act[-1]} RS active max={rs[-1]} heap max={max(heap):.0f} "
          f"old-postGC max={max(post):.0f} direct max={max(dirm):.0f} GC% young={yms/dur/10:.1f} full={oldms/dur/10:.1f} rowsLastRead={','.join(rl)} "
          f"overloaded={ov} timeouts={to} badpages={bad} K_max w/s={kw}/{ksm} rfpRequests={rq} srpRequests(delta)={srp}")
