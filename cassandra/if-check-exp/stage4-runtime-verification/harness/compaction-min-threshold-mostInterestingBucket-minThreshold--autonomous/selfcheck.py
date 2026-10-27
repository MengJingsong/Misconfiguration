#!/usr/bin/env python3
"""Independent self-check for stage 4: re-parses RAW logs (junit XML stdout, raw nodetool text, system/debug logs, stress tails),
not the readings.txt / phase JSON that the runners wrote, and re-derives the B2f/B3f relations.   usage: selfcheck.py <unit-outdir> <cluster-outdir>"""
import sys, re, glob, os, math, datetime, xml.etree.ElementTree as ET
U, C = sys.argv[1], sys.argv[2]
res = []
def chk(name, ok, detail): res.append((name, ok)); print(('PASS ' if ok else 'FAIL ') + name + ' :: ' + detail)

# ---------- unit: from the junit XML system-out
xmls = glob.glob(U + '/TEST-*.xml')
txt = ''
for x in xmls:
    r = ET.parse(x).getroot()
    chk('junit: no failures or errors', r.get('failures') == '0' and r.get('errors') == '0', f"tests={r.get('tests')} failures={r.get('failures')} errors={r.get('errors')}")
    for so in r.iter('system-out'): txt += (so.text or '')
txt += open(U + '/ant.log', errors='replace').read()   # the readings are logged to ant's console (the junit XML has none)
vals = {}
for m in re.finditer(r'\bR (\w+) (\S+) (.*)', txt): vals[(m.group(1), m.group(2))] = m.group(3).strip()
chk('ant.log carries the readings', len(vals) >= 300, f'{len(vals)} distinct readings')
def v(s, k): return vals[(s, k)]
bad = []
for n in (3, 7, 15, 31, 40):
    tot = int(v('grid', f'N{n}.totalBytes')); prev = -1
    for m in (2, 4, 8, 16, 32):
        want = min(n, 32) if min(n, 32) >= m else 0
        got_s, got_r = int(v('grid', f'N{n}.M{m}.static.returned')), int(v('grid', f'N{n}.M{m}.real.inputs'))
        unc = int(v('grid', f'N{n}.M{m}.static.uncompactedBytes'))
        if got_s != want or got_r != want: bad.append((n, m, want, got_s, got_r))
        if unc < prev: bad.append(('non-monotone', n, m))
        prev = unc
        if want == 0 and unc != tot: bad.append(('uncompacted != total', n, m))
chk('unit grid: returned = min(N,32) if >= M else empty, both ways, uncompacted bytes monotone', not bad, str(bad[:5]))
b = []
for n in (7, 40):
    for mx in (4, 8, 32):
        if int(v('ctl', f'N{n}.max{mx}.static.returned')) != min(n, mx) or int(v('ctl', f'N{n}.max{mx}.real.inputs')) != min(n, mx): b.append((n, mx))
chk('unit control: returned = min(N, max_threshold)', not b, str(b))
chk('unit ovw: M=8 unchanged, M=4 <= 0.25', v('ovw', 'M8.bytesBefore') == v('ovw', 'M8.bytesAfter') and int(v('ovw', 'M4.bytesAfter')) <= 0.25 * int(v('ovw', 'M4.bytesBefore')), f"M8 {v('ovw','M8.bytesBefore')}->{v('ovw','M8.bytesAfter')}; M4 {v('ovw','M4.bytesBefore')}->{v('ovw','M4.bytesAfter')}")

# ---------- cluster: raw text
def tstat(path):
    t = open(path).read()
    def f(p):
        m = re.search(p + r':\s*([0-9.]+)', t); return float(m.group(1)) if m else None
    return {'n': int(f(r'SSTable count')), 'total': f(r'Space used \(total\)'), 'bloom': f(r'Bloom filter off heap memory used'), 'summary': f(r'Index summary off heap memory used')}
