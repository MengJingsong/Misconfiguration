#!/usr/bin/env python3
"""Cluster tier analysis against B3f / B3g (B3i of the file). Usage: analyze_cluster.py <outdir>
Thresholds are those made exact in B3i.5 before the run."""
import sys, os, re, csv, json
MiB = 1048576
out = sys.argv[1]
fails = []
def chk(name, ok, detail):
    print('RESULT', 'PASS' if ok else 'FAIL', name, detail)
    if not ok: fails.append(name)
def samples(a): return list(csv.DictReader(open(os.path.join(out, a, 'samples.csv'))))
def ph(a, p): return [s for s in samples(a) if s['phase'] == p][-1]
def summ(a): return json.load(open(os.path.join(out, a, 'summary.json')))
def setcap(a, tag):
    t = open(os.path.join(out, a, 'setcap-%s.out' % tag)).read()
    return int(re.search(r'exit: (\d+)', t)[1]), t
arms = [a for a in ('A', 'AP', 'B32', 'B8') if os.path.isdir(os.path.join(out, a))]
rssgrow = {}
for a in arms:
    S = samples(a)
    ld = ph(a, 'after-load'); last = ph(a, 'end-pass4') if a != 'B8' else ph(a, 'end-pass2')
    rssgrow[a] = int(last['rssAnon']) - int(ld['rssAnon'])
    print('INFO %s RssAnon growth after-load -> %s = %.1f MiB' % (a, last['phase'], rssgrow[a] / MiB))
for a in ('A', 'AP'):
    if a not in arms: continue
    S = samples(a)
    chk('%s RowCache Capacity/Size/Entries/Hits 0 at every sample (%d samples, all phases)' % (a, len(S)), all(int(s['capacity']) == 0 and int(s['size']) == 0 and int(s['entries']) == 0 and int(s['hits']) == 0 for s in S), 'max size=%d entries=%d capacity=%d' % (max(int(s['size']) for s in S), max(int(s['entries']) for s in S), max(int(s['capacity']) for s in S)))
    ex, txt = setcap(a, 'req64')
    if a == 'A':
        chk('A request 0 64 0 exits non-zero with "Setting capacity of NopCache is not permitted"', ex != 0 and 'Setting capacity of NopCache is not permitted' in txt, 'exit=%d %s' % (ex, txt.strip().splitlines()[-1][:120]))
        ex0, t0 = setcap(a, 'req0')
        chk('A request 0 0 0 exits 0', ex0 == 0, 'exit=%d' % ex0)
        S_ = summ(a); print('INFO A key cache line before / after the failed request:', S_.get('info_before'), '/', S_.get('info_after_req64'))
    else:
        chk('AP (patched) request 0 64 0 exits 0 and Capacity stays 0', ex == 0 and ph(a, 'end-pass4')['capacity'] == '0', 'exit=%d' % ex)
if 'B32' in arms:
    p2 = ph('B32', 'end-pass2'); p4 = ph('B32', 'end-pass4'); ex, txt = setcap('B32', 'req64')
    chk('B32 Capacity 32 MiB after passes 1-2, Size <= cap and >= 80%', int(p2['capacity']) == 32 * MiB and 0.8 * 32 * MiB <= int(p2['size']) <= 32 * MiB, 'size=%s cap=%s entries=%s' % (p2['size'], p2['capacity'], p2['entries']))
    chk('B32 request 0 64 0 exits 0, Capacity 64 MiB, Size <= cap and >= 80% after passes 3-4, Entries higher', ex == 0 and int(p4['capacity']) == 64 * MiB and 0.8 * 64 * MiB <= int(p4['size']) <= 64 * MiB and int(p4['entries']) > int(p2['entries']), 'exit=%d size=%s cap=%s entries %s -> %s' % (ex, p4['size'], p4['capacity'], p2['entries'], p4['entries']))
    chk('B32 Size <= Capacity at every sample', all(int(s['size']) <= int(s['capacity']) for s in samples('B32')), '')
if 'B8' in arms:
    p2 = ph('B8', 'end-pass2')
    chk('B8 Size <= 8 MiB and >= 80%', int(p2['capacity']) == 8 * MiB and 0.8 * 8 * MiB <= int(p2['size']) <= 8 * MiB, 'size=%s cap=%s entries=%s' % (p2['size'], p2['capacity'], p2['entries']))
    chk('B8 Size <= Capacity at every sample', all(int(s['size']) <= int(s['capacity']) for s in samples('B8')), '')
if 'B8' in arms and 'B32' in arms:
    r = int(ph('B32', 'end-pass2')['size']) / int(ph('B8', 'end-pass2')['size'])
    chk('Size(B32 at 32 MiB) / Size(B8) in [3,5]', 3 <= r <= 5, '%.2f' % r)
if 'A' in arms and 'B32' in arms:
    chk('A RssAnon growth < half of B32 growth', rssgrow['A'] < 0.5 * rssgrow['B32'], 'A=%.1f MiB B32=%.1f MiB' % (rssgrow['A'] / MiB, rssgrow['B32'] / MiB))
for a in arms:
    S_ = summ(a); print('INFO', a, 'errors_in_log=%s' % S_['errors_in_log'], '|', S_['nodetool_info_row'])
print('\nFAILED CHECKS (%d): %s' % (len(fails), fails))
