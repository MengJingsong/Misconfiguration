# Compare probe-<v>.txt with case B2f (predictions computed with the same functions as the source).
import re, sys, os
O = sys.argv[1]
CAP = {'v32': 1 << 15, 'v64': 1 << 16, 'v1m': 1 << 20}
K = 32; NORMAL_CHUNK = 128 << 10
def rbs(size, cap):
    if size <= 0: return 4096
    size = (size + 4095) & ~4095
    return min(size, cap)
def ssd(r, cap):
    if (r % 4096) / 4096. - 0.1 > -1e-16: r += 4096
    return rbs(r, cap)
def spin(r, cap): return rbs(r + 4096, cap)
def rfc(size, cap, up=False):
    if size <= 4096: return 4096
    ret = (1 << (size - 1).bit_length()) if up else (1 << (size.bit_length() - 1))
    return min(cap, ret)
ok_all = True
print('| v | strategy | r | bufferSize obs/pred | chunk obs/pred | bufCap | dUsed | dOverflow obs/pred | perReader | row ok |')
print('|---|---|---|---|---|---|---|---|---|---|')
summary = {}
for v in ('v64', 'v32', 'v1m'):
    p = os.path.join(O, 'probe-%s.txt' % v)
    lines = open(p).read().split('\n')
    mx = [l for l in lines if l.startswith('PROBE MAX_BUFFER_SIZE=')]
    mval = int(mx[0].split('=')[1]) if mx else None
    if mval != CAP[v]: ok_all = False
    print('| %s | MAX_BUFFER_SIZE printed = %s (expect %d) | | | | | | | | %s |' % (v, mval, CAP[v], 'yes' if mval == CAP[v] else 'NO'))
    for l in lines:
        m = re.match(r'PROBE strategy=(\S+) r=(\d+) bufferSize=(\d+) chunk=(\d+) bufCap=(\d+) dUsed=(-?\d+) dOverflow=(-?\d+) perReader=(-?\d+)', l)
        if not m: continue
        st, r, bs, ch, cap_, du, do, pr = m.group(1), *map(int, m.groups()[1:])
        f = ssd if st.startswith('Ssd') else spin
        pbs = f(r, CAP[v]); pch = rfc(pbs, CAP[v]); pdo = K * pch if pch > NORMAL_CHUNK else 0
        ok = (bs == pbs and ch == pch and cap_ == pch and du == K * pch and do == pdo and pr == pch)
        ok_all &= ok
        summary[(v, st, r)] = pr
        print('| %s | %s | %d | %d / %d | %d / %d | %d | %d | %d / %d | %d | %s |' % (v, st[:4], r, bs, pbs, ch, pch, cap_, du, do, pdo, pr, 'yes' if ok else 'NO'))
print()
for st in ('SsdDiskOptimizationStrategy', 'SpinningDiskOptimizationStrategy'):
    for r in (1 << 20, 16 << 20):
        print('perReader %s r=%d: v32=%s v64=%s v1m=%s' % (st[:4], r, summary.get(('v32', st, r)), summary.get(('v64', st, r)), summary.get(('v1m', st, r))))
mx64 = max(pr for (v, st, r), pr in summary.items() if v == 'v64') if summary else None
print('max perReader on v64 over all rows: %s' % mx64)
small_same = all(summary.get(('v32', st, r)) == summary.get(('v64', st, r)) == summary.get(('v1m', st, r)) for st in ('SsdDiskOptimizationStrategy', 'SpinningDiskOptimizationStrategy') for r in (1000, 10000))
print('small-r rows (1000, 10000) identical across variants: %s' % small_same)
print('ALL ROWS MATCH B2f: %s' % ok_all)
