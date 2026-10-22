#!/usr/bin/env python3
"""Self-check (step 4) for index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous.
Re-parses the raw files, not phases.json's derived numbers (phases.json is read only to compare against):
unit: the PROBE lines of the ant log (the logger's capture path) against probe.out, and against the B2f values typed in here;
cluster: system-<life>.log (every Beginning / downsample / Completed line, in order), r258-<life>.log, isr-trace-<life>.log
(split per run), rss-<life>.csv (a second reader of RssAnon), stress-*.out and session.log.
usage: selfcheck.py <unit dir> <cluster dir>"""
import csv, json, re, statistics, sys

U, D = sys.argv[1], sys.argv[2]
n_ok = n_all = 0
fails = []


def chk(name, cond, detail=''):
    global n_ok, n_all
    n_all += 1; n_ok += bool(cond)
    if not cond:
        fails.append(name)
    print(f'{"HOLDS" if cond else "FAILS"}: {name} -- {detail}')


# ---------------- unit ----------------
probe = [l.strip() for l in open(f'{U}/rep1.probe') if l.startswith('PROBE')]
antl = [re.sub(r'^.*?(PROBE .*)$', r'\1', l.strip()) for l in open(f'{U}/ant-rep1.log') if 'PROBE ' in l]
chk('unit: ant-log PROBE lines equal probe.out', antl == probe, f'{len(antl)} vs {len(probe)} lines')
chk('unit: rep2 identical to rep1', open(f'{U}/rep2.probe').read() == open(f'{U}/rep1.probe').read())
rows = {l.split()[1]: dict(kv.split('=', 1) for kv in l.split()[2:] if '=' in kv) for l in probe}
# typed in from the case file B2c arithmetic and B2f: S = 1250 x 20 = 25,000 B; F = 40 x 20 = 800 B; N = 10
S, F, N = 25000, 800, 10
chk('unit: S and F as B2c arithmetic', int(rows['setup']['S']) == S and int(rows['floor']['F']) == F and int(rows['setup']['Fp']) == F,
    f"S={rows['setup']['S']} F={rows['floor']['F']} Fp={rows['setup']['Fp']}")
