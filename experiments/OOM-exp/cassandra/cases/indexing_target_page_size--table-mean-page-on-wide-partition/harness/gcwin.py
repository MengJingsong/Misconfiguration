#!/usr/bin/env python3
# Service-loss check over all stop-the-world pauses (protocol default: >= 90% of wall in STW over >= 60 s).
# Linear-time rewrite of B6 run-4 gcwin.py (same parsing, same criterion) for logs with thousands of pauses.
#   gcwin.py <dir-with-gc.log*>
# Reports pauses, total pause, Full GC count, max STW fraction over any 60 s window (sampled at 1 s), the
# longest window >= 60 s with fraction >= 90% (computed on a 0.1 s grid), and HeapDumper/OOM safepoints.
import glob, re, sys
iv = []; marks = []; full = 0
pat = re.compile(r'\]\[([0-9.]+)s\].*Pause .* ([0-9.]+)ms$')
for f in sorted(glob.glob(sys.argv[1] + '/gc.log*')):
    for line in open(f, errors='replace'):
        m = pat.search(line.rstrip())
        if m:
            end = float(m.group(1)); ms = float(m.group(2)); iv.append((end - ms / 1000, end))
            if 'Pause Full' in line and 'Diagnostic' not in line: full += 1
        elif 'safepoint region: HeapDumper' in line or 'safepoint region: ReportJavaOutOfMemory' in line:
            marks.append(line.split('region: ')[1].strip() + '@' + re.search(r'\]\[([0-9.]+)s\]', line).group(1) + 's')
if not iv:
    print('no pauses'); sys.exit()
G = 0.1
T = int(max(e for _, e in iv) / G) + 2
cov = [0.0] * T
for s, e in iv:
    i = int(s / G)
    while i * G < e and i < T:
        cov[i] += max(0.0, min(e, (i + 1) * G) - max(s, i * G)); i += 1
pre = [0.0] * (T + 1)
for i in range(T): pre[i + 1] = pre[i] + min(cov[i], G)
W = int(60 / G)
best60 = max(((pre[i + W] - pre[i]) / 60 for i in range(0, T - W + 1)), default=0)
# longest window >= 60 s with fraction >= 0.9: f(i,j) = pre[j]-pre[i] >= 0.9*(j-i)*G  <=>  g[j] >= g[i], g[k] = pre[k] - 0.9*k*G
g = [pre[k] - 0.9 * k * G for k in range(T + 1)]
longest = 0; lw = None
# for each i, the largest j with g[j] >= g[i]: suffix max scan
sufmax = [0.0] * (T + 2); sufmax[T + 1] = -1e18
for k in range(T, -1, -1): sufmax[k] = max(g[k], sufmax[k + 1])
j = 0
for i in range(T + 1):
    j = max(j, i)
    while j + 1 <= T and sufmax[j + 1] >= g[i]: j += 1
    if (j - i) * G >= 60 and (j - i) * G > longest:
        longest = (j - i) * G; lw = (i * G, j * G, pre[j] - pre[i])
tot = sum(e - s for s, e in iv)
sl = 'MET' if longest >= 60 else 'not met'
w = f'{lw[0]:.0f}-{lw[1]:.0f}s ({lw[2]:.0f}s paused)' if lw else '-'
print(f'pauses={len(iv)} full_gcs={full} total_pause={tot:.0f}s max60={100*best60:.0f}% longest>=90%win={longest:.0f}s {w} service_loss(all STW)={sl} oom_marks={",".join(marks) or "none"}')
