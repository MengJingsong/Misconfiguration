#!/usr/bin/env python3
"""Compare unit logs with the frozen B2f table (as amended by A3). Usage: unit-analyze.py <dir with unit-<P>.log>"""
import re, sys, os
d = sys.argv[1]
MiB = 1 << 20
Ps = {'4096': 4096, 'default': 8192, '1048576': 1048576, '16777216': 16777216}
# B2f, columns P=4096, 8192, 1048576, 16777216
B2F = {
 'initial':        [16, 16, 16, 16],
 'request=100':    [128, 128, 128, 128],
 'request=5000':   [4096, 8192, 8192, 8192],
 'request=8193':   [4096, 8192, 16384, 16384],
 'request=65537':  [4096, 8192, 131072, 131072],
 'request=1048576':[4096, 8192, 1048576, 2097152],
 'request=4194304':[4096, 8192, 1048576, 8388608],
 'request=20971520':[4096, 8192, 1048576, 16777216],
 'directWrite 4MiB':[4096, 8192, 1048576, 8388608],
 'writeUTF 60000': [4096, 8192, 65536, 65536],
 'sumLen':         [131072, 262144, 33554432, 268435456],
}
npass = nfail = 0
def check(label, ok, msg):
    global npass, nfail
    if ok: npass += 1
    else: nfail += 1
    print(("PASS " if ok else "FAIL ") + label + ": " + msg)
for i, (pn, P) in enumerate(Ps.items()):
    txt = open(os.path.join(d, f'unit-{pn}.log')).read()
    got = {}
    m = re.search(r'initial len=(\d+)', txt); got['initial'] = int(m.group(1)) if m else None
    for r, l in re.findall(r'request=(\d+) len=(\d+)', txt): got[f'request={r}'] = int(l)
    m = re.search(r'directWrite 4MiB len=(\d+)', txt); got['directWrite 4MiB'] = int(m.group(1)) if m else None
    m = re.search(r'writeUTF 60000 len=(\d+)', txt); got['writeUTF 60000'] = int(m.group(1)) if m else None
    m = re.search(r'threads=(\d+) sumLen=(\d+) maxLen=(\d+) heapDelta=(-?\d+)', txt)
    got['sumLen'] = int(m.group(2)) if m else None
    maxLen = int(m.group(3)) if m else None
    hd = int(m.group(4)) if m else None
    pl = re.search(r'P=\S+', txt).group(0)
    print(f"--- P={pn} ({P}); property line: {pl}")
    for k, row in B2F.items():
        check(f"P={pn} {k}", got.get(k) == row[i], f"expected {row[i]} got {got.get(k)}")
    allLens = [v for k, v in got.items() if v is not None] + ([maxLen] if maxLen else [])
    lens_only = [v for k, v in got.items() if k != 'sumLen' and v is not None] + [maxLen]
    check(f"P={pn} len<=P everywhere", all(v <= P for v in lens_only), f"max observed len {max(lens_only)}")
    s = got['sumLen']; tol = max(4 * MiB, 0.10 * s)
    if P <= 8192:
        ok = abs(hd) <= 4 * MiB
        check(f"P={pn} heapDelta noise (|hd|<=4MiB)", ok, f"heapDelta={hd} ({hd/MiB:.2f} MiB), sumLen={s}")
    else:
        ok = abs(hd - s) <= tol
        check(f"P={pn} heapDelta tracks sumLen (A3 tol {tol/MiB:.1f} MiB)", ok, f"heapDelta={hd} ({hd/MiB:.2f} MiB) sumLen={s} ({s/MiB:.2f} MiB) diff={(hd-s)/MiB:.2f} MiB")
print(f"TOTAL PASS={npass} FAIL={nfail}")
