#!/usr/bin/env python3
# B21 per-item summary of a lifetime (adapted from B17's qsum.py): client Q lines grouped by (item, Q, limit), and run
# items joined with the 1 s JMX samples (heap, G1 old post-GC, NTR/ReadStage active, direct, self-connection large messages).
#   qsum.py <out/LABEL>
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
M = 2 ** 20
def win(t0, t1):
    ss = [x for x in smp if t0 <= int(x['t_ms']) <= t1]
    if not ss: return 'no samples'
    g = lambda k: [int(x[k]) for x in ss]
    lmc = g('lm_completed_bytes'); lmd = g('lm_drop_overload')
    return (f"heap max {max(g('heap_used'))/M:.0f} MiB, old-postGC max {max(g('old_postgc'))/M:.0f} MiB, NTR act max {max(g('ntr_active'))}, "
            f"RS act max {max(g('rs_active'))}, direct max {max(g('direct_used'))/M:.0f} MiB, lm pending max {max(g('lm_pending_bytes'))/M:.0f} MiB, "
            f"lm completed +{(lmc[-1]-lmc[0])/M:.0f} MiB, lm overload drops +{lmd[-1]-lmd[0]}")
for it in items:
    print(f"== {it['spec']}")
    g = collections.OrderedDict()
    for q in it['q']: g.setdefault((q['Q'], q['limit'], q['fetch']), []).append(q)
    for (Q, lim, fe), qs in g.items():
        okq = [q for q in qs if q['err'] is None]; ms = [q['ms'] for q in qs]
        errs = collections.Counter(q['err'] for q in qs if q['err'])
        rows = sorted(set(q['rows'] for q in okq)); pages = sorted(set(q['pages'] for q in okq)); warns = sorted(set(q['warns'] for q in okq))
        vb = sum(q['vbytes'] for q in okq)
        t0 = min(q['start'] for q in qs); t1 = max(q['end'] for q in qs)
        print(f"  {Q} limit={lim} fetch={fe}: n={len(qs)} ok={len(okq)} errs={dict(errs)} ms={ms if len(ms) <= 6 else (min(ms), sorted(ms)[len(ms)//2], max(ms))} rows={rows} pages={pages} warns={warns} vbytes_ok={vb/M:.0f} MiB | {win(t0, t1)}")
        for q in [q for q in qs if q['err']][:3]: print(f"     err: {q['err']}: {(q['msg'] or '')[:200]}")
        for q in okq[:1]:
            if q['warn']: print(f"     warn: {q['warn'][:220]}")
    if it['s']:
        by = collections.OrderedDict()
        for s in it['s']: by.setdefault(s[1], []).append(s)
        prev = None
        for c, ss in by.items():
            t0 = int(ss[0][0]) - 1000; t1 = int(ss[-1][0])
            okn = sum(int(s[8]) for s in ss); vbs = sum(int(s[10]) for s in ss); infl = sorted(int(s[2]) for s in ss)
            e = [int(ss[-1][i]) for i in (4, 5, 6, 7)]; e0 = [int(prev[i]) for i in (4, 5, 6, 7)] if prev else [0, 0, 0, 0]
            de = [a - b for a, b in zip(e, e0)]
            print(f"  run c={c}: {len(ss)} s ok={okn} q/s={okn/len(ss):.2f} value MiB/s={vbs/len(ss)/M:.1f} step errs(rf,to,inv,oth)={de} inflight med={infl[len(infl)//2]} | {win(t0, t1)}")
            prev = ss[-1]
