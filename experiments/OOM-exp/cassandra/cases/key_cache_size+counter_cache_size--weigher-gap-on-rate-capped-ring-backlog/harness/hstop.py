#!/usr/bin/env python3
# R19 (2026-11-21, case file §2.5): heap after GC at STOP, from V's gc.log (`time` decoration) and the client's
# FIRST_SEND / TOTAL_REACHED epoch ms.   hstop.py <evidence run dir>   (reads <dir>/V/gc.log*, <dir>/client/load.log)
# Prints one line:
#   h_stop=<MiB after GC of the last pause ending at or before STOP+5 s | censored (V died before STOP) | -> no STOP>
#   stop_s=<STOP - first send> max_after_any=<MiB in [first send, STOP+15 s]> max_after_full=<MiB, same window>
#   oom_mark_after_send=<s> oom_mark_after_stop=<s>   (first HeapDumper / ReportJavaOutOfMemory safepoint)
import glob, re, sys, datetime
d = sys.argv[1].rstrip('/') + '/'
cl = open(d + 'client/load.log', errors='replace').read() if glob.glob(d + 'client/load.log') else ''
fs = re.search(r'^FIRST_SEND epochMs=(\d+)', cl, re.M); tr = re.search(r'^TOTAL_REACHED t=(\d+) sent=(\d+) ok=(\d+) epochMs=(\d+)', cl, re.M)
t0 = int(fs.group(1)) / 1000 if fs and int(fs.group(1)) > 0 else None
ts = int(tr.group(4)) / 1000 if tr else None
TP = re.compile(r'^\[(\d{4}-\d\d-\d\dT[\d:.]+)([-+]\d{4})\]')
pauses = []; marks = []
for f in sorted(glob.glob(d + 'V/gc.log*')):
    for line in open(f, errors='replace'):
        m = TP.match(line)
        if not m: continue
        t = datetime.datetime.strptime(m.group(1) + m.group(2), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp()
        if 'safepoint region: HeapDumper' in line or 'safepoint region: ReportJavaOutOfMemory' in line:
            marks.append(t); continue
        if ' Pause ' in line:
            a = re.search(r'(\d+)M->(\d+)M\((\d+)M\) [\d.]+ms\s*$', line)
            if a: pauses.append((t, int(a.group(2)), 'Pause Full' in line))
pauses.sort(); mk = min(marks) if marks else None
out = []
if ts is None:
    out.append('h_stop=- (no TOTAL_REACHED)')
elif mk is not None and mk < ts:
    out.append('h_stop=censored (OOM mark before STOP)')
else:
    pre = [p for p in pauses if p[0] <= ts + 5]
    out.append(f'h_stop={pre[-1][1]} (pause {pre[-1][0] - ts:+.1f} s from STOP)' if pre else 'h_stop=- (no pause)')
if t0 is not None and ts is not None: out.append(f'stop_s={ts - t0:.1f}')
if t0 is not None:
    hi = (ts + 15) if ts is not None else float('inf')
    w = [p for p in pauses if t0 <= p[0] <= hi]
    out.append(f'max_after_any={max((p[1] for p in w), default="-")}')
    out.append(f'max_after_full={max((p[1] for p in w if p[2]), default="-")} n_full={sum(1 for p in w if p[2])}')
    out.append(f'oom_mark_after_send={(mk - t0):.1f}' if mk else 'oom_mark_after_send=-')
    out.append(f'oom_mark_after_stop={(mk - ts):.1f}' if (mk and ts) else 'oom_mark_after_stop=-')
print(' '.join(out))
