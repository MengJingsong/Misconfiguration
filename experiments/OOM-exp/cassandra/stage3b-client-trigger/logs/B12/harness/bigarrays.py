#!/usr/bin/env python3
"""bigarrays.py (B12 copy of B11's; tail reports byte[min_bytes] exactly) <dump.hprof> [min_bytes=1048576]: primitive arrays >= min bytes by (type, length): count, bytes,
how many are reachable from GC roots, and how many are referenced directly by a ROOT_JAVA_FRAME root of a
Native-Transport-Requests thread; plus heap total. Shallow sizes as hprof_histo.py (16-byte array header)."""
import mmap, struct, sys
from collections import defaultdict, deque
PS = {4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}
PN = {4: 'boolean[]', 5: 'char[]', 6: 'float[]', 7: 'double[]', 8: 'byte[]', 9: 'short[]', 10: 'int[]', 11: 'long[]'}
A8 = lambda n: (n + 7) & ~7
MIN = int(sys.argv[2]) if len(sys.argv) > 2 else 1 << 20
f = open(sys.argv[1], 'rb'); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
he = mm.find(b'\0'); assert struct.unpack_from('>I', mm, he + 1)[0] == 8
pos = he + 13
u4 = lambda o: struct.unpack_from('>I', mm, o)[0]; uid = lambda o: struct.unpack_from('>Q', mm, o)[0]; u2 = lambda o: struct.unpack_from('>H', mm, o)[0]
strings = {}; cname_id = {}; classes = {}; static_refs = []; roots = []; frame_roots = []  # (obj, thread serial)
thread_obj = {}  # thread serial -> thread object id
obj_off = {}; big = {}; total = 0
RSK = {0xFF: 0, 0x01: 8, 0x02: 8, 0x03: 8, 0x04: 4, 0x05: 0, 0x06: 4, 0x07: 0, 0x08: 8, 0x89: 0, 0x8a: 0, 0x8b: 0, 0x8c: 4, 0x8d: 0, 0x8e: 8, 0x90: 0}
inst_nb = {}
def seg(p, end):
    global total
    while p < end:
        t = mm[p]; p += 1
        if t == 0x21:
            oid = uid(p); cid = uid(p + 12); nb = u4(p + 20); obj_off[oid] = p - 1; inst_nb[cid] = nb; total += A8(12 + nb); p += 24 + nb
        elif t == 0x22:
            oid = uid(p); n = u4(p + 12); obj_off[oid] = p - 1; total += A8(16 + 4 * n); p += 24 + 8 * n
        elif t == 0x23:
            oid = uid(p); n = u4(p + 12); et = mm[p + 16]; sz = A8(16 + PS[et] * n); total += sz
            if sz >= MIN: big[oid] = (PN[et], n, sz)
            p += 17 + PS[et] * n
        elif t == 0x20:
            cid = uid(p); sup = uid(p + 12); q = p + 8 + 4 + 48; q += 4
            ncp = u2(q); q += 2
            for _ in range(ncp):
                ty = mm[q + 2]; q += 3 + (8 if ty == 2 else PS[ty])
            nst = u2(q); q += 2
            for _ in range(nst):
                ty = mm[q + 8]
                if ty == 2:
                    r = uid(q + 9)
                    if r: static_refs.append(r)
                q += 9 + (8 if ty == 2 else PS[ty])
            nf = u2(q); q += 2; fl = []
            for _ in range(nf): fl.append(mm[q + 8]); q += 9
            classes[cid] = (sup, fl); p = q
        elif t == 0x03:   # ROOT_JAVA_FRAME: id, thread serial u4, frame u4
            roots.append(uid(p)); frame_roots.append((uid(p), u4(p + 8))); p += 16
        elif t == 0x08:   # ROOT_THREAD_OBJECT: id, thread serial, stack serial
            roots.append(uid(p)); thread_obj[u4(p + 8)] = uid(p); p += 16
        elif t in RSK:
            roots.append(uid(p)); p += 8 + RSK[t]
        else: raise ValueError(hex(t))
while pos < len(mm):
    tag = mm[pos]; ln = u4(pos + 5); b = pos + 9
    if tag == 0x01: strings[uid(b)] = mm[b + 8:b + ln].decode('utf-8', 'replace')
    elif tag == 0x02: cname_id[uid(b + 4)] = uid(b + 16)
    elif tag in (0x0C, 0x1C): seg(b, b + ln)
    pos = b + ln
lay = {}
def layout(cid):
    if cid in lay: return lay[cid]
    offs = []; o = 0; c = cid
    while c and c in classes:
        for ty in classes[c][1]:
            if ty == 2: offs.append(o); o += 8
            else: o += PS[ty]
        c = classes[c][0]
    lay[cid] = offs; return offs
def refs(oid):
    p = obj_off.get(oid)
    if p is None: return
    t = mm[p]
    if t == 0x21:
        cid = uid(p + 13); base = p + 25
        for o in layout(cid):
            r = uid(base + o)
            if r: yield r
    elif t == 0x22:
        n = u4(p + 13); base = p + 25
        for i in range(n):
            r = uid(base + 8 * i)
            if r: yield r
