#!/usr/bin/env python3
"""Analyze B3 readings against B3f/B3g as amended by S5 (frozen 2026-11-24 before any reading).
Usage: analyze_cluster.py sizes-gen.txt sizes-node.txt rowcounts.txt"""
import sys, re, math
MiB = 1048576
gen, node = {}, {}
for line in open(sys.argv[1]):
    m = re.match(r'(\d+) (\S+/s4ks/(t_\w+)/\S+-(\d+)-\w+-Data\.db)$', line.strip())
    if m:
        gen.setdefault(m.group(3), []).append((int(m.group(4)), int(m.group(1))))
cur = None; stats = {}
for line in open(sys.argv[2]):
    line = line.strip()
    if line.startswith('== '):
        cur = line[3:]; node[cur] = []; stats[cur] = {}
    elif line.startswith('SSTable count'):  # D2: not 'Old SSTable count'
        stats[cur]['count'] = int(line.split(':')[1])
    elif 'Space used (live)' in line:
        stats[cur]['live'] = int(line.split(':')[1])
    else:
        m = re.match(r'(\d+) \S+-Data\.db$', line)
        if m: node[cur].append(int(m.group(1)))
rc = {}; cur = None
txt = open(sys.argv[3]).read().splitlines()
for i, line in enumerate(txt):
    if line.startswith('== '): cur = line[3:]
    elif re.match(r'^\s*\d+\s*$', line) and cur and cur not in rc: rc[cur] = int(line)

ok = bad = 0
def check(c, msg):
    global ok, bad
    ok += c; bad += (not c)
    print(("  ok   " if c else "  BAD  ") + msg)
counts = {}
for t in ('t_m1', 't_m4', 't_m16', 't_unset', 't_ctl'):
    s = sorted(gen.get(t, []))
    d = [x[1] for x in s]
    T = sum(d); P = T / 60000; Pb = math.ceil(P) + 16
    counts[t] = len(d)
    print(f"{t}: gen sstables={len(d)} T={T} P={P:.2f} Pb={Pb} min={min(d)} max={max(d)} last={d[-1]}; node count={stats[t].get('count')} live={stats[t].get('live')} node Data.db n={len(node[t])}; rows={rc.get(t)}")
    if t in ('t_m1', 't_m4', 't_m16'):
        M = int(t[3:]); L = M * MiB
        nl = d[:-1]
        print(f"     non-last minus L: {min(nl)-L}..{max(nl)-L}")
        exp = math.ceil(T / L)
        check(abs(len(d) - exp) <= max(1, 0.1 * exp), f"{t}: count {len(d)} vs ceil(T/L) {exp}")
        check(all(L < x <= L + Pb for x in nl), f"{t}: every non-last Data.db in (L, L+Pb] = ({L}, {L+Pb}]")
        check(d[-1] <= L + Pb, f"{t}: last {d[-1]} <= L+Pb")
    if t == 't_unset':
        check(len(d) == 1, f"t_unset: 1 SSTable (got {len(d)}), Data.db={d[0]}")
    if t == 't_ctl':
        check(len(d) >= 2, f"t_ctl: {len(d)} SSTables >= 2, sizes {d}")
    check(sorted(d) == sorted(node[t]) and stats[t].get('count') == len(d), f"{t}: node-side Data.db sizes and tablestats count identical to generator side")
    check(rc.get(t) == 60000, f"{t}: row count {rc.get(t)} == 60000")
    check(T >= 40_000_000, f"{t}: T {T} >= 40 MB")
c1, c4, c16 = counts['t_m1'], counts['t_m4'], counts['t_m16']
check(abs(c1 - 4 * c4) <= 2, f"|c1 - 4*c4| = |{c1} - {4*c4}| <= 2")
check(abs(c4 - 4 * c16) <= 2, f"|c4 - 4*c16| = |{c4} - {4*c16}| <= 2")
print(f"\nCHECKS ok={ok} bad={bad}")
