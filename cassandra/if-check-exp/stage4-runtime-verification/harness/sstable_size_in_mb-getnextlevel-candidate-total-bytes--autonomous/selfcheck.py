#!/usr/bin/env python3
"""Independent self-check for sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous.
Does not reuse unit-analyze.py / cluster-analyze.py. Unit: console echo in ant.log vs readings.txt, claims re-derived from raw numbers.
Cluster: Cassandra's own raw tablestats text (counts, live bytes, per-level bytes), the sampler's records, stress output, yaml, commands.log,
system.log. usage: selfcheck.py <unit dir> <cluster dir>"""
import sys, re, os, json
UNIT, CL = sys.argv[1], sys.argv[2]; MIB = 1 << 20
out = []
def claim(n, ok, note): out.append(ok); print(f"[{'holds' if ok else 'DOES NOT HOLD'}] {n}: {note}")
rd = {}
for l in open(f'{UNIT}/readings.txt'):
    p = l.rstrip('\n').split(' ', 3)
    if p[0] == 'R': rd[(p[1], p[2])] = p[3] if len(p) > 3 else ''
ant = {}
for l in open(f'{UNIT}/ant.log', errors='replace'):
    m = re.search(r'SubstituteLogger\.java:\d+ - R (\S+) (\S+) ?(.*)$', l)
    if m: ant[(m.group(1), m.group(2))] = m.group(3)
claim('U0 readings.txt equals the console echo in ant.log', ant == rd and len(rd) > 200, f'{len(rd)} vs {len(ant)} readings')
txt = open(f'{UNIT}/ant.log', errors='replace').read()
claim('U0b ant reports 4 tests, 0 failures, 0 errors', bool(re.search(r'Tests run: 4, Failures: 0, Errors: 0', txt)), re.search(r'Tests run: .*', txt).group(0)[:80])
g = lambda s, k: rd[(s, k)]
ok = True; det = {}
for n in (1, 5, 20, 160):
    for d, exp in ((-1, '0'), (0, '1'), (1, '1')):
        for kind in ('single', 'three'):
            tb = int(g('boundary', f'N{n}.{kind}[{d}].totalBytes'))
            ok &= tb == n * MIB + d and g('boundary', f'N{n}.{kind}[{d}].nextLevel') == exp
    ok &= g('boundary', f'N{n}.maxSSTableBytes') == str(n * MIB)
    det[n] = [g('boundary', f'N{n}.single[{d}].nextLevel') for d in (-1, 0, 1)]
claim('U1 boundary: total = N MiB - 1 gives level 0, N MiB and N MiB + 1 give level 1 (exact byte totals, single and 3-way split, N = 1/5/20/160)', ok, str(det))
claim('U2 mixed {L0, L1} gives 1; all-L1 gives 2 at every N', all(g('boundary', f'N{n}.mixedL0L1.nextLevel') == '1' and g('boundary', f'N{n}.allL1.nextLevel') == '2' for n in (1, 5, 20, 160)), 'ok')
ok = True; det = []
for n in (1, 5, 20, 160):
    for st in ('A', 'B'):
        for r in (1, 2, 3):
            t = f'N{n}.set{st}.rep{r}'
            ratio = int(g('sets', t + '.totalBytes')) / int(g('sets', t + '.sizeBytes'))
            exp = '0' if (st == 'A' or n == 160) else '1'
            ok &= g('sets', t + '.nextLevel') == exp and ((ratio < 1) if exp == '0' else (ratio > 1))
    det.append((n, round(int(g('sets', f'N{n}.setA.rep1.totalBytes')) / (n * MIB), 3), round(int(g('sets', f'N{n}.setB.rep1.totalBytes')) / (n * MIB), 3)))
claim('U3 real flushed sets: Set A below the size gives 0, Set B above it gives 1 (N=160: both below, 0); totals recomputed from bytes', ok, f'(N, A/size, B/size) {det}')
ok = True; det = []
for n in (1, 5, 20):
    for r in (1, 2, 3):
        sz = [int(x) for x in re.findall(r'\d+', g('sets', f'N{n}.setB.rep{r}.outputSizes'))]
        lv = [int(x) for x in re.findall(r'\d+', g('sets', f'N{n}.setB.rep{r}.outputLevels'))]
        ok &= max(sz) <= n * MIB + 200 * 1024 and set(lv) == {1}
    det.append((n, len(sz), round(max(sz) / MIB, 3)))
