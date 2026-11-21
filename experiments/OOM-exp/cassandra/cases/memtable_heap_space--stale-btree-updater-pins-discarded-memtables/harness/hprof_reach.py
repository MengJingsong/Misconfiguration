#!/usr/bin/env python3
"""R21 stage-2 (design §2.5): R16's hprof_reach.py extended to print the object ids of the SlabAllocator instances reachable only
through the updateF cut (D; joined with hprof_scan.py's allocator ids by analyze.py), the number of SEPWorker instances, the number
of BTree$Updater instances and of those with a non-null updateF. Below, R16's text.
R16 stage-2 diagnostic (added 2026-11-20, amendment A2; offline on a kept dump, does not touch a run): reachability of the
slab regions. Builds the object graph of an HPROF dump (instance reference fields via CLASS DUMP layouts, object-array elements),
takes as roots every GC-root record plus every class object and its static reference fields, and counts the reachable
byte[1048576] (slab regions) and reachable shallow bytes. Then repeats the traversal with cut edges, to measure what is reachable
ONLY through them:
  cut 'updateF'  : the field updateF of org.apache.cassandra.utils.btree.BTree$Updater (the pooled updater's stale update function)
  cut 'tinypool' : every reference out of org.apache.cassandra.utils.caching.TinyThreadLocalPool$TinyPool (the thread-local pools)
Prints one JSON object. usage: python3 -I hprof_reach.py <file.hprof>"""
import json, mmap, struct, sys
from array import array

SIZES = {2: None, 4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}


def a8(n):
    return (n + 7) & ~7


