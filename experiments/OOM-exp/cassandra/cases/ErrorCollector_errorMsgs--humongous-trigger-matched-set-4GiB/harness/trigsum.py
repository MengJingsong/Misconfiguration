#!/usr/bin/env python3
"""R20 (R15's + wave 2: t_det2, t_trig2, t_OOM - t_trig2). R15: trigger summary of a run dir. From trigger.txt (load_start, t_det, t_trig, trigger responses), driver.txt (first
OOM line seen, 1-s resolution) and gc.log* (Pause Full lines with region counts: free regions = heap regions - used
after GC). Prints offsets from load start, t_OOM - t_trig, the last Full GCs before the trigger and the GCs after it.
Usage: trigsum.py <run dir>"""
import glob, os, re, sys, datetime as dt
def iso(a, z): return dt.datetime.fromisoformat(a + z[:3] + ':' + z[3:])
R = sys.argv[1]
def rd(n):
    try: return open(os.path.join(R, n), errors='replace').read()
    except OSError: return ''
tt = rd('trigger.txt'); drv = rd('driver.txt')
def ms(pat):
    m = re.search(pat, tt, re.M); return int(m.group(1)) / 1000 if m else None
t_load = ms(r'^load_start (\d+)'); t_det = ms(r'^t_det (\d+)'); t_trig = ms(r'^t_trig (\d{10,})') or ms(r'^t_trig\(no send[^)]*\) (\d{10,})')
t_det2 = ms(r'^t_det2 (\d+)'); t_trig2 = ms(r'^t_trig2 (\d+)')
if t_load and (t_det2 or t_trig2):
    print('wave 2: t_det2 %s; t_trig2 %s' % ('+%.1f s' % (t_det2 - t_load) if t_det2 else ('undetected' if 'undetected2' in tt else '-'),
                                          '+%.1f s' % (t_trig2 - t_load) if t_trig2 else '-'))
print('trigger: load_start %s; t_det %s; t_trig %s' % (
    t_load and dt.datetime.fromtimestamp(t_load).strftime('%H:%M:%S'),
    '+%.1f s' % (t_det - t_load) if t_det and t_load else ('undetected' if 'undetected' in tt else '-'),
    '+%.1f s' % (t_trig - t_load) if t_trig and t_load else '-'))
for l in tt.splitlines():
    if l.startswith(('trig', '  fired', 'undetected', '#')) and not l.startswith('t_trig'): print('  ' + l[:220])

m = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)(-0700) OOM line seen', drv)
t_oom = iso(m.group(1), m.group(2)).timestamp() if m else None
if t_oom:
    print('OOM line seen at +%.1f s after load start; t_OOM - t_trig = %s' % (
        t_oom - (t_load or t_oom), '%.1f s' % (t_oom - t_trig) if t_trig else '- (no trigger)'))
    if t_trig2: print('t_OOM - t_trig2 = %.1f s' % (t_oom - t_trig2))
heapm = re.search(r'-Xmx(\d+)([GMgm])', rd('vm-cmdline.txt'))
regions = None
if heapm:
    regions = int(heapm.group(1)) * (1024 if heapm.group(2) in 'Gg' else 1) // 16
pat = re.compile(r'^\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)(-0700)\]\[[\d.]+s\]\[\d+\]\[\d+\]\[info\s*\] GC\((\d+)\) (Pause [^\n]*?) (\d+)M->(\d+)M\((\d+)M\) (\d+\.\d+)ms', re.M)
rpat = re.compile(r'GC\((\d+)\) (Eden|Survivor|Old|Archive|Humongous) regions: (\d+)->(\d+)')
ev = {}; reg = {}
for f in glob.glob(os.path.join(R, 'gc.log*')):
    s = open(f, errors='replace').read()
    for m in pat.finditer(s):
        ev[int(m.group(3))] = (iso(m.group(1), m.group(2)).timestamp(), m.group(4), int(m.group(5)), int(m.group(6)), float(m.group(8)))
    for m in rpat.finditer(s):
        reg.setdefault(int(m.group(1)), {})[m.group(2)] = int(m.group(4))
def line(g):
    t, kind, b, a, p = ev[g]; r = reg.get(g, {})
    used = sum(r.values()) if r else None
    free = (regions - used) if (regions and used is not None) else None
    return 'GC(%d) %s %s %dM->%dM %.0f ms; regions after: %s; free regions %s' % (
        g, ('+%.1f s' % (t - t_load)) if t_load else '', kind[:60], b, a, p,
        ' '.join('%s %d' % (k[:3], v) for k, v in sorted(r.items())), free)
ids = sorted(ev)
for lab, tt_ in (('t_trig', t_trig), ('t_trig2', t_trig2)):
  if tt_ and ids:
    before = [g for g in ids if ev[g][0] <= tt_ and 'Full' in ev[g][1]]
    print('last Full GCs before %s (%d Full GCs before it):' % (lab, len(before)))
    for g in before[-3:]: print('  ' + line(g))
    after = [g for g in ids if ev[g][0] > tt_]
    print('GCs after %s (%d):' % (lab, len(after)))
    for g in after[:12]: print('  ' + line(g))
if not (t_trig or t_trig2) and ids:
    full = [g for g in ids if 'Full' in ev[g][1]]
    print('last Full GCs (no trigger):')
    for g in full[-3:]: print('  ' + line(g))
print('stw:', os.popen('python3 -I %s %s 2>&1' % (os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stw.py'), R)).read().strip())
