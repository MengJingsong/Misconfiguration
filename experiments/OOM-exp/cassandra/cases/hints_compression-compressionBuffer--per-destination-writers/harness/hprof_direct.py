#!/usr/bin/env python3
# C1 run 4 (amendment 4): attribute live JVM direct memory in an HPROF dump to its holders.
#   hprof_direct.py <file.hprof> [maxHops=5]
# Pass 1: class layouts; every java.nio.DirectByteBuffer(R) instance: capacity, address, att, cleaner, fd.
#   Owners = allocateDirect buffers (cleaner != null, fd == null): they hold `capacity` native bytes
#   (counted against MaxDirectMemorySize). Mapped buffers (fd != null) are excluded and reported apart.
#   Slices/duplicates: att -> owner (JDK 11 keeps the root owner in att).
# Passes 2..: referrer search, hop by hop, from the buffers up the object graph (instance fields, object
#   array elements, static fields), stopping a chain at a "classifying" class.
# Attribution by address range per owner: bytes covered by live consumer slices are attributed to the
#   category of the consumer chain; slices whose only holders are BufferPool internals (Chunk slabs) are
#   containers, not consumers; owner bytes not covered by a consumer slice go to the owner's own category
#   (BufferPool chunk = pool retained/free).
import struct, sys, collections, re

F = sys.argv[1]; MAXHOPS = int(sys.argv[2]) if len(sys.argv) > 2 else 5
MiB = 1048576.0

def records(f):
    while True:
        h = f.read(9)
        if len(h) < 9: return
        tag, _, ln = struct.unpack('>BII', h)
        yield tag, f.read(ln)

def openf():
    f = open(F, 'rb', buffering=1 << 24)
    while f.read(1) != b'\0': pass
    idsz = struct.unpack('>I', f.read(4))[0]; f.read(8)
    return f, idsz

f, IDS = openf()
TS = {2: IDS, 4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}
rid = lambda b, j: int.from_bytes(b[j:j + IDS], 'big')

cstatic_long = {}; ALONG = {}
strings = {}; cname = {}; csuper = {}; cfields = {}; cstatic_refs = {}
# ---------- pass 1 ----------
dbb = {}          # id -> [classid, capacity, address, att, cleaner, fd]
inst_class = {}   # filled later only for referrers
def parse_classes_and_dbb():
    lay = {}
    for tag, b in records(f):
        if tag == 0x01:
            strings[rid(b, 0)] = b[IDS:].decode('utf-8', 'replace')
        elif tag == 0x02:
            cname[rid(b, 4)] = strings.get(rid(b, 8 + IDS), '?').replace('/', '.')
        elif tag in (0x0C, 0x1C):
            heap1(b, lay)
def heap1(b, lay):
    i = 0; n = len(b)
    while i < n:
        t = b[i]; i += 1
        if t == 0xFF: i += IDS
        elif t == 0x01: i += 2 * IDS
        elif t in (0x02, 0x03): i += IDS + 8
        elif t == 0x04: i += IDS + 4
        elif t in (0x05, 0x07): i += IDS
        elif t == 0x06: i += IDS + 4
        elif t == 0x08: i += IDS + 8
        elif t == 0x20:
            cid = rid(b, i); i += IDS + 4
            csuper[cid] = rid(b, i); i += 6 * IDS
            i += 4
            cp = struct.unpack('>H', b[i:i + 2])[0]; i += 2
            for _ in range(cp):
                i += 2; ty = b[i]; i += 1 + TS[ty]
            sf = struct.unpack('>H', b[i:i + 2])[0]; i += 2
            srefs = []
            for _ in range(sf):
                nm = rid(b, i); i += IDS; ty = b[i]; i += 1
                if ty == 2: srefs.append((strings.get(nm, '?'), rid(b, i)))
                elif ty == 11: cstatic_long.setdefault(cid, {})[strings.get(nm, '?')] = struct.unpack('>q', b[i:i + 8])[0]
                elif ty == 4: cstatic_long.setdefault(cid, {})[strings.get(nm, '?')] = b[i]
                i += TS[ty]
            cstatic_refs[cid] = srefs
            nf = struct.unpack('>H', b[i:i + 2])[0]; i += 2
            fl = []
            for _ in range(nf):
                fl.append((strings.get(rid(b, i), '?'), b[i + IDS])); i += IDS + 1
            cfields[cid] = fl
        elif t == 0x21:
            oid = rid(b, i); i += IDS + 4; cid = rid(b, i); i += IDS
            ln = struct.unpack('>I', b[i:i + 4])[0]; i += 4
            if cname.get(cid, '') == 'java.util.concurrent.atomic.AtomicLong':
                ALONG[oid] = decode(cid, b[i:i + ln]).get('value')
            if cid in DBBC:
                d = decode(cid, b[i:i + ln])
                dbb[oid] = [cid, d.get('capacity', 0), d.get('address', 0), d.get('att', 0), d.get('cleaner', 0), d.get('fd', 0)]
            i += ln
        elif t == 0x22:
            i += IDS + 4; ln = struct.unpack('>I', b[i:i + 4])[0]; i += 4 + IDS + ln * IDS
        elif t == 0x23:
            i += IDS + 4; ln = struct.unpack('>I', b[i:i + 4])[0]; i += 4; ty = b[i]; i += 1 + ln * TS[ty]
        else:
            raise SystemExit('bad subtag %#x' % t)