sz160 = [int(x) for x in re.findall(r'\d+', g('sets', 'N160.setB.rep1.outputSizes'))]
claim('U4 Set B compaction: files no larger than N MiB + 200 KiB at level 1 (N = 1/5/20); at N=160 one file at level 0', ok and len(sz160) == 1 and g('sets', 'N160.setB.rep1.outputLevels') == '[0]', f'(N, files, max MiB) {det}; N=160 {len(sz160)} file {sz160[0]/MIB:.2f} MiB')
cn = {n: [int(g('same', f'same.N{n}.rep{r}.outputs')) for r in (1, 2, 3)] for n in (1, 5, 20, 160)}
inp = {n: int(g('same', f'same.N{n}.rep1.inputBytes')) for n in cn}
claim('U5 positive control (same ~30 MiB input at every N): file count 29 > 6 > 2 > 1 as N grows 1 < 5 < 20 < 160; outputs sum to the input within 0.1%', all(cn[1][i] > cn[5][i] > cn[20][i] > cn[160][i] for i in range(3)) and all(abs(int(g('same', f'same.N{n}.rep{r}.outputSum')) / int(g('same', f'same.N{n}.rep{r}.inputBytes')) - 1) < 0.001 for n in cn for r in (1, 2, 3)), f'counts {cn}; inputs {set(inp.values())}')
claim('U6 ~15 MiB partition at N=5 ends as a file larger than 5 MiB', all(int(g('big', f'big5.rep{r}.maxFile')) > 5 * MIB for r in (1, 2, 3)), str([int(g('big', f'big5.rep{r}.maxFile')) for r in (1, 2, 3)]))
# ---------------- cluster
def rawstats(path):
    t = open(path).read()
    lv = lambda key: [int(re.split(r'/', x.strip())[0]) for x in re.search(key + r': \[(.*?)\]', t).group(1).split(',')] if re.search(key + r': \[', t) else None
    return dict(count=int(re.search(r'SSTable count: (\d+)', t).group(1)), live=int(re.search(r'Space used \(live\): (\d+)', t).group(1)), lvb=lv('SSTable bytes in each level'))
SIZE = {'N5': 5, 'N20': 20, 'N160': 160, 'T20': 20, 'STCS': None}
THR = {'N5': '0MiB/s', 'N20': '0MiB/s', 'N160': '0MiB/s', 'T20': '16MiB/s', 'STCS': '0MiB/s'}
info = {}
for lb, n in SIZE.items():
    d = f'{CL}/{lb}'
    st = open(f'{d}/stress-write.txt').read(); cmd = open(f'{d}/commands.log').read(); yml = open(f'{d}/conf/cassandra.yaml').read()
    errs = int(re.search(r'Total errors\s*:\s*(\d+)', st).group(1)); parts = int(re.search(r'Total partitions\s*:\s*([\d,]+)', st).group(1).replace(',', ''))
    ct = re.search(r'CREATE TABLE IF NOT EXISTS ks.standard1.*', cmd).group(0)
    opt = ('SizeTiered' in ct) if n is None else (f"'sstable_size_in_mb':'{n}'" in ct)
    thr = re.search(r'^compaction_throughput: (\S+)', yml, re.M).group(1) == THR[lb] and re.search(r'^concurrent_compactors: (\d+)', yml, re.M).group(1) == '1'
    ex = open(f'{d}/exit.txt').read().strip(); syslog = open(f'{d}/logs/system.log', errors='replace').read()
    ow = open(f'{d}/stress-overwrite.txt').read(); ow_err = int(re.search(r'Total errors\s*:\s*(\d+)', ow).group(1))
    rec = dict(errs=errs, parts=parts, opt=opt, thr=thr, ok=('rc=0 daemons_stopped=True' in ex and 'daemons left after stop: none' in cmd and len(re.findall(r'^ERROR', syslog, re.M)) == 0), ow_err=ow_err)
    rec['lag'] = rawstats(f'{d}/tablestats-lag-end.txt'); rec['setl'] = rawstats(f'{d}/tablestats-settled-write.txt'); rec['trunc'] = rawstats(f'{d}/tablestats-truncated.txt')
    rec['ow'] = rawstats(f'{d}/tablestats-settled-overwrite.txt')
    peak = rec['lag']['lvb'][0] if rec['lag']['lvb'] else 0
    for l in open(f'{d}/samples-standard1.jsonl'):
        r = json.loads(l)
        if 'tablestats' in r:
            m = re.search(r'SSTable bytes in each level: \[(.*?)\]', r['tablestats'])
            if m: peak = max(peak, int(re.split(r'/', m.group(1).split(',')[0])[0]))
    rec['peak'] = peak; rec['peakfile'] = max(json.loads(l).get('bytes', 0) for l in open(f'{d}/samples-standard1.jsonl'))
    if n:
        rec['big'] = rawstats(f'{d}/tablestats-settled-big.txt') if os.path.exists(f'{d}/tablestats-settled-big.txt') else None
        rec['bigmax'] = max(json.loads(l).get('maxdata', 0) for l in open(f'{d}/samples-big.jsonl')) if os.path.exists(f'{d}/samples-big.jsonl') else 0
    info[lb] = rec
