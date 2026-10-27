#!/usr/bin/env python3
"""lcmt_cluster_analyze.py <outdir>  -- judges B3f/B3g (amendments C1-C5) from <outdir>/run-{lcs,stcs}-N<N>/ .
Written before any cluster reading. Prints per-run readings, PASS/FAIL per prediction, and the matched B3g row."""
import sys, os, re, json, glob, datetime, statistics
OUT = sys.argv[1]
MIB = 1048576.0
def ts(s):
    return datetime.datetime.strptime(s, '%Y-%m-%dT%H:%M:%S,%f').replace(tzinfo=datetime.timezone.utc).timestamp()
def tobytes(v, u):
    return float(v.replace(',', '')) * {'B': 1, 'KiB': 1024, 'MiB': MIB, 'GiB': MIB * 1024, 'TiB': MIB * MIB}[u]
runs = {}
for d in sorted(glob.glob(f'{OUT}/run-*-N*')):
    m = re.search(r'run-(lcs|stcs)-N(\d+)$', d)
    if not m or not os.path.exists(d + '/meta.json'): continue
    role, N = m.group(1), int(m.group(2))
    meta = json.load(open(d + '/meta.json')); before = json.load(open(d + '/files-before.json'))
    lines = [l for l in open(d + '/system.log.copy', errors='replace') if 'standard1' in l and ('Compacting (' in l or 'Compacted (' in l)]
    comp = [l for l in lines if 'Compacting (' in l]
    first = comp[0]
    uid = re.search(r'Compacting \(([0-9a-f-]+)\)', first).group(1)
    t_start = ts(re.search(r'(\d{4}-\d\d-\d\dT[\d:,]+)', first).group(1))
    files = re.findall(r'/([^/\s,\[\]]+-Data\.db):level=(\d+)', first)
    n0 = sum(1 for f, l in files if l == '0'); n1 = sum(1 for f, l in files if l != '0')
    b_in = sum(before.get(f, 0) for f, l in files); b_in0 = sum(before.get(f, 0) for f, l in files if l == '0'); b_in1 = b_in - b_in0
    missing = [f for f, l in files if f not in before]
    done = [l for l in lines if 'Compacted (' in l and uid in l]
    t_end = out_b = out_files = lvl = None
    if done:
        dl = done[0]; t_end = ts(re.search(r'(\d{4}-\d\d-\d\dT[\d:,]+)', dl).group(1))
        mm = re.search(r'Compacted \([^)]*\) (\d+) sstables to \[(.*?)\] to level=(\d+)\.\s+([\d.,]+)\s*(B|KiB|MiB|GiB) to ([\d.,]+)\s*(B|KiB|MiB|GiB)', dl)
        out_b = tobytes(mm.group(6), mm.group(7)); out_files = len(re.findall(r'-big,', mm.group(2))) ; lvl = int(mm.group(3))
        in_logged = tobytes(mm.group(4), mm.group(5))
    S = [json.loads(l) for l in open(d + '/samples.jsonl')]
    SL = [x for x in S if 'liveHeapKB' in x]      # run 2 only (LC_SAMPLER=v2): live heap from GC.class_histogram
    S = [x for x in S if 'bytes' in x]
    base = [x for x in S if x['t'] < meta['t_enable']]
    bbytes = statistics.median(x['bytes'] for x in base[-8:]) if base else None
    bheap = max(x.get('heapUsedKB', 0) for x in base) / 1024 if base else None
    brss = max(x.get('rssAnonKB', 0) for x in base) / 1024 if base else None
    win = [x for x in S if t_start - 1 <= x['t'] <= (t_end or 1e18) + 1]
    peak = max(x['bytes'] for x in win) if win else None
    heap = max(x.get('heapUsedKB', 0) for x in win) / 1024 if win else None
    rss = max(x.get('rssAnonKB', 0) for x in win) / 1024 if win else None
    if SL:
        heap = max((x['liveHeapKB'] for x in SL if x['t_end'] >= t_start - 1 and x['t'] <= (t_end or 1e18) + 1), default=0) / 1024
        bheap = max((x['liveHeapKB'] for x in SL if x['t_end'] < meta['t_enable']), default=0) / 1024
    later = [l for l in comp[1:] if t_end is None or ts(re.search(r'(\d{4}-\d\d-\d\dT[\d:,]+)', l).group(1)) < t_end]
    fx = open(d + '/tablestats-before.txt').read()
    mc = re.search(r'SSTables in each level: \[(.*?)\]', fx)
    lv = [int(re.sub(r'[^0-9]', '', x.split('/')[0]) or 0) for x in mc.group(1).split(',')] if mc else None
    l1fx = sum(v for f, v in before.items()) if False else None
    runs[(role, N)] = dict(dir=d, N=N, n0=n0, n1=n1, count=len(files), b_in=b_in, b_in0=b_in0, b_in1=b_in1, missing=missing, out_b=out_b, out_files=out_files, level=lvl,
        dur=(t_end - t_start) if t_end else None, base=bbytes, peak=peak, delta=(peak - bbytes) if peak and bbytes else None, heap=heap, rss=rss, bheap=bheap, brss=brss,
        extra_tasks_before_end=len(later), levels_before=lv, settled=meta.get('settled'), in_logged=in_logged if done else None, disable=meta.get('disable_reply'), nfiles_before=len(before))
