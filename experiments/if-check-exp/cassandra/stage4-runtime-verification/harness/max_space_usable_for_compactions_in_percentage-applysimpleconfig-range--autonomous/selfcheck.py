#!/usr/bin/env python3
"""Independent re-parse of the raw files of the run (unit probe outputs, closed-control readings, cluster samples/logs) against the
predictions of the case file (B2f + amendments U3/U4, B3f + amendment C4). Prints one line per check: PASS/FAIL. Run on the node:
  selfcheck.py [~/s4b-logs/msu]"""
import csv, glob, json, os, re, sys
R = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/s4b-logs/msu')
bad = 0
def chk(name, ok, detail=''):
    global bad
    bad += (not ok)
    print(('PASS ' if ok else 'FAIL ') + name + (' | ' + detail if detail else ''))
U = R + '/unit'
heaps = {}
for rep in (1, 2):
    for v in ('-0.01', '0', '0.5', '0.95', '1', '1.01', 'default'):
        t = open(f'{U}/probe-{rep}-{v}.out').read()
        acc = 'PROBE result=ACCEPT' in t
        rej = 'PROBE result=REJECT' in t
        want_rej = v in ('-0.01', '1.01')
        chk(f'unit rep{rep} v={v} {"rejected" if want_rej else "accepted"}', rej == want_rej and acc != want_rej)
        if rej:
            chk(f'unit rep{rep} v={v} ConfigurationException with line-1017 text', 'class=org.apache.cassandra.exceptions.ConfigurationException msg=max_space_usable_for_compactions_in_percentage must be between 0 and 1' in t)
            continue
        want = 0.95 if v == 'default' else float(v)
        g = float(re.search(r'getMaxSpaceForCompactionsPerDrive=(\S+)', t).group(1))
        chk(f'unit rep{rep} v={v} getter == {want}', g == want, str(g))
        m = re.search(r'budget=(\d+) expected_lo=(\d+) expected_hi=(\d+) in_range=(\w+)', t)
        b, lo, hi = int(m.group(1)), int(m.group(2)), int(m.group(3))
        chk(f'unit rep{rep} v={v} budget within drift of round((usable-minFree)*v)', lo <= b <= hi and m.group(4) == 'true', f'budget {b} lo {lo} hi {hi}')
        if want == 0:
            chk(f'unit rep{rep} v=0 budget 0', b == 0)
        u = re.search(r'usable_before=(\d+) usable_after=(\d+)', t)
        chk(f'unit rep{rep} v={v} usable drift <= 4 MiB', abs(int(u.group(1)) - int(u.group(2))) <= 4 * 1048576)
        gate = re.search(r'gate budget-1=(\w+) budget\+1=(\w+)', t)
        chk(f'unit rep{rep} v={v} gate true/false at budget-1/budget+1', (gate.group(1), gate.group(2)) == ('true', 'false') or b == 0, gate.group(0))
        s1 = re.search(r'PROBE setter value=1.5 accepted=true getter=1.5 budget=(\d+) usable_now=(\d+) minFree=(\d+)', t)
        chk(f'unit rep{rep} v={v} setter accepts 1.5 and budget = 1.5*(usable-minFree)', bool(s1) and abs(int(s1.group(1)) - round((int(s1.group(2)) - int(s1.group(3))) * 1.5)) <= 8 * 1048576, s1.group(0)[:120] if s1 else '')
        s2 = re.search(r'PROBE setter value=-0.25 accepted=true getter=-0.25 budget=(\d+)', t)
        chk(f'unit rep{rep} v={v} setter accepts -0.25, budget 0', bool(s2) and int(s2.group(1)) == 0)
        h = re.search(r'after_accepted_init=(\d+)', t)
        heaps[(rep, v)] = int(h.group(1))
hs = list(heaps.values())
chk('unit heap after init+GC spread across accepted values < 8 MiB', max(hs) - min(hs) < 8 * 1048576, f'min {min(hs)} max {max(hs)}')
ctl = open(U + '/readings-control.txt').read()
chk('closed control: 56 OK, 0 MISMATCH', ctl.count('READING OK') == 56 and 'MISMATCH' not in ctl, f'OK={ctl.count("READING OK")}')
# cluster
Cd = R + '/cluster'
res = {}
for p in ('0.95', '0.10', '1.0'):
    res[p] = json.load(open(f'{Cd}/run-{p}/result-{p}.json'))
inv = open(Cd + '/invalid/summary.txt').read()
chk('cluster 1.5: node refused to start, line-1017 text', 'alive after' in inv and 'node alive after' in inv and ': False;' in inv and 'in stdout: True' in inv)
for p, r in res.items():
    T = sum(r['ss0'])
    if p in ('0.95', '1.0'):
        chk(f'cluster {p}: compact rc 0, 4 sstables -> 1', r['rc'] == 0 and len(r['ss0']) == 4 and len(r['ss1']) == 1)
        chk(f'cluster {p}: no "has only" WARN', r['warn'] == 0)
        chk(f'cluster {p}: rise in [0.7, 1.2] x sum(Data.db)', 0.7 * T <= r['rise'] <= 1.2 * T, f'rise {r["rise"]} T {T} ratio {r["rise"] / T:.3f}')
    else:
        chk(f'cluster {p}: compact fails (rc != 0), 4 sstables unchanged', r['rc'] != 0 and r['ss1'] == r['ss0'])
        chk(f'cluster {p}: "has only" WARN >= 1 and reduce-scope/not-enough lines >= 1', r['warn'] >= 1 and r['reduce'] >= 1, f'warn {r["warn"]} reduce {r["reduce"]}')
        chk(f'cluster {p}: rise < 16 MiB', r['rise'] < 16 * 1048576, str(r['rise']))
        chk(f'cluster {p}: every sstable larger than the budget', min(r['ss0']) > int(r['budgets'][0][0]), f'min {min(r["ss0"])} budget {r["budgets"][0][0]}')
d = [r['du0'] for r in res.values()]; h = [r['heap'] for r in res.values()]
chk('at-rest du across settings < 8 MiB apart', max(d) - min(d) < 8 * 1048576, str(d))
chk('at-rest heap across settings < 32 MiB apart', max(h) - min(h) < 32 * 1048576, str(h))
for p, r in res.items():
    b = int(r['budgets'][0][0]); free = r['avail0']; mf = 50 * 1048576
    chk(f'cluster {p}: logged budget == round((avail-50MiB)*pct) within 1 MiB', abs(b - round((free - mf) * float(p))) <= 1048576, f'{b} vs {round((free - mf) * float(p))}')
print('FAILS', bad)
sys.exit(1 if bad else 0)
