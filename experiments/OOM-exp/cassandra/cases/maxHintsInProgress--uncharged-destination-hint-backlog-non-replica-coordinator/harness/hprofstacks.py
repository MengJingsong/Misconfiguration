#!/usr/bin/env python3
# B23: print the thread stack traces recorded in an HPROF file (STACK TRACE / STACK FRAME records), top <n> frames each,
# grouped by identical top frames. usage: hprofstacks.py <file.hprof> [n=8]
import struct, sys, collections
f = open(sys.argv[1], 'rb'); n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
while f.read(1) != b'\0': pass
idsz = struct.unpack('>I', f.read(4))[0]; f.read(8)
rid = lambda b: int.from_bytes(b, 'big')
strings = {}; cser = {}; frames = {}; traces = []
while True:
    h = f.read(9)
    if len(h) < 9: break
    tag = h[0]; ln = struct.unpack('>I', h[5:9])[0]
    if tag == 0x01:
        b = f.read(ln); strings[rid(b[:idsz])] = b[idsz:].decode('utf-8', 'replace')
    elif tag == 0x02:
        b = f.read(ln); cser[struct.unpack('>I', b[:4])[0]] = rid(b[8 + idsz:8 + 2 * idsz])
    elif tag == 0x04:
        b = f.read(ln); fid = rid(b[:idsz]); m = rid(b[idsz:2*idsz]); src = rid(b[3*idsz:4*idsz])
        cs, line = struct.unpack('>Ii', b[4*idsz:4*idsz+8]); frames[fid] = (cs, m, src, line)
    elif tag == 0x05:
        b = f.read(ln); ser, tser, nf = struct.unpack('>III', b[:12])
        traces.append((ser, tser, [rid(b[12+i*idsz:12+(i+1)*idsz]) for i in range(nf)]))
    else:
        f.seek(ln, 1)
def fr(fid):
    cs, m, src, line = frames[fid]
    return f"{strings.get(cser.get(cs), '?').replace('/', '.')}.{strings.get(m, '?')}({strings.get(src, '?')}:{line})"
groups = collections.defaultdict(list)
for ser, tser, fl in traces:
    if not fl: continue
    groups[tuple(fr(x) for x in fl[:n])].append(tser)
for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    print(f'--- {len(v)} thread(s), serials {v[:6]}')
    for line in k: print('   ', line)