LAYOUT = {}
def layout(cid):
    if cid in LAYOUT: return LAYOUT[cid]
    out = []; off = 0; c = cid
    while c and c in cfields:
        for nm, ty in cfields[c]:
            out.append((nm, ty, off)); off += TS[ty]
        c = csuper.get(c, 0)
    LAYOUT[cid] = out; return out
def decode(cid, data):
    d = {}
    for nm, ty, off in layout(cid):
        if nm in d: continue
        if ty == 2: d[nm] = rid(data, off)
        elif ty == 10: d[nm] = struct.unpack('>i', data[off:off + 4])[0]
        elif ty == 11: d[nm] = struct.unpack('>q', data[off:off + 8])[0]
    return d

# need class names before instances: HPROF writes LOAD_CLASS before heap dump, so resolve DBB classes lazily
class LazySet:
    def __contains__(self, cid):
        n = cname.get(cid, '')
        return n in ('java.nio.DirectByteBuffer', 'java.nio.DirectByteBufferR')
DBBC = LazySet()
parse_classes_and_dbb()

owners = {o: v for o, v in dbb.items() if v[4] and not v[5]}
mapped = {o: v for o, v in dbb.items() if v[4] and v[5]}
slices = {o: v for o, v in dbb.items() if not v[4] and v[3] in owners}
other = {o: v for o, v in dbb.items() if o not in owners and o not in mapped and o not in slices}
tot = sum(v[1] for v in owners.values())
print('DirectByteBuffer instances: %d; owners (allocateDirect) %d = %.1f MiB; mapped %d = %.1f MiB; slices of owners %d; other %d'
      % (len(dbb), len(owners), tot / MiB, len(mapped), sum(v[1] for v in mapped.values()) / MiB, len(slices), len(other)))

# Netty's own direct-memory accounting (PlatformDependent): DIRECT_MEMORY_COUNTER (AtomicLong) / DIRECT_MEMORY_LIMIT
for cid, n in cname.items():
    if n == 'io.netty.util.internal.PlatformDependent':
        refs = dict(cstatic_refs.get(cid, [])); lv = cstatic_long.get(cid, {})
        ctr = refs.get('DIRECT_MEMORY_COUNTER', 0)
        print('Netty PlatformDependent: DIRECT_MEMORY_COUNTER=%s (%s), DIRECT_MEMORY_LIMIT=%s, USE_DIRECT_BUFFER_NO_CLEANER=%s, MAX_DIRECT_MEMORY=%s'
              % ((('%.1f MiB' % (ALONG[ctr] / MiB)) if ctr in ALONG and ALONG[ctr] is not None else 'null'),
                 'counter object present' if ctr else 'no counter (Netty uses JDK-accounted buffers)',
                 lv.get('DIRECT_MEMORY_LIMIT'), lv.get('USE_DIRECT_BUFFER_NO_CLEANER'), lv.get('MAX_DIRECT_MEMORY')))
nc = [v for o, v in other.items() if not v[5]]
print('DirectByteBuffers without cleaner and without a known owner (Netty no-cleaner / JNI / slices of those): %d, total capacity %.1f MiB (upper bound; slices may overlap)'
      % (len(nc), sum(v[1] for v in nc) / MiB))
# ---------- referrer passes ----------
STOP = re.compile(r'LargeMessage|ProcessLargeMessage|ProcessSmallMessage|InboundMessageHandler$|FrameDecoder|DataOutputBuffer|'
                  r'BufferPool\$Chunk|BufferPool\$MicroQueueOfChunks|BufferPool\$LocalPool|BufferPool\$GlobalPool|'
                  r'CommitLog|Memtable|SSTable|Compress|ChunkCache|Thread$|FastThreadLocal|Hints|Cleaner')
