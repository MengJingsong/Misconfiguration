#!/usr/bin/env python3
"""Count live byte[] arrays by exact length in an HPROF heap dump (case-file A5d; replaces MAT/jhat).
Usage: hprof_count.py <file.hprof> [len ...]   -> prints byteArrays=<n> byteArrayBytes=<sum> len<L>=<count> ... maxLen=<L>"""
import mmap, struct, sys

TSIZE = {4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}

def main():
    path = sys.argv[1]
    lens = [int(x) for x in sys.argv[2:]]
    with open(path, 'rb') as f:
        m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    hdr_end = m.find(b'\0') + 1
    idsz = struct.unpack_from('>I', m, hdr_end)[0]
    TSIZE[2] = idsz
    pos = hdr_end + 4 + 8
    n = len(m)
    counts = {L: 0 for L in lens}
    nb = 0; sb = 0; maxlen = 0; big = {}
    while pos < n:
        tag = m[pos]; length = struct.unpack_from('>I', m, pos + 5)[0]
        body = pos + 9; end = body + length
        if tag in (0x0C, 0x1C):
            p = body
            while p < end:
                st = m[p]; p += 1
                if st == 0xFF: p += idsz
                elif st == 0x01: p += 2 * idsz
                elif st in (0x02, 0x03, 0x08): p += idsz + 8
                elif st in (0x04, 0x06): p += idsz + 4
                elif st in (0x05, 0x07): p += idsz
                elif st == 0x20:
                    p += idsz + 4 + 6 * idsz + 4
                    cp = struct.unpack_from('>H', m, p)[0]; p += 2
                    for _ in range(cp):
                        t = m[p + 2]; p += 3 + TSIZE[t]
                    ns = struct.unpack_from('>H', m, p)[0]; p += 2
                    for _ in range(ns):
                        t = m[p + idsz]; p += idsz + 1 + TSIZE[t]
                    ni = struct.unpack_from('>H', m, p)[0]; p += 2 + ni * (idsz + 1)
                elif st == 0x21:
                    p += idsz + 4 + idsz
                    ln = struct.unpack_from('>I', m, p)[0]; p += 4 + ln
                elif st == 0x22:
                    p += idsz + 4
                    cnt = struct.unpack_from('>I', m, p)[0]; p += 4 + idsz + cnt * idsz
                elif st == 0x23:
                    p += idsz + 4
                    cnt = struct.unpack_from('>I', m, p)[0]; t = m[p + 4]; p += 5
                    if t == 8:
                        nb += 1; sb += cnt
                        if cnt in counts: counts[cnt] += 1
                        if cnt > maxlen: maxlen = cnt
                        if cnt >= 1048576: big[cnt] = big.get(cnt, 0) + 1
                    p += cnt * TSIZE[t]
                else:
                    raise SystemExit(f"unknown subrecord 0x{st:02x} at {p - 1}")
        pos = end
    out = [f"byteArrays={nb}", f"byteArrayBytes={sb}"] + [f"len{L}={counts[L]}" for L in lens] + [f"maxLen={maxlen}"]
    out.append("ge1MiB=" + ";".join(f"{k}x{v}" for k, v in sorted(big.items())))
    print(" ".join(out))

if __name__ == '__main__':
    main()
