#!/usr/bin/env python3
"""Unit tier analysis against B2f (as amended B2i). Usage: analyze_unit.py <obs.txt>. Prints RESULT lines and a per-point table."""
import sys, re, collections
MiB = 1024 * 1024
obs = [l[4:].strip() for l in open(sys.argv[1]) if l.startswith('OBS ')]
def kv(s): return {k: v for k, v in re.findall(r'(\S+?)=(\S+)', s)}
pts = collections.OrderedDict(); ctl = []; clr = collections.OrderedDict()
for o in obs:
    d = kv(o)
    m = re.match(r'C=(\d+)MiB S=(\d+) rep=(\d+) phase=(\w+)', o)
    if m: pts.setdefault((int(m[1]), int(m[2]), int(m[3])), {})[m[4]] = d; continue
    m = re.match(r'clear rep=(\d+) phase=(\w+)', o)
    if m: clr.setdefault(int(m[1]), {})[m[2]] = d; continue
    if o.startswith('control='): ctl.append((o.split()[0].split('=')[1], d, o))
fails = []
def chk(name, ok, detail):
    print('RESULT', 'PASS' if ok else 'FAIL', name, detail)
    if not ok: fails.append(name)
print('points:', len(pts), 'control lines:', len(ctl), 'clear reps:', len(clr))
tab = []
for (C, S, rep), p in pts.items():
    Cb = C * MiB
    f, g, c, h = p['fill'], p['get'], p['concurrent'], p['setCapacityHalf']
    w, size = int(f['weighted']), int(f['size'])
    chk('C%d_S%d_r%d fill weighted<=C' % (C, S, rep), w <= Cb, 'weighted=%d cap=%d' % (w, Cb))
    chk('C%d_S%d_r%d fill weighted>=C-S-4' % (C, S, rep), w >= Cb - S - 4, 'weighted=%d floor=%d' % (w, Cb - S - 4))
    exp = Cb // (S + 4)
    chk('C%d_S%d_r%d size~C/(S+4)' % (C, S, rep), abs(size - exp) <= 1 + 0.01 * exp, 'size=%d expected=%d' % (size, exp))
    d = int(f['rssAnonDelta'])
    lo, hi = (0.8 * Cb, Cb + 48 * MiB) if C == 16 else (0.9 * Cb, Cb + 64 * MiB)
    chk('C%d_S%d_r%d fill RssAnon delta in range' % (C, S, rep), lo <= d <= hi, 'delta=%.1fMiB range=[%.1f,%.1f]MiB' % (d / MiB, lo / MiB, hi / MiB))
    chk('C%d_S%d_r%d get hits<=size' % (C, S, rep), int(g['hits']) <= int(g['size']), 'hits=%s size=%s' % (g['hits'], g['size']))
    chk('C%d_S%d_r%d concurrent maxWeighted<=C' % (C, S, rep), int(c['maxWeighted']) <= Cb, 'max=%s cap=%d' % (c['maxWeighted'], Cb))
    pk = int(c['peakRssDelta']); lim = Cb + 16 * (S + 4) + 64 * MiB
    chk('C%d_S%d_r%d concurrent peak RssAnon<=C+16(S+4)+64MiB' % (C, S, rep), pk <= lim, 'peak=%.1fMiB limit=%.1fMiB' % (pk / MiB, lim / MiB))
    chk('C%d_S%d_r%d setCapacity(C/2) weighted<=C/2' % (C, S, rep), int(h['weighted']) <= Cb // 2, 'weighted=%s half=%d' % (h['weighted'], Cb // 2))
    tab.append((C, S, rep, w / MiB, size, d / MiB, int(c['maxWeighted']) / MiB, pk / MiB, int(c['endRssDelta']) / MiB))
print('\nC_MiB S rep weighted_MiB size fillRssDelta_MiB concMaxWeighted_MiB concPeakRss_MiB concEndRss_MiB')
for t in tab: print('%d %d %d %.2f %d %.1f %.2f %.1f %.1f' % t)
# tracking across C for each S: median fill delta increases with C
print()
for S in (4096, 262144, 4194304):
    med = {}
    for C in (16, 64, 256):
        v = sorted(int(pts[(C, S, r)]['fill']['rssAnonDelta']) for r in (1, 2, 3) if (C, S, r) in pts)
        med[C] = v[len(v) // 2] / MiB if v else None
    ok = None not in med.values() and med[16] < med[64] < med[256]
    chk('S%d median fill RssAnon delta rises with C' % S, ok, str({k: round(x, 1) for k, x in med.items()}))
# controls
for kind, d, o in ctl:
    if kind == 'singleton': chk('control singleton S=%s r%s holds exactly 4' % (d['S'], d['rep']), d['size'] == '4' and d['weighted'] == '4', o)
    elif kind == 'zero-capacity': chk('control C=0 r%s keeps nothing' % d['rep'], d['size'] == '0' and d['weighted'] == '0', o)
    elif kind == 'huge-entry': chk('control 2^31 entry r%s rejected' % d['rep'], d['result'].startswith('IllegalArgumentException') and d['size'] == '0', o)
# clear arm
Cb = 64 * MiB
for rep, p in clr.items():
    ac, f2 = p['afterClear'], p['fill2']
    chk('clear r%d weighted==0,size==0' % rep, ac['weighted'] == '0' and ac['size'] == '0', str(ac))
    pk = int(f2['peakRssDelta'])
    verdict = 'LEAK(>=1.7C)' if pk >= 1.7 * Cb else ('NO_LEAK(<=C+64MiB)' if pk <= Cb + 64 * MiB else 'INDETERMINATE')
    print('RESULT INFO clear r%d fill1Delta=%.1fMiB afterClearDelta=%.1fMiB fill2Peak=%.1fMiB 1.7C=%.1fMiB -> %s' % (rep, int(p['fill1']['rssAnonDelta']) / MiB, int(ac['rssAnonDelta']) / MiB, pk / MiB, 1.7 * Cb / MiB, verdict))
print('\nFAILED CHECKS (%d): %s' % (len(fails), fails))
