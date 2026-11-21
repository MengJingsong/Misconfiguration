#!/usr/bin/env python3
"""R16 stage-2 diagnostic (added 2026-11-20 after H2-T-1, amendment A2; offline on a kept OOM dump, does not touch a run):
who keeps the memtables reachable? Pass 0: class dumps (instance field layouts), every memtable instance (class name ending in
'Memtable', e.g. SkipListMemtable), its `allocator` -> SlabAllocator -> on-heap SubAllocator (owns, state ordinal), and the
`byte[1048576]` count. Then up to <depth> backward passes: for the current target id set, every instance field / object-array
element / GC root that points at a target is recorded (referrer class, field, referrer id); the referrers become the next targets
(classes in the stop list are not expanded). Prints one JSON object: memtables (id, class, owns, state, regionCount) and per level
the referrer edges grouped by (referrer class, field, target class), with up to 5 example ids.
With a third argument `discarded`, the start set is instead every SlabAllocator whose on-heap SubAllocator is DISCARDED (what still
references the allocators of flushed memtables).
usage: python3 -I hprof_refs.py <file.hprof> [depth] [discarded]"""
import json, mmap, struct, sys

SIZES = {2: None, 4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}
FMT = {4: '>?', 5: '>H', 6: '>f', 7: '>d', 8: '>b', 9: '>h', 10: '>i', 11: '>q'}
LIFECYCLE = ['LIVE', 'DISCARDING', 'DISCARDED']
STOP = ('java.lang.Class', 'java.lang.Thread')


