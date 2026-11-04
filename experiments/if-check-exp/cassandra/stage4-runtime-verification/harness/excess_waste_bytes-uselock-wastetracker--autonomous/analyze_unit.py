#!/usr/bin/env python3
"""Readings of the unit tier (WasteProbe output) of one EXCESS_WASTE_* case: python3 analyze_unit.py <case 1|2|3|4> [dir]
Prints, per build, the tables used in the results file and the PASS/FAIL of each pre-registered relation of the case's B0 text (the
"formula" relations are those of B2f/B0; the S2 relations are those of B0). Default dir ~/stage4-logs/ew/unit-c<case>."""
import glob, math, os, re, statistics, sys

case = int(sys.argv[1]); D = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser('~/stage4-logs/ew/unit-c%d' % case)
KV = re.compile(r'(\w+)=(\S+)')


def load(f):
    rows = []
    for l in open(f):
        if not l.startswith('PROBE '): continue
        parts = l.split(None, 2)
        kind = parts[1]; kv = dict(KV.findall(parts[2] if len(parts) > 2 else ''))
        rows.append((kind, kv))
    return rows


def num(x):
    try: return int(x)
    except ValueError: return float(x)


res = []
def chk(name, ok, detail=''):
    res.append(ok); print('  %s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


for f in sorted(glob.glob(D + '/*.out')):
    rows = load(f); lab = os.path.basename(f)[:-4]
    cfg = [kv for k, kv in rows if k == 'config'][0]; C = int(cfg['C']); OFF = int(cfg['OFFSET'])
    print('\n=== %s  C=%d OFFSET=%d instrumented=%s from %s' % (lab, C, OFF, cfg['instrumented'], cfg['loadedFrom'].split('/')[-2]))
    for k, kv in rows:
        if k == 'direct':
            w = int(kv['w']); u = int(kv['units']); exp = (w >= C) or u >= OFF
            chk('direct w=%d (C%+d) ret=%s' % (w, w - C, kv['ret']), (kv['ret'] == 'true') == exp and kv['useLock'] == kv['ret'] and (kv['sentinel'] == 'true') == exp,
                'tracker=%s expect lock=%s' % (kv['tracker'], exp))
        elif k == 'latch':
            chk('latch: stays true after the sentinel', kv['afterSentinelTenCallsOfOneByte'] == 'true')
        elif k == 'burst':
            w = int(kv['w']); u = int(kv['units']); calls = int(kv['calls']); el = int(kv['elapsedNs']); gap = int(kv['gapMs'])
            per = el / calls / 131072.0  # ticks per call
            if gap == 0:
                exp = math.ceil((OFF + (el >> 17)) / u) if w < C else 1
                tol = 2 + 0.02 * exp
                chk('burst gap0 w=%d units=%d calls=%d' % (w, u, calls), kv['locked'] == 'true' and abs(calls - exp) <= tol,
                    'expected %d (OFFSET + elapsed ticks %d, / units) +-%.1f; formulaCalls(no credit)=%s elapsed %.1f ms' % (exp, el >> 17, tol, kv['formulaCalls'], el / 1e6))
            else:
                net = u - per
                if net > 0.5:
                    exp = OFF / net
                    ok = (kv['locked'] == 'true' and abs(calls - exp) <= 0.25 * exp + 3) or (kv['locked'] == 'false' and calls * net < 1.1 * OFF)   # not locked: the cap (4 s) came before the expected lock
                    chk('burst %s w=%d units=%d: net %.2f units/call' % (kv['label'], w, u, net), ok, 'calls=%d locked=%s expected ~%.0f (cap-limited if not locked) elapsed %.2f s' % (calls, kv['locked'], exp, el / 1e9))
                else:
                    chk('burst %s w=%d units=%d: net %.2f <= 0.5: no lock' % (kv['label'], w, u, net), kv['locked'] == 'false', 'calls=%d elapsed %.2f s' % (calls, el / 1e9))
        elif k == 'burstk':
            kk = int(kv['k']); w = int(kv['w']); u = (w + 1023) // 1024
            chk('burstk C/8 x%d lastRet=%s' % (kk, kv['lastRet']), (kv['lastRet'] == 'true') == (kk * u >= OFF + 0) or (kk * u >= OFF - 1 and kv['lastRet'] == 'true'), 'units %d x k = %d vs OFFSET %d' % (u, kk * u, OFF))
        elif k == 'refill':
            g = int(kv['gapMs']); exp2 = g < int(kv['windowMs'])
            chk('refill gap %d ms: first=%s second=%s' % (g, kv['first'], kv['second']), kv['first'] == 'false' and (kv['second'] == 'true') == exp2, 'window %s ms, expected second=%s' % (kv['windowMs'], exp2))
        elif k == 'stream':
            w = int(kv['w']); n = int(kv['calls']); el = int(kv['elapsedNs']); rate = (w / 1024.0) * n / (el / 1e6)
            net = (rate - 7.63) * (el / 1e6) * 1.0 / 1.0  # KiB over the whole run beyond the allowance
            exp_lock = net > 1.05 * OFF
            chk('stream w=%d gap %s ms: %d calls locked=%s rate %.2f KiB/ms vs 7.63 (excess %.0f KiB vs window %d KiB)' % (w, kv['gapMs'], n, kv['locked'], rate, net, OFF),
                (kv['locked'] == 'true') == exp_lock or abs(net - OFF) <= 0.1 * OFF)
        elif k == 'memo':
            chk('memo: heap delta after 3M reports %s B (< 1 MB)' % kv['deltaBytes'], abs(int(kv['deltaBytes'])) < 1_000_000, 'reported %s B, useLock=%s' % (kv['reportedBytes'], kv['useLock']))
    # accounting
    for k, kv in rows:
        if k == 'calib': print('  calib', kv['type'], 'heapPerRow', kv['heapPerRow'], 'ownsOn', kv['ownsOn'], 'ownsOff', kv['ownsOff'], '(2000 rows x 100 B)')
    for k, kv in rows:
        if k == 'fail':
            if 'skipped' in kv: print('  fail', kv['type'], kv['factor'], 'skipped', kv['skipped']); continue
            t = kv['type']; ex = int(kv['excessOff']) if t == 'offheap_objects' else int(kv['excessOn']); pay = int(kv['payloadOfFailedAttempt'])
            W = int(kv['measuredW']); exp_lock = (W >= C) or ((W + 1023) // 1024 >= OFF)
            chk('fail %s factor %s: W=%d tracker sentinel=%s' % (t, kv['factor'], W, kv['sentinel']), (kv['sentinel'] == 'true') == exp_lock and kv['fails'] == '1', 'expect lock=%s fails=%s' % (exp_lock, kv['fails']))
            chk('S2 fail %s factor %s: owns excess %d vs payload %d (ratio %.2f, 0.9-1.5 expected; 1.3 and above only for offheap_objects cell headers)' % (t, kv['factor'], ex, pay, ex / pay), 0.9 <= ex / pay <= 1.5)   # native (off-heap) cells add a header to the value bytes
        elif k == 'seqc':
            if kv['k'] in ('1', '8', '9', '10', '11', '12'): print('  seqc', kv['type'], 'k', kv['k'], 'W', kv['measuredW'], 'useLock', kv['useLock'])
        elif k == 'seqd':
            chk('seqd %s 200 x 8 KiB/2 ms: never locks (firstLock=%s)' % (kv['type'], kv['firstLock']), kv['useLock'] == 'false', 'elapsed %s ms' % kv['elapsedMs'])
        elif k == 'nohook':
            chk('nohook %s tracker stays 0' % kv['type'], kv['tracker'] == '0' and kv['useLock'] == 'false')
        elif k == 'sentinel':
            same = all(kv[a] == kv[b] for a, b in (('sentinelOwnsOn', 'normalOwnsOn'), ('sentinelOwnsOff', 'normalOwnsOff'), ('dataSizeS', 'dataSizeN'), ('heapSizeS', 'heapSizeN')))
            chk('sentinel %s: uncontended owns/dataSize/heapSize equal sentinel vs not' % kv['type'], same, 'owns on/off %s/%s vs %s/%s' % (kv['sentinelOwnsOn'], kv['sentinelOwnsOff'], kv['normalOwnsOn'], kv['normalOwnsOff']))
    # first lock index in the seqc sequence
    for t in ('heap_buffers', 'offheap_objects'):
        sq = [kv for k, kv in rows if k == 'seqc' and kv['type'] == t]
        if sq:
            first = next((int(x['k']) for x in sq if x['useLock'] == 'true'), None)
            W = [int(x['measuredW']) for x in sq if x['measuredW'] != '-1']
            print('  seqc %s: 12 failures, W %s..%s, first lock at failure %s' % (t, min(W) if W else '-', max(W) if W else '-', first))
    # contention
    labs = sorted({kv['label'] for k, kv in rows if k == 'cont'})
    for lb in labs:
        single = [kv for k, kv in rows if k == 'cont' and kv['label'] == lb and kv['run'] == 'single'][0]
        runs = [kv for k, kv in rows if k == 'cont' and kv['label'] == lb and kv['run'] != 'single']
        t = single['type']; key = 'ownsOff' if t == 'offheap_objects' else 'ownsOn'
        vals = [int(r[key]) for r in runs]; s = int(single[key])
        print('  cont %s %s: single %s=%d; contended n=%d median %d min %d max %d (ratio to single %.2f); fails med %s; flips %s; useLock %s; elapsed ms %s' % (
            lb, t, key, s, len(vals), statistics.median(vals), min(vals), max(vals), statistics.median(vals) / s,
            statistics.median([int(r['fails']) for r in runs]), [r['flips'] for r in runs], [r['useLock'] for r in runs], [r['elapsedMs'] for r in runs]))
        chk('S2 cont %s: every contended %s above single (%d)' % (lb, key, s), all(v > s for v in vals))
    # control
    for k, kv in rows:
        if k == 'control':
            lim = int(kv['limit']); t = kv['type']; own = int(kv['ownsOffAtFirstClean']) if t == 'offheap_objects' else int(kv['ownsOnAtFirstClean'])
            chk('control %s limit %d MiB: cleaner first called at owns %d = %.3f x limit (0.5 to 0.55)' % (t, lim >> 20, own, own / lim), 0.5 <= own / lim <= 0.55 and int(kv['cleanerCalls']) > 0)
    for t in ('heap_buffers', 'offheap_objects', 'unslabbed_heap_buffers'):
        c = {int(kv['limit']): kv for k, kv in rows if k == 'control' and kv['type'] == t}
        if len(c) == 2:
            key = 'ownsOffAtFirstClean' if t == 'offheap_objects' else 'ownsOnAtFirstClean'
            r = int(c[33554432][key]) / int(c[8388608][key])
            chk('control %s: 32 MiB / 8 MiB first-clean owns ratio %.2f (4 +-10%%)' % (t, r), 3.6 <= r <= 4.4)
print('\nSUMMARY: %d checks, %d PASS, %d FAIL' % (len(res), sum(res), len(res) - sum(res)))
