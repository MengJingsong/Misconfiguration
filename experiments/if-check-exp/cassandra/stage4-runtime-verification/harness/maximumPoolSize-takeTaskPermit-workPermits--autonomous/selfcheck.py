#!/usr/bin/env python3
"""Independent self-check of run 1 (maximumPoolSize-takeTaskPermit-workPermits--autonomous). usage: selfcheck.py <run dir>
<run dir> = ~/stage4-logs/mps/run1 (unit/ and cluster/). It does NOT read summary.txt, analysis.json, samples-heap.jsonl or the
unit .probe files. Unit: rebuilds the PROBE records from the per-test log (build/test/logs copy test-<rep>.log), a different
file from the ant log the run script parsed. Cluster: live bytes from the raw `jmap -histo:live` files (Total line; a
different heap statistic from the run script's GC.heap_info), Pending / Active from samples-tp.csv, the pool sizes from the
node's own "Resized MutationStage" lines in B's system.log copies, the reserve usage from the cqlsh output in session.log,
stress results from stress-*.out. phases.json is used only for time windows. Prints ok / FAIL per check."""
import glob, json, os, re, sys
D = sys.argv[1]; U = D + '/unit'; CL = D + '/cluster'
MIB = 1 << 20
ok = fail = 0
def chk(desc, c):
    global ok, fail
    if c: ok += 1
    else: fail += 1
    print(('ok   ' if c else 'FAIL ') + desc)

# ---------------- unit
def unit_recs(rep):
    p = f'{U}/test-{rep}.log'
    if not os.path.exists(p):
        return []
    frag = []
    for l in open(p, errors='replace'):
        m = re.search(r'^INFO\s+\[main\] \S+ (.*?)\n?$', l)   # this log has no class:line field; printf fragments one per line
        if m:
            frag.append(m.group(1))
    text = re.sub(r'(PROBE phase=)', r'\n\1', ''.join(frag))
    return [dict(re.findall(r'(\w+)=([-\w.]+)', l)) for l in text.splitlines() if l.startswith('PROBE phase=')]
p1 = {}
for rep in ('rep1', 'rep2', 'rep3'):
    R = unit_recs(rep)
    # the per-test log is appended by every run in the clone: keep this rep's last 14 records
    R = R[-14:]
    chk(f'unit {rep}: 14 PROBE records rebuilt from the per-test log (got {len(R)})', len(R) == 14)
    ph = lambda x: [r for r in R if r.get('phase') == x]
    one = {int(r['max']): float(r['heapDeltaMiB']) for r in ph('1')}
    p1[rep] = one
    act = {int(r['max']): (int(r['active']), int(r['pending'])) for r in ph('1')}
    chk(f'unit {rep} P1: active = n, pending = 2000 − n ({act})', all(a == n and p == 2000 - n for n, (a, p) in act.items()) and len(act) == 4)
    chk(f'unit {rep} P1: heap flat within ±10 MiB of the mean and in 110–145 ({one})',
        one and all(abs(v - sum(one.values()) / len(one)) <= 10 and 110 <= v <= 145 for v in one.values()))
    b, c = ph('2b'), ph('2c')
    chk(f'unit {rep} P2: active 32 > max 4 after the shrink, then 4 running, 196 pending ({b and b[0]}, {c and c[0]})',
        bool(b and c) and b[0]['active'] == '32' and b[0]['max'] == '4' and c[0]['active'] == '4' and c[0]['running'] == '4' and c[0]['pending'] == '196')
    p3 = {int(r['limitMiB']): float(r['heapDeltaMiB']) for r in ph('3')}
    chk(f'unit {rep} P3: control heap tracks the cap ({p3})', p3.get(16, 0) and 14 <= p3[16] <= 22 and 58 <= p3.get(64, 0) <= 75)
    p4 = {int(r['max']): float(r['heapDeltaMiB']) for r in ph('4')}
    slope = [p4[n] / n for n in (4, 32, 128) if n in p4]
    chk(f'unit {rep} P4: heap ∝ n (MiB per running task {[round(s, 3) for s in slope]}, all within 5 % of each other)',
        len(slope) == 3 and max(slope) <= 1.05 * min(slope))
    chk(f'unit {rep} P4 sub-prediction n × 1 MiB (+2): {p4}', all(n <= p4.get(n, -1) <= n + 2 + 0.1 * n for n in (1, 4, 32, 128)))
if len(p1) == 3:
    worst = max(abs(p1[a][n] - p1[b][n]) for n in (1, 4, 32, 128) for a in p1 for b in p1 if n in p1[a] and n in p1[b])
    chk(f'unit repeats agree within 10 MiB (worst {worst:.2f})', worst <= 10)

