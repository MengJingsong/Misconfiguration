#!/usr/bin/env python3
"""hprof_holders.py - small HotSpot .hprof analyser for the OOM-exp R4 recheck (2026-11-11).

Usage: python3 -I hprof_holders.py <dump.hprof> [topN]

Prints:
  1. class histogram of ALL objects in the dump (count, estimated shallow bytes);
  2. reachability from GC roots (roots = hprof GC-root records + class statics + class loaders);
  3. holder attribution for the three R4 domains: objects reachable from the holder but NOT
     reachable from the GC roots when the holders are blocked (an approximation of retained size,
     the same idea as MAT's retained set), with the top classes inside each holder:
       memtable      = every instance of a subclass of o.a.c.db.memtable.AbstractMemtable
       counter_cache = CacheService.instance.counterCache (AutoSavingCache)
       key_cache     = CacheService.instance.keyCache (AutoSavingCache)
  4. the controls' own counters (K) read from the dump: Caffeine weightedSize/maximum for each
     cache, MemtablePool SubPool fields, each memtable's on-heap SubAllocator 'owns';
  5. the thread whose stack HotSpot marked as throwing the OutOfMemoryError (a fake top frame
     OutOfMemoryError.<init>, written only for -XX:+HeapDumpOnOutOfMemoryError dumps), with its stack.

Shallow sizes are estimates for a 64-bit JVM with compressed oops and class pointers (heap < 32 GiB):
instance = align8(12 + fields, refs 4 bytes); array = align8(16 + n * elem).  The id size must be 8.
Read-only; standard library only.
"""
import sys, mmap, struct, bisect, array, collections, time

T0 = time.time()
def log(*a):
    print("[%7.1fs]" % (time.time() - T0), *a, file=sys.stderr, flush=True)

BASIC_SIZE_DUMP = {2: 8, 4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}   # sizes in the dump (id = 8)
BASIC_SIZE_MEM = {2: 4, 4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}    # sizes in memory (compressed oops)
PRIM_NAME = {4: 'boolean[]', 5: 'char[]', 6: 'float[]', 7: 'double[]', 8: 'byte[]', 9: 'short[]', 10: 'int[]', 11: 'long[]'}
STRUCT_CH = {4: 'b', 5: 'H', 6: 'f', 7: 'd', 8: 'b', 9: 'h', 10: 'i', 11: 'q', 2: 'Q'}
K_INST, K_OARR, K_PARR = 0, 1, 2

def a8(x):
    return (x + 7) & ~7

def pretty(n):
    if n is None:
        return '?'
    if n.startswith('['):
        dims = len(n) - len(n.lstrip('['))
        rest = n[dims:]
        base = {'B': 'byte', 'C': 'char', 'Z': 'boolean', 'S': 'short', 'I': 'int', 'J': 'long', 'F': 'float', 'D': 'double'}.get(rest)
        if base is None and rest.startswith('L'):
            base = rest[1:].rstrip(';')
        return (base or rest).replace('/', '.') + '[]' * dims
    return n.replace('/', '.')