fails = []
def check(name, ok, note=''):
    if not ok: fails.append(name)
    print(('PASS ' if ok else 'FAIL ') + name + ((' -- ' + note) if note else ''))
print('run readings (MiB):')
for k, r in sorted(runs.items()):
    print(f"  {k[0]:5s} N={k[1]:3d}: inputs {r['count']} (L0 {r['n0']}, L1 {r['n1']}), in {r['b_in']/MIB:8.1f} (L0 {r['b_in0']/MIB:8.1f}, L1 {r['b_in1']/MIB:8.1f}), logged in {r['in_logged'] and round(r['in_logged']/MIB,1)}, out {r['out_b'] and round(r['out_b']/MIB,1)} in {r['out_files']} files, level {r['level']}, dur {r['dur'] and round(r['dur'],1)} s, "
          f"base {r['base'] and round(r['base']/MIB)}, peak {r['peak'] and round(r['peak']/MIB)}, delta {r['delta'] and round(r['delta']/MIB)}, heap {r['heap'] and round(r['heap'])} (base {r['bheap'] and round(r['bheap'])}), rssAnon {r['rss'] and round(r['rss'])} (base {r['brss'] and round(r['brss'])}), extra tasks {r['extra_tasks_before_end']}")
L = {N: r for (role, N), r in runs.items() if role == 'lcs'}; T = {N: r for (role, N), r in runs.items() if role == 'stcs'}
Ns = sorted(L)
check('V0 every run settled, first task identified, no input file missing from files-before', all(r['settled'] and r['out_b'] and not r['missing'] for r in runs.values()))
check('V1 LCS first tasks are L0 tasks (L0 inputs > 0, output level >= 1) at every N', all(r['n0'] > 0 and (r['level'] or 0) >= 1 for r in L.values()))
check('V2 STCS control first tasks have no level>0 files', all(r['n1'] == 0 for r in T.values()))
if L:
    l1n = max(r['n1'] for r in L.values())
    check('P1 LCS: L0 inputs = N at every N (the cap at :548 binds on the L0 part)', all(r['n0'] == min(N, 100) for N, r in L.items()), str({N: r['n0'] for N, r in L.items()}))
    check('P2 LCS: L1 inputs = all L1 sstables of the fixture (> 0) at every N, so count = N + L1 count > N', all(r['n1'] == r['levels_before'][1] and r['n1'] > 0 and r['count'] > N for N, r in L.items()), str({N: (r['count'], r['n1']) for N, r in L.items()}))
    # linear fit of input bytes vs N
    xs = [N for N in Ns]; ys = [L[N]['b_in'] for N in Ns]
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs); icpt = my - slope * mx
    l1b = statistics.mean(r['b_in1'] for r in L.values())
    check('P3 LCS: input bytes = slope x N + fixed offset, offset within 20% of the L1 bytes (the fixed L1 offset of B3f)', abs(icpt - l1b) <= 0.2 * l1b, f'slope {slope/MIB:.1f} MiB/N, intercept {icpt/MIB:.0f} MiB, L1 bytes {l1b/MIB:.0f} MiB')
    dx = [L[N]['delta'] for N in Ns]
    mdy = sum(dx) / n; dslope = sum((x - mx) * (y - mdy) for x, y in zip(xs, dx)) / sum((x - mx) ** 2 for x in xs); dicpt = mdy - dslope * mx
    check('P4 LCS: peak table bytes above baseline carry the same fixed L1 offset (within 30% of L1 bytes)', abs(dicpt - l1b) <= 0.3 * l1b, f'slope {dslope/MIB:.1f} MiB/N, intercept {dicpt/MIB:.0f} MiB')
    hs = [L[N]['heap'] for N in Ns]
    check('P5 LCS: peak heap used spread across N <= 25% of the mean (heap about flat; run 1: jcmd GC.heap_info used, includes garbage; run 2: live heap by class histogram)', (max(hs) - min(hs)) <= 0.25 * (sum(hs) / len(hs)), f'{[round(h) for h in hs]} MiB')
    check('P6 LCS: peak table bytes above baseline exceed N x (mean L0 size) for every N (usage not bounded by N x file size)', all(L[N]['delta'] > N * statistics.mean([L[M]['b_in0'] / L[M]['n0'] for M in Ns]) for N in Ns))
