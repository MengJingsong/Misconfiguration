#!/usr/bin/env python3
# B8 per-run summary: replay outcome, replayed mutations, memtable charge flushed during replay for the b8 table
# (sum of "Writing Memtable-t_* ... X on-heap" lines = the replayed tail's memtable charge), client ok count and
# rate during load, runtime and replay GC summary, max live Mutation count in mid-replay histograms.
#   summ.py /mydata/b8/runs/<run> [...]
import re, sys, os, glob
def mib(s):
    v, u = float(s[:-3]), s[-3:]
    return v * {'KiB': 1/1024, 'MiB': 1, 'GiB': 1024}[u]
for R in sys.argv[1:]:
    a = open(f'{R}/arm.log').read()
    out = re.findall(r'replay: outcome=(\S+) after (\d+)s', a)
    rep = re.findall(r'Log replay complete, (\d+) replayed mutations in (\d+) ms', a)
    charge = ser = 0.0; n = 0
    sl = f'{R}/replay/system.log'
    if os.path.exists(sl):
        for line in open(sl, errors='replace'):
            m = re.search(r'Writing Memtable-t_\w+@\d+\(([\d.]+[KMG]iB) serialized bytes, \d+ ops, ([\d.]+[KMG]iB)', line)
            if m: ser += mib(m[1]); charge += mib(m[2]); n += 1
    cl = open(f'{R}/load/client.txt').read() if os.path.exists(f'{R}/load/client.txt') else ''
    oks = re.findall(r't=(\d+)s sent=\d+ ok=(\d+) \(([\d.]+)/s\) err=(\d+)', cl)
    lastok = max([int(o[1]) for o in oks], default=0)
    wto = len(re.findall('WriteTimeout', cl))
    g = lambda p: (open(p).read().strip().splitlines() or [''])[-1] if os.path.exists(p) else ''
    hist = re.findall(r'histogram \+(\d+)s: total (\d+) MiB live; Mutation n=(\d*)', a)
    oom = 'java.lang.OutOfMemoryError' in (open(f'{R}/replay/stdout.txt', errors='replace').read() if os.path.exists(f'{R}/replay/stdout.txt') else '')
    print(f'{os.path.basename(R)}: outcome={out[-1] if out else "?"} oom={oom} replayed={rep[-1] if rep else "-"} '
          f'tail_flushes={n} tail_charge={charge:.0f}MiB tail_memtable_serialized={ser:.0f}MiB client_ok={lastok} wto_lines={wto} histos={hist}')
    print(f'   load  gc: {g(R + "/load/gcsum.txt")}')
    print(f'   replay gc: {g(R + "/replay/gcsum.txt")}')
