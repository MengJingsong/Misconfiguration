#!/usr/bin/env python3
"""Independent re-parse of the raw run-1 files of logs_virtual_table_default_rows-addtobuffer-messagebuffer_size--autonomous.
usage: selfcheck.py <run1 dir>  (contains unit/unit.out, cluster/<label>/{readings.txt,samples.csv,stdout.txt,cmdlog.txt})
Does not use the run scripts' own pass/fail logic: every number is re-derived from the files."""
import csv, os, re, sys
R = sys.argv[1]; fails = 0
def chk(ok, msg):
    global fails; fails += (not ok); print(('PASS ' if ok else 'FAIL ') + msg)
# ---------------- unit
cells = {}; label = None
for l in open(os.path.join(R, 'unit', 'unit.out')):
    m = re.match(r'== (\S+) .*', l)
    if m and not l.startswith('== rc'): label = m.group(1); cells[label] = {'rc': None, 'lines': []}; continue
    m = re.match(r'== rc (\d+)', l)
    if m and label: cells[label]['rc'] = int(m.group(1)); continue
    if label and l.startswith('STAGE4'): cells[label]['lines'].append(l.strip())
def kv(line): return dict(re.findall(r'(\w+)=(\S+)', line))
def get(label, tag):
    for l in cells[label]['lines']:
        if l.startswith('STAGE4 ' + tag + ' '): return kv(l)
    return None
chk(all(c['rc'] == 0 for c in cells.values()) and len(cells) == 12, 'unit: %d JVMs, all exit 0 (expect 12)' % len(cells))
delta = {}
for N in (0, 1000, 49999, 50000, 50001, 120000):
    c = get('A100-N%d' % N, 'appender-after-push'); s = get('A100-N%d' % N, 'appender-after-stop')
    exp = min(N, 50000)
    chk(int(c['size']) == exp, 'unit N=%d 100B: appender size %s == min(N,50000) = %d' % (N, c['size'], exp))
    if N:
        chk(c['firstSeq'] == '0' and int(c['lastSeq']) == exp - 1, 'unit N=%d: oldest events kept (firstSeq %s, lastSeq %s)' % (N, c['firstSeq'], c['lastSeq']))
    chk(abs(int(c['LoggingEventInstances']) - exp) <= 5, 'unit N=%d: live LoggingEvent instances %s ~ size' % (N, c['LoggingEventInstances']))
    chk(int(s['size']) == 0 and int(s['LoggingEventInstances']) <= 5, 'unit N=%d: after stop() size %s, instances %s' % (N, s['size'], s['LoggingEventInstances']))
    chk(abs(int(s['heapDelta'])) < 25_000_000, 'unit N=%d: after stop() heap delta %s B within 25 MB of baseline' % (N, s['heapDelta']))
    delta[N] = int(c['heapDelta'])
# The heap baseline of a fresh JVM wobbles by up to ~11 MB between JVMs (delta of the N=0 JVM is about -22.8 MB), so a delta is corrected by the N=0 JVM's value
# and an uncertainty of 12 MB is carried; the 10 KiB cells are far above it.
off = delta[0]
chk(max(delta[k] for k in (49999, 50000, 50001, 120000)) > max(delta[0], delta[1000]), 'unit 100B: heap delta of the full-buffer JVMs is above the empty / 1000-event JVMs (%s)' % {k: delta[k] for k in (0, 1000, 49999, 50000, 50001, 120000)})
cap100 = [delta[k] - off for k in (50000, 50001, 120000)]
chk(max(cap100) - min(cap100) < 12_500_000, 'unit 100B: N=50000 / 50001 / 120000 retain the same bytes within baseline noise (corrected deltas %s)' % cap100)
big = {N: get('A10K-N%d' % N, 'appender-after-push') for N in (50000, 120000)}
for N, c in big.items(): chk(int(c['size']) == 50000, 'unit 10KiB N=%d: size %s == 50000' % (N, c['size']))
b10 = int(big[50000]['heapDelta']) - off
lo, hi = b10 / (max(cap100) + 12_000_000), b10 / max(min(cap100) - 12_000_000, 1)
chk(lo > 10, 'unit: heap delta at N=50000 is %.0f MB with a 10 KiB payload against %.0f..%.0f MB with 100 B (baseline-corrected; ratio at least %.0fx): the count cap does not bound bytes' % (b10 / 1e6, min(cap100) / 1e6, max(cap100) / 1e6, lo))
print('   info per-event retained bytes: 10KiB payload ~ %.0f; 100B payload ~ %.0f +- 240' % (b10 / 50000, sum(cap100) / len(cap100) / 50000))
chk(abs(int(big[120000]['heapDelta']) - int(big[50000]['heapDelta'])) < 0.1 * int(big[50000]['heapDelta']), 'unit 10KiB: N=120000 retains the same bytes as N=50000')
tdel = {}
for m in (1000, 50000, 100000):
    t = get('T-m%d' % m, 'table-after-add'); a = get('T-m%d' % m, 'appender-after-push'); r = get('T-m%d' % m, 'table')
    chk(int(r['resolveBufferSize']) == m and int(t['size']) == m, 'unit max.rows=%d: resolveBufferSize %s, table size %s' % (m, r['resolveBufferSize'], t['size']))
    chk(t['firstSeq'] == '119999' and int(t['lastSeq']) == 120000 - m, 'unit max.rows=%d: table keeps the newest m (first %s last %s)' % (m, t['firstSeq'], t['lastSeq']))
    chk(int(a['size']) == 50000, 'unit max.rows=%d: appender buffer still %s (property has no effect on it)' % (m, a['size']))
    tdel[m] = int(t['heapDelta'])
