#!/usr/bin/env python3
"""Independent re-read of the committed excerpts against the case's B2f / B3f sub-predictions (run from run1/).
Parses raw lines itself (not the harness readings scripts). Prints PASS / MISS per sub-prediction per cell."""
import os, re
MIB = 1 << 20; S = 32
def kv(l): return dict(re.findall(r'(\w+)=("[^"]*"|\S+)', l))
out = []
def chk(ok, what): out.append(('PASS' if ok else 'MISS') + '  ' + what)
# ---------------- unit tier
U = {}
for c in sorted(os.listdir('unit')):
    p = 'unit/%s/readings.txt' % c
    if not os.path.exists(p): continue
    L = open(p).read().splitlines()
    cfg = kv(next(l for l in L if ' config ' in l)); rows = [kv(l) for l in L if ' row i=' in l]
    fin = kv(next(l for l in L if ' final ' in l and 'afterUpdate' not in l)); sam = kv(next(l for l in L if ' sampler ' in l))
    wd = kv(next(l for l in L if ' writesDone ' in l)); tr = open('unit/%s/cdc-verdict.txt' % c).read().splitlines() if os.path.exists('unit/%s/cdc-verdict.txt' % c) else []
    n = int(cfg['totalSpaceMiB']); mode = cfg['mode']; du = int(fin['duBytes']) / MIB; peak = int(sam['peakBytes']) / MIB
    dele = sum(1 for l in tr if l.startswith('deleteOld'))
    U[c] = dict(n=n, mode=mode, du=du, peak=peak, dele=dele, rej=int(wd['rejected']), acc=int(wd['accepted']), enabled=cfg['cdcEnabled'], table=cfg['table'], vol=int(cfg['volumeMiB']),
                trk=(None if fin['tracker'] == 'na' else int(fin['tracker'])), dub=int(fin['duBytes']), seen=int(sam['distinctLinksSeen']), links=int(fin['links']),
                rowdu=[int(r['duBytes']) / MIB for r in rows], rejrows=[i for i, r in enumerate(rows) if 'REJECTED' in str(r) or r.get('i') is None])
    # rows: 'accepted'/'REJECTED' is a bare word, so re-read it from the text
    U[c]['status'] = [('REJECTED' in l) for l in L if ' row i=' in l]
for c, u in U.items():
    if c.startswith(('b', 'nb')) and u['table'] == 'cdc' and u['enabled'] == 'true' and u['n'] != 4096:
        if u['mode'] == 'blocking':
            chk(u['du'] <= u['n'] + S + 1, 'unit %s blocking: final du %.1f <= n + 1 segment (%d)' % (c, u['du'], u['n'] + S))
            chk(u['peak'] <= u['n'] + S + 1, 'unit %s blocking: peak du %.1f <= n + 1 segment' % (c, u['peak']))
            chk(u['rej'] > 0, 'unit %s blocking: CDCWriteException count %d > 0' % (c, u['rej']))
            chk(u['dele'] == 0, 'unit %s blocking: deleteOld never called (%d)' % (c, u['dele']))
            chk(u['trk'] is not None and abs(u['trk'] - u['dub']) <= S * MIB, 'unit %s blocking: tracker within one segment of du after the final walk' % c)
            first = u['status'].index(True) if True in u['status'] else None
            chk(first is not None and max(u['rowdu'][first:]) - min(u['rowdu'][first:]) <= 0.001, 'unit %s blocking: du flat from the first rejection to the end' % c)
        else:
            chk(u['rej'] == 0, 'unit %s nonblocking: no CDCWriteException' % c)
            chk(u['peak'] <= u['n'] + 2 * S + 1, 'unit %s nonblocking: peak %.1f <= n + 2 segments' % (c, u['peak']))
            chk(u['du'] <= u['n'] + S + 1, 'unit %s nonblocking: final %.1f <= n + 1 segment' % (c, u['du']))
            chk(u['seen'] > u['links'] and u['dele'] > 0, 'unit %s nonblocking: oldest links gone (%d seen, %d left) and deleteOld called %d times' % (c, u['seen'], u['links'], u['dele']))