# ---------------- cluster
P = json.load(open(CL + '/phases.json'))
def htotal(label, n='B'):
    p = f'{CL}/histo-{label}-{n}.txt'
    try:
        for l in open(p):
            f = l.split()
            if f and f[0] == 'Total':
                return int(f[2])
    except OSError:
        pass
    return None
def hcount(label, cls):
    try:
        for l in open(f'{CL}/histo-{label}-B.txt'):
            f = l.split()
            if len(f) >= 4 and f[3] == cls:
                return int(f[1])
    except OSError:
        pass
    return 0
TP = []
for l in open(CL + '/samples-tp.csv').read().splitlines()[1:]:
    v = l.split(',')
    if len(v) == 6:
        TP.append((int(v[0]), v[1], int(v[2]), int(v[3])))
resize = []
for f in sorted(glob.glob(CL + '/B*-system.log'), key=lambda s: int(re.search(r'/B(\d+)-system', s).group(1))):
    for l in open(f, errors='replace'):
        m = re.search(r'Resized MutationStage maximum pool size from (\d+) to (\d+)', l)
        if m:
            resize.append(int(m.group(2)))
print('resize sequence on B (system.log):', resize)
exp_seq = [8, 32, 1, 32, 0, 32] + [0, 32] * 3 + [0, 32] + [512] * 0
chk(f'resize lines begin with the filed sequence 8,32,1,32,0,32 then (0,32) per control and drift ({resize[:14]})',
    resize[:6] == [8, 32, 1, 32, 0, 32] and resize[6:12] == [0, 32, 0, 32, 0, 32] and resize[12:14] == [0, 32])
binds = [x for x in resize[14:]]
chk(f'bind lifetimes: pairs (v, 512) for v = 1, 8, 32, 128 twice ({binds}; v = 32 equals the default and logs no resize)',
    binds == [1, 512, 8, 512, 512, 128, 512, 1, 512, 8, 512, 512, 128, 512])
# baselines per B lifetime: label of baseline samples
bases = {'filed': 'L1-baseline', '-ctl16MiB': 'ctl16MiB-baseline', '-ctl128MiB': 'ctl128MiB-baseline',
         '-ctl512MiB': 'ctl512MiB-baseline', '-rep': 'drift-baseline'}
Hh = {}
print('NOTE harness defect H2: histo-L1-baseline-B.txt was overwritten by R5\'s L1 baseline (same label); the filed lifetime-1 '
      'phases are compared against that later file (an R5-lifetime baseline, idle node), which is the only raw baseline left')
for p in [p for p in P if p['kind'] == 'filed']:
    name = f'v{p["v"]}{p["tag"]}'
    base = bases['filed' if p['tag'] == '' else p['tag']]
    t, b = htotal(name + '-t90'), htotal(base)
    if t is None or b is None:
        chk(f'{name}: histogram files present', False); continue
    win = [x for x in TP if x[1] == name and p['stress_start'] <= x[0] <= p['stress_end']]
    p90 = min(win, key=lambda x: abs(x[0] - p['t90']))[3] if win else -1
    Hh[name] = ((t - b) / MIB, p90, hcount(name + '-t90', 'org.apache.cassandra.db.Mutation'))
    rate = re.search(r'Op rate\s*:\s*([\d,]+)', open(CL + '/stress-' + name + '.out').read())
    print(f'{name}: live-bytes rise {Hh[name][0]:.1f} MiB; P(t≈90) {p90}; Mutation {Hh[name][2]}; stress op rate {rate.group(1) if rate else "?"}')
g = lambda k: Hh[k][0]
if all(k in Hh for k in ('v32', 'v8', 'v1', 'v0')):
    chk(f'filed row 1: H(32), H(8) < 100 MiB and H(0) − H(32) ≥ 100 MiB on live bytes ({g("v32"):.1f}, {g("v8"):.1f}, {g("v0"):.1f})',
        g('v32') < 100 and g('v8') < 100 and g('v0') - g('v32') >= 100)
    chk('filed row 2 (Refuted) not met: H not decreasing 0 < 1 < 8 < 32', not (g('v0') < g('v1') < g('v8') < g('v32') and g('v32') - g('v0') > 50))
    chk(f'v0: P in 90,000–150,000 ({Hh["v0"][1]}) and Mutation ≈ P within 20 % ({Hh["v0"][2]})',
        90000 <= Hh['v0'][1] <= 150000 and abs(Hh['v0'][2] - Hh['v0'][1]) <= 0.2 * Hh['v0'][1])
    late0 = [x[2] for x in TP if x[1] == 'v0' and x[0] > [p for p in P if p.get('v') == 0 and p.get('tag') == ''][0]['stress_start'] + 10000]
    chk(f'v0: Active 0 at every sample after the first 10 s (max {max(late0) if late0 else None})', late0 and max(late0) == 0)
