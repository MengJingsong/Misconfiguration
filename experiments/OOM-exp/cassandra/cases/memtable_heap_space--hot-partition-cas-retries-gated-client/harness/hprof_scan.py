#!/usr/bin/env python3
"""R16 stage-2 HPROF scanner (design §2.5): B18's scanner plus instance-field decoding (CLASS DUMP field descriptors, inherited
fields, AtomicInteger/AtomicLong values, enum ordinals) for the memtable pool and allocators: keys `pool` (the SlabPool's on-heap
SubPool limit/allocated/reclaiming/nextClean), `allocators` (per SlabAllocator: regionCount, on-heap SubAllocator owns/reclaiming/
state), `writer_traces` (stack traces in Keyspace.applyInternal / Mutation.apply). `--decode A,B,...` decodes the named classes
instead (known-answer check). Below, B18's text:
B18 stage-2 HPROF scanner: C6's scanner (design §2.5) extended 2026-11-18 per B18 design §2.5 with a shallow-bytes
histogram by class (instances by class; object arrays by element class as "<class>[]"; primitive arrays by type as "[B" etc.):
keys classes_top (top 20 by bytes) and classes_named (the B18 classes, listed even outside the top 20). From C6: Reads an HPROF 1.0.2 file sequentially (HEAP DUMP / HEAP DUMP SEGMENT records)
and prints one JSON object: count and bytes of byte[] arrays of length exactly 1,048,576 (slab regions; bytes counted as
16-byte header + 1,048,576 = 1,048,592 each, as in the class histogram), total byte[] count/bytes (header 16 + length,
8-aligned), instance count, object-array count, primitive-array count, and the total of all instance + array records as
shallow bytes (instance: 16 + field bytes, 8-aligned; arrays: 16 + payload, 8-aligned; compressed oops assumed for
object arrays: 4 bytes per element). usage: python3 -I hprof_scan.py <file.hprof>"""
import json, mmap, struct, sys

SIZES = {2: None, 4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}
REGION = 1048576


def a8(n):
    return (n + 7) & ~7


CASS_DECODE = ('org.apache.cassandra.utils.memory.SlabPool', 'org.apache.cassandra.utils.memory.MemtablePool$SubPool',
               'org.apache.cassandra.utils.memory.SlabAllocator', 'org.apache.cassandra.utils.memory.MemtableAllocator$SubAllocator',
               'org.apache.cassandra.utils.memory.MemtableAllocator$LifeCycle')
ALWAYS = ('java.util.concurrent.atomic.AtomicInteger', 'java.util.concurrent.atomic.AtomicLong')
WANT = set()
LIFECYCLE = ['LIVE', 'DISCARDING', 'DISCARDED']


