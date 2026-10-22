#!/usr/bin/env python3
"""Independent self-check of run 1 (results §5). usage: selfcheck.py <unit dir> <cluster dir>
Re-parses the raw files: the junit XML / ant logs (unit), and per lifetime the system.log slice, the TRACE slice, the 2-s RSS csv,
session.log and the stress output (cluster). It recomputes every number the conclusion uses from those files and compares with the
values the run script derived (probe.out, phases.json). Prints one CHECK line per item and a count."""
import csv, json, os, re, statistics, sys
U, D = sys.argv[1], sys.argv[2]
MiB = 1024 * 1024
res = []


def CHECK(name, cond, detail=''):
    res.append(bool(cond)); print(f"CHECK {'holds' if cond else 'FAILS'}: {name} -- {detail}")


# ---------------- unit ----------------
def probe_from_xml(p):
    s = open(p, errors='replace').read()
    m = re.search(r'<system-out><!\[CDATA\[(.*?)\]\]></system-out>', s, re.S)
    body = m[1] if m else s
    # the logger may split a line: join everything and split at each PROBE
    flat = re.sub(r'\n', ' ', body)
    return [x.strip().split('  ')[0].strip() for x in re.findall(r'(PROBE (?:setup|A|B|C)[^P]*?(?=PROBE|$))', flat)]


for rep in ('rep1', 'rep2'):
    probe = [l.strip() for l in open(os.path.join(U, f'{rep}.probe')) if l.startswith('PROBE')]
    ant = open(os.path.join(U, f'ant-{rep}.log'), errors='replace').read()
    CHECK(f'unit {rep}: junit 1 test, 0 failures, 0 errors', re.search(r'Tests run: 1, Failures: 0, Errors: 0', ant), '')
    CHECK(f'unit {rep}: 17 PROBE lines', len(probe) == 17, str(len(probe)))
    # second capture path: System.out -> the test JVM's logger -> the ant log ([main] SubstituteLogger lines), independent of probe.out
    logged = [m.group(1).strip() for m in re.finditer(r'\[main\] \S+ SubstituteLogger\.java:\d+ - (PROBE .*)', ant)]
    CHECK(f'unit {rep}: probe.out equals the PROBE lines the logger wrote to the ant log', logged == probe, f'{len(logged)} logged lines')
p1 = [l.strip() for l in open(os.path.join(U, 'rep1.probe')) if l.startswith('PROBE')]
p2 = [l.strip() for l in open(os.path.join(U, 'rep2.probe')) if l.startswith('PROBE')]
CHECK('unit: rep1 and rep2 identical', p1 == p2, '')
# B2f constants (case file), not the test's own computed values
s, m, F, d, SF = 5120, 160, 1280, 4960, 40960
CHECK('unit: setup line equals B2f arithmetic', p1[0] == f'PROBE setup sFull={SF} s={s} mPred={m} F={F} d={d}', p1[0])
pools = [0, F - 1, F, F + d - 1, F + d, F + 3 * d - 1, F + 3 * d, F + 7 * d, F + 8 * d - 1, F + 8 * d, 2 * SF]
B2F = {0: (0, 1280), 1279: (0, 1280), 1280: (0, 1280), 6239: (0, 1280), 6240: (1, 6240), 16159: (2, 11200), 16160: (3, 16160),
       36000: (7, 36000), 40959: (7, 36000), 40960: (8, 40960), 81920: (8, 40960)}   # the B2f table, typed in
A = [re.match(r'PROBE A P=(\d+) T=(\d+) kept=(\d+)', l) for l in p1 if l.startswith('PROBE A')]
CHECK('unit A: pools are the filed 11 values', [int(a[1]) for a in A] == pools, '')
for a in A:
    P, T, k = int(a[1]), int(a[2]), int(a[3])
    CHECK(f'unit A P={P}: kept, T as the B2f table; T<=P when P>=F', (k, T) == B2F[P] and (P < F or T <= P), f'kept={k} T={T} table={B2F[P]}')
