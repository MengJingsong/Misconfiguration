#!/usr/bin/env python3
"""Cluster-tier PASS/FAIL per frozen prediction B3f(1)-(4) (as amended B5). Usage: analyze_cluster.py <outdir with m/ c1/ c16/ tc/>. Exit 1 on any FAIL."""
import json, sys, os, csv
od = sys.argv[1]
fails = 0
def check(tag, exp, got, ok):
    global fails
    print('%s EXPECTED: %s | GOT: %s | %s' % (tag, exp, got, 'PASS' if ok else 'FAIL'))
    if not ok: fails += 1
L = {l: json.load(open('%s/%s/summary.json' % (od, l))) for l in ('m', 'c1', 'c16', 'tc')}
for l, d in L.items():
    check('valid %s' % l, 'no error; -Xms2G -Xmx2G', 'error=%s xmx=%s xms=%s' % (d.get('error'), d.get('xmx'), d.get('xms')), 'error' not in d and d['xmx'] == ['-Xmx2G'] and d['xms'] == ['-Xms2G'])
    allw = [d[k] for k in d if k.startswith('log_')]
    check('no OOM / other ERROR %s' % l, '0 / 0', '%d / %d' % (sum(w['oom'] for w in allw), sum(w['error_lines_other'] for w in allw)), all(w['oom'] == 0 and w['error_lines_other'] == 0 for w in allw))
    check('no builder ERROR rejection line %s' % l, 0, sum(w['err_rejecting_builder'] for w in allw), all(w['err_rejecting_builder'] == 0 for w in allw))
# (1) label m
m = L['m']; s1, s2 = m['steps']
a1, a2 = s1['files_after_flush']['si_bytes_by_index']['t_a_idx'], s2['files_after_flush']['si_bytes_by_index']['t_a_idx']
check('B3f(1) a bytes lower bound', '>= rows*1023 at 100k and 400k', 'a1=%d (min %d) a2=%d (min %d)' % (a1, 100000 * 1023, a2, 400000 * 1023), a1 >= 100000 * 1023 and a2 >= 400000 * 1023)
check('B3f(1) a bytes ratio 400k/100k', '3.5..4.5', '%.2f' % (a2 / a1), 3.5 <= a2 / a1 <= 4.5)
check('B3f(1) b index bytes', '0 at both steps and after compaction', '%s %s %s' % (s1['files_after_flush']['si_bytes_by_index']['t_b_idx'], s2['files_after_flush']['si_bytes_by_index']['t_b_idx'], m['files_after_compact']['si_bytes_by_index']['t_b_idx']),
      s1['files_after_flush']['si_bytes_by_index']['t_b_idx'] == 0 and s2['files_after_flush']['si_bytes_by_index']['t_b_idx'] == 0 and m['files_after_compact']['si_bytes_by_index']['t_b_idx'] == 0)
for n, rows in ((1, 100000), (2, 300000)):
    lo, fl = m['log_load%d' % n], m['log_flush%d' % n]
    check('B3f(1) b memtable-path lines step %d' % n, "Can't add term col b = %d" % rows, str(lo['cant_add_col_b'] + fl['cant_add_col_b']), lo['cant_add_col_b'] + fl['cant_add_col_b'] == rows)
    check('B3f(1) b writer-path lines step %d (load+flush windows)' % n, 'Rejecting value col b = %d, col a = 0' % rows, 'b=%d a=%d' % (lo['rejecting_writer_col_b'] + fl['rejecting_writer_col_b'], lo['rejecting_writer_col_a'] + fl['rejecting_writer_col_a']),
          lo['rejecting_writer_col_b'] + fl['rejecting_writer_col_b'] == rows and lo['rejecting_writer_col_a'] + fl['rejecting_writer_col_a'] == 0)
c = m['log_compact']
check('B3f(1) b writer-path lines in compaction', '400000', str(c['rejecting_writer_col_b']), c['rejecting_writer_col_b'] == 400000)
check('B3f(1) queries', 'a -> 1 row, b -> 0 rows, before and after compaction', '%s | %s' % (m['queries_before_compact'], m['queries_after_compact']),
      all('query a' in q and ' 1 rows' in q for q in (m['queries_before_compact'][0], m['queries_after_compact'][0])) and all(' 0 rows' in q for q in (m['queries_before_compact'][1], m['queries_after_compact'][1])))
# (2) cap control
cmin = {'m': (129575, 'def'), 'c16': (13498, '16'), 'c1': (844, '1')}
after = {}
for l, (cm, opt) in cmin.items():
    d = L[l]; cuts = 400000 // cm; lines = cuts + (1 if 400000 % cm else 0)
    got = d['log_compact'].get('flushed_segment_t_a_idx', 0)
    pre = sum(d[k].get('flushed_segment_total', 0) for k in d if k.startswith('log_') and k != 'log_compact')
    check('B3f(2) %s (option %s) compaction-window segment lines' % (l, opt), '%d (floor(400000/%d)=%d cuts + leftover)' % (lines, cm, cuts), str(got), got == lines)
    check('B3f(2) %s flush/load-time segment lines' % l, '0', str(pre), pre == 0)
    after[l] = d['files_after_compact']['si_bytes_by_index']['t_a_idx']
check('B3f(2) a bytes after compaction equal across m, c1, c16 (1%)', 'max/min <= 1.01', str(after), max(after.values()) / min(after.values()) <= 1.01)
# (3) tc
t = L['tc']; ta, tb = t['steps'][0]['files_after_flush']['si_bytes_by_index']['tc_c_idx'], t['steps'][1]['files_after_flush']['si_bytes_by_index']['tc_c_idx']
allw = [t[k] for k in t if k.startswith('log_')]
check('B3f(3) tc rejections', "0 Rejecting value, 0 Can't add term", '%d, %d' % (sum(w['rejecting_writer_total'] for w in allw), sum(w['cant_add_total'] for w in allw)), all(w['rejecting_writer_total'] == 0 and w['cant_add_total'] == 0 for w in allw))
check('B3f(3) tc index bytes ratio 8000/2000 rows', '3..5', '%d / %d = %.2f' % (tb, ta, tb / ta), 3 <= tb / ta <= 5)
# (4) indicative
for l in ('m', 'c1', 'c16'):
    rows = list(csv.DictReader(open('%s/%s/compaction-histo.csv' % (od, l))))
    peak = max(int(r['dttb_instances']) for r in rows)
    cm = cmin[l][0]
    check('B3f(4) %s live DynamicTokenTreeBuilder peak (indicative)' % l, '< 2 x %d' % cm, '%d over %d samples' % (peak, len(rows)), peak < 2 * cm)
print('SUMMARY', 'ALL PASS' if not fails else '%d FAIL' % fails)
sys.exit(1 if fails else 0)
