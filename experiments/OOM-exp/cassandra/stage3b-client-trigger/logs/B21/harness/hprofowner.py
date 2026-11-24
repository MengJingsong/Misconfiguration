#!/usr/bin/env python3
# B21 (2026-11-21): owner split of the large byte[] in an HPROF dump (design: "split by owner").
# One multi-source BFS from every GC root (thread-stack locals, thread objects, JNI globals/locals, sticky classes and
# their static fields), so each object gets its shortest path from a root. For every target byte[] (row values of
# 100-140 KiB, and arrays >= 8 MiB) it walks that path back to its root and groups bytes by
#   root   = "frame <method> [thread <top cassandra frames>]" for a stack local, "static <Class>" for class statics, ...
#   chain  = the distinct class names along the path (consecutive repeats collapsed; Cassandra/java.util names kept).
#   hprofowner.py <file.hprof> [maxchain=14]
import mmap, struct, sys, collections
fn = sys.argv[1]; MAXC = int(sys.argv[2]) if len(sys.argv) > 2 else 14
f = open(fn, 'rb'); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
p = mm.find(b'\0') + 1
idsz = struct.unpack('>I', mm[p:p + 4])[0]; p += 12
U4 = struct.Struct('>I'); U2 = struct.Struct('>H')
def rid(o): return int.from_bytes(mm[o:o + idsz], 'big')
PSZ = {2: idsz, 4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}
PNAME = {4: 'boolean[]', 5: 'char[]', 6: 'float[]', 7: 'double[]', 8: 'byte[]', 9: 'short[]', 10: 'int[]', 11: 'long[]'}
strings = {}; cname = {}; frames = {}; traces = {}; ts_by_thread = {}
csuper = {}; cfields = {}; cstatics = {}
inst = {}      # id -> (data offset, class id)
oarr = {}      # id -> (data offset, n, elem class id)
parr = {}      # id -> (type, len)   (only byte[] >= 100 KiB, and everything else as type only for chain naming)
ptype = {}
roots = []     # (id, desc)
def heap(a, n):
    i = a; e = a + n
    while i < e:
        t = mm[i]; i += 1
        if t == 0xFF: roots.append((rid(i), 'unknown')); i += idsz
        elif t == 0x01: roots.append((rid(i), 'JNI global')); i += 2 * idsz
        elif t == 0x02: o = rid(i); th, fr = struct.unpack('>Ii', mm[i + idsz:i + idsz + 8]); roots.append((o, ('L', th, fr, 'JNI local'))); i += idsz + 8
        elif t == 0x03: o = rid(i); th, fr = struct.unpack('>Ii', mm[i + idsz:i + idsz + 8]); roots.append((o, ('L', th, fr, 'frame'))); i += idsz + 8
        elif t == 0x04: o = rid(i); th = U4.unpack_from(mm, i + idsz)[0]; roots.append((o, ('L', th, -1, 'native stack'))); i += idsz + 4
        elif t == 0x05: roots.append((rid(i), 'sticky')); i += idsz
        elif t == 0x06: o = rid(i); th = U4.unpack_from(mm, i + idsz)[0]; roots.append((o, ('L', th, -1, 'thread block'))); i += idsz + 4
        elif t == 0x07: roots.append((rid(i), 'monitor')); i += idsz
        elif t == 0x08:
            o = rid(i); th, st = struct.unpack('>II', mm[i + idsz:i + idsz + 8]); ts_by_thread[th] = st; roots.append((o, ('T', th))); i += idsz + 8
        elif t == 0x20:
            cid = rid(i); i += idsz + 4
            csuper[cid] = rid(i); i += 6 * idsz
            i += 4
            cp = U2.unpack_from(mm, i)[0]; i += 2
            for _ in range(cp):
                i += 2; ty = mm[i]; i += 1; i += PSZ[ty]
            sf = U2.unpack_from(mm, i)[0]; i += 2; st = []
            for _ in range(sf):
                i += idsz; ty = mm[i]; i += 1
                if ty == 2: v = rid(i); st.append(v) if v else None
                i += PSZ[ty]
            cstatics[cid] = st
            nf = U2.unpack_from(mm, i)[0]; i += 2; fl = []
            for _ in range(nf):
                i += idsz; fl.append(mm[i]); i += 1
            cfields[cid] = fl
        elif t == 0x21:
            o = rid(i); i += idsz + 4; cid = rid(i); i += idsz
            ln = U4.unpack_from(mm, i)[0]; i += 4
            inst[o] = (i, cid); i += ln
        elif t == 0x22:
            o = rid(i); i += idsz + 4; ln = U4.unpack_from(mm, i)[0]; i += 4
            cid = rid(i); i += idsz
            oarr[o] = (i, ln, cid); i += ln * idsz
        elif t == 0x23:
            o = rid(i); i += idsz + 4; ln = U4.unpack_from(mm, i)[0]; i += 4
            ty = mm[i]; i += 1
            if ty == 8 and ln >= 100 * 1024: parr[o] = ln
            else: ptype[o] = ty
            i += ln * PSZ[ty]
        else:
            raise SystemExit(f'unknown subtag {t:#x} at {i}')
