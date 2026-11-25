#!/usr/bin/env python3
# R24: per-query outcome summary of a run's queries.csv (start_ms,end_ms,outcome,rows,check,error): started, ok, err, bad pages,
# latency of ok queries (p50/p90/max), error classes, completion rate.   qsum.py <queries.csv>
import csv, sys, collections
r = list(csv.DictReader(open(sys.argv[1])))
ok = [x for x in r if x['outcome'] == 'ok']; er = [x for x in r if x['outcome'] == 'err']
lat = sorted((int(x['end_ms']) - int(x['start_ms'])) / 1000 for x in ok)
q = lambda p: lat[min(len(lat) - 1, int(len(lat) * p))] if lat else -1
ec = collections.Counter(x['error'].split(':')[0] for x in er)
ems = collections.Counter(x['error'][:140] for x in er).most_common(3)
print(f"queries={len(r)} ok={len(ok)} err={len(er)} completion={100*len(ok)/max(1,len(r)):.0f}% badpages={sum(1 for x in ok if x['check']!='ok')} "
      f"lat_ok p50={q(.5):.2f}s p90={q(.9):.2f}s max={lat[-1] if lat else -1:.2f}s errclasses={dict(ec)}")
for m, n in ems: print(f"  {n} x {m}")
