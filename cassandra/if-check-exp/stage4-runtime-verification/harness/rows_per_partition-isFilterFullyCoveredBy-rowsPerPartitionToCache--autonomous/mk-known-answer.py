#!/usr/bin/env python3
"""Writes a synthetic unit.txt (row 110 B, header 60 B) for the instrument check of analyze_unit.py. Usage: mk-known-answer.py good|bad > file
'bad' lets N=10 cache 15 rows (cap broken) -- the analyzer must then print CLASS 'claim wrong'."""
import sys
mode = sys.argv[1]
def out(k, v): print('%s=%s' % (k, v))
out('ROWS', 1000); out('firsttrigger', 'OK')
for n, live in (('1', 1), ('10', 10), ('100', 100), ('ALL', 1000), ('2000', 1000)):
    if mode == 'bad' and n == '10': live = 15
    p = 'N' + n
    out(p + '.entry', 'present'); out(p + '.cachedLiveRows', live); out(p + '.rowCount', live); out(p + '.serializedSize', 60 + 110 * live)
    out(p + '.coveredFullSlice', 'true' if n in ('ALL', '2000') else 'false'); out(p + '.coveredHead5', 'false' if n == '1' else 'true')
    out(p + '.read1.rows', 5); out(p + '.read2.rows', 5)
out('N10.after1.miss', 1); out('N10.after1.hit', 0); out('N10.after2.hit', 1); out('N1.after2.hit', 0); out('N1.after2.outOfRange', 1)
out('NNONE.entry', 'absent'); out('NNONE.after2.hit', 0); out('NNONE.after2.miss', 0); out('NNONE.after2.outOfRange', 0); out('NNONE.isRowCacheEnabled', 'false')
out('TOMBROWS.entry', 'present'); out('TOMBROWS.cachedLiveRows', 10); out('TOMBROWS.rowCount', 60)
out('TOMBRANGE.cachedLiveRows', 10); out('TOMBRANGE.rowCount', 10); out('TOMBRANGE.rangeTombstones', 1)
for k, v in (('NOCK_N1_v100', 100), ('NOCK_N5_v100', 100), ('NOCK_N1_v5000', 5000)):
    out(k + '.cachedLiveRows', 1); out(k + '.rowCount', 1); out(k + '.serializedSize', 50 + v)
out('done', 1)
