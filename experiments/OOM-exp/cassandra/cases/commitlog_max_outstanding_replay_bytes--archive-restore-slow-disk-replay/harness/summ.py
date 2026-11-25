#!/usr/bin/env python3
# R23 per-arm summary (B8/B15 summ.py adapted to the runs/<run>/ layout): outcome, heap OOM in stdout, guard kill,
# replayed count, b8.t_map flushes during the restart (count, serialized MiB, on-heap charge MiB), restored-segment count,
# histogram readings.   summ.py /mydata/s4/r23/runs/<run> [...]
import re, sys, os
def mib(s):
    v, u = float(s[:-3]), s[-3:]
    return v * {'KiB': 1/1024, 'MiB': 1, 'GiB': 1024}[u]
for R in sys.argv[1:]:
    a = open(f'{R}/arm.log').read()
    out = re.findall(r'outcome=(\S+) after (\d+)s', a)
    sl = f'{R}/system.log'; txt = open(sl, errors='replace').read() if os.path.exists(sl) else ''
    rep = re.findall(r'Log replay complete, (\d+) replayed mutations in (\d+) ms', txt)
    charge = ser = 0.0; n = 0
    for m in re.finditer(r'Writing Memtable-t_map@\d+\(([\d.]+[KMG]iB) serialized bytes, (\d+) ops, ([\d.]+[KMG]iB)', txt):
        ser += mib(m[1]); charge += mib(m[3]); n += 1
    so = open(f'{R}/stdout.txt', errors='replace').read() if os.path.exists(f'{R}/stdout.txt') else ''
    oom = re.search(r'java\.lang\.OutOfMemoryError[^\n]*', so)
    thr = re.search(r'Exception in thread "([^"]+)" java\.lang\.OutOfMemoryError', so) or re.search(r'OutOfMemoryError[^\n]*thread[^\n]*', txt)
    ev = open(f'{R}/memevents.txt').read() if os.path.exists(f'{R}/memevents.txt') else ''
    ok = re.search(r'oom_kill (\d+)', ev)
    hist = re.findall(r'histogram \+(\d+)s: total (\d+) MiB live; Mutation n=(\d*)', a)
    print(f'{os.path.basename(R)}: outcome={out[-1][0] if out else "?"} t={out[-1][1] if out else "?"}s heapOOM={bool(oom)} '
          f'oom_thread={thr.group(1) if thr and thr.lastindex else "-"} guard_oom_kill={ok.group(1) if ok else "?"} '
          f'replayed={rep[-1] if rep else "-"} t_map_flushes={n} t_map_ser={ser:.0f}MiB t_map_charge={charge:.0f}MiB histos={hist}')
