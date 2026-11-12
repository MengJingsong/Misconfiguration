#!/usr/bin/env python3
"""Minimal HPROF (JAVA PROFILE 1.0.2) analyser for the OOM-exp R3 recheck.

Usage: python3 -I hprof_histo.py <dump.hprof> [topN]

Prints:
  1. class histogram of ALL objects in the dump (count, shallow bytes);
  2. live set (reachable from GC roots + all class objects' statics) totals;
  3. domain attribution by bounded reachability walks over live objects:
     - memtable domain: from each SkipListMemtable/TrieMemtable `partitions` field, following
       references only into memtable-data classes (allowlist below);
     - Caffeine cache domains: from each Caffeine BoundedLocalCache instance, following references
       only into Caffeine-internal / ConcurrentHashMap / cache key+value classes; each cache is
       reported separately and labelled by the key class found in it.
Shallow sizes assume a 64-bit JVM with compressed oops and class pointers (12-byte object header,
16-byte array header, 4-byte references, 8-byte alignment) -- the -Xmx1024M default.
"""
import mmap, struct, sys
from collections import defaultdict, deque

PRIM_SIZE = {4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}
PRIM_NAME = {4: 'boolean[]', 5: 'char[]', 6: 'float[]', 7: 'double[]', 8: 'byte[]', 9: 'short[]', 10: 'int[]', 11: 'long[]'}
A8 = lambda n: (n + 7) & ~7

path = sys.argv[1]
TOP = int(sys.argv[2]) if len(sys.argv) > 2 else 40
f = open(path, 'rb')
mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
hdr_end = mm.find(b'\0')
IDS = struct.unpack_from('>I', mm, hdr_end + 1)[0]
assert IDS == 8, IDS
pos = hdr_end + 1 + 4 + 8
U4 = struct.Struct('>I'); ID = struct.Struct('>Q'); U2 = struct.Struct('>H')
u4 = U4.unpack_from; uid = ID.unpack_from; u2 = U2.unpack_from

strings = {}            # id -> str
class_name_id = {}      # class obj id -> name string id
classes = {}            # class id -> (super, [(name_id, type)], instsize)
static_refs = []        # ids referenced by class statics
roots = []
obj_off = {}            # object id -> offset of its sub-record body (after tag)
hist_cnt = defaultdict(int); hist_bytes = defaultdict(int)   # key: class id or prim name
inst_nbytes = {}        # class id -> instance data length (bytes in hprof)

ROOT_SKIP = {0xFF: 0, 0x01: 8, 0x02: 8, 0x03: 8, 0x04: 4, 0x05: 0, 0x06: 4, 0x07: 0, 0x08: 8,
             0x89: 0, 0x8a: 0, 0x8b: 0, 0x8c: 4, 0x8d: 0, 0x8e: 8, 0x90: 0}

def parse_segment(p, end):
    while p < end:
        t = mm[p]; p += 1
        if t == 0x21:
            oid = uid(mm, p)[0]; cid = uid(mm, p + 12)[0]; nb = u4(mm, p + 20)[0]
            obj_off[oid] = p - 1
            hist_cnt[cid] += 1; inst_nbytes[cid] = nb
            p += 24 + nb
        elif t == 0x22:
            oid = uid(mm, p)[0]; n = u4(mm, p + 12)[0]; acid = uid(mm, p + 16)[0]
            obj_off[oid] = p - 1
            hist_cnt[acid] += 1; hist_bytes[acid] += A8(16 + 4 * n)
            p += 24 + 8 * n
        elif t == 0x23:
            oid = uid(mm, p)[0]; n = u4(mm, p + 12)[0]; et = mm[p + 16]
            obj_off[oid] = p - 1
            k = PRIM_NAME[et]; hist_cnt[k] += 1; hist_bytes[k] += A8(16 + PRIM_SIZE[et] * n)
            p += 17 + PRIM_SIZE[et] * n
        elif t == 0x20:
            cid = uid(mm, p)[0]; sup = uid(mm, p + 12)[0]
            q = p + 8 + 4 + 8 * 6
            isz = u4(mm, q)[0]; q += 4
            ncp = u2(mm, q)[0]; q += 2
            for _ in range(ncp):
                ty = mm[q + 2]; q += 3 + (8 if ty == 2 else PRIM_SIZE[ty])
            nst = u2(mm, q)[0]; q += 2
            for _ in range(nst):
                ty = mm[q + 8]
                if ty == 2:
                    r = uid(mm, q + 9)[0]
                    if r: static_refs.append(r)
                q += 9 + (8 if ty == 2 else PRIM_SIZE[ty])
            nf = u2(mm, q)[0]; q += 2
            flds = []
            for _ in range(nf):
                flds.append((uid(mm, q)[0], mm[q + 8])); q += 9
            classes[cid] = (sup, flds, isz)
            p = q
        elif t in ROOT_SKIP:
            roots.append(uid(mm, p)[0]); p += 8 + ROOT_SKIP[t]
        else:
            raise ValueError('unknown subrecord 0x%x at %d' % (t, p - 1))

