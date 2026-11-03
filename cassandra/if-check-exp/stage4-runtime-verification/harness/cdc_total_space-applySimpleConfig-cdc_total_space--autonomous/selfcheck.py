#!/usr/bin/env python3
"""Independent self-check (results §5) of run 1. It does not use the RESULT lines, logscan.txt, summary.txt or the readings
scripts: it re-derives every number the conclusion uses from the per-row STAGE4 lines (unit) and from sampler.csv/.events,
stress.log, count.txt, settings.txt and the node logs (cluster), and checks each against the amended B2f/B3f bounds.
usage: selfcheck.py <unit log dir | -> <cluster log dir>
("-" skips the unit part: used for the cluster re-run of 2026-10-24, where ctl-plain is checked against B3h (a) as re-amended after
run 1 -- every sampler row from 30 s after `nodetool flush` returned (flush.txt, cross-checked with commands.log) has <= 2 links)."""
import csv, os, re, sys, zipfile
U, C = sys.argv[1], sys.argv[2]; MIB = 1 << 20
fails = []
def check(name, ok, note):
    print('%-4s %s: %s' % ('ok' if ok else 'FAIL', name, note))
    if not ok: fails.append(name)
# ---------------- unit
for lab, s, mode in [] if U == '-' else [('block-s8', 8, 'b'), ('block-s16', 16, 'b'), ('block-s32', 32, 'b'), ('nonblock-s8', 8, 'n'),
                     ('nonblock-s16', 16, 'n'), ('nonblock-s32', 32, 'n'), ('ctl-plain', 8, 'p'), ('ctl-1024', 1024, 'c')]:
    L = open(os.path.join(U, lab + '.stage4.out')).read().splitlines()
    cfg = [l for l in L if ' config ' in l][0]
    A = int(re.search(r' A=(\d+)', cfg).group(1)); S = int(re.search(r' S=(\d+)', cfg).group(1))
    rowl = [l for l in L if re.search(r' row \d+ accepted=', l)]
    lb = [int(re.search(r'linkBytes=(\d+)', l).group(1)) for l in L if re.search(r' (idle|row \d+|firstReject|end) ', l)]
    acc = int(re.search(r'accepted=(\d+)', rowl[-1]).group(1)) if rowl else 0
    fr = [l for l in L if ' firstReject ' in l]
    dels = len(set(re.search(r'name=(\S+)', l).group(1) for l in L if ' linkDeleted ' in l))
    mx = max(lb)
    if mode == 'b':
        fa = int(re.search(r'acceptedRows=(\d+)', fr[0]).group(1)) if fr else None
        ok = A == s * MIB and S == MIB and len(fr) == 1 and fa is not None and (A - 4 * S) <= fa * 65536 <= (A + S) and mx <= A + S
        check('unit ' + lab, ok, 'A=%d S=%d first rejection after %s rows (%.2f MiB), window [%d,%d] MiB; max link bytes %d (%.2f MiB) <= %d MiB' % (A, S, fa, (fa or 0) * 65536 / MIB, s - 4, s + 1, mx, mx / MIB, s + 1))
    elif mode == 'n':
        ok = A == s * MIB and not fr and acc == 4 * s * 16 and mx <= A + S and dels >= 1
        check('unit ' + lab, ok, 'A=%d no rejection=%s rows accepted %d (4*s MiB = %d rows); max link bytes %d (%.2f MiB) <= %d MiB; distinct links deleted %d' % (A, not fr, acc, 4 * s * 16, mx, mx / MIB, s + 1, dels))
    elif mode == 'p':
        ar = [l for l in L if ' afterRecycle ' in l]
        al = int(re.search(r'links=(\d+)', ar[0]).group(1)) if ar else 99
        check('unit ctl-plain', not fr and acc == 512 and al <= 2, 'no rejection=%s rows %d; links during writes max %d bytes; links after recycle %d' % (not fr, acc, mx, al))
    else:
        check('unit ctl-1024', not fr and acc == 2048, 'no rejection=%s rows %d (128 MiB)' % (not fr, acc))
