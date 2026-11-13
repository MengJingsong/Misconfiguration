#!/usr/bin/env python3
"""OOM-exp R2 (2026-11-11; copied for C3 2026-11-12 with a configurable large-buffer threshold): minimal HPROF reader for direct-buffer attribution.

Usage: python3 -I hprof_direct.py <dump.hprof> [topN]

Output:
  1. class histogram (instances + arrays): count, shallow bytes (instance field bytes + 16 B header
     estimate; arrays: elements + 16 B), top N by bytes; plus the rows for DirectByteBuffer, HintsBuffer,
     DataOutputBuffer classes.
  2. java.nio.DirectByteBuffer: memory owners (cleaner != null, att == null) vs views (slices/duplicates);
     sum of owner capacities.
  3. owners grouped by holder: the object(s) that strongly reference each owner (Reference.referent is
     ignored; a view's referrers are attributed to its owner via att). HintsBuffer.slab = hints slab;
     DataOutputBuffer$1$1.buffer = DOB thread-local scratch (mapped to its thread through
     InternalThreadLocalMap.indexedVariables and FastThreadLocalThread.threadLocalMap); no referrer =
     unreferenced, still charged to Bits until its Cleaner runs.
No reachability from GC roots is computed (the OOM dump is not preceded by a GC); holders are direct
referrers.
"""
import mmap, os, struct, sys
# C3 (2026-11-12): threshold for the 'large' scratch-buffer state table, env HPROF_LARGE (default 1 MiB as in R2)
LARGE = int(os.environ.get('HPROF_LARGE', '1048576'))
from collections import defaultdict

BT_SIZE = {2: None, 4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}


