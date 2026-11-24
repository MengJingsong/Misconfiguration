#!/usr/bin/env python3
"""C9 3-b confirm: victim view per phase and per second. usage: c9b_vsum.py <rundir>
Reads phases.csv and victim/ops.csv; prints one table row per phase (ops, ok %, errors by class, latency of ok ops),
the time from each attack start to the victim's first failure, the outage length, and writes victim/per-second.csv
(seconds relative to scan1_start: ok, err, p50, max latency)."""
import csv, os, sys
from collections import Counter, defaultdict

d = sys.argv[1]
ph = {}
for l in open(d + '/phases.csv'):
    k, v = l.strip().split(','); ph.setdefault(k, int(v))
ops = []
for r in csv.DictReader(open(d + '/victim/ops.csv')):
    try:
        ops.append((int(r['ms_start']), int(r['ms_end']), r['op'], r['ok'] == '1', float(r['lat_ms']), r['err']))
    except (ValueError, KeyError):
        pass
ops.sort()
end = ops[-1][0] if ops else 0


def first_ok_after(t):
    for o in ops:
        if o[0] >= t and o[3]:
            return o[0]
    return None


def first_err_after(t):
    for o in ops:
        if o[0] >= t and not o[3]:
            return o
    return None


def q(xs, p):
    return xs[min(len(xs) - 1, int(len(xs) * p))] if xs else float('nan')


win = []
if 'victim_start' in ph and 'attack_prep' in ph:
    win.append(('before (60 s, no attack)', ph['victim_start'] + 5000, ph['attack_prep']))
if 'build_end' in ph:
    win.append(('prep + build of the many-sstable table (DDL arm: attacker; data arm: admin)', ph['attack_prep'], ph['build_end']))
    win.append(('idle before scan', ph['build_end'], ph['scan1_start']))
rec1 = None
if 'scan1_node_gone' in ph:
    win.append(('scan1: attack start -> node gone', ph['scan1_start'], ph['scan1_node_gone']))
    rec1 = first_ok_after(ph['scan1_node_gone'] + 3000)   # first success of a request issued after the node died
    win.append(('node down (gone -> first ok after restart)', ph['scan1_node_gone'], rec1 or ph.get('after', end)))
    if rec1 and 'scan2_start' in ph:
        win.append(('recovered (first ok -> repeat attack)', rec1, ph['scan2_start']))
elif 'scan1_start' in ph:
    win.append(('scan1 (no endpoint)', ph['scan1_start'], ph.get('after', end)))
if 'scan2_start' in ph:
    e2 = ph.get('scan2_node_gone', ph.get('after', end))
    win.append(('scan2 (repeat): attack start -> node gone', ph['scan2_start'], e2))
    if 'scan2_node_gone' in ph:
        win.append(('after repeat (node down, no restart)', ph['scan2_node_gone'], end + 1))
print('| Phase | Length s | Ops | OK % (reads / writes) | Errors | Latency ok p50 / p99 / max ms |')
print('|---|---|---|---|---|---|')
for name, a, b in win:
    sel = [o for o in ops if a <= o[0] < b]
    ok = [o for o in sel if o[3]]
    errs = Counter(o[5] for o in sel if not o[3])
    lat = sorted(o[4] for o in ok)
    pr = lambda op: (lambda xs: f'{100 * sum(1 for o in xs if o[3]) / len(xs):.0f}' if xs else '-')([o for o in sel if o[2] == op])
    print(f'| {name} | {(b - a) / 1000:.1f} | {len(sel)} | {100 * len(ok) / len(sel) if sel else float("nan"):.1f} ({pr("r")} / {pr("w")}) | '
          f'{dict(errs) if errs else "-"} | {q(lat, .5):.1f} / {q(lat, .99):.1f} / {lat[-1] if lat else float("nan"):.1f} |')
for s in ('scan1', 'scan2'):
    if s + '_start' in ph:
        fe = first_err_after(ph[s + '_start'])
        g = ph.get(s + '_node_gone')
        print(f'{s}: first victim failure at attack+{(fe[0] - ph[s + "_start"]) / 1000:.1f} s ({fe[2]} {fe[5]})' if fe else f'{s}: no victim failure',
              f'; node gone at attack+{(g - ph[s + "_start"]) / 1000:.1f} s' if g else '')
        # latency in the last 5 s before node gone
        if g:
            sel = sorted(o[4] for o in ops if g - 5000 <= o[0] < g and o[3])
            print(f'  ok ops in the last 5 s before node gone: {len(sel)}, p50 {q(sel, .5):.1f} max {sel[-1] if sel else float("nan"):.1f} ms')
if 'restart_cmd' in ph:
    print(f'restart: command at gone+{(ph["restart_cmd"] - ph["scan1_node_gone"]) / 1000:.1f} s, native port up after '
          f'{(ph.get("restart_up", 0) - ph["restart_cmd"]) / 1000:.1f} s, victim first ok at restart_cmd+'
          f'{((rec1 or 0) - ph["restart_cmd"]) / 1000:.1f} s; victim outage (last ok before gone -> first ok after) '
          f'{((rec1 or 0) - max(o[0] for o in ops if o[3] and o[0] < ph["scan1_node_gone"])) / 1000:.1f} s')
# per-second
t0 = ph.get('scan1_start', ops[0][0] if ops else 0)
per = defaultdict(lambda: [0, 0, []])
for o in ops:
    k = (o[0] - t0) // 1000
    per[k][0 if o[3] else 1] += 1
    if o[3]:
        per[k][2].append(o[4])
with open(d + '/victim/per-second.csv', 'w') as f:
    f.write('sec_rel_scan1,ok,err,p50_ms,max_ms\n')
    for k in sorted(per):
        ok, er, la = per[k]; la.sort()
        f.write(f'{k},{ok},{er},{q(la, .5):.1f},{la[-1] if la else float("nan"):.1f}\n')
print('phases (ms):', ', '.join(f'{k}={v}' for k, v in ph.items()))