H = '' if U == '-' else open(os.path.join(U, 'helper.stage4.out')).read()
hv = re.findall(r'totalBytes=(\d+) result=(\d+)', H)
if U != '-': check('unit helper', hv == [('4294967296', '512'), ('107374182400', '4096')], 'helper results %s; independent min(4096, MiB/8): %s' % (hv, [min(4096, int(t) // MIB // 8) for t, _ in hv]))
# ---------------- cluster
def logtext(D, prefix):
    out = []
    for n in sorted(os.listdir(D)):
        p = os.path.join(D, n)
        if n == prefix: out.append(open(p, errors='replace').read())
        elif n.startswith(prefix) and n.endswith('.zip'):
            with zipfile.ZipFile(p) as z:
                out += [z.read(m).decode('utf-8', 'replace') for m in z.namelist()]
    return '\n'.join(out)
def stress(D):
    t = open(os.path.join(D, 'stress.log'), errors='replace').read()
    g = lambda k: int(re.search(r'^%s\s*:\s*([\d,]+)' % k, t, re.M).group(1).replace(',', ''))
    return g('Total errors'), g('Total partitions')
def samp(D):
    r = list(csv.reader(open(os.path.join(D, 'sampler.csv'))))[1:]
    ev = open(os.path.join(D, 'sampler.events')).read().splitlines()
    return max(int(x[3]) for x in r), max(int(x[2]) for x in r), sum(1 for e in ev if e.split()[1] == '-'), int(r[-1][2])
statv = None
for arm, knob, blk in [('b256', 256, True), ('b1024', 1024, True), ('bdef', 0, True), ('n256', 256, False), ('n1024', 1024, False), ('ndef', 0, False)]:
    D = os.path.join(C, arm)
    st = open(os.path.join(D, 'settings.txt')).read()
    rb = int(re.search(r'cdc_total_space\s*\|\s*(\d+)MiB', st).group(1))
    if knob == 0:
        tot = int(re.search(r'total_bytes=(\d+)', open(os.path.join(D, 'statvfs.txt')).read()).group(1))
        exp = min(4096, tot // MIB // 8)
        check('cluster %s default read-back' % arm, rb == exp, 'read back %d MiB; statvfs total %d B -> min(4096, %d/8) = %d' % (rb, tot, tot // MIB, exp))
    else:
        check('cluster %s knob read-back' % arm, rb == knob, 'read back %d MiB' % rb)
    A = rb * MIB; S = 32 * MIB
    err, parts = stress(D)
    cnt = int(re.search(r'^\s*(\d+)\s*$', open(os.path.join(D, 'count.txt')).read(), re.M).group(1))
    mx, ml, dels, _ = samp(D)
    sl = logtext(D, 'system.log'); dl = logtext(D, 'debug.log')
    warn = len(re.findall(r'^WARN .*Rejecting mutation', sl, re.M)); freed = len(re.findall(r'Freed up .* after deleting the oldest CDC commit log segments', dl))
    if blk:
        ok = err > 0 and warn >= 1 and A - 4 * S <= cnt * 16384 <= A + S and mx <= A + S
        check('cluster ' + arm, ok, 'errors %d of %d; WARN Rejecting %d; rows %d = %.1f MiB in [%d, %d]; max link bytes %d (%.2f MiB, %d links) <= %d MiB' % (err, parts, warn, cnt, cnt * 16384 / MIB, rb - 128, rb + 32, mx, mx / MIB, ml, rb + 32))
    else:
        ok = err == 0 and warn == 0 and freed >= 1 and dels >= 1 and mx <= A + S
        check('cluster ' + arm, ok, 'errors %d of %d; WARN Rejecting %d; Freed up %d; links deleted %d; rows %d; max link bytes %d (%.2f MiB, %d links) <= %d MiB' % (err, parts, warn, freed, dels, cnt, mx, mx / MIB, ml, rb + 32))
D = os.path.join(C, 'ctl-plain'); err, parts = stress(D); mx, ml, dels, fin = samp(D)
warn = len(re.findall(r'^WARN .*Rejecting mutation', logtext(D, 'system.log'), re.M))
fp = os.path.join(D, 'flush.txt')
if os.path.exists(fp):
    import datetime
    ft = open(fp).read(); f0 = int(re.search(r'start_ms=(\d+)', ft).group(1)); f1 = int(re.search(r'end_ms=(\d+)', ft).group(1)); fx = re.search(r'exit=(\d+)', ft).group(1)
    cl = open(os.path.join(C, 'commands.log')).read().splitlines()
    i = [k for k, l in enumerate(cl) if re.search(r'\] \+ nt flush$', l)]
    ex = [l for l in cl[i[0]:] if re.search(r'^\[\S+\]   exit=', l)][0] if i else ''
    tsx = datetime.datetime.strptime(ex[1:25], '%Y-%m-%dT%H:%M:%S%z').timestamp() * 1000 if ex else 0
    rows = list(csv.reader(open(os.path.join(D, 'sampler.csv'))))[1:]
    post = [int(x[2]) for x in rows if int(x[0]) >= f1 + 30000]
    check('cluster ctl-plain (flush all, re-run)', len(i) == 1 and fx == '0' and abs(tsx - f1) < 2000 and err == 0 and warn == 0 and mx <= (256 + 32) * MIB and post and max(post) <= 2,
          'nodetool flush (no keyspace) lines %d, exit %s, %d ms, commands.log exit at %s (flush.txt end %d); errors %d of %d, WARN %d, max link bytes %d (%.1f MiB); post-flush samples %d, max links %s, last %d' % (len(i), fx, f1 - f0, ex[1:25], f1, err, parts, warn, mx, mx / MIB, len(post), max(post) if post else '-', fin))
else:
    check('cluster ctl-plain', err == 0 and warn == 0 and mx <= (256 + 32) * MIB and fin <= 2, 'errors %d of %d, WARN %d, max link bytes %d (%.1f MiB), links at last sample %d' % (err, parts, warn, mx, mx / MIB, fin))
D = os.path.join(C, 'ctl-cdcoff'); err, parts = stress(D); mx, ml, dels, fin = samp(D)
check('cluster ctl-cdcoff', err == 0 and ml == 0, 'errors %d of %d, max links %d' % (err, parts, ml))
D = os.path.join(C, 'startup-cdcoff-0'); st = open(os.path.join(D, 'settings.txt')).read()
check('cluster startup-cdcoff-0', re.search(r'cdc_total_space\s*\|\s*0MiB', st) is not None and re.search(r'cdc_enabled\s*\|\s*false', st) is not None, 'settings: %s' % ' '.join(l.strip() for l in st.splitlines() if 'cdc_total_space' in l or 'cdc_enabled' in l))
print('\nSELF-CHECK: %d failed: %s' % (len(fails), fails))