def main():
    path = sys.argv[1]
    topn = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    f = open(path, 'rb')
    m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    hdr_end = m.find(b'\0') + 1
    idsz = struct.unpack_from('>I', m, hdr_end)[0]
    assert idsz == 8, idsz
    BT_SIZE[2] = idsz
    start = hdr_end + 4 + 8
    Q = struct.Struct('>Q').unpack_from
    I = struct.Struct('>I').unpack_from
    H = struct.Struct('>H').unpack_from

    strings = {}
    cls_name = {}       # class obj id -> name
    cls_super = {}
    cls_fields = {}     # class id -> [(name, type)] declared instance fields
    cls_isize = {}

    def records():
        p = start
        n = len(m)
        while p < n:
            tag = m[p]; ln = I(m, p + 5)[0]
            yield tag, p + 9, ln
            p += 9 + ln

    def subrecords(p, end):
        """yield (subtag, pos_of_body, body_end) for heap dump sub-records"""
        while p < end:
            st = m[p]; p += 1
            b = p
            if st == 0xFF: p += idsz
            elif st == 0x01: p += 2 * idsz
            elif st == 0x02: p += idsz + 8
            elif st == 0x03: p += idsz + 8
            elif st == 0x04: p += idsz + 4
            elif st == 0x05: p += idsz
            elif st == 0x06: p += idsz + 4
            elif st == 0x07: p += idsz
            elif st == 0x08: p += idsz + 8
            elif st == 0x20:
                q = p + idsz + 4 + 6 * idsz + 4
                ncp = H(m, q)[0]; q += 2
                for _ in range(ncp):
                    t = m[q + 2]; q += 3 + BT_SIZE[t]
                nst = H(m, q)[0]; q += 2
                for _ in range(nst):
                    t = m[q + idsz]; q += idsz + 1 + BT_SIZE[t]
                nif = H(m, q)[0]; q += 2
                q += nif * (idsz + 1)
                p = q
            elif st == 0x21:
                nb = I(m, p + idsz + 4 + idsz)[0]
                p += idsz + 4 + idsz + 4 + nb
            elif st == 0x22:
                ne = I(m, p + idsz + 4)[0]
                p += idsz + 4 + 4 + idsz + ne * idsz
            elif st == 0x23:
                ne = I(m, p + idsz + 4)[0]; t = m[p + idsz + 8]
                p += idsz + 4 + 4 + 1 + ne * BT_SIZE[t]
            else:
                raise ValueError('unknown subtag %#x at %d' % (st, b - 1))
            yield st, b, p

    # ---- pass 1: strings, class names, class dumps
    for tag, p, ln in records():
        if tag == 0x01:
            strings[Q(m, p)[0]] = m[p + idsz:p + ln].decode('utf-8', 'replace')
        elif tag == 0x02:
            cid = Q(m, p + 4)[0]; nid = Q(m, p + 4 + idsz + 4)[0]
            cls_name[cid] = nid
        elif tag in (0x0C, 0x1C):
            for st, b, e in subrecords(p, p + ln):
                if st != 0x20: continue
                cid = Q(m, b)[0]
                sup = Q(m, b + idsz + 4)[0]
                q = b + idsz + 4 + 6 * idsz
                cls_isize[cid] = I(m, q)[0]; q += 4
                ncp = H(m, q)[0]; q += 2
                for _ in range(ncp):
                    t = m[q + 2]; q += 3 + BT_SIZE[t]
                nst = H(m, q)[0]; q += 2
                for _ in range(nst):
                    t = m[q + idsz]; q += idsz + 1 + BT_SIZE[t]
                nif = H(m, q)[0]; q += 2
                fl = []
                for _ in range(nif):
                    fl.append((strings.get(Q(m, q)[0], '?'), m[q + idsz])); q += idsz + 1
                cls_super[cid] = sup; cls_fields[cid] = fl
    name = {c: strings.get(n, '?').replace('/', '.') for c, n in cls_name.items()}

    layout = {}   # cid -> list of (offset, fieldname, declaring class name, type) all fields

    def get_layout(cid):
        if cid in layout: return layout[cid]
        out = []; off = 0; c = cid
        while c and c in cls_fields:
            for fn, t in cls_fields[c]:
                out.append((off, fn, name.get(c, '?'), t)); off += BT_SIZE[t]
            c = cls_super.get(c, 0)
        layout[cid] = out
        return out

    def is_sub(cid, target):
        c = cid
        while c:
            if name.get(c) == target: return True
            c = cls_super.get(c, 0)
        return False

    objoffs = {}

    def obj_offsets(cid):
        if cid not in objoffs:
            objoffs[cid] = [(o, fn, dc) for (o, fn, dc, t) in get_layout(cid) if t == 2]
        return objoffs[cid]

    def fields(cid, b):
        """decode instance fields of an instance whose field bytes start at b"""
        d = {}
        for o, fn, dc, t in get_layout(cid):
            q = b + o
            if t == 2: v = Q(m, q)[0]
            elif t == 10: v = struct.unpack_from('>i', m, q)[0]
            elif t == 11: v = struct.unpack_from('>q', m, q)[0]
            elif t in (4, 8): v = m[q]
            else: v = None
            d.setdefault(fn, v)   # first = most derived
            d[dc + '.' + fn] = v
        return d

    want = {}
    for c, n in name.items():
        if n == 'java.nio.DirectByteBuffer': want[c] = 'dbb'
        elif n == 'org.apache.cassandra.hints.HintsBuffer': want[c] = 'hb'
        elif n.startswith('org.apache.cassandra.io.util.DataOutputBuffer'): want[c] = 'dob'
        elif n == 'io.netty.util.internal.InternalThreadLocalMap': want[c] = 'itlm'
        elif is_sub(c, 'java.lang.Thread'): want[c] = 'thr'

    # ---- pass 2: histogram + target instances
    histo = defaultdict(lambda: [0, 0])
    inst = {k: {} for k in ('dbb', 'hb', 'dob', 'itlm', 'thr')}
    for tag, p, ln in records():
        if tag not in (0x0C, 0x1C): continue
        for st, b, e in subrecords(p, p + ln):
            if st == 0x21:
                oid = Q(m, b)[0]; cid = Q(m, b + idsz + 4)[0]; nb = I(m, b + 2 * idsz + 4)[0]
                h = histo[cid]; h[0] += 1; h[1] += nb + 16
                k = want.get(cid)
                if k: inst[k][oid] = (cid, fields(cid, b + 2 * idsz + 8))
            elif st == 0x22:
                ne = I(m, b + idsz + 4)[0]; acid = Q(m, b + idsz + 8)[0]
                h = histo[('objarr', acid)]; h[0] += 1; h[1] += ne * idsz + 16
            elif st == 0x23:
                ne = I(m, b + idsz + 4)[0]; t = m[b + idsz + 8]
                h = histo[('primarr', t)]; h[0] += 1; h[1] += ne * BT_SIZE[t] + 16

    PRIM = {4: 'boolean[]', 5: 'char[]', 6: 'float[]', 7: 'double[]', 8: 'byte[]', 9: 'short[]', 10: 'int[]', 11: 'long[]'}

    def hname(k):
        if isinstance(k, tuple):
            return PRIM[k[1]] if k[0] == 'primarr' else name.get(k[1], '?')
        return name.get(k, '?')

    print('== class histogram (top %d by shallow bytes; header estimate 16 B) ==' % topn)
    rows = sorted(histo.items(), key=lambda kv: -kv[1][1])
    tot = sum(v[1] for v in histo.values()); totn = sum(v[0] for v in histo.values())
    print('total objects %d, shallow %.1f MiB' % (totn, tot / 2**20))
    print('%5s %12s %14s  %s' % ('rank', 'count', 'bytes', 'class'))
    for i, (k, v) in enumerate(rows[:topn]):
        print('%5d %12d %14d  %s' % (i + 1, v[0], v[1], hname(k)))
    print('-- selected rows --')
    for i, (k, v) in enumerate(rows):
        n = hname(k)
        if n in ('java.nio.DirectByteBuffer', 'org.apache.cassandra.hints.HintsBuffer') or n.startswith('org.apache.cassandra.io.util.DataOutputBuffer'):
            print('%5d %12d %14d  %s' % (i + 1, v[0], v[1], n))

    dbb = inst['dbb']
    # memory owners charged to Bits (MaxDirectMemorySize): allocateDirect buffers (cleaner set, no att, no fd).
    # File mappings (MappedByteBuffer: fd set) also carry a cleaner but are not charged to Bits.
    mapped = {o: d for o, (c, d) in dbb.items() if d.get('cleaner') and not d.get('att') and d.get('fd')}
    owners = {o: d for o, (c, d) in dbb.items() if d.get('cleaner') and not d.get('att') and not d.get('fd')}
    views = {o: d for o, (c, d) in dbb.items() if o not in owners and o not in mapped}
    cap = lambda d: d.get('java.nio.Buffer.capacity', d.get('capacity', 0))
    print('\n== java.nio.DirectByteBuffer ==')
    print('instances %d; memory owners charged to Bits (cleaner!=null, att==null, fd==null) %d, capacity sum %d B = %.1f MiB; views %d (capacity sum %.1f MiB, not memory)'
          % (len(dbb), len(owners), sum(cap(d) for d in owners.values()), sum(cap(d) for d in owners.values()) / 2**20,
             len(views), sum(cap(d) for d in views.values()) / 2**20))
    print('file mappings (MappedByteBuffer, fd!=null; not charged to MaxDirectMemorySize): %d, capacity sum %.1f MiB'
          % (len(mapped), sum(cap(d) for d in mapped.values()) / 2**20))

    # ---- pass 3: reverse references to owners, views (for att), DOB instances, ITLM index arrays
    def view_root(o):
        seen = 0
        while o in views and views[o].get('att') in dbb and seen < 8:
            o = views[o]['att']; seen += 1
        return o
    targets = set(dbb) | set(inst['dob'])
    refs = defaultdict(list)    # target -> [(referrer id, referrer class name, field)]
    arrays_needed = {d.get('indexedVariables') for c, d in inst['itlm'].values()}
    arr_elems = {}
    for tag, p, ln in records():
        if tag not in (0x0C, 0x1C): continue
        for st, b, e in subrecords(p, p + ln):
            if st == 0x21:
                oid = Q(m, b)[0]; cid = Q(m, b + idsz + 4)[0]; fb = b + 2 * idsz + 8
                for o, fn, dc in obj_offsets(cid):
                    v = Q(m, fb + o)[0]
                    if v in targets:
                        if fn == 'referent' and dc == 'java.lang.ref.Reference':
                            continue
                        refs[v].append((oid, name.get(cid, '?'), dc.rsplit('.', 1)[-1] + '.' + fn))
            elif st == 0x22:
                oid = Q(m, b)[0]; ne = I(m, b + idsz + 4)[0]
                if ne == 0: continue
                els = struct.unpack_from('>%dQ' % ne, m, b + idsz + 8 + idsz)
                hit = targets.intersection(els)
                if oid in arrays_needed:
                    arr_elems[oid] = els
                if hit:
                    acid = Q(m, b + idsz + 8)[0]
                    for v in hit:
                        refs[v].append((oid, name.get(acid, '?') + '(array)', '[]'))

    # thread names: need String -> value byte[]; collect in pass 4
    itlm_by_arr = {d.get('indexedVariables'): oid for oid, (c, d) in inst['itlm'].items()}
    thr_by_itlm = {}
    for oid, (c, d) in inst['thr'].items():
        t = d.get('threadLocalMap')
        if t: thr_by_itlm[t] = oid
    dob_thread = {}
    for arr, els in arr_elems.items():
        it = itlm_by_arr.get(arr); th = thr_by_itlm.get(it)
        for v in els:
            if v in inst['dob']:
                dob_thread[v] = th
    name_str = {oid: d.get('java.lang.Thread.name') for oid, (c, d) in inst['thr'].items()}
    need_str = set(x for x in name_str.values() if x)
    str_val = {}; val_bytes = {}
    for tag, p, ln in records():
        if tag not in (0x0C, 0x1C): continue
        for st, b, e in subrecords(p, p + ln):
            if st == 0x21:
                oid = Q(m, b)[0]
                if oid in need_str:
                    cid = Q(m, b + idsz + 4)[0]; d = fields(cid, b + 2 * idsz + 8)
                    str_val[oid] = d.get('value')
    need_val = set(str_val.values())
    for tag, p, ln in records():
        if tag not in (0x0C, 0x1C): continue
        for st, b, e in subrecords(p, p + ln):
            if st == 0x23:
                oid = Q(m, b)[0]
                if oid in need_val:
                    ne = I(m, b + idsz + 4)[0]; t = m[b + idsz + 8]
                    raw = m[b + idsz + 9:b + idsz + 9 + ne * BT_SIZE[t]]
                    val_bytes[oid] = raw.decode('latin-1') if t == 8 else raw.decode('utf-16-be', 'replace')

    def tname(th):
        if not th: return '?'
        s = name_str.get(th); return val_bytes.get(str_val.get(s), '?')

    # attribute owners
    owner_refs = defaultdict(list)
    for t, rl in refs.items():
        if t in dbb:
            for r in rl:
                if r[1] == 'java.nio.DirectByteBuffer' and r[2].endswith('.att'):
                    continue   # a view pointing to its parent: not a holder
                owner_refs[view_root(t)].append(r)
    groups = defaultdict(lambda: [0, 0, []])
    for o, d in owners.items():
        rl = owner_refs.get(o, [])
        kinds = set()
        for rid, rc, fld in rl:
            if rc == 'org.apache.cassandra.hints.HintsBuffer':
                kinds.add('HintsBuffer.slab (hints pool slab)')
            elif rc.startswith('org.apache.cassandra.io.util.DataOutputBuffer$1'):
                kinds.add('DataOutputBuffer$1$1.buffer (DOB thread-local scratch)')
            elif rc.startswith('org.apache.cassandra.io.util.DataOutputBuffer'):
                kinds.add('%s.buffer (non-scratch DOB)' % rc)
            elif rc == 'jdk.internal.ref.Cleaner' or rc == 'java.nio.DirectByteBuffer$Deallocator':
                continue
            else:
                kinds.add('%s %s' % (rc, fld))
        k = ' + '.join(sorted(kinds)) if kinds else '(no strong referrer: dropped, awaiting Cleaner)'
        g = groups[k]; g[0] += 1; g[1] += cap(d); g[2].append((o, cap(d), rl))
    print('\n== direct memory owners by holder (capacity) ==')
    print('%6s %14s %9s  %s' % ('count', 'bytes', 'MiB', 'holder'))
    for k, (n, s, _) in sorted(groups.items(), key=lambda kv: -kv[1][1]):
        print('%6d %14d %9.1f  %s' % (n, s, s / 2**20, k))
    # detail: DOB scratch per thread, hints slabs
    for k, (n, s, lst) in groups.items():
        if 'DOB thread-local scratch' in k:
            print('\n-- DOB scratch buffers by thread (capacity) --')
            byth = defaultdict(list)
            for o, c, rl in lst:
                dob = [rid for rid, rc, fld in rl if rc.startswith('org.apache.cassandra.io.util.DataOutputBuffer$1')]
                th = dob_thread.get(dob[0]) if dob else None
                byth[tname(th)].append(c)
            # idle (closed: buffer.clear() -> position 0) vs in use (position > 0), for the large buffers
            st = defaultdict(lambda: [0, 0, defaultdict(int)])
            for o, c, rl in lst:
                if c < LARGE: continue
                d = owners[o]; pos = d.get('java.nio.Buffer.position', d.get('position', 0))
                dob = [rid for rid, rc, fld in rl if rc.startswith('org.apache.cassandra.io.util.DataOutputBuffer$1')]
                tn = tname(dob_thread.get(dob[0]) if dob else None)
                key = ('idle (position 0)' if pos == 0 else 'in use (position > 0)', c)
                st[key][0] += 1; st[key][1] += c; st[key][2][tn.rsplit('-', 1)[0] if '-' in tn else tn] += 1
            print('  large (>= %d B) scratch buffers by state:' % LARGE)
            for (state, c), (n, b, pools) in sorted(st.items()):
                print('    %-24s capacity %9d B x %3d = %6.1f MiB  threads: %s' % (state, c, n, b / 2**20, dict(pools)))
            caps = defaultdict(int)
            for t in sorted(byth):
                for c in byth[t]: caps[c] += 1
                print('  %-40s %s' % (t, ','.join(str(c) for c in byth[t])))
            print('  capacity distribution: %s' % ', '.join('%d B x %d' % kv for kv in sorted(caps.items())))
            stages = defaultdict(int)
            for t, cl in byth.items():
                stages[t.rsplit('-', 1)[0] if '-' in t else t] += len(cl)
            print('  threads by pool: %s' % dict(stages))
        if 'hints pool slab' in k:
            print('\n-- hints slabs --')
            print('  %d slabs, capacities %s' % (n, sorted(set(c for o, c, rl in lst))))
    small = groups.get('(no strong referrer: dropped, awaiting Cleaner)')
    if small:
        cs = defaultdict(int)
        for o, c, rl in small[2]: cs[c] += 1
        big = sorted(((c, k) for c, k in cs.items()), reverse=True)[:10]
        print('\n-- unreferenced owners, largest capacities: %s' % ', '.join('%d B x %d' % ck for ck in big))


if __name__ == '__main__':
    main()
