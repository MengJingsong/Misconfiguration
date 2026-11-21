#!/usr/bin/env python3
# R18 phase 0 step 3 (design §2.5): R10's pristine sets, read only. (a) every file name and size equals R10's generator
# listing (logs/pristine-listing.txt of R10); (b) each Data.db's CRC32 equals its Digest.crc32. Usage:
#   verify_pristine.py <pristine root> <r10 pristine-listing.txt>
import os, re, sys, zlib, stat
root, listing = sys.argv[1], sys.argv[2]
exp = {}; cur = None
for l in open(listing):
    l = l.rstrip('\n')
    m = re.match(r'^data/pristine/(\w+)/:$', l)
    if m: cur = m.group(1); continue
    f = l.split()
    if cur and len(f) >= 9 and f[0].startswith('-'): exp[f'{cur}/{f[8]}'] = int(f[4])
got = {}
for s in sorted(os.listdir(root)):
    for f in sorted(os.listdir(os.path.join(root, s))):
        p = os.path.join(root, s, f); st = os.stat(p); got[f'{s}/{f}'] = (st.st_size, oct(stat.S_IMODE(st.st_mode)))
ok = 0; bad = []
for k, v in exp.items():
    if k in got and got[k][0] == v: ok += 1
    else: bad.append((k, v, got.get(k)))
extra = [k for k in got if k not in exp]
print(f"LISTING expected={len(exp)} matched={ok} mismatched={len(bad)} extra={len(extra)} total_bytes={sum(v[0] for v in got.values())} modes={sorted(set(v[1] for v in got.values()))}")
for b in bad: print('MISMATCH', b)
for e in extra: print('EXTRA', e)
for s in sorted(os.listdir(root)):
    d = os.path.join(root, s)
    for f in sorted(os.listdir(d)):
        if not f.endswith('-Data.db'): continue
        c = 0
        with open(os.path.join(d, f), 'rb') as fh:
            while True:
                b = fh.read(1 << 24)
                if not b: break
                c = zlib.crc32(b, c)
        dig = open(os.path.join(d, f.replace('-Data.db', '-Digest.crc32'))).read().strip()
        print(f"CRC {s}/{f} computed={c & 0xffffffff} digest={dig} {'OK' if str(c & 0xffffffff) == dig else 'FAIL'}")
print("VERIFY DONE")