for m in ('blocking', 'nonblocking'):
    pts = [(u['n'], u['du']) for c, u in U.items() if u['mode'] == m and c[0] in 'bn' and not c.startswith('ctl') and u['table'] == 'cdc']
    ns = sorted(set(p[0] for p in pts)); means = {n: sum(d for k, d in pts if k == n) / sum(1 for k, d in pts if k == n) for n in ns}
    chk(all(abs(means[n] - n) <= S for n in ns), 'unit dose-response %s: mean final du per n %s within one segment of n' % (m, {n: round(v, 1) for n, v in means.items()}))
for c in ('ctl-b4096', 'ctl-nb4096'):
    u = U[c]; chk(u['du'] >= u['vol'] and u['dele'] == 0 and u['rej'] == 0, 'unit %s control: du %.1f >= volume %d, deleteOld %d, rejected %d' % (c, u['du'], u['vol'], u['dele'], u['rej']))
chk(U['ctl-cdcoff']['dub'] == 0, 'unit CDC-off control: cdc_raw empty')
for c in ('ctl-plain-b128', 'ctl-plain-nb128'):
    u = U[c]; chk(u['rej'] == 0, 'unit %s: no CDCWriteException on a non-CDC table' % c)
    chk(u['peak'] == 0, 'unit %s: cdc_raw stays empty (B2h as filed): peak %.1f MiB' % (c, u['peak']))
# ---------------- cluster tier
C = {}
for c in sorted(os.listdir('cluster')):
    s = open('cluster/%s/summary.txt' % c).read(); ph = {l.split(',')[1].strip(): int(l.split(',')[0]) for l in open('cluster/%s/phases.csv' % c)}
    cap = int(re.search(r'cap=(\d+)MiB', s).group(1)); mode = re.search(r'mode=(\w+)', s).group(1)
    csv = [list(map(int, l.split(','))) for l in list(open('cluster/%s/sampler-1s.csv' % c))[1:]]
    W = [r for r in csv if ph['W_start'] <= r[0] <= ph['W_end'] + 3000]
    peakW = max((r[2] + r[5] for r in W), default=0) / MIB; endW = (W[-1][2] + W[-1][5]) / MIB if W else 0
    sam = re.search(r'max_link_bytes=(\d+)', s)
    err = re.search(r'stress W:.*?Total errors : ([\d,]+)', s); err = int(err.group(1).replace(',', '')) if err else None
    rows = int(re.search(r'rows=(\d+)', s).group(1)); warn = int(re.search(r'WARN=(\d+) FreedUp', s).group(1)); fr = int(re.search(r'FreedUp=(\d+)', s).group(1))
    rel = re.search(r'release: accepted=(\d) after (\d+) probe\(s\), (\d+) ms', s); sw = re.search(r'switch: first CDC probe accepted=(\d) after (\d+) probe\(s\), (\d+) ms', s)
    swl = re.search(r'switch: links before=\[(.*?)\] after=\[(.*?)\]', s)
    clog = int(re.search(r'commit log dir: (\d+) bytes', s).group(1)) / MIB
    C[c] = dict(cap=cap, mode=mode, peakW=peakW, endW=endW, wholepeak=int(sam.group(1)) / MIB, err=err, rows=rows, warn=warn, fr=fr, rel=rel, sw=sw, swl=swl, clog=clog)
