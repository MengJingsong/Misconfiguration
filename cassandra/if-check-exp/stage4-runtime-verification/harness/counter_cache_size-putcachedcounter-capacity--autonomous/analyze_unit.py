#!/usr/bin/env python3
"""Unit tier analysis against B2f / B2g of the three counter_cache_size autonomous cases.
Usage: analyze_unit.py <case: is|get|put> <unit.txt> [<label>]      (label: base | noguard; noguard prints the comparison lines only)
The thresholds are the ones filed in B2f (and the dated B2i amendment of each file); nothing here is tuned to a reading."""
import sys, re
MiB = 1048576
case, path = sys.argv[1], sys.argv[2]
label = sys.argv[3] if len(sys.argv) > 3 else 'base'
other = sys.argv[4] if len(sys.argv) > 4 else None     # with label 'compare': <base unit.txt> <noguard unit.txt> -> allocation comparison (B2i.7)
def kv(s): return {k: v for k, v in re.findall(r'(\S+?)=(\S+)', s)}
L = [l.strip() for l in open(path) if l.strip()]
U = lambda p: [(l, kv(l)) for l in L if l.startswith(p + ' ')]
fails = []
def chk(name, ok, detail):
    print('RESULT', 'PASS' if ok else 'FAIL', name, detail)
    if not ok: fails.append(name)
if label == 'compare':
    base = [kv(l) for l in open(path) if l.startswith('U2 ') and 'arm=' in l]
    ng = [kv(l) for l in open(other) if l.startswith('U2 ') and 'arm=' in l]
    b0 = [d for d in base if d['capMiB'] == '0'][0]; b1 = [d for d in base if d['capMiB'] == '1'][0]; n0 = [d for d in ng if d['capMiB'] == '0'][0]
    for what, key in (('put', 'putAllocPerCall'), ('get', 'getAllocPerCall')):
        a0, a1, an = int(b0[key]), int(b1[key]), int(n0[key])
        print('INFO %s alloc per call: base cap0=%d base cap1=%d noguard cap0=%d' % (what, a0, a1, an))
        print('RESULT', 'PASS' if (a1 - a0 >= 100 and an - a0 >= 100) else 'FAIL', 'B2i.7 %s: base cap0 at least 100 B/call below base cap1 (%d) and noguard cap0 (%d)' % (what, a1 - a0, an - a0))
    for what, d in (('base', b0), ('noguard', n0)):
        print('INFO', what, 'cap0 settled_size=%s settled_weighted=%s getHits=%s' % (d['settled_size'], d['settled_weighted'], d['getHits']))
    sys.exit(0)
u0 = kv(L[0]); initCap = int(u0['initCapacity'])
print('tree label:', label, 'init capacity', initCap)
def arms(part): return [d for l, d in U(part) if d.get('arm') is not None]
if case == 'is':
    rows = arms('U1')
    by = {}
    for d in rows: by.setdefault(d['capMiB'], []).append(d)
    for m in ('0', '1', '4'):
        for d in by[m]:
            cap = int(m) * MiB
            w = int(d['settled_weighted']); s = int(d['settled_size']); wi = int(d['immediate_weighted'])
            if label == 'base':
                chk('U1 cap%s helperCounter == (cap>0)' % m, d['helperCounter'] == str(cap > 0).lower(), 'helperCounter=%s' % d['helperCounter'])
            else:
                chk('U1 noguard cap%s helperCounter (patched >= 0: true at 0)' % m, d['helperCounter'] == 'true', 'helperCounter=%s' % d['helperCounter'])
            chk('U1 cap%s helperRegular false' % m, d['helperRegular'] == 'false', 'helperRegular=%s' % d['helperRegular'])
            chk('U1 cap%s weighted<=cap (settled and immediate)' % m, w <= cap and wi <= cap, 'settled=%d immediate=%d cap=%d' % (w, wi, cap))
            if cap == 0: chk('U1 cap0 retains nothing', w == 0 and s == 0, 'weighted=%d size=%d' % (w, s))
            else: chk('U1 cap%s reaches the cap (weighted >= cap - 2 entries)' % m, w >= cap - 2 * int(d['entryWeight']), 'weighted=%d cap=%d' % (w, cap))
    s1 = int(by['1'][0]['settled_size']); s4 = int(by['4'][0]['settled_size'])
    chk('U1 size(4 MiB)/size(1 MiB) about 4 (3.6..4.4)', 3.6 <= s4 / s1 <= 4.4, 'ratio=%.3f' % (s4 / s1))
    d = by['init'][0]; w = int(d['settled_weighted'])
    chk('U1 init arm (unit default) weighted<=capacity and reached', w <= int(d['settled_capacity']) and w >= int(d['settled_capacity']) - 2 * int(d['entryWeight']), 'weighted=%d capacity=%s' % (w, d['settled_capacity']))
