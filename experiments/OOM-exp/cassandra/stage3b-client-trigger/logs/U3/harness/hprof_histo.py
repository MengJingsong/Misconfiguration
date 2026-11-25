#!/usr/bin/env python3
"""Minimal HPROF (JAVA PROFILE 1.0.2) parser for U3 (design §2.6 O3). Pure Python + struct, run with python3 -I.
usage: hprof_histo.py <file.hprof> [top]
Prints: instance counts and approx. shallow bytes per class (instances: 12-byte header + field bytes, 8-aligned;
object arrays: 16 + n*id; primitive arrays: 16 + n*size), the U3 holder classes, and per-thread stack traces
classified by the U3 frame markers. A dump at OOM follows the failed full GC but is not preceded by an extra GC:
it approximates the live heap."""
import mmap, struct, sys
from collections import defaultdict

PSIZE = {4: 1, 8: 1, 5: 2, 9: 2, 6: 4, 10: 4, 7: 8, 11: 8}
PNAME = {4: 'boolean[]', 5: 'char[]', 6: 'float[]', 7: 'double[]', 8: 'byte[]', 9: 'short[]', 10: 'int[]', 11: 'long[]'}
HOLDERS = ['org.apache.cassandra.db.rows.ArrayCell', 'org.apache.cassandra.db.rows.BufferCell',
           'org.apache.cassandra.db.rows.CellPath$SingleItemCellPath', 'org.apache.cassandra.db.rows.BTreeRow',
           'org.apache.cassandra.db.rows.ComplexColumnData', 'java.nio.HeapByteBuffer', 'byte[]', 'java.lang.Object[]']
MARKERS = {'replica_row_build': ('UnfilteredSerializer.deserializeRowBody', 'UnfilteredSerializer.readComplexColumn',
                                 'UnfilteredSerializer.deserialize'),
           'response_serialize': ('ReadResponse', 'LocalDataResponse'),
           'coordinator': ('SelectStatement.processPartition', 'ResultSetBuilder', 'SelectStatement.process')}


def al8(x):
    return (x + 7) & ~7


