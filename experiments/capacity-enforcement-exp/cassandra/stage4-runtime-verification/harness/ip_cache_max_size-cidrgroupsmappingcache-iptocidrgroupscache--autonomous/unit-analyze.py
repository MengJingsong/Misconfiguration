#!/usr/bin/env python3
"""B2f/B2g check for the unit tier (thresholds: case file B2f + section D AM4). Usage: unit-analyze.py <probe-lines.txt>"""
import re, sys
MB = 1024 * 1024
rows = {}
for line in open(sys.argv[1]):
    m = re.match(r'max=(\d+) .*PROBE (.*)', line.strip())
    if not m: continue
    M = int(m.group(1)); d = rows.setdefault(M, {})
    for k, v in re.findall(r'(\w+)=(-?\d+)', m.group(2)): d[k] = int(v)
ok = True
def exp(cond, text):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + "EXPECTED: " + text)
N = 600000
for M in sorted(rows):
    d = rows[M]; print(f"max={M}: {d}")
for M in sorted(rows):
    d = rows[M]
    exp(d.get('policyMaximum') == M, f"max={M}: policyMaximum == {M} (got {d.get('policyMaximum')})")
# outsideGroups is printed as 'outsideGroups estimatedSize=X': parse separately
outside = {}
for line in open(sys.argv[1]):
    m = re.match(r'max=(\d+) .*PROBE outsideGroups estimatedSize=(\d+)', line.strip())
    if m: outside[int(m.group(1))] = int(m.group(2))
final = {}
for line in open(sys.argv[1]):
    m = re.match(r'max=(\d+) .*PROBE max=(\d+) n=(\d+) estimatedSize=(\d+) maxSampledSize=(\d+) heapDeltaBytes=(-?\d+)', line.strip())
    if m: final[int(m.group(1))] = dict(n=int(m.group(3)), size=int(m.group(4)), maxs=int(m.group(5)), heap=int(m.group(6)))
for M in sorted(final):
    f = final[M]
    print(f"max={M}: outside={outside.get(M)} size={f['size']} maxSampled={f['maxs']} heapDelta={f['heap']} B ({f['heap']/MB:.2f} MB)")
pred = {0: (0, 16, 0, 2*MB), 100: (100, 1, 100+16, 2*MB), 100000: (100000, 16, 100000+16, None), 1000000: (600000, 16, 600000+16, None)}
for M, (sz, tol, maxs, hmax) in pred.items():
    if M not in final: print(f"MISSING max={M}"); ok = False; continue
    f = final[M]
    exp(outside.get(M) == 0, f"max={M}: outsideGroups size == 0 (got {outside.get(M)})")
    exp(abs(f['size'] - sz) <= tol, f"max={M}: estimatedSize = {sz} +-{tol} (got {f['size']})")
    exp(f['maxs'] <= maxs, f"max={M}: maxSampledSize <= {maxs} (got {f['maxs']})")
    if hmax is not None: exp(f['heap'] < hmax, f"max={M}: heapDelta < 2 MB (got {f['heap']/MB:.2f} MB)")
if 100000 in final: exp(8*MB <= final[100000]['heap'] <= 20*MB, f"max=100000: heapDelta in 8-20 MB (got {final[100000]['heap']/MB:.2f})")
if 1000000 in final: exp(50*MB <= final[1000000]['heap'] <= 110*MB, f"max=1000000: heapDelta in 50-110 MB (got {final[1000000]['heap']/MB:.2f})")
if 100000 in final and 1000000 in final and final[100000]['heap'] > 0:
    r = final[1000000]['heap'] / final[100000]['heap']
    exp(5 <= r <= 7, f"heapDelta(1e6)/heapDelta(1e5) in 5-7 (got {r:.2f})")
if 0 in final and 100 in final:
    exp(abs(final[100]['heap'] - final[0]['heap']) <= 2*MB, f"|heapDelta(100)-heapDelta(0)| <= 2 MB (got {(final[100]['heap']-final[0]['heap'])/MB:.2f})")
# per-entry bytes (informative)
if 100000 in final and 1000000 in final:
    per = (final[1000000]['heap'] - final[100000]['heap']) / (600000 - 100000)
    print(f"INFO bytes per entry from (1e6 - 1e5) delta, sketch difference included: {per:.1f}")
print("ALL EXPECTED HOLD" if ok else "SOME EXPECTED FAIL")
