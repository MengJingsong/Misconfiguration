#!/usr/bin/env python3
# Print the thread stack traces stored in an HPROF dump (B6 run 4), for the OOM thread/stack (V5).
#   hprofstacks.py <file.hprof> [grep-word]
# Thread names come from ROOT_THREAD_OBJ -> java.lang.Thread.name is not resolved (needs field
# parsing); traces are listed by thread serial. With a grep word, only traces whose frames contain it.
import struct, sys
f = open(sys.argv[1], 'rb'); word = sys.argv[2] if len(sys.argv) > 2 else None
while f.read(1) != b'\0': pass
idsz = struct.unpack('>I', f.read(4))[0]; f.read(8)
rid = lambda b: int.from_bytes(b, 'big')
strings = {}; cls_by_serial = {}; frames = {}; traces = []
while True:
    h = f.read(9)
    if len(h) < 9: break
    tag = h[0]; ln = struct.unpack('>I', h[5:9])[0]
    if tag == 0x01:
        b = f.read(ln); strings[rid(b[:idsz])] = b[idsz:].decode('utf-8', 'replace')
    elif tag == 0x02:
        b = f.read(ln); cls_by_serial[struct.unpack('>I', b[:4])[0]] = rid(b[8 + idsz:8 + 2 * idsz])
    elif tag == 0x04:
        b = f.read(ln); fid = rid(b[:idsz]); m = rid(b[idsz:2 * idsz]); src = rid(b[3 * idsz:4 * idsz])
        cs, line = struct.unpack('>Ii', b[4 * idsz:4 * idsz + 8]); frames[fid] = (cs, m, src, line)
    elif tag == 0x05:
        b = f.read(ln); ts, th, n = struct.unpack('>III', b[:12])
        traces.append((th, [rid(b[12 + i * idsz:12 + (i + 1) * idsz]) for i in range(n)]))
    else:
        f.seek(ln, 1)
def fr(fid):
    cs, m, src, line = frames[fid]
    return f"{strings.get(cls_by_serial.get(cs), '?').replace('/', '.')}.{strings.get(m, '?')}({strings.get(src, '?')}:{line})"
for th, fl in traces:
    if not fl: continue
    s = [fr(x) for x in fl]
    if word and not any(word in x for x in s): continue
    print(f'--- thread serial {th}, {len(s)} frames'); print('\n'.join('  ' + x for x in s[:14]))
