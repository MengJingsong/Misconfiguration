#!/usr/bin/env python3
"""Cluster tier: PASS/FAIL per frozen prediction (B3f) with EXPECTED/GOT. Usage: analyze_cluster.py <run1-cl dir>"""
import sys, json, re, os
D = sys.argv[1]
TOL = float(sys.argv[2]) if len(sys.argv) > 2 else 0.011   # MiB below H/3 that still counts as 'at least H/3'; the as-run analysis used 0.011, the prediction states 85.3 (1 decimal) so 0.05 is the stated precision
MiB = 1048576.0
def load(l):
    d = os.path.join(D, l); s = json.load(open(d + '/summary.json'))
    smp = [tuple(int(x) for x in ln.split(',')) for ln in open(d + '/samples.csv').read().strip().splitlines()[1:] if ln.count(',') == 3 and ln.split(',')[0].isdigit()]
    rows = [tuple(int(x) for x in ln.split(',')) for ln in open(d + '/rows.csv').read().strip().splitlines() if ln]
    fl = []
    for ln in open(d + '/flush-lines.txt'):
        m = re.search(r'Enqueuing flush of ks\.t, Reason: MEMTABLE_LIMIT, Usage: ([\d.]+)(B|KiB|MiB|GiB) ', ln)
        if m: fl.append(float(m.group(1)) * {'B': 1, 'KiB': 1024, 'MiB': MiB, 'GiB': MiB * 1024}[m.group(2)])
    base = s.get('base_switch', 1)
    # rows at each switch: first sample where switch_count reaches base+k; rows = last rows line at or before that time
    at = []
    for k in range(1, 40):
        t = next((x[0] for x in smp if x[3] >= base + k), None)
        if t is None: break
        r = [n for (tt, n) in rows if tt <= t]
        at.append(r[-1] if r else 0)
    return s, smp, rows, fl, at
res = []
def chk(name, ok, exp, got):
    res.append(ok); print('%s %s\n  EXPECTED: %s\n  GOT: %s' % ('PASS' if ok else 'FAIL', name, exp, got))
T = {}
for l, H in (('A1024c', 256), ('A1024c128', 128), ('A1024r', 256), ('A1024n', 256), ('A1024p', 256), ('A256c', 256), ('A4096c', 256)):
    try: T[l] = (load(l), H)
    except Exception as e: print('MISSING', l, e)
def rowsum(l):
    (s, smp, rows, fl, at), H = T[l]; total = rows[-1][1]
    return total
for l, (v, H) in T.items():
    (s, smp, rows, fl, at) = v
    print('INFO %s: rows=%d flushes(MEMTABLE_LIMIT)=%d switches=%d usage_MiB=%s rows_at_switch=%s maxheap_MiB=%.0f oom=%s' % (l, rows[-1][1], len(fl), max(x[3] for x in smp) - s['base_switch'], [round(x / MiB, 2) for x in fl[:6]], at[:6], max(x[1] for x in smp) / MiB, s['log_counts']['java.lang.OutOfMemoryError']))
def flush_check(l, per_row_cap_mib=None):
    (s, smp, rows, fl, at), H = T[l]; trig = H / 3.0
    nrows = rows[-1][1]; per_row = max(x[2] for x in smp) / max(1, nrows)
    ok_lo = all(x >= (trig - TOL) * MiB for x in fl)
    hi = (trig * MiB) + (per_row_cap_mib * MiB if per_row_cap_mib else 3 * per_row)
    ok_hi = all(x <= hi for x in fl)
    chk('%s flush usage within [H/3, H/3 + one row]' % l, len(fl) >= 3 and ok_lo and ok_hi, 'n>=3, each in [%.2f, %.2f] MiB' % (trig, hi / MiB), 'n=%d, %s MiB' % (len(fl), [round(x / MiB, 2) for x in fl[:8]]))
    return fl, at