def main(path):
    f = open(path, 'rb')
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    end = mm.find(b'\0', 0, 64)
    idsz = struct.unpack_from('>I', mm, end + 1)[0]
    SIZES[2] = idsz
    uid = struct.Struct('>Q' if idsz == 8 else '>I').unpack_from
    uI = struct.Struct('>I').unpack_from
    uH = struct.Struct('>H').unpack_from
    n = len(mm)
    strings, cobj, segs = {}, {}, []
    pos = end + 1 + 4 + 8
    while pos < n:
        tag = mm[pos]; length = uI(mm, pos + 5)[0]; body = pos + 9
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
    cdump, roots, statics = {}, [], {}
    # pass 1: class dumps and roots
    for b, e in segs:
        p = b
        while p < e:
            st = mm[p]; p += 1
            if st == 0x21:
                p += idsz + 4 + idsz + 4 + uI(mm, p + idsz + 4 + idsz)[0]
            elif st == 0x23:
                cnt = uI(mm, p + idsz + 4)[0]; t = mm[p + idsz + 8]; p += idsz + 9 + cnt * SIZES[t]
            elif st == 0x22:
                cnt = uI(mm, p + idsz + 4)[0]; p += idsz + 4 + 4 + idsz + cnt * idsz
            elif st == 0x20:
                ccid = uid(mm, p)[0]; csup = uid(mm, p + idsz + 4)[0]
                q = p + idsz + 4 + idsz * 6 + 4
                cp = uH(mm, q)[0]; q += 2
                for _ in range(cp):
                    t = mm[q + 2]; q += 3 + SIZES[t]
                sc = uH(mm, q)[0]; q += 2
                sr = []
                for _ in range(sc):
                    t = mm[q + idsz]
                    if t == 2:
                        sr.append(uid(mm, q + idsz + 1)[0])
                    q += idsz + 1 + SIZES[t]
                fc = uH(mm, q)[0]; q += 2
                flds = []
                for _ in range(fc):
                    flds.append((uid(mm, q)[0], mm[q + idsz])); q += idsz + 1
                cdump[ccid] = (csup, flds)
                statics[ccid] = sr
                p = q
            elif st in (0xFF, 0x05, 0x07):
                roots.append(uid(mm, p)[0]); p += idsz
            elif st == 0x01:
                roots.append(uid(mm, p)[0]); p += 2 * idsz
            elif st in (0x02, 0x03, 0x08):
                roots.append(uid(mm, p)[0]); p += idsz + 8
            elif st in (0x04, 0x06):
                roots.append(uid(mm, p)[0]); p += idsz + 4
            else:
                raise SystemExit(f'unknown sub-record 0x{st:02x}')
    cname = {}

    def cn(cid):
        if cid not in cname:
            cname[cid] = sv(cobj.get(cid, 0)).replace('/', '.')
        return cname[cid]
    layout = {}

    def refoffs(cid):
        if cid in layout:
            return layout[cid]
        out, off, c = [], 0, cid
        while c and c in cdump:
            sup, flds = cdump[c]
            for nid, t in flds:
                if t == 2:
                    out.append((off, sv(nid)))
                off += SIZES[t]
            c = sup
        layout[cid] = out
        return out
    upd_cls = [c for c in cdump if cn(c) == 'org.apache.cassandra.utils.btree.BTree$Updater']
    pool_cls = set(c for c in cdump if cn(c) == 'org.apache.cassandra.utils.caching.TinyThreadLocalPool$TinyPool')
    slab_cls = set(c for c in cdump if cn(c) == 'org.apache.cassandra.utils.memory.SlabAllocator')
    sep_cls = set(c for c in cdump if cn(c) == 'org.apache.cassandra.concurrent.SEPWorker')
    updset = set(upd_cls)
    slab_idx, n_sep, n_upd = [], 0, 0
    # pass 2: graph
    idx = {}          # object id -> index
    size = array('q')
    isreg = bytearray()
    kind = array('b')  # 0 normal, 1 tinypool
    edges_start = array('q')
    edges = array('q')    # child object ids (resolved later)
    cutF = []          # (parent index, child id) for BTree$Updater.updateF
    ids = []
    for b, e in segs:
        p = b
        while p < e:
            st = mm[p]; p += 1
            if st == 0x21:
                oid = uid(mm, p)[0]; cid = uid(mm, p + idsz + 4)[0]; nb = uI(mm, p + idsz + 4 + idsz)[0]
                off = p + idsz + 4 + idsz + 4
                i = len(ids); idx[oid] = i; ids.append(oid)
                size.append(a8(16 + nb)); isreg.append(0); kind.append(1 if cid in pool_cls else 0)
                if cid in slab_cls:
                    slab_idx.append(i)
                elif cid in sep_cls:
                    n_sep += 1
                elif cid in updset:
                    n_upd += 1
                edges_start.append(len(edges))
                for o, nm in refoffs(cid):
                    v = uid(mm, off + o)[0]
                    if v:
                        if nm == 'updateF' and cid in upd_cls:
                            cutF.append((i, v))
                            edges.append(-v)   # marked: an updateF edge
                        else:
                            edges.append(v)
                p = off + nb
            elif st == 0x23:
                oid = uid(mm, p)[0]; cnt = uI(mm, p + idsz + 4)[0]; t = mm[p + idsz + 8]
                i = len(ids); idx[oid] = i; ids.append(oid)
                size.append(a8(16 + cnt * SIZES[t])); isreg.append(1 if (t == 8 and cnt == 1048576) else 0); kind.append(0)
                edges_start.append(len(edges))
                p += idsz + 9 + cnt * SIZES[t]
            elif st == 0x22:
                oid = uid(mm, p)[0]; cnt = uI(mm, p + idsz + 4)[0]
                off = p + idsz + 4 + 4 + idsz
                i = len(ids); idx[oid] = i; ids.append(oid)
                size.append(a8(16 + cnt * 4)); isreg.append(0); kind.append(0)
                edges_start.append(len(edges))
                for k in range(cnt):
                    v = uid(mm, off + k * idsz)[0]
                    if v:
                        edges.append(v)
                p = off + cnt * idsz
            elif st == 0x20:
                q = p + idsz + 4 + idsz * 6 + 4
                cp = uH(mm, q)[0]; q += 2
                for _ in range(cp):
                    t = mm[q + 2]; q += 3 + SIZES[t]
                sc = uH(mm, q)[0]; q += 2
                for _ in range(sc):
                    t = mm[q + idsz]; q += idsz + 1 + SIZES[t]
                fc = uH(mm, q)[0]; q += 2 + fc * (idsz + 1)
                p = q
            elif st in (0xFF, 0x05, 0x07):
                p += idsz
            elif st == 0x01:
                p += 2 * idsz
            elif st in (0x02, 0x03, 0x08):
                p += idsz + 8
            elif st in (0x04, 0x06):
                p += idsz + 4
    edges_start.append(len(edges))
    N = len(ids)
    start_ids = list(roots) + list(cdump.keys()) + [v for sr in statics.values() for v in sr]

    def traverse(cut):
        seen = bytearray(N)
        stack = [idx[r] for r in start_ids if r in idx]
        for s in stack:
            seen[s] = 1
        regs = 0; byt = 0
        while stack:
            i = stack.pop()
            byt += size[i]
            if isreg[i]:
                regs += 1
            if cut == 'tinypool' and kind[i] == 1:
                continue
            for k in range(edges_start[i], edges_start[i + 1]):
                v = edges[k]
                if v < 0:
                    if cut == 'updateF':
                        continue
                    v = -v
                j = idx.get(v)
                if j is not None and not seen[j]:
                    seen[j] = 1
                    stack.append(j)
        return regs, byt, seen
    tot_regs = sum(isreg)
    res = {'file': path, 'objects': N, 'regions_in_dump': tot_regs, 'shallow_bytes_in_dump': sum(size),
           'btree_updaters_with_updateF': len(cutF), 'btree_updaters': n_upd, 'sep_workers': n_sep,
           'slab_allocators': len(slab_idx), 'tinypools': sum(1 for k in kind if k == 1)}
    seen_by = {}
    for cut in (None, 'updateF', 'tinypool'):
        r, b, seen = traverse(cut)
        seen_by[cut] = seen
        res['reachable' if cut is None else 'reachable_without_' + cut] = {'regions': r, 'region_MiB': round(r * 1048592 / 1048576, 1),
                                                                            'shallow_MiB': round(b / 1048576, 1)}
    res['regions_only_via_updateF'] = res['reachable']['regions'] - res['reachable_without_updateF']['regions']
    res['regions_only_via_tinypool'] = res['reachable']['regions'] - res['reachable_without_tinypool']['regions']
    a0, a1 = seen_by[None], seen_by['updateF']
    res['slab_allocators_reachable'] = sum(1 for i in slab_idx if a0[i])
    res['slab_allocators_only_via_updateF'] = [hex(ids[i]) for i in slab_idx if a0[i] and not a1[i]]
    print(json.dumps(res))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
