#!/usr/bin/env python3
"""Cluster tier analysis against B3f / B3g (and B3i of each file). Usage: analyze_cluster.py <case: is|get|put> <outdir>
Thresholds are those filed in B3f and made numeric in B3i.6 before the run; nothing here is tuned to a reading."""
import sys, os, re, csv, json, glob
MiB = 1048576
case, out = sys.argv[1], sys.argv[2]
fails = []
def chk(name, ok, detail):
    print('RESULT', 'PASS' if ok else 'FAIL', name, detail)
    if not ok: fails.append(name)
def samples(arm):
    return list(csv.DictReader(open(os.path.join(out, arm, 'samples.csv'))))
def hist(arm, f):
    d = {}
    for l in open(os.path.join(out, arm, f)):
        m = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
        if m: d[m[3]] = (int(m[1]), int(m[2]))
    return d
def used_kb(arm, tag):
    t = open(os.path.join(out, arm, 'heapinfo-%s.txt' % tag)).read()
    return int(re.search(r'used (\d+)K', t)[1])
def phase(arm, ph):
    return [s for s in samples(arm) if s['phase'] == ph][-1]
CK, CAC = 'org.apache.cassandra.cache.CounterCacheKey', 'org.apache.cassandra.db.ClockAndCount'
W = 120
CAP = {'c0': 0, 'c1': 1 * MiB, 'c8': 8 * MiB, 'c64': 64 * MiB, 'cdef': 50 * MiB, 'c8b': 8 * MiB}
have = [a for a in CAP if os.path.isdir(os.path.join(out, a))]
info = {}
for a in have:
    S = samples(a); cap = CAP[a]
    sz = [int(s['size']) for s in S]; en = [int(s['entries']) for s in S]; cp = {int(s['capacity']) for s in S}
    chk('%s capacity at every sample = %d' % (a, cap), cp == {cap}, str(cp))
    chk('%s Size <= Capacity at every sample (%d samples)' % (a, len(S)), max(sz) <= cap, 'max=%d cap=%d' % (max(sz), cap))
    e1 = phase(a, 'end-pass1'); e2 = phase(a, 'end-pass2')
    if cap == 0:
        chk('%s Entries 0 and Size 0 at every sample, Hits 0' % a, max(en) == 0 and max(sz) == 0 and all(int(s['hits']) == 0 for s in S), 'max entries=%d' % max(en))
        hs = sorted(glob.glob(os.path.join(out, a, 'hist-*.txt')))
        n = sum(hist(a, os.path.basename(h)).get(CK, (0, 0))[0] for h in hs)
        # ClockAndCount has one static instance (ClockAndCount.BLANK) that is not a cache entry; an entry would add instances
        chk('%s no CounterCacheKey instances, and at most the 1 static ClockAndCount, in any of %d histograms' % (a, len(hs)), n == 0 and all(hist(a, os.path.basename(h)).get(CAC, (0, 0))[0] <= 1 for h in hs), 'CounterCacheKey instances=%d, ClockAndCount max=%d' % (n, max(hist(a, os.path.basename(h)).get(CAC, (0, 0))[0] for h in hs)))
    else:
        chk('%s Size reaches cap at end of pass 1 (>= cap - 240)' % a, int(e1['size']) >= cap - 2 * W, 'size=%s cap=%d' % (e1['size'], cap))
        chk('%s Entries = cap//120 +-2 at end of pass 1' % a, abs(int(e1['entries']) - cap // W) <= 2, 'entries=%s expected=%d' % (e1['entries'], cap // W))
        h = hist(a, 'hist-end-pass2.txt'); ck, cac = h.get(CK, (0, 0)), h.get(CAC, (0, 0))
        r = (ck[1] + cac[1]) / int(e2['size'])
        chk('%s (CounterCacheKey+ClockAndCount bytes)/Size in [0.5,2.0]' % a, 0.5 <= r <= 2.0, 'bytes=%d size=%s ratio=%.3f instances=%d' % (ck[1] + cac[1], e2['size'], r, ck[0]))
        chk('%s CounterCacheKey instances == Entries (+-1%%)' % a, abs(ck[0] - int(e2['entries'])) <= 0.01 * int(e2['entries']) + 2, 'instances=%d entries=%s' % (ck[0], e2['entries']))
        hr = (int(e2['hits']) - int(e1['hits'])) / max(1, int(e2['requests']) - int(e1['requests']))
        info[a] = dict(size=int(e2['size']), entries=int(e2['entries']), hitrate=hr, used=used_kb(a, 'end-pass2'), named=ck[1] + cac[1])
        print('INFO %s end-pass2 size=%s entries=%s pass2 hitrate=%.4f' % (a, e2['size'], e2['entries'], hr))
if 'c0' in have:
    u0 = used_kb('c0', 'end-pass2')
    for a in have:
        if a == 'c0': continue
        d = (info[a]['used'] - u0) * 1024; r = d / info[a]['size']
        info[a]['heapdelta'] = d; info[a]['heapratio'] = r
        print('INFO %s whole-heap increase over c0 at end-pass2 = %d B = %.2f x Size' % (a, d, r))
    for a in ('c8', 'c64', 'cdef'):
        if a in info: chk('%s whole-heap increase / Size in [1.5,3.0]' % a, 1.5 <= info[a]['heapratio'] <= 3.0, '%.2f' % info[a]['heapratio'])
    if 'c8' in info and 'c64' in info: chk('heap ratio c64/c8 within 0.75..1.33 (proportional)', 0.75 <= info['c64']['heapratio'] / info['c8']['heapratio'] <= 1.33, '%.2f' % (info['c64']['heapratio'] / info['c8']['heapratio']))
if 'c1' in info and 'c8' in info:
    r = info['c8']['entries'] / info['c1']['entries']
    chk('Entries(8 MiB)/Entries(1 MiB) in [7.2,8.8]', 7.2 <= r <= 8.8, 'ratio=%.3f' % r)
    if case in ('get', 'put'):
        chk('Entries(1 MiB) in [7000,10000]', 7000 <= info['c1']['entries'] <= 10000, str(info['c1']['entries']))
    if case == 'get':
        chk('pass-2 hit rate: 1 MiB <= 20%% and < 8 MiB, 8 MiB < 100%%', info['c1']['hitrate'] <= 0.2 and info['c1']['hitrate'] < info['c8']['hitrate'] < 1.0, '1MiB=%.4f 8MiB=%.4f' % (info['c1']['hitrate'], info['c8']['hitrate']))
    else:
        print('INFO pass-2 hit rate 1MiB=%.4f 8MiB=%.4f' % (info['c1']['hitrate'], info['c8']['hitrate']))
    if case == 'put':
        chk('Entries(8 MiB) ~ 8x Entries(1 MiB) (histogram bytes track Size: named bytes ratio 8 MiB / 1 MiB in [7.2,8.8])', 7.2 <= info['c8']['named'] / info['c1']['named'] <= 8.8, '%.3f' % (info['c8']['named'] / info['c1']['named']))
if 'c8' in info and 'c8b' in info:
    chk('c8 repeat: same Entries (+-1%)', abs(info['c8']['entries'] - info['c8b']['entries']) <= 0.01 * info['c8']['entries'], '%d vs %d' % (info['c8']['entries'], info['c8b']['entries']))
if os.path.isdir(os.path.join(out, 'cdef')):
    il = json.load(open(os.path.join(out, 'cdef', 'summary.json')))['init_log']
    chk('cdef init log says capacity of 50 MiBs (auto default on 2 GiB heap)', 'capacity of 50 MiBs' in il, il.splitlines()[0][-80:] if il else '')
if os.path.isdir(os.path.join(out, 'rt64')):
    S = samples('rt64'); e1 = phase('rt64', 'end-pass1'); e2 = phase('rt64', 'end-pass2')
    after = [s for s in S if s['phase'] == 'after-setcap']
    chk('rt64 before: capacity 64 MiB, Size<=cap, reached', int(e1['capacity']) == 64 * MiB and int(e1['size']) >= 64 * MiB - 240, str(e1['size']))
    chk('rt64 after JMX set 8 MiB: capacity 8 MiB, Size <= 8 MiB at every sample, Entries 69,905+-2 within 30 s', all(int(s['capacity']) == 8 * MiB and int(s['size']) <= 8 * MiB for s in after) and abs(int(after[-1]['entries']) - 69905) <= 2, 'last=%s' % after[-1])
    chk('rt64 end-pass2 Size <= 8 MiB', int(e2['size']) <= 8 * MiB and int(e2['capacity']) == 8 * MiB, str(e2['size']))
    u1, u2 = used_kb('rt64', 'end-pass1'), used_kb('rt64', 'after-setcap-hist')
    print('INFO rt64 used heap after full GC: 64 MiB state %d KB -> 8 MiB state %d KB (decrease %.1f MiB)' % (u1, u2, (u1 - u2) / 1024))
    chk('rt64 heap decreases by more than 30 MiB after the shrink', (u1 - u2) / 1024 > 30, '%.1f MiB' % ((u1 - u2) / 1024))
if os.path.isdir(os.path.join(out, 'r8')):
    S = samples('r8')
    chk('r8 (regular-table writes) Entries 0, Size 0 at every sample', max(int(s['entries']) for s in S) == 0 and max(int(s['size']) for s in S) == 0, 'n=%d' % len(S))
    hs = sorted(glob.glob(os.path.join(out, 'r8', 'hist-*.txt')))
    chk('r8 no CounterCacheKey in any histogram', all(hist('r8', os.path.basename(h)).get(CK, (0, 0))[0] == 0 for h in hs), '%d histograms' % len(hs))
if case == 'is':
    if os.path.isdir(os.path.join(out, 'sv8')):
        ls = open(os.path.join(out, 'sv8', 'saved_caches.ls')).read()
        m = re.search(r'(\d+) \d+ CounterCache-\w+\.db', ls.replace('\n', ' \n')) or re.search(r'\s(\d+)\s+\d+\s+CounterCache-\S+\.db', ls)
        sz = int(re.search(r'(\d+)\s+\d+ CounterCache-\S+\.db', ls)[1]) if re.search(r'(\d+)\s+\d+ CounterCache-\S+\.db', ls) else 0
        chk('sv8 saved CounterCache file is non-empty', sz > 0, 'bytes=%d' % sz)
    for a, cap in (('rl0', 0), ('rl1', 1 * MiB), ('rl8', 8 * MiB)):
        if not os.path.isdir(os.path.join(out, a)): continue
        S = samples(a)
        sz = [int(s['size']) for s in S]; en = [int(s['entries']) for s in S]
        chk('%s capacity %d at every sample' % (a, cap), {int(s['capacity']) for s in S} == {cap}, '')
        chk('%s Size <= Capacity at every sample (%d samples)' % (a, len(S)), max(sz) <= cap, 'max=%d' % max(sz))
        last = S[-1]
        if cap == 0:
            chk('rl0 Entries 0 and Size 0 at every sample (saved file present, helper false)', max(en) == 0 and max(sz) == 0, 'max entries=%d' % max(en))
            h = hist('rl0', 'hist-reload-end.txt'); chk('rl0 no CounterCacheKey instances', h.get(CK, (0, 0))[0] == 0, str(h.get(CK)))
        else:
            chk('%s Entries = cap//120 +-2 after reload (<= the capacity\'s worth)' % a, abs(int(last['entries']) - cap // W) <= 2, 'entries=%s expected=%d' % (last['entries'], cap // W))
print('\nFAILED CHECKS (%d): %s' % (len(fails), fails))
