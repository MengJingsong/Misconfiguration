#!/usr/bin/env python3
"""Independent re-parse of the raw run-1 files of block_size-add-blockindex--autonomous (does not import analyze_*.py; regexes on the raw text).
usage: selfcheck.py <unit-dir> [<cluster-root>]    prints PASS / FAIL lines and a total; exit status 1 on any FAIL."""
import glob, os, re, sys

bad = 0


def chk(name, ok, detail=''):
    global bad
    print(('PASS ' if ok else 'FAIL ') + name + (' :: ' + detail if detail else ''))
    bad += (not ok)


ud = sys.argv[1]
outs = sorted(glob.glob(ud + '/*.out'))
chk('unit: 43 .out files (2 reps x [2 kinds x (2 invalid + 5 full + 3 short)] + 3 controls)', len(outs) == 43, str(len(outs)))
summ = open(ud + '/summary.txt').read()
chk('unit: every run exited 0', summ.count('exit=0') == 43 and 'exit=1' not in summ and 'no CassandraDaemon' in summ)
ok_writer = 0
for f in outs:
    t = open(f).read()
    name = os.path.basename(f)
    if 'finish' in t:
        bs = int(re.search(r' bs=(\d+) ', t).group(1)); n = int(re.search(r' N=(\d+) ', t).group(1))
        ln = int(re.search(r'blockValuesLen=(\d+)', t).group(1)); mx = int(re.search(r'maxBlockIndex=(\d+)', t).group(1))
        fl = int(re.search(r'STAGE4 finish.*? flushes=(\d+) ', t).group(1))
        jd = int(re.search(r'J_bytes_delta=(-?\d+)', t).group(1))
        good = ln == bs and mx <= bs and fl == -(-n // bs) and 8 * bs + 16 <= jd <= 8 * bs + 16 + 200
        ok_writer += good
        if not good:
            chk(name, False, f'bs={bs} N={n} len={ln} max={mx} flushes={fl} jd={jd}')
chk('unit: 32 writer runs: array length == bs, blockIndex <= bs, flushes == ceil(N/bs), retained long[] == 8bs+16 (+<=200) after N adds', ok_writer == 32, str(ok_writer))
inv = {os.path.basename(f): open(f).read() for f in outs if 'invalid' in os.path.basename(f)}
chk('unit: 100 -> power-of-two message, 32 -> range message', all(('power of two, got 100' in t) for k, t in inv.items() if '-100-' in k) and all(('must be >= 64 and <= 134217728, got 32' in t) for k, t in inv.items() if '-32-' in k) and len(inv) == 8)
for kind in ('plain', 'mono'):
    big = [int(re.search(r'STAGE4 finish.*? metaBytes=(\d+)', open(f'{ud}/{kind}-{bs}-full-r1.out').read()).group(1)) for bs in (128, 16384, 1048576)]
    chk(f'unit: {kind} metadata bytes at N=167,772,160 for bs 128 / 16384 / 2^20 shrink as blocks get larger (grow with the block count)', big[0] > big[1] > big[2], str(big))
ctl = [(int(re.search(r'N=(\d+)', open(f).read()).group(1)), int(re.search(r'J_bytes_delta=(\d+)', open(f).read()).group(1))) for f in sorted(glob.glob(ud + '/ctl-*.out'))]; ctl.sort()
chk('unit: control long[] bytes grow with N (>= 8N)', len(ctl) == 3 and all(j >= 8 * n for n, j in ctl) and ctl[0][1] < ctl[1][1] < ctl[2][1], str(ctl))
if len(sys.argv) > 2:
    cr = sys.argv[2]
    summ = open(cr + '/summary.txt').read()
    for lab, want in (('A-3M', {'128', '16384'}), ('A2-3M', {'128', '16384'}), ('A-750k', {'128', '16384'}), ('ctl-seg16', {'128', '16384'}), ('B-num64', {'64'}), ('C-num1m', {'1048576'})):
        led = [l.split() for l in open(f'{cr}/{lab}/ledger.txt') if l.startswith('BPW')]
        chk(f'cluster {lab}: BPW lengths are exactly {sorted(want)}', {l[1] for l in led} == want and len(led) % 5 == 0 and len(led) >= 5, f'{len(led)} lines')
    jars = {l: open(f'{cr}/{l}/jar.txt').read().split()[-1] if os.path.exists(f'{cr}/{l}/jar.txt') else None for l in ('A-3M', 'B-num64', 'C-num1m')}
    chk('cluster: three different jar md5 for the three builds', len({open(f'{cr}/{l}/jar.txt').read().strip().split('\n')[-1].split()[0] for l in jars if jars[l]}) == 3)
    for lab in ('A-3M', 'A2-3M', 'B-num64', 'C-num1m', 'A-750k', 'ctl-seg16'):
        seg = summ.split(f'ARM {lab} start')[1].split(f'ARM {lab} STOPPED')[0]
        chk(f'cluster {lab}: VERIFY OK and daemon stopped', 'VERIFY count(v>=0)' in seg and ' OK' in re.search(r'VERIFY.*', seg).group(0) and 'daemons left: none' in summ.split(f'ARM {lab} STOPPED')[1].split('\n')[0])
    comps = lambda lab: {m.group(1): int(m.group(2)) for m in re.finditer(r'SAI\+aa\+(?:\w+\+)?(\w+)\.db\t(\d+)', open(f'{cr}/{lab}/files-{lab}-after-build.txt').read())}
    tot = lambda lab: sum(int(l.split('\t')[1]) for l in open(f'{cr}/{lab}/files-{lab}-after-build.txt') if '\t' in l)
    t = [tot(x) for x in ('A-3M', 'B-num64', 'C-num1m')]
    chk(f'cluster: frozen criterion "total SAI bytes within 10 percent across A / B / C" is NOT met (spread {100 * (max(t) / min(t) - 1):.1f} percent): confirms the analyze_cluster MISMATCH', not (max(t) <= 1.1 * min(t)), str(t))
    comp = lambda lab: {m.group(1): int(m.group(2)) for m in re.finditer(r'SAI\+aa\+(\w+)\.db\t(\d+)', open(f'{cr}/{lab}/files-{lab}-after-build.txt').read())}
    cA, cB, cC = comp('A-3M'), comp('B-num64'), comp('C-num1m')
    diff = {k for k in cA if cA[k] != cB.get(k) or cA[k] != cC.get(k)}
    chk('cluster: only per-SSTable numeric-values components differ between the builds (per-index files and key blocks are byte-identical)', diff <= {'RowToToken', 'RowToPartition', 'PartitionToSize', 'PartitionKeyBlockOffsets', 'ClusteringKeyBlockOffsets'}, str(sorted(diff)))
    gh = lambda lab: max(int(l.split(',')[4]) for l in open(f'{cr}/{lab}/gauges-{lab}.csv').read().splitlines()[1:] if l.count(',') == 5) / 1048576
    noise = abs(gh('A-3M') - gh('A2-3M'))
    chk('cluster: heap-peak differences of B and C from A lie inside the A vs A2 noise band (so the peak cannot resolve them)', abs(gh('B-num64') - gh('A-3M')) <= noise and abs(gh('C-num1m') - gh('A-3M')) <= noise, f'noise {noise:.0f} MiB; B-A {gh("B-num64") - gh("A-3M"):.0f}; C-A {gh("C-num1m") - gh("A-3M"):.0f}; A {gh("A-3M"):.0f} A2 {gh("A2-3M"):.0f}')
    chk('cluster: A-3M / A-750k total bytes ratio 3.4 .. 4.6', 3.4 <= tot('A-3M') / tot('A-750k') <= 4.6, f"{tot('A-3M') / tot('A-750k'):.2f}")
    g = lambda lab: max(int(l.split(',')[1]) for l in open(f'{cr}/{lab}/gauges-{lab}.csv').read().splitlines()[1:] if l.count(',') == 5)
    chk('cluster control: seg-buffer peak 16 MiB arm <= 20 MiB < 32 MiB < default arm peak', g('ctl-seg16') <= 20 * 1048576 and g('A-3M') > 32 * 1048576, f"{g('ctl-seg16')} vs {g('A-3M')}")
print(f'SELFCHECK total FAIL={bad}')
sys.exit(1 if bad else 0)
