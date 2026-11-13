#!/usr/bin/env python3
"""One line per C2 lifetime from the repo logs: summarize.py <logs-dir> [label-prefix ...]
Columns: label, arm/heap/direct, outcome (OOM type / survived), time from load start to death, completed reads,
client errors, peak NMT Other (MiB, 10 s readings), peak heap used and peak old-gen post-GC (MiB, 1 s JMX),
NTR active max, rejection-control lines, gcwin."""
import csv, glob, os, re, sys

d = sys.argv[1]; pre = tuple(sys.argv[2:]) or ('',)
for ld in sorted(glob.glob(d + '/*/')):
    L = os.path.basename(ld.rstrip('/'))
    if not L.startswith(pre):
        continue
    ctl = open(f'{d}/controller-{L}.out', errors='replace').read() if os.path.exists(f'{d}/controller-{L}.out') else ''
    meta = open(ld + 'run.meta').read() if os.path.exists(ld + 'run.meta') else ''
    m = re.search(r'arm=(\S+) .*heap=(\S+) direct=(\S+)', meta)
    xmx = re.search(r'-Xmx(\S+)', meta); mdm = re.search(r'MaxDirectMemorySize=(\S+)', meta)
    cfg = f'{m.group(1)} Xmx={xmx.group(1) if xmx else "?"} direct={mdm.group(1) if mdm else "?"}' if m else '?'
    dead = re.search(r'VICTIM DEAD at \+(\d+)s', ctl)
    oom = ''
    if os.path.exists(ld + 'oom-excerpt.txt'):
        t = open(ld + 'oom-excerpt.txt', errors='replace').read()
        oom = 'direct-OOM(Netty)' if 'OutOfDirectMemoryError' in t else ('heap-OOM' if 'Java heap space' in t else 'OOM?')
    if dead and not oom:
        oom = 'heap-OOM' if 'Java heap space' in ctl else ('direct-OOM(Netty)' if 'OutOfDirectMemoryError' in ctl else 'died')
    outcome = (oom + f' @+{dead.group(1)}s') if dead else 'survived'
    reads = errs = '?'
    if os.path.exists(ld + 'client.csv'):
        rows = [r for r in open(ld + 'client.csv') if r[:1].isdigit()]
        sm = [r for r in open(ld + 'client.csv') if r.startswith('SUMMARY')]
        if sm:
            g = re.search(r'(?:ok|responses)=(\d+) err(?:ors)?=(\d+)', sm[0]); reads, errs = g.group(1), g.group(2)
        elif rows:
            f = rows[-1].split(','); hdr = open(ld + 'client.csv').readline()
            if hdr.startswith('t,outstanding'):
                reads, errs = f[2], f[3]
            else:
                reads, errs = f[3], f[4]
    nmt = []
    if os.path.exists(ld + 'readings.csv'):
        for r in open(ld + 'readings.csv'):
            g = re.search(r'nmtOtherKB=(\d+)', r)
            if g: nmt.append(int(g.group(1)) / 1024)
    heap = post = act = 0
    if os.path.exists(ld + 'samples.csv'):
        for r in csv.DictReader(open(ld + 'samples.csv')):
            try:
                heap = max(heap, int(r['heap_used']) / 2**20); post = max(post, int(r['old_postgc']) / 2**20); act = max(act, int(r['ntr_active']))
            except (ValueError, TypeError, KeyError):
                pass
    rej = ' '.join(f'pk{a}:' + ('OK' if b == 'OK' else b.split()[1]) for a, b in re.findall(r'one pk=(\d+) (OK|ERROR \w+)', ctl))
    gw = open(ld + 'gcwin.txt').read().strip() if os.path.exists(ld + 'gcwin.txt') else ''
    gw = re.sub(r'pauses=\d+ ', '', gw).replace('service_loss(all STW)=', 'SL=')
    print(f'{L:<14} {cfg:<34} {outcome:<24} reads={reads:<6} err={errs:<5} nmtOther_base/max={nmt[0] if nmt else 0:.0f}/{max(nmt) if nmt else 0:.0f} '
          f'heap_max={heap:.0f} oldpostGC_max={post:.0f} NTRact_max={act} [{rej}] {gw}')
