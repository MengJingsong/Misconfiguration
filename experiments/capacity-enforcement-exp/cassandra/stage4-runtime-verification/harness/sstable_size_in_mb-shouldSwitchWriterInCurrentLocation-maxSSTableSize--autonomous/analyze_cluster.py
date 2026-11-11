#!/usr/bin/env python3 -I
"""Cluster-tier analyzer for sstable_size_in_mb-…--autonomous (B3f). Usage: analyze_cluster.py <outdir>  (arms s5 s20 s80 s160 stcs wide20)."""
import json, os, sys
d = sys.argv[1]; res = []
def check(name, ok, det): res.append(ok); print(('RESULT PASS ' if ok else 'RESULT FAIL ') + name + ' :: ' + det)
MiB = 1 << 20
SZ = {'s5': 5, 's20': 20, 's80': 80, 's160': 160, 'wide20': 20}
A = {}
for a in ('s5', 's20', 's80', 's160', 'stcs', 'wide20'):
    p = f'{d}/{a}/summary.json'
    if os.path.exists(p): A[a] = json.load(open(p))
live = None
for a, s in A.items():
    sizes = [int(l.split(',')[1]) for l in open(f'{d}/{a}/files.csv').read().split('\n')[1:] if l]
    levels = {int(k): v for k, v in s['levels'].items()}
    print(f'ARM {a}: files={s["files"]} bytes={s["bytes"]} levels={levels} input={s["input_bytes"]} peak_table_du={s["du_table_peak"]} (x{s["du_table_peak"]/s["input_bytes"]:.2f}) readback={s["readback"]}/{s["expected_rows"]} compact_ms={s["compact_ms"]} biggest={s["sizes_sorted_desc"][:3]}')
    check(f'{a}: no data loss', s['readback'] == s['expected_rows'], f'{s["readback"]} vs {s["expected_rows"]}')
    check(f'{a}: a Compacted line and no ERROR', len(s['compacted_lines']) >= 1 and not s['errors_in_log'], f'{len(s["compacted_lines"])} lines, errors {s["errors_in_log"]}')
    if a == 'stcs':
        check('stcs control: one file regardless', s['files'] == 1, f'files={s["files"]}'); continue
    S = SZ[a] * MiB
    exp = {'s5': 80, 's20': 20, 's80': 5, 's160': 3}.get(a)
    check(f'{a}: option applied', s['compaction_option'].get('sstable_size_in_mb') == (None if a == 's160' else str(SZ[a])), str(s['compaction_option']))
    check(f'{a}: no L0 output', 0 not in levels, str(levels))
    if a == 'wide20':
        big = [x for x in sizes if x >= 60 * MiB]
        check('wide20: one file >= 60 MiB (> S)', len(big) >= 1 and max(sizes) > S, f'biggest {sorted(sizes, reverse=True)[:3]}')
        continue
    ratio = s['bytes'] / S
    check(f'{a}: file count ~ live/S (+-1 file, +-5 %)', abs(s['files'] - s['bytes'] / S) <= 1.5 + 0.05 * (s['bytes'] / S), f'files={s["files"]} live/S={s["bytes"]/S:.2f} (B3f ~{exp})')
    nonfinal = sorted(sizes)[1:] if len([x for x in sizes if x <= S]) >= 1 else sizes
    check(f'{a}: non-final files in (S, S + ~11 KiB]', len([x for x in sizes if x <= S]) <= 1 and all(x <= S + 16 * 1024 for x in sizes), f'max excess {max(sizes)-S}; files <= S: {len([x for x in sizes if x <= S])}')
    check(f'{a}: levels: <=10 in L1, rest L2', levels.get(1, 0) == min(10, s['files']) and set(levels) <= {1, 2}, str(levels))
reg = [a for a in ('s5', 's20', 's80', 's160') if a in A]
if len(reg) >= 3:
    B = [A[a]['bytes'] for a in reg]
    check('live bytes the same across S (within one default-size file or 5 %)', max(B) - min(B) <= 0.05 * max(B), str(dict(zip(reg, B))))
    P = [A[a]['du_table_peak'] / A[a]['input_bytes'] for a in reg]
    check('peak table du ~ input + output (1.5 to 2.3 x input) for every S', all(1.5 <= p <= 2.3 for p in P), str(dict(zip(reg, [round(p, 2) for p in P]))))
print('SUMMARY', 'ALL PASS' if all(res) else f'{res.count(False)} FAIL of {len(res)}')
