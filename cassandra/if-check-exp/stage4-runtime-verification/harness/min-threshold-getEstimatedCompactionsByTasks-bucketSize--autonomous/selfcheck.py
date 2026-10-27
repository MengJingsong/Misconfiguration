#!/usr/bin/env python3
"""Independent self-check: re-parses the raw logs (unit test.out; cluster session.log BASELINE lines, series CSVs, node system.log)
without using analyze-*.py or the ARM json lines. usage: selfcheck.py [run-name]"""
import csv, glob, json, math, os, re, sys
run = sys.argv[1] if len(sys.argv) > 1 else 'run1'
L = os.path.expanduser(f'~/s4-b11-m71-logs/{run}')
res = []
def chk(name, ok, note=''):
    res.append(ok); print(f'{"holds" if ok else "DOES NOT HOLD"}: {name} {note}')
# ---- unit
rows = []
for l in open(f'{L}/unit/test.out'):
    if l.startswith('STAGE4 cell '):
        rows.append({k: v for k, v in re.findall(r'(\w+)=(\S+)', l)})
chk('U1 14 recorded cells', len(rows) == 14, f'({len(rows)})')
bad = []
for r in rows:
    n, mn, mx = int(r['n']), int(r['min']), int(r['max'])
    want = math.ceil(n / mx) if n >= mn else 0
    if int(r['est']) != want or int(r['csm']) != want or int(r['gauge']) != want: bad.append((n, mn, r['est'], want))
chk('U2 estimate = ceil(n/max) if n>=min else 0, strategy, manager and gauge', not bad, str(bad))
for n in (8, 40):
    rr = [r for r in rows if int(r['n']) == n]
    chk(f'U3 n={n} bytes/live/total constant over min', all(len({r[k] for r in rr}) == 1 for k in ('bytes', 'live', 'total')), f"bytes {rr[0]['bytes']}")
    h = [int(r['heap']) for r in rr]
    chk(f'U4 n={n} heap spread < 1 MiB', max(h) - min(h) < 1048576, f'({(max(h)-min(h))/1048576:.3f} MiB)')
txt = open(f'{L}/unit/test.out').read()
ce = re.search(r'control-exec .*inputs=(\d+) sstables-before=(\d+) sstables-after=(\d+) bytes-before=(\d+) bytes-after=(\d+)', txt)
chk('U5 control: 8 inputs -> 1 sstable', ce and ce.group(1) == '8' and ce.group(3) == '1', ce.group(0) if ce else '')
cm = re.findall(r'control-max n=40 min=4 max=(\d+) est=(\d+) inputs=(\d+) input-bytes=(\d+)', txt)
chk('U6 control: max 4/32/4 -> inputs 4/32/4 and est 10/2/10', [(m[0], m[1], m[2]) for m in cm] == [('4', '10', '4'), ('32', '2', '32'), ('4', '10', '4')], str(cm))
x = glob.glob(f'{L}/unit/TEST-*.xml')
chk('U7 junit xml: 1 test, 0 failures, 0 errors', bool(x) and re.search(r'tests="1"', open(x[0]).read()) and 'failures="0"' in open(x[0]).read() and 'errors="0"' in open(x[0]).read())
# ---- cluster
C = f'{L}/cluster'
sess = open(f'{C}/session.log').read()
base = {m.group(1): json.loads(m.group(2)) for m in re.finditer(r'^BASELINE (\S+) (\{.*\})$', sess, re.M)}
chk('C0 11 baselines (9 estimate + 2 control)', len(base) == 11, str(sorted(base)))
slog = open(os.path.expanduser('~/s4-b11-m71-node/logs/system.log')).read()
comp = {}
for m in re.finditer(r'Compacted \(\S+\) (\d+) sstables to \[[^\]]*?/(\w+)/standard1-', slog):
    comp.setdefault(m.group(2), []).append(int(m.group(1)))
series = {}
for f in glob.glob(f'{C}/series-*.csv'):
    series[os.path.basename(f)[7:-4]] = list(csv.DictReader(open(f)))
est = [n for n in base if n.startswith('e')]
for mn, wantg in ((2, 1), (4, 1), (16, 0)):
    names = [n for n in est if n.endswith(f'm{mn}')]
    gm = {n: max(int(r['gauge']) for r in series[n] if r['gauge'] not in ('', 'None')) for n in names}
    chk(f'C1 min={mn}: max polled gauge = {wantg} in {len(names)} reps', len(names) == 3 and all(v == wantg for v in gm.values()), str(gm))
    if wantg:
        chk(f'C2 min={mn}: system.log shows exactly one "Compacted ... 10 sstables" per rep', all(comp.get('' + n, [])[:1] == [10] and len(comp.get(n, [])) == 1 for n in names), str({n: comp.get(n) for n in names}))
    else:
        chk(f'C2 min={mn}: no Compacted line in system.log', all(n not in comp for n in names))
tot = [base[n]['total'] for n in est]; dus = [base[n]['du'] for n in est]
chk('C3 baseline total/du spread < 2%', max(tot) < 1.02 * min(tot) and max(dus) < 1.02 * min(dus), f'(total {min(tot)}-{max(tot)}, du {min(dus)}-{max(dus)})')
for k in ('heap', 'rss'):
    mean = {mn: sum(base[n][k] for n in est if n.endswith(f'm{mn}')) / 3 for mn in (2, 4, 16)}
    sp = (max(mean.values()) - min(mean.values())) / min(mean.values())
    chk(f'C4 baseline {k} per-min means within 5%', sp <= 0.05, f'(spread {sp*100:.2f}%, means MB { {m: round(v/1e6,1) for m,v in mean.items()} })')
chk('C5 baseline gauge 0 and 10 sstables before the enable in all arms', all(b['gauge'] == 0 and b['sstables'] == 10 for b in base.values()))
chk('C6 control: first compaction 4 inputs at max=4, 10 at max=32', comp.get('c4', [None])[0] == 4 and comp.get('c32', [None])[0] == 10, f"{comp.get('c4')} {comp.get('c32')}")
def peak(n):
    mx = 0
    for r in series[n]:
        mx = max(mx, int(r['du']))
        if int(r['compacted_lines']) >= 1: break
    return mx - base[n]['du']
p4, p32 = peak('c4'), peak('c32')
chk('C7 control peak du above baseline: max=32 > 1.8 x max=4', p32 > 1.8 * p4, f'({p4/1e6:.0f} vs {p32/1e6:.0f} MB)')
for n in est:
    if not n.endswith('m16'):
        chk(f'C8 {n}: du rose above baseline by > 50 MB during its compaction (disk moved only after the enable)', max(int(r['du']) for r in series[n]) > base[n]['du'] + 50e6)
errs = len(re.findall(r'^ERROR', slog, re.M))
chk('C9 node system.log has 0 ERROR lines', errs == 0, f'({errs})')
print('ALL HOLD' if all(res) else 'SOME PARTS DO NOT HOLD')
