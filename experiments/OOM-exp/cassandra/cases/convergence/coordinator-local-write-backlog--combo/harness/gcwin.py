#!/usr/bin/env python3
# Protocol service-loss check over ALL stop-the-world G1 pauses (B6 run 4).
#   gcwin.py <dir-with-gc.log*>
# Pause interval = [uptime - ms, uptime] of each "Pause ..." line. Reports: total pause time, the max
# pause fraction over any 60 s window, and the longest window (>= 60 s, starting at a pause start) with
# pause fraction >= 90% (the protocol's default criterion), plus the HeapDumper / ReportJavaOutOfMemory
# safepoints (heap OOM evidence when Cassandra's own log is starved).
import glob, re, sys
iv = []; marks = []
pat = re.compile(r'\]\[([0-9.]+)s\].*Pause .* ([0-9.]+)ms$')
for f in sorted(glob.glob(sys.argv[1] + '/gc.log*')):
    for line in open(f, errors='replace'):
        m = pat.search(line.rstrip())
        if m:
            end = float(m.group(1)); ms = float(m.group(2)); iv.append((end - ms / 1000, end))
        elif 'safepoint region: HeapDumper' in line or 'safepoint region: ReportJavaOutOfMemory' in line:
            marks.append(line.split('region: ')[1].strip() + '@' + re.search(r'\]\[([0-9.]+)s\]', line).group(1) + 's')
iv.sort()
def paused(a, b):
    return sum(max(0, min(e, b) - max(s, a)) for s, e in iv if e > a and s < b)
tot = sum(e - s for s, e in iv)
best60 = max((paused(s, s + 60) / 60 for s, _ in iv), default=0)
longest = 0; lw = None
last = iv[-1][1] if iv else 0
for s, _ in iv:
    # extend the window end over pause ends while the fraction stays >= 90%
    for _, e in reversed(iv):
        if e - s < 60: break
        if paused(s, e) / (e - s) >= 0.9:
            if e - s > longest: longest = e - s; lw = (s, e, paused(s, e))
            break
sl = 'MET' if longest >= 60 else 'not met'
w = f'{lw[0]:.0f}-{lw[1]:.0f}s ({lw[2]:.0f}s paused)' if lw else '-'
print(f'pauses={len(iv)} total_pause={tot:.0f}s max60={100*best60:.0f}% longest>=90%win={longest:.0f}s {w} service_loss(all STW)={sl} oom_marks={",".join(marks) or "none"}')