parents = collections.defaultdict(list)   # child id -> [(parent id, parent class name, field)]
clsof = {}
def pass_refs(targets):
    f2, _ = openf(); found = collections.defaultdict(list)
    tg = targets
    for tag, b in records(f2):
        if tag not in (0x0C, 0x1C): continue
        i = 0; n = len(b)
        while i < n:
            t = b[i]; i += 1
            if t == 0xFF: i += IDS
            elif t == 0x01: i += 2 * IDS
            elif t in (0x02, 0x03): i += IDS + 8
            elif t == 0x04: i += IDS + 4
            elif t in (0x05, 0x07): i += IDS
            elif t == 0x06: i += IDS + 4
            elif t == 0x08: i += IDS + 8
            elif t == 0x20:
                cid = rid(b, i); i += IDS + 4 + 6 * IDS + 4
                cp = struct.unpack('>H', b[i:i + 2])[0]; i += 2
                for _ in range(cp):
                    i += 2; ty = b[i]; i += 1 + TS[ty]
                sf = struct.unpack('>H', b[i:i + 2])[0]; i += 2
                for _ in range(sf):
                    i += IDS; ty = b[i]; i += 1 + TS[ty]
                nf = struct.unpack('>H', b[i:i + 2])[0]; i += 2 + nf * (IDS + 1)
            elif t == 0x21:
                oid = rid(b, i); i += IDS + 4; cid = rid(b, i); i += IDS
                ln = struct.unpack('>I', b[i:i + 4])[0]; i += 4
                offs = ROFF.get(cid)
                if offs is None:
                    offs = ROFF[cid] = [(nm, off) for nm, ty, off in layout(cid) if ty == 2]
                if cname.get(cid, '') in IGNORE: offs = ()   # Cleaner links are not holders
                for nm, off in offs:
                    v = int.from_bytes(b[i + off:i + off + IDS], 'big')
                    if v in tg: found[v].append((oid, cname.get(cid, '?'), nm))
                i += ln
            elif t == 0x22:
                oid = rid(b, i); i += IDS + 4; ln = struct.unpack('>I', b[i:i + 4])[0]; i += 4
                acid = rid(b, i); i += IDS
                if ln:
                    arr = struct.unpack('>%d%s' % (ln, 'Q' if IDS == 8 else 'I'), b[i:i + ln * IDS])
                    for v in tg.intersection(arr):
                        found[v].append((oid, cname.get(acid, '?') + '[]', '[]'))
                i += ln * IDS
            elif t == 0x23:
                i += IDS + 4; ln = struct.unpack('>I', b[i:i + 4])[0]; i += 4; ty = b[i]; i += 1 + ln * TS[ty]
    for cid, srefs in cstatic_refs.items():
        for nm, v in srefs:
            if v in tg: found[v].append((cid, 'static ' + cname.get(cid, '?'), nm))
    return found
ROFF = {}
IGNORE = {'jdk.internal.ref.Cleaner', 'java.lang.ref.Cleaner', 'jdk.internal.ref.CleanerImpl$PhantomCleanableRef'}

BIGNC = {o for o, v in other.items() if not v[5] and v[1] >= (1 << 20)}
frontier = set(owners) | set(slices) | BIGNC
for hop in range(MAXHOPS):
    if not frontier: break
    found = pass_refs(frontier)
    nxt = set()
    for child, lst in found.items():
        parents[child].extend(lst)
        for pid, pc, fld in lst:
            clsof[pid] = pc
            if not STOP.search(pc.split('$$')[0]) and pid not in parents and not pc.startswith('static '):
                nxt.add(pid)
    print('hop %d: %d targets -> %d referrers, %d to follow' % (hop + 1, len(frontier), sum(len(v) for v in found.values()), len(nxt)), file=sys.stderr)
    frontier = nxt

def chains(oid, depth=0, seen=None):
    seen = seen or set()
    if depth > MAXHOPS or oid in seen or oid not in parents: return [[]]
    seen = seen | {oid}; out = []
    for pid, pc, fld in parents[oid]:
        for c in chains(pid, depth + 1, seen):
            out.append(['%s.%s' % (pc, fld)] + c)
    return out[:20] or [[]]

def category(ch):
    s = ' <- '.join(ch)
    if re.search(r'LargeMessage|ProcessLargeMessage', s): return 'R: receive queue, queued LARGE frames'
    if re.search(r'ProcessSmallMessage', s): return 'R: receive queue, small messages'
    if re.search(r'IntactFrame|FrameDecoder', s): return 'R: inbound frames being decoded'
    if re.search(r'Hints', s): return 'O: hints buffers'
    if re.search(r'DataOutputBuffer|scratch', s, re.I): return 'O: DataOutputBuffer scratch'
    if re.search(r'BufferPool', s): return 'P: BufferPool chunks, no live consumer'
    if re.search(r'CommitLog|Compress|SSTable|Memtable|ChunkCache|Flush|ReadAhead', s): return 'O: storage I/O buffers'
    if re.search(r'netty|Epoll|sun.nio.ch', s): return 'O: netty / NIO buffers'
    if not s: return 'O: no strong referrer (garbage awaiting Cleaner)'
    return 'O: other'

