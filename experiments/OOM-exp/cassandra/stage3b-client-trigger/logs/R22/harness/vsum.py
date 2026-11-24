#!/usr/bin/env python3
"""R22 3-b confirm (pc72, 2026-11-23): the victim tenant's view per window, from <run>/logs/victim.csv (one row per second of
completions: epoch,w_sent,w_ok,w_to,w_err,r_sent,r_ok,r_to,r_err,skipped,inflight,p50_ms,p99_ms,max_ms,err) and the
driver.log marks (victim started, fill start, W start, W stop). Optional OOM time (seconds after W start) splits W.
  vsum.py <run dir> [oom_at_W_s]"""
import sys

run = sys.argv[1]
oom = float(sys.argv[2]) if len(sys.argv) > 2 else None
marks = {}
for l in open(run + '/logs/driver.log'):
    p = l.split()
    for key, tag in (('victim', 'victim started'), ('fill', 'fill start'), ('W0', ' W start '), ('W1', ' W stop: '), ('vstop', 'victim stopped')):
        if tag in l and key not in marks:
            marks[key] = float(p[0])
V = []
for l in open(run + '/logs/victim.csv').read().splitlines()[1:]:
    f = l.split(',', 14)
    V.append([int(x) for x in f[:14]] + [f[14] if len(f) > 14 else ''])
w0, w1 = marks.get('W0'), marks.get('W1')
wins = [('before (victim only, 60 s)', marks['victim'] + 5, marks['fill']), ('attack fill + quiesce', marks['fill'], w0)]
if oom is not None:
    wins += [('attack W until OOM', w0, w0 + oom), ('OOM -> JVM gone (heap dump)', w0 + oom, w1)]
else:
    wins += [('attack W', w0, w1)]
wins += [('after (node down)', w1, V[-1][0] + 1)]
print('marks:', {k: round(v - w0, 1) for k, v in marks.items()}, '(s from W start)')


def summ(name, w):
    if not w:
        print('  %s: no seconds' % name)
        return
    s = [sum(x[i] for x in w) for i in range(1, 10)]
    ws, wok, wto, wer, rs, rok, rto, rer, sk = s
    wd, rd = wok + wto + wer, rok + rto + rer
    p99 = [x[12] for x in w if x[12] >= 0]
    mx = [x[13] for x in w if x[13] >= 0]
    p50 = sorted(x[11] for x in w if x[11] >= 0)
    z = sum(1 for x in w if x[2] + x[6] == 0)
    print('  %s: %d s | writes sent %d, ok %d, timeout %d, error %d (ok %.1f %% of completed) | reads sent %d, ok %d, timeout %d, error %d (ok %.1f %%) | '
          'skipped %d | s with 0 ok: %d | p50 median %s ms, p99 max %s ms, max %s ms | inflight max %d' % (
              name, len(w), ws, wok, wto, wer, 100.0 * wok / wd if wd else float('nan'), rs, rok, rto, rer, 100.0 * rok / rd if rd else float('nan'),
              sk, z, p50[len(p50) // 2] if p50 else 'NA', max(p99) if p99 else 'NA', max(mx) if mx else 'NA', max(x[10] for x in w)))
    errs = [x[14] for x in w if x[14]]
    for e in list(dict.fromkeys(errs))[:4]:
        print('      err: %s' % e)


for name, t0, t1 in wins:
    summ(name, [x for x in V if t0 <= x[0] < t1])
print('per 60 s of W:')
t = w0
while t < w1:
    summ('W+%d..%d' % (t - w0, min(t + 60, w1) - w0), [x for x in V if t <= x[0] < min(t + 60, w1)])
    t += 60
for x in V:
    if x[0] >= w0 and (x[3] + x[4] + x[7] + x[8] > 0 or x[13] > 1000):
        print('first degraded victim second: W+%d (w ok %d to %d err %d, r ok %d to %d err %d, max %d ms)' % (x[0] - w0, x[2], x[3], x[4], x[6], x[7], x[8], x[13]))
        break
