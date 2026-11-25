# Stage-4 harness, order 20: attribute byte[] in a JN heap dump (jcmd GC.heap_dump, live objects) to
# JournaledEditsCache.dataMap (B3d's optional K3 heap dump; done with this parser because Eclipse MAT is not on
# the node). Run with python3 -I. Usage: hprof_cache.py <file.hprof>
# Prints: cache entries and their byte[] bytes (shallow, 16 B header + length rounded up to 8), all live byte[]
# bytes, the byte[] >= 32 KiB outside the cache by length, and the classes that reference them.
import struct, sys
from collections import Counter, defaultdict

f = open(sys.argv[1], "rb").read()
p = f.index(b"\0") + 1
IDS = struct.unpack(">I", f[p:p + 4])[0]; p += 12
assert IDS == 8
def rid(b, o): return struct.unpack(">Q", b[o:o + 8])[0]
TS = {2: 8, 4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}
strings, cname = {}, {}
classes = {}   # id -> (super, [(name, type)])
inst = {}      # id -> (classid, offset, len)
barr = {}      # id -> length
oarr = {}      # id -> (offset, n)
def shallow(n): return (16 + n + 7) // 8 * 8
while p < len(f):
    tag = f[p]; ln = struct.unpack(">I", f[p + 5:p + 9])[0]; b0 = p + 9; p = b0 + ln
    if tag == 0x01:
        strings[rid(f, b0)] = f[b0 + 8:b0 + ln].decode("utf-8", "replace")
    elif tag == 0x02:
        cname[rid(f, b0 + 4)] = rid(f, b0 + 16)
    elif tag in (0x0C, 0x1C):
        q, end = b0, b0 + ln
        while q < end:
            st = f[q]; q += 1
            if st == 0xFF: q += 8
            elif st == 0x01: q += 16
            elif st in (0x02, 0x03, 0x08): q += 16
            elif st in (0x04, 0x06): q += 12
            elif st in (0x05, 0x07): q += 8
            elif st == 0x20:
                cid = rid(f, q); sup = rid(f, q + 12); q += 8 + 4 + 8 * 6 + 4
                ncp = struct.unpack(">H", f[q:q + 2])[0]; q += 2
                for _ in range(ncp):
                    t = f[q + 2]; q += 3 + TS[t]
                ns = struct.unpack(">H", f[q:q + 2])[0]; q += 2
                for _ in range(ns):
                    t = f[q + 8]; q += 9 + TS[t]
                nf = struct.unpack(">H", f[q:q + 2])[0]; q += 2
                fl = []
                for _ in range(nf):
                    fl.append((rid(f, q), f[q + 8])); q += 9
                classes[cid] = (sup, fl)
            elif st == 0x21:
                oid = rid(f, q); cid = rid(f, q + 12); n = struct.unpack(">I", f[q + 20:q + 24])[0]
                inst[oid] = (cid, q + 24, n); q += 24 + n
            elif st == 0x22:
                oid = rid(f, q); n = struct.unpack(">I", f[q + 12:q + 16])[0]
                oarr[oid] = (q + 24, n); q += 24 + 8 * n
            elif st == 0x23:
                oid = rid(f, q); n = struct.unpack(">I", f[q + 12:q + 16])[0]; t = f[q + 16]
                if t == 8: barr[oid] = n
                q += 17 + TS[t] * n
            else:
                raise SystemExit("unknown sub-record %x at %d" % (st, q))
def cn(cid): return strings.get(cname.get(cid), "?").replace("/", ".")
def fields(oid):
    cid, off, n = inst[oid]; out = {}; c = cid
    while c and c in classes:
        sup, fl = classes[c]
        for nm, t in fl:
            s = TS[t]
            out.setdefault(strings.get(nm, "?"), rid(f, off) if t == 2 else f[off:off + s]); off += s
        c = sup
    return out
byname = defaultdict(list)
for oid, (cid, _, _) in inst.items():
    byname[cn(cid)].append(oid)
caches = byname.get("org.apache.hadoop.hdfs.qjournal.server.JournaledEditsCache", [])
print("JournaledEditsCache instances:", len(caches))
incache = set()
for c in caches:
    fd = fields(c)
    tm = fd["dataMap"]; tmf = fields(tm)
    stack, n, tot = [tmf["root"]], 0, 0
    while stack:
        e = stack.pop()
        if not e: continue
        ef = fields(e); v = ef["value"]
        incache.add(v); n += 1; tot += barr.get(v, 0)
        stack += [ef["left"], ef["right"]]
    ts = struct.unpack(">i", fd["totalSize"])[0]; cap = struct.unpack(">i", fd["capacity"])[0]
    print("cache %x: capacity=%d totalSize=%d entries=%d sum(len)=%d shallow(byte[])=%d" % (
        c, cap, ts, n, tot, sum(shallow(barr[v]) for v in incache)))
allb = sum(shallow(n) for n in barr.values())
print("all live byte[]: count=%d shallow bytes=%d" % (len(barr), allb))
big = {o: n for o, n in barr.items() if n >= 32768 and o not in incache}
print("byte[] >= 32 KiB outside the cache: count=%d shallow bytes=%d" % (len(big), sum(shallow(n) for n in big.values())))
for n, k in sorted(Counter(big.values()).items(), key=lambda x: -x[0] * x[1])[:15]:
    print("   length=%d x%d" % (n, k))
# referrers of the big outside arrays
ref = defaultdict(list)
for oid, (cid, off, n) in inst.items():
    cid0 = cid; o = off; c = cid
    while c and c in classes:
        sup, fl = classes[c]
        for nm, t in fl:
            if t == 2:
                v = rid(f, o)
                if v in big: ref[v].append(cn(cid0) + "." + strings.get(nm, "?"))
            o += TS[t]
        c = sup
for oid, (off, n) in oarr.items():
    for i in range(n):
        v = rid(f, off + 8 * i)
        if v in big: ref[v].append("Object[]")
agg = Counter()
for o, n in big.items():
    agg[(tuple(sorted(set(ref.get(o, ["(no referrer: root or unknown)"])))))] += shallow(n)
for k, v in agg.most_common(15):
    print("   referrers %s : %d bytes" % (", ".join(k)[:200], v))
small_out = sum(shallow(n) for o, n in barr.items() if n < 32768 and o not in incache)
print("byte[] < 32 KiB outside the cache: shallow bytes=%d" % small_out)
