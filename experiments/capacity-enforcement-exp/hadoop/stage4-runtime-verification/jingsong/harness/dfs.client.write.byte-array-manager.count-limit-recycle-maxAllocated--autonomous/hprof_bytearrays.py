#!/usr/bin/env python3
"""Diagnostic (not a reading of the case): byte[] length distribution in an HPROF heap dump.
Usage: python3 -I hprof_bytearrays.py <dump.hprof>
Prints the count and total bytes of byte[] arrays per length for lengths >= 4096, and the total of all byte[].
"""
import collections
import struct
import sys

f = open(sys.argv[1], "rb")
hdr = b""
while True:
    c = f.read(1)
    if c == b"\0":
        break
    hdr += c
idsize = struct.unpack(">I", f.read(4))[0]
f.read(8)
BASIC = {2: idsize, 4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}
cls_inst_size = {}
big = collections.Counter()
total_bytes = 0
total_n = 0


def rid(b, o):
    return int.from_bytes(b[o:o + idsize], "big")


while True:
    h = f.read(9)
    if len(h) < 9:
        break
    tag, _, ln = struct.unpack(">BII", h)
    body = f.read(ln)
    if tag not in (0x0C, 0x1C):
        continue
    o = 0
    n = len(body)
    while o < n:
        st = body[o]
        o += 1
        if st == 0xFF:
            o += idsize
        elif st in (0x01,):
            o += 2 * idsize
        elif st in (0x02, 0x03):
            o += idsize + 8
        elif st == 0x04:
            o += idsize + 4
        elif st in (0x05, 0x07):
            o += idsize
        elif st == 0x06:
            o += idsize + 4
        elif st == 0x08:
            o += idsize + 8
        elif st == 0x20:  # class dump
            o += idsize + 4 + 6 * idsize + 4
            cp = struct.unpack(">H", body[o:o + 2])[0]
            o += 2
            for _ in range(cp):
                o += 2
                t = body[o]
                o += 1 + BASIC[t]
            sf = struct.unpack(">H", body[o:o + 2])[0]
            o += 2
            for _ in range(sf):
                o += idsize
                t = body[o]
                o += 1 + BASIC[t]
            fi = struct.unpack(">H", body[o:o + 2])[0]
            o += 2 + fi * (idsize + 1)
        elif st == 0x21:  # instance dump
            o += idsize + 4 + idsize
            sz = struct.unpack(">I", body[o:o + 4])[0]
            o += 4 + sz
        elif st == 0x22:  # object array
            o += idsize + 4
            cnt = struct.unpack(">I", body[o:o + 4])[0]
            o += 4 + idsize + cnt * idsize
        elif st == 0x23:  # primitive array
            o += idsize + 4
            cnt, t = struct.unpack(">IB", body[o:o + 5])
            o += 5 + cnt * BASIC[t]
            if t == 8:
                total_n += 1
                total_bytes += cnt
                if cnt >= 4096:
                    big[cnt] += 1
        else:
            raise SystemExit(f"unknown subtag {st:#x} at {o}")
print(f"byte[] total: n={total_n} elements(bytes)={total_bytes}")
for length, c in sorted(big.items(), key=lambda x: -x[0] * x[1]):
    print(f"  length {length}: count {c}, bytes {length * c}")
