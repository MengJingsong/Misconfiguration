#!/usr/bin/env python3
"""Independent re-parse of run 1's raw files (does not import analyze_*.py). Usage: selfcheck.py <run1 dir on the node>
Recomputes every number from results-*.csv, ant logs, samples.csv, B-system.log, B-debug.log, session.log and checks the frozen predictions."""
import sys, os, re, glob, json, datetime, statistics, csv
R = sys.argv[1]
MiB = 1048576
out = []
def rec(part, ok, note):
    out.append((part, 'holds' if ok else 'DOES NOT HOLD', note)); print('%-9s %-13s %s' % (part, out[-1][1], note))

# ---------------- unit
arms = {}
for f in sorted(glob.glob(R + '/unit/raw/results-*.csv')):
    hdr = open(f).readline()
    lim = re.search(r'MaxDirectMemorySize=(\w+)', hdr)
    for row in csv.reader(l for l in open(f) if not l.startswith('#')):
        arms[row[0]] = (f, lim.group(1) if lim else None, row)
exp_lim = {'main': '512m', 'cap': '16m', 'cap38': '38m'}
for a, (f, lim, row) in arms.items():
    s = re.search(r'results-(\w+)\.csv', f).group(1)
    rec('U-limit', lim == exp_lim[s], '%s ran in a JVM with MaxDirectMemorySize=%s (expected %s)' % (a, lim, exp_lim[s]))
for s in ['main', 'cap', 'cap38']:
    log = open(R + '/unit/ant-%s.log' % s).read()
    rec('U-ant', 'Tests run: 1, Failures: 0, Errors: 0' in log, 'ant-%s.log: %s' % (s, re.search(r'Tests run:[^\n]*', log).group(0)))
