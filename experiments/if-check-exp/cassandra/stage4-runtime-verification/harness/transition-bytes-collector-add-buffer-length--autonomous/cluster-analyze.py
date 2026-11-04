#!/usr/bin/env python3
"""Analyzer of the cluster tier of transition-bytes-collector-add-buffer-length--autonomous. usage: cluster-analyze.py <run cluster dir>
Prints EXPECTED lines for B3f (a)-(d) and the matched B3g row."""
import json, os, re, sys
d = sys.argv[1]
LIVES = ['T1k', 'T8k', 'T64k', 'BIG']
recs = [json.loads(l) for l in open(os.path.join(d, 'cells.jsonl'))]
# expected acceptance (B3f (c)): table -> set of lifetimes in which every write is accepted
ACC = {'w1': set(LIVES), 'w2': {'T8k', 'T64k', 'BIG'}, 'w3': set(LIVES), 'w4': {'T64k'}}
res = {}
def chk(name, ok, detail):
    res[name] = ok
    print(f"EXPECTED: {name}: {'HOLDS' if ok else 'FAILS'}  [{detail}]")
loads = {}; reads = {}; ends = {}; du = {}; lives_seen = []
for r in recs:
    if r['kind'] == 'life': lives_seen.append(r['life'])
    elif r['kind'] == 'phase' and r['phase'].startswith('load_'): loads[(r['life'], r['phase'][5:])] = r['detail']
    elif r['kind'] == 'phase' and r['phase'] == 'reads': reads[r['life']] = r['detail']
    elif r['kind'] == 'end': ends[r['life']] = r
    elif r['kind'] == 'du': du[r['life']] = r['data_bytes']
chk('lifetimes run', set(LIVES) <= set(lives_seen), str(lives_seen))
# (a) collector lines
coll = {}; live = {}
for L in LIVES:
    p = os.path.join(d, L, 'trace.txt')
    lines = open(p, errors='replace').read().splitlines() if os.path.exists(p) else None
    if lines is None: coll[L] = None; continue
    coll[L] = sum(1 for l in lines if l.startswith('COLL'))
    mx = {}; cls = set()
    for l in lines:
        m = re.match(r'LIVE (\w+) n=(\d+).*?(?:cls=(\S+))?$', l)
        if m:
            mx[m.group(1)] = max(mx.get(m.group(1), 0), int(m.group(2)))
            if m.group(3): cls.add(m.group(3))
    live[L] = (mx, cls)
chk('B3f(a) zero COLL lines (constructions or add calls of the collector) in every lifetime', all(coll.get(L) == 0 for L in LIVES), str(coll))
ok_b = all(L in live and live[L][0].get('walker', 0) > 0 and live[L][0].get('saireader', 0) > 0 for L in LIVES)
chk('B3f(b) liveness counters nonzero in every lifetime (Walker, TrieTermsDictionaryReader)', ok_b, '; '.join(f'{L}: {live[L][0]}' for L in LIVES if L in live))
bti_ok = all(any('TrieTermsDictionaryReader' not in c for c in live[L][1]) or live[L][0].get('walker', 0) > 0 for L in ('T1k', 'T8k', 'T64k') if L in live)
print('INFO: Walker classes seen per lifetime:', {L: sorted(live[L][1]) for L in live})
bad = []
for t, accset in ACC.items():
    for L in LIVES:
        x = loads.get((L, t), {})
        want_all = L in accset
        okc = x.get('other_errors', 1) == 0 and ((x.get('rejected', 1) == 0 and x.get('ok') == x.get('expected')) if want_all else (x.get('ok', 1) == 0 and x.get('rejected') == x.get('expected')))
        if not okc: bad.append((L, t, x.get('ok'), x.get('rejected'), x.get('expected'), x.get('other_errors')))
chk('B3f(c) accepted counts follow the thresholds (w1,w3 all lifetimes; w2 not at 1KiB; w4 only at 64KiB)', not bad and len(loads) == 16, f'{len(loads)} loads, violations {bad[:4]}')
d_ok = all(L in du for L in LIVES) and du['T1k'] < du['T8k'] < du['T64k'] and du['BIG'] > du['T1k']
chk('B3f(d) [auxiliary] data directory size follows the accepted volume (T1k < T8k < T64k; BIG above T1k: the formats differ, so BIG is not compared with T8k)', d_ok, str(du))
rd_ok = all(L in reads and reads[L].get('errors_n', 1) == 0 and reads[L].get('sai_hit', 0) > 0 and reads[L].get('point_hit', 0) > 0 for L in LIVES)
chk('reads ran: point reads and SAI queries returned data, zero errors, every lifetime', rd_ok, '; '.join(f"{L}: point {reads[L].get('point')}/{reads[L].get('point_hit')} sai {reads[L].get('sai')}/{reads[L].get('sai_hit')} err {reads[L].get('errors_n')}" for L in reads))
er_ok = all(L in ends and ends[L]['error_lines'] == 0 for L in LIVES)
chk('system.log: zero ERROR/OutOfMemoryError lines apart from the guardrail rejection line', er_ok, str({L: ends[L]['error_lines'] for L in ends}))
core = res['B3f(a) zero COLL lines (constructions or add calls of the collector) in every lifetime'] and ok_b and not bad and len(loads) == 16
inst = rd_ok and er_ok and res['lifetimes run']
if core and inst:
    row = 'B3g row 1: no collector lines in any lifetime, liveness counters nonzero, accepted counts follow the thresholds - claim confirmed' + ('' if d_ok else ' (auxiliary B3f(d) did not hold: see above)')
elif any((coll.get(L) or 0) > 0 for L in LIVES):
    row = 'B3g rows 2/3: collector lines appear - inspect lengths vs key length and vs the threshold (refuted for "never exercised")'
else:
    row = 'B3g row 4: instrument or load inadequate (see FAILS above) - Not confirmed'
print('MATCHED:', row)
