#!/usr/bin/env python3
"""Cluster-tier analysis of trie-pathreconstructor-keybytes-growth--autonomous: B3f (a)-(d) as EXPECTED lines, then the B3g row.
usage: python3 -I cluster-analyze.py <cluster-dir> [<tp33-unit.txt>]     (c, the constant of path = key length + c, is read from the unit file)"""
import collections, json, os, re, sys

D = sys.argv[1]
UNIT = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser('~/s4-tp33-logs/run1b/unit/tp33-unit.txt')
c = None
for l in open(UNIT):
    if l.startswith('TP33 ') and 'kind=real' in l and 'bt=ON_HEAP' in l:
        kv = dict(x.split('=', 1) for x in l[5:].split())
        c = int(kv['P']) - int(kv['L']) - int(kv['z']); break
P_BIG, P_SMALL = 60000 + c, 16 + c
BIG_PH = ('load_big', 'warm', 'scan_big_R1', 'scan_big_R32')
LIVES = [x for x in ('H256', 'H1024', 'H64', 'O256') if os.path.isdir(f'{D}/{x}')]
print(f'c = {c}; P_big = {P_BIG}; P_small = {P_SMALL}; lifetimes found {LIVES}')
res = {}


def check(name, expected, ok, detail):
    res[name] = ok
    print(f'EXPECTED {name}: {expected}')
    print(f'  {"HOLDS" if ok else "FAILS"}: {detail}')


def phases(life):
    out = {}
    for l in list(open(f'{D}/{life}/phases.csv'))[1:]:
        p = l.rstrip('\n').split(',', 3)
        out[p[0]] = (int(p[1]), int(p[2]), p[3])
    return out


def trace(life):
    ev = []
    fn = f'{D}/{life}/growth-trace.txt'
    if os.path.exists(fn):
        for l in open(fn, errors='replace'):
            m = re.match(r'(byte|bytes) ms=(\d+) thr=(\S+) it=(-?\d+) len=(\d+) cls=(\S+)', l)
            if m:
                ev.append(dict(m=m.group(1), ms=int(m.group(2)), thr=m.group(3), it=m.group(4), len=int(m.group(5)), cls=m.group(6)))
    return ev


def series(life):
    rows = []
    for l in list(open(f'{D}/{life}/series.csv'))[1:]:
        p = l.strip().split(',')
        try:
            rows.append([float(x) for x in p])
        except ValueError:
            pass
    return rows


def thrkind(t):
    return re.sub(r'[-_:]?\d+.*$', '', t)


info = {}
for lf in LIVES:
    ph, ev, se = phases(lf), trace(lf), series(lf)
    w = {}
    for name, (a, b, det) in ph.items():
        e = [x for x in ev if a <= x['ms'] <= b]
        w[name] = dict(n=len(e), maxlen=max([x['len'] for x in e], default=0), lens=sorted({x['len'] for x in e}),
                       iters=len({(x['thr'], x['it']) for x in e}), thr=collections.Counter(thrkind(x['thr']) for x in e), det=det)
    info[lf] = dict(ph=ph, w=w, ev=ev, se=se)
    print(f'\n{lf}: trace events {len(ev)}')
    for name, x in w.items():
        print(f'  {name:14s} events {x["n"]:6d} maxlen {x["maxlen"]:7d} iterators {x["iters"]:5d} threads {dict(x["thr"])}')

# (a) lengths
bad_a = []
for lf in LIVES:
    for name in BIG_PH:
        if name in info[lf]['w'] and info[lf]['w'][name]['maxlen'] > 2 * P_BIG:
            bad_a.append((lf, name, info[lf]['w'][name]['maxlen']))
    allbig = max([info[lf]['w'][n]['maxlen'] for n in BIG_PH if n in info[lf]['w']], default=0)
    info[lf]['bigmax'] = allbig
ok_a1 = not bad_a and all(P_BIG <= info[lf]['bigmax'] <= 2 * P_BIG for lf in LIVES)
check('B3f(a1)', f'big phases: largest traced length per lifetime in [P_big, 2 P_big] = [{P_BIG}, {2 * P_BIG}], none above 2 P_big',
      ok_a1, f'bigmax per lifetime {dict((lf, info[lf]["bigmax"]) for lf in LIVES)}; over 2P: {bad_a}')
ok_a2 = True
det2 = []
for lf in LIVES:
    for name in ('load_small', 'scan_small_R1'):
        x = info[lf]['w'].get(name)
        if x is None:
            ok_a2 = False; continue
        lim = 0 if P_SMALL <= 32 else 2 * P_SMALL
        det2.append((lf, name, x['n'], x['maxlen']))
        if x['maxlen'] > lim:
            ok_a2 = False
check('B3f(a2)', f'small phases (P_small = {P_SMALL}): no growth when P_small <= 32, else lengths <= 2 P_small', ok_a2, str(det2))
mx = [info[lf]['bigmax'] for lf in LIVES]
check('B3f(a3)', 'the largest big length is the same for the settings, within one growth step (max/min <= 2)', bool(mx) and max(mx) <= 2 * min(mx) and min(mx) > 0,
      f'{dict((lf, info[lf]["bigmax"]) for lf in LIVES)}')