def main(path, decode_names=None):
    WANT.clear(); WANT.update(decode_names or CASS_DECODE); WANT.update(ALWAYS)
    f = open(path, 'rb')
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    end = mm.find(b'\0', 0, 64)
    hdr = mm[:end].decode()
    idsz = struct.unpack_from('>I', mm, end + 1)[0]
    SIZES[2] = idsz
    pos = end + 1 + 4 + 8
    n = len(mm)
    r = dict(header=hdr, id_size=idsz, region_arrays=0, region_bytes=0, near_region_arrays=0, byte_arrays=0, byte_array_bytes=0,
             instances=0, instance_bytes=0, obj_arrays=0, obj_array_bytes=0, prim_arrays=0, prim_array_bytes=0, classes=0, segments=0)
    unpack_I = struct.Struct('>I').unpack_from
    unpack_H = struct.Struct('>H').unpack_from
    ra = rb = nra = ba = bab = ins = insb = oa = oab = pa = pab = cl = 0
    strings, cls, frames, traces = {}, {}, {}, []
    cobj, hb, hn = {}, {}, {}
    cdump, keep, want_kind = {}, {}, {}

    def sv(i):
        a = strings.get(i)
        return mm[a[0]:a[1]].decode('utf-8', 'replace') if a else '?'

    fmt_id = '>Q' if idsz == 8 else '>I'
    uid = struct.Struct(fmt_id).unpack_from
    while pos < n:
        tag = mm[pos]
        length = unpack_I(mm, pos + 5)[0]
        body = pos + 9
        rend = body + length
        if tag == 0x01:  # STRING
            strings[uid(mm, body)[0]] = (body + idsz, rend)
        elif tag == 0x02:  # LOAD CLASS
            cls[unpack_I(mm, body)[0]] = uid(mm, body + 8 + idsz)[0]
            cobj[uid(mm, body + 4)[0]] = uid(mm, body + 8 + idsz)[0]
        elif tag == 0x04:  # STACK FRAME
            fid = uid(mm, body)[0]
            frames[fid] = (uid(mm, body + idsz)[0], unpack_I(mm, body + 4 * idsz)[0], struct.unpack_from('>i', mm, body + 4 * idsz + 4)[0])
        elif tag == 0x05:  # STACK TRACE
            nf = unpack_I(mm, body + 8)[0]
            traces.append((unpack_I(mm, body + 4)[0], [uid(mm, body + 12 + i * idsz)[0] for i in range(nf)]))
        elif tag in (0x0C, 0x1C):
            r['segments'] += 1
            p = body
            while p < rend:
                st = mm[p]; p += 1
                if st == 0x21:  # instance dump
                    nb = unpack_I(mm, p + idsz + 4 + idsz)[0]
                    k = ('I', uid(mm, p + idsz + 4)[0]); sz = a8(16 + nb)
                    kd = want_kind.get(k[1])
                    if kd is None:
                        kd = want_kind[k[1]] = (sv(cobj.get(k[1], 0)).replace('/', '.') in WANT)
                    if kd:
                        keep[uid(mm, p)[0]] = (k[1], p + idsz + 4 + idsz + 4, nb)
                    hb[k] = hb.get(k, 0) + sz; hn[k] = hn.get(k, 0) + 1
                    p += idsz + 4 + idsz + 4 + nb
                    ins += 1; insb += sz
                elif st == 0x23:  # primitive array
                    cnt = unpack_I(mm, p + idsz + 4)[0]
                    t = mm[p + idsz + 8]
                    nb = cnt * SIZES[t]
                    p += idsz + 9 + nb
                    pa += 1; sz = a8(16 + nb); pab += sz
                    k = ('P', t); hb[k] = hb.get(k, 0) + sz; hn[k] = hn.get(k, 0) + 1
                    if t == 8:
                        ba += 1; bab += sz
                        if cnt == REGION:
                            ra += 1; rb += 16 + REGION
                        elif REGION - 64 <= cnt < REGION:
                            nra += 1
                elif st == 0x22:  # object array
                    cnt = unpack_I(mm, p + idsz + 4)[0]
                    k = ('A', uid(mm, p + idsz + 8)[0]); sz = a8(16 + cnt * 4)
                    hb[k] = hb.get(k, 0) + sz; hn[k] = hn.get(k, 0) + 1
                    p += idsz + 4 + 4 + idsz + cnt * idsz
                    oa += 1; oab += sz
                elif st == 0x20:  # class dump
                    cl += 1
                    ccid = uid(mm, p)[0]; csup = uid(mm, p + idsz + 4)[0]
                    p += idsz + 4 + idsz * 6 + 4
                    cp = unpack_H(mm, p)[0]; p += 2
                    for _ in range(cp):
                        t = mm[p + 2]; p += 3 + SIZES[t]
                    sc = unpack_H(mm, p)[0]; p += 2
                    for _ in range(sc):
                        t = mm[p + idsz]; p += idsz + 1 + SIZES[t]
                    fc = unpack_H(mm, p)[0]; p += 2
                    flds = []
                    for _ in range(fc):
                        flds.append((uid(mm, p)[0], mm[p + idsz])); p += idsz + 1
                    cdump[ccid] = (csup, flds)
                elif st == 0xFF or st == 0x05 or st == 0x07:
                    p += idsz
                elif st == 0x01:
                    p += 2 * idsz
                elif st in (0x02, 0x03, 0x08):
                    p += idsz + 8
                elif st in (0x04, 0x06):
                    p += idsz + 4
                else:
                    raise SystemExit(f'unknown sub-record 0x{st:02x} at {p-1}')
        pos = rend
    r.update(region_arrays=ra, region_bytes=rb, near_region_arrays=nra, byte_arrays=ba, byte_array_bytes=bab, instances=ins,
             instance_bytes=insb, obj_arrays=oa, obj_array_bytes=oab, prim_arrays=pa, prim_array_bytes=pab, classes=cl,
             total_shallow_bytes=insb + oab + pab, file_bytes=n)

    def fr(fid):
        m, cs, line = frames.get(fid, (0, 0, 0))
        return f"{sv(cls.get(cs, 0)).rsplit('/', 1)[-1]}.{sv(m)}:{line}"
    PN = {4: '[Z', 5: '[C', 6: '[F', 7: '[D', 8: '[B', 9: '[S', 10: '[I', 11: '[J'}

    def kname(k):
        if k[0] == 'P':
            return PN.get(k[1], '[?')
        nm = sv(cobj.get(k[1], 0)).replace('/', '.')
        return nm  # object arrays: the array class name, e.g. [Ljava.lang.Object;
    rows = sorted(({'class': kname(k), 'bytes': b, 'count': hn[k]} for k, b in hb.items()), key=lambda x: -x['bytes'])
    r['classes_top'] = rows[:20]
    want = ('org.apache.cassandra.db.Mutation', 'org.apache.cassandra.db.partitions.PartitionUpdate',
            'org.apache.cassandra.db.rows.BufferCell', 'org.apache.cassandra.utils.memory.SlabAllocator$Region',
            'org.apache.cassandra.db.partitions.AtomicBTreePartition', 'org.apache.cassandra.db.memtable.SkipListMemtable',
            'org.apache.cassandra.db.rows.BTreeRow', 'java.nio.HeapByteBuffer', 'HoldRegions$Marker', 'org.apache.cassandra.utils.memory.SlabAllocator', 'org.apache.cassandra.utils.memory.MemtablePool$SubPool',
            'org.apache.cassandra.db.partitions.AtomicBTreePartition$B18Lock')
    r['classes_named'] = [x for x in rows if x['class'] in want]
    keys = ('SlabAllocator', 'MemtableAllocator', 'OutOfMemory')
    sel = []
    for ts, fids in traces:
        fs = [fr(f) for f in fids]
        if any(k in x for x in fs for k in keys):
            sel.append({'thread_serial': ts, 'frames': fs[:18]})
    r['traces_total'] = len(traces)
    r['slab_traces'] = len(sel)
    r['slab_trace_samples'] = sel[:4]
    FMT = {4: '>?', 5: '>H', 6: '>f', 7: '>d', 8: '>b', 9: '>h', 10: '>i', 11: '>q'}

    def decode(oid):
        if oid not in keep:
            return None
        cid, off, nb = keep[oid]
        out = {'_class': sv(cobj.get(cid, 0)).replace('/', '.')}
        refs = set()
        c = cid
        while c and c in cdump:
            sup, flds = cdump[c]
            for nid, t in flds:
                nm = sv(nid)
                if t == 2:
                    v = uid(mm, off)[0]; off += idsz
                else:
                    v = struct.unpack_from(FMT[t], mm, off)[0]; off += SIZES[t]
                if nm not in out:
                    out[nm] = v
                    if t == 2:
                        refs.add(nm)
            c = sup
        out['_refs'] = sorted(refs)
        return out

    def atomic(oid):
        d = decode(oid)
        return d.get('value') if d else None

    def deref(v):
        d = decode(v) if isinstance(v, int) and v else None
        if d and d['_class'] in ALWAYS:
            return d.get('value')
        if d and 'ordinal' in d:
            return {'enum': d['_class'], 'ordinal': d['ordinal']}
        return d
    r['decoded'] = {}
    if decode_names:
        for oid, (cid, _, _) in keep.items():
            nm = sv(cobj.get(cid, 0)).replace('/', '.')
            if nm in decode_names and nm not in ALWAYS:
                d = decode(oid)
                r['decoded'].setdefault(nm, []).append({k: (deref(v) if k in d['_refs'] and v else v)
                                                        for k, v in d.items() if k != '_refs'})
    else:
        pools, allocs = [], []
        for oid, (cid, _, _) in keep.items():
            nm = sv(cobj.get(cid, 0)).replace('/', '.')
            if nm == 'org.apache.cassandra.utils.memory.SlabPool':
                d = decode(oid)
                for side in ('onHeap', 'offHeap'):
                    sp = decode(d.get(side)) or {}
                    d[side] = {k: sp.get(k) for k in ('limit', 'allocated', 'reclaiming', 'nextClean', 'cleanThreshold')}
                pools.append({'onHeap': d['onHeap'], 'offHeap': d['offHeap'], 'allocateOnHeap': d.get('allocateOnHeap')})
            elif nm == 'org.apache.cassandra.utils.memory.SlabAllocator':
                d = decode(oid)
                sa = decode(d.get('onHeap')) or {}
                st = decode(sa.get('state')) or {}
                ordn = st.get('ordinal')
                allocs.append({'id': hex(oid), 'regionCount': atomic(d.get('regionCount')), 'unslabbed': atomic(d.get('unslabbedSize')),
                               'owns_onheap': sa.get('owns'), 'reclaiming_onheap': sa.get('reclaiming'),
                               'state': LIFECYCLE[ordn] if isinstance(ordn, int) and 0 <= ordn < 3 else ordn,
                               'allocateOnHeapOnly': d.get('allocateOnHeapOnly')})
        allocs.sort(key=lambda x: -(x['owns_onheap'] or 0))
        r['pool'] = pools[0]['onHeap'] if len(pools) == 1 else pools
        r['pools_n'] = len(pools)
        r['allocators'] = allocs[:30]
        r['allocators_n'] = len(allocs)
        r['allocators_owns_sum'] = sum(x['owns_onheap'] or 0 for x in allocs)
        r['allocators_regions_sum'] = sum(x['regionCount'] or 0 for x in allocs)
        r['allocators_by_state'] = {s: [sum(1 for x in allocs if x['state'] == s), sum(x['owns_onheap'] or 0 for x in allocs if x['state'] == s)]
                                    for s in set(x['state'] for x in allocs)}
    wt = 0
    for ts, fids in traces:
        fs = [fr(f) for f in fids]
        if any(x.startswith('Keyspace.applyInternal') or x.startswith('Mutation.apply') for x in fs):
            wt += 1
    r['writer_traces'] = wt
    print(json.dumps(r))


if __name__ == '__main__':
    a = sys.argv[1:]
    dn = None
    if len(a) == 3 and a[0] == '--decode':
        dn = a[1].split(','); a = a[2:]
    if len(a) != 1:
        raise SystemExit(__doc__)
    main(a[0], dn)
