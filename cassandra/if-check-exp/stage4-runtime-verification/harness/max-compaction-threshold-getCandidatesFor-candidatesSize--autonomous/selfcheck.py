#!/usr/bin/env python3
"""selfcheck.py <unit dir> <cluster dir> -- independent re-derivation of the run-1 claims from the raw files (does not import or call the analysis scripts).
unit dir: ant.log (console echo of the readings), readings.txt.  cluster dir: run-*/ (system.log.copy, tablestats-*.txt, files-before.json, samples.jsonl,
getcompactionthreshold.txt, cassandra.yaml.used, exit.txt, meta.json) and build-*/ (stress-*.txt, tablestats-*.txt)."""
import sys, re, os, json, glob, datetime, statistics
UD, CD = sys.argv[1], sys.argv[2]
bad = []
def ok(name, cond, note=''):
    print(('holds    ' if cond else 'DOES NOT HOLD ') + name + (' -- ' + note if note else ''))
    if not cond: bad.append(name)

# ---------------- unit tier
echo = {}
for l in open(f'{UD}/ant.log', errors='replace'):
    m = re.search(r'SubstituteLogger\.java:\d+ - R (\S+) (\S+) (.*)$', l.rstrip())     # the test's System.out line, echoed by the test logger
    if m: echo[(m.group(1), m.group(2))] = m.group(3)
rd = {}
for l in open(f'{UD}/readings.txt'):
    p = l.rstrip('\n').split(' ', 3); rd[(p[1], p[2])] = p[3]
ok('U0 console echo of the readings in ant.log = readings.txt', echo == rd, f'{len(echo)} vs {len(rd)} readings')
ok('U1 JUnit: 5 tests, 0 failures, 0 errors', re.search(r'Tests run: 5, Failures: 0, Errors: 0', open(f'{UD}/ant.log', errors='replace').read()) is not None)
tags = sorted({k[1].rsplit('.', 1)[0] for k in rd if k[0] == 'step3' and k[1].endswith('.candidateCount')})
def v(tag, f): return int(rd[('step3', f'{tag}.{f}')])
nfix = {'small.setter': 100, 'large.setter': 100, 'groups': 100, 'small20': 20}
viol_l0 = viol_gate = over = 0
for t in tags:
    N = v(t, 'knobN'); fam = 'small20' if t.startswith('small20') else 'groups' if t.startswith('groups') else 'large.setter' if t.startswith('large') else 'small.setter'
    n0 = nfix.get('small.setter' if fam == 'small.setter' else fam)
    if v(t, 'candidateL0') != min(N, n0): viol_l0 += 1
    if (v(t, 'candidateL0Bytes') > v(t, 'gateBytes')) != (v(t, 'candidateL1') > 0) and fam != 'groups': viol_gate += 1
    if v(t, 'candidateCount') > N: over += 1
ok('U2 L0 count = min(N, L0 sstables) in all probes, never above N', viol_l0 == 0, f'{len(tags)} probes')
ok('U3 L1 present iff L0 candidate bytes > gate bytes (strict) in all probes with an L1', viol_gate == 0)
ok('U4 some probes have candidateCount > N (L1 appended after the cap)', over > 0, f'{over} probes')
big = {N: v(f'large.setterN{N}.stcsL0On.gate160', 'candidateL1') for N in (4, 6, 8, 12, 32, 64, 100)}
ok('U5 large class: L1 absent at N=4, 6 and present at N>=8..100 (gate between 6 and 8 x ~21 MiB)', big[4] == 0 and big[6] == 0 and all(big[N] == 10 for N in (8, 12, 32, 64, 100)), str(big))
stcs = {N: int(rd[('control', f'large.setter.stcs.N{N}.count')]) for N in (4, 6, 8, 12, 32, 64, 100)}
ok('U6 STCS control (positive control): bucket size = N for N<=100', all(stcs[N] == N for N in stcs), str(stcs))
ok('U7 fixture overlaps as designed (100 L0: 4950 pairs, L0-L1 1000, L1-L1 0; groups 150)',
   rd[('fixture', 'small.setter.overlapPairsL0L0')] == '4950' and rd[('fixture', 'small.setter.overlapPairsL0L1')] == '1000' and rd[('fixture', 'small.setter.overlapPairsL1L1')] == '0' and rd[('fixture', 'groups.overlapPairsL0L0')] == '150')
