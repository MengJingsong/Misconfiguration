#!/usr/bin/env python3
# B17 3-b confirm (pc75, 2026-11-23): copied unchanged from the stage-2 harness.
# B17 per-item summary of a lifetime: client Q lines grouped by (item, Q, k), and run items joined with the 1 s JMX
# samples (heap, G1 old post-GC, NTR/ReadStage active).   qsum.py <logs/LABEL>
import json, sys, csv, collections
d = sys.argv[1]
items = []; cur = None
for line in open(d + '/client.out', errors='replace'):
    if line.startswith('ITEM '):
        p = line.split(' ', 2); cur = {'t': int(p[1]), 'spec': p[2].strip(), 'q': [], 's': []}; items.append(cur)
    elif line.startswith('Q ') and cur is not None:
        try: cur['q'].append(json.loads(line[2:]))
        except Exception: pass
    elif line.startswith('S ') and cur is not None and line[2:3].isdigit():
        cur['s'].append(line[2:].split(','))
    elif line.startswith(('SUMMARY', 'HOSTGONE')): print(line.strip())
smp = []
try:
    for r in csv.DictReader(open(d + '/samples.csv')):
        if r.get('heap_used', '').lstrip('-').isdigit() and int(r['heap_used']) >= 0: smp.append(r)
except FileNotFoundError: pass
def win(t0, t1):
    ss = [x for x in smp if t0 <= int(x['t_ms']) <= t1]
    if not ss: return 'no samples'
    h = max(int(x['heap_used']) for x in ss) / 2**20; o = max(int(x['old_postgc']) for x in ss) / 2**20
    na = max(int(x['ntr_active']) for x in ss); ra = max(int(x['rs_active']) for x in ss)
    return f'heap max {h:.0f} MiB, old-postGC max {o:.0f} MiB, NTR active max {na}, RS active max {ra}'
for it in items:
    print(f"== {it['spec']}")
    g = collections.OrderedDict()
    for q in it['q']: g.setdefault((q['Q'], q['k']), []).append(q)
    for (Q, k), qs in g.items():
        okq = [q for q in qs if q['err'] is None]; ms = [q['ms'] for q in qs]
        errs = collections.Counter(q['err'] for q in qs if q['err'])
        rows = sorted(set(q['rows'] for q in okq))
        t0 = min(q['start'] for q in qs); t1 = max(q['end'] for q in qs)
        print(f"  {Q} k={k}: n={len(qs)} ok={len(okq)} errs={dict(errs)} ms={ms if len(ms) <= 6 else (min(ms), sorted(ms)[len(ms)//2], max(ms))} rows={rows} | {win(t0, t1)}")
        for q in qs[:3]:
            if q['err']: print(f"     err: {q['err']}: {(q['msg'] or '')[:160]}")
        if okq and len(okq) <= 3:
            for q in okq: print(f"     first10: {q['first']} vbytes={q['vbytes']} pks={q['pks']}")
    if it['s']:
        by = collections.OrderedDict()
        for s in it['s']: by.setdefault(s[1], []).append(s)
        for c, ss in by.items():
            t0 = int(ss[0][0]) - 1000; t1 = int(ss[-1][0])
            okn = sum(int(s[8]) for s in ss); infl = sorted(int(s[2]) for s in ss)
            print(f"  run c={c}: {len(ss)} s ok={okn} q/s={okn/len(ss):.2f} errs(rf,rt,inv,oth)={ss[-1][4]},{ss[-1][5]},{ss[-1][6]},{ss[-1][7]} inflight med={infl[len(infl)//2]} | {win(t0, t1)}")
