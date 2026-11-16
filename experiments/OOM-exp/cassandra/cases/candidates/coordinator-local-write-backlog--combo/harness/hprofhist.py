#!/usr/bin/env python3
# Minimal HPROF class histogram (instances + shallow bytes per class), B6 run 4.
#   hprofhist.py <file.hprof> [top=25]
# Reads LOAD_CLASS/STRING records for names and counts INSTANCE_DUMP / OBJ_ARRAY / PRIM_ARRAY
# sub-records of HEAP_DUMP(_SEGMENT). Shallow size = payload + 16 B header (approximation, compressed
# oops); arrays: payload + 16 B. Also lists thread names with an OutOfMemoryError in their stack trace
# (none expected: HotSpot does not record the throwing frame in the dump).
import struct, sys, collections
f = open(sys.argv[1], 'rb'); top = int(sys.argv[2]) if len(sys.argv) > 2 else 25
hdr = b''
while True:
    c = f.read(1)
    if c == b'\0': break
    hdr += c
idsz = struct.unpack('>I', f.read(4))[0]; f.read(8)
rid = (lambda b: int.from_bytes(b, 'big'))
strings = {}; cname = {}; inst_size = {}
cnt = collections.Counter(); byt = collections.Counter()
PSZ = {2: idsz, 4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}
PNAME = {4: 'boolean[]', 5: 'char[]', 6: 'float[]', 7: 'double[]', 8: 'byte[]', 9: 'short[]', 10: 'int[]', 11: 'long[]'}
def heap(buf):
    i = 0; n = len(buf)
    def id_(j): return rid(buf[j:j + idsz])
    while i < n:
        t = buf[i]; i += 1
        if t == 0xFF: i += idsz
        elif t in (0x01,): i += 2 * idsz
        elif t in (0x02, 0x03): i += idsz + 8
        elif t == 0x04: i += idsz + 4
        elif t in (0x05, 0x07): i += idsz
        elif t == 0x06: i += idsz + 4
        elif t == 0x08: i += idsz + 8
        elif t == 0x20:
            cid = id_(i); i += idsz + 4  # class id, stack serial
            i += 6 * idsz  # super, loader, signers, protection domain, reserved1, reserved2
            isz = struct.unpack('>I', buf[i:i + 4])[0]; i += 4; inst_size[cid] = isz
            cp = struct.unpack('>H', buf[i:i + 2])[0]; i += 2
            for _ in range(cp):
                i += 2; ty = buf[i]; i += 1; i += PSZ[ty]
            sf = struct.unpack('>H', buf[i:i + 2])[0]; i += 2
            for _ in range(sf):
                i += idsz; ty = buf[i]; i += 1; i += PSZ[ty]
            nf = struct.unpack('>H', buf[i:i + 2])[0]; i += 2
            i += nf * (idsz + 1)
        elif t == 0x21:
            i += idsz + 4; cid = id_(i); i += idsz
            ln = struct.unpack('>I', buf[i:i + 4])[0]; i += 4 + ln
            cnt[cid] += 1; byt[cid] += ln + 16
        elif t == 0x22:
            i += idsz + 4; ln = struct.unpack('>I', buf[i:i + 4])[0]; i += 4
            cid = id_(i); i += idsz + ln * idsz
            cnt[('A', cid)] += 1; byt[('A', cid)] += ln * 4 + 16
        elif t == 0x23:
            i += idsz + 4; ln = struct.unpack('>I', buf[i:i + 4])[0]; i += 4
            ty = buf[i]; i += 1; i += ln * PSZ[ty]
            cnt[('P', ty)] += 1; byt[('P', ty)] += ln * PSZ[ty] + 16
        else:
            raise SystemExit(f'unknown subtag {t:#x} at {i}')
while True:
    h = f.read(9)
    if len(h) < 9: break
    tag = h[0]; ln = struct.unpack('>I', h[5:9])[0]
    if tag == 0x01:
        b = f.read(ln); strings[rid(b[:idsz])] = b[idsz:].decode('utf-8', 'replace')
    elif tag == 0x02:
        b = f.read(ln); cname[rid(b[4:4 + idsz])] = rid(b[8 + idsz:8 + 2 * idsz])
    elif tag in (0x0C, 0x1C):
        heap(f.read(ln))
    else:
        f.seek(ln, 1)
def name(k):
    if isinstance(k, tuple):
        if k[0] == 'P': return PNAME[k[1]]
        return strings.get(cname.get(k[1]), '?').replace('/', '.') + '[]'
    return strings.get(cname.get(k), '?').replace('/', '.')
tot = sum(byt.values())
print(f'total shallow {tot/2**20:.0f} MiB, objects {sum(cnt.values())}')
for k, b in byt.most_common(top):
    print(f'{b/2**20:10.1f} MiB {cnt[k]:>11} {name(k)}')
for want in ('org.apache.cassandra.db.Mutation', 'org.apache.cassandra.db.rows.BufferCell', 'org.apache.cassandra.db.rows.ArrayCell',
             'org.apache.cassandra.net.Message', 'org.apache.cassandra.net.RequestCallbacks$CallbackInfo',
             'org.apache.cassandra.service.WriteResponseHandler', 'org.apache.cassandra.db.partitions.PartitionUpdate'):
    ks = [k for k in cnt if not isinstance(k, tuple) and name(k) == want]
    print(f'{want}: {sum(cnt[k] for k in ks)}')