src = '/proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledManifest.java'
sl = open(src).read().splitlines()
ok('U8 pinned source at the cited lines (548 trim, 551 subList, 557 gate, 567 union with L1)',
   'candidates.size() > cfs.getMaximumCompactionThreshold()' in sl[547] and 'subList(0, cfs.getMaximumCompactionThreshold())' in sl[550] and 'getTotalBytes(candidates) > maxSSTableSizeInBytes' in sl[556] and 'Sets.union(candidates, l1overlapping)' in sl[566])

# ---------------- cluster tier
def tstamp(line): return datetime.datetime.strptime(re.search(r'(\d{4}-\d\d-\d\dT[\d:,]+)', line).group(1), '%Y-%m-%dT%H:%M:%S,%f').replace(tzinfo=datetime.timezone.utc).timestamp()
rows = {}
for d in sorted(glob.glob(f'{CD}/run-*-N*')):
    if not os.path.isdir(d): continue
    m = re.search(r'run-(lcs|stcs)-N(\d+)$', d)
    role, N = m.group(1), int(m.group(2))
    ex = open(d + '/exit.txt').read().strip()
    yaml = open(d + '/cassandra.yaml.used').read()
    thr = open(d + '/getcompactionthreshold.txt').read()
    lines = [l for l in open(d + '/system.log.copy', errors='replace') if 'standard1' in l]
    comp = [l for l in lines if 'Compacting (' in l]
    first = comp[0]; uid = re.search(r'Compacting \(([0-9a-f-]+)\)', first).group(1)
    entries = [e.strip() for e in first.split('[', 1)[1].rsplit(']', 1)[0].split(', ') if e.strip()]
    lev = [(re.search(r'(nb-(\d+)-big-Data\.db)', e).group(1), int(re.search(r'(nb-(\d+)-big-Data\.db)', e).group(2)), int(e.rsplit('level=', 1)[1])) for e in entries]
    before = json.load(open(d + '/files-before.json'))
    tsb = open(d + '/tablestats-before.txt').read()
    ml = re.search(r'SSTables in each level: \[(.*?)\]', tsb)
    cnt = [int(x.split('/')[0]) for x in ml.group(1).replace(' ', '').split(',')] if ml else [0, 0]    # STCS tables print no level line
    nsst = int(re.search(r'SSTable count: (\d+)', tsb).group(1))
    done = [l for l in lines if 'Compacted (' in l and uid in l]
    t0 = tstamp(first); t1 = tstamp(done[0])
    second = [l for l in comp[1:] if tstamp(l) < t1]
    S = [json.loads(x) for x in open(d + '/samples.jsonl')]
    meta = json.load(open(d + '/meta.json'))
    base = statistics.median([s['bytes'] for s in S if s['t'] < meta['t_enable'] and 'bytes' in s][-8:])
    peak = max(s['bytes'] for s in S if 'bytes' in s and t0 - 1 <= s['t'] <= t1 + 1)
    live = [x for x in S if 'liveHeapKB' in x]
    lh = max((x['liveHeapKB'] for x in live if x['t_end'] >= t0 - 1 and x['t'] <= t1 + 1), default=None)
    lbase = max((x['liveHeapKB'] for x in live if x['t_end'] < meta['t_enable']), default=None)
    rows[(role, N)] = dict(live=lh, lbase=lbase, lev=lev, cnt=cnt, nsst=nsst, before=before, ex=ex, yaml=yaml, thr=thr, second=len(second), base=base, peak=peak, dur=t1 - t0, done=done[0])
    ok(f'C0 {role} N={N}: node stopped cleanly (exit.txt), concurrent_compactors 1, compaction_throughput 0MiB/s, threshold {N} read back',
       'rc=0 daemons_stopped=True' in ex and re.search(r'^concurrent_compactors: 1$', d and yaml, re.M) and re.search(r'^compaction_throughput: 0MiB/s$', yaml, re.M) and re.search(rf'\b{N}\b', thr) is not None)
    ok(f'C1 {role} N={N}: restored fixture as built (' + (f'L0 {cnt[0]}, L1 {cnt[1]}, rest {sum(cnt[2:])}' if role == 'lcs' else f'{nsst} sstables') + ')',
       (cnt[0] == 100 and sum(cnt[2:]) == 0 and cnt[1] > 0) if role == 'lcs' else nsst == 100)
    ok(f'C2 {role} N={N}: exactly one task started before the first finished', len(second) == 0)
