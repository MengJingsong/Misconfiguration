#!/usr/bin/env python3
"""owners.py <dump.hprof> [min_bytes=1048576] -- U16 V5 analysis (from R12's, extended 2026-11-24, design §2.6).

Walks BACKWARDS from every live primitive array >= min bytes (breadth-first over referrers, up to 14 levels) and assigns it
to the NEAREST identifying owner:
  QR  a frame of a ReadStage thread whose stack contains QueryCancelledException.<init> (render transients, message under
      construction)
  QL  a QueryCancelledException instance; a ch.qos.logback.classic.spi.LoggingEvent / ThrowableProxy whose throwable is a
      QueryCancelledException; a frame of the AsyncAppender-Worker while it holds (as a frame root) such a LoggingEvent
  M   an org.apache.cassandra.db.monitoring.MonitoringTask$* instance, or a ScheduledTasks frame under MonitoringTask
  L   any other ch.qos.logback.* instance or AsyncAppender-Worker frame (e.g. queued monitor drain messages)
  F   org.apache.cassandra.transport.* / io.netty.* instances; frames of NTR, Netty event-loop and ReadStage threads not in
      the render (requests in flight)
  O   any other root
Ties at the same level: QR, QL, M, L, F, O. Shares are printed of the dump's shallow total and of the live >= min arrays
(the frozen V5 test: Q = QR + QL >= 40 % of the live >= 1 MiB array bytes and the largest of {Q, M, F, L, O}).
Also prints counts: live QueryCancelledException, LoggingEvents carrying one, MonitoringTask$FailedOperation/SlowOperation,
byte[16,000,000], arrays of 2S..2S+400 bytes (rendered hex messages / names)."""
import mmap, struct, sys, re
from collections import defaultdict, Counter
PS = {4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}
PN = {4: 'boolean[]', 5: 'char[]', 6: 'float[]', 7: 'double[]', 8: 'byte[]', 9: 'short[]', 10: 'int[]', 11: 'long[]'}
A8 = lambda n: (n + 7) & ~7
MIN = int(sys.argv[2]) if len(sys.argv) > 2 else 1 << 20
S = 16_000_000
f = open(sys.argv[1], 'rb'); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
he = mm.find(b'\0')
u4 = lambda o: struct.unpack_from('>I', mm, o)[0]; uid = lambda o: struct.unpack_from('>Q', mm, o)[0]; u2 = lambda o: struct.unpack_from('>H', mm, o)[0]
strings = {}; cname_id = {}; cls_serial = {}; classes = {}; frames = {}; traces = {}
objcls = {}; big = {}; total = 0; parents = defaultdict(list); children = {}
rootthr = defaultdict(set)   # obj -> thread serials (frame / JNI local / native stack / thread block)
otherroot = set(); thread_obj = {}; static_of = defaultdict(set)
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


LE = 'ch.qos.logback.classic.spi.LoggingEvent'; TP = 'ch.qos.logback.classic.spi.ThrowableProxy'
QCE = 'org.apache.cassandra.exceptions.QueryCancelledException'
le_tp = {}; tp_thr = {}
for oid, cid, base in pending_inst:
    ch = []
    nm = cn(cid)
    for o, fn in layout(cid):
        r = uid(base + o)
        if r: parents[r].append(oid); ch.append(r)
        if nm == LE and fn == 'throwableProxy': le_tp[oid] = r
        if nm == TP and fn == 'throwable': tp_thr[oid] = r
    children[oid] = ch
del pending_inst
tp_qce = set(t for t, r in tp_thr.items() if r and cn(objcls.get(r, 0)) == QCE)
le_qce = set(e for e, t in le_tp.items() if t in tp_qce)
from collections import deque
live = set(); dq = deque()
for r in list(rootthr) + list(otherroot) + list(static_of):
    if r not in live: live.add(r); dq.append(r)
while dq:
    o = dq.popleft()
    for r in children.get(o, ()):
        if r not in live: live.add(r); dq.append(r)
del children


def getf(oid, name):
    cid = objcls.get(oid)
    if cid is None: return None
    # locate instance data again by scanning is costly; thread names come from the String -> byte[] via parents instead
    return None


# thread names: Thread.name -> String -> value byte[]; find by walking parents of small byte[]s is costly, so read them
# from the stack-trace's thread serial -> thread object -> (we scan the instance once more for the 'name' field)
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
stack = defaultdict(set)
for tsr, (thr, fl) in traces.items():
    for fid in fl:
        m, cs = frames.get(fid, (0, 0))
        stack[thr].add(strings.get(cls_serial.get(cs, 0), '?').replace('/', '.') + '.' + strings.get(m, '?'))
has = lambda ser, suf: any(x.endswith(suf) for x in stack.get(ser, ()))
netty = lambda n: 'EventLoop' in n or n.startswith('epoll') or n.startswith('nio')


