#!/usr/bin/env python3
"""Independent self-check of run 1 (results section 5): re-parses the raw files with its own code.
usage: selfcheck.py <run-dir>"""
import csv, glob, re, sys, xml.etree.ElementTree as ET
R = sys.argv[1]; ok = []
def chk(c, t): ok.append(c); print(('holds   ' if c else 'FAILS   ') + t)
# unit: junit XML result and the raw test log (not the extracted lines)
x = ET.parse(glob.glob(f'{R}/unit/TEST-*.xml')[0]).getroot()
chk(x.get('tests') == '1' and x.get('failures') == '0' and x.get('errors') == '0', f"unit junit: tests={x.get('tests')} failures={x.get('failures')} errors={x.get('errors')}")
raw = open(f'{R}/unit/test.log').read()
w = int(re.search(r'O53 EMPTY=(\d+) TIMEUUID_SIZE=(\d+)', raw).group(1)) + int(re.search(r'TIMEUUID_SIZE=(\d+)', raw).group(1))
last = {}
for m in re.finditer(r'peer=(\w+) size=(\w+) cap=(\d+) inserted=(\d+) retained=(\d+) weightNow=(\d+) deep=(\d+)', raw):
    p, s, cap, ins, ret, wn, deep = m.group(1), m.group(2), *map(int, m.groups()[2:])
    if s == '40MiB': chk(ret == ins, f"unit {p} 40MiB inserted={ins} retained={ret}") if ins in (250, 5000) else None
    last.setdefault((p, s), []).append((ins, ret, wn, deep))
for (p, s), v in sorted(last.items()):
    if s == '40MiB': chk(all(r == i for i, r, _, _ in v), f"unit {p} 40MiB retained = inserted at all {len(v)} samples"); continue
    ins, ret, wn, deep = v[-1]; cap = v[-1] and {'16KiB': 16384, '256KiB': 262144, '1MiB': 1048576}[s]
    seg = 4 * ((cap // 4) // w)
    chk(ins == 5000 and len({r for _, r, _, _ in v[-3:]}) == 1 and ret * w <= cap and deep <= 2 * cap,
        f"unit {p} {s}: final retained {ret} (4 segments x floor(cap/4/w) = {seg}), flat over last 3, weight {ret*w} <= {cap}, deep {deep} <= {2*cap}, deep/cap {deep/cap:.3f}")
    first_evict = next((i for i, r, _, _ in v if r < i), None)
    print(f"        first sample with eviction: inserted={first_evict}")
# cluster: samples.csv against the summary's own sample lines, final histogram and vtable files, rebuild exit codes
for lbl in ('s16k', 's32k', 's4m', 's4m-nostats'):
    D = f'{R}/cluster/{lbl}'
    rows = list(csv.DictReader(open(f'{D}/samples.csv')))
    summ = open(f'{D}/summary.txt').read()
    for r in rows:
        chk(f"{r['i']},{r['node']},{r['vtable']},{r['live']}," in summ, f"{lbl} i={r['i']} n{r['node']} vtable={r['vtable']} live={r['live']} also in summary.txt") if r['i'] == '150' else None
    rc = [l.split(',')[1] for l in open(f'{D}/rebuilds.csv')]
    chk(len(rc) == 150 and set(rc) == {'0'}, f"{lbl}: {len(rc)} rebuilds, exit codes {sorted(set(rc))}")
    for k in (1, 2):
        h = open(f'{D}/n{k}-histo-final.txt').read()
        m = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+org\.apache\.cassandra\.streaming\.StreamingState\s*$', h, re.M)
        n_h = int(m.group(1)) if m else 0
        vt = open(f'{D}/n{k}-vtable-final.txt').read()
        n_v = int(re.search(r'\((\d+) rows\)', vt).group(1)) if re.search(r'\((\d+) rows\)', vt) else 0
        futs = re.findall(r'^\s*\d+:\s+(\d+)\s+\d+\s+org\.apache\.cassandra\.streaming\.(StreamResultFuture|StreamSession|StreamCoordinator)\s*$', h, re.M)
        log = open(f'{D}/n{k}/logs/system.log').read()
        plans = len(re.findall(r'(Executing|Creating new) streaming plan for Rebuild', log))
        print(f"        {lbl} n{k}: final histogram StreamingState={n_h}, final vtable rows={n_v}, live futures/sessions/coordinators={futs}, plans in log={plans}, ERROR lines={len(re.findall(r'^ERROR', log, re.M))}")
        chk(plans == 150 and n_h == n_v, f"{lbl} n{k}: 150 plans in system.log; histogram {n_h} == vtable rows {n_v}")
print(f"self-check: {sum(ok)} holds, {len(ok)-sum(ok)} fails")