B = [re.match(r'PROBE B P=(\d+) T=(\d+)', l) for l in p1 if l.startswith('PROBE B')]
CHECK('unit B: F <= T <= P + s/4 + F for the 4 rows', len(B) == 4 and all(F <= int(b[2]) <= int(b[1]) + s // 4 + F for b in B), str([(b[1], b[2]) for b in B]))
CHECK('unit B: T strictly decreasing S_full/2 -> S_full/8', int(B[0][2]) > int(B[1][2]) > int(B[2][2]), '')
c = [l for l in p1 if l.startswith('PROBE C')][0]
CHECK('unit C: T = S_full, all levels 128', f'T={SF} ' in c and re.search(r'levels=(128,){8}$', c), c)
lv = {int(a[1]): l for a, l in zip(A, [l for l in p1 if l.startswith('PROBE A')])}
CHECK('unit A: kept count equals number of 128s in the level string (line 341 successes)',
      all(int(re.search(r'kept=(\d+)', l)[1]) == re.search(r'levels=(\S*)', l)[1].split(',').count('128') for l in lv.values()), '')

# ---------------- cluster ----------------
P = json.load(open(os.path.join(D, 'phases.json')))
LT = P['lifetimes']
sess = open(os.path.join(D, 'session.log'), errors='replace').read()
st = open(os.path.join(D, 'stress-load.out'), errors='replace').read()
tp = re.search(r'Total partitions\s*:\s*([\d,]+)', st); te = re.search(r'Total errors\s*:\s*([\d,]+)', st)
CHECK('cluster: load stress wrote N partitions with 0 errors', tp and int(tp[1].replace(',', '')) == P['N'] and te and te[1] == '0', f'{tp[1] if tp else None} / {te[1] if te else None}')
runs = {}
for name, rec in LT.items():
    if name == 'L0-load':
        continue
    sl = open(os.path.join(D, f'system-{name}.log'), errors='replace').read()
    tr = open(os.path.join(D, f'isr-trace-{name}.log'), errors='replace').read()
    pool = re.search(r'memory pool size of (\d+) MB and a resize interval of (-?\d+) minutes', sl)
    CHECK(f'{name}: pool line in its own system.log slice equals phases ({rec.get("pool_MB")} MB)', pool and int(pool[1]) == rec.get('pool_MB'), pool[0] if pool else '')
    comp = [float(x) for x in re.findall(r'Completed resizing of index summaries; current approximate memory used: ([\d.E-]+) MiB', sl)]
    beg = [float(x) for x in re.findall(r'current spaced used is ([\d.E-]+) MiB', sl)]
    # trace split per run
    parts = re.split(r'Redistributing index summaries', tr)[1:]
    keeps = [len(re.findall(r'Using leftover space to keep \S*isc/t-', x)) for x in parts]
    resam = [len(re.findall(r'Re-sampling index summary for \S*isc/t-', x)) for x in parts]
    runs[name] = dict(comp=comp, beg=beg, keeps=keeps, resam=resam)
    print(f'  {name}: Completed T per run {comp}; Beginning T {beg}; trace keep/resample per run {list(zip(keeps, resam))}')
    first = rec.get('first') or rec.get('manual_run')
    CHECK(f'{name}: first Completed T in the raw slice equals the run script\'s T', comp and abs(comp[0] - first['T_MiB']) < 1e-9, f'{comp[:1]} vs {first["T_MiB"]}')
    CHECK(f'{name}: trace keep/resample of the first run equal the script\'s counts', keeps and (keeps[0], resam[0]) == (first['trace_keep_isc'], first['trace_resample_isc']), '')
    if len(comp) > 1 and name != 'L6-0b':
        CHECK(f'{name}: later runs in the lifetime leave T unchanged (stable)', max(comp) - min(comp) < 0.01, str(comp))
    # RSS: the 2-s sampler at the five sample times vs the script's direct reads
    rows = [(int(r['epoch_ms']), int(r['RssAnon_kB'])) for r in csv.DictReader(open(os.path.join(D, f'rss-{name}.csv'))) if r['RssAnon_kB'] not in ('None', '')]
    for tag in ('first', 'after_alter_max1', 'manual_run'):
        mm = rec.get(tag)
        if not mm:
            continue
        near = [min(rows, key=lambda r: abs(r[0] - t))[1] / 1024 for t, _, _ in mm['rss_samples']]
        CHECK(f'{name}/{tag}: 2-s sampler median at the sample times within 32 MiB of R', abs(statistics.median(near) - mm['R_MiB']) <= 32,
              f'{statistics.median(near):.1f} vs {mm["R_MiB"]:.1f}')
        mm['_R_sampler'] = statistics.median(near)
        if tag == 'first':
            end = mm['redist_seen_ms']; pre = [v / 1024 for t, v in rows if end - 20000 <= t <= end - 2000]
            mm['_pre'] = statistics.median(pre) if pre else None

g = lambda n: LT[n]['first']
T4, R4 = g('L1-4096')['T_MiB'], g('L1-4096')['R_MiB']
T0 = g('L5-0a')['T_MiB']
CHECK('positive control: T4096 >= 728 MiB (raw)', runs['L1-4096']['comp'][0] >= 728, f"{runs['L1-4096']['comp'][0]:.3f}")
CHECK('4096: every isc sstable kept by line 341, none re-sampled', runs['L1-4096']['resam'][0] == 0 and runs['L1-4096']['keeps'][0] == g('L1-4096')['sstables'],
      f"{runs['L1-4096']['keeps'][0]} kept of {g('L1-4096')['sstables']}")
for n, X in (('L2-default', 409), ('L3-400', 400), ('L4-100', 100)):
    T = runs[n]['comp'][0]
    CHECK(f'{n}: T <= X + 64 KiB (raw)', T <= X + 0.0625, f'{T:.4f} vs {X}')
    if runs[n]['beg'][0] - T > 0.01:
        CHECK(f'{n}: line 341 both outcomes (keep > 0, re-sample > 0)', runs[n]['keeps'][0] > 0 and runs[n]['resam'][0] > 0, f"{runs[n]['keeps'][0]}/{runs[n]['resam'][0]}")
    else:
        CHECK(f'{n}: run changed nothing and re-sampled no isc sstable', runs[n]['resam'][0] == 0, f"{runs[n]['keeps'][0]}/{runs[n]['resam'][0]}")
prev = {'L2-default': 'L1-4096', 'L3-400': 'L2-default', 'L4-100': 'L3-400', 'L5-0a': 'L4-100', 'L6-0b': 'L5-0a'}
for n, pn in prev.items():
    CHECK(f'{n}: Beginning T equals the last T of {pn} (Summary.db state carried across the restart)', abs(runs[n]['beg'][0] - runs[pn]['comp'][-1]) < 0.01,
          f"{runs[n]['beg'][0]:.3f} vs {runs[pn]['comp'][-1]:.3f}")
CHECK('X=0: 3 <= T0 <= 12 MiB and no keep', 3 <= runs['L5-0a']['comp'][0] <= 12 and runs['L5-0a']['keeps'][0] == 0, f"{runs['L5-0a']['comp'][0]:.3f}")
sig = abs(g('L6-0b')['R_MiB'] - g('L5-0a')['R_MiB']); sig2 = abs(g('L6-0b')['_R_sampler'] - g('L5-0a')['_R_sampler'])
CHECK('sigma <= 0.25*(T4096 - T0), by both RSS readers', sig <= 0.25 * (T4 - T0) and sig2 <= 0.25 * (T4 - T0), f'{sig:.1f} / {sig2:.1f}')
for n in ('L2-default', 'L3-400', 'L4-100', 'L5-0a'):
    dT = T4 - g(n)['T_MiB']
    for lab, a, b in (('script', R4, g(n)['R_MiB']), ('sampler', g('L1-4096')['_R_sampler'], g(n)['_R_sampler'])):
        CHECK(f'{n}: across-lifetime RSS fall >= 0.5*dT ({lab})', a - b >= 0.5 * dT, f'fall={a-b:.1f} dT={dT:.1f}')
    pre = g(n)['_pre']; dTw = runs[n]['beg'][0] - runs[n]['comp'][0]   # raw log values
    dRw = None if pre is None else pre - g(n)['_R_sampler']
    if dTw >= 16:   # D3
        CHECK(f'{n}: within-lifetime fall >= 0.5*dTw (same side as across)', dRw is not None and dRw >= 0.5 * dTw, f'{dRw} vs {dTw:.1f}')
    else:
        CHECK(f'{n}: run changed T by < 16 MiB; |within-lifetime fall| <= 3 sigma', dRw is not None and abs(dRw) <= 3 * sig2, f'{dRw} (sigma {sig2:.1f})')
L6 = runs['L6-0b']
CHECK('step 5: a run after the ALTER raised T above 2*T0 (raw: last Completed in L6)', L6['comp'][-1] > 2 * T0, f'{L6["comp"]}')
fu = re.findall(r'force upsample: (\d+)', open(os.path.join(D, 'system-L6-0b.log')).read())
CHECK('step 5: the ALTER run force-upsampled (INFO line)', any(int(x) > 0 for x in fu), str(fu))
L7 = LT['L7-step6']; r7 = runs['L7-step6']
CHECK('step 6: exactly one Completed line in L7 (the manual run)', len(r7['comp']) == 1, str(r7['comp']))
CHECK('step 6: manual run T <= 100 MiB + 64 KiB', r7['comp'][0] <= 100.0625, f"{r7['comp'][0]:.3f}")
mx = re.findall(r'sjk mx -b org.apache.cassandra.db:type=IndexSummaries -mg -f MemoryPoolSizeInMB\n((?:  \|.*\n)+)', sess)
vals = [float(x) for blk in mx for x in re.findall(r'^\s*\|\s*([\d.E-]+)\s*$', blk, re.M)]
CHECK('step 6: session.log JMX MemoryPoolSizeInMB readings are T_trig then T_after > 100', len(vals) >= 2 and vals[-1] > 100 and abs(vals[-1] - L7['T_after_jmx_MiB']) < 1e-6, str(vals))
st2 = open(os.path.join(D, 'stress-extra.out'), errors='replace').read()
tp2 = re.search(r'Total partitions\s*:\s*([\d,]+)', st2)
CHECK('step 6: extra stress wrote N2 partitions', tp2 and int(tp2[1].replace(',', '')) == P['N2'], tp2[1] if tp2 else '')
CHECK('no daemon or stress left (session.log last line)', re.search(r"daemons left: \[\]; stress left: 0", sess), '')
print(f'SELFCHECK: {sum(res)}/{len(res)} hold')