P_exp = {'P0': N * F // 2, 'P1': N * F + (S - F) // 2, 'P2': N * F + 7 * (S - F) // 2, 'P3': N * F + 15 * (S - F) // 2, 'P4': N * S + 1024}
k_exp = {'P0': 0, 'P1': 0, 'P2': 3, 'P3': 7, 'P4': 10}
for p in ('P0', 'P1', 'P2', 'P3', 'P4'):
    r = rows[p]; P = int(r['P']); R = int(r['R_refl']); k = int(r['k']); T = int(r['T'])
    chk(f'unit {p}: P as B2b', P == P_exp[p], f'{P} vs {P_exp[p]}')
    chk(f'unit {p}: both operand readers = P - N*F', R == int(r['R_compl']) == P - N * F, f'{R} {r["R_compl"]} {P - N*F}')
    chk(f'unit {p}: k as B2f table', k == k_exp[p], f'{k} vs {k_exp[p]}')
    chk(f'unit {p}: T = k*S + (N-k)*F', T == k * S + (N - k) * F, f'{T}')
    chk(f'unit {p}: branch sign (R>0 except P0)', (R > 0) == (p != 'P0'))
    chk(f'unit {p}: T<=P except P0 (T = N*F > P0)', (T <= P) if p != 'P0' else (T == N * F > P))
    chk(f'unit {p}: reset to full before (tBefore = N*S)', int(r['tBefore']) == N * S)
chk('unit: levels at P2 hold three 128s', rows['P2']['levels'].split(',').count('128') == 3, rows['P2']['levels'])

# ---------------- cluster ----------------
PH = json.load(open(f'{D}/phases.json'))
MiB = 1 << 20
sess = open(f'{D}/session.log').read()
tot = [int(x.replace(',', '')) for x in re.findall(r'Total partitions\s*:\s*([\d,]+)', ''.join(open(f'{D}/stress-load{i:02d}.out').read() for i in range(20)))]
errs = re.findall(r'Total errors\s*:\s*([\d,]+)', ''.join(open(f'{D}/stress-load{i:02d}.out').read() for i in range(20)))
chk('load: 20 batches x 100,000 partitions, 0 errors', tot == [100000] * 20 and all(e == '0' for e in errs), f'{tot[:3]}… errors {set(errs)}')
m = re.search(r'Index summary off heap memory used: (\d+)', sess)
chk('load: first isr tablestats = 2,000,000 x 1012 B (distinct 1000-byte keys)', m and int(m[1]) == 2_000_000 * 1012, m and m[1])


def runs_from(syslog):
    txt = open(syslog).read()
    out = []
    for seg in txt.split('Redistributing index summaries')[1:]:
        b = re.search(r'memory pool size (\d+) MiB; current spaced used is ([\d.E-]+) MiB', seg)
        c = re.search(r'Completed resizing of index summaries; current approximate memory used: ([\d.E-]+) MiB', seg)
        d = re.search(r'downsample: (\d+), force resample: (\d+), upsample: (\d+), force upsample: (\d+)', seg)
        out.append((int(b[1]), float(b[2]), float(c[1]) if c else None, tuple(map(int, d.groups())) if d else None))
    return out, txt


r0, t0 = runs_from(f'{D}/system-L0-main.log')
r1, t1 = runs_from(f'{D}/system-L1-auto.log')
pools = [x[0] for x in r0]
chk('cluster: L0 run order 4096,8192,1024,8192,512,8192,64,8192,8,8192', pools == [4096, 8192, 1024, 8192, 512, 8192, 64, 8192, 8, 8192], str(pools))
chk('cluster: L0 pool line 64 MB, L1 pool line 409 MB', 'memory pool size of 64 MB' in t0 and 'memory pool size of 409 MB' in t1)
chk('cluster: L1 one run at 409', [x[0] for x in r1] == [409], str([x[0] for x in r1]))
r258_0 = [tuple(map(int, x)) for x in re.findall(r'remainingSpace=(-?\d+) memoryPoolCapacity=(-?\d+)', open(f'{D}/r258-L0-main.log').read())]
r258_1 = [tuple(map(int, x)) for x in re.findall(r'remainingSpace=(-?\d+) memoryPoolCapacity=(-?\d+)', open(f'{D}/r258-L1-auto.log').read())]
chk('cluster: one R258 line per run, pools match', [p // MiB for _, p in r258_0] == pools and [p // MiB for _, p in r258_1] == [409])
tr0 = open(f'{D}/isr-trace-L0-main.log').read().split('Redistributing index summaries')[1:]
tr1 = open(f'{D}/isr-trace-L1-auto.log').read().split('Redistributing index summaries')[1:]
keeps = [len(re.findall(r'Using leftover space to keep \S*isr/t-', s)) for s in tr0 + tr1]
allkeeps = [s.count('Using leftover space to keep') for s in tr0 + tr1]
runs = r0 + r1; rr = r258_0 + r258_1
k_tab = {4096: 20, 1024: 10, 512: 5, 409: 4, 64: 0, 8: 0}
# full and floor totals from the raw lines: the first Beginning is the full state
T_full = r0[0][1]
for i, (pool, before, T, dcounts) in enumerate(runs):
    R = rr[i][0]
    if pool == 8192:
        chk(f'cluster restore #{i}: T back to full (>= {T_full - 1:.1f})', T >= T_full - 1, f'T={T}')
        continue
    chk(f'cluster C={pool}: started from full', abs(before - T_full) < 1, f'before={before}')
    if pool >= 64:
        chk(f'cluster C={pool}: T <= C + 1 (row 1)', T <= pool + 1, f'T={T:.3f}')
        chk(f'cluster C={pool}: R258 > 0', R > 0, f'R={R} ({R / MiB:.3f} MiB)')
    else:
        chk(f'cluster C={pool}: R258 < 0 and T > C (floor overshoot)', R < 0 and T > pool, f'R={R} T={T:.3f}')
    chk(f'cluster C={pool}: keep(isr) = B3f table k', keeps[i] == k_tab[pool], f'{keeps[i]} vs {k_tab[pool]}')
    chk(f'cluster C={pool}: no keep line when R258 <= 0', R > 0 or allkeeps[i] == 0)
    chk(f'cluster C={pool}: matches phases.json T', any(abs(v.get('T_MiB', -1) - T) < 1e-6 for life in PH['lifetimes'].values() for v in life['runs'].values()))


def rss(path):
    return [(int(r['epoch_ms']), int(r['RssAnon_kB']) / 1024) for r in csv.DictReader(open(path)) if r['RssAnon_kB'] not in ('None', '')]


for life, csvf in (('L0-main', 'rss-L0-main.csv'), ('L1-auto', 'rss-L1-auto.csv')):
    s = rss(f'{D}/{csvf}')
    for tag, r in PH['lifetimes'][life]['runs'].items():
        t_trig = r['r258'][0][0]
        pre = [v for t, v in s if t_trig - 32000 <= t < t_trig - 1000]
        post_t0 = r['rss_after'][0][0]
        post = [v for t, v in s if post_t0 - 1000 <= t <= r['rss_after'][-1][0] + 1000]
        if not pre or not post:
            chk(f'rss reader 2 {tag}', False, 'no samples'); continue
        Rb, Ra = statistics.median(pre), statistics.median(post)
        dT = r['T_before_MiB'] - r['T_MiB']
        chk(f'rss reader 2 {tag}: agrees with script within 32 MiB', abs(Rb - r['R_before_MiB']) <= 32 and abs(Ra - r['R_after_MiB']) <= 32,
            f'{Rb:.1f}/{Ra:.1f} vs {r["R_before_MiB"]:.1f}/{r["R_after_MiB"]:.1f}')
        chk(f'rss reader 2 {tag}: fall {Rb - Ra:.1f} ~ dT {dT:.1f} (max(0.15 dT, 64))', abs((Rb - Ra) - dT) <= max(0.15 * abs(dT), 64))
neg = PH['lifetimes']['L0-main']['negative_control']
s = rss(f'{D}/rss-L0-main.csv')
win = [v for t, v in s if neg['start_ms'] <= t <= neg['rss'][-1][0]]
chk('negative control: 2-s sampler range <= 64 MiB over the window', win and max(win) - min(win) <= 64, f'n={len(win)} range={max(win) - min(win):.1f} MiB')
chk('negative control: no Redistributing between the C=8 restore and the stop', len(r0) == 10)
print(f'SELF-CHECK: {n_ok} / {n_all} hold; failing: {fails or "none"}')