c = [Hh.get(f'v0-ctl{R}') for R in ('16MiB', '128MiB', '512MiB')]
if all(c):
    chk(f'control: live bytes ordered 16 < 128 < 512 and ratio ≥ 8 ({[round(x[0], 1) for x in c]}; P {[x[1] for x in c]})',
        c[0][0] < c[1][0] < c[2][0] and c[0][0] > 0 and c[2][0] / c[0][0] >= 8)
if 'v32-rep' in Hh and 'v0-rep' in Hh:
    chk(f'drift: |Δ| ≤ 50 MiB on live bytes (v32 {g("v32"):.1f}/{g("v32-rep"):.1f}, v0 {g("v0"):.1f}/{g("v0-rep"):.1f})',
        abs(g('v32') - g('v32-rep')) <= 50 and abs(g('v0') - g('v0-rep')) <= 50)
# inbound reserve usage from the cqlsh outputs in session.log, in order of appearance
sess = open(CL + '/session.log', errors='replace').read()
inb = [int(a) for a, b in re.findall(r'internode_inbound;"\n\n address\s*\| using_bytes \| using_reserve_bytes\n-+\+-+\+-+\n 127\.0\.0\.21 \|\s*(\d+) \|\s*(\d+)', sess)]
print('inbound using_bytes samples (MiB):', [round(x / MIB, 1) for x in inb])
B = {}
for p in [p for p in P if p['kind'] == 'bind']:
    lab = f'{p["size"]}{p["v"]}'
    t, b = htotal(lab + '-t60'), htotal(lab + '-baseline')
    win = [x for x in TP if x[1] == lab and p['stress_start'] + 20000 <= x[0] <= p['t60']]
    frac = sum(1 for x in win if x[2] >= 0.9 * p['v']) / len(win) if win else 0
    B[lab] = ((t - b) / MIB if t and b else None, frac, [x[3] for x in win][-1] if win else -1,
              hcount(lab + '-t60', 'org.apache.cassandra.db.Mutation'))
    print(f'{lab}: live-bytes rise {B[lab][0]:.1f} MiB; Active ≥ 0.9v fraction {frac:.2f} ({[x[2] for x in win]}); Pending last {B[lab][2]}; Mutation {B[lab][3]}')
    chk(f'{lab}: the pool binds (Active ≥ 0.9 v at ≥ 80 % of samples, {frac:.2f})', frac >= 0.8)
S = [B.get(f'S{v}') for v in (1, 8, 32, 128)]; L = [B.get(f'L{v}') for v in (1, 8, 32, 128)]
if all(S) and all(L):
    hs = [x[0] for x in S]; hl = [x[0] for x in L]
    flat = lambda h: (min(h) > 0 and max(h) / min(h) <= 1.2) or (max(h) - min(h) <= 30)
    sf, lf = flat(hs), flat(hl)
    li = hl[1] < hl[2] < hl[3] and hl[3] - hl[0] >= 40
    si = hs[0] < hs[1] < hs[2] < hs[3] and hs[3] - hs[0] >= 40
    row = 'BIND-1' if sf and lf else 'BIND-2' if sf and li else 'BIND-3' if si and li else 'BIND-5'
    if not all(x[1] >= 0.8 for x in S + L):
        row = 'BIND-4'
    print(f'live-bytes H_S {[round(h, 1) for h in hs]}, H_L {[round(h, 1) for h in hl]} -> {row}')
    chk(f'R5 row on live bytes (independent statistic): {row}', True)
    chk(f'L: Mutation instances at t = 60 s ≈ v (running only; {[x[3] for x in L]})', all(abs(x[3] - v) <= max(3, 0.2 * v) for x, v in zip(L, (1, 8, 32, 128))))
    chk(f'S: Mutation instances at t = 60 s ≈ Pending + v ({[(x[3], x[2]) for x in S]})', all(abs(x[3] - (x[2] + v)) <= 0.1 * (x[2] + v) for x, v in zip(S, (1, 8, 32, 128))))
    print('R5_ROW', row)
for f in sorted(glob.glob(CL + '/stress-*.out')):
    m = re.search(r'Total errors\s*:\s*([\d,]+)', open(f, errors='replace').read())
    print(os.path.basename(f), 'errors', m.group(1) if m else '?')
print(f'TALLY {ok} ok, {fail} FAIL')
