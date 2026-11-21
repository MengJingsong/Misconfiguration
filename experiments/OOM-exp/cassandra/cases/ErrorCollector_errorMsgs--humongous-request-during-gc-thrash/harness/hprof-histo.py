#!/usr/bin/env python3
"""U6 copy of B14's copy of the B10 stage-2 tool (want-list changed for U6 classes, --len-range added, 2026-11-18); B10 stage 2 (2026-11-17): class histogram of an HPROF heap dump (the -XX:+HeapDumpOnOutOfMemoryError file), read-only.
Counts every object record in the dump (the OOM dump is written after the failing full GC; no reachability filter).
Shallow bytes: instance = 16 + field bytes, object array = 16 + n*id, primitive array = 16 + n*elem (compressed-oops
header estimate). Also counts byte[] of exactly --value-len bytes (the decoded bound values, CBUtil.readValue).
usage: hprof-histo.py <file.hprof> [--len-range 47 54] [--top 25]
Also counts byte[] with length in --len-range (the ErrorCollector messages), char[]/byte[]/Object[] >= 1 MiB elements.
"""
import mmap, struct, sys
from collections import defaultdict

ELEM = {2: None, 4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}
PRIM_NAME = {4: 'boolean[]', 5: 'char[]', 6: 'float[]', 7: 'double[]', 8: 'byte[]', 9: 'short[]', 10: 'int[]', 11: 'long[]'}


def main():
    path = sys.argv[1]
    i = sys.argv.index('--len-range') if '--len-range' in sys.argv else -1
    lo, hi = (int(sys.argv[i + 1]), int(sys.argv[i + 2])) if i > 0 else (47, 54)
    big = defaultdict(lambda: [0, 0])
    top = int(sys.argv[sys.argv.index('--top') + 1]) if '--top' in sys.argv else 25
    f = open(path, 'rb')
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    z = mm.find(b'\0')
    idsz = struct.unpack('>I', mm[z + 1:z + 5])[0]
    idf = '>Q' if idsz == 8 else '>I'
    pos = z + 1 + 4 + 8
    strings, cls_name_id = {}, {}
    cnt, byt = defaultdict(int), defaultdict(int)
    cls_isize = {}
    vcount = 0; vbytes = [0]
    end = len(mm)
    U4 = struct.Struct('>I').unpack_from
    U2 = struct.Struct('>H').unpack_from
    ID = struct.Struct(idf).unpack_from
    while pos < end:
        tag = mm[pos]; ln = U4(mm, pos + 5)[0]; body = pos + 9; pos = body + ln
        if tag == 0x01:
            strings[ID(mm, body)[0]] = mm[body + idsz:body + ln].decode('utf-8', 'replace')
        elif tag == 0x02:
            cls_name_id[ID(mm, body + 4)[0]] = ID(mm, body + 8 + idsz)[0]
        elif tag in (0x0C, 0x1C):
            p, e = body, body + ln
            while p < e:
                st = mm[p]; p += 1
                if st == 0x21:
                    c = ID(mm, p + idsz + 4)[0]; nb = U4(mm, p + 2 * idsz + 4)[0]
                    cnt[c] += 1; byt[c] += 16 + nb
                    p += 2 * idsz + 8 + nb
                elif st == 0x23:
                    n = U4(mm, p + idsz + 4)[0]; t = mm[p + idsz + 8]
                    k = ('prim', t); cnt[k] += 1; byt[k] += 16 + n * ELEM[t]
                    if t == 8 and lo <= n <= hi:
                        vcount += 1; vbytes[0] += 16 + n
                    if n >= 1048576:
                        big[PRIM_NAME.get(t)][0] += 1; big[PRIM_NAME.get(t)][1] += 16 + n * ELEM[t]
                    p += idsz + 9 + n * ELEM[t]
                elif st == 0x22:
                    n = U4(mm, p + idsz + 4)[0]; c = ID(mm, p + idsz + 8)[0]
                    k = ('arr', c); cnt[k] += 1; byt[k] += 16 + n * idsz
                    if n >= 1048576:
                        big['Object[]'][0] += 1; big['Object[]'][1] += 16 + n * idsz
                    p += 2 * idsz + 8 + n * idsz
                elif st == 0x20:
                    c = ID(mm, p)[0]
                    q = p + 7 * idsz + 4
                    cls_isize[c] = U4(mm, q)[0]; q += 4
                    ncp = U2(mm, q)[0]; q += 2
                    for _ in range(ncp):
                        t = mm[q + 2]; q += 3 + (idsz if t == 2 else ELEM[t])
                    ns = U2(mm, q)[0]; q += 2
                    for _ in range(ns):
                        t = mm[q + idsz]; q += idsz + 1 + (idsz if t == 2 else ELEM[t])
                    nf = U2(mm, q)[0]; q += 2 + nf * (idsz + 1)
                    p = q
                elif st == 0xFF or st == 0x05 or st == 0x07:
                    p += idsz
                elif st == 0x01:
                    p += 2 * idsz
                elif st in (0x02, 0x03, 0x08):
                    p += idsz + 8
                elif st in (0x04, 0x06):
                    p += idsz + 4
                else:
                    sys.exit(f'unknown sub-record 0x{st:02x} at {p - 1}')

    def name(k):
        if isinstance(k, tuple):
            if k[0] == 'prim':
                return PRIM_NAME.get(k[1], str(k[1]))
            return strings.get(cls_name_id.get(k[1]), hex(k[1])).replace('/', '.') + '[]'
        return strings.get(cls_name_id.get(k), hex(k)).replace('/', '.')

    rows = sorted(((byt[k], cnt[k], name(k)) for k in cnt), reverse=True)
    total = sum(r[0] for r in rows)
    print(f'file {path} id_size {idsz} objects {sum(cnt.values())} shallow_bytes {total}')
    print(f'byte[{lo}..{hi}] count {vcount} bytes {vbytes[0]}')
    for k, (c, b) in sorted(big.items()):
        print(f'large {k} (>= 1M elements) count {c} bytes {b}')
    for want in ('java.util.LinkedList$Node', 'java.lang.String', 'java.util.LinkedList',
                 'org.apache.cassandra.cql3.ErrorCollector', 'org.antlr.runtime.NoViableAltException',
                 'org.antlr.runtime.CommonToken', 'org.apache.cassandra.cql3.Marker$Raw',
                 'org.apache.cassandra.cql3.AbstractMarker$Raw', 'org.apache.cassandra.cql3.ColumnSpecification',
                 'java.lang.StackTraceElement', 'java.util.ArrayList'):
        for b, c, nm in rows:
            if nm == want:
                print(f'class {nm} count {c} bytes {b}')
    print('rank bytes count class')
    for i, (b, c, nm) in enumerate(rows[:top]):
        print(f'{i + 1} {b} {c} {nm}')


if __name__ == '__main__':
    main()