elif case in ('get', 'put'):
    rows = arms('U2')
    by = {}
    for d in rows: by.setdefault(d['capMiB'], []).append(d)
    for m in ('0', '1', '4'):
        for d in by[m]:
            cap = int(m) * MiB
            w = int(d['settled_weighted']); s = int(d['settled_size']); wi = int(d['immediate_weighted']); n = int(d['puts'])
            chk('U2 cap%s weighted<=cap (settled and immediate)' % m, w <= cap and wi <= cap, 'settled=%d immediate=%d cap=%d' % (w, wi, cap))
            if cap == 0:
                chk('U2 cap0 size==0 weighted==0', w == 0 and s == 0, 'weighted=%d size=%d' % (w, s))
                chk('U2 cap0 every get returns null', int(d['getHits']) == 0, 'getHits=%s of %d' % (d['getHits'], n))
                if case == 'put': chk('U2 cap0 heap delta ~0 (|delta| < 1 MiB)', abs(int(d['heapDelta'])) < MiB, 'heapDelta=%s' % d['heapDelta'])
            else:
                chk('U2 cap%s size far below N' % m, s < 0.25 * n, 'size=%d N=%d' % (s, n))
                chk('U2 cap%s reaches the cap' % m, w >= cap - 2 * int(d['entryWeight']), 'weighted=%d cap=%d' % (w, cap))
                if case == 'get':
                    chk('U2 cap%s only recent keys hit (last yes, first no, hits==size)' % m, d['getLast'] == 'true' and d['getFirst'] == 'false' and int(d['getHits']) == s, 'hits=%s size=%d first=%s last=%s' % (d['getHits'], s, d['getFirst'], d['getLast']))
    s1 = int(by['1'][0]['settled_size']); s4 = int(by['4'][0]['settled_size'])
    chk('U2 size(4 MiB)/size(1 MiB) about 4 (3.6..4.4)', 3.6 <= s4 / s1 <= 4.4, 'ratio=%.3f' % (s4 / s1))
    if case == 'put':
        for m in ('1', '4'):
            for d in by[m]:
                hd = int(d['heapDelta']); w = int(d['settled_weighted'])
                print('INFO U2 cap%s heapDelta=%d weighted=%d ratio=%.2f' % (m, hd, w, hd / w))
    d = by['init'][0]; w = int(d['settled_weighted'])
    chk('U2 init arm weighted<=capacity and reached', w <= int(d['settled_capacity']) and w >= int(d['settled_capacity']) - 2 * int(d['entryWeight']), 'weighted=%d capacity=%s' % (w, d['settled_capacity']))
# production path (U3), reload (U4), resize (U5) apply to all three cases
for l, d in U('U3'):
    if 'updates' in d:
        cap = int(d['capMiB']) * MiB; w = int(d['settled_weighted'])
        chk('U3 production path cap%s weighted<=cap' % d['capMiB'], w <= cap, 'weighted=%d' % w)
        if cap == 0: chk('U3 cap0 production path keeps nothing', w == 0 and int(d['settled_size']) == 0, d['settled_size'])
        else: chk('U3 cap%s reaches cap (60,000 updates)' % d['capMiB'], w >= cap - 240, 'weighted=%d' % w)
    elif d.get('control') == 'regular-writes':
        chk('U3 regular-table writes leave counter cache empty', int(d['settled_size']) == 0 and d['helperRegular'] == 'false', l)
if case == 'is':
    for l, d in U('U4'):
        if 'loadSavedReturned' in d:
            cap = d['capMiB']; ret = int(d['loadSavedReturned']); w = int(d['settled_weighted']); c = int(d['settled_capacity'])
            if label == 'base':
                if cap == '0': chk('U4 reload cap0: helper false, nothing loaded', d['helperCounter'] == 'false' and ret == 0 and w == 0, l)
                else: chk('U4 reload cap%s: helper true, entries loaded, weighted<=cap' % cap, d['helperCounter'] == 'true' and ret > 0 and 0 < w <= c, l)
            else:
                if cap == '0': print('INFO U4 noguard reload cap0:', l)
                else: chk('U4 noguard reload cap%s weighted<=cap' % cap, w <= c, l)
for l, d in U('U5'):
    print('INFO', l)
print('\nFAILED CHECKS (%d): %s' % (len(fails), fails))