if T:
    check('P7 STCS control: input count = N exactly at every N', all(r['count'] == min(N, 100) for N, r in T.items()), str({N: r['count'] for N, r in T.items()}))
    per = [r['b_in'] / r['count'] for r in T.values()]
    check('P8 STCS control: input bytes = count x mean sstable size (proportional to N, within 15%)', all(abs(r['b_in'] / r['count'] - statistics.mean(per)) <= 0.15 * statistics.mean(per) for r in T.values()))
    dd = [(N, r['delta'] / N) for N, r in sorted(T.items())]
    check('P9 STCS control: peak table bytes above baseline per N constant within 25% (usage scales with N)', max(v for _, v in dd) <= 1.25 * min(v for _, v in dd), str([(N, round(v / MIB, 1)) for N, v in dd]))
    check('P10 control moves: STCS count rises with N', [T[N]['count'] for N in sorted(T)] == sorted(T[N]['count'] for N in T) and len({T[N]['count'] for N in T}) == len(T))
print()
inv = [f for f in fails if f.startswith('V')]
if not L or not T: row = 'INCOMPLETE (missing runs)'
elif inv: row = 'Not confirmed / invalid: ' + '; '.join(inv)
elif all(r['count'] <= N and r['delta'] <= N * (r['b_in0'] / r['n0']) for N, r in L.items()): row = 'B3g "Task input count <= N and peak disk delta <= N x file size": Refuted'
elif any(f.startswith('P1') for f in fails): row = 'B3g "L0 count != N" (limit not reached or trace wrong): Not confirmed / see readings'
elif any(f.startswith(('P7', 'P8', 'P9', 'P10')) for f in fails): row = 'B3g "STCS control does not move with N": Not confirmed'
elif fails: row = 'Not confirmed (a prediction failed: ' + '; '.join(fails) + ')'
else: row = 'B3g "LCS task input count = N + L1 count and peak disk has the fixed L1 offset, heap about flat across N, while STCS control scales with N": Confirmed'
print('MATCHED ROW:', row)
