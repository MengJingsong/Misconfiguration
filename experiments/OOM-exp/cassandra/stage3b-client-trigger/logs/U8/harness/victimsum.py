#!/usr/bin/env python3
# Victim view: per-second and per-window success / latency of the victim role's ops.
#   victimsum.py <victim.csv> <attack_t0_ms> <death_ms|0> <out_prefix>
import sys, json, collections
f, t0, td, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
ops = []
for l in open(f):
    p = l.rstrip('\n').split(',', 3)
    if len(p) < 4 or not p[0].isdigit(): continue
    ops.append((int(p[0]), int(p[1]), p[2], p[3]))
ops.sort()
def pct(v, q):
    if not v: return None
    v = sorted(v); return v[min(len(v) - 1, int(q * len(v)))]
def stat(sel):
    ok = [e - s for s, e, _, r in sel if r == 'ok']
    errs = collections.Counter(r.split(':')[0] for s, e, _, r in sel if r != 'ok')
    return {'issued': len(sel), 'ok': len(ok), 'ok_pct': round(100.0 * len(ok) / len(sel), 2) if sel else None,
            'p50_ms': pct(ok, .5), 'p99_ms': pct(ok, .99), 'max_ms': max(ok) if ok else None, 'errors': dict(errs)}
w = {'before': [o for o in ops if o[0] < t0]}
if td:
    w['during (attack start to node death)'] = [o for o in ops if t0 <= o[0] < td]
    w['after (node dead)'] = [o for o in ops if o[0] >= td]
else:
    w['during/after (node alive)'] = [o for o in ops if o[0] >= t0]
res = {'attack_t0_ms': t0, 'death_ms': td, 'windows': {k: stat(v) for k, v in w.items()}}
json.dump(res, open(out + '-summary.json', 'w'), indent=1)
print(json.dumps(res, indent=1))
by = collections.defaultdict(list)
for o in ops:
    by[(o[0] - t0) // 1000].append(o)
with open(out + '-per-second.csv', 'w') as g:
    g.write('sec_from_attack,issued,ok,err,p50_ms,max_ms,err_classes\n')
    for s in sorted(by):
        st = stat(by[s])
        g.write('%d,%d,%d,%d,%s,%s,%s\n' % (s, st['issued'], st['ok'], st['issued'] - st['ok'], st['p50_ms'], st['max_ms'],
                                            ';'.join('%s=%d' % kv for kv in st['errors'].items())))
