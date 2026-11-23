#!/usr/bin/env python3
"""Independent per-arm check from raw files (stdout.log banner, samples.csv, client.log, cg.csv, histograms).
   python3 -I selfcheck.py <runsdir>   -> one row per arm (markdown)"""
import sys, os, re, csv, glob
RUNS = sys.argv[1]; MiB = 1048576.0
order = ['T_r1','C1_r1','I1_r1','T_r2','C1_r2','I1_r2','T_r3','C1_r3','I1_r3','T2_r1','C2_r1','I2_r1','T2_r2','C2_r2','I2_r2','T2_r3','C2_r3','I2_r3','T_4G','P0','S_vm']
print('| arm | heap | outcome (HotSpot banner) | JVM gone after FLOOD_START (s) | K max (MiB) | K at last live sample (MiB) | paused max | heap used max (MiB) | client sent / ROWS / errors | 32 MiB byte[] in dump or histogram | oom_kill |')
print('|---|---|---|---|---|---|---|---|---|---|---|')
for a in order:
    R = os.path.join(RUNS, a)
    if not os.path.isdir(R): continue
    so = open(os.path.join(R, 'V-logs', 'stdout.log'), errors='replace').read() if os.path.exists(os.path.join(R, 'V-logs', 'stdout.log')) else ''
    m = re.search(r'^#? ?java\.lang\.OutOfMemoryError: ([^\n]*)', so, re.M)
    banner = m.group(1).strip() if m else ''
    killed = 'Executing /bin/sh -c "kill -9' in so
    args = open(os.path.join(R, 'args.txt')).read()
    xmx = re.search(r'xmx=(\S+)', args).group(1)
    cl = open(os.path.join(R, 'client.log'), errors='replace').read()
    mt = re.search(r'FLOOD_START (\d+)', cl); t0 = int(mt.group(1))
    rows = list(csv.DictReader(open(os.path.join(R, 'samples.csv'))))
    live = [r for r in rows if r['heap_used'] not in ('NA', '-1')]
    after = [r for r in live if int(r['epoch_ms']) >= t0]
    gone = [int(r['epoch_ms']) for r in rows if int(r['epoch_ms']) >= t0 and r['heap_used'] == 'NA']
    kmax = max((float(r['K_requests_size']) for r in after), default=0) / MiB
    klast = float(after[-1]['K_requests_size']) / MiB if after else 0
    pmax = max((int(r['paused_conns']) for r in after), default=0)
    hmax = max((float(r['heap_used']) for r in after), default=0) / MiB
    fin = re.search(r'FINAL ms=\d+ (.*)', cl); f = fin.group(1) if fin else ''
    ms = re.search(r'sent=(\d+) rows=(\d+).*?errs=(\{[^}]*\})', f)
    cli = f'{ms.group(1)} / {ms.group(2)} / {ms.group(3)}' if ms else re.sub(r'\s+', ' ', f)[:60]
    d = ''
    hh = os.path.join(R, 'hprofhist.txt')
    if os.path.exists(hh):
        mm = re.search(r'==D\(32MiB\):\s+(\d+) arrays\s+([0-9.]+) MiB', open(hh).read()); d = f'dump {mm.group(1)} ({mm.group(2)} MiB)'
    elif os.path.exists(os.path.join(R, 'histo-end.txt')):
        mm = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+\[B ', open(os.path.join(R, 'histo-end.txt')).read(), re.M)
        if mm: d = f'histo-end [B total {int(mm.group(2))/MiB:.0f} MiB'
    cg = [l.strip().split(',') for l in open(os.path.join(R, 'cg.csv'))][1:] if os.path.exists(os.path.join(R, 'cg.csv')) else []
    ok = [c[3] for c in cg if len(c) > 3 and c[3] != '']
    out = (f'OOM: {banner}' + (' → kill -9' if killed else '')) if banner else 'alive (no banner)'
    print(f'| {a} | {xmx} | {out} | {round((gone[0]-t0)/1000,1) if gone else "—"} | {kmax:.2f} | {klast:.2f} | {pmax} | {hmax:.0f} | {cli} | {d} | {ok[-1] if ok else "?"} |')
