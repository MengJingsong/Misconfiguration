#!/usr/bin/env python3
"""Independent self-check of run 1 for the two NAME_LENGTH cases: re-parses the RAW files (unit test.out; cluster histo.txt, samples.csv,
node system.log, cmd.log and the node data directories), not the json that cluster-run.py wrote, and prints the numbers the conclusion cites.
usage: selfcheck.py --case ks|tbl [--tag run1]      (on the run node)"""
import argparse, glob, os, re, statistics, sys

ap = argparse.ArgumentParser()
ap.add_argument('--case', required=True, choices=['ks', 'tbl'])
ap.add_argument('--tag', default='run1')
a = ap.parse_args()
HOME = os.path.expanduser('~')
STEM = {'ks': 'schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous', 'tbl': 'table_name_length-validatetablename-name_length--autonomous'}[a.case]
BASE = '%s/s4-b2/logs/%s/%s' % (HOME, STEM, a.tag)
RUN = '%s/s4-b2/run/%s' % (HOME, a.case)
bad = 0


def line(s):
    print(s)


def claim(what, ok):
    """a check of the case's own claim (B1/B3g): 'refuted' is a result, not a failure of the self-check"""
    line('  [claim %s] %s' % ('holds' if ok else 'REFUTED', what))


def chk(what, ok):
    global bad
    if not ok:
        bad += 1
    line('  [%s] %s' % ('holds' if ok else 'DOES NOT HOLD', what))


line('== UNIT %s ==' % BASE)
t = open(BASE + '/unit/test.out').read().splitlines()
checks = [l for l in t if l.startswith('STAGE4 check')]
chk('%d known-answer checks, all ok (none MISMATCH)' % len(checks), checks and all(l.endswith(' ok') for l in checks))
for l in t:
    if l.startswith('STAGE4 case') or l.startswith('STAGE4 info'):
        line('  ' + l[:230])
sizes = {}
for l in t:
    m = re.match(r'STAGE4 size L=(\d+) N=(\d+) (?:T=(\d+)|extra_cols=(\d+)) rep=(\d+) total=(\d+) jamm_objectsizes=(\d+) per_', l)
    if m:
        L, N, X, Y, rep, tot, jm = int(m[1]), int(m[2]), int(m[3] or m[4]), None, int(m[5]), int(m[6]), int(m[7])
        sizes.setdefault((L, X), []).append(tot / N)
line('  per-object bytes (mean of %d reps; min..max):' % len(next(iter(sizes.values()))))
for k in sorted(sizes, key=lambda k: (k[1], k[0])):
    v = sizes[k]
    line('    L=%-4d %s=%-3d %.2f  (%.2f..%.2f)' % (k[0], 'T' if a.case == 'ks' else 'extra_cols', k[1], statistics.mean(v), min(v), max(v)))
if a.case == 'ks':
    lo, hi = statistics.mean(sizes[(10, 0)]), statistics.mean(sizes[(48, 0)])
    ctl = statistics.mean(sizes[(48, 10)]) - hi
    line('  L=10 -> 48 at T=0: %+.2f B per keyspace; T=0 -> 10 at L=48: %+.2f B per keyspace; control/delta = %.0f x' % (hi - lo, ctl, ctl / (hi - lo)))
    claim('the L change (38 chars) moves retained size by tens of bytes (<= 100 B per keyspace)', 0 < hi - lo <= 100)
    claim('the T control moves it at least 100 x more', ctl >= 100 * (hi - lo))
else:
    lo, hi = statistics.mean(sizes[(2, 0)]), statistics.mean(sizes[(222, 0)])
    ctl = statistics.mean(sizes[(48, 50)]) - statistics.mean(sizes[(48, 0)])
    line('  L=2 -> 222 at 0 extra columns: %+.2f B per table; 50 extra columns at L=48: %+.2f B per table; control/delta = %.0f x' % (hi - lo, ctl, ctl / (hi - lo)))
    claim('the L change (220 chars) moves retained size by a small multiple of 220 B (<= 1000 B per table)', 0 < hi - lo <= 1000)
    claim('the 50-column control moves it more than the whole name range', ctl > 5 * (hi - lo))

line('== CLUSTER %s ==' % BASE)
CL = BASE + '/cluster'
H = {}
for f in sorted(glob.glob(CL + '/*.histo.txt')):
    lab = os.path.basename(f).split('.')[0]
    tot = [int(m[1]) for m in (re.match(r'^Total\s+\d+\s+(\d+)', l) for l in open(f)) if m]
    H[lab] = tot[-1]