while pos < len(mm):
    tag = mm[pos]; ln = u4(mm, pos + 5)[0]; body = pos + 9
    if tag == 0x01:
        strings[uid(mm, body)[0]] = mm[body + 8: body + ln].decode('utf-8', 'replace')
    elif tag == 0x02:
        class_name_id[uid(mm, body + 4)[0]] = uid(mm, body + 16)[0]
    elif tag in (0x0C, 0x1C):
        parse_segment(body, body + ln)
    pos = body + ln
print('objects: %d  classes: %d  roots: %d' % (len(obj_off), len(classes), len(roots)), flush=True)

def cname(cid):
    if isinstance(cid, str): return cid
    n = strings.get(class_name_id.get(cid), '?%x' % cid)
    if n.startswith('['):   # object array class, e.g. [Ljava.lang.Object;
        return (n[2:-1] + '[]' if n.startswith('[L') else n).replace('/', '.')
    return n.replace('/', '.')

layout_cache = {}
def layout(cid):
    """list of (byte offset in hprof instance data, is_ref) for ref fields; nrefs."""
    if cid in layout_cache: return layout_cache[cid]
    chain = []; c = cid
    while c and c in classes:
        chain.append(c); c = classes[c][0]
    offs = []; o = 0; nrefs = 0
    for c in chain:          # hprof writes fields of the class first, then its supers
        for (_, ty) in classes[c][1]:
            if ty == 2: offs.append(o); nrefs += 1; o += 8
            else: o += PRIM_SIZE[ty]
    layout_cache[cid] = (offs, nrefs)
    return layout_cache[cid]

field_off_cache = {}
def field_off(cid, fname):
    key = (cid, fname)
    if key in field_off_cache: return field_off_cache[key]
    c = cid; o = 0; res = None
    chain = []
    while c and c in classes:
        chain.append(c); c = classes[c][0]
    for c in chain:
        for (nid, ty) in classes[c][1]:
            if strings.get(nid) == fname and ty == 2 and res is None: res = o
            o += 8 if ty == 2 else PRIM_SIZE[ty]
    field_off_cache[key] = res
    return res

def shallow_inst(cid):
    nb = inst_nbytes.get(cid, 0); _, nrefs = layout(cid)
    return A8(12 + nb - 4 * nrefs)

def obj_class_and_size(oid):
    p = obj_off[oid]; t = mm[p]
    if t == 0x21:
        cid = uid(mm, p + 13)[0]; return cid, shallow_inst(cid)
    if t == 0x22:
        n = u4(mm, p + 13)[0]; return uid(mm, p + 17)[0], A8(16 + 4 * n)
    n = u4(mm, p + 13)[0]; et = mm[p + 17]
    return PRIM_NAME[et], A8(16 + PRIM_SIZE[et] * n)

def refs(oid):
    p = obj_off[oid]; t = mm[p]
    if t == 0x21:
        cid = uid(mm, p + 13)[0]; base = p + 25
        for o in layout(cid)[0]:
            r = uid(mm, base + o)[0]
            if r: yield r
    elif t == 0x22:
        n = u4(mm, p + 13)[0]; base = p + 25
        for i in range(n):
            r = uid(mm, base + 8 * i)[0]
            if r: yield r

def get_field(oid, fname):
    p = obj_off[oid]; cid = uid(mm, p + 13)[0]; o = field_off(cid, fname)
    if o is None: return None
    return uid(mm, p + 25 + o)[0] or None

# ---- 1. full histogram
rows = []
for k, c in hist_cnt.items():
    b = hist_bytes[k] if (isinstance(k, str) or k not in inst_nbytes) else c * shallow_inst(k)
    rows.append((b, c, cname(k)))
rows.sort(reverse=True)
tot = sum(r[0] for r in rows)
print('\n== class histogram, all objects in dump: %d objects, %.1f MiB shallow' % (sum(r[1] for r in rows), tot / 2**20))
print('%12s %14s  %s' % ('count', 'shallow_bytes', 'class'))
for b, c, n in rows[:TOP]:
    print('%12d %14d  %s' % (c, b, n))

# ---- 2. live set
live = set(); dq = deque()
for r in roots + static_refs + list(classes.keys()):
    if r in obj_off and r not in live: live.add(r); dq.append(r)
while dq:
    o = dq.popleft()
    for r in refs(o):
        if r in obj_off and r not in live: live.add(r); dq.append(r)
live_bytes = 0; live_hist = defaultdict(lambda: [0, 0])
for o in live:
    cid, sz = obj_class_and_size(o); live_bytes += sz
    h = live_hist[cid]; h[0] += 1; h[1] += sz
print('\n== live set (reachable from roots/classes): %d objects, %.1f MiB shallow; unreachable %.1f MiB'
      % (len(live), live_bytes / 2**20, (tot - live_bytes) / 2**20))
lr = sorted(((v[1], v[0], cname(k)) for k, v in live_hist.items()), reverse=True)
print('%12s %14s  %s' % ('count', 'shallow_bytes', 'class (live)'))
for b, c, n in lr[:TOP]:
    print('%12d %14d  %s' % (c, b, n))

