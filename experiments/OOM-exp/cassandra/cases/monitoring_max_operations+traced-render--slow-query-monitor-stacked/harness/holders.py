#!/usr/bin/env python3
"""holders.py <dump.hprof> [min_bytes=1048576] — R12 (from B11's bigarrays.py + retainers.py).

Every primitive array >= min bytes is assigned to the FIRST root category that reaches it, in a multi-source BFS run
category by category in this order (design §2.6):
  M = static MonitoringTask.instance (its `reportingTask` field not followed) + frames of `ScheduledTasks*` threads
  R = frames of Native-Transport-Requests threads whose stack contains ExecuteMessage.traceQuery
  F = frames of the other NTR threads, and frames/thread objects of Netty event-loop threads (in-flight requests)
  L = logback: frames of `AsyncAppender-Worker*` threads and every ch.qos.logback.core.AsyncAppenderBase instance
  O = everything else (all other GC roots and class statics)
Traversal never enters java.lang.Thread, ThreadPoolExecutor, ClassLoader, DelayedWorkQueue or java.util.concurrent.FutureTask instances (other than a source itself), so a
category does not leak into the whole heap through executors or thread locals.
Prints shares of the dump's shallow total per category, the (type, length) breakdown per category, and monitor counts
(SlowOperation / FailedOperation instances, OperationsQueue sizes, name-length byte[] arrays)."""
import mmap, struct, sys
from collections import defaultdict, deque, Counter
PS = {4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}
PN = {4: 'boolean[]', 5: 'char[]', 6: 'float[]', 7: 'double[]', 8: 'byte[]', 9: 'short[]', 10: 'int[]', 11: 'long[]'}
A8 = lambda n: (n + 7) & ~7
MIN = int(sys.argv[2]) if len(sys.argv) > 2 else 1 << 20
f = open(sys.argv[1], 'rb'); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
he = mm.find(b'\0'); assert struct.unpack_from('>I', mm, he + 1)[0] == 8
u4 = lambda o: struct.unpack_from('>I', mm, o)[0]; uid = lambda o: struct.unpack_from('>Q', mm, o)[0]; u2 = lambda o: struct.unpack_from('>H', mm, o)[0]
strings = {}; cname_id = {}; classes = {}; statics = {}  # cid -> [(name, ref)]
other_roots = []; frame_roots = []; thread_obj = {}
obj_off = {}; objcls = {}; big = {}; total = 0
frames = {}; cls_serial = {}; traces = {}  # trace serial -> (thread serial, [frame ids])
RSK = {0xFF: 0, 0x01: 8, 0x02: 8, 0x03: 8, 0x04: 4, 0x05: 0, 0x06: 4, 0x07: 0, 0x08: 8, 0x89: 0, 0x8a: 0, 0x8b: 0, 0x8c: 4, 0x8d: 0, 0x8e: 8, 0x90: 0}
smallb = {}  # byte[] < 200 for thread names (filled in pass 2)


def seg(p, end):
    global total
    while p < end:
        t = mm[p]; p += 1
        if t == 0x21:
            oid = uid(p); cid = uid(p + 12); nb = u4(p + 20); obj_off[oid] = p - 1; objcls[oid] = cid; total += A8(12 + nb); p += 24 + nb
        elif t == 0x22:
            oid = uid(p); n = u4(p + 12); obj_off[oid] = p - 1; total += A8(16 + 4 * n); p += 24 + 8 * n
        elif t == 0x23:
            oid = uid(p); n = u4(p + 12); et = mm[p + 16]; sz = A8(16 + PS[et] * n); total += sz
            if sz >= MIN: big[oid] = (PN[et], n, sz)
            p += 17 + PS[et] * n
        elif t == 0x20:
            cid = uid(p); sup = uid(p + 12); q = p + 8 + 4 + 48 + 4
            ncp = u2(q); q += 2
            for _ in range(ncp):
                ty = mm[q + 2]; q += 3 + (8 if ty == 2 else PS[ty])
            nst = u2(q); q += 2; st = []
            for _ in range(nst):
                ty = mm[q + 8]
                if ty == 2:
                    r = uid(q + 9)
                    if r: st.append((uid(q), r))
                q += 9 + (8 if ty == 2 else PS[ty])
            nf = u2(q); q += 2; fl = []
            for _ in range(nf): fl.append((uid(q), mm[q + 8])); q += 9
            classes[cid] = (sup, fl); statics[cid] = st; p = q
        elif t == 0x03:
            frame_roots.append((uid(p), u4(p + 8))); p += 16
        elif t == 0x08:
            thread_obj[u4(p + 8)] = uid(p); p += 16
        elif t in (0x02, 0x04, 0x06):   # JNI local, native stack, thread block: also per thread
            frame_roots.append((uid(p), u4(p + 8))); p += 8 + RSK[t]
        elif t in RSK:
            other_roots.append(uid(p)); p += 8 + RSK[t]
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


