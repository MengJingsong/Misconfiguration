#!/usr/bin/env python3
"""Diagnostic (not a frozen observable): for each byte[] of a given length in an HPROF dump, list the classes of the
instances / object arrays that reference it, and for referencing instances one level further (who holds them).
Usage: hprof_refs.py <file.hprof> <len>"""
import mmap, struct, sys
from collections import defaultdict

TSIZE = {4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}


def main():
    path, L = sys.argv[1], int(sys.argv[2])
    fh = open(path, 'rb')
    m = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    he = m.find(b'\0') + 1
    I = struct.unpack_from('>I', m, he)[0]
    TSIZE[2] = I
    fmt = '>Q' if I == 8 else '>I'
    rid = lambda p: struct.unpack_from(fmt, m, p)[0]
    strings, cname, objclass = {}, {}, {}
    targets = set()
    inst = []   # (objid, classid, start, len)
    oarr = []   # (objid, start, count)
    pos = he + 12
    n = len(m)
    while pos < n:
        tag = m[pos]; length = struct.unpack_from('>I', m, pos + 5)[0]; b = pos + 9; end = b + length
        if tag == 0x01:
            strings[rid(b)] = m[b + I:end].decode(errors='replace')
        elif tag == 0x02:
            cname[rid(b + 4)] = rid(b + 8 + I)
        elif tag in (0x0C, 0x1C):
            p = b
            while p < end:
                st = m[p]; p += 1
                if st == 0xFF: p += I
                elif st == 0x01: p += 2 * I
                elif st in (0x02, 0x03, 0x08): p += I + 8
                elif st in (0x04, 0x06): p += I + 4
                elif st in (0x05, 0x07): p += I
                elif st == 0x20:
                    p += I + 4 + 6 * I + 4
                    cp = struct.unpack_from('>H', m, p)[0]; p += 2
                    for _ in range(cp):
                        t = m[p + 2]; p += 3 + TSIZE[t]
                    ns = struct.unpack_from('>H', m, p)[0]; p += 2
                    for _ in range(ns):
                        t = m[p + I]; p += I + 1 + TSIZE[t]
                    ni = struct.unpack_from('>H', m, p)[0]; p += 2 + ni * (I + 1)
                elif st == 0x21:
                    oid = rid(p); cid = rid(p + I + 4); ln = struct.unpack_from('>I', m, p + 2 * I + 4)[0]
                    s = p + 2 * I + 8
                    inst.append((oid, cid, s, ln)); objclass[oid] = cid
                    p = s + ln
                elif st == 0x22:
                    oid = rid(p); cnt = struct.unpack_from('>I', m, p + I + 4)[0]; s = p + I + 8 + I
                    oarr.append((oid, s, cnt)); objclass[oid] = rid(p + I + 8)
                    p = s + cnt * I
                elif st == 0x23:
                    oid = rid(p); cnt = struct.unpack_from('>I', m, p + I + 4)[0]; t = m[p + I + 8]
                    if t == 8 and cnt == L:
                        targets.add(oid)
                    p += I + 9 + cnt * TSIZE[t]
                else:
                    raise SystemExit(f'unknown 0x{st:02x}')
        pos = end
    name = lambda cid: strings.get(cname.get(cid), f'?{cid:x}')
    tb = {struct.pack(fmt, t): t for t in targets}

    def holders(ids):
        res = defaultdict(list)
        bs = {struct.pack(fmt, t): t for t in ids}
        for oid, cid, s, ln in inst:
            blob = m[s:s + ln]
            for kb, t in bs.items():
                i = blob.find(kb)
                while i >= 0:
                    if True:  # field data is not aligned
                        res[t].append((oid, name(cid)))
                    i = blob.find(kb, i + 1)
        for oid, s, cnt in oarr:
            blob = m[s:s + cnt * I]
            for kb, t in bs.items():
                i = blob.find(kb)
                while i >= 0:
                    if i % I == 0:
                        res[t].append((oid, 'Object[]'))
                    i = blob.find(kb, i + 1)
        return res

    r1 = holders(targets)
    print(f'{len(targets)} byte[{L}] arrays; idsize={I}; instances={len(inst)}; objarrays={len(oarr)}')
    for t in sorted(targets):
        hs = r1.get(t, [])
        line = f'  array {t:x}: held by ' + (', '.join(f'{c}@{o:x}' for o, c in hs) or 'NOTHING (unreachable)')
        r2 = holders([o for o, _ in hs])
        for o, c in hs:
            line += f' | {c}@{o:x} held by ' + (', '.join(f'{cc}' for _, cc in r2.get(o, [])[:6]) or 'nothing')
        print(line)


if __name__ == '__main__':
    main()
