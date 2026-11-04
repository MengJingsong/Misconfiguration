#!/usr/bin/env python3
"""PASS/FAIL per frozen unit prediction (B2f as amended B5). Usage: analyze_unit.py <unit raw dir>"""
import csv, sys, math, os
d = sys.argv[1]
N = int(os.environ.get("STAGE4_N", 1000000)); PER = 224
res = {r['arm']: r for r in csv.DictReader(open(d + '/unit-results.csv'))}
cuts = {}
for r in csv.DictReader(open(d + '/unit-cuts.csv')):
    cuts.setdefault(r['arm'], []).append((int(r['add_index']), int(r['segments']), int(r['estimate_at_cut'])))
gm = {r['option']: r for r in csv.DictReader(open(d + '/getmode.csv'))}
fail = 0
def check(name, expected, got):
    global fail
    ok = expected == got; fail += (not ok)
    print('%s  %s  EXPECTED: %s  GOT: %s' % ('PASS' if ok else 'FAIL', name, expected, got))
DEF = 161061273
for opt, exp, rev in [('absent', DEF, 0), ('0', 0, 0), ('1', 1048576, 0), ('8', 8388608, 0), ('64', 67108864, 0), ('102400', 107374182400, 0),
                      ('102401', DEF, 1), ('-1', -1048576, 0), ('9223372036854775807', -1048576, 0), ('abc', 'NumberFormatException', 0)]:
    r = gm[opt]
    check('getMode(%s) bytes' % opt, str(exp), r['max_bytes_or_exception'])
    check('getMode(%s) "reverting" error lines' % opt, rev, int(r['reverting_log_lines']))
cases = [('comp-102400', 107374182400), ('comp-102401', DEF), ('comp-default', DEF), ('comp-1', 1 << 20), ('flush-1', 1 << 30)]
for arm, limit in cases:
    n = math.ceil(limit / PER); exp_cuts = N // n; r = res[arm]
    check(arm + ' segments before complete', exp_cuts, int(r['segments_before_complete']))
    check(arm + ' max estimate', (n * PER if exp_cuts else N * PER), int(r['max_estimate']))
    if exp_cuts:
        cl = cuts.get(arm, [])
        check(arm + ' estimate at every cut', [n * PER] * exp_cuts, [c[2] for c in cl])
        check(arm + ' cut positions (add index)', [n * k for k in range(1, exp_cuts + 1)], [c[0] for c in cl])
    check(arm + ' segment files on disk == segments', exp_cuts, int(r['segment_files_on_disk']))
    check(arm + ' Flushed-index-segment log lines (cuts + inline tail when any cut)', (exp_cuts + 1) if exp_cuts else 0, int(r['flushed_segment_logs']))
    check(arm + ' segment files left after complete', 0, int(r['segment_files_after_complete']))
    check(arm + ' final index terms', N, int(r['final_terms']))
    check(arm + ' errors logged', 0, int(r['errors_logged']))
for arm, limit in cases:
    r = res[arm]
    print('INFO heap  %s active-builder estimate %s heap_delta %s ratio %.2f' % (arm, r['estimate_active_before_complete'], r['heap_delta_active_bytes'], int(r['heap_delta_active_bytes']) / max(1, int(r['estimate_active_before_complete']))))
print('FAILS', fail); sys.exit(1 if fail else 0)