def main():
    path = sys.argv[1]; top = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    f = open(path, 'rb'); m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    end = m.find(b'\0')
    hdr = m[:end].decode(); ids = struct.unpack_from('>I', m, end + 1)[0]
    pos = end + 1 + 4 + 8
    assert ids in (4, 8), ids
    idf = '>Q' if ids == 8 else '>I'
    u4 = struct.Struct('>I'); u2 = struct.Struct('>H'); idst = struct.Struct(idf)
    strings = {}; classname = {}; cserial = {}; frames = {}; traces = []
    inst_size = {}  # class id -> instance field bytes
    cnt = defaultdict(int); byt = defaultdict(int)
    acnt = defaultdict(int); abyt = defaultdict(int)  # obj arrays by class id
    pcnt = defaultdict(int); pbyt = defaultdict(int)
    nobj = 0
    L = len(m)
    while pos < L:
        tag = m[pos]; ln = u4.unpack_from(m, pos + 5)[0]; body = pos + 9; pos = body + ln
        if tag == 0x01:
            sid = idst.unpack_from(m, body)[0]
            strings[sid] = m[body + ids:body + ln].decode('utf-8', 'replace')
        elif tag == 0x02:
            ser = u4.unpack_from(m, body)[0]; cid = idst.unpack_from(m, body + 4)[0]
            nid = idst.unpack_from(m, body + 8 + ids)[0]
            classname[cid] = strings.get(nid, '?').replace('/', '.'); cserial[ser] = classname[cid]
        elif tag == 0x04:
            fid, mn, sg, sf = struct.unpack_from('>' + ('Q' if ids == 8 else 'I') * 4, m, body)
            cs, line = struct.unpack_from('>Ii', m, body + 4 * ids)
            frames[fid] = '%s.%s' % (cserial.get(cs, '?'), strings.get(mn, '?'))
        elif tag == 0x05:
            ser, tser, n = struct.unpack_from('>III', m, body)
            fl = [idst.unpack_from(m, body + 12 + i * ids)[0] for i in range(n)]
            traces.append((ser, tser, fl))
        elif tag in (0x0C, 0x1C):
            p = body; e = body + ln
            while p < e:
                st = m[p]; p += 1
                if st == 0x21:
                    cid = idst.unpack_from(m, p + ids + 4)[0]; n = u4.unpack_from(m, p + 2 * ids + 4)[0]
                    cnt[cid] += 1; byt[cid] += al8(12 + n); p += 2 * ids + 8 + n; nobj += 1
                elif st == 0x23:
                    n = u4.unpack_from(m, p + ids + 4)[0]; t = m[p + ids + 8]
                    s = n * PSIZE[t]; pcnt[t] += 1; pbyt[t] += al8(16 + s); p += ids + 9 + s; nobj += 1
                elif st == 0x22:
                    n = u4.unpack_from(m, p + ids + 4)[0]; cid = idst.unpack_from(m, p + ids + 8)[0]
                    acnt[cid] += 1; abyt[cid] += al8(16 + n * ids); p += 2 * ids + 8 + n * ids; nobj += 1
                elif st == 0x20:
                    cid = idst.unpack_from(m, p)[0]
                    q = p + ids + 4 + 6 * ids
                    inst_size[cid] = u4.unpack_from(m, q)[0]; q += 4
                    ncp = u2.unpack_from(m, q)[0]; q += 2
                    for _ in range(ncp):
                        t = m[q + 2]; q += 3 + (ids if t == 2 else PSIZE[t])
                    nst = u2.unpack_from(m, q)[0]; q += 2
                    for _ in range(nst):
                        t = m[q + ids]; q += ids + 1 + (ids if t == 2 else PSIZE[t])
                    nf = u2.unpack_from(m, q)[0]; q += 2 + nf * (ids + 1)
                    p = q
                elif st == 0xFF or st == 0x05 or st == 0x07:
                    p += ids
                elif st == 0x01:
                    p += 2 * ids
                elif st in (0x02, 0x03, 0x08):
                    p += ids + 8
                elif st in (0x04, 0x06):
                    p += ids + 4
                else:
                    raise SystemExit('unknown sub-record 0x%02x at %d' % (st, p - 1))
    rows = []
    for cid, c in cnt.items():
        rows.append((byt[cid], c, classname.get(cid, '0x%x' % cid)))
    for cid, c in acnt.items():
        nm = classname.get(cid, '0x%x' % cid)
        rows.append((abyt[cid], c, nm if nm.startswith('[') else nm + '(objarray)'))
    for t, c in pcnt.items():
        rows.append((pbyt[t], c, PNAME[t]))
    by = {}
    for b, c, nm in rows:
        nm2 = nm
        if nm.startswith('[L') and nm.endswith(';'):
            nm2 = nm[2:-1] + '[]'
        prev = by.get(nm2, (0, 0)); by[nm2] = (prev[0] + b, prev[1] + c)
    tot = sum(b for b, _ in by.values())
    print('HPROF %s header=%s idsize=%d objects=%d approx_shallow_total=%d (%.1f MB)' % (path, hdr, ids, nobj, tot, tot / 1e6))
    print('TOP %d by approx shallow bytes:' % top)
    for nm, (b, c) in sorted(by.items(), key=lambda x: -x[1][0])[:top]:
        print('  %14d B %12d  %s' % (b, c, nm))
    print('HOLDERS:')
    for nm in HOLDERS:
        b, c = by.get(nm, (0, 0)); print('  %-60s count=%d bytes=%d' % (nm, c, b))
    print('THREAD STACKS (%d traces with frames):' % sum(1 for t in traces if t[2]))
    tally = defaultdict(int)
    for ser, tser, fl in traces:
        names = [frames.get(x, '?') for x in fl]
        if not names:
            continue
        hit = [k for k, ms in MARKERS.items() if any(any(mk in nmf for mk in ms) for nmf in names)]
        for k in hit:
            tally[k] += 1
        if hit:
            print('  thread_serial=%d markers=%s top=%s' % (tser, ','.join(hit), ' <- '.join(n.split('.')[-2] + '.' + n.split('.')[-1] for n in names[:6])))
    print('MARKER TALLY ' + ' '.join('%s=%d' % (k, tally[k]) for k in MARKERS))


main()
