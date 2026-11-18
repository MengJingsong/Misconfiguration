#!/usr/bin/env python3
"""Print the stack of the thread that triggered a HeapDumpOnOutOfMemoryError dump.
HotSpot (VM_HeapDumper::dump_stack_traces) prepends a fake frame `java.lang.OutOfMemoryError.<init>` to the
stack trace of the thread that threw the OOME. Usage: python3 -I hprof_oome_thread.py <dump.hprof> [nframes]"""
import mmap, struct, sys
f = open(sys.argv[1], 'rb'); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
NF = int(sys.argv[2]) if len(sys.argv) > 2 else 25
p = mm.find(b'\0') + 1 + 4 + 8
uid = lambda o: struct.unpack_from('>Q', mm, o)[0]; u4 = lambda o: struct.unpack_from('>I', mm, o)[0]
strings = {}; cls_serial = {}; frames = {}; traces = {}; thread_roots = {}
segs = []
while p < len(mm):
    tag = mm[p]; ln = u4(p + 5); b = p + 9
    if tag == 0x01: strings[uid(b)] = mm[b + 8:b + ln].decode('utf-8', 'replace')
    elif tag == 0x02: cls_serial[u4(b)] = uid(b + 16)
    elif tag == 0x04: frames[uid(b)] = (uid(b + 8), uid(b + 24), u4(b + 32), struct.unpack_from('>i', mm, b + 36)[0])
    elif tag == 0x05:
        n = u4(b + 8); traces[u4(b)] = (u4(b + 4), [uid(b + 12 + 8 * i) for i in range(n)])
    elif tag in (0x0C, 0x1C): segs.append((b, b + ln))
    p = b + ln
def fr(fid):
    m, src, cs, line = frames[fid]
    return '%s.%s(%s:%s)' % (strings.get(cls_serial.get(cs), '?').replace('/', '.'), strings.get(m, '?'), strings.get(src, '?'), line)
hits = [(s, t) for s, t in traces.items() if t[1] and strings.get(frames[t[1][0]][0]) == '<init>'
        and 'OutOfMemoryError' in strings.get(cls_serial.get(frames[t[1][0]][2]), '')]
for s, (tser, fl) in hits:
    print('OOME-initiating thread: trace serial %d, thread serial %d' % (s, tser))
    for fid in fl[:NF]: print('    at ' + fr(fid))
if not hits: print('no trace with a leading OutOfMemoryError.<init> frame found')