# ---- 3. domain walks
def walk(starts, allow):
    seen = set(); dq = deque(); dh = defaultdict(lambda: [0, 0]); total = 0
    for s in starts:
        if s and s in obj_off and s in live and s not in seen: seen.add(s); dq.append(s)
    while dq:
        o = dq.popleft()
        cid, sz = obj_class_and_size(o); total += sz
        h = dh[cid]; h[0] += 1; h[1] += sz
        for r in refs(o):
            if r in seen or r not in obj_off: continue
            if allow(cname(obj_class_and_size(r)[0])): seen.add(r); dq.append(r)
    return total, dh, seen

MEM_ALLOW = ('java.util.concurrent.ConcurrentSkipListMap', 'org.apache.cassandra.db.partitions.AtomicBTreePartition',
             'org.apache.cassandra.db.partitions.BTreePartitionData', 'org.apache.cassandra.db.rows.',
             'org.apache.cassandra.db.BufferDecoratedKey', 'org.apache.cassandra.db.PreHashedDecoratedKey',
             'org.apache.cassandra.dht.Murmur3Partitioner$LongToken', 'java.nio.HeapByteBuffer', 'byte[]', 'java.lang.Object[]',
             'org.apache.cassandra.db.LivenessInfo', 'org.apache.cassandra.db.ExpiringLivenessInfo',
             'org.apache.cassandra.db.DeletionTime', 'org.apache.cassandra.db.BufferClustering',
             'org.apache.cassandra.db.Clustering', 'org.apache.cassandra.db.MutableDeletionInfo',
             'org.apache.cassandra.db.DeletionInfo', 'org.apache.cassandra.db.memtable.', 'java.nio.ByteBuffer[]')
mem_allow = lambda n: n.startswith(MEM_ALLOW) and not n.startswith('org.apache.cassandra.db.memtable.Memtable_API')
CACHE_ALLOW = ('com.github.benmanes.caffeine.cache.', 'java.util.concurrent.ConcurrentHashMap',
               'org.apache.cassandra.cache.CounterCacheKey', 'org.apache.cassandra.db.ClockAndCount', 'byte[]',
               'long[]', 'java.lang.Object[]', 'org.apache.cassandra.cache.KeyCacheKey', 'org.apache.cassandra.cache.RowCacheKey',
               'org.apache.cassandra.db.RowIndexEntry', 'org.apache.cassandra.io.sstable.format.')
cache_allow = lambda n: n.startswith(CACHE_ALLOW) and 'BoundedLocalCache' not in n and 'LocalLoadingCache' not in n \
    and 'LocalManualCache' not in n and not n.startswith('com.github.benmanes.caffeine.cache.SS') \
    and not n.startswith('com.github.benmanes.caffeine.cache.SI') and 'Policy' not in n

def report(title, total, dh, n=15):
    print('\n== %s: %.1f MiB shallow (%d objects)' % (title, total / 2**20, sum(v[0] for v in dh.values())))
    for b, c, nm in sorted(((v[1], v[0], cname(k)) for k, v in dh.items()), reverse=True)[:n]:
        print('%12d %14d  %s' % (c, b, nm))

# memtables
import os
MT_NAMES = tuple(os.environ.get('MT_CLASSES', 'org.apache.cassandra.db.memtable.SkipListMemtable,org.apache.cassandra.db.memtable.TrieMemtable').split(','))
MT_FIELD = os.environ.get('MT_FIELD', 'partitions')
mt_classes = [c for c in classes if cname(c) in MT_NAMES]
mt_objs = [o for o in live if obj_class_and_size(o)[0] in mt_classes] if mt_classes else []
starts = [get_field(o, MT_FIELD) for o in mt_objs]
starts = [s for s in starts if s]
mtot, mdh, mseen = walk(starts, mem_allow)
print('\nmemtable instances (live): %d, with partitions map: %d' % (len(mt_objs), len(starts)))
report('MEMTABLE domain (walk from memtable partition maps)', mtot, mdh)

# caffeine caches
cache_objs = [o for o in live if 'BoundedLocalCache' not in cname(obj_class_and_size(o)[0])
              and cname(obj_class_and_size(o)[0]).startswith('com.github.benmanes.caffeine.cache.')
              and obj_off[o] is not None and mm[obj_off[o]] == 0x21
              and field_off(obj_class_and_size(o)[0], 'data') is not None
              and field_off(obj_class_and_size(o)[0], 'writeBuffer') is not None]
for co in cache_objs:
    ctot, cdh, cseen = walk([co], cache_allow)
    keys = [cname(k) for k in cdh if isinstance(k, int) and cname(k).startswith('org.apache.cassandra.cache.')]
    if ctot < 1 << 20: continue
    report('CAFFEINE cache %s (%s) domain' % (cname(obj_class_and_size(co)[0]), ','.join(keys) or '-'), ctot, cdh)
    ov = len(cseen & mseen)
    print('   overlap with memtable domain: %d objects' % ov)
