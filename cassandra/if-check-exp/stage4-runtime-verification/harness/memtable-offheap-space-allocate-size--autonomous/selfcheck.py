#!/usr/bin/env python3
"""Independent self-check (step 4) of memtable-offheap-space-allocate-size--autonomous. Re-parses the RAW files (unit .out files,
jmx.csv, rss.csv, system.log, stress.out, big.out) without importing cluster-run.py or reading the probe's check lines.
usage: selfcheck.py <run> (default run1). Prints one line per relation; exit 0."""
import glob, json, os, re, sys

RUN = sys.argv[1] if len(sys.argv) > 1 else 'run1'
LG = os.path.expanduser(f'~/s4-b7-mo-logs/{RUN}')
MIB = 1 << 20


def kv(path):
    d = {}
    for l in open(path, errors='replace'):
        m = re.match(r'STAGE4 reading (\w+)=(.*)$', l.strip())
        if m:
            d[m.group(1)] = m.group(2)
    return d


print('== unit tier (raw readings recomputed)')
bad = 0
rows = []
for f in sorted(glob.glob(f'{LG}/unit/fill-*.out')):
    m = re.search(r'fill-L(\d+)-S(\d+)\.out', f)
    L, S = int(m.group(1)) * MIB, int(m.group(2))
    d = kv(f)
    n, used, cap, reg = int(d['n']), int(d['used']), int(d['capacity_sum']), int(d['regions'])
    r = {'L': L // MIB, 'S': S, 'n': n, 'used': used, 'cap': cap, 'plateau': used <= L < used + S, 'exact': used == n * S and n == L // S,
         'oversize_exact': (cap == used) if S > 131072 else None, 'parked': d.get('extra_state_2s') in ('WAITING', 'TIMED_WAITING'),
         'released': d.get('extra_state_after_discard') == 'TERMINATED', 'rss_delta': int(d['rss_delta'])}
    r['rss_vs_used'] = round((r['rss_delta'] - used) / MIB, 1)
    r['rss_vs_cap'] = round((r['rss_delta'] - cap) / MIB, 1)
    rows.append(r)
    ok = r['plateau'] and r['exact'] and r['parked'] and r['released'] and r['oversize_exact'] in (None, True) and cap >= used
    bad += not ok
    print(('ok  ' if ok else 'BAD ') + json.dumps(r))
print(f'fill runs {len(rows)}; runs failing plateau/exact/parked/released/oversize/cap>=used: {bad}')
for f in sorted(glob.glob(f'{LG}/unit/blocking-*.out')):
    d = kv(f)
    L = int(re.search(r'L(\d+)', f).group(1)) * MIB
    print(os.path.basename(f), 'used_after_blocking > L:', int(d['used_after_blocking']) > L, '| writer finished:', d['blocking_writer_alive'].lower() == 'false',
          '| non-blocking extra parked:', d['nonblocking_extra_state'])
for f in sorted(glob.glob(f'{LG}/unit/control-*.out')):
    d = kv(f)
    print(os.path.basename(f), 'offHeap_used', d['offHeap_used'], 'onHeap_used', d['onHeap_used'], 'extra_alive_2s', d['extra_alive_2s'])
for L in (32, 64, 128):
    for S in (1024, 131073):
        f = f'{LG}/unit/fill-L{L}-S{S}.out'
        if os.path.exists(f):
            d = kv(f)
            print(f'L={L} S={S}: used/L = {int(d["used"]) / (L * MIB):.6f}')

print('== cluster tier (raw files)')
for arm in ('k128', 'k256', 'k512', 'b128', 'b256', 'b512', 'ctl', 'hp'):
    base = f'{LG}/cluster/{arm}'
    if not os.path.exists(base + '/phases.json'):
        print(arm, 'no phases.json')
        continue
    ph = json.load(open(base + '/phases.json'))
    w0, fl = ph['work_ms'], ph['flush_ms']
    off = on = 0.0
    blocked = []
    for l in open(base + '/jmx.csv'):
        p = l.strip().split(',')
        if len(p) != 5 or not p[0].isdigit():
            continue
        t = int(p[0])
        if w0 <= t <= fl:
            off = max(off, float(p[1])); on = max(on, float(p[2]))
        if t >= ph['base_ms']:
            blocked.append(float(p[3]))
    rss = [int(l.split(',')[1]) for l in open(base + '/rss.csv').read().splitlines()[1:] if l.count(',') == 4 and l.split(',')[1].isdigit()
           and w0 <= int(l.split(',')[0]) <= fl]
    nmt = [int(l.split(',')[1]) for l in open(base + '/nmt.csv').read().splitlines()[1:] if l.count(',') == 2 and l.split(',')[1].isdigit()]
    tbl = 'standard1' if ph['work'] == 'stress' else 'big'
    flushes = sum(1 for l in open(base + '/system.log', errors='replace') if 'Enqueuing flush of' in l and tbl in l)
    errs = [l.strip()[:150] for l in open(base + '/system.log', errors='replace') if l.startswith('ERROR')][:3]
    L = ph['L']
    print(f'{arm}: L={L} MiB tracked peak off={off/MIB:.1f} MiB ({off/(L*MIB):.3f} L) on={on/MIB:.1f} MiB | blocked {blocked[0]:.0f}->{blocked[-1]:.0f} | '
          f'flushes {flushes} | RssAnon base {ph["baseline"]["RssAnon"]/MIB:.0f} MiB peak delta {(max(rss) - ph["baseline"]["RssAnon"])/MIB:.1f} MiB | '
          f'NMT Other min/max {min(nmt)/MIB:.2f}/{max(nmt)/MIB:.2f} MiB | gauges after flush {ph["gauges_after_flush"]} | ERROR lines {len(errs)} {errs}')
    so = base + '/stress.out'
    if os.path.exists(so):
        txt = open(so, errors='replace').read()
        m = re.search(r'Total errors\s*:\s*([\d,]+)', txt); p = re.search(r'Total partitions\s*:\s*([\d,]+)', txt)
        print(f'   stress: total partitions {p and p.group(1)}, total errors {m and m.group(1)}')
    bo = base + '/big.out'
    if os.path.exists(bo):
        print('   big:', open(bo).read().strip()[:300])
