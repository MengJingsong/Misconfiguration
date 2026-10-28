#!/usr/bin/env python3
"""Self-check of run 1 (prepared_statements_cache_size-loadpreparedstatements-preparedbytesloaded--autonomous): re-parses the raw files in this folder
(unit/run.out, cluster/*/summary.txt, cluster/*/excerpt.txt) and tests each statement the conclusion rests on. Prints PASS/FAIL per statement."""
import os, re, sys, collections
here = os.path.dirname(os.path.abspath(__file__)); ok = True


def chk(name, cond, detail=''):
    global ok
    ok &= bool(cond); print(('PASS ' if cond else 'FAIL ') + name + ('  ' + detail if detail else ''))


# ---- unit
U = {}
for l in open(here + '/unit/run.out'):
    if l.startswith('STAGE4 final'):
        d = dict(re.findall(r'(\w+)=(\S+)', l)); U[d['label']] = {k: (int(v) if re.fullmatch(r'-?\d+', v) else v) for k, v in d.items()}
chk('unit: 22 final lines', len(U) == 22, str(len(U)))
chk('unit: no MISMATCH in checks', 'MISMATCH' not in open(here + '/unit/run.out').read())
for lab, d in U.items():
    arm = d['arm']; cap = d['cap']; s = d['s']
    chk(f'{lab}: sumWeights<=cap and cache full', d['sumWeights'] <= cap and d['sumWeights'] > cap - 2 * (s + 16))
    chk(f'{lab}: count+evicted==loaded', d['count'] + d['evicted'] == d['loaded'])
    if arm == 'A':
        exp = int(1.1 * cap // s) + 1
        chk(f'{lab}: A loaded == floor(1.1 cap/s)+1 and WARN', d['loaded'] == exp and d['warn'] == 'true', f"loaded={d['loaded']} expected={exp}")
    else:
        chk(f'{lab}: B loaded == n and no WARN', d['loaded'] == d['n'] and d['warn'] == 'false')
for cap in (1, 4, 10):
    for r in (1, 2, 3):
        a, b = U[f'A-cap{cap}-f3-r{r}'], U[f'B-cap{cap}-f3-r{r}']
        chk(f'cap{cap} f3 r{r}: live heap B-A below one cap', b['liveDelta'] - a['liveDelta'] < a['cap'], f"{b['liveDelta'] - a['liveDelta']} vs cap {a['cap']}")
        chk(f'cap{cap} f3 r{r}: cache component equal', a['sumWeights'] == b['sumWeights'])
for cap in (1, 10):
    a, b = U[f'A-cap{cap}-f30-r1'], U[f'B-cap{cap}-f30-r1']
    dl = b['liveDelta'] - a['liveDelta']; dm = b['memtableAfter'] - a['memtableAfter']
    chk(f'cap{cap} f30: cache component equal', a['sumWeights'] == b['sumWeights'])
    chk(f'cap{cap} f30: live heap B-A >= one cap', dl >= a['cap'], f"{dl} vs cap {a['cap']} = {dl / a['cap']:.2f} caps")
    print(f"INFO cap{cap} f30: memtable diff {dm}, live diff {dl}, |mt-live|/live = {abs(dm - dl) / dl:.2f} (rule: within 25 %)")
w = {cap: U[f'B-cap{cap}-f3-r1']['sumWeights'] for cap in (1, 4, 10)}
chk('unit positive control: sumWeights 1:4:10 within 1 %', abs(w[4] / w[1] - 4) < 0.04 and abs(w[10] / w[1] - 10) < 0.1, str(w))
# ---- cluster
C = {}
for t in sorted(os.listdir(here + '/cluster')):
    f = f'{here}/cluster/{t}/summary.txt'
    if t == 'seed' or not os.path.exists(f): continue
    x = open(f).read()
    pre = re.search(r"PRELOAD lines=\[\('(\d+)', '(\d+)'\)\]; filling-up warnings=(\d+)", x); c = re.search(r'COUNTERS count=(\d+) evicted=(\d+) memtable_heap=(\d+)', x)
    h = re.search(r'HISTO after-preload live_bytes=(\d+) live_objects=\d+ prepared_instances=(\d+) prepared_shallow=(\d+)', x); r = re.search(r'ROWS system.prepared_statements: (\d+)', x)
    C[t] = dict(loaded=int(pre.group(1)), warn=int(pre.group(3)), count=int(c.group(1)), ev=int(c.group(2)), mt=int(c.group(3)), live=int(h.group(1)), prep=int(h.group(2)), rows=int(r.group(1)),
                cap=int(re.search(r'cap (\d+) MiB', x).group(1)) << 20, readback=re.search(r'Initialized prepared statement caches with (\d+) MiB', x).group(1))
chk('cluster: 8 starts', len(C) == 8)
for t, d in C.items():
    chk(f'{t}: knob read-back == cap', int(d['readback']) << 20 == d['cap'])
    chk(f'{t}: arm {t[0]}', (d['warn'] == 1 and d['loaded'] < 20010) if t[0] == 'A' else (d['warn'] == 0 and d['loaded'] == 20010), f"loaded={d['loaded']} warn={d['warn']}")
    ex = open(f'{here}/cluster/{t}/excerpt.txt').read()
    chk(f'{t}: raw log excerpt agrees with summary on Preloaded line', f"Preloaded {d['loaded']} prepared statements" in ex)
for cap in (1, 4, 10):
    for r in (1, 2):
        a, b = C.get(f'A-cap{cap}-r{r}'), C.get(f'B-cap{cap}-r{r}')
        if not (a and b): continue
        chk(f'cluster cap{cap} r{r}: Prepared instances and cache count equal across arms', a['prep'] == b['prep'] and a['count'] == b['count'], f"{a['prep']} {b['prep']} {a['count']} {b['count']}")
        dl = b['live'] - a['live']; dm = b['mt'] - a['mt']
        print(f"INFO cluster cap{cap} r{r}: live B-A {dl} ({dl / a['cap']:.2f} caps), memtable B-A {dm}, |mt-live|/live {abs(dm - dl) / dl:.2f}")
        chk(f'cluster cap{cap} r{r}: memtable difference within 25 % of live difference', abs(dm - dl) / dl <= 0.25)
cnt = {cap: C[f'B-cap{cap}-r1']['count'] for cap in (1, 4, 10)}
chk('cluster positive control: cache count 1:4:10 within 2 %', abs(cnt[4] / cnt[1] - 4) < 0.08 and abs(cnt[10] / cnt[1] - 10) < 0.2, str(cnt))
print('ALL PASS' if ok else 'SOME FAIL'); sys.exit(0 if ok else 1)