live = set(); dq = deque()
for r in roots + static_refs + list(classes):
    if r not in live: live.add(r); dq.append(r)
while dq:
    o = dq.popleft()
    for r in refs(o):
        if r not in live: live.add(r); dq.append(r)
# rebuild class field-name tables (second light pass over class dumps)
cf = {}
def seg2(p, end):
    while p < end:
        t = mm[p]; p += 1
        if t == 0x21: p += 24 + u4(p + 20)
        elif t == 0x22: p += 24 + 8 * u4(p + 12)
        elif t == 0x23: p += 17 + PS[mm[p + 16]] * u4(p + 12)
        elif t == 0x20:
            cid = uid(p); q = p + 8 + 4 + 48 + 4
            ncp = u2(q); q += 2
            for _ in range(ncp):
                ty = mm[q + 2]; q += 3 + (8 if ty == 2 else PS[ty])
            nst = u2(q); q += 2
            for _ in range(nst):
                ty = mm[q + 8]; q += 9 + (8 if ty == 2 else PS[ty])
            nf = u2(q); q += 2; fl = []
            for _ in range(nf): fl.append((strings.get(uid(q), '?'), mm[q + 8])); q += 9
            cf[cid] = fl; p = q
        elif t == 0x03 or t == 0x08: p += 16
        elif t in RSK: p += 8 + RSK[t]
pos = he + 13
while pos < len(mm):
    tag = mm[pos]; ln = u4(pos + 5); b = pos + 9
    if tag in (0x0C, 0x1C): seg2(b, b + ln)
    pos = b + ln
def getf(oid, name):
    p = obj_off.get(oid)
    if p is None or mm[p] != 0x21: return None
    cid = uid(p + 13); base = p + 25; o = 0; c = cid
    while c and c in classes:
        for (n, ty) in cf.get(c, []):
            if n == name and ty == 2: return uid(base + o)
            o += 8 if ty == 2 else PS[ty]
        c = classes[c][0]
    return None
small = {}
def seg3(p, end):
    while p < end:
        t = mm[p]; p += 1
        if t == 0x21: p += 24 + u4(p + 20)
        elif t == 0x22: p += 24 + 8 * u4(p + 12)
        elif t == 0x23:
            oid = uid(p); n = u4(p + 12); et = mm[p + 16]
            if et == 8 and n < 200 and oid in want: small[oid] = mm[p + 17:p + 17 + n].decode('latin-1')
            p += 17 + PS[et] * n
        elif t == 0x20:
            q = p + 8 + 4 + 48 + 4; ncp = u2(q); q += 2
            for _ in range(ncp):
                ty = mm[q + 2]; q += 3 + (8 if ty == 2 else PS[ty])
            nst = u2(q); q += 2
            for _ in range(nst):
                ty = mm[q + 8]; q += 9 + (8 if ty == 2 else PS[ty])
            nf = u2(q); q += 2 + 9 * nf; p = q
        elif t == 0x03 or t == 0x08: p += 16
        elif t in RSK: p += 8 + RSK[t]
want = set()
tname_sid = {}
for ser, tid in thread_obj.items():
    s = getf(tid, 'name')
    if s:
        v = getf(s, 'value')
        if v: want.add(v); tname_sid[ser] = v
pos = he + 13
while pos < len(mm):
    tag = mm[pos]; ln = u4(pos + 5); b = pos + 9
    if tag in (0x0C, 0x1C): seg3(b, b + ln)
    pos = b + ln
tname = {ser: small.get(v, '?') for ser, v in tname_sid.items()}
ntr_frame = defaultdict(set)
for oid, ser in frame_roots:
    if oid in big and tname.get(ser, '').startswith('Native-Transport-Requests'):
        ntr_frame[oid].add(ser)
agg = defaultdict(lambda: [0, 0, 0, 0])
for oid, (ty, n, sz) in big.items():
    a = agg[(ty, n)]; a[0] += 1; a[1] += sz; a[2] += oid in live; a[3] += oid in ntr_frame
print('dump %s: all objects %.1f MiB shallow; arrays >= %d B: %d, %.1f MiB' % (sys.argv[1], total / 2**20, MIN, len(big), sum(v[2] for v in big.values()) / 2**20))
print('%-10s %12s %6s %10s %6s %10s' % ('type', 'length', 'count', 'MiB', 'live', 'NTRframe'))
for (ty, n), a in sorted(agg.items(), key=lambda x: -x[1][1])[:25]:
    print('%-10s %12d %6d %10.1f %6d %10d' % (ty, n, a[0], a[1] / 2**20, a[2], a[3]))
exact = [(ty, n, a) for (ty, n), a in agg.items() if ty == 'byte[]' and n == MIN]
for ty, n, a in exact:
    print('byte[%d] exactly: count %d, %.1f MiB = %.1f%% of dump, live (reachable) %d' % (n, a[0], a[1] / 2**20, 100 * a[1] / total, a[2]))
