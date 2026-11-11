#!/usr/bin/env python3
"""usage: python3 -I hprof_big.py <dump.hprof> [min_bytes]   prints 'bytearray <length>' for every live byte[] of at least min_bytes
(default 1 MiB), then 'total_bytearrays <count> <sum bytes>'. Streams the HPROF 1.0.2 record structure (heap dump from jcmd GC.heap_dump,
live objects only)."""
import mmap, struct, sys
SZ = {4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}
def main(path, minb):
    f = open(path, 'rb'); m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    z = m.find(b'\0'); idsz = struct.unpack('>I', m[z + 1:z + 5])[0]
    pos = z + 1 + 4 + 8
    vs = lambda t: idsz if t == 2 else SZ[t]
    big, cnt, tot = [], 0, 0
    n = len(m)
    while pos + 9 <= n:
        tag = m[pos]; ln = struct.unpack('>I', m[pos + 5:pos + 9])[0]; body = pos + 9
        if tag in (0x0C, 0x1C):
            p, end = body, body + ln
            while p < end:
                st = m[p]; p += 1
                if st == 0xFF or st == 0x05 or st == 0x07: p += idsz
                elif st == 0x01: p += 2 * idsz
                elif st in (0x02, 0x03, 0x08): p += idsz + 8
                elif st in (0x04, 0x06): p += idsz + 4
                elif st == 0x20:
                    p += idsz + 4 + 6 * idsz + 4   # id, stack, super, loader, signers, domain, res1, res2, instance size
                    nc = struct.unpack('>H', m[p:p + 2])[0]; p += 2
                    for _ in range(nc):
                        t = m[p + 2]; p += 3 + vs(t)
                    ns = struct.unpack('>H', m[p:p + 2])[0]; p += 2
                    for _ in range(ns):
                        t = m[p + idsz]; p += idsz + 1 + vs(t)
                    ni = struct.unpack('>H', m[p:p + 2])[0]; p += 2 + ni * (idsz + 1)
                elif st == 0x21:
                    l = struct.unpack('>I', m[p + idsz + 4 + idsz:p + idsz + 4 + idsz + 4])[0]; p += idsz + 4 + idsz + 4 + l
                elif st == 0x22:
                    l = struct.unpack('>I', m[p + idsz + 4:p + idsz + 8])[0]; p += idsz + 8 + idsz + l * idsz
                elif st == 0x23:
                    l = struct.unpack('>I', m[p + idsz + 4:p + idsz + 8])[0]; t = m[p + idsz + 8]; p += idsz + 9 + l * SZ[t]
                    if t == 8:
                        cnt += 1; tot += l
                        if l >= minb: big.append(l)
                else:
                    raise SystemExit('unknown subrecord %x at %d' % (st, p))
        pos = body + ln
    for l in sorted(big, reverse=True): print('bytearray', l)
    print('total_bytearrays', cnt, tot)
main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1 << 20)
