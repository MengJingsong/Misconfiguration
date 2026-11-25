#!/usr/bin/env python3
"""B28 owners.py <dump.hprof> [min_bytes=1048576] (stage 2, 2026-11-24; adapted from R12's owners.py).

Walks BACKWARDS from every primitive array >= min bytes (breadth-first over referrers, up to 16 levels) and assigns it to
the NEAREST identifying owner (case file section 2.6, "Holder at failure"):
  Q  TRACING queue: a java.util.concurrent.LinkedBlockingQueue$Node (the TracingStage executor's queue; the queue object
     is checked: its owner executor name is reported)
  T  running trace task / write path: a frame of a TracingStage or MutationStage thread, or an instance of
     org.apache.cassandra.db.commitlog.* / org.apache.cassandra.hints.*
  M  memtable: an instance of org.apache.cassandra.db.memtable.* / db.partitions.AtomicBTreePartition / utils.memory.*
  P  pending in an open trace session: org.apache.cassandra.tracing.* instance (TraceStateImpl.pendingFutures) without Q;
     the task lambdas (TraceStateImpl$$Lambda) are not owners: the walk continues to their FutureTask's referrers
  D  decode buffer: java.nio.HeapCharBuffer (CBUtil TL_CHAR_BUFFER) or a FastThreadLocal map of an event-loop thread
  F  in-flight request: a frame of a Native-Transport-Requests or Netty event-loop thread, or an
     org.apache.cassandra.transport.* / io.netty.* instance
  O  any other root
Ties at the same level are broken in the order Q, T, M, P, D, F, O. Arrays not reachable from any GC root are
'unreachable'. Shares are of the dump's shallow total. Also prints the length histogram of the big arrays per owner."""
import mmap, struct, sys, re
from collections import defaultdict, Counter, deque
PS = {4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}
PN = {4: 'boolean[]', 5: 'char[]', 6: 'float[]', 7: 'double[]', 8: 'byte[]', 9: 'short[]', 10: 'int[]', 11: 'long[]'}
A8 = lambda n: (n + 7) & ~7
MIN = int(sys.argv[2]) if len(sys.argv) > 2 else 1 << 20
f = open(sys.argv[1], 'rb'); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
he = mm.find(b'\0')
u4 = lambda o: struct.unpack_from('>I', mm, o)[0]; uid = lambda o: struct.unpack_from('>Q', mm, o)[0]; u2 = lambda o: struct.unpack_from('>H', mm, o)[0]
strings = {}; cname_id = {}; cls_serial = {}; classes = {}; frames = {}; traces = {}
objcls = {}; big = {}; total = 0; parents = defaultdict(list); children = {}
rootthr = defaultdict(set); otherroot = set(); thread_obj = {}; static_of = defaultdict(set)
RSK = {0xFF: 0, 0x01: 8, 0x02: 8, 0x03: 8, 0x04: 4, 0x05: 0, 0x06: 4, 0x07: 0, 0x08: 8, 0x89: 0, 0x8a: 0, 0x8b: 0, 0x8c: 4, 0x8d: 0, 0x8e: 8, 0x90: 0}
pending_inst = []


def seg(p, end):
    global total
    while p < end:
        t = mm[p]; p += 1
        if t == 0x21:
            oid = uid(p); cid = uid(p + 12); nb = u4(p + 20); objcls[oid] = cid; pending_inst.append((oid, cid, p + 24)); total += A8(12 + nb); p += 24 + nb
        elif t == 0x22:
            oid = uid(p); n = u4(p + 12); objcls[oid] = uid(p + 16); total += A8(16 + 4 * n); base = p + 24
            ch = []
            for i in range(n):
                r = uid(base + 8 * i)
                if r: parents[r].append(oid); ch.append(r)
            children[oid] = ch
            p += 24 + 8 * n
        elif t == 0x23:
            oid = uid(p); n = u4(p + 12); et = mm[p + 16]; sz = A8(16 + PS[et] * n); total += sz
            if sz >= MIN: big[oid] = (PN[et], n, sz)
            p += 17 + PS[et] * n
        elif t == 0x20:
            cid = uid(p); sup = uid(p + 12); q = p + 8 + 4 + 48 + 4
            ncp = u2(q); q += 2
            for _ in range(ncp):
                ty = mm[q + 2]; q += 3 + (8 if ty == 2 else PS[ty])
            nst = u2(q); q += 2
            for _ in range(nst):
                ty = mm[q + 8]
                if ty == 2:
                    r = uid(q + 9)
                    if r: static_of[r].add(cid)
                q += 9 + (8 if ty == 2 else PS[ty])
            nf = u2(q); q += 2; fl = []
            for _ in range(nf): fl.append((uid(q), mm[q + 8])); q += 9
            classes[cid] = (sup, fl); p = q
        elif t in (0x02, 0x03, 0x04, 0x06):
            rootthr[uid(p)].add(u4(p + 8)); p += 8 + RSK[t]
        elif t == 0x08:
            thread_obj[u4(p + 8)] = uid(p); otherroot.add(uid(p)); p += 16
        elif t in RSK:
            otherroot.add(uid(p)); p += 8 + RSK[t]
        else: raise ValueError(hex(t))