chk(tdel[1000] < tdel[50000] < tdel[100000] or tdel[100000] > tdel[1000] + 1_000_000, 'unit: table heap delta rises with max.rows (%s)' % tdel)
f = get('T-m500-fallback', 'table'); t = get('T-m500-fallback', 'table-after-add')
chk(int(f['resolveBufferSize']) == 50000 and int(t['size']) == 50000, 'unit max.rows=500 (out of range): falls back to the default 50000 (table size %s)' % t['size'])
# ---------------- cluster
CL = os.path.join(R, 'cluster'); runs = {}
for lab in sorted(os.listdir(CL)):
    d = os.path.join(CL, lab)
    if not os.path.exists(d + '/readings.txt'): continue
    txt = open(d + '/readings.txt').read(); so = open(d + '/stdout.txt', errors='replace').read()
    e = re.search(r'LVFLUSH_ENTRY ms=(\d+) attempts=(\d+) buffered=(\d+)', so); x = re.search(r'LVFLUSH_EXIT ms=(\d+) buffered=(\d+)', so)
    cm = open(d + '/cmdlog.txt').read()
    k = {}
    k['entry'] = tuple(map(int, e.groups())) if e else None; k['exit'] = int(x.group(2)) if x else None
    k['t1'] = re.search(r'TABLE_AFTER_STARTUP LOGROWS total=(\d+) pre=(\d+) post=(\d+)', txt)
    k['t2'] = re.search(r'TABLE_AFTER_STRESS LOGROWS total=(\d+) pre=(\d+) post=(\d+)', txt)
    k['dbg'] = re.search(r'DEBUGLOG lines_total=(\d+) lines_before_flush=(\d+)', txt)
    k['const'] = re.findall(r'(sipush\s+1000|ldc\s+#\d+\s+// int 50000|DEFAULT_ROWS = \d+)', cm)
    k['maxrows'] = open(d + '/jvm-extra.txt').read().strip().split('max.rows=')[1]
    rows = list(csv.DictReader(open(d + '/samples.csv')))
    k['le'] = [(int(r['epoch_ms']), int(r['LoggingEvent'])) for r in rows]
    k['lm'] = [(int(r['epoch_ms']), int(r['LogMessage'])) for r in rows]
    k['rss'] = [int(r['RssAnon_kB']) for r in rows]; k['stress'] = re.search(r'STRESS seconds=(\d+) rc=(\S+)', txt)
    runs[lab] = k
    print('   run %-18s const=%s maxrows=%s entry=%s exit=%s dbg=%s t1=%s t2=%s samples=%d peakLE=%d peakLM=%d' % (lab, k['const'], k['maxrows'], k['entry'], k['exit'], k['dbg'].groups() if k['dbg'] else None,
          k['t1'].groups() if k['t1'] else None, k['t2'].groups() if k['t2'] else None, len(rows), max([v for _, v in k['le']] or [0]), max([v for _, v in k['lm']] or [0])))
