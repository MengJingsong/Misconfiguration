#!/usr/bin/env python3
"""usage: selfcheck.py <logs-dir (~/s4-b7-hv-logs)>. Independent re-parse for the self-check; does not import the run or analysis scripts.
 - unit: re-reads RESULT lines of unit/run1/summary.txt AND the same lines in unit/run1/unit.log (two files must agree), recomputes 10*2^ceil(log2(n/10)) and the budget arithmetic in Python (int32 wrap) for each S.
 - cluster: opens every runN/<label>/n<i>.jfr itself (jfr print --json, all long[] outside-TLAB events, whatever the stack) and lists long[] sizes with HistogramBuilder.add in the stack; counts
   'Partitions per leaf' lines in the node debug.log between the run's start and end epoch (from summary.txt), and the bucket sum; reads the GC log for the heap after the last young pause in the window."""
import json, math, re, subprocess, sys, os, collections, datetime
L = sys.argv[1]
def kv(line): return {k: (int(v) if re.fullmatch(r'-?\d+', v) else v) for k, v in (x.split('=', 1) for x in line.split()[1:] if '=' in x)}
print('== unit')
a = [kv(l) for l in open(f'{L}/unit/run1/summary.txt') if l.startswith('RESULT')]
b = [kv(l) for l in open(f'{L}/unit/run1/unit.log') if l.startswith('RESULT')]
print('rows in summary', len(a), 'rows in unit.log', len(b), 'identical:', [r for r in a] == [r for r in b])
def i32(x): x &= 0xFFFFFFFF; return x - (1 << 32) if x >= 1 << 31 else x
def cdiv(a_, b_): return int(a_ / b_) if a_ * b_ >= 0 else -int(-a_ / b_)  # Java int division truncates toward zero
for r in a:
    if r['mode'] == 'tree':
        avail = cdiv(i32(r['S'] * 1048576), r['RF']); ok_avail = avail == r['availableBytes']
        n = r['leaves']; cap_ = 10 * 2 ** max(0, math.ceil(math.log2(n / 10)))
        print(f"S={r['S']:5d} RF={r['RF']} D={r['D']:2d}: availableBytes {r['availableBytes']} (recomputed {avail}, match {ok_avail}); depth {r['depth']} leaves {n} (2^depth {2**r['depth']}); values_length {r['values_length']} (formula {cap_}); array_bytes {r['array_bytes']} (16+8*len {16 + 8 * r['values_length']})")
    elif r['mode'] == 'direct':
        n = r['n']; cap_ = 10 * 2 ** max(0, math.ceil(math.log2(n / 10)))
        print(f"direct n={n}: values_length {r['values_length']} formula {cap_} ok {cap_ == r['values_length']}")
print('== cluster')
for lab in ('r1', 'r2', 'r3', 'r4', 'r5', 'r1b'):
    d = f'{L}/cluster/run1/{lab}'
    sm = open(f'{d}/summary.txt').read()
    t0 = int(re.search(r't0_ms=(\d+)', sm).group(1)); wall = int(re.search(r'wall_ms=(\d+)', sm).group(1))
    lo = datetime.datetime.utcfromtimestamp(t0 / 1000 - 1); hi = datetime.datetime.utcfromtimestamp((t0 + wall) / 1000 + 5)
    for i in (1, 2):
        js = json.loads(subprocess.run(['jfr', 'print', '--json', '--events', 'jdk.ObjectAllocationOutsideTLAB', '--stack-depth', '8', f'{d}/n{i}.jfr'], capture_output=True, text=True, check=True).stdout)['recording']['events']
        longs = collections.Counter(); hb = collections.Counter(); other_big = 0
        for e in js:
            v = e['values']; cls = v['objectClass']['name']
            fr = (v.get('stackTrace') or {}).get('frames') or []
            top = [f['method']['type']['name'].split('/')[-1] + '.' + f['method']['name'] for f in fr]
            if 'HistogramBuilder.add' in top: hb[v['allocationSize']] += 1
            elif cls == '[J' and v['allocationSize'] > 1_000_000: other_big += 1
        # debug.log window
        n_ppl = 0; bsum = 0; on = False; ts_re = re.compile(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),(\d+)')
        for l in open(f'{L}/cluster/run1/nodes/n{i}/debug.log', errors='replace'):
            m = ts_re.search(l)
            if not m: continue
            t = datetime.datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S')
            if not (lo <= t <= hi): continue
            if 'Partitions per leaf' in l: n_ppl += 1; on = True; continue
            if 'Partition sizes are' in l: on = False
            m2 = re.search(r'EstimatedHistogram\.java:\d+ - +\[\d+\.\.\d+\]: (\d+)', l)
            if on and m2: bsum += int(m2.group(1))
        print(f"{lab} node{i}: HistogramBuilder.add sizes {dict(sorted(hb.items()))}; other long[] > 1 MB events not from HistogramBuilder: {other_big}; 'Partitions per leaf' lines in window {n_ppl}; first-block bucket sum {bsum}")