def getf(oid, name):
    p = obj_off.get(oid)
    if p is None or mm[p] != 0x21: return None
    for o, fn in layout(uid(p + 13)):
        if fn == name: return uid(p + 25 + o)
    return None


def getint(oid, name):
    """int field value of an instance (JDK object field layout as dumped)."""
    p = obj_off.get(oid)
    if p is None: return None
    cid = uid(p + 13); base = p + 25; o = 0; c = cid
    while c and c in classes:
        for (nid, ty) in classes[c][1]:
            if strings.get(nid) == name and ty == 10: return struct.unpack_from('>i', mm, base + o)[0]
            o += 8 if ty == 2 else PS[ty]
        c = classes[c][0]
    return None


def is_sub(cid, names):
    c = cid
    while c and c in classes:
        if cn(c) in names: return True
        c = classes[c][0]
    return False


BLOCK_NAMES = {'java.lang.Thread', 'java.util.concurrent.ThreadPoolExecutor', 'java.lang.ClassLoader',
               'java.util.concurrent.ScheduledThreadPoolExecutor$DelayedWorkQueue', 'java.util.concurrent.FutureTask'}  # +2: 2026-11-20 11:20, an idle ScheduledTasks frame reached other tasks through its work queue
blockc = {}


def blocked(oid):
    c = objcls.get(oid)
    if c is None: return False
    if c not in blockc: blockc[c] = is_sub(c, BLOCK_NAMES)
    return blockc[c]


def refs(oid):
    p = obj_off.get(oid)
    if p is None: return
    t = mm[p]
    if t == 0x21:
        cid = uid(p + 13); base = p + 25; skiprt = cn(cid) == 'org.apache.cassandra.db.monitoring.MonitoringTask'
        for o, fn in layout(cid):
            if skiprt and fn == 'reportingTask': continue
            r = uid(base + o)
            if r: yield r
    elif t == 0x22:
        n = u4(p + 13); base = p + 25
        for i in range(n):
            r = uid(base + 8 * i)
            if r: yield r


# thread names (second pass for small byte[] of name strings)
want = {}
for ser, tid in thread_obj.items():
    s = getf(tid, 'name')
    if s:
        v = getf(s, 'value')
        if v: want[v] = ser


def seg2(p, end):
    while p < end:
        t = mm[p]; p += 1
        if t == 0x21: p += 24 + u4(p + 20)
        elif t == 0x22: p += 24 + 8 * u4(p + 12)
        elif t == 0x23:
            oid = uid(p); n = u4(p + 12); et = mm[p + 16]
            if oid in want: smallb[oid] = mm[p + 17:p + 17 + n * PS[et]].decode('latin-1' if et == 8 else 'utf-16-be', 'replace')
            p += 17 + PS[et] * n
        elif t == 0x20:
            q = p + 8 + 4 + 48 + 4; ncp = u2(q); q += 2
            for _ in range(ncp):
                ty = mm[q + 2]; q += 3 + (8 if ty == 2 else PS[ty])
            nst = u2(q); q += 2
            for _ in range(nst):
                ty = mm[q + 8]; q += 9 + (8 if ty == 2 else PS[ty])
            nf = u2(q); q += 2 + 9 * nf; p = q
        elif t in (0x03, 0x08): p += 16
        elif t in RSK: p += 8 + RSK[t]


pos = he + 13
while pos < len(mm):
    tag = mm[pos]; ln = u4(pos + 5); b = pos + 9
    if tag in (0x0C, 0x1C): seg2(b, b + ln)
    pos = b + ln
tname = {ser: smallb.get(v, '?') for v, ser in want.items()}
# thread serial -> methods on its stack
stack = defaultdict(set)
for tsr, (thr, fl) in traces.items():
    for fid in fl:
        m, cs = frames.get(fid, (0, 0))
        stack[thr].add(strings.get(cls_serial.get(cs, 0), '?').replace('/', '.') + '.' + strings.get(m, '?'))
traced = lambda ser: any(x.endswith('ExecuteMessage.traceQuery') for x in stack.get(ser, ()))
cats = {k: [] for k in 'MRFLO'}
mt_cid = [c for c in classes if cn(c) == 'org.apache.cassandra.db.monitoring.MonitoringTask']
for c in mt_cid:
    for nid, r in statics[c]:
        if strings.get(nid) == 'instance': cats['M'].append(r)
netty = lambda n: 'EventLoop' in n or 'eventLoop' in n or n.startswith('epoll') or n.startswith('nio')
for oid, ser in frame_roots:
    n = tname.get(ser, '?')
    if n.startswith('ScheduledTasks'): cats['M'].append(oid)
    elif n.startswith('Native-Transport-Requests'): cats['R' if traced(ser) else 'F'].append(oid)
    elif netty(n): cats['F'].append(oid)
    elif n.startswith('AsyncAppender-Worker'): cats['L'].append(oid)
    else: cats['O'].append(oid)