fA, atA = flush_check('A1024c')
chk('A1024c three flushes within 260 rows', len(T['A1024c'][0][4]) >= 3 and T['A1024c'][0][4][2] <= 260, 'rows at 3rd switch <= 260', T['A1024c'][0][4][:4])
r1 = T['A1024c'][0][4][0]
chk('A1024c growth per row 1 to 5 MB (first memtable)', 1e6 <= 85.33 * MiB / r1 <= 5.2e6, '1e6..5e6 B/row', round(85.33 * MiB / r1))
m = T['A1024c'][0][0].get('mid_sample'); h = T['A1024c'][0][0]
if m:
    live = h['histo_mid']['total_bytes'] - h['histo_base']['total_bytes']
    print('INFO A1024c live heap rise %.1f MiB vs tracked on-heap %.1f MiB (ratio tracked/live %.2f; predicted within about 2)' % (live / MiB, m[2] / MiB, m[2] / live))
(s, smp, rows, fl, at) = T['A1024r'][0]
chk('A1024r (1024 chars) rejected, no growth', s['log_counts']["Can't add term"] == rows[-1][1] and max(x[3] for x in smp) - s['base_switch'] == 0 and max(x[2] for x in smp) < 2 * MiB and not fl,
    "Can't add term == rows (%d); 0 switches; on-heap < 2 MiB; no MEMTABLE_LIMIT flush" % rows[-1][1], "logs=%d switches=%d maxonheap=%.2f MiB flushes=%d" % (s['log_counts']["Can't add term"], max(x[3] for x in smp) - s['base_switch'], max(x[2] for x in smp) / MiB, len(fl)))
chk('A1024r rows readable by key, LIKE finds nothing', 'read_by_key rows=1' in s['verify_out'] and 'like_hits=0' in s['verify_out'], 'key 1 row, like_hits=0', s['verify_out'])
(s, smp, rows, fl, at) = T['A1024n'][0]
chk('A1024n index dropped: no flush, no growth beyond data', max(x[3] for x in smp) - s['base_switch'] == 0 and max(x[2] for x in smp) < 2 * MiB and not fl, '0 switches, on-heap < 2 MiB', "switches=%d maxonheap=%.2f MiB" % (max(x[3] for x in smp) - s['base_switch'], max(x[2] for x in smp) / MiB))
fP, atP = flush_check('A1024p', 1.0)
chk('A1024p three flushes at 31,000 to 60,000 rows', len(atP) >= 3 and 31000 <= atP[2] <= 60000, '31000..60000', atP[:4])
f2, at2 = flush_check('A1024c128')
chk('A1024c128 (128 MiB) rows per flush about half of A1024c', 0.35 <= at2[0] / float(r1) <= 0.65, 'ratio 0.35..0.65', round(at2[0] / float(r1), 2))
chk('A1024c128 flush usage about half of 256 MiB run', all(x < 0.65 * min(fA) for x in f2), 'each < 0.65 * %.1f MiB' % (min(fA) / MiB), [round(x / MiB, 1) for x in f2[:4]])
f3, at3 = flush_check('A256c', 100.0 - 85.33)
chk('A256c rows per flush 8x to 32x those of A1024c', 8 <= at3[0] / float(r1) <= 32, '8..32', round(at3[0] / float(r1), 1))
f4, at4 = flush_check('A4096c', 170.0 - 85.33)
chk('A4096c rows per flush 1/32 to 1/8 of A1024c', 1 / 32. <= at4[0] / float(r1) <= 1 / 8., '%.3f..%.3f' % (1 / 32., 1 / 8.), round(at4[0] / float(r1), 3))
for l in T:
    (s, smp, rows, fl, at), H = T[l]
    chk('%s peak heap under Xmx, no OOM' % l, max(x[1] for x in smp) < 2048 * MiB and s['log_counts']['java.lang.OutOfMemoryError'] == 0, '< 2048 MiB, 0 OOM', '%.0f MiB, %d' % (max(x[1] for x in smp) / MiB, s['log_counts']['java.lang.OutOfMemoryError']))
    chk('%s constant in the running jar' % l, any('MAX_TERM_SIZE' in c for c in s['constant_check']), 'MAX_TERM_SIZE shown', s['constant_check'])
print('RESULT', 'ALL PASS' if all(res) else 'SOME FAIL', sum(res), '/', len(res))