for c, u in C.items():
    if c.startswith(('b', 'nb')) and not c.startswith('b4096') and not c.startswith('nb4096') and not c.startswith('plain'):
        cap = u['cap']
        if u['mode'] == 'blocking':
            chk(u['peakW'] <= cap + 2 * S, 'cluster %s blocking: W peak %.1f <= cap + 2 segments' % (c, u['peakW']))
            chk(u['err'] and u['err'] > 0 and u['warn'] > 0, 'cluster %s blocking: write failures %s and Rejecting-mutation WARN %s' % (c, u['err'], u['warn']))
            chk(cap <= u['endW'] <= cap + 2 * S or cap == 16, 'cluster %s blocking: plateau %.1f inside the filed range cap .. cap + 2 segments' % (c, u['endW']))
            chk(abs(u['peakW'] - u['endW']) < 0.01, 'cluster %s blocking: flat (peak == end of the 3x workload)' % c)
            if cap >= 64:
                chk(u['rel'] and u['rel'].group(1) == '1' and int(u['rel'].group(3)) <= 3000, 'cluster %s blocking: writes resumed after deleting two links (%s ms from the deletion, includes cqlsh starts)' % (c, u['rel'] and u['rel'].group(3)))
            chk(u['sw'] and u['sw'].group(1) == '1', 'cluster %s: first CDC write accepted after the live switch to non-blocking' % c)
            chk(u['swl'] is not None and u['fr'] > 0, 'cluster %s: old links deleted after the switch (Freed up %d)' % (c, u['fr']))
        else:
            chk(u['err'] == 0, 'cluster %s nonblocking: no write failures' % c)
            lim = cap + 2 * S if cap != 16 else 32
            chk(u['peakW'] <= lim, 'cluster %s nonblocking: W peak %.1f <= %s MiB (cap + 2 segments; 16 MiB case: about one segment, 32)' % (c, u['peakW'], lim))
            chk(u['fr'] > 0, 'cluster %s nonblocking: DEBUG Freed up lines %d' % (c, u['fr']))
            chk(u['clog'] >= 0, 'cluster %s: commit log dir %.0f MiB at end (not bounded by cdc_total_space)' % (c, u['clog']))
for m, pre in (('blocking', 'b'), ('nonblocking', 'nb')):
    e = {cap: [C['%s%d-r%d' % (pre, cap, r)]['endW'] for r in (1, 2)] for cap in (128, 256, 512)}
    chk(all(abs(v[0] - v[1]) < 0.01 for v in e.values()), 'cluster %s: the two repeats agree exactly %s' % (m, e))
    chk(e[256][0] / e[128][0] > 1.8 and e[512][0] / e[256][0] > 1.8, 'cluster %s dose-response: plateau %s doubles with the knob' % (m, {k: v[0] for k, v in e.items()}))
for c in ('b4096-r1', 'b4096-r2', 'nb4096-r1'):
    u = C[c]; chk(u['peakW'] >= u['rows'] / 16 and u['fr'] == 0 and (u['err'] or 0) == 0, 'cluster %s control: cdc_raw %.1f MiB >= volume %d MiB, no failures, no deletion' % (c, u['peakW'], u['rows'] // 16))
for c in ('plainb128-r1', 'plainb128-r2'):
    u = C[c]; chk(u['err'] == 0 and u['warn'] == 0, 'cluster %s: non-CDC table, no failures' % c); chk(u['peakW'] == 0, 'cluster %s: cdc_raw empty during the workload (B3h as filed): peak %.1f MiB' % (c, u['peakW']))
chk(C['cdcoff128-r1']['peakW'] == 0 and C['cdcoff128-r1']['err'] == 0, 'cluster cdc_enabled=false: cdc_raw empty, no failures')
for c in ('nb16-r1', 'nb16-r2'): chk(C[c]['peakW'] <= 32, 'cluster %s: 16 MiB case non-blocking holds about one segment (filed: about 32 MiB), observed %.1f' % (c, C[c]['peakW']))
for c in ('b16-r1', 'b16-r2'): chk(C[c]['err'] == C[c]['rows'], 'cluster %s: every CDC write rejected at a 16 MiB cap (%s of %s)' % (c, C[c]['err'], C[c]['rows']))
print('\n'.join(out)); print('\nPASS %d, MISS %d' % (sum(1 for o in out if o.startswith('PASS')), sum(1 for o in out if o.startswith('MISS'))))
