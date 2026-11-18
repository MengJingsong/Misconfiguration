#!/usr/bin/env python3
"""retainers.py <dump> <type: byte|char> <length> [levels]: referrer chains (class names) for primitive arrays of that length."""
import mmap, struct, sys
from collections import defaultdict, Counter
PS = {4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}
ET = {'byte': 8, 'char': 5}
f = open(sys.argv[1], 'rb'); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
WANT_ET = ET[sys.argv[2]]; WANT_N = int(sys.argv[3]); LV = int(sys.argv[4]) if len(sys.argv) > 4 else 8
he = mm.find(b'\0'); pos = he + 13
u4 = lambda o: struct.unpack_from('>I', mm, o)[0]; uid = lambda o: struct.unpack_from('>Q', mm, o)[0]; u2 = lambda o: struct.unpack_from('>H', mm, o)[0]
strings = {}; cname_id = {}; classes = {}; insts = []; oarrs = []; targets = set(); rootkind = {}
RSK = {0xFF: 0, 0x01: 8, 0x02: 8, 0x03: 8, 0x04: 4, 0x05: 0, 0x06: 4, 0x07: 0, 0x08: 8, 0x89: 0, 0x8a: 0, 0x8b: 0, 0x8c: 4, 0x8d: 0, 0x8e: 8, 0x90: 0}
objcls = {}
def seg(p, end):
    while p < end:
        t = mm[p]; p += 1
        if t == 0x21:
            oid = uid(p); cid = uid(p + 12); nb = u4(p + 20); insts.append((oid, cid, p + 24)); objcls[oid] = cid; p += 24 + nb
        elif t == 0x22:
            oid = uid(p); n = u4(p + 12); acid = uid(p + 16); oarrs.append((oid, n, p + 24)); objcls[oid] = acid; p += 24 + 8 * n
        elif t == 0x23:
            oid = uid(p); n = u4(p + 12); et = mm[p + 16]
            if et == WANT_ET and n == WANT_N: targets.add(oid)
            p += 17 + PS[et] * n
        elif t == 0x20:
            cid = uid(p); sup = uid(p + 12); q = p + 8 + 4 + 48 + 4
            ncp = u2(q); q += 2
            for _ in range(ncp):
                ty = mm[q + 2]; q += 3 + (8 if ty == 2 else PS[ty])
            nst = u2(q); q += 2
            for _ in range(nst):
                ty = mm[q + 8]; q += 9 + (8 if ty == 2 else PS[ty])
            nf = u2(q); q += 2; fl = []
            for _ in range(nf): fl.append((uid(q), mm[q + 8])); q += 9
            classes[cid] = (sup, fl); p = q
        elif t in RSK:
            rootkind.setdefault(uid(p), hex(t)); p += 8 + RSK[t]
        else: raise ValueError(hex(t))
while pos < len(mm):
    tag = mm[pos]; ln = u4(pos + 5); b = pos + 9
    if tag == 0x01: strings[uid(b)] = mm[b + 8:b + ln].decode('utf-8', 'replace')
    elif tag == 0x02: cname_id[uid(b + 4)] = uid(b + 16)
    elif tag in (0x0C, 0x1C): seg(b, b + ln)
    pos = b + ln
def cn(cid): return strings.get(cname_id.get(cid), '?').replace('/', '.')
lay = {}
def layout(cid):
    if cid in lay: return lay[cid]
    offs = []; o = 0; c = cid
    while c and c in classes:
        for (nid, ty) in classes[c][1]:
            if ty == 2: offs.append((o, strings.get(nid, '?'))); o += 8
            else: o += PS[ty]
        c = classes[c][0]
    lay[cid] = offs; return offs
# reverse edges for objects in frontier sets, level by level
frontier = set(targets); chains = {t: [] for t in targets}
print('targets', len(targets), 'roots among them', sum(t in rootkind for t in targets))
level_info = []
for lv in range(LV):
    parents = defaultdict(list)
    for oid, cid, base in insts:
        for o, fn in layout(cid):
            r = uid(base + o)
            if r in frontier: parents[r].append((oid, cn(cid) + '.' + fn))
    for oid, n, base in oarrs:
        # scan object arrays
        for i in range(n):
            r = uid(base + 8 * i)
            if r in frontier: parents[r].append((oid, cn(objcls[oid]) + '[]'))
    c = Counter(); nxt = set()
    for t in frontier:
        ps = parents.get(t, [])
        if not ps: c['(no referrer; root=%s)' % rootkind.get(t, '-')] += 1
        for oid, lab in ps[:3]:
            c[lab + (' [root %s]' % rootkind[oid] if oid in rootkind else '')] += 1; nxt.add(oid)
    print('level %d:' % (lv + 1)); [print('   %5d  %s' % (v, k)) for k, v in c.most_common(12)]
    frontier = nxt
    if not frontier: break