while p + 9 <= len(mm):
    tag = mm[p]; ln = U4.unpack_from(mm, p + 5)[0]; b = p + 9
    if tag == 0x01: strings[rid(b)] = mm[b + idsz:b + ln].decode('utf-8', 'replace')
    elif tag == 0x02: cname[rid(b + 4)] = rid(b + 8 + idsz); cname[('s', U4.unpack_from(mm, b)[0])] = rid(b + 8 + idsz)
    elif tag == 0x04:
        fid = rid(b); m = rid(b + idsz); cs, line = struct.unpack('>Ii', mm[b + 4 * idsz:b + 4 * idsz + 8]); frames[fid] = (cs, m, line)
    elif tag == 0x05:
        ss, th, n = struct.unpack('>III', mm[b:b + 12]); traces[ss] = [rid(b + 12 + k * idsz) for k in range(n)]
    elif tag in (0x0C, 0x1C): heap(b, ln)
    p = b + ln
print(f'parsed: {len(inst)} instances, {len(oarr)} object arrays, {len(parr)} byte[] >= 100 KiB, {len(roots)} roots', flush=True)
def cn(c): return strings.get(cname.get(c), '?').replace('/', '.')
def frs(fid):
    cs, m, line = frames[fid]
    return f"{strings.get(cname.get(('s', cs)), '?').replace('/', '.').split('.')[-1]}.{strings.get(m, '?')}:{line}"
KEY = ('VectorTopKProcessor', 'takeTopK', 'consumeSortByScore', 'LocalDataResponse', 'DataOutputBuffer', 'expandToFit',
       'processResults', 'ResultSet', 'RemoteDataResponse', 'deserialize', 'ReadCommandVerbHandler', 'StorageAttachedIndexSearcher',
       'SelectStatement', 'DataResolver', 'Message$Serializer', 'InboundMessageHandler', 'OutboundConnection', 'CBUtil', 'encode',
       'ResultMessage', 'executeLocally', 'ReadCallback', 'awaitResults')
def thread_sig(th):
    fl = traces.get(ts_by_thread.get(th), [])
    s = [frs(x) for x in fl if x in frames]
    k = [x for x in s if any(w in x for w in KEY)]
    return ' < '.join(k[:4]) or (' < '.join(s[:2]) if s else 'no-trace')
# reference offsets per class (own fields, then super's)
refoff = {}
def roffs(cid):
    r = refoff.get(cid)
    if r is not None: return r
    out = []; off = 0; c = cid
    while c and c in cfields:
        for ty in cfields[c]:
            if ty == 2: out.append(off)
            off += PSZ[ty]
        c = csuper.get(c)
    refoff[cid] = out; return out
