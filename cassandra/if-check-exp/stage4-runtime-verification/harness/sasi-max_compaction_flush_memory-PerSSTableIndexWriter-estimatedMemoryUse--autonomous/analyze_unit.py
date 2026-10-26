#!/usr/bin/env python3
"""PASS/FAIL per frozen unit prediction (B2f, with the B5 derived checks). Usage: analyze_unit.py <unit-results.csv> <unit-cuts.csv>"""
import csv, sys, math, os
res = {r['arm']: r for r in csv.DictReader(open(sys.argv[1]))}
cuts = {}
for r in csv.DictReader(open(sys.argv[2])):
    cuts.setdefault(r['arm'], []).append((int(r['add_index']), int(r['segments']), int(r['estimate_at_cut'])))
N = int(os.environ.get("STAGE4_N", 100000))   # STAGE4_N only for the instrument check
PER = 224   # 64+48+4 for a new 4-byte term, plus 60+40+8 per add
fail = 0
def check(name, expected, got):
    global fail
    ok = expected == got
    fail += (not ok)
    print('%s  %s  EXPECTED: %s  GOT: %s' % ('PASS' if ok else 'FAIL', name, expected, got))
cases = [('comp-1', 1 << 20), ('comp-4', 4 << 20), ('comp-16', 16 << 20), ('comp-default', 161061273), ('flush-1', 1 << 30), ('flush-default', 1 << 30)]
# frozen B2f: segments cut 21 / 5 / 1 / 0 / 0; estimate at every cut = n*224 (first count with 224n >= limit); max estimate = limit + at most 224 (cuts) or 22,400,000 (no cut)
for arm, limit in cases:
    n = math.ceil(limit / PER)
    exp_cuts = N // n
    r = res[arm]
    check(arm + ' segments before complete', exp_cuts, int(r['segments_before_complete']))
    check(arm + ' max estimate', (n * PER if exp_cuts else N * PER), int(r['max_estimate']))
    if exp_cuts:
        cl = cuts.get(arm, [])
        check(arm + ' estimate at every cut', [n * PER] * exp_cuts, [c[2] for c in cl])
        check(arm + ' cut positions (add index)', [n * k for k in range(1, exp_cuts + 1)], [c[0] for c in cl])
    # derived checks
    check(arm + ' segment files on disk == segments', exp_cuts, int(r['segment_files_on_disk']))
    check(arm + ' non-null segments == segments', exp_cuts, int(r['segments_nonnull']))
    check(arm + ' Flushed-index-segment log lines (cuts + inline tail when any cut)', (exp_cuts + 1) if exp_cuts else 0, int(r['flushed_segment_logs']))
    check(arm + ' segment files left after complete', 0, int(r['segment_files_after_complete']))
    check(arm + ' final index terms', N, int(r['final_terms']))
    check(arm + ' errors logged', 0, int(r['errors_logged']))
for arm, limit in cases:
    r = res[arm]
    print('INFO heap  %s active-builder estimate %s heap_delta %s ratio %.2f' % (arm, r['estimate_active_before_complete'], r['heap_delta_active_bytes'], int(r['heap_delta_active_bytes']) / max(1, int(r['estimate_active_before_complete']))))
print('FAILS', fail)
sys.exit(1 if fail else 0)