pos = he + 13
while pos < len(mm):
    tag = mm[pos]; ln = u4(pos + 5); b = pos + 9
    if tag == 0x01: strings[uid(b)] = mm[b + 8:b + ln].decode('utf-8', 'replace')
    elif tag == 0x02: cname_id[uid(b + 4)] = uid(b + 16); cls_serial[u4(b)] = uid(b + 16)
    elif tag == 0x04: frames[uid(b)] = (uid(b + 8), u4(b + 32))
    elif tag == 0x05:
        n = u4(b + 8); traces[u4(b)] = (u4(b + 4), [uid(b + 12 + 8 * i) for i in range(n)])
    elif tag in (0x0C, 0x1C): seg(b, b + ln)
    pos = b + ln
cn = lambda cid: strings.get(cname_id.get(cid), '?').replace('/', '.')
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


for oid, cid, base in pending_inst:
    ch = []
    for o, fn in layout(cid):
        r = uid(base + o)
        if r: parents[r].append(oid); ch.append(r)
    children[oid] = ch
del pending_inst
live = set(); dq = deque()
for r in list(rootthr) + list(otherroot) + list(static_of):
    if r not in live: live.add(r); dq.append(r)
while dq:
    o = dq.popleft()
    for r in children.get(o, ()):
        if r not in live: live.add(r); dq.append(r)
del children

# thread names (Thread.name -> String.value byte[])
tname = {}
want = {tid: ser for ser, tid in thread_obj.items()}
off = {}


def seg2(p, end):
    while p < end:
        t = mm[p]; p += 1
        if t == 0x21:
            oid = uid(p); nb = u4(p + 20)
            if oid in want or oid in need_s or oid in need_b: off[oid] = p - 1
            p += 24 + nb
        elif t == 0x22: p += 24 + 8 * u4(p + 12)
        elif t == 0x23:
            oid = uid(p); n = u4(p + 12); et = mm[p + 16]
            if oid in need_b: off[oid] = p - 1
            p += 17 + PS[et] * n
        elif t == 0x20:
            q = p + 8 + 4 + 48 + 4; ncp = u2(q); q += 2
            for _ in range(ncp):
                ty = mm[q + 2]; q += 3 + (8 if ty == 2 else PS[ty])
            nst = u2(q); q += 2
            for _ in range(nst):
                ty = mm[q + 8]; q += 9 + (8 if ty == 2 else PS[ty])
            nf = u2(q); q += 2 + 9 * nf; p = q
        elif t in RSK: p += 8 + RSK[t]


def fieldref(oid, name):
    p = off.get(oid)
    if p is None: return None
    for o, fn in layout(uid(p + 13)):
        if fn == name: return uid(p + 25 + o)


def scan():
    pos = he + 13
    while pos < len(mm):
        tag = mm[pos]; ln = u4(pos + 5); b = pos + 9
        if tag in (0x0C, 0x1C): seg2(b, b + ln)
        pos = b + ln


need_s = set(); need_b = set(); scan()
s_of = {tid: fieldref(tid, 'name') for tid in want}
need_s = set(v for v in s_of.values() if v); scan()
b_of = {s: fieldref(s, 'value') for s in need_s}
need_b = set(v for v in b_of.values() if v); scan()
for tid, ser in want.items():
    bo = b_of.get(s_of.get(tid)); p = off.get(bo)
    if p is not None and mm[p] == 0x23:
        n = u4(p + 13); et = mm[p + 17]; tname[ser] = mm[p + 18:p + 18 + n * PS[et]].decode('latin-1' if et == 8 else 'utf-16-be', 'replace')
netty = lambda n: 'EventLoop' in n or n.startswith('epoll') or n.startswith('nio') or n.startswith('Native-Transport-Requests') is False and 'netty' in n.lower()


def cls_tag(oid):
    c = cn(objcls.get(oid, 0))
    if c == 'java.util.concurrent.LinkedBlockingQueue$Node': return 'Q'
    if c.startswith('org.apache.cassandra.db.commitlog.') or c.startswith('org.apache.cassandra.hints.'): return 'T'
    if (c.startswith('org.apache.cassandra.db.memtable.') or c == 'org.apache.cassandra.db.partitions.AtomicBTreePartition'
            or c.startswith('org.apache.cassandra.utils.memory.')): return 'M'
    if c.startswith('org.apache.cassandra.tracing.') and '$$Lambda' not in c: return 'P'   # the task lambda is not an owner
    if c == 'java.nio.HeapCharBuffer' or c == 'io.netty.util.internal.InternalThreadLocalMap': return 'D'
    if c.startswith('org.apache.cassandra.transport.') or c.startswith('io.netty.'): return 'F'
    return None