parent = {}
dq = collections.deque()
for o, d in roots:
    if o and o not in parent: parent[o] = ('ROOT', d); dq.append(o)
for c in cstatics:     # class objects are reachable (sticky); their statics are children
    if c not in parent: parent[c] = ('ROOT', 'class'); dq.append(c)
while dq:
    o = dq.popleft()
    x = inst.get(o)
    if x is not None:
        base, cid = x; ch = [rid(base + k) for k in roffs(cid)]
    else:
        y = oarr.get(o)
        if y is not None:
            base, n, _ = y; ch = [int.from_bytes(mm[base + k * idsz:base + (k + 1) * idsz], 'big') for k in range(n)]
        elif o in cstatics: ch = cstatics[o]
        else: continue
    for c in ch:
        if c and c not in parent: parent[c] = o; dq.append(c)
print(f'reached {len(parent)} objects', flush=True)
def name(o):
    if o in inst: return cn(inst[o][1])
    if o in oarr: return cn(oarr[o][2]) + '[]'
    if o in cstatics: return 'class ' + cn(o)
    if o in parr: return 'byte[]'
    if o in ptype: return PNAME[ptype[o]]
    return '?'
def keep(nm):
    return nm.startswith(('org.apache.cassandra', 'java.util', 'class ', 'io.netty', 'java.lang.Thread', 'io.github.jbellis')) or nm.endswith('[]')
def short(nm):
    if nm.startswith('class '): return 'static ' + nm[6:].split('.')[-1]
    return nm.split('.')[-1]
def rootdesc(d):
    if isinstance(d, tuple):
        if d[0] == 'T': return f'thread-object [{thread_sig(d[1])}]'
        th, fr, kind = d[1], d[2], d[3]
        fl = traces.get(ts_by_thread.get(th), [])
        m = frs(fl[fr]) if 0 <= fr < len(fl) and fl[fr] in frames else '?'
        return f'{kind} {m} [{thread_sig(th)}]'
    return d
groups = collections.defaultdict(lambda: [0, 0]); unreached = [0, 0]
for o, ln in list(parr.items()):
    if 100 * 1024 <= ln <= 140 * 1024: kind = 'value 100-140KiB'
    elif ln >= 8 << 20: kind = f'big {ln / 2**20:.0f}MiB'
    else: continue
    if o not in parent: unreached[0] += 1; unreached[1] += ln; continue
    path = []; x = o; seen = 0
    while True:
        pr = parent[x]
        if isinstance(pr, tuple) and pr[0] == 'ROOT': rd = rootdesc(pr[1]) if pr[1] != 'class' else 'static ' + cn(x); break
        x = pr; path.append(name(x)); seen += 1
        if seen > 5000: rd = 'chain>5000'; break
    ch = []
    for nm in reversed(path):
        if keep(nm):
            s = short(nm)
            if not ch or ch[-1] != s: ch.append(s)
    if len(ch) > MAXC: ch = ch[:MAXC - 3] + ['...'] + ch[-3:]
    k = (kind.split(' ')[0] if kind.startswith('value') else 'big>=8MiB', rd, ' > '.join(ch))
    groups[k][0] += 1; groups[k][1] += ln
    if kind.startswith('big'): print(f'  {kind}: root {rd} | {" > ".join(ch)}')
tot = sum(v[1] for v in groups.values())
print(f'targets reached: {sum(v[0] for v in groups.values())} arrays, {tot / 2**20:.1f} MiB; unreachable (garbage): {unreached[0]} arrays, {unreached[1] / 2**20:.1f} MiB')
for k, v in sorted(groups.items(), key=lambda kv: -kv[1][1]):
    print(f'{v[1] / 2**20:9.1f} MiB {v[0]:>6} {k[0]:6} | root: {k[1]}\n{"":24}chain: {k[2]}')