def cls_tag(oid):
    c = cn(objcls.get(oid, 0))
    if c.startswith('org.apache.cassandra.db.monitoring.MonitoringTask$'): return 'M'
    if c == QCE or oid in le_qce or oid in tp_qce: return 'QL'
    if c.startswith('ch.qos.logback.'): return 'L'
    if c.startswith('org.apache.cassandra.transport.') or c.startswith('io.netty.'): return 'F'
    return None


worker_qce = set()
for e in le_qce:
    for ser in rootthr.get(e, ()):
        if tname.get(ser, '').startswith('AsyncAppender-Worker'): worker_qce.add(ser)


def thr_tag(ser, ty, n):
    nm = tname.get(ser, '?')
    if nm.startswith('ScheduledTasks') and has(ser, 'MonitoringTask.logOperations'): return 'M'
    if has(ser, 'QueryCancelledException.<init>'): return 'QR'
    if nm.startswith('AsyncAppender-Worker'): return 'QL' if ser in worker_qce else 'L'
    if nm.startswith('Native-Transport-Requests') or nm.startswith('ReadStage') or netty(nm): return 'F'
    return 'O'


CATS = ['QR', 'QL', 'M', 'L', 'F', 'O']
PRI = {k: i for i, k in enumerate(CATS)}
owner = {}; how = {}
for oid, (ty, n, sz) in big.items():
    front = [oid]; seen = {oid}; found = None
    for lv in range(14):
        cand = []
        for o in front:
            if o != oid:
                t = cls_tag(o)
                if t: cand.append((t, cn(objcls.get(o, 0))))
            for ser in rootthr.get(o, ()):
                cand.append((thr_tag(ser, ty, n), 'frame:' + re.sub(r'[-:]?\d+$', '', tname.get(ser, '?'))))
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
# liveness: an array with no parents and no root is garbage (as holders.py "unreachable"); approximate with no referrers
catb = Counter(); det = defaultdict(Counter)
for oid, (ty, n, sz) in big.items():
    k = owner[oid]
    if oid not in live: k = 'unreachable'
    catb[k] += sz; det[k][(ty, n if n not in range(2 * S + 3, 2 * S + 401) else 'name~2S', how[oid])] += sz
livebig = sum(v[2] for o, v in big.items() if o in live)
print('dump %s: all objects %.1f MiB shallow; arrays >= %d B: %d, %.1f MiB (live %.1f MiB)' % (sys.argv[1], total / 2**20, MIN, len(big), sum(v[2] for v in big.values()) / 2**20, livebig / 2**20))
print('nearest-owner shares (of the dump total | of live arrays >= min):')
for k in CATS + ['unreached', 'unreachable']:
    print('  O_%-3s %8.1f MiB  %5.1f%% | %5.1f%%' % (k, catb[k] / 2**20, 100 * catb[k] / total, 100 * catb[k] / livebig if livebig else 0))
q = catb['QR'] + catb['QL']
others = {k: catb[k] for k in ['M', 'L', 'F', 'O']}
print('Q = QR + QL = %.1f MiB = %.1f%% of live arrays >= min; largest other %s %.1f MiB -> Q-attributed (frozen test): %s' % (
    q / 2**20, 100 * q / livebig if livebig else 0, max(others, key=others.get), max(others.values()) / 2**20,
    'YES' if livebig and q >= 0.4 * livebig and q > max(others.values()) else 'NO'))
for k in CATS + ['unreached', 'unreachable']:
    if det[k]:
        print('[%s] ' % k + '; '.join('%s %s via %s: %.0f MiB' % (a, b, c, v / 2**20) for (a, b, c), v in det[k].most_common(8)))
cnt = Counter(cn(objcls.get(o, 0)) for o in live if cn(objcls.get(o, 0)) in (QCE, LE, 'org.apache.cassandra.db.monitoring.MonitoringTask$FailedOperation', 'org.apache.cassandra.db.monitoring.MonitoringTask$SlowOperation'))
print('live counts:', dict(cnt), '; LoggingEvents carrying a QCE: %d (live %d); worker holds one: %s' % (len(le_qce), len(le_qce & live), bool(worker_qce)))
print('byte[16,000,000] live: %d; arrays of 2S..2S+400 B live: %d; 4S..4S+400 B live: %d' % (
    sum(1 for o, (ty, n, sz) in big.items() if o in live and ty == 'byte[]' and n == S),
    sum(1 for o, (ty, n, sz) in big.items() if o in live and 2 * S <= n * (2 if ty == 'char[]' else 1) <= 2 * S + 400),
    sum(1 for o, (ty, n, sz) in big.items() if o in live and 4 * S <= n * (2 if ty == 'char[]' else 1) <= 4 * S + 400)))