def thr_tag(ser):
    nm = tname.get(ser, '?')
    if nm.startswith('TracingStage') or nm.startswith('MutationStage'): return 'T'
    if nm.startswith('Native-Transport-Requests') or netty(nm): return 'F'
    return 'O'


PRI = {k: i for i, k in enumerate('QTMPDFO')}
owner = {}; how = {}
for oid, (ty, n, sz) in big.items():
    front = [oid]; seen = {oid}; found = None
    for lv in range(16):
        cand = []
        for o in front:
            if o != oid:
                t = cls_tag(o)
                if t: cand.append((t, cn(objcls.get(o, 0))))
            for ser in rootthr.get(o, ()):
                cand.append((thr_tag(ser), 'frame:' + re.sub(r'[-:]?\d+$', '', tname.get(ser, '?'))))
        if cand:
            found = min(cand, key=lambda x: PRI[x[0]]); break
        nxt = []
        for o in front:
            for pp in parents.get(o, ()):
                if pp not in seen and pp in live: seen.add(pp); nxt.append(pp)
            if o in otherroot or o in static_of: cand.append(('O', 'root/static'))
        if cand and not nxt:
            found = ('O', 'root/static'); break
        front = nxt
        if not front: break
    if found is None:
        found = ('O', 'other') if seen & (otherroot | set(static_of)) else ('unreached', '-')
    owner[oid] = found[0]; how[oid] = found[1]
# which executor owns the LinkedBlockingQueue nodes: count LBQ objects reached from Q-owned arrays (head-of-queue name)
catb = Counter(); catn = Counter(); det = defaultdict(Counter)
for oid, (ty, n, sz) in big.items():
    k = owner[oid]
    if oid not in live: k = 'unreachable'
    catb[k] += sz; catn[k] += 1
    lb = n if not (15_999_900 <= n <= 16_000_600) else '16.0M'
    if ty == 'char[]' and 15_999_900 <= n <= 16_000_600: lb = '16.0M chars'
    det[k][(ty, lb, how[oid])] += sz
names = {'Q': 'TRACING queue', 'T': 'running trace task / write path', 'M': 'memtable', 'P': 'open trace session',
         'D': 'decode buffer', 'F': 'in-flight request', 'O': 'other root', 'unreached': 'unreached', 'unreachable': 'unreachable'}
print('dump %s: all objects %.1f MiB shallow; arrays >= %d B: %d, %.1f MiB' % (sys.argv[1], total / 2**20, MIN, len(big), sum(v[2] for v in big.values()) / 2**20))
print('nearest-owner shares of the dump total:')
for k in ['Q', 'T', 'M', 'P', 'D', 'F', 'O', 'unreached', 'unreachable']:
    print('  %-12s %-32s %5d arrays %9.1f MiB  %5.1f%%' % (k, names[k], catn[k], catb[k] / 2**20, 100 * catb[k] / total))
for k in ['Q', 'T', 'M', 'P', 'D', 'F', 'O', 'unreached', 'unreachable']:
    if det[k]:
        print('[%s] ' % k + '; '.join('%s %s via %s: %.0f MiB' % (a, b, c, v / 2**20) for (a, b, c), v in det[k].most_common(8)))
# LBQ owner check: from each Q array go up to its LinkedBlockingQueue$Node, then along Node.next referrers to the queue
NODE = 'java.util.concurrent.LinkedBlockingQueue$Node'; LBQ = 'java.util.concurrent.LinkedBlockingQueue'
memo = {}


def queue_of(node):
    path = []; o = node
    for _ in range(5000):
        if o in memo: r = memo[o]; break
        path.append(o)
        ps = parents.get(o, ())
        q = [p for p in ps if cn(objcls.get(p, 0)) == LBQ]
        if q: r = q[0]; break
        nx = [p for p in ps if cn(objcls.get(p, 0)) == NODE and p not in path]
        if not nx: r = None; break
        o = nx[0]
    else:
        r = None
    for x in path: memo[x] = r
    return r


lbq = Counter()
for oid in big:
    if owner[oid] != 'Q': continue
    front = [oid]; seen = {oid}; node = None
    for lv in range(16):
        nxt = []
        for o in front:
            if cn(objcls.get(o, 0)) == NODE: node = o; break
            for pp in parents.get(o, ()):
                if pp not in seen: seen.add(pp); nxt.append(pp)
        if node or not nxt: break
        front = nxt
    lbq[queue_of(node) if node else None] += 1
for q, c in lbq.most_common(5):
    refs = Counter(cn(objcls.get(p, 0)) for p in parents.get(q, ()))
    refs2 = Counter()
    for p in parents.get(q, ()):
        for p2 in parents.get(p, ()): refs2[cn(objcls.get(p2, 0))] += 1
    print('Q arrays %d reach LinkedBlockingQueue %s; its referrers %s; next %s' % (c, ('%x' % q) if q else None, dict(refs), dict(refs2.most_common(4))))
