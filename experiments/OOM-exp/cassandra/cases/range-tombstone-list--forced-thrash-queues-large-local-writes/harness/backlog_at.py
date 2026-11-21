# backlog_blob at given W offsets (s): sum of three blob clients' issued - r22.blob applied (poll), per run
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
B = '/mydata/s4/r22/'
def cum(p):
    d = {}
    for l in open(p).read().splitlines()[1:]:
        v = list(map(int, l.split(','))); d[v[0]] = v[1:]
    return d
def at(d, t):
    ks = [k for k in d if k <= t]; return d[max(ks)] if ks else None
for run in sys.argv[1:]:
    L = B + run + '/logs/'
    ws = [float(l.split()[0]) for l in open(L + 'driver.log') if ' W start ' in l][0]
    lines = open(L + 'poll.log').read().splitlines(); hdr = lines[0].split()
    rows = [dict(zip(hdr, map(int, l.split()))) for l in lines[1:] if len(l.split()) == len(hdr)]
    rows = [r for r in rows if r['wl_blob'] >= 0]
    pre = [r for r in rows if r['epoch_ms'] < ws * 1000][-1]
    bl = [cum(L + 'blob%d.csv' % j) for j in range(3)]
    out = []
    for off in (30, 60, 90, 120, 140, 180, 240, 300):
        cand = [r for r in rows if r['epoch_ms'] <= (ws + off) * 1000]
        if not cand or cand[-1]['epoch_ms'] < (ws + off - 5) * 1000:
            out.append('%d:n/a' % off); continue
        r = cand[-1]; t = r['epoch_ms'] // 1000
        iss = sum((at(b, t) or [0])[0] for b in bl)
        out.append('%d:%d' % (off, iss - (r['wl_blob'] - pre['wl_blob'])))
    print(run, ' '.join(out))
