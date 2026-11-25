#!/usr/bin/env python3
"""B25 stage-2 (design §2.5): R21's hprof_reach.py with the cut 'sampler' in place of 'updateF'/'tinypool'.
Builds the object graph of an HPROF dump (instance reference fields via CLASS DUMP layouts, including inherited fields with
their declaring class; object-array elements), takes as roots every GC-root record plus every class object and its static
reference fields, and counts the reachable byte[1048576] (slab regions) and reachable shallow bytes. Then repeats the traversal
with the cut edges, to measure what is reachable ONLY through them:
  cut 'sampler': the field 'queue' declared in org.apache.cassandra.metrics.MaxSampler, the field 'summary' declared in
                 org.apache.cassandra.metrics.FrequencySampler, and every reference out of an instance whose class name starts
                 with org.apache.cassandra.metrics.Sampler$$Lambda (queued insert tasks of samplerExecutor).
R_s = reachable regions - reachable regions with the cut. Also counts instances of org.apache.cassandra.metrics.Sampler$Sample
and com.clearspring.analytics.stream.Counter (K_s: the samplers' own entries), reachable ones too.
Prints one JSON object. usage: python3 -I hprof_reach.py <file.hprof>"""
import json, mmap, struct, sys
from array import array

SIZES = {2: None, 4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}
CUT_FIELDS = {('org.apache.cassandra.metrics.MaxSampler', 'queue'), ('org.apache.cassandra.metrics.FrequencySampler', 'summary')}
LAMBDA_PREFIX = 'org.apache.cassandra.metrics.Sampler$$Lambda'
COUNT_CLASSES = ('org.apache.cassandra.metrics.Sampler$Sample', 'com.clearspring.analytics.stream.Counter')


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
        """reference field offsets of an instance of cid: (offset, is_cut_field)"""
        if cid in layout:
            return layout[cid]
        out, off, c = [], 0, cid
        while c and c in cdump:
            sup, flds = cdump[c]
            decl = cn(c)
            for nid, t in flds:
                if t == 2:
                    out.append((off, (decl, sv(nid)) in CUT_FIELDS))
                off += SIZES[t]
            c = sup
        layout[cid] = out
        return out
    lambda_cls = set(c for c in cdump if cn(c).startswith(LAMBDA_PREFIX))
    count_cls = {c: cn(c) for c in cdump if cn(c) in COUNT_CLASSES}
    cut_field_hits = 0
    idx = {}
    size = array('q')
    isreg = bytearray()
    kind = bytearray()          # 1: sampler lambda (all out-edges cut), 2.. : counted class index + 2
    cls_index = {c: i for i, c in enumerate(COUNT_CLASSES)}
    edges_start = array('q')
    edges = array('q')
    ids = []
    for b, e in segs:
        p = b
        while p < e:
            st = mm[p]; p += 1
            if st == 0x21:
                oid = uid(mm, p)[0]; cid = uid(mm, p + idsz + 4)[0]; nb = uI(mm, p + idsz + 4 + idsz)[0]
                off = p + idsz + 4 + idsz + 4
                i = len(ids); idx[oid] = i; ids.append(oid)
                size.append(a8(16 + nb)); isreg.append(0)
                if cid in lambda_cls:
                    kind.append(1)
                elif cid in count_cls:
                    kind.append(2 + cls_index[count_cls[cid]])
                else:
                    kind.append(0)
                edges_start.append(len(edges))
                for o, cut in refoffs(cid):
                    v = uid(mm, off + o)[0]
                    if v:
                        if cut:
                            cut_field_hits += 1
                            edges.append(-v)
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
        regs = 0; byt = 0; cnts = [0] * len(COUNT_CLASSES)
        while stack:
            i = stack.pop()
            byt += size[i]
            if isreg[i]:
                regs += 1
            k = kind[i]
            if k >= 2:
                cnts[k - 2] += 1
            if cut and k == 1:
                continue
            for x in range(edges_start[i], edges_start[i + 1]):
                v = edges[x]
                if v < 0:
                    if cut:
                        continue
                    v = -v
                j = idx.get(v)
                if j is not None and not seen[j]:
                    seen[j] = 1
                    stack.append(j)
        return regs, byt, cnts
    res = {'file': path, 'objects': N, 'regions_in_dump': sum(isreg), 'shallow_bytes_in_dump': sum(size),
           'sampler_cut_field_refs': cut_field_hits, 'sampler_lambdas': sum(1 for k in kind if k == 1),
           'instances': {c: sum(1 for k in kind if k == 2 + i) for i, c in enumerate(COUNT_CLASSES)}}
    for cut in (False, True):
        r, b, cnts = traverse(cut)
        res['reachable_without_sampler' if cut else 'reachable'] = {
            'regions': r, 'region_MiB': round(r * 1048592 / 1048576, 1), 'shallow_MiB': round(b / 1048576, 1),
            'counted': {c: cnts[i] for i, c in enumerate(COUNT_CLASSES)}}
    res['R_s'] = res['reachable']['regions'] - res['reachable_without_sampler']['regions']
    res['R_s_MiB'] = round(res['R_s'] * 1048592 / 1048576, 1)
    res['only_via_sampler_shallow_MiB'] = round(res['reachable']['shallow_MiB'] - res['reachable_without_sampler']['shallow_MiB'], 1)
    print(json.dumps(res))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
