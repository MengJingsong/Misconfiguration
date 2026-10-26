#!/usr/bin/env python3
"""Independent self-check (step 4) of max-cloned-size-allocate-size--autonomous. Re-parses the RAW files (unit .out 'reading' lines,
jmx.csv, rss.csv, system.log, big.out, phases.json) without importing cluster-run.py or reading the probe's check lines; the region
formula is recomputed here. usage: selfcheck.py <run> (default run1). Prints one line per relation; exit 0."""
import glob, json, math, os, re, sys

RUN = sys.argv[1] if len(sys.argv) > 1 else 'run1'
LG = os.path.expanduser(f'~/s4-b7-mc-logs/{RUN}')
MIB = 1 << 20


def kv(path):
    d = {}
    for l in open(path, errors='replace'):
        m = re.match(r'STAGE4 reading (\w+)=(.*)$', l.strip())
        if m:
            d[m.group(1)] = m.group(2)
    return d


def regions(n, s):
    if s > 131072:
        return n * s, n
    per = MIB // s
    r = math.ceil(n / per)
    return r * MIB, r


print('== unit tier (raw readings recomputed)')
bad = 0
rows = []
for f in sorted(glob.glob(f'{LG}/unit/fill-*.out')):
    m = re.search(r'fill-L(\d+)-S(\d+)\.out', f)
    L, S = int(m.group(1)) * MIB, int(m.group(2))
    d = kv(f)
    n, used = int(d['n']), int(d['used'])
    dd, dc = int(d['direct_delta']), int(d['count_delta'])
    cap, reg = regions(n, S)
    r = {'L': L // MIB, 'S': S, 'n': n, 'used': used, 'plateau': used <= L < used + S, 'exact': used == n * S == (L // S) * S,
         'direct_formula': (dd, dc) == (cap, reg), 'oversize_direct_eq_used': (dd == used) if S > 131072 else None,
         'waste_pct': round(100 * (dd - used) / used, 2), 'parked': d.get('extra_state_2s') in ('WAITING', 'TIMED_WAITING'),
         'released': d.get('extra_state_after_discard') == 'TERMINATED', 'rss_vs_used_MiB': round((int(d['rss_delta']) - used) / MIB, 1),
         'rss_vs_direct_MiB': round((int(d['rss_delta']) - dd) / MIB, 1), 'on_heap_0': d.get('onHeap_used') == '0'}
    rows.append(r)
    ok = r['plateau'] and r['exact'] and r['direct_formula'] and r['parked'] and r['released'] and r['oversize_direct_eq_used'] in (None, True) and r['on_heap_0']
    bad += not ok
    print(('ok  ' if ok else 'BAD ') + json.dumps(r))
print(f'fill runs {len(rows)}; failing plateau/exact/direct-formula/parked/released/oversize/on-heap: {bad}')
# same plateau either side of the threshold, per L
for L in (32, 64, 128):
    sub = {r['S']: r['used'] / (L * MIB) for r in rows if r['L'] == L}
    print(f'L={L}: used/L by S: ' + ', '.join(f'{s}:{v:.5f}' for s, v in sorted(sub.items())) + ' | max gap to L (bytes) ' +
          str(max(L * MIB - r['used'] for r in rows if r['L'] == L)))
for S in sorted({r['S'] for r in rows}):
    u = [r['used'] for r in sorted(rows, key=lambda r: r['L']) if r['S'] == S]
    if len(u) == 3:
        print(f'S={S}: used at L=32/64/128 = {u}; ratios {u[1]/u[0]:.4f}, {u[2]/u[0]:.4f}')
for f in sorted(glob.glob(f'{LG}/unit/blocking-*.out')):
    d = kv(f)
    L = int(re.search(r'L(\d+)', f).group(1)) * MIB
    print(os.path.basename(f), 'used_after_blocking > L:', int(d['used_after_blocking']) > L, '| writer finished:', d['blocking_writer_alive'].lower() == 'false',
          '| non-blocking extra:', d['nonblocking_extra_state'])