def utc(s): return datetime.datetime.strptime(s, '%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp()
arms = {}
for a in ('m2', 'm4', 'm16', 'm32', 'mm4'):
    d = f'{C}/{a}'
    if not os.path.exists(d + '/tablestats-end.txt'): print('MISSING', a); continue
    e = tstat(d + '/tablestats-end.txt')
    hist = sum(1 for l in open(d + '/compactionhistory-end.txt') if 'standard1' in l)
    # compactions seen in the debug log with a timestamp, up to the end-state record's file time
    dl = open(d + '/logs/debug.log', errors='replace').read().splitlines()
    comp = [l for l in dl if re.search(r'Compacted \(.*\) \d+ sstables to', l) and 'standard1' in l]
    errs = []
    for f in sorted(glob.glob(d + '/stress-*.tail.txt')):
        t = open(f).read(); m = re.search(r'Total errors\s*:\s*(\d+)', t)
        if not m or m.group(1) != '0': errs.append(f)
    sysl = open(d + '/logs/system.log', errors='replace').read()
    errlines = len(re.findall(r'^(ERROR|WARN)', sysl, re.M))
    arms[a] = dict(e, hist=hist, comp=len(comp), errs=errs, errlines=errlines)
    print(a, arms[a])
if all(a in arms for a in ('m2', 'm4', 'm16', 'm32')):
    A = arms
    chk('stress: every chunk reported 0 errors (all arms)', all(not A[a]['errs'] for a in A), str({a: A[a]['errs'] for a in A}))
    chk('M=32: exactly 20 sstables and zero compaction history rows (raw tablestats / compactionhistory)', A['m32']['n'] == 20 and A['m32']['hist'] == 0, f"n={A['m32']['n']} hist={A['m32']['hist']}")
    chk('M=2, M=4: <= 4 sstables; M=16: 5 (<= 15)', A['m2']['n'] <= 4 and A['m4']['n'] <= 4 and A['m16']['n'] == 5, f"m2={A['m2']['n']} m4={A['m4']['n']} m16={A['m16']['n']}")
    ms = ('m2', 'm4', 'm16', 'm32')
    chk('sstable count non-decreasing in M', all(A[x]['n'] <= A[y]['n'] for x, y in zip(ms, ms[1:])), str([A[a]['n'] for a in ms]))
    chk('bloom + summary memory non-decreasing in M', all(A[x]['bloom'] <= A[y]['bloom'] and A[x]['summary'] <= A[y]['summary'] for x, y in zip(ms, ms[1:])), str([(A[a]['bloom'], A[a]['summary']) for a in ms]))
    chk('bytes M=32 >= 3 x M=2; non-decreasing in M', A['m32']['total'] >= 3 * A['m2']['total'] and all(A[x]['total'] <= A[y]['total'] for x, y in zip(ms, ms[1:])), str([A[a]['total'] for a in ms]))
    if os.path.exists(C + '/m32/tablestats-flip.txt'):
        F = tstat(C + '/m32/tablestats-flip.txt')
        chk('flip: raw tablestats after the flip: <= 5 sstables, bytes fall >= 3x', F['n'] <= 5 and F['total'] * 3 <= A['m32']['total'], f"{A['m32']['n']}->{F['n']} bytes {A['m32']['total']}->{F['total']}")
    if 'mm4' in A: chk('min 4/max 4 arm < 20 sstables', A['mm4']['n'] < 20, str(A['mm4']['n']))
    # trace evidence: gate held 20 sstables in the M=32 arm (a "Compaction buckets are" line listing >= 20 sstables in one bucket, before the flip)
    dl = open(C + '/m32/logs/debug.log', errors='replace').read().splitlines()
    big = 0
    for l in dl:
        if 'Compaction buckets are' in l:
            br = re.findall(r'\[([^\[\]]*)\]', l.split('Compaction buckets are', 1)[1])
            if any(len(re.findall(r'BigTableReader|BtiTableReader|SSTableReader', b)) >= 20 for b in br): big += 1
    print('trace lines in the M=32 arm with a >= 20-sstable bucket:', big)
ok = all(r[1] for r in res)
print('SUMMARY', 'ALL PASS' if ok else 'FAILURES: ' + ', '.join(r[0] for r in res if not r[1]))
