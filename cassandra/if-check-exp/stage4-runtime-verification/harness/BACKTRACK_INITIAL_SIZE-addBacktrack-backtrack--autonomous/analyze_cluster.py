#!/usr/bin/env python3
"""Checks the frozen cluster-tier predictions (case file B3i.6) against <outdir>/<label>/result.json. Usage: analyze_cluster.py <outdir>"""
import sys, os, json, re
out = sys.argv[1]
npass = nfail = 0
def chk(ok, msg):
    global npass, nfail
    if ok: npass += 1
    else: nfail += 1
    print(('PASS ' if ok else 'FAIL ') + msg)
def parse_stats(s):
    d = dict(re.findall(r'(\w+)=(\d+)', s)); cur = int(d.get('cursors', -1))
    grow = {int(k[4:]): int(v) for k, v in d.items() if k.startswith('grow')}
    return cur, grow
UNIT = {'B': 1, 'KiB': 1024, 'MiB': 1 << 20, 'GiB': 1 << 30}
def first_limit_flush(res):
    for l in res['flush_log']:
        m = re.search(r'Enqueuing flush of ks\.t, Reason: MEMTABLE_LIMIT, Usage: ([\d.]+)(\w+) \((\d+)%\) on-heap, ([\d.]+)(\w+) \((\d+)%\) off-heap', l)
        if m: return float(m.group(1)) * UNIT[m.group(2)] / (1 << 20), float(m.group(4)) * UNIT[m.group(5)] / (1 << 20)
    return None
R = {}
for lab in ('hb64', 'hb256', 'hb512', 'oo64', 'm3', 'sl'):
    f = os.path.join(out, lab, 'result.json')
    if os.path.exists(f): R[lab] = json.load(open(f))
    else: print('MISSING', lab)
maxlen = {}
for lab, r in R.items():
    cur, grow = parse_stats(r['stats_final'])
    chk(r['filler']['err'] == 0 and r['scan']['err'] == 0 and r['scan']['scans'] > 0 and r['scan']['badrows'] == 0 and r['errors']['log_ERROR_lines'] == 0,
        '%s validity: filler err %s, scan err %s, scans %s, badrows %s, log ERROR lines %s' % (lab, r['filler']['err'], r['scan']['err'], r['scan']['scans'], r['scan']['badrows'], r['errors']['log_ERROR_lines']))
    if lab in ('hb64', 'hb256', 'hb512', 'oo64'):
        olds = sorted(grow)
        chk(set(olds) <= {48, 96, 192, 384, 768, 1536} and set(olds) == {48, 96, 192, 384, 768, 1536}, '%s grow old lengths %s (predicted exactly {48..1536})' % (lab, olds))
        counts = set(grow.values()); N = max(counts) if counts else 0
        chk(len(counts) == 1 and N >= 16, '%s the six counts are equal (%s), N=%d >= 16' % (lab, sorted(counts), N))
        chk(not any(k >= 3072 for k in grow), '%s no event with old length >= 3072' % lab)
        maxlen[lab] = 2 * max(grow) if grow else 48
        chk(maxlen[lab] == 3072, '%s largest array %d ints = %d B (predicted 3072 ints = 12304 B)' % (lab, maxlen[lab], 16 + 4 * maxlen[lab]))
        chk(r['stats_final'] is not None and cur >= 16, '%s cursors counted %d' % (lab, cur))
        a = {x['tag']: x for x in r['accounting']}
        chk(a['before_scan']['MemtableOnHeapDataSize'] == a['after_scan']['MemtableOnHeapDataSize'] and a['before_scan']['MemtableOffHeapDataSize'] == a['after_scan']['MemtableOffHeapDataSize'],
            '%s accounting equal before/after scan phase: on-heap %s -> %s, off-heap %s -> %s' % (lab, a['before_scan']['MemtableOnHeapDataSize'], a['after_scan']['MemtableOnHeapDataSize'], a['before_scan']['MemtableOffHeapDataSize'], a['after_scan']['MemtableOffHeapDataSize']))
    elif lab == 'm3':
        chk(not grow and cur >= 1000, 'm3 zero grow events (%s) and cursors %d >= 1000' % (grow, cur))
    elif lab == 'sl':
        chk(not grow and cur == 0, 'sl cursors %d == 0 and zero grow events (%s)' % (cur, grow))
if len(maxlen) == 4: chk(len(set(maxlen.values())) == 1, 'largest array equal across hb64/hb256/hb512/oo64: %s' % maxlen)
S = {l: first_limit_flush(R[l]) for l in R}
print('first MEMTABLE_LIMIT flush usage (on-heap MiB, off-heap MiB):', S)
if all(S.get(l) for l in ('hb64', 'hb256', 'hb512')):
    r4 = S['hb256'][0] / S['hb64'][0]; r8 = S['hb512'][0] / S['hb64'][0]
    chk(3 <= r4 <= 5, 'control S(256)/S(64) = %.2f in [3,5]' % r4)
    chk(6 <= r8 <= 10, 'control S(512)/S(64) = %.2f in [6,10]' % r8)
if S.get('oo64'): chk(10 <= S['oo64'][1] <= 40, 'control oo64 off-heap usage at first limit flush %.1f MiB in [10,40]' % S['oo64'][1])
print('SUMMARY pass=%d fail=%d' % (npass, nfail))
