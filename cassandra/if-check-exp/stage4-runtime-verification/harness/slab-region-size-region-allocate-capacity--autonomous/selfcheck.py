#!/usr/bin/env python3
"""Independent self-check (step 4) of slab-region-size-region-allocate-capacity--autonomous. Re-parses the RAW files (unit .out 'reading' lines,
jmx.csv, rss.csv, system.log, big.out, phases.json) without importing cluster-run.py and without reading the probe's check lines; the region rule
is recomputed here from the code of Region.allocate, and the frozen B2f/B3f numbers are typed in again as literals.
usage: selfcheck.py <run> (default run1). Prints one line per relation (ok / BAD); exit 0."""
import glob, json, os, re, statistics, sys

RUN = sys.argv[1] if len(sys.argv) > 1 else 'run1'
LG = os.path.expanduser(f'~/s4-b7-sr7-logs/{RUN}')
MIB = 1 << 20
bad = 0


def verdict(ok, msg):
    global bad
    bad += (not ok)
    print(('ok  ' if ok else 'BAD ') + msg)


def kv(path):
    d = {}
    for l in open(path, errors='replace'):
        m = re.match(r'STAGE4 reading (\w+)=(.*)$', l.strip())
        if m:
            d[m.group(1)] = m.group(2)
    return d


def regions(n, s, cap):
    if s > 131072:
        return 0
    r, off = 0, None
    for _ in range(n):
        while True:
            if off is None:
                r += 1; off = 0
            nw = off; off += s
            if nw + s <= cap:
                break
            off = None
    return r


