#!/usr/bin/env python3
"""Unit tier B2 analysis for maxTasksQueued-takeTaskPermit-taskPermits--autonomous: EXPECTED lines from the amended
B2f/B2g definitions (case file amendment block, 2026-10-22). usage: unit-analyze.py <unit dir>"""
import glob, os, re, sys

d = sys.argv[1]
yes = no = 0


def expect(desc, cond):
    global yes, no
    yes += bool(cond); no += (not cond)
    print(f'EXPECTED: {desc} - {"yes" if cond else "NO (recorded; judged in the results file)"}')


def kv(line):
    return dict(re.findall(r'(\w+)=(\S+)', line))


sep, ctl = {}, {}
for f in sorted(glob.glob(d + '/*-P*-rep*.log')):
    base = os.path.basename(f)
    kind, p, rep = re.match(r'(sep|control)-P(\d+)-(rep\d+)\.log', base).groups()
    for l in open(f, errors='replace'):
        if l.startswith('PROBE kind='):
            v = kv(l)
            if 'DRAIN' in l:
                (sep if kind == 'sep' else ctl).setdefault((int(p), rep), {})['drain'] = v
            elif int(v['N']) > 0:
                (sep if kind == 'sep' else ctl).setdefault((int(p), rep), {})[int(v['N'])] = v
    txt = open(f, errors='replace').read()
    expect(f'{base}: no OutOfMemoryError', 'OutOfMemoryError' not in txt)
    expect(f'{base}: JVM max heap 2048 MiB', 'maxHeapMiB=2048' in txt)
    if kind == 'sep':
        m = re.search(r'HISTO \d+:\s+(\d+)\s+(\d+)\s+java.util.concurrent.ConcurrentLinkedQueue\$Node', txt)
        last = max(k for k in sep[(int(p), rep)] if isinstance(k, int))
        expect(f'{base}: class histogram ConcurrentLinkedQueue$Node count within 1 % of N+1 at N={last} ({m.group(1) if m else None})',
               bool(m) and abs(int(m.group(1)) - (last + 1)) <= 0.01 * last)

slope = {}
for (P, rep), pts in sorted(sep.items()):
    tag = f'sep P={P} {rep}'
    ns = sorted(k for k in pts if isinstance(k, int))
    expect(f'{tag}: points N = {ns}', ns[:3] == [10000, 100000, 1000000] and (P != 0 or ns == [10000, 100000, 1000000, 4000000]))
    prev = None
    for n in ns:
        v = pts[n]
        expect(f'{tag} N={n}: submitted = pending = N, no error, maxQueued = 2147483647',
               int(v['submitted']) == n - (prev or 0) and int(v['pending']) == n and v['err'] == 'none' and int(v['maxQueued']) == 2147483647)
        expect(f'{tag} N={n}: active = 1 (the blocker)', int(v['active']) == 1)
        expect(f'{tag} N={n}: no blocking (batch wall per task <= 100 us; slowest call <= 1 s)',
               int(v['wallMs']) * 1000 / (n - (prev or 0)) <= 100 and int(v['maxCallUs']) <= 1_000_000)
        prev = n
    dl = {n: float(pts[n]['deltaMiB']) * 1048576 for n in ns}
    lo, hi = P + 32, P + 250
    s1 = (dl[100000] - dl[10000]) / 90000
    s2 = (dl[1000000] - dl[100000]) / 900000
    slope[(P, rep)] = s2
    expect(f'{tag}: slope 1e4->1e5 {s1:.1f} B/task and 1e5->1e6 {s2:.1f} B/task, each in [P+32, P+250] = [{lo}, {hi}]', lo <= s1 <= hi and lo <= s2 <= hi)
    expect(f'{tag}: slopes agree within 25 % ({s1:.1f} vs {s2:.1f})', abs(s1 - s2) <= 0.25 * max(s1, s2))
    expect(f'{tag}: heap not flat (delta at 1e6 {dl[1000000] / 1048576:.1f} MiB >= 0.5 x N x (P+32))', dl[1000000] >= 0.5 * 1_000_000 * (P + 32))
    dr = pts.get('drain', {})
    expect(f'{tag}: drain: pending 0, completed = total + 1 ({dr.get("completed")} vs {ns[-1] + 1})', dr.get('pending') == '0' and int(dr.get('completed', -1)) == ns[-1] + 1)
for rep in sorted({r for (_, r) in sep}):
    if (0, rep) in sep and (1024, rep) in sep:
        d0 = float(sep[(0, rep)][1000000]['deltaMiB']) * 1048576 / 1e6
        d1 = float(sep[(1024, rep)][1000000]['deltaMiB']) * 1048576 / 1e6
        expect(f'{rep}: per-task difference P=1024 minus P=0 at 1e6 = {d1 - d0:.1f} B in [874, 1174]', 874 <= d1 - d0 <= 1174)
for P in (0, 1024):
    r = [slope[(P, k)] for k in sorted({r for (_, r) in sep}) if (P, k) in slope]
    if len(r) == 2:
        expect(f'P={P}: the two repetitions agree within 10 % ({r[0]:.1f} vs {r[1]:.1f})', abs(r[0] - r[1]) <= 0.10 * max(r))
for (P, rep), pts in sorted(ctl.items()):
    tag = f'control P={P} {rep}'
    ns = sorted(k for k in pts if isinstance(k, int))
    for n in ns:
        v = pts[n]
        expect(f'{tag} N={n}: accepted 10000, rejected N-10000, queued 10000, first reject (once there is one) after 10000 accepted',
               int(v['accepted']) == 10000 and int(v['rejected']) == n - 10000 and int(v['queued']) == 10000 and (v['firstReject'] == 'afterAccepted=10000' or (n == 10000 and v['firstReject'] == 'none')))
    d4, d6 = float(pts[10000]['deltaMiB']), float(pts[ns[-1]]['deltaMiB'])
    expect(f'{tag}: heap plateaus (delta {d4:.2f} MiB at 1e4, {d6:.2f} MiB at {ns[-1]}: growth <= 20 % or <= 2 MiB)', d6 <= 1.2 * d4 or d6 - d4 <= 2)
    if P == 1024:
        s6 = float(sep[(1024, rep)][1000000]['deltaMiB']) if (1024, rep) in sep else None
        expect(f'{tag}: the sep arm at 1e6 holds >= 10 x the control ({s6} vs {pts[1000000]["deltaMiB"]} MiB)', s6 is not None and s6 >= 10 * float(pts[1000000]['deltaMiB']))
print(f'EXPECTED summary: {yes} yes, {no} NO')
