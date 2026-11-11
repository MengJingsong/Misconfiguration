#!/usr/bin/env python3
"""Independent re-parse of the raw files of the run: unit probe outputs and cluster gauge CSVs / logs. Two kinds of lines:
  FROZEN  - the case file's frozen prediction (B2f + U4, B3f + C4) restated; FAIL here is a recorded miss, not a script error
  OBSERVED - a relation derived after the fact from the readings (never used to judge the frozen rows)
usage on the node: selfcheck.py [~/s4b-logs/sai]"""
import csv, glob, os, re, sys
R = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/s4b-logs/sai')
miss = 0
def chk(kind, name, ok, detail=''):
    global miss
    miss += (not ok)
    print(f'{"PASS" if ok else "FAIL"} {kind} {name}' + (' | ' + detail if detail else ''))
U = R + '/unit'
INT = 2147483647
for tag, maxmb in (('stock', 32768), ('patched', 2048)):
    for f in sorted(glob.glob(f'{U}/probe-{tag}-*.out')):
        m = re.match(r'probe-\w+-(\d)-(\S+)\.out', os.path.basename(f))
        rep, v = int(m.group(1)), m.group(2)
        t = open(f).read()
        n = 1024 if v == 'default' else int(v)
        rej = 'PROBE result=REJECT' in t
        chk('FROZEN', f'{tag} rep{rep} v={v}: {"rejected" if n > maxmb else "accepted"}', rej == (n > maxmb))
        if rej:
            chk('FROZEN', f'{tag} rep{rep} v={v}: message is INVALID_BUFFER_SIZE_ERROR for max {maxmb}',
                f'Value must be a positive integer less than {maxmb}MiB' in t and 'ConfigurationException' in t)
            continue
        lim = int(re.search(r'limiter\.limitBytes=(\d+)', t).group(1))
        flip = int(re.search(r'flip_step_MiB=(\d+)', t).group(1))
        chk('FROZEN', f'{tag} rep{rep} v={v}: real limiter limit == n MiB in bytes', lim == n * 1048576, f'limit {lim} n*MiB {n * 1048576}')
        chk('FROZEN', f'{tag} rep{rep} v={v}: flip at step n+1', flip == n + 1, f'flip {flip}')
        chk('OBSERVED', f'{tag} rep{rep} v={v}: limit == min(n MiB, 2^31-1)', lim == min(n * 1048576, INT), f'limit {lim}')
        chk('OBSERVED', f'{tag} rep{rep} v={v}: flip == first step with step MiB > limit', flip == (lim // 1048576) + 1, f'flip {flip} limit {lim}')
# cluster
C = R + '/cluster'
inv = open(C + '/invalid/summary.txt').read()
chk('FROZEN', 'cluster 32769MiB: node refused to start with the message', 'alive after' in inv and ': False;' in inv and 'message in stdout: True' in inv)
peaks = {}
for mib in (64, 256, 1024, 4096):
    f = f'{C}/run-{mib}/gauges-{mib}.csv'
    if not os.path.exists(f):
        continue
    rows = [r for r in csv.DictReader(open(f)) if r['used'] != '' ]
    used = [int(r['used']) for r in rows]; lim = sorted(set(int(r['limit']) for r in rows)); heap = [int(r['heap_used']) for r in rows]
    peaks[mib] = (max(used), max(heap))
    L = mib * 1048576
    eff = min(L, INT)
    chk('FROZEN', f'cluster {mib}MiB: limit gauge == {mib} MiB in bytes (once the gauge exists)', [x for x in lim if x > 0] == [L], f'limit values {lim}')
    chk('OBSERVED', f'cluster {mib}MiB: limit gauge == min(n MiB, 2^31-1)', [x for x in lim if x > 0] == [eff], f'limit values {lim}')
    chk('FROZEN', f'cluster {mib}MiB: peak used >= limit and <= 1.25 x limit + 16 MiB', L <= max(used) <= 1.25 * L + 16 * 1048576, f'peak {max(used)} limit {L}')
    chk('FROZEN', f'cluster {mib}MiB: peak used far below 32768 MiB', max(used) < 32768 * 1048576 / 10, f'peak {max(used) / 1048576:.1f} MiB')
    fl = open(f'{C}/run-{mib}/flush-lines-{mib}.txt').read()
    chk('FROZEN', f'cluster {mib}MiB: memory-limit flush DEBUG line present', 'Global limit of' in fl, f'{fl.count("Global limit of")} lines')
if all(m in peaks for m in (64, 256, 1024)):
    chk('FROZEN', 'cluster: peak(64) < peak(256) < peak(1024)', peaks[64][0] < peaks[256][0] < peaks[1024][0], str({k: round(v[0] / 1048576, 1) for k, v in peaks.items()}))
    chk('FROZEN', 'cluster: heap peak at 1024 >= heap peak at 64 (support)', peaks[1024][1] >= peaks[64][1])
print('MISSES', miss)
