#!/usr/bin/env python3
"""3-b R20: victim view per window. before = victim start .. load start (trigger.txt load_start); during = load start ..
daemon gone (first 'OOM line seen' / 'daemon gone' / 'client ended' in driver.txt); after = the rest.
Also 10-s timeline. Usage: vsum.py <run dir>"""
import os, re, sys, datetime as dt
R = sys.argv[1]
rows = []
for l in open(os.path.join(R, 'victim.txt')):
    if l.startswith('#') or not l.strip(): continue
    f = l.split(); rows.append([int(x) for x in f[:7]] + [None if x == '-' else float(x) for x in f[7:10]])
def ts(pat):
    for l in open(os.path.join(R, 'driver.txt')):
        if pat in l:
            return dt.datetime.fromisoformat(l.split()[0][:23] + '-07:00').timestamp()
tr = open(os.path.join(R, 'trigger.txt')).read() if os.path.exists(os.path.join(R, 'trigger.txt')) else ''
m = re.search(r'^load_start (\d+)', tr, re.M); t_load = int(m.group(1)) / 1000 if m else (ts('baseline done') or ts('S0A auth shakedown'))
m = re.search(r'^t_trig (\d+)', tr, re.M); t_trig = int(m.group(1)) / 1000 if m else None
t_oom = ts('OOM line seen'); t_gone = ts('daemon gone') or ts('client ended')
t_end = t_oom or t_gone
print('t_load %.1f  t_trig %s  t_oom(line seen) %s  daemon-gone %s' % (t_load, ('+%.1f' % (t_trig - t_load)) if t_trig else '-',
      ('+%.1f' % (t_oom - t_load)) if t_oom else '-', ('+%.1f' % (t_gone - t_load)) if t_gone else '-'))
def win(name, a, b):
    w = [r for r in rows if a <= r[0] < b]
    if not w: print('%-8s (empty)' % name); return
    s = lambda i: sum(r[i] for r in w)
    slots = s(1) + s(6); ok = s(2)
    p50 = sorted(r[7] for r in w if r[7] is not None); mx = [r[9] for r in w if r[9] is not None]
    full = sum(1 for r in w if r[2] >= 19)
    print('%-8s %4d s  slots %5d  ok %5d (%.1f %%)  err %d  timeout %d  connfail %d  missed %d  median p50 %s ms  max %s ms  seconds with >= 19/20 ok: %d/%d' % (
        name, len(w), slots, ok, 100.0 * ok / slots if slots else 0, s(3), s(4), s(5), s(6),
        ('%.1f' % p50[len(p50) // 2]) if p50 else '-', ('%.0f' % max(mx)) if mx else '-', full, len(w)))
t0 = rows[0][0]; t9 = rows[-1][0] + 1
win('before', t0, t_load)
if t_trig:
    win('load', t_load, t_trig); win('trig->end', t_trig, t_end or t9)
else:
    win('during', t_load, t_end or t9)
if t_end: win('after', t_end, t9)
print('10-s timeline (offset from load start: slots ok err timeout connfail missed max_ms)')
for a in range(int(t0), int(t9), 10):
    w = [r for r in rows if a <= r[0] < a + 10]
    if not w: continue
    mx = [r[9] for r in w if r[9] is not None]
    print('  %+7.0f  %4d %4d %3d %3d %4d %4d %s' % (a - t_load, sum(r[1] for r in w), sum(r[2] for r in w), sum(r[3] for r in w),
          sum(r[4] for r in w), sum(r[5] for r in w), sum(r[6] for r in w), ('%.0f' % max(mx)) if mx else '-'))
