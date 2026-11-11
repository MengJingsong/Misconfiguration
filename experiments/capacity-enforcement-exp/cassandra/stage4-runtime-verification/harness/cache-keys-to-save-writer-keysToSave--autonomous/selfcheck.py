#!/usr/bin/env python3
"""Independent self-check for cache-keys-to-save-writer-keysToSave--autonomous. Re-parses RAW logs (not the harness's own summaries):
  unit:    the Cassandra test log (build/test/logs/_jdk11/TEST-...KeysToSaveWriterTest.log) 'Saved KeyCache|CounterCache (n items)' lines in order,
           the unit.txt measurements, and the rules n = min(K, N), affine file length.
  cluster: each arm's system.log.full 'Saved KeyCache (n items)' lines against results.json, the stress logs ('Total errors : 0'), the heap csv
           peaks recomputed, and the relations recomputed from the raw numbers with its own code.
usage: selfcheck.py <unit-test-log> <unit.txt> <cluster-dir>"""
import json, os, re, sys
ulog, utxt, cdir = sys.argv[1:4]
bad = 0
def chk(name, ok, detail=''):
    global bad
    print('SELFCHECK %s: %s %s' % (name, 'holds' if ok else 'DOES NOT HOLD', detail)); bad += 0 if ok else 1
MAX = 2**31 - 1
# ---- unit
saved = [(m.group(1), int(m.group(2))) for l in open(ulog, errors='replace') for m in [re.search(r'Saved (KeyCache|CounterCache) \((\d+) items\)', l)] if m]
kv = {}
N = None
for l in open(utxt):
    l = l.strip()
    if l.startswith('N='): N = int(l[2:])
    m = re.match(r'(key|ctr) K=(\d+) n_logged=(\d+) file_len=(\d+)', l)
    if m: kv.setdefault(m.group(1), []).append((int(m.group(2)), int(m.group(3)), int(m.group(4))))
# the test log is appended to by every run in the tree: take the last 7 KeyCache and last 2 CounterCache saves (this run)
keys = [n for t, n in saved if t == 'KeyCache'][-7:]; ctrs = [n for t, n in saved if t == 'CounterCache'][-2:]
chk('unit: test log has one KeyCache save per K in order (7)', len(keys) == 7, str(keys))
chk('unit: KeyCache n from the test log == n_logged in unit.txt', keys == [x[1] for x in kv.get('key', [])], '')
want = [min(k, N) if k > 0 else N for k, _, _ in kv.get('key', [])]
chk('unit: n == min(K, N) (0 and MAX mean N)', keys == want, 'log=%s want=%s' % (keys, want))
chk('unit: CounterCache n == min(K, N) for K=100, 0', ctrs == [min(100, N), N], str(ctrs))
pts = sorted((n, l) for _, n, l in kv.get('key', []))
(n0, l0), (n1, l1) = pts[0], pts[-1]
e = (l1 - l0) / float(n1 - n0)
chk('unit: file length affine in n (resid <= 8 B at every point)', all(abs(l - (l0 + e * (n - n0))) <= 8 for n, l in pts), 'e=%.2f hdr=%.1f' % (e, l0 - e * n0))
# ---- cluster
def L(a):
    p = os.path.join(cdir, a, 'results.json'); return json.load(open(p)) if os.path.exists(p) else None
for a in ('main', 'ctl20', 'yaml10k'):
    r = L(a)
    if not r: print('no', a); continue
    ls = [int(m.group(1)) for l in open(os.path.join(cdir, a, 'system.log.full'), errors='replace') for m in [re.search(r'Saved KeyCache \((\d+) items\)', l)] if m]
    got = [s['n_logged'] for s in r['saves']]
    tail = ls[-len(got):] if a != 'yaml10k' else ls[-1:]
    chk('%s: system.log Saved lines == results.json n_logged (in order)' % a, tail == (got if a != 'yaml10k' else got[-1:]), 'log=%s json=%s' % (ls[-len(got) - 1:], got))
    for f in os.listdir(os.path.join(cdir, a)):
        if f.startswith('stress-') and f.endswith('.log'):
            t = open(os.path.join(cdir, a, f), errors='replace').read()
            m = re.search(r'Total errors\s*:\s*(\d+)', t)
            chk('%s: %s Total errors 0' % (a, f), bool(m) and m.group(1) == '0', m.group(0) if m else 'no line')
    for s in r['saves']:
        hp = os.path.join(cdir, a, 'heap-%s.csv' % s['label'])
        pk = max([int(x.split(',')[1]) for x in open(hp).read().splitlines()[1:] if ',' in x and x.split(',')[1].isdigit()] or [0])
        chk('%s %s: heap peak recomputed from csv == recorded' % (a, s['label']), pk == s['heap_peak_during_save'], '%d' % pk)
m = L('main')
if m:
    S = {s['K']: s for s in m['saves']}
    F = {k: s['files_after']['KeyCache-g.db'] for k, s in S.items()}
    ent = S[0]['before']['entries']
    chk('main: n == K for K=10000,100000; n ~ entries for 0/MAX', S[10000]['n_logged'] == 10000 and S[100000]['n_logged'] == 100000 and all(abs(S[k]['n_logged'] - ent) <= 0.005 * ent for k in (0, MAX)), str({k: s['n_logged'] for k, s in S.items()}))
    chk('main: F(10000) < F(100000) < F(0) ~ F(MAX)', F[10000] < F[100000] < F[0] and abs(F[0] - F[MAX]) <= 0.01 * F[0], str(F))
    per_entry = {k: F[k] / float(S[k]['n_logged']) for k in F}
    chk('main: bytes per entry constant within 2 % across K', max(per_entry.values()) / min(per_entry.values()) <= 1.02, str({k: round(v, 2) for k, v in per_entry.items()}))
print('SELFCHECK total not holding:', bad); sys.exit(1 if bad else 0)