def main(path, depth, mode='memtables'):
    f = open(path, 'rb')
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    end = mm.find(b'\0', 0, 64)
    idsz = struct.unpack_from('>I', mm, end + 1)[0]
    SIZES[2] = idsz
    uid = struct.Struct('>Q' if idsz == 8 else '>I').unpack_from
    uI = struct.Struct('>I').unpack_from
    uH = struct.Struct('>H').unpack_from
    start = end + 1 + 4 + 8
    n = len(mm)
    strings, cobj, cdump = {}, {}, {}
    segs = []
    pos = start
    while pos < n:
        tag = mm[pos]
        length = uI(mm, pos + 5)[0]
        body = pos + 9
        if tag == 0x01:
            strings[uid(mm, body)[0]] = (body + idsz, body + length)
        elif tag == 0x02:
            cobj[uid(mm, body + 4)[0]] = uid(mm, body + 8 + idsz)[0]
        elif tag in (0x0C, 0x1C):
            segs.append((body, body + length))
        pos = body + length

    def sv(i):
        a = strings.get(i)
        return mm[a[0]:a[1]].decode('utf-8', 'replace') if a else '?'
    cname = {}

    def cn(cid):
        if cid not in cname:
            cname[cid] = sv(cobj.get(cid, 0)).replace('/', '.')
        return cname[cid]

    def walk(cb_inst, cb_arr, cb_root, cb_class):
        for b, e in segs:
            p = b
            while p < e:
                st = mm[p]; p += 1
                if st == 0x21:
                    oid = uid(mm, p)[0]; cid = uid(mm, p + idsz + 4)[0]; nb = uI(mm, p + idsz + 4 + idsz)[0]
                    off = p + idsz + 4 + idsz + 4
                    if cb_inst:
                        cb_inst(oid, cid, off, nb)
                    p = off + nb
                elif st == 0x23:
                    cnt = uI(mm, p + idsz + 4)[0]; t = mm[p + idsz + 8]
                    if cb_arr and t == 8 and cnt == 1048576:
                        cb_arr('region', uid(mm, p)[0], None, None, None)
                    p += idsz + 9 + cnt * SIZES[t]
                elif st == 0x22:
                    oid = uid(mm, p)[0]; cnt = uI(mm, p + idsz + 4)[0]; acid = uid(mm, p + idsz + 8)[0]
                    off = p + idsz + 4 + 4 + idsz
                    if cb_arr:
                        cb_arr('objarr', oid, acid, off, cnt)
                    p = off + cnt * idsz
                elif st == 0x20:
                    ccid = uid(mm, p)[0]; csup = uid(mm, p + idsz + 4)[0]
                    q = p + idsz + 4 + idsz * 6 + 4
                    cp = uH(mm, q)[0]; q += 2
                    for _ in range(cp):
                        t = mm[q + 2]; q += 3 + SIZES[t]
                    sc = uH(mm, q)[0]; q += 2
                    sref = []
                    for _ in range(sc):
                        t = mm[q + idsz]
                        if t == 2:
                            sref.append((sv(uid(mm, q)[0]), uid(mm, q + idsz + 1)[0]))
                        q += idsz + 1 + SIZES[t]
                    fc = uH(mm, q)[0]; q += 2
                    flds = []
                    for _ in range(fc):
                        flds.append((uid(mm, q)[0], mm[q + idsz])); q += idsz + 1
                    if cb_class:
                        cb_class(ccid, csup, flds, sref)
                    p = q
                elif st in (0xFF, 0x05, 0x07):
                    if cb_root:
                        cb_root(st, uid(mm, p)[0], None)
                    p += idsz
                elif st == 0x01:
                    if cb_root:
                        cb_root(st, uid(mm, p)[0], None)
                    p += 2 * idsz
                elif st in (0x02, 0x03, 0x08):
                    if cb_root:
                        cb_root(st, uid(mm, p)[0], uI(mm, p + idsz)[0])
                    p += idsz + 8
                elif st in (0x04, 0x06):
                    if cb_root:
                        cb_root(st, uid(mm, p)[0], uI(mm, p + idsz)[0])
                    p += idsz + 4
                else:
                    raise SystemExit(f'unknown sub-record 0x{st:02x}')
    statics = {}

    def on_class(ccid, csup, flds, sref):
        cdump[ccid] = (csup, flds)
        statics[ccid] = sref
    walk(None, None, None, on_class)
    layout = {}

    def lay(cid):
        if cid in layout:
            return layout[cid]
        out, off, c = [], 0, cid
        while c and c in cdump:
            sup, flds = cdump[c]
            for nid, t in flds:
                out.append((off, t, sv(nid)))
                off += SIZES[t]
            c = sup
        layout[cid] = out
        return out

    def decode(off, cid):
        d = {}
        for o, t, nm in lay(cid):
            if nm in d:
                continue
            d[nm] = uid(mm, off + o)[0] if t == 2 else struct.unpack_from(FMT[t], mm, off + o)[0]
        return d
    # pass 0: memtables and the objects needed to decode their allocator state
    keep, mts = {}, []
    regions = [0]

    def p0(oid, cid, off, nb):
        nm = cn(cid)
        if nm.endswith('Memtable') and nm.startswith('org.apache.cassandra'):
            mts.append(oid)
        if nm in ('org.apache.cassandra.utils.memory.SlabAllocator', 'org.apache.cassandra.utils.memory.MemtableAllocator$SubAllocator',
                  'org.apache.cassandra.utils.memory.MemtableAllocator$LifeCycle', 'java.util.concurrent.atomic.AtomicInteger') \
                or (nm.endswith('Memtable') and nm.startswith('org.apache.cassandra')) or nm == 'org.apache.cassandra.schema.TableMetadataRef' \
                or nm == 'org.apache.cassandra.schema.TableMetadata':
            keep[oid] = (cid, off)

    def p0a(kind, oid, acid, off, cnt):
        if kind == 'region':
            regions[0] += 1
    walk(p0, p0a, None, None)

    def dec(oid):
        if oid not in keep:
            return {}
        cid, off = keep[oid]
        d = decode(off, cid)
        d['_class'] = cn(cid)
        return d
    memt = []
    for m in mts:
        d = dec(m)
        a = dec(d.get('allocator'))
        sa = dec(a.get('onHeap'))
        stv = dec(sa.get('state')).get('ordinal')
        rc = dec(a.get('regionCount')).get('value')
        md = dec(d.get('metadata'))
        tm = dec(md.get('get') or md.get('metadata') or 0) if md else {}
        memt.append({'id': hex(m), 'class': d['_class'], 'owns': sa.get('owns'), 'state': LIFECYCLE[stv] if isinstance(stv, int) and 0 <= stv < 3 else stv,
                     'regionCount': rc})
    res = {'file': path, 'region_arrays': regions[0], 'memtables': memt, 'levels': [], 'mode': mode}
    targets = set(mts)
    tclass = {m: cn(keep[m][0]) for m in mts}
    if mode == 'discarded':
        targets, tclass, dl = set(), {}, []
        for oid, (cid, off) in keep.items():
            if cn(cid) == 'org.apache.cassandra.utils.memory.SlabAllocator':
                a = dec(oid)
                stv = dec(dec(a.get('onHeap')).get('state')).get('ordinal')
                if stv == 2:
                    targets.add(oid); tclass[oid] = 'SlabAllocator(DISCARDED)'
                    dl.append({'id': hex(oid), 'regionCount': dec(a.get('regionCount')).get('value')})
        res['discarded_allocators'] = dl
    seen = set(targets)
    for lvl in range(depth):
        edges, nxt = {}, {}

        def add(rc, field, tid, rid):
            k = (rc, field, tclass.get(tid, '?'))
            e = edges.setdefault(k, [0, []])
            e[0] += 1
            if len(e[1]) < 5:
                e[1].append([hex(rid) if isinstance(rid, int) else rid, hex(tid)])

        def pi(oid, cid, off, nb):
            for o, t, nm in lay(cid):
                if t == 2:
                    v = uid(mm, off + o)[0]
                    if v in targets:
                        rc = cn(cid)
                        add(rc, nm, v, oid)
                        if oid not in seen and rc not in STOP:
                            nxt[oid] = rc

        def pa(kind, oid, acid, off, cnt):
            if kind != 'objarr':
                return
            for i in range(cnt):
                v = uid(mm, off + i * idsz)[0]
                if v in targets:
                    rc = cn(acid) + '[]'
                    add(rc, '[i]', v, oid)
                    if oid not in seen:
                        nxt[oid] = rc

        def pr(st, oid, ser):
            if oid in targets:
                add(f'ROOT 0x{st:02x}', f'thread_serial={ser}', oid, f'root:{ser}')
        walk(pi, pa, pr, None)
        for cid, sref in statics.items():
            for nm, v in sref:
                if v in targets:
                    add('STATIC ' + cn(cid), nm, v, cid)
        res['levels'].append(sorted(([k[0], k[1], k[2], v[0], v[1]] for k, v in edges.items()), key=lambda x: -x[3]))
        if not nxt:
            break
        targets = set(nxt)
        tclass = dict(nxt)
        seen |= targets
        if len(targets) > 200000:
            res['truncated_at_level'] = lvl + 1
            break
    print(json.dumps(res))


if __name__ == '__main__':
    if len(sys.argv) not in (2, 3, 4):
        raise SystemExit(__doc__)
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) >= 3 else 4, sys.argv[3] if len(sys.argv) == 4 else 'memtables')