for f in sorted(glob.glob(f'{LG}/unit/control-*.out')):
    d = kv(f)
    L = int(re.search(r'L(\d+)', f).group(1)) * MIB; S = int(re.search(r'S(\d+)', f).group(1))
    print(os.path.basename(f), 'offHeap_used', d['offHeap_used'], 'onHeap_used', d['onHeap_used'], 'plateau ok:', int(d['onHeap_used']) == (L // S) * S,
          'extra', d['extra_state_2s'], 'direct', d['direct_delta'])

print('== cluster tier (raw files)')
MP = {}
for arm in ('s128', 's256', 's512', 'd128', 'd256', 'd512', 'cs', 'cd', 'hp'):
    base = f'{LG}/cluster/{arm}'
    if not os.path.exists(base + '/phases.json'):
        print(arm, 'no phases.json')
        continue
    ph = json.load(open(base + '/phases.json'))
    w0, fl = ph['work_ms'], ph['flush_ms']
    off = on = dmax = 0.0
    blocked = []
    for l in open(base + '/jmx.csv'):
        p = l.strip().split(',')
        if len(p) != 7 or not p[0].isdigit():
            continue
        t = int(p[0])
        if w0 <= t <= fl:
            off = max(off, float(p[1])); on = max(on, float(p[2])); dmax = max(dmax, float(p[5]))
        if t >= ph['base_ms']:
            blocked.append(float(p[3]))
    rss = [int(l.split(',')[1]) for l in open(base + '/rss.csv').read().splitlines()[1:] if l.count(',') == 4 and l.split(',')[1].isdigit()
           and w0 <= int(l.split(',')[0]) <= fl]
    dbase = float(ph['baseline_gauges']['direct'])
    flushes = sum(1 for l in open(base + '/system.log', errors='replace') if 'Enqueuing flush of' in l and 'big' in l)
    errs = [l.strip()[:150] for l in open(base + '/system.log', errors='replace') if l.startswith('ERROR')][:3]
    L = ph['L']
    rd = (max(rss) - ph['baseline']['RssAnon'])
    dd = dmax - dbase
    MP[arm] = (off, dd, rd, ph['V'], L)
    big = json.load(open(base + '/big.out'))
    print(f'{arm}: L={L} MiB V={ph["V"]} {ph["alloc"]} tracked peak off={off/MIB:.1f} MiB ({off/(L*MIB):.3f} L) on={on/MIB:.1f} MiB | blocked {blocked[0]:.0f}->{blocked[-1]:.0f} | '
          f'flushes {flushes} | direct peak delta {dd/MIB:.1f} MiB | RssAnon peak delta {rd/MIB:.1f} MiB | gauges after flush {ph["gauges_after_flush"]} | '
          f'client ok {big.get("ok")}/{ph["rows"]} err {big.get("err")} | ERROR lines {len(errs)} {errs}')
print('== net of control (arm minus control of the same V), rule of the harness README')
for a, (off, dd, rd, V, L) in MP.items():
    c = MP.get('cs' if V == 102400 else 'cd')
    if a in ('cs', 'cd', 'hp') or not c:
        continue
    nd, nr = dd - c[1], rd - c[2]
    print(f'{a}: net direct {nd/MIB:.1f} MiB ({nd/(L*MIB):.3f} L), net RssAnon {nr/MIB:.1f} MiB ({nr/(L*MIB):.3f} L), tracked/L {off/(L*MIB):.3f}')
for V, k in ((102400, 's'), (204800, 'd')):
    if all(f'{k}{L}' in MP for L in (128, 256, 512)):
        pk = [MP[f'{k}{L}'][0] for L in (128, 256, 512)]
        print(f'V={V}: tracked peak ratios {pk[1]/pk[0]:.3f}, {pk[2]/pk[0]:.3f}')
for L in (128, 256, 512):
    if f's{L}' in MP and f'd{L}' in MP:
        a, b = MP[f's{L}'][0], MP[f'd{L}'][0]
        print(f'L={L}: |peak(V=100K) - peak(V=200K)| / max = {abs(a-b)/max(a,b):.3f}')
