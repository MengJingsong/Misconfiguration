#!/usr/bin/env python3
# B23: one-line summary per run from the node logs. usage: python3 -I summary.py <run dir> [...]
import sys, os, re
def rows(p):
    try: L = open(p).read().split('\n')
    except OSError: return [], []
    h = L[0].split(); out = []
    for l in L[1:]:
        f = l.split()
        if len(f) == len(h) and f[0].isdigit(): out.append(dict(zip(h, map(int, f))))
    return h, out
for d in sys.argv[1:]:
    lab = os.path.basename(d.rstrip('/'))
    drv = open(f'{d}/logs/driver.log').read()
    m = re.search(r'^(\d+\.\d+) .* load start', drv, re.M); L0 = float(m.group(1)) if m else 0
    _, p = rows(f'{d}/logs/poll1.log'); _, p2 = rows(f'{d}/logs/poll2.log')
    base = [r for r in p if r['epoch_ms'] / 1000 <= L0] or p[:1]; b = base[-1] if base else {}
    run = [r for r in p if r['epoch_ms'] / 1000 > L0]
    def mx(k): return max((r[k] for r in run), default=-1)
    def dl(k): return (run[-1][k] - b.get(k, 0)) if run else -1
    kmax = mx('K'); first = next((r['epoch_ms'] / 1000 - L0 for r in run if r['K'] > 5120), None)
    hr = []
    for l in open(f'{d}/logs/hints-rss.log'):
        f = l.split()
        if len(f) == 3 and f[1].isdigit(): hr.append((float(f[0]), int(f[1]), int(f[2])))
    hl = [x for x in hr if x[0] >= L0]
    D = None; D10 = 0
    if len(hl) > 2:
        last = max(hl, key=lambda x: x[1]); t_last = next(x[0] for x in hl if x[1] == last[1])
        D = (last[1] - hl[0][1]) / max(1e-9, t_last - hl[0][0])
        for i in range(len(hl)):
            j = next((j for j in range(i, len(hl)) if hl[j][0] - hl[i][0] >= 10), None)
            if j: D10 = max(D10, (hl[j][1] - hl[i][1]) / (hl[j][0] - hl[i][0]))
    rss = max((x[2] for x in hl), default=-1)
    end = re.search(r'stop: (.*)', drv); done = re.search(r'done alive=(\d)', drv)
    oom = open(f'{d}/logs/oom-grep.txt').read().strip().split('\n')[0][:160] if os.path.exists(f'{d}/logs/oom-grep.txt') else ''
    lam = None
    if run:
        w = [r for r in run if r['wr_done'] > b.get('wr_done', 0)]
        if w: w = [r for r in w if r['wr_done'] < w[-1]['wr_done']] + [next(r for r in w if r['wr_done'] == w[-1]['wr_done'])]
        if len(w) > 1: lam = (w[-1]['wr_done'] - w[0]['wr_done']) / max(1e-9, (w[-1]['epoch_ms'] - w[0]['epoch_ms']) / 1000)
    n2mx = max((r['dropped_mut'] for r in p2), default=-1)
    print(f"{lab}: stop={end.group(1) if end else '?'} alive={done.group(1) if done else '?'} | Kmax={kmax} t(K>5120)={first and round(first,1)} "
          f"pend_max={mx('mut_pending')} old_max={mx('old')/2**20:.0f}MiB old_coll_max={mx('old_coll')/2**20:.0f}MiB RssAnon_max={rss/1024:.0f}MiB "
          f"direct_max={mx('direct')/2**20:.0f}MiB | wr_done={dl('wr_done')} unavail={dl('unavail')} timeouts={dl('timeouts')} failures={dl('failures')} hints={dl('hints_total')} "
          f"| lambda={lam and round(lam)} op/s ({lam and round(lam*64000/1e6)} MB/s at 64 kB) D={D and round(D/1e6,1)} MB/s D10max={round(D10/1e6,1)} MB/s hintsB={hl[-1][1] if hl else -1} "
          f"| n2 dropped_mut={n2mx} | oom: {oom}")