claim('C1 every run: labelled compaction in CREATE TABLE, yaml throughput and 1 compactor as specified, 0 errors in write and overwrite stress, 2,000,000 partitions', all(i['opt'] and i['thr'] and i['errs'] == 0 and i['ow_err'] == 0 and i['parts'] == 2000000 for i in info.values()), str({k: (i['opt'], i['thr'], i['errs'], i['ow_err']) for k, i in info.items()}))
claim('C2 clean exits (rc 0, daemon stopped, "daemons left after stop: none") and no ERROR in any system.log', all(i['ok'] for i in info.values()), str({k: i['ok'] for k, i in info.items()}))
main = ['N5', 'N20', 'N160']
lv = [info[k]['setl']['live'] for k in main]
claim('C3 settled live bytes (Cassandra\'s own count) within 10% across N = 5/20/160, and the STCS reference within 10% of them', max(lv) / min(lv) < 1.10 and all(abs(info['STCS']['setl']['live'] / x - 1) < 0.10 for x in lv), f'live {[round(x/MIB) for x in lv]} MiB, STCS {info["STCS"]["setl"]["live"]/MIB:.0f} MiB; spread {max(lv)/min(lv)-1:.4f}')
cnt = {k: info[k]['setl']['count'] for k in main}
claim('C4 SSTable count (raw tablestats) falls with N: > 2.5x from 5 to 20 and > 3x from 20 to 160', cnt['N5'] / cnt['N20'] > 2.5 and cnt['N20'] / cnt['N160'] > 3, f"counts {cnt}; ratios {cnt['N5']/cnt['N20']:.1f}, {cnt['N20']/cnt['N160']:.1f}")
mean = {k: info[k]['setl']['live'] / info[k]['setl']['count'] / MIB for k in main}
claim('C5 mean file size from Cassandra\'s own numbers is between 0.5 N and 1.05 N for N = 5/20/160', all(0.5 * n <= mean[k] <= 1.05 * n for k, n in (('N5', 5), ('N20', 20), ('N160', 160))), str({k: round(v, 2) for k, v in mean.items()}))
bg = {k: (info[k]['big']['count'], round(info[k]['bigmax'] / MIB, 1)) for k in main}
PART = 40960000 / MIB
claim('C6 large-partition table (each partition 39.1 MiB): where the partition exceeds N (N = 5, 20) a file larger than N exists (sampler record of the largest Data.db); at N=160 the partition and all three (117 MiB) are below N, so that arm cannot show an oversized file (limit never reached)', bg['N5'][1] > 5 and bg['N20'][1] > 20 and PART < 160 and 3 * PART < 160, f'(files, largest MiB) {bg}')
def ratios(lb, n, until=None):
    mx = {}
    t0 = json.load(open(f'{CL}/{lb}/snapshot-lag-end.json'))['t']
    for l in open(f'{CL}/{lb}/samples-standard1.jsonl'):
        r = json.loads(l)
        if 'tablestats' in r and (until is None or r['t'] <= t0 + 1):
            m = re.search(r'SSTable bytes in each level: \[(.*?)\]', r['tablestats'])
            for i, x in enumerate(int(re.split(r'/', y.strip())[0]) for y in m.group(1).split(',')):
                mx[i] = max(mx.get(i, 0), x / ((4 if i == 0 else 10 ** i) * n * MIB))
    return {i: round(v, 2) for i, v in mx.items() if v}
rw = ratios('T20', 20, True); ra = ratios('T20', 20)
claim('C7 T20 (16 MiB/s) re-read from the raw tablestats text: in the throttled write window L0 exceeded its 4N quota (> 10x) and NO level above L0 exceeded its quota (the B3f bullet "L1+ exceed fanout^level x N under throttling" did not occur there); L1 exceeded its quota only later, in the unthrottled overwrite phase', rw.get(0, 0) > 10 and all(r <= 1.0 for i, r in rw.items() if i >= 1) and ra.get(1, 0) > 1.001, f'write window {rw}; whole run {ra}')
claim('C7b supplementary: in N5 and N20 (no throttle) L1 also exceeded fanout^1 x N at some sample (a quota is a trigger)', ratios('N5', 5).get(1, 0) > 1.001 and ratios('N20', 20).get(1, 0) > 1.001, f"N5 {ratios('N5', 5)}, N20 {ratios('N20', 20)}")
claim('C8 peak file bytes exceed settled bytes (transient compaction space) in N5/N20/N160', all(info[k]['peakfile'] > info[k]['setl']['live'] for k in main), str({k: (round(info[k]['peakfile'] / MIB), round(info[k]['setl']['live'] / MIB)) for k in main}))
claim('C9 TRUNCATE control: raw tablestats shows 0 live bytes afterwards in all 5 runs', all(i['trunc']['live'] == 0 for i in info.values()), 'ok')
print('INFO supplementary overwrite phase (settled live MiB: write -> overwrite):', {k: (round(i['setl']['live'] / MIB), round(i['ow']['live'] / MIB)) for k, i in info.items()})
print('SELF-CHECK:', 'ALL HOLD' if all(out) else f'{out.count(False)} DO NOT HOLD')
