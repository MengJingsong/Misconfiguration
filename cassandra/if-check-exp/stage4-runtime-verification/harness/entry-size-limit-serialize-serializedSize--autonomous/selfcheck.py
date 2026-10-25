#!/usr/bin/env python3
"""Independent re-parse of the raw files for the self-check (results section 5). Does not use analyze_*.py.
Usage: selfcheck.py <run1-dir>   (expects <run1-dir>/unit/{ant.log,raw/} and <run1-dir>/cluster/)"""
import sys, os, re, json, glob
run = sys.argv[1]; MiB = 1 << 20; bad = 0
def say(ok, m):
    global bad; print(('OK   ' if ok else 'BAD  ') + m); bad += (not ok)
# ---- unit: raw ant.log RESULT lines vs the per-arm 10 ms series ----
ant = open(os.path.join(run, 'unit/ant.log'), errors='replace').read()
say('Tests run: 1, Failures: 0, Errors: 0' in ant, 'ant.log: the probe test ran once without failure/error')
res = {}
for l in ant.splitlines():
    m = re.search(r'RESULT (.*)$', l)
    if m: d = dict(t.split('=', 1) for t in m.group(1).split() if '=' in t); res[d['arm']] = d
say(len(res) >= 14, 'ant.log carries %d RESULT lines (expected 14)' % len(res))
for arm, d in res.items():
    ser = [tuple(map(int, l.split(','))) for l in open(os.path.join(run, 'unit/raw/series-%s.csv' % arm)) if l.strip()]
    base = int(d['base_MiB']); pk = max(v for _, v in ser) // 1024 - base
    say(abs(pk - int(d['peak_delta_MiB'])) <= 2, '%s: peak from 10 ms series %d MiB vs RESULT %s (sampler window includes the settle after the body)' % (arm, pk, d['peak_delta_MiB']))
# independent restatement of the headline unit facts
g = lambda a, k: float(res[a][k])
say(res['guard_2147483647']['exception'] == 'none' and res['guard_2147483648']['message'] == '"Unable_to_allocate_2.000GiB"', 'guard: 2^31-1 passes, 2^31 throws with the filed message')
say(g('agg3072', 'peak_delta_MiB') > 2048 and g('over8x512MiB', 'peak_delta_MiB') > 2048, 'total native usage exceeded 2048 MiB (agg3072 %s, over8x512 %s) with every entry <= 1 MiB / 512 MiB' % (res['agg3072']['peak_delta_MiB'], res['over8x512MiB']['peak_delta_MiB']))
sl = (g('agg256', 'peak_delta_MiB') - g('agg64', 'peak_delta_MiB')) / 192
say(0.9 <= sl <= 1.1, 'slope of peak vs C (64..256) = %.3f' % sl)
# ---- cluster ----
cl = os.path.join(run, 'cluster')
if os.path.exists(cl):
    def rd(p): return [tuple(map(int, l.split(','))) for l in open(p).read().splitlines()[1:] if l.strip()]
    ph = {os.path.basename(p)[6:-5]: json.load(open(p)) for p in glob.glob(cl + '/phase-*.json')}
    for l, S in sorted(ph.items()):
        ev = os.path.join(cl, 'evidence-' + l)
        cmd = open(ev + '/cmdline.txt').read(); env = open(ev + '/environ.txt').read(); yk = open(ev + '/yaml-keys.txt').read()
        say('-Xmx2G' in cmd.replace('2048M', '2G') or '-Xmx2048M' in cmd or '-Xmx2G' in cmd, '%s: heap flag in cmdline: %s' % (l, re.findall(r'-Xm[sx]\w+', cmd)))
        say('AlwaysPreTouch' in cmd and 'MaxDirectMemorySize=256m' in cmd, '%s: AlwaysPreTouch and MaxDirectMemorySize=256m on the live command line' % l)
        say('MALLOC_ARENA_MAX=1' in env and 'MALLOC_MMAP_THRESHOLD_=65536' in env, '%s: malloc variables in the live environ' % l)
        say(('row_cache_size: %dMiB' % S['cap_mib']) in yk and 'SerializingCacheProvider' in yk, '%s: yaml row_cache_size %d MiB and provider' % (l, S['cap_mib']))
        stl = open(ev + '/system.log.startup').read()
        say('Initializing row cache with capacity of %d MiBs' % S['cap_mib'] in stl, '%s: startup line "Initializing row cache with capacity of %d MiBs"' % (l, S['cap_mib']))
        say(not S['errors_in_log'], '%s: no ERROR lines in system.log (%s)' % (l, S['errors_in_log'][:1]))
    # recompute the peak rise for the 64 KiB phases from the raw 100 ms samples with a different method (explicit loop)
    D = {}
    for l in ('c0', 'c64', 'c256', 'c1024'):
        if l not in ph: continue
        S = ph[l]; s = rd(os.path.join(cl, 'samples-%s.csv' % l)); a = S['marks']['pass1_start']; b = S['marks'].get('shrink_start', S['marks']['pass2_end'] + 8000)
        base = sum(v for t, v in s if t < a)  # mean of last 40 samples before pass 1
        pre = [v for t, v in s if t < a][-40:]; base = sum(pre) / len(pre)
        pk = 0
        for t, v in s:
            if a <= t <= b and v - base > pk: pk = v - base
        D[l] = pk / 1024
        inf = rd(os.path.join(cl, 'info-%s.csv' % l)); inw = [r for r in inf if a <= r[0] <= b]
        print('   %s: base %.1f MiB, D %.1f MiB, Size max %.1f MiB, last %.1f MiB (entries %d, cap %.0f MiB), RefCountedMemory %s' % (l, base / 1024, D[l], max(r[2] for r in inw) / MiB, inw[-1][2] / MiB, inw[-1][1], inw[-1][3] / MiB, ph[l]['refcounted']))
    if 'c0' in D:
        for l, C in (('c64', 64), ('c256', 256), ('c1024', 1024)):
            if l in D: say(0.8 * C <= D[l] - D['c0'] <= 1.25 * C + 64, '%s: D - D0 = %.1f MiB against C = %d' % (l, D[l] - D['c0'], C))
print('SELFCHECK-SUMMARY bad=%d' % bad)