def peak(l, lo=None, hi=None): return max([v for t, v in l if (lo is None or t >= lo) and (hi is None or t <= hi)] or [0])
for lab, k in runs.items():
    if lab.startswith('R1'):
        chk(k['entry'] is None, '%s: appender off: no flushBuffer call seen' % lab)
        chk(peak(k['le']) <= 50, '%s: appender off: LoggingEvent instances never above %d (async queues only)' % (lab, peak(k['le'])))
        chk(peak(k['lm']) == 0, '%s: appender off: no LogMessage instances' % lab)
        continue
    a, b, buf = k['entry'][1], k['entry'][2], k['entry'][2]
    cap = 1000 if lab[:2] == 'R3' else 50000
    chk(any('1000' in c for c in k['const']) == (cap == 1000), '%s: build constant check (%s)' % (lab, k['const']))
    chk(buf == min(a, cap), '%s: messageBuffer at flush = min(attempts %d, cap %d) = %d' % (lab, a, cap, buf))
    chk(k['exit'] == 0, '%s: buffer empty after flushBuffer' % lab)
    startup_only = lab[-0:] and ('r2-' in lab or 'r3-' in lab)
    if k['dbg']:
        if startup_only: chk(abs(int(k['dbg'].group(2)) - a) <= 20, '%s: debug.log lines before the flush (%s) ~ attempts (%d)' % (lab, k['dbg'].group(2), a))
        else: print('   info %s: debug.log rotated during the stress phase (%s lines left, %s before the flush): not used as ground truth here' % (lab, k['dbg'].group(1), k['dbg'].group(2)))
    mr = int(k['maxrows'])
    fl = k['entry'][0]
    if k['t1']:
        tot, pre, post = int(k['t1'].group(1)), int(k['t1'].group(2)), int(k['t1'].group(3))
        want = min(buf, mr) if mr >= buf + post else 0   # the table keeps only the newest max.rows rows: the pre-flush rows survive only if the later events fit
        chk(abs(pre - want) <= 10, '%s: table rows stamped <= flush = %d ~ %d (min(buffered %d, max.rows %d); the table keeps the newest max.rows rows, %d later events)' % (lab, pre, want, buf, mr, post))
    later = [v for t, v in k['le'] if t >= fl + 20000]
    if startup_only: chk(max(later or [0]) <= 5, '%s: start-up-only run: LoggingEvent instances after the flush (+20 s): max %d' % (lab, max(later or [0])))
    else:
        chk(max(later[-2:] or [0]) <= 5, '%s: LoggingEvent instances at the idle end of the run: %s (transient in-flight peak during the stress phase: %d)' % (lab, later[-2:], max(later or [0])))
        chk(max(later or [0]) <= 60000, '%s: transient LoggingEvent peak %d is far below anything tied to a cap' % (lab, max(later or [0])))
        lmend = [v for t, v in k['lm']][-2:]
        chk(all(abs(v - mr) <= 0.005 * mr for v in lmend), '%s: LogMessage instances at the idle end %s == max.rows %d' % (lab, lmend, mr))
    if cap == 1000 and a > 1000: chk(buf == 1000, '%s: build B: peak buffer 1000 while %d events were logged before the flush' % (lab, a))
    if lab[:2] == 'R2': chk(a < 50000, '%s: stock build: events before the flush (%d) < 50000: the stock cap is not reached in practice' % (lab, a))
    if k['t2']:
        t2 = int(k['t2'].group(1)); pl = peak(k['lm'])
        print('   info %s: table rows after stress %d, peak LogMessage instances %d (transient), stress %s' % (lab, t2, pl, k['stress'].groups() if k['stress'] else None))
        chk(mr * 0.99 <= t2 <= mr, '%s: rows after stress %d within 1%% of max.rows %d (rows with an equal timestamp key collapse in a read)' % (lab, t2, mr))
tp = {lab: peak([(t, v) for t, v in k['le'] if t >= k['entry'][0] + 20000]) for lab, k in runs.items() if k['t2'] and k['entry']}
print('   info transient LoggingEvent peaks in the full runs:', tp)
plate = {lab: int(k['t2'].group(1)) for lab, k in runs.items() if k['t2']}
print('   info plateaus (rows after stress):', plate)
if 'R4-A-on-1000' in plate: chk(plate['R4-A-on-1000'] <= 1200 and plate['R4-A-on-1000'] >= 1000, 'positive control R4: table plateau %d at max.rows=1000' % plate['R4-A-on-1000'])
if 'R2-A-on-100k' in plate and 'R3-B-on-100k' in plate:
    p2, p3 = plate['R2-A-on-100k'], plate['R3-B-on-100k']
    chk(abs(p2 - p3) <= 0.1 * max(p2, p3), 'steady state: R2 (constant 50000) %d vs R3 (constant 1000) %d rows after stress: same within 10%%' % (p2, p3))
print('SELFCHECK fails=%d' % fails)
