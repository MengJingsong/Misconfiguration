import mmap, struct, sys
f = open(sys.argv[1], 'rb'); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ); pat = sys.argv[2:]
p = mm.find(b'\0') + 13
uid = lambda o: struct.unpack_from('>Q', mm, o)[0]; u4 = lambda o: struct.unpack_from('>I', mm, o)[0]
strings = {}; cs = {}; frames = {}; traces = {}
while p < len(mm):
    tag = mm[p]; ln = u4(p + 5); b = p + 9
    if tag == 0x01: strings[uid(b)] = mm[b + 8:b + ln].decode('utf-8', 'replace')
    elif tag == 0x02: cs[u4(b)] = uid(b + 16)
    elif tag == 0x04: frames[uid(b)] = (uid(b + 8), uid(b + 24), u4(b + 32), struct.unpack_from('>i', mm, b + 36)[0])
    elif tag == 0x05:
        n = u4(b + 8); traces[u4(b)] = (u4(b + 4), [uid(b + 12 + 8 * i) for i in range(n)])
    p = b + ln
def fr(fid):
    m, src, c, line = frames[fid]; return '%s.%s:%s' % (strings.get(cs.get(c), '?').split('/')[-1], strings.get(m, '?'), line)
for s, (t, fl) in traces.items():
    st = [fr(x) for x in fl]
    if any(q in x for x in st for q in pat):
        print('thread serial', t); [print('   ', x) for x in st[:14]]
