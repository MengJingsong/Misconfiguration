#!/usr/bin/env python3
# B29 (2026-11-24) per-lifetime summary from logs/<label>/: queries.csv (client, one line per query) joined with samples.csv
# (1 s JMX on node 1). Test queries are k < 1000, warm-up k >= 1000.
#   summ.py <logs/LABEL> [...]
import csv, sys, collections
for d in sys.argv[1:]:
    try:
        q = list(csv.DictReader(open(d + '/queries.csv')))
    except FileNotFoundError:
        q = []
    s = [r for r in csv.DictReader(open(d + '/samples.csv')) if r.get('heap_used', '').lstrip('-').isdigit() and r['heap_used'] != '-1']
    test = [r for r in q if r['k'].isdigit() and int(r['k']) < 1000]
    warm = [r for r in q if r['k'].isdigit() and int(r['k']) >= 1000]
    ok = [r for r in test if not r['error']]
    errs = collections.Counter(r['error'].split(':')[0] for r in test if r['error'])
    rows = collections.Counter(r['rows'] for r in ok)
    lat = sorted(int(r['latMs']) for r in ok)
    t0 = min((int(r['startMs']) for r in test), default=None)
    pre = [x for x in s if t0 and int(x['t_ms']) < t0]
    dur = [x for x in s if t0 and int(x['t_ms']) >= t0]
    def mx(rows, col, f=1): return max((int(x[col]) for x in rows), default=-1) / f
    def delta(col): return (int(dur[-1][col]) - int(pre[-1][col])) if dur and pre else -1
    M = 2 ** 20
    out = open(d + '/outcome').read().strip() if __import__('os').path.exists(d + '/outcome') else '?'
    print(f"{d.rstrip('/').split('/')[-1]}: outcome=[{out}] warm ok={sum(1 for r in warm if not r['error'])}/{len(warm)} "
          f"test started={len(test)} ok={len(ok)} rows={dict(rows)} errors={dict(errs)} "
          f"lat ms med/max={lat[len(lat)//2] if lat else -1}/{lat[-1] if lat else -1} | "
          f"pre-test heap max={mx(pre,'heap_used',M):.0f}MiB; test: heap max={mx(dur,'heap_used',M):.0f}MiB old_postgc max={mx(dur,'old_postgc',M):.0f}MiB "
          f"direct max={mx(dur,'direct_used',M):.0f}MiB NTR active max={mx(dur,'ntr_active'):.0f} RS active max={mx(dur,'rs_active'):.0f} "
          f"K max={mx(s,'rfpK_max'):.0f} rfpRequests +{delta('rfp_req')} rrBlocking +{delta('rr_blocking')} samples={len(dur)}")