# (b) iterators / scratch bound (inferred)
det_b = []
ok_b = True
for lf in LIVES:
    x = info[lf]['w'].get('scan_big_R32')
    if x:
        rd = sum(v for k, v in x['thr'].items() if 'Read' in k or 'Native' in k or 'Request' in k)
        det_b.append((lf, 'R32 iterators with growth', x['iters'], 'events by thread kind', dict(x['thr'])))
        ok_b = ok_b and x['n'] > 0 and x['maxlen'] <= 2 * P_BIG
    y = info[lf]['w'].get('scan_big_R1')
    ok_b = ok_b and bool(y) and y['n'] > 0 and y['maxlen'] <= 2 * P_BIG
check('B3f(b)', f'per-iterator scratch <= 2 P_big in both scan phases (growth seen in each); peak scratch (R+4) x 2 P_big = {(32 + 4) * 2 * P_BIG} B at R=32 [inferred, from the executors]', ok_b, str(det_b))
# (c) control: memtable size follows the setting; flushes of t_small fall
big_on, sw = {}, {}
for lf in LIVES:
    ph, se = info[lf]['ph'], info[lf]['se']
    a, b = ph['load_big'][0], ph['scan_big_R32'][1]
    big_on[lf] = max([r[1] for r in se if a <= r[0] <= b] or [0])
    s0 = ph['load_small']
    sel = [r for r in se if s0[0] <= r[0] <= s0[1] + 4000]
    sw[lf] = (sel[-1][6] - sel[0][6]) if sel else None
order = [x for x in ('H64', 'H256', 'H1024') if x in big_on]
okc1 = len(order) == 3 and big_on['H64'] < big_on['H256'] < big_on['H1024']
okc2 = len(order) == 3 and None not in (sw['H64'], sw['H256'], sw['H1024']) and sw['H64'] >= sw['H256'] >= sw['H1024'] and sw['H64'] > sw['H1024']
check('B3f(c)', 'max t_big MemtableOnHeapDataSize (load_big..scan_big_R32) rises over 64 < 256 < 1024 MiB; t_small flushes during its load fall (>= >=, 64 > 1024)',
      okc1 and okc2, f'max big_on {big_on}; t_small switch count during load_small {sw}')
# (d) offheap_objects
if 'O256' in info and 'H256' in info:
    o, h = info['O256']['bigmax'], info['H256']['bigmax']
    boff = max([r[2] for r in info['O256']['se']] or [0])
    check('B3f(d)', 'offheap_objects: largest big length within [P_big, 2P_big] and within a factor 2 of heap_buffers 256 MiB; accounted off-heap size > 0',
          P_BIG <= o <= 2 * P_BIG and max(o, h) <= 2 * min(o, h) and boff > 0, f'O256 {o}, H256 {h}; max t_big MemtableOffHeapDataSize in O256 {boff}')
else:
    check('B3f(d)', 'offheap_objects lifetime present', False, 'O256 or H256 missing')
# validity
valid = True
det_v = []
for lf in LIVES:
    for name in ('load_small', 'load_big', 'scan_big_R1', 'scan_big_R32', 'scan_small_R1'):
        if name not in info[lf]['ph']:
            valid = False; det_v.append((lf, name, 'missing')); continue
    cells = [json.loads(l) for l in open(f'{D}/cells.jsonl') if l.strip()]
    ph_rec = {r['phase']: r['detail'] for r in cells if r.get('kind') == 'phase' and r['life'] == lf}
    for name in ('load_small', 'load_big'):
        d = ph_rec.get(name, {})
        if d.get('ok') != d.get('expected') or d.get('errors'):
            valid = False; det_v.append((lf, name, d))
    for name in ('scan_big_R1', 'scan_big_R32', 'scan_small_R1'):
        sc = ph_rec.get(name, {}).get('scan', {})
        if not sc.get('rows') or sc.get('errors'):
            valid = False; det_v.append((lf, name, sc))
    end = [r for r in cells if r.get('kind') == 'end' and r['life'] == lf]
    if not end or end[0]['error_lines']:
        det_v.append((lf, 'system.log ERROR lines', end[0]['error_lines'] if end else 'no end record'))
check('B3g-valid', 'loads complete without errors, scans read rows without errors, all five phases per lifetime, no ERROR/OOM in system.log', valid and not any('ERROR' in str(x) for x in det_v), str(det_v))
scans_grew = all(info[lf]['w'].get(n, {}).get('n', 0) > 0 for lf in LIVES for n in ('scan_big_R1', 'scan_big_R32'))
print('\nMATCHED ROW (B3g):')
if not valid or not scans_grew or not okc1 or not okc2:
    print('  Not confirmed (control did not move, scans produced no traced growth on t_big, or the run was incomplete) - see the lines above')
elif not res['B3f(a1)'] and any(v[2] > 2 * P_BIG for v in bad_a):
    print('  Mechanism mis-traced (a traced length above 2P)')
elif not res['B3f(a3)']:
    print('  Claim refuted (the largest traced length moves with memtable_heap_space by more than one growth step)')
elif all(res[k] for k in res):
    print('  Claim confirmed (traced lengths independent of memtable_heap_space, set by L; memtable size scales with the setting)')
else:
    print('  UNMATCHED: ' + ', '.join(k for k, v in res.items() if not v) + ' - do not edit B3f')