for ser, tid in thread_obj.items():
    n = tname.get(ser, '?')
    (cats['F'] if netty(n) else cats['O']).append(tid)
aa = [o for o, c in objcls.items() if is_sub(c, {'ch.qos.logback.core.AsyncAppenderBase'})]
cats['L'] += aa
cats['O'] += other_roots
for c, st in statics.items():
    if c in mt_cid: continue
    cats['O'] += [r for nid, r in st]
owner = {}
seen = set()
for k in 'MRFLO':
    dq = deque(); src = set(cats[k])
    for r in cats[k]:
        if r not in seen: seen.add(r); dq.append(r)
    while dq:
        o = dq.popleft()
        if o in big: owner[o] = k
        if o not in src and blocked(o): continue
        for r in refs(o):
            if r not in seen: seen.add(r); dq.append(r)
agg = defaultdict(lambda: defaultdict(lambda: [0, 0]))
catb = Counter()
for oid, (ty, n, sz) in big.items():
    k = owner.get(oid, 'unreachable')
    a = agg[k][(ty, n)]; a[0] += 1; a[1] += sz; catb[k] += sz
livebig = sum(v[2] for o, v in big.items() if o in owner)
print('dump %s: all objects %.1f MiB shallow; arrays >= %d B: %d, %.1f MiB' % (sys.argv[1], total / 2**20, MIN, len(big), sum(v[2] for v in big.values()) / 2**20))
print('category shares of the dump total (arrays >= min):')
for k in ['M', 'R', 'F', 'L', 'O', 'unreachable']:
    print('  H_%s %8.1f MiB  %5.1f%%' % (k, catb[k] / 2**20, 100 * catb[k] / total))
print('  H_M+H_R+H_F %5.1f%%   (reachable arrays >= min: %.1f MiB; H_M of them %.1f%%, H_R %.1f%%)' % (
    100 * (catb['M'] + catb['R'] + catb['F']) / total, livebig / 2**20, 100 * catb['M'] / max(livebig, 1), 100 * catb['R'] / max(livebig, 1)))
for k in ['M', 'R', 'F', 'L', 'O', 'unreachable']:
    if not agg[k]: continue
    print('[%s]' % k)
    for (ty, n), a in sorted(agg[k].items(), key=lambda x: -x[1][1])[:10]:
        print('   %-8s %12d x%-4d %9.1f MiB' % (ty, n, a[0], a[1] / 2**20))
# monitor counts
cnt = Counter(cn(c) for c in objcls.values() if 'monitoring.MonitoringTask$' in cn(c))
print('monitor instances:', dict(cnt))
for c in mt_cid:
    for nid, inst in statics[c]:
        if strings.get(nid) != 'instance': continue
        for fn in ('slowOperationsQueue', 'failedOperationsQueue'):
            q = getf(inst, fn); qq = getf(q, 'queue') if q else None
            ai = getf(qq, 'count') if qq else None
            print('  %s: maxOperations=%s queue count=%s' % (fn, getint(q, 'maxOperations') if q else None, getint(ai, 'value') if ai else None))
nm = Counter()
for oid, (ty, n, sz) in big.items():
    if ty == 'byte[]' and 32000003 <= n <= 32000400: nm[owner.get(oid, 'unreachable')] += 1
print('name-length byte[] (32,000,003..32,000,400) by category:', dict(nm))
print('NTR threads: %d (with traceQuery on stack: %d); ScheduledTasks threads: %d' % (
    sum(1 for s, n in tname.items() if n.startswith('Native-Transport-Requests')),
    sum(1 for s, n in tname.items() if n.startswith('Native-Transport-Requests') and traced(s)),
    sum(1 for n in tname.values() if n.startswith('ScheduledTasks'))))
# supplementary (not a category change): O arrays referenced directly by a thread's frame, by thread-name prefix and
# whether that thread's stack contains QueryCancelledException.<init> (read aborted at the deadline renders the command)
import re as _re
frt = defaultdict(set)
for oid, ser in frame_roots: frt[oid].add(ser)
sup = Counter()
for oid, (ty, n, sz) in big.items():
    if owner.get(oid) != 'O': continue
    sers = frt.get(oid)
    if not sers: sup['(no direct frame root)'] += sz; continue
    ser = sorted(sers)[0]; pre = _re.sub(r'[-:]?\d+$', '', tname.get(ser, '?'))
    qc = any(x.endswith('QueryCancelledException.<init>') for x in stack.get(ser, ()))
    sup[pre + (' [QueryCancelledException render]' if qc else '')] += sz
print('O detail:', ', '.join('%s %.1f MiB (%.1f%%)' % (k, v / 2**20, 100 * v / total) for k, v in sup.most_common()))