def cat_of(oid):
    cs = chains(oid); cats = collections.Counter(category(c) for c in cs)
    # prefer a consumer category over the BufferPool container
    for pref in ('R: receive queue, queued LARGE frames', 'R: receive queue, small messages',
                 'R: inbound frames being decoded', 'O: hints buffers', 'O: DataOutputBuffer scratch'):
        if pref in cats: return pref, cs
    return cats.most_common(1)[0][0], cs

bycat = collections.Counter(); examples = {}
# group slices by owner
sl_by_owner = collections.defaultdict(list)
for s_id, sv in slices.items(): sl_by_owner[sv[3]].append(s_id)
for o, v in owners.items():
    cap, addr = v[1], v[2]
    cov = []
    for s_id in sl_by_owner.get(o, []):
        c, cs = cat_of(s_id)
        if c.startswith('P: BufferPool') or c.startswith('O: no strong referrer'):
            continue  # container slice (Chunk slab) or garbage slice: not a consumer
        sa, sc = slices[s_id][2], slices[s_id][1]
        cov.append((sa, sa + sc, c)); examples.setdefault(c, cs[0] if cs else [])
    cov.sort()
    # union of consumer ranges inside the owner (first category wins on overlap)
    pos = addr; used = 0
    for a, e, c in cov:
        a = max(a, pos, addr); e = min(e, addr + cap)
        if e > a: bycat[c] += e - a; used += e - a; pos = e
    rest = cap - used
    if rest > 0:
        c, cs = cat_of(o); bycat[c if not cov else ('P: BufferPool chunks, no live consumer' if 'BufferPool' in ' '.join(cs[0] if cs else []) else c)] += rest
        examples.setdefault(c, cs[0] if cs else [])

print('\nLive direct memory by holder (owners = %.1f MiB):' % (tot / MiB))
for c, b in bycat.most_common():
    print('  %-52s %8.1f MiB  %5.1f %%' % (c, b / MiB, 100.0 * b / tot if tot else 0))
print('\nExample referrer chain per category (buffer <- holder <- ...):')
for c, ch in examples.items():
    print('  %s:\n      %s' % (c, ' <- '.join(ch[:6])))
sz = collections.Counter()
for o, v in owners.items(): sz[v[1]] += 1
print('\nOwner sizes (bytes x count, top 8):', ', '.join('%d x %d' % (k, n) for k, n in sz.most_common(8)))

# ---- detail: bytes per (category, holder signature = first 3 hops), and per owner size class ----
if '--detail' in sys.argv:
    det = collections.Counter(); szc = collections.Counter()
    for o, v in owners.items():
        cap = v[1]
        sl = sl_by_owner.get(o, [])
        kind = 'macro/pool' if cap >= 4 << 20 else 'single'
        if sl:
            for s_id in sl:
                c, cs = cat_of(s_id); sig = ' <- '.join((cs[0] if cs else [])[:3])
                det[(kind, 'slice', c, sig)] += slices[s_id][1]
        else:
            c, cs = cat_of(o); sig = ' <- '.join((cs[0] if cs else [])[:3])
            det[(kind, 'owner', c, sig)] += cap
    print('\nDetail (bytes of slices or unsliced owners; slices may overlap their container chunk slab):')
    for (k, w, c, sig), b in det.most_common(25):
        print('  %7.1f MiB  %-10s %-6s %-45s %s' % (b / MiB, k, w, c[:45], sig[:200]))

if '--detail' in sys.argv:
    print('\nNo-cleaner DirectByteBuffers >= 1 MiB (Netty arena chunks?): count by (capacity, holder):')
    cc = collections.Counter(); seen_addr = {}
    for o in BIGNC:
        v = other[o]; cs = chains(o); sig = ' <- '.join((cs[0] if cs else [])[:3])
        cc[(v[1], sig)] += 1; seen_addr.setdefault(v[2], v[1])
    for (cap, sig), n in cc.most_common(10):
        print('  %d x %.1f MiB  %s' % (n, cap / MiB, sig[:220]))
    print('  distinct base addresses: %d, sum of their capacities %.1f MiB' % (len(seen_addr), sum(seen_addr.values()) / MiB))