# frozen B2f table (typed again): (REGION_SIZE, S) -> (regionCount, real, owns)
TABLE = {(MIB, 116509): (50, 52428800, 46603600), (MIB, 131072): (50, 52428800, 52428800), (MIB, 100000): (40, 41943040, 40000000),
         (MIB, 4096): (2, 2097152, 1638400), (MIB, 131073): (0, 52429200, 52429200), (MIB // 2, 116509): (100, 52428800, 46603600),
         (MIB // 2, 100000): (80, 41943040, 40000000), (2 * MIB, 116509): (24, 50331648, 46603600), (2 * MIB, 100000): (20, 41943040, 40000000)}
print('== unit tier: waste runs (raw readings vs the literal table)')
real_by = {}
for f in sorted(glob.glob(f'{LG}/unit/*-waste_offheap_*.out')):
    m = re.search(r'/(stock|v512|v2048)-waste_offheap_(\d+)_(\d+)\.out', f)
    v, S, N = m.group(1), int(m.group(2)), int(m.group(3))
    d = kv(f)
    cap = int(d['REGION_SIZE'])
    exp = TABLE.get((cap, S))
    reg, owns, real, dd, dc = int(d['regionCount']), int(d['owns']), int(d['real']), int(d['direct_delta']), int(d['direct_count_delta'])
    real_by[(v, S)] = real
    verdict(owns == N * S and int(d['pool_used']) == owns and d['other_owns'] == '0', f'{v} S={S}: owns {owns} == N*S, other counter 0')
    verdict(reg == regions(N, S, cap), f'{v} S={S}: regionCount {reg} == recomputed rule {regions(N, S, cap)}')
    if exp:
        verdict((reg, real, owns) == exp, f'{v} S={S}: (regionCount, real, owns) = {(reg, real, owns)} vs table {exp}; ratio {real / owns:.5f}')
    verdict(abs(dd - real) <= 65536, f'{v} S={S}: direct delta {dd} within 64 KiB of real {real} (count {dc})')
print('== unit tier: real vs REGION_SIZE (not proportional)')
for S in (116509, 100000):
    if all((v, S) in real_by for v in ('v512', 'stock', 'v2048')):
        r = real_by[('v2048', S)] / real_by[('v512', S)]
        verdict(0.9 <= r <= 1.1, f'S={S}: real 512K/1M/2M = {real_by[("v512", S)]}/{real_by[("stock", S)]}/{real_by[("v2048", S)]}; 2M/512K = {r:.3f} (4.0 would be proportional)')
print('== unit tier: limit runs')
LIT = {('offheap', 64, 116509): (575, 66992675, 72, 75497472), ('offheap', 128, 116509): (1151, 134101859, 144, 150994944), ('offheap', 64, 131072): (512, 67108864, 64, 67108864)}
for f in sorted(glob.glob(f'{LG}/unit/*-limit_*.out')):
    m = re.search(r'/(stock|v512|v2048)-limit_(offheap|heap)_(\d+)_(\d+)_(\d+)\.out', f)
    v, typ, Lm, S = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
    d = kv(f)
    cap = int(d['REGION_SIZE']); L = Lm * MIB
    n, owns, reg, real = int(d['allocations_done']), int(d['owns']), int(d['regionCount']), int(d['real'])
    verdict(n == L // S and owns == n * S <= L and d['worker_alive'] == 'true', f'{v} {typ} L={Lm} S={S}: stalled after {n} (floor(L/S)={L // S}), owns {owns} <= L, worker alive')
    verdict('MemtableAllocator$SubAllocator.allocate' in d['worker_stack'], f'{v} {typ} L={Lm} S={S}: stall stack starts {d["worker_stack"][:110]}')
    verdict(reg == regions(n, S, cap), f'{v} {typ} L={Lm} S={S}: regionCount {reg} == recomputed {regions(n, S, cap)}; real {real} = {real / L:.4f} L; real/owns {real / owns:.4f}')
    if v == 'stock' and (typ, Lm, S) in LIT:
        verdict((n, owns, reg, real) == LIT[(typ, Lm, S)], f'  literal B2f (n, owns, regions, real) {LIT[(typ, Lm, S)]}')
    if typ == 'heap':
        verdict(d['other_owns'] == '0' and abs(int(d['direct_delta'])) <= 65536 and abs(int(d['heap_used_delta']) - real) <= 3 * MIB,
                f'  heap run: offHeap counter {d["other_owns"]}, direct delta {d["direct_delta"]}, retained heap delta {d["heap_used_delta"]} vs real {real}')
for f in sorted(glob.glob(f'{LG}/unit/*-threads_*.out')):
    d = kv(f)
    rounds = [re.match(r'owns=(\d+) regionCount=(\d+) stash=(\d+)', v) for k, v in d.items() if k.startswith('round')]
    ok = all(int(r.group(1)) == 400 * 116509 and int(r.group(2)) == regions(400, 116509, MIB) for r in rounds)
    verdict(ok and len(rounds) == 20, f'threads: {len(rounds)} rounds, owns == 400*S and regionCount == 50 each; final stash {d["final_stash"]}')
    verdict(abs(int(d['direct_delta']) - (int(d['sum_regionCount']) + int(d['final_stash'])) * MIB) <= 65536,
            f'threads: direct delta {d["direct_delta"]} vs (sum regionCount {d["sum_regionCount"]} + stash {d["final_stash"]}) x 1 MiB')

print('== cluster tier (raw files)')
ST = {}
for arm in ('a64', 'a128', 'a64b', 'e64', 'f64', 'h64'):
    base = f'{LG}/cluster/{arm}'
    if not os.path.exists(base + '/phases.json'):
        print(arm, 'no phases.json')
        continue
    ph = json.load(open(base + '/phases.json'))
    w0, fl, pa = ph['work_ms'], ph['flush_ms'], ph['phaseB_ms']
    L = ph['L'] * MIB
    heap = ph['alloc'] == 'heap_buffers'
    dbase = float(ph['baseline_gauges']['direct'])
    samples = []
    blocked = []
    for l in open(base + '/jmx.csv'):
        p = l.strip().split(',')
        if len(p) != 7 or not p[0].isdigit():
            continue
        try:
            t = int(p[0]); off, on, bl, dr = float(p[1]), float(p[2]), float(p[3]), float(p[5])
        except ValueError:
            continue
        if w0 <= t < pa:
            samples.append((t, off, on, dr - dbase))
        if t >= ph['base_ms']:
            blocked.append(bl)
    acc = [(s[2] if heap else s[1]) for s in samples]
    peak_acc = max(acc); peak_dir = max(s[3] for s in samples)
    rho = [s[3] / s[1] for s in samples if s[1] >= 0.9 * L]
    rss = [int(x.split(',')[1]) for x in open(base + '/rss.csv').read().splitlines()[1:] if x.count(',') == 4 and x.split(',')[1].isdigit()
           and w0 <= int(x.split(',')[0]) < pa]
    rssd = max(rss) - ph['baseline']['RssAnon']
    flushes = sum(1 for l in open(base + '/system.log', errors='replace') if 'Enqueuing flush of ks.t' in l and 'MEMTABLE_LIMIT' in l)
    errs = [l.strip()[:120] for l in open(base + '/system.log', errors='replace') if l.startswith('ERROR')][:3]
    bigA, bigB = json.load(open(base + '/bigA.out')), json.load(open(base + '/bigB.out'))
    ST[arm] = dict(L=L, peak_acc=peak_acc, peak_dir=peak_dir, rho=statistics.median(rho) if rho else None, rssd=rssd, flushes=flushes, blocked=(blocked[0], blocked[-1]))
    print(f'{arm}: L={L / MIB:.0f} MiB S={ph["V"]} {ph["alloc"]}: peak_acc {peak_acc / MIB:.1f} MiB ({peak_acc / L:.3f} L), peak_dir {peak_dir / MIB:.1f} MiB, '
          f'rho median {ST[arm]["rho"]} over {len(rho)} samples, RssAnon peak delta {rssd / MIB:.1f} MiB, blocked {blocked[0]:.0f}->{blocked[-1]:.0f}, '
          f'MEMTABLE_LIMIT flushes {flushes}, client ok {bigA.get("ok")}+{bigB.get("ok")}/{ph["rows"]} err {bigA.get("err")}+{bigB.get("err")} phase-A {bigA.get("seconds")} s @ {bigA.get("rate")}/s, ERROR lines {len(errs)} {errs}')
bands = {'a64': (1.10, 1.20), 'a128': (1.10, 1.20), 'a64b': (1.10, 1.20), 'e64': (0.97, 1.07), 'f64': (1.11, 1.20)}
for a, (lo, hi) in bands.items():
    if a in ST and ST[a]['rho'] is not None:
        s = ST[a]
        verdict(lo <= s['rho'] <= hi, f'{a}: rho {s["rho"]:.4f} in [{lo}, {hi}]')
        verdict(0.9 * s['L'] <= s['peak_acc'] <= 1.05 * s['L'], f'{a}: peak_acc/L {s["peak_acc"] / s["L"]:.3f} in [0.90, 1.05]')
        verdict(s['blocked'][1] > s['blocked'][0] and s['flushes'] >= 2, f'{a}: blocked grew {s["blocked"]}, MEMTABLE_LIMIT flushes {s["flushes"]}')
if 'a64' in ST and 'a128' in ST:
    verdict(1.8 <= ST['a128']['peak_acc'] / ST['a64']['peak_acc'] <= 2.2, f'a128/a64 peak_acc {ST["a128"]["peak_acc"] / ST["a64"]["peak_acc"]:.3f} in [1.8, 2.2]')
    verdict(1.7 <= ST['a128']['peak_dir'] / ST['a64']['peak_dir'] <= 2.3, f'a128/a64 peak_dir {ST["a128"]["peak_dir"] / ST["a64"]["peak_dir"]:.3f} in [1.7, 2.3]')
    verdict(1.5 <= ST['a128']['rssd'] / ST['a64']['rssd'] <= 2.5, f'a128/a64 RssAnon delta {ST["a128"]["rssd"] / ST["a64"]["rssd"]:.3f} in [1.5, 2.5]')
if 'a64' in ST:
    verdict(ST['a64']['peak_dir'] > ST['a64']['L'], f'a64 peak_dir {ST["a64"]["peak_dir"] / MIB:.1f} MiB above L = 64 MiB')
print(f'selfcheck {RUN}: BAD lines {bad}')