def main():
    path = sys.argv[1]
    topn = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    f = open(path, 'rb')
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    end = len(mm)
    hdr_end = mm.find(b'\0')
    fmt = mm[:hdr_end].decode()
    idsize, = struct.unpack_from('>I', mm, hdr_end + 1)
    assert idsize == 8, "id size %d unsupported" % idsize
    pos = hdr_end + 1 + 4 + 8
    log("header", fmt, "idsize", idsize, "file bytes", end)

    strings = {}
    class_name = {}          # class obj id -> name
    class_serial = {}        # serial -> class obj id
    frames = {}              # frame id -> (method, sig, class serial, line)
    traces = {}              # serial -> (thread serial, [frame ids])
    classes = {}             # class id -> (super, loader, instsize, [(nameid, type)], [(nameid,type,value)])
    roots = array.array('Q')
    thread_objs = []         # (obj id, thread serial, trace serial)

    ids = array.array('Q'); offs = array.array('Q'); kinds = bytearray(); clsref = array.array('Q'); sizes = array.array('I')
    # for K_INST: clsref = class id, offs = start of field data, sizes filled later
    # for K_OARR: clsref = array class id, offs = start of element ids, sizes = len (count)
    # for K_PARR: clsref = prim type, offs = start of data, sizes = len
    unpack = struct.unpack_from
    nrec = 0
    while pos < end:
        tag = mm[pos]; length, = unpack('>I', mm, pos + 5); body = pos + 9; nxt = body + length
        if tag == 0x01:
            sid, = unpack('>Q', mm, body)
            strings[sid] = mm[body + 8:nxt].decode('utf-8', 'replace')
        elif tag == 0x02:
            ser, cid, _st, nid = unpack('>IQIQ', mm, body)
            class_serial[ser] = cid; class_name[cid] = strings.get(nid)
        elif tag == 0x04:
            fid, mn, sg, sf, cser, line = unpack('>QQQQIi', mm, body)
            frames[fid] = (strings.get(mn), strings.get(sg), cser, line)
        elif tag == 0x05:
            ser, tser, nf = unpack('>III', mm, body)
            traces[ser] = (tser, list(unpack('>%dQ' % nf, mm, body + 12)))
        elif tag in (0x0C, 0x1C):
            p = body
            while p < nxt:
                st = mm[p]; p += 1
                if st == 0x21:
                    oid, _s, cid, nb = unpack('>QIQI', mm, p)
                    ids.append(oid); offs.append(p + 24); kinds.append(K_INST); clsref.append(cid); sizes.append(0)
                    p += 24 + nb
                elif st == 0x22:
                    oid, _s, n, acid = unpack('>QIIQ', mm, p)
                    ids.append(oid); offs.append(p + 24); kinds.append(K_OARR); clsref.append(acid); sizes.append(n)
                    p += 24 + n * 8
                elif st == 0x23:
                    oid, _s, n, ty = unpack('>QIIB', mm, p)
                    ids.append(oid); offs.append(p + 17); kinds.append(K_PARR); clsref.append(ty); sizes.append(n)
                    p += 17 + n * BASIC_SIZE_DUMP[ty]
                elif st == 0x20:
                    cid, _s, sup, ldr, _sg, _pd, _r1, _r2, isz = unpack('>QIQQQQQQI', mm, p); p += 64
                    ncp, = unpack('>H', mm, p); p += 2
                    for _ in range(ncp):
                        ty = mm[p + 2]; p += 3 + BASIC_SIZE_DUMP[ty]
                    nst, = unpack('>H', mm, p); p += 2
                    statics = []
                    for _ in range(nst):
                        nid, ty = unpack('>QB', mm, p); p += 9
                        sz = BASIC_SIZE_DUMP[ty]
                        val = unpack('>' + STRUCT_CH[ty], mm, p)[0]; p += sz
                        statics.append((nid, ty, val))
                        if ty == 2 and val:
                            roots.append(val)
                    nif, = unpack('>H', mm, p); p += 2
                    fl = []
                    for _ in range(nif):
                        nid, ty = unpack('>QB', mm, p); p += 9
                        fl.append((nid, ty))
                    classes[cid] = (sup, ldr, isz, fl, statics)
                    if ldr:
                        roots.append(ldr)
                elif st == 0xFF:
                    roots.append(unpack('>Q', mm, p)[0]); p += 8
                elif st == 0x01:
                    roots.append(unpack('>Q', mm, p)[0]); p += 16
                elif st in (0x02, 0x03):
                    roots.append(unpack('>Q', mm, p)[0]); p += 16
                elif st in (0x04, 0x06):
                    roots.append(unpack('>Q', mm, p)[0]); p += 12
                elif st in (0x05, 0x07):
                    roots.append(unpack('>Q', mm, p)[0]); p += 8
                elif st == 0x08:
                    oid, tser, sser = unpack('>QII', mm, p); p += 16
                    roots.append(oid); thread_objs.append((oid, tser, sser))
                else:
                    raise ValueError("unknown heap sub-record 0x%x at %d" % (st, p - 1))
                nrec += 1
                if nrec % 5000000 == 0:
                    log("parsed", nrec, "heap sub-records,", "%.0f%%" % (100.0 * p / end))
        pos = nxt
    n = len(ids)
    log("objects", n, "classes", len(classes), "roots", len(roots))

    # ---- per-class layouts (data order: own fields, then superclass fields)
    layout_cache = {}
    def layout(cid):
        if cid in layout_cache:
            return layout_cache[cid]
        fl = []
        c = cid
        while c and c in classes:
            fl.extend(classes[c][3]); c = classes[c][0]
        offs_ = []; o = 0; mem = 0
        names = []
        for nid, ty in fl:
            names.append((strings.get(nid), ty, o))
            if ty == 2:
                offs_.append(o)
            o += BASIC_SIZE_DUMP[ty]; mem += BASIC_SIZE_MEM[ty]
        fmtparts = []; cur = 0
        for ro in offs_:
            if ro > cur:
                fmtparts.append('%dx' % (ro - cur))
            fmtparts.append('Q'); cur = ro + 8
        reffmt = struct.Struct('>' + ''.join(fmtparts)) if offs_ else None
        res = (reffmt, a8(12 + mem), names)
        layout_cache[cid] = res
        return res

    def is_subclass(cid, target):
        c = cid
        while c and c in classes:
            if class_name.get(c) == target:
                return True
            c = classes[c][0]
        return False

    # ---- sort by id (needed for bisect lookups)
    sorted_ok = all(ids[i] < ids[i + 1] for i in range(n - 1))
    if not sorted_ok:
        log("sorting object table")
        order = sorted(range(n), key=ids.__getitem__)
        ids = array.array('Q', (ids[i] for i in order)); offs = array.array('Q', (offs[i] for i in order))
        kinds = bytearray(kinds[i] for i in order); clsref = array.array('Q', (clsref[i] for i in order))
        sizes = array.array('I', (sizes[i] for i in order)); del order
    # shallow sizes and histogram keys
    shallow = array.array('I', bytes(4 * n))
    hkey = array.array('Q', bytes(8 * n))      # class id (instances, obj arrays) or prim type
    for i in range(n):
        k = kinds[i]
        if k == K_INST:
            shallow[i] = layout(clsref[i])[1]
        elif k == K_OARR:
            shallow[i] = a8(16 + 4 * sizes[i])
        else:
            shallow[i] = a8(16 + BASIC_SIZE_MEM[clsref[i]] * sizes[i])
        hkey[i] = clsref[i]
    log("sizes computed")

    def kname(i):
        k = kinds[i]
        if k == K_PARR:
            return PRIM_NAME[clsref[i]]
        return pretty(class_name.get(clsref[i]))

    def idx(oid):
        j = bisect.bisect_left(ids, oid)
        if j < n and ids[j] == oid:
            return j
        return -1

    def refs(i):
        k = kinds[i]
        if k == K_INST:
            rf = layout(clsref[i])[0]
            return rf.unpack_from(mm, offs[i]) if rf else ()
        if k == K_OARR:
            m = sizes[i]
            return unpack('>%dQ' % m, mm, offs[i]) if m else ()
        return ()

    def fields(i):
        names = layout(clsref[i])[2]
        out = {}
        for nm, ty, o in names:
            if nm in out:
                continue                     # subclass field shadows superclass field of same name
            out[nm] = unpack('>' + STRUCT_CH[ty], mm, offs[i] + o)[0]
        return out

    def jstring(oid):
        j = idx(oid)
        if j < 0:
            return None
        fs = fields(j)
        v = idx(fs.get('value', 0))
        if v < 0:
            return None
        raw = mm[offs[v]:offs[v] + sizes[v] * BASIC_SIZE_DUMP[clsref[v]]]
        if clsref[v] == 8:
            return raw.decode('latin-1') if fs.get('coder', 0) == 0 else raw.decode('utf-16-be', 'replace')
        return raw.decode('utf-16-be', 'replace')

    def hist(sel_iter, title, top):
        cnt = collections.Counter(); byt = collections.Counter(); tot = 0; tn = 0
        for i in sel_iter:
            key = (kinds[i] == K_PARR, hkey[i])
            cnt[key] += 1; byt[key] += shallow[i]; tot += shallow[i]; tn += 1
        print("\n## %s: %d objects, %.1f MiB shallow" % (title, tn, tot / 1048576.0))
        print("%12s %14s %8s  %s" % ("count", "shallow_bytes", "MiB", "class"))
        for key, b in byt.most_common(top):
            nm = PRIM_NAME[key[1]] if key[0] else pretty(class_name.get(key[1]))
            print("%12d %14d %8.1f  %s" % (cnt[key], b, b / 1048576.0, nm))
        return tot

    print("# hprof_holders.py report for", path)
    print("format %s, objects %d, classes %d, GC-root/static refs %d" % (fmt, n, len(classes), len(roots)))
    total_all = hist(range(n), "Histogram, all objects in dump (incl. unreachable)", topn)

    # ---- locate holders
    cs_cid = [c for c, nm in class_name.items() if nm == 'org/apache/cassandra/service/CacheService']
    holders = collections.OrderedDict()
    cache_objs = {}
    for i in range(n):
        if kinds[i] == K_INST and clsref[i] in cs_cid:
            fs = fields(i)
            for nm in ('keyCache', 'counterCache', 'rowCache'):
                if fs.get(nm):
                    cache_objs[nm] = fs[nm]
    mem_cids = set(c for c in classes if is_subclass(c, 'org/apache/cassandra/db/memtable/AbstractMemtable'))
    memtables = [i for i in range(n) if kinds[i] == K_INST and clsref[i] in mem_cids]
    holders['memtable'] = memtables
    # the Caffeine BoundedLocalCache behind each AutoSavingCache (AutoSavingCache.map -> CaffeineCache.cache
    # -> BoundedLocalManualCache.cache). Blocking it (not the AutoSavingCache) matters: metrics gauges and
    # other wrappers also reference the outer objects, so the entries would otherwise count as 'base'.
    def cache_core(oid):
        cur = idx(oid)
        for fld in ('map', 'cache', 'cache'):
            if cur < 0:
                return -1
            cur = idx(fields(cur).get(fld, 0))
        return cur
    holders['counter_cache'] = [j for j in [cache_core(cache_objs.get('counterCache', 0))] if j >= 0]
    holders['key_cache'] = [j for j in [cache_core(cache_objs.get('keyCache', 0))] if j >= 0]
    log("holders:", {k: len(v) for k, v in holders.items()})

    # ---- base traversal from GC roots with the holder objects blocked
    BASE, BLOCK = 1, 2
    mark = bytearray(n)
    for lst in holders.values():
        for j in lst:
            mark[j] = BLOCK
    def traverse(start_ids_or_idx, tagv, is_idx=False, mk=None):
        mark_ = mark if mk is None else mk
        stack = array.array('Q')
        tot = 0; cntn = 0
        for r in start_ids_or_idx:
            j = r if is_idx else idx(r)
            if j >= 0 and mark_[j] == 0:
                mark_[j] = tagv; stack.append(j)
        members = array.array('Q')
        while stack:
            j = stack.pop()
            members.append(j); tot += shallow[j]; cntn += 1
            for r in refs(j):
                if r:
                    k = idx(r)
                    if k >= 0 and mark_[k] == 0:
                        mark_[k] = tagv; stack.append(k)
        return tot, cntn, members
    btot, bcnt, _ = traverse(roots, BASE)
    log("base reachable", bcnt, btot)
    print("\n## Reachability")
    print("base (reachable from GC roots without passing through the holders): %d objects, %.1f MiB" % (bcnt, btot / 1048576.0))
    tag = 3
    holder_tot = {}
    for name, lst in holders.items():
        for j in lst:
            mark[j] = 0
        t, c, members = traverse(lst, tag, is_idx=True)
        holder_tot[name] = t
        tag += 1
        hist(members, "Holder %s (%d root objects): exclusive reachable set" % (name, len(lst)), 15)
    unreach = sum(shallow[i] for i in range(n) if mark[i] == 0)
    # inclusive reachable set per holder (also counts objects shared with base, e.g. a flushing memtable's
    # partitions also held by the flush writer's iterator); the other holders stay blocked.
    incl = {}
    allh = set(j for lst in holders.values() for j in lst)
    for name, lst in holders.items():
        m2 = bytearray(n)
        for j in allh:
            m2[j] = BLOCK
        for j in lst:
            m2[j] = 0
        t, c, members = traverse(lst, 9, is_idx=True, mk=m2)
        incl[name] = (t, c)
    # memtable DATA (shared or not): from each memtable's 'partitions' map, following only the classes
    # that make up partition data (no schema/CFS/allocator/pool objects), so a flushing memtable whose
    # partitions are also referenced by the flush writer still counts as memtable memory.
    MEM_DATA = set('''java.util.concurrent.ConcurrentSkipListMap java.util.concurrent.ConcurrentSkipListMap$Node
      java.util.concurrent.ConcurrentSkipListMap$Index java.util.concurrent.ConcurrentSkipListMap$HeadIndex
      org.apache.cassandra.db.partitions.AtomicBTreePartition org.apache.cassandra.db.partitions.BTreePartitionData
      org.apache.cassandra.db.rows.BTreeRow org.apache.cassandra.db.rows.BufferCell org.apache.cassandra.db.rows.EncodingStats
      org.apache.cassandra.db.BufferDecoratedKey org.apache.cassandra.dht.Murmur3Partitioner$LongToken
      org.apache.cassandra.db.LivenessInfo org.apache.cassandra.db.LivenessInfo$ExpiringLivenessInfo
      org.apache.cassandra.db.BufferClustering org.apache.cassandra.db.rows.Row$Deletion org.apache.cassandra.db.DeletionTime
      org.apache.cassandra.db.rows.ComplexColumnData java.nio.HeapByteBuffer java.lang.Object[] java.nio.ByteBuffer[]
      org.apache.cassandra.db.rows.CellPath$SingleItemCellPath'''.split())
    m3 = bytearray(n)
    stack = array.array('Q'); mtot = 0; mcnt = 0; mh = collections.Counter()
    for j in memtables:
        pj = idx(fields(j).get('partitions', 0))
        if pj >= 0 and not m3[pj]:
            m3[pj] = 1; stack.append(pj)
    while stack:
        j = stack.pop(); mtot += shallow[j]; mcnt += 1; mh[kname(j)] += shallow[j]
        for r in refs(j):
            if r:
                k = idx(r)
                if k >= 0 and not m3[k] and (kinds[k] == K_PARR or kname(k) in MEM_DATA):
                    m3[k] = 1; stack.append(k)
    print("\n## Memtable data (from each memtable's partitions map, data classes only, shared or not): %.1f MiB, %d objects; top: %s" % (
        mtot / 1048576.0, mcnt, ", ".join("%s %.1f" % (k, v / 1048576.0) for k, v in mh.most_common(6))))
    print("\n## Inclusive reachable per holder (other holders blocked; includes objects shared with base; for memtable this also reaches schema/CFS objects, use the line above), MiB: %s" % (
        " | ".join("%s %.1f (%d objects)" % (k, v[0] / 1048576.0, v[1]) for k, v in incl.items())))
    print("\n## Totals (MiB): dump all %.1f | base %.1f | %s | unreachable (garbage) %.1f" % (
        total_all / 1048576.0, btot / 1048576.0,
        " | ".join("%s %.1f" % (k, v / 1048576.0) for k, v in holder_tot.items()), unreach / 1048576.0))

    # ---- K counters from the dump
    print("\n## Control counters (K) read from the dump")
    for nm, oid in cache_objs.items():
        j = idx(oid)
        if j < 0:
            continue
        chain = [nm]
        cur = j
        # AutoSavingCache.map -> CaffeineCache.cache -> Bounded*ManualCache.cache -> BoundedLocalCache subclass
        for fld in ('map', 'cache', 'cache'):
            fs = fields(cur)
            nxt_ = idx(fs.get(fld, 0)) if fld in fs else -1
            if nxt_ < 0:
                break
            cur = nxt_; chain.append("%s:%s" % (fld, kname(cur)))
        fs = fields(cur)
        longs = {k: v for k, v in fs.items() if k and ('eight' in k.lower() or 'maximum' in k.lower())}
        print("%s -> %s :" % (nm, " -> ".join(chain[1:])))
        print("   %s" % longs)
        mapj = idx(fs.get('data', 0))
        if mapj >= 0:
            mf = fields(mapj)
            print("   data map %s fields: %s" % (kname(mapj), {k: v for k, v in mf.items() if k in ('baseCount', 'sizeCtl')}))
    for i in range(n):
        if kinds[i] == K_INST and class_name.get(clsref[i], '') and 'MemtablePool$SubPool' in class_name[clsref[i]]:
            fs = fields(i)
            print("MemtablePool SubPool %s: %s" % (kname(i), {k: v for k, v in fs.items() if k in ('limit', 'allocated', 'reclaiming', 'nextClean')}))
    for j in memtables:
        fs = fields(j)
        al = idx(fs.get('allocator', 0))
        owns = None
        if al >= 0:
            af = fields(al)
            oh = idx(af.get('onHeap', 0))
            if oh >= 0:
                owns = fields(oh).get('owns')
        if owns:
            print("memtable %s id=0x%x allocator.onHeap.owns=%s" % (kname(j), ids[j], owns))

    # ---- OOME thread
    print("\n## Threads / OutOfMemoryError thread")
    for oid, tser, sser in thread_objs:
        tr = traces.get(sser)
        if not tr or not tr[1]:
            continue
        top = frames.get(tr[1][0])
        topcls = class_name.get(class_serial.get(top[2])) if top else None
        if top and top[0] == '<init>' and topcls == 'java/lang/OutOfMemoryError':
            j = idx(oid)
            tname = jstring(fields(j).get('name', 0)) if j >= 0 else None
            print("OOME thread: serial %d name %r" % (tser, tname))
            for fid in tr[1][:40]:
                fr = frames.get(fid)
                if fr:
                    print("    at %s.%s%s line %s" % (pretty(class_name.get(class_serial.get(fr[2]))), fr[0], fr[1], fr[3]))
    log("done")

if __name__ == '__main__':
    main()