# per-run claims
for (role, N), r in sorted(rows.items()):
    lev = r['lev']; n0 = [x for x in lev if x[2] == 0]; n1 = [x for x in lev if x[2] > 0]
    if role == 'lcs':
        fx_l1 = r['cnt'][1]
        gens_l0_fx = sorted(int(re.search(r'nb-(\d+)-', f).group(1)) for f in r['before'] if f.endswith('-Data.db') and f not in {x[0] for x in n1})
        oldest = gens_l0_fx[:N]
        ok(f'C3 lcs N={N}: {len(n0)} L0 inputs = N, and they are the {N} lowest-generation L0 sstables of the fixture (age order), {len(n1)} L1 inputs = all {fx_l1} L1 sstables',
           len(n0) == N and sorted(x[1] for x in n0) == oldest and len(n1) == fx_l1, f'total {len(lev)} inputs > N={N}')
    else:
        ok(f'C3 stcs N={N}: {len(lev)} inputs = N, none above level 0', len(lev) == N and not n1)
    inb = sum(r['before'][x[0]] for x in lev)
    r['inb'] = inb
    r['delta'] = r['peak'] - r['base']
    print(f'    {role} N={N}: inputs {len(lev)} ({len(n0)}+{len(n1)}), input MiB {inb/1048576:.1f}, peak-minus-baseline MiB {r["delta"]/1048576:.1f}, task {r["dur"]:.1f} s')
L = {N: r for (role, N), r in rows.items() if role == 'lcs'}
T = {N: r for (role, N), r in rows.items() if role == 'stcs'}
def fit(xs, ys):
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    s = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs); return s, my - s * mx
if len(L) >= 3:
    xs = sorted(L); s, i = fit(xs, [L[x]['inb'] for x in xs])
    l1b = sum(L[xs[0]]['before'][x[0]] for x in L[xs[0]]['lev'] if x[2] > 0)
    ok('C4 LCS input bytes fit slope x N + offset with offset = L1 bytes (20%)', abs(i - l1b) <= 0.2 * l1b, f'slope {s/1048576:.1f} MiB, offset {i/1048576:.0f} MiB, L1 {l1b/1048576:.0f} MiB')
    s, i = fit(xs, [L[x]['delta'] for x in xs])
    ok('C5 LCS peak table bytes above baseline carry the L1 offset (30%)', abs(i - l1b) <= 0.3 * l1b, f'slope {s/1048576:.1f} MiB, offset {i/1048576:.0f} MiB')
if len(T) >= 3:
    per = [T[x]['delta'] / x for x in sorted(T)]
    ok('C6 STCS control: peak bytes above baseline per N constant within 25%', max(per) <= 1.25 * min(per), str([round(p / 1048576, 1) for p in per]))
if all(r['live'] for r in L.values()) and L:
    hs = [L[x]['live'] / 1024 for x in sorted(L)]
    ok('C9 LCS live heap (class histogram total) at the task peak: spread across N <= 25% of the mean, and far below the 2 GiB heap', (max(hs) - min(hs)) <= 0.25 * (sum(hs) / len(hs)) and max(hs) < 512,
       f'{[round(h, 1) for h in hs]} MiB (idle baselines {[round(L[x]["lbase"] / 1024, 1) for x in sorted(L)]})')
if all(r['live'] for r in T.values()) and T:
    hs = [T[x]['live'] / 1024 for x in sorted(T)]
    ok('C10 STCS control live heap likewise flat', (max(hs) - min(hs)) <= 0.25 * (sum(hs) / len(hs)), f'{[round(h, 1) for h in hs]} MiB')
# builds
for b in sorted(glob.glob(f'{CD}/build-*')):
    if not os.path.isdir(b): continue
    errs = [f for f in glob.glob(b + '/stress-*.txt') if not re.search(r'Total errors\s*:\s*0 ', open(f, errors='replace').read())]
    ok(f'C7 {os.path.basename(b)}: stress runs with 0 errors', not errs, f'{len(glob.glob(b + "/stress-*.txt"))} runs')
    ok(f'C8 {os.path.basename(b)}: exit.txt rc=0 and node stopped', 'rc=0 daemons_stopped=True' in open(b + '/exit.txt').read())
print()
print('SELF-CHECK:', 'all hold' if not bad else 'FAILED: ' + '; '.join(bad))
