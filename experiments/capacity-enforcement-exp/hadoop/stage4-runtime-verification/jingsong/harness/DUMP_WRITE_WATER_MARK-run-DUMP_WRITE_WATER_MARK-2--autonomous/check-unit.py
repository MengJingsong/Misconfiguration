#!/usr/bin/env python3
"""Summarise the unit-tier trace (DUMPWM lines + OpenFileCtx DEBUG lines) per arm. Usage: check-unit.py unit-trace.log"""
import re, sys, collections
arm = None; A = collections.OrderedDict()
for line in open(sys.argv[1]):
    m = re.search(r'DUMPWM ARM-BEGIN (\S+) mark=(\d+) w=(\d+) n=(\d+)', line)
    if m:
        arm = m.group(1); A[arm] = dict(mark=int(m.group(2)), w=int(m.group(3)), n=int(m.group(4)), maxdbg=0, updates=0,
            starts=0, before=[], after=[], woke=0, ask=0, create=0, rows=[], other=[]); continue
    if arm is None: continue
    a = A[arm]
    if 'ARM-END' in line: arm = None; continue
    m = re.search(r'Update nonSequentialWriteInMemory by (-?\d+) new value: (\d+)', line)
    if m:
        a['updates'] += 1; a['maxdbg'] = max(a['maxdbg'], int(m.group(2))); continue
    m = re.search(r'Before dump, nonSequentialWriteInMemory == (\d+)', line)
    if m: a['starts'] += 1; a['before'].append(int(m.group(1))); continue
    m = re.search(r'After dump, nonSequentialWriteInMemory == (\d+)', line)
    if m: a['after'].append(int(m.group(1))); continue
    if 'Dumper woke up' in line: a['woke'] += 1; continue
    if 'Asking dumper to dump' in line: a['ask'] += 1; continue
    if 'Create dump file' in line: a['create'] += 1; continue
    m = re.search(r'DUMPWM ROW,[^,]+,(\d+),(\d+),(\d+),(\d+),(-?\d+),(\d+),(\w+)', line)
    if m: a['rows'].append(tuple(int(x) for x in m.groups()[:6]) + (m.group(7),)); continue
    if 'DUMPWM' in line: a['other'].append(line.split(' - ', 1)[1].strip())
for name, a in A.items():
    M, w = a['mark'], a['w']; rows = a['rows']
    # row = (i, off, ctr, inHeap, dumpLen, dumpedCount, dumperAlive)
    ctr_ne_heap = sum(1 for r in rows if r[2] != r[3])
    over = sum(1 for r in rows if r[2] >= M)
    sumv = sum(1 for r in rows if r[2] + max(r[4], 0) != r[0] * w)
    lens = [max(r[4], 0) for r in rows]
    steps = sorted({lens[k] - (lens[k-1] if k else 0) for k in range(len(lens)) if lens[k] != (lens[k-1] if k else 0)})
    print(f"ARM {name}: mark={M} w={w} n={a['n']} rows={len(rows)} maxDebugNewValue={a['maxdbg']} bound(mark+w-1)={M+w-1} "
          f"withinBound={a['maxdbg'] <= M + w - 1} updates={a['updates']} createDump={a['create']} askDumper={a['ask']} "
          f"dumpRounds={a['starts']} beforeSet={sorted(set(a['before']))} afterSet={sorted(set(a['after']))} dumperWokeUp={a['woke']}")
    if rows:
        print(f"   maxCtrAfterReturn={max(r[2] for r in rows)} maxInHeap={max(r[3] for r in rows)} rowsCtr!=inHeap={ctr_ne_heap} "
              f"rowsCtr>=mark={over} rowsCtr+dump!=i*w={sumv} finalDumpLen={rows[-1][4]} finalDumpedEntries={rows[-1][5]} "
              f"dumpGrowthSteps={steps} dumpGrowthEvents={sum(1 for k in range(len(lens)) if lens[k] != (lens[k-1] if k else 0))}")
    for o in a['other']: print('   ' + o[:400])