def g(a, i): return arms[a][2][i]
for a in arms:
    row = arms[a][2]; kind, n, L = row[1], int(row[2]), int(row[3])
    bufB, ccB, bufA, ccA, p0, pC, pP, pCl = [int(x) for x in row[4:12]]
    dataOk, ctorEx, posEx = row[12], row[13], row[14]
    if a.startswith('cap'):
        continue
    if kind == 'natural':
        rec('U-' + a, ccA == (n * 3) // 2 and ccA > n and dataOk == 'yes' and not posEx[4:], 'n=%d W=%d (W-n=%d) ccAfter=%d (1.5n=%d) bytes-equal=%s' % (n, L, L - n, ccA, (n * 3) // 2, dataOk))
    elif kind == 'ratio11':
        rec('U-' + a, ccA == n and dataOk == 'yes' and pP - p0 == 2 * n, 'n=%d ccAfter=%d pool delta=%d (2n=%d)' % (n, ccA, pP - p0, 2 * n))
    else:
        e = n if L <= n else max((n * 3) // 2, L)
        rec('U-' + a, ccA == e and pP - p0 == n + ccA and pCl - p0 == 0, 'n=%d L=%d ccAfter=%d expected=%d pool delta=%d close delta=%d' % (n, L, ccA, e, pP - p0, pCl - p0))
D = 'Direct buffer memory'
if 'cap_wire32MiB' in arms:
    r = arms['cap_wire32MiB'][2]; rec('U-cap', r[13] == 'ctor:' and D in r[14] and int(r[7]) == 16384, 'cap_wire32MiB under 16m: ctor=%r pos=%r ccAfter=%s' % (r[13], r[14], r[7]))
if 'cap_natural16MiB_init' in arms:
    r = arms['cap_natural16MiB_init'][2]; rec('U-cap', D in r[13], 'cap_natural16MiB_init under 16m: ctor=%r' % r[13])
if 'cap38_natural16MiB' in arms and 'cap38_ratio11_16MiB' in arms:
    a1, a2 = arms['cap38_natural16MiB'][2], arms['cap38_ratio11_16MiB'][2]
    rec('U-cap38', a1[13] == 'ctor:' and D in a1[14] and a2[13] == 'ctor:' and a2[14] == 'pos:' and a2[12] == 'yes',
        'natural 16 MiB under 38m: ctor ok, pos=%r; raw-path 16 MiB under 38m: ctor ok, pos=%r, bytes equal=%s' % (a1[14], a2[14], a2[12]))

# ---------------- cluster
def ts(line):
    m = re.search(r'(\d{4}-\d\d-\d\d)T(\d\d:\d\d:\d\d),(\d{3})', line)
    if not m: return None
    return int(datetime.datetime.strptime(m.group(1) + 'T' + m.group(2), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000) + int(m.group(3))
P = {}
for d in sorted(glob.glob(R + '/cluster/r[0-9]*/')):
    name = os.path.basename(d.rstrip('/'))
    if not os.path.exists(d + 'summary.json'):
        rec('C-' + name, False, 'no summary.json'); continue
    s = json.load(open(d + 'summary.json'))
    bl = open(d + 'B-system.log', errors='replace').read().split('\n')
    t0 = next((ts(l) for l in bl if 'Executing streaming plan for Bootstrap' in l), None)
    t1 = next((ts(l) for l in bl if 'All sessions completed' in l), None)
    smp = [tuple(int(x) for x in l.split(',')[:2]) for l in open(d + 'samples.csv') if l[0].isdigit()]
    base = [u for t, u in smp if t0 - 5000 <= t < t0]
    win = [u for t, u in smp if t0 <= t <= (t1 or t0 + 120000) + 500]
    bmed = statistics.median(base); pk = max(win)
    P[name] = (pk - bmed) / MiB
    dbg = open(d + 'B-debug.log', errors='replace').read()
    n_true = dbg.count('Incoming stream entireSSTable=true'); n_false = dbg.count('Incoming stream entireSSTable=false')
    ddl = [l for l in open(d + 'session.log') if 'table created' in l]
    ssz = sorted(s['A_sstables'])[-1:]   # the glob ran right after compaction; the obsolete input file may still be on disk, the live SSTable is the compaction output
    alog = open(d + 'A-system.log', errors='replace').read()
    comp_ok = bool(re.search(r'Compacted \([^)]*\) 2 sstables to \[[^\]]*/ks/t-[^\]]*/%s' % ssz[0][0].replace('-Data.db', ''), alog))
    mode = s['mode']
    ok = (t0 is not None and len(base) > 100 and len(win) > 30 and comp_ok)
    if mode == 'normal':
        ok = ok and t1 is not None and s['B_outcome'] == 'B_UN_binary_running' and n_true == 0 and n_false > 0 and 0.35 < s['B_data_bytes'] / ssz[0][1] < 0.65
    elif mode == 'entire':
        ok = ok and t1 is not None and n_true > 0 and n_false == 0
    elif mode == 'cap':
        sl = [l for l in bl if 'java.lang.OutOfMemoryError: Direct buffer memory' in l or D in l]
        ok = ok and t1 is None and len(sl) > 0
        i = next(k for k, l in enumerate(bl) if 'java.lang.OutOfMemoryError: Direct buffer memory' in l)
        print('   first OOM in B-system.log line %d (stream window opened at line %d); frames: %s' % (i + 1, next(k for k, l in enumerate(bl) if 'Executing streaming plan' in l) + 1, [x.strip() for x in bl[i + 1:i + 7]]))
    rec('C-' + name, ok, 'chunk=%sKiB ratio=%s mode=%s | baseline=%.2f MiB peak=%.2f MiB P=%.2f MiB | window=%s ms samples_in_window=%d | stream entire=true/false lines %d/%d | A live sstables=1 (compaction output %s ok=%s, %.0f MiB) B received %.0f MiB | DDL ok=%s'
        % (s['chunk_kb'], s['ratio'], mode, bmed / MiB, pk / MiB, P[name], (t1 - t0) if t1 else 'none', len(win), n_true, n_false, ssz[0][0], comp_ok, ssz[0][1] / MiB, s['B_data_bytes'] / MiB,
           bool(ddl) and ("'chunk_length_in_kb':'%s'" % s['chunk_kb']) in ddl[0] and (("min_compress_ratio" in ddl[0]) == (s['ratio'] != '0'))))
def pk(n): return P.get(n)
need = ['r01_c16', 'r02_c64', 'r03_c4', 'r04_c1024_r0', 'r05_c1024_r11', 'r06_c16384_r0_a', 'r07_c16384_r11_a', 'r08_c16384_r0_b', 'r09_c16384_r11_b', 'r10_cap100m_c16384', 'r11_entire_c16384']
if all(k in P for k in need):
    Pa, Pb, Qa, Qb = P['r06_c16384_r0_a'], P['r08_c16384_r0_b'], P['r07_c16384_r11_a'], P['r09_c16384_r11_b']
    rec('C-pred5', 50 <= Pa <= 95 and 50 <= Pb <= 95, 'P(16384 KiB, ratio 0) = %.2f, %.2f MiB; frozen range [50, 95]' % (Pa, Pb))
    rec('C-predD', 5 <= Pa - Qa <= 11 and 5 <= Pb - Qb <= 11, 'D = P(r0)-P(r1.1) = %.2f (rep a), %.2f (rep b) MiB; frozen [5, 11]' % (Pa - Qa, Pb - Qb))
    rec('C-noise', abs(Pa - Pb) <= 2 and abs(Qa - Qb) <= 2, 'repeat differences: ratio 0 %.2f, ratio 1.1 %.2f MiB; frozen <= 2' % (abs(Pa - Pb), abs(Qa - Qb)))
    rec('C-dose', P['r06_c16384_r0_a'] > P['r04_c1024_r0'] > P['r02_c64'], 'P(16384)=%.2f > P(1024)=%.2f > P(64)=%.2f' % (P['r06_c16384_r0_a'], P['r04_c1024_r0'], P['r02_c64']))
    rec('C-info', True, 'informational: P(4)=%.2f P(16)=%.2f P(64)=%.2f P(1024 r0)=%.2f P(1024 r1.1)=%.2f D(1024)=%.2f MiB' % (P['r03_c4'], P['r01_c16'], P['r02_c64'], P['r04_c1024_r0'], P['r05_c1024_r11'], P['r04_c1024_r0'] - P['r05_c1024_r11']))
    rec('C-entire', P['r11_entire_c16384'] <= 10, 'entire-sstable control P = %.2f MiB (frozen <= 10)' % P['r11_entire_c16384'])
else:
    rec('C-pred', False, 'missing runs: %s' % [k for k in need if k not in P])
json.dump(out, open(R + '/selfcheck.json', 'w'), indent=1)
print('SUMMARY holds=%d does-not-hold=%d' % (sum(1 for o in out if o[1] == 'holds'), sum(1 for o in out if o[1] != 'holds')))
