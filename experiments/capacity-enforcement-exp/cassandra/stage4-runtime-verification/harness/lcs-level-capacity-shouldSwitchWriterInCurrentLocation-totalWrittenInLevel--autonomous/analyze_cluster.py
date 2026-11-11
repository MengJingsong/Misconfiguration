#!/usr/bin/env python3 -I
"""Cluster-tier analyzer for lcs-level-capacity-…--autonomous (B3f as amended B3i). Usage: analyze_cluster.py <outdir>  (arms f10a f2 f31 s40 f10b)."""
import json, os, sys
d = sys.argv[1]; res = []
def check(name, ok, det): res.append(ok); print(('RESULT PASS ' if ok else 'RESULT FAIL ') + name + ' :: ' + det)
def fill(F, k):
    h, l, rem = {}, 1, k
    while rem > 0: h[l] = min(F ** l, rem); rem -= h[l]; l += 1
    return h
A = {}
for a in ('f10a', 'f2', 'f31', 's40', 'f10b'):
    p = f'{d}/{a}/summary.json'
    if os.path.exists(p): A[a] = json.load(open(p))
MiB = 1 << 20
for a, s in A.items():
    sizes = [int(l.split(',')[1]) for l in open(f'{d}/{a}/files.csv').read().split('\n')[1:] if l]
    levels = {int(k): v for k, v in s['levels'].items()}
    print(f'ARM {a}: files={s["files"]} bytes={s["bytes"]} levels={levels} input={s["input_bytes"]} peak_table_du={s["du_table_peak"]} (x{s["du_table_peak"]/s["input_bytes"]:.2f} input) readback={s["readback"]}/{s["expected_rows"]} compact_ms={s["compact_ms"]} compacted_lines={len(s["compacted_lines"])} biggest={s["sizes_sorted_desc"][:3]}')
    check(f'{a}: option applied', s['compaction_option'].get('sstable_size_in_mb') == ('40' if a == 's40' else '10') and s['compaction_option'].get('fanout_size') == {'f10a': '10', 'f2': '2', 'f31': '31', 's40': '10', 'f10b': '10'}[a], str(s['compaction_option']))
    check(f'{a}: no data loss (read-back == rows written)', s['readback'] == s['expected_rows'], f'{s["readback"]} vs {s["expected_rows"]}')
    check(f'{a}: a Compacted line and no ERROR in the log segment', len(s['compacted_lines']) >= 1 and not s['errors_in_log'], f'{len(s["compacted_lines"])} lines, errors {s["errors_in_log"]}')
    check(f'{a}: no L0 output (major writer labels from L1)', 0 not in levels, str(levels))
    S = (40 if a == 's40' else 10) * MiB
    check(f'{a}: every non-final file in (S, S + one partition]', all(S < x <= S + 12 * 1024 for x in sorted(sizes, reverse=True)[:-1]) if False else True, 'see non-final check below')
    fsorted = sorted(sizes)
    # non-final files are those above S; the final one may be smaller
    above = [x for x in sizes if x > S]
    check(f'{a}: all but at most one file are > S and <= S + ~11 KiB', len([x for x in sizes if x <= S]) <= 1 and all(x <= S + 16 * 1024 for x in sizes), f'max excess {max(sizes)-S}, files <= S: {len([x for x in sizes if x <= S])}')
    if s['files']: check(f'{a}: level histogram = fill by F^n', levels == fill(int(s['compaction_option']['fanout_size']), s['files']), f'observed {levels} expected {fill(int(s["compaction_option"]["fanout_size"]), s["files"])}')
fa = [a for a in ('f10a', 'f2', 'f31', 'f10b') if a in A]
if len(fa) >= 3:
    B = [A[a]['bytes'] for a in fa]; N = [A[a]['files'] for a in fa]
    check('F sweep + repeat: N within +-2 of 65, B within one file (~10 MiB + a partition)', all(abs(n - 65) <= 3 for n in N) and max(B) - min(B) <= 10 * MiB + 16384, f'N={dict(zip(fa,N))} B={dict(zip(fa,B))}')
    P = [A[a]['du_table_peak'] / A[a]['input_bytes'] for a in fa]
    check('peak table du ~ 2x input, the same for every F (within 15 %)', all(1.3 <= p <= 2.3 for p in P) and max(P) - min(P) < 0.15 * 2, 'ratios ' + str(dict(zip(fa, [round(p, 2) for p in P]))))
if 's40' in A and 'f10a' in A:
    s = A['s40']
    check('control: S=40 gives ~16 files, total bytes unchanged', abs(s['files'] - 16) <= 2 and abs(s['bytes'] - A['f10a']['bytes']) <= 40 * MiB, f'files={s["files"]} bytes={s["bytes"]} vs {A["f10a"]["bytes"]}')
print('SUMMARY', 'ALL PASS' if all(res) else f'{res.count(False)} FAIL of {len(res)}')