D = {}
for lab in H:
    d = '%s/%s' % (RUN, lab)
    s = 0
    names = []
    for r, ds, fs in os.walk(d + '/data'):
        for fn in fs:
            s += os.path.getsize(os.path.join(r, fn))
    for ks in os.listdir(d + '/data'):
        names.append(ks)
        names += os.listdir(os.path.join(d, 'data', ks))
    uk = [len(x) for x in os.listdir(d + '/data') if not x.startswith('system')]
    D[lab] = (s, max(len(x) for x in names), max(uk) if uk else 0)
    line('  %s histogram Total = %d B; data dir = %d B; longest dir name = %d (longest user keyspace dir = %d)' % (lab, H[lab], s, D[lab][1], D[lab][2]))
if all(l in H for l in ('A1', 'A2', 'B1', 'B2')):
    ma, mb = statistics.mean([H['A1'], H['A2']]), statistics.mean([H['B1'], H['B2']])
    spread = max(abs(H['A1'] - H['A2']), abs(H['B1'] - H['B2']))
    budget = 200 * 45 * 50 if a.case == 'ks' else 500 * 214 * 20
    line('  long mean - short mean = %+.0f B; rep spread = %d B; name-byte budget = %d B' % (mb - ma, spread, budget))
    dm = statistics.mean([D['B1'][0], D['B2'][0]]) - statistics.mean([D['A1'][0], D['A2'][0]])
    line('  data dir: long - short = %+.0f B (%.3f %% of %d)' % (dm, 100 * dm / D['A1'][0], D['A1'][0]))
    claim('arms differ by no more than max(budget, spread)', abs(mb - ma) <= max(budget, spread))
    claim('data dirs differ by no more than 1 %', abs(dm) <= 0.01 * D['A1'][0])
    if a.case == 'ks':
        chk('longest user keyspace directory: short arm 3 characters, long arm 48', D['A1'][2] == 3 and D['B1'][2] == 48 and D['A2'][2] == 3 and D['B2'][2] == 48)
    else:
        chk('longest directory name: short arm < 100, long arm exactly 255 (222 + 1 + 32)', D['A1'][1] < 100 and D['B1'][1] == 255 and D['B2'][1] == 255)
cmd = open(CL + '/cmd.log').read()
for m in re.finditer(r'^(\{"ok": true, "rejected": [^\n]*)', cmd, re.M):      # the client's stdout line (the stderr echo is cut at 300 characters)
    line('  reject reading: ' + m[1][:300])
want = 'Keyspace name must not be more than 48 characters long' if a.case == 'ks' else 'Table name must not be more than 222 characters long'
rl = [m[1] for m in re.finditer(r'^(\{"ok": true, "rejected": [^\n]*)', cmd, re.M)]
chk('%d rejection readings (2 expected, one per long arm), each rejected=true with the message "%s"' % (len(rl), want), len(rl) == 2 and all('"rejected": true' in x and want in x for x in rl))
for lab in sorted(H):
    lg = '%s/%s/logs/system.log' % (RUN, lab)
    e = len(re.findall(r'^ERROR', open(lg).read(), re.M))
    oom = open(lg).read().count('java.lang.OutOfMemoryError')
    line('  %s system.log: ERROR lines %d, OutOfMemory %d' % (lab, e, oom))
for lab in ('C64', 'C256'):
    f = '%s/%s.samples.csv' % (CL, lab)
    if os.path.exists(f):
        v = [(int(x[1]), int(x[2])) for x in (l.strip().split(',') for l in open(f)) if len(x) == 3 and x[1].isdigit() and x[2].isdigit()]
        lg = '%s/%s/logs/system.log' % (RUN, lab)
        fl = len(re.findall(r'Enqueuing flush of', open(lg).read()))
        line('  %s: %d samples, peak AllMemtablesHeapSize = %d B, peak heap used = %d B, flushes enqueued = %d' % (lab, len(v), max(x[0] for x in v), max(x[1] for x in v), fl))
        H[lab + '_peak'] = max(x[0] for x in v)
        H[lab + '_fl'] = fl
if 'C64_peak' in H and 'C256_peak' in H:
    claim('control B moves clearly: 64MiB peak <= 0.5 x 256MiB peak, and more flushes at 64MiB', H['C64_peak'] <= 0.5 * H['C256_peak'] and H['C64_fl'] > H['C256_fl'])
    if 'A1' in H and 'B1' in H:
        diff = abs(mb - ma)
        claim('arm difference is below 10 %% of the control peak difference (%d B)' % (H['C256_peak'] - H['C64_peak']), diff < 0.1 * (H['C256_peak'] - H['C64_peak']))
left = os.popen("ps -eo cmd | grep '[C]assandraDaemon'").read().strip()
chk('no CassandraDaemon left running', left == '')
print('SELFCHECK-RESULT: %s (%d integrity checks fail; [claim ...] lines are the case claim, not integrity)' % ('INTEGRITY OK' if bad == 0 else 'INTEGRITY PROBLEM', bad))
