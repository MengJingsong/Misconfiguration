#!/usr/bin/env python3
"""Independent self-check of run 1, native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided.
Re-parses the raw files only (never summary.txt's EXPECTED lines or arms.csv's derived numbers, which it compares against):
  unit:    <root>/unit/test.out (STAGE4 lines), <root>/unit/nqa.trace
  cluster: <root>/cluster/<label>/{client.txt, poll.csv, final.json, histogram-idle.txt, histogram-at-peak.txt, nqa.trace},
           <root>/cluster/summary.txt (JMX read-back lines only), <root>/cluster/arms.csv (compared, not used)
usage: python3 selfcheck.py [~/stage4-logs/nqa/run1]      prints "ok"/"FAIL" per check and a summary; exit 1 on any FAIL.
The frozen prediction (§9a + 9f R4) is evaluated here from the raw readings, with the same edges; the source-derived
throwing-mode estimate admitted ~= 4 + 1 + rate x limit is reported for information (not a frozen relation)."""
import csv, json, os, re, statistics, sys

ROOT = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/stage4-logs/nqa/run1')
MiB, GiB = 1 << 20, 1 << 30
RATE, SECONDS = 100, 60
LABELS = ['off1', 't0.5', 't0.1', 't0.02', 'off2', 'd0.1', 'ctl', 'off3']
THR = {'off1': None, 'off2': None, 'off3': None, 't0.5': 0.5, 't0.1': 0.1, 't0.02': 0.02, 'd0.1': 0.1, 'ctl': None}
THROW = {l: l != 'd0.1' for l in LABELS}
GLOB = {l: (8 * MiB if l == 'ctl' else GiB) for l in LABELS}
res = []


def check(name, cond, detail=''):
    res.append(bool(cond))
    print(('ok   ' if cond else 'FAIL ') + name + (' — ' + detail if detail else ''))


def info(s):
    print('info ' + s)


# ---------------------------------------------------------------- unit tier
U = ROOT + '/unit'
lines = open(U + '/test.out').read().splitlines()
checks = [l for l in lines if l.startswith('STAGE4 check')]
check('unit: STAGE4 check lines present and none MISMATCH', checks and not any('MISMATCH' in l for l in checks), f'{len(checks)} checks')
M_unit = int(re.search(r'STAGE4 info M=(\d+)', '\n'.join(lines)).group(1))
info(f'unit M = {M_unit} B')
arms = {}
for l in lines:
    m = re.match(r'STAGE4 arm (u\d) thr=(\S+) limit_ms=(\S+) global=(\d+) sent=(\d+) peak_pending=(\d+) peak_active=(\d+) admitted=(\d+) '
                 r'queued_bytes=(\d+) peak_requests_size=(\d+) refused_queue=(\d+) refused_bytes=(\d+) discarded=(\d+)', l)
    if m:
        arms[(m.group(1), m.group(2))] = dict(limit=m.group(3), glob=int(m.group(4)), sent=int(m.group(5)), adm=int(m.group(8)),
                                              qb=int(m.group(9)), rs=int(m.group(10)), rq=int(m.group(11)), rb=int(m.group(12)),
                                              disc=int(m.group(13)))
for k, a in arms.items():
    check(f'unit {k}: queued_bytes = admitted x M', a['qb'] == a['adm'] * M_unit, f"{a['qb']} vs {a['adm']}x{M_unit}")
    check(f'unit {k}: admitted + refused = sent', a['adm'] + a['rq'] + a['rb'] == a['sent'])
    check(f'unit {k}: RequestDiscarded = refusals', a['disc'] == a['rq'] + a['rb'])
    if a['limit'] not in ('inf',):
        est = 4 + 1 + 50 * float(a['limit']) / 1000
        info(f"unit {k}: admitted {a['adm']} vs source estimate 5 + 50 x limit = {est:.1f}")
offu = arms[('u4', 'off')]['qb']
for t in ('0.2', '0.05', '0.01'):
    a = arms[('u4', t)]
    info(f"unit u4 thr={t}: queued bytes {a['qb']} = {100 * a['qb'] / offu:.1f} % of check-off {offu}")
check('unit u4: queued bytes fall monotonically with the threshold (off > 0.2 > 0.05 > 0.01)',
      offu > arms[('u4', '0.2')]['qb'] > arms[('u4', '0.05')]['qb'] > arms[('u4', '0.01')]['qb'])
c = arms[('u5', 'off')]
check('unit u5 control: RequestsSize <= 2 MiB with "bytes in flight" refusals', c['rs'] <= 2 * MiB and c['rb'] > 0, f"{c['rs']}, {c['rb']}")
tr = open(U + '/nqa.trace').read().splitlines()
hin = sum(1 for l in tr if l.startswith('hold in')); hout = sum(1 for l in tr if l.startswith('hold out'))
check('unit trace: every hold in has a hold out', hin == hout and hin > 0, f'{hin}/{hout}')
# the chk lines' verdict must equal age < timeout x thr (allowing one approx-clock tick, the line re-reads the age)
bad = 0; n = 0
for l in tr:
    m = re.match(r'chk ms=\d+ age_ns=(\d+) thr=(\S+) timeout_ns=(\d+) ret=(\w+)', l)
    if m:
        age, thr, to, ret = int(m.group(1)), float(m.group(2)), int(m.group(3)), m.group(4) == 'true'
        if thr <= 0:
            exp = True
        else:
            lim = to * thr
            if abs(age - lim) < 20_000_000:
                continue        # within 20 ms of the limit: the re-read age may straddle it
            exp = age < lim
        n += 1
        bad += exp != ret
check('unit trace: every chk verdict = (age < timeout x threshold) away from the edge', bad == 0, f'{n} lines, {bad} disagree')

# ---------------------------------------------------------------- cluster tier
CL = ROOT + '/cluster'
summ = open(CL + '/summary.txt').read()
derived = {r['label']: r for r in csv.DictReader(open(CL + '/arms.csv'))}
R = {}
for l in LABELS:
    d = f'{CL}/{l}'
    rb = re.search(rf'\[{re.escape(l)}\] JMX read-back: threshold=(\S+) throw_on_overload=(\S+) timeout_ms=(\S+) in_flight=(\S+) '
                   rf'in_flight_per_ip=(\S+) request_pool_max=(\S+)', summ)
    want_thr = THR[l] if THR[l] is not None else sys.float_info.max
    check(f'{l}: JMX read-back threshold, mode, 12 s timeout, in-flight limits, pool 4',
          rb and abs(float(rb.group(1)) - want_thr) <= 1e-12 * max(1, want_thr) and rb.group(2) == str(THROW[l]).lower()
          and float(rb.group(3)) == 12000 and float(rb.group(4)) == GLOB[l] and float(rb.group(5)) == GiB and float(rb.group(6)) == 4,
          rb.group(0) if rb else 'missing')
    ct = open(d + '/client.txt').read().splitlines()
    reqs = [tuple(re.match(r'r k=(\d+) sent_ms=(\d+) resp_ms=(-?\d+) outcome=(\S+)', x).groups()) for x in ct if x.startswith('r k=')]
    reqs = [(int(a), int(b), int(c), e) for a, b, c, e in reqs]
    oc = {}
    for r in reqs:
        oc[r[3]] = oc.get(r[3], 0) + 1
    adm = sum(v for k, v in oc.items() if k not in ('ovl_queue', 'ovl_bytes'))
    check(f'{l}: {RATE * SECONDS} requests sent, every one answered', len(reqs) == RATE * SECONDS and 'none' not in oc, str(oc))
    span = (reqs[-1][1] - reqs[0][1]) / 1000
    check(f'{l}: send span {span:.2f} s at 100/s (59.99 s nominal, within 0.5 s)', abs(span - 59.99) < 0.5)
    fin = json.loads(open(d + '/final.json').read())
    rows = []
    for x in open(d + '/poll.csv'):
        p = x.strip().split(',')
        if len(p) == 12 and 'ERR' not in p:
            rows.append([float(v) for v in p])
    peak_rs = max([r[1] for r in rows] + [fin['requests_size']])
    def hist(f):
        b = t = None
        for x in open(f):
            p = x.split()
            if len(p) >= 4 and p[3] == '[B': b = int(p[2])
            if len(p) == 3 and p[0] == 'Total': t = int(p[2])
            if len(p) >= 4 and p[3].endswith('ExecuteMessage'): R.setdefault(l, {})['hist_exec'] = int(p[1])
        return b, t
    b0, t0 = hist(d + '/histogram-idle.txt'); b1, t1 = hist(d + '/histogram-at-peak.txt')
    tr = open(d + '/nqa.trace').read().splitlines()
    holds = [x for x in tr if x.startswith('hold in')]
    falses = [int(re.search(r'ms=(\d+)', x).group(1)) for x in tr if x.startswith('chk ') and ' ret=false' in x]
    first_q_ms = reqs[4][1]
    queued_at_fin = fin['pending'] + fin['active']
    R.setdefault(l, {}).update(dict(peak_rs=peak_rs, adm=adm, oc=oc, qcount=queued_at_fin, ba_rise=b1 - b0, live_rise=t1 - t0,
                                    holds=len(holds), falses=len(falses), first_false=(min(falses) - first_q_ms) if falses else None,
                                    disc=fin['discarded'], paused=fin['paused'], pool_size=max([r[4] for r in rows] + [fin['pool_size']]),
                                    pool_over=max([r[6] for r in rows] + [fin['pool_overflow']]), series=[r[1] for r in rows if r[0] <= fin['ms']]))
    x = R[l]
    check(f'{l}: stall held exactly 4 (hold in lines; ActiveTasks {fin["active"]})', x['holds'] == 4 and fin['active'] == 4)
    if THROW[l]:
        check(f'{l}: admitted (client outcomes) = PendingTasks + ActiveTasks at the peak = live ExecuteMessage',
              adm == queued_at_fin == x.get('hist_exec'), f'{adm} / {queued_at_fin} / {x.get("hist_exec")}')
    check(f'{l}: arms.csv peak_requests_size agrees with the raw poll', int(float(derived[l]['peak_requests_size'])) == int(peak_rs))
    check(f'{l}: arms.csv bytearray_rise agrees with the raw histograms', int(float(derived[l]['bytearray_rise'])) == x['ba_rise'])
    info(f"{l}: peak RequestsSize {int(peak_rs)}, admitted {adm}, queued at peak {queued_at_fin}, byte[] rise {x['ba_rise']}, "
         f"live rise {x['live_rise']}, outcomes {oc}, chk false {x['falses']}, first false {x['first_false']} ms after the first "
         f"queued request, RequestDiscarded {x['disc']}, ConnectionPaused {x['paused']}, pool Size max {int(x['pool_size'])} "
         f"Overflow max {int(x['pool_over'])}")

M = statistics.median(float(derived[l]['M']) for l in LABELS if THROW[l])
info(f'cluster M (BytesReceived per request - 9) = {M:.1f} B')
# validity: check-off grows for the whole run
for l in ('off1', 'off2', 'off3'):
    s = R[l]['series']
    check(f'{l}: check off — RequestsSize nondecreasing over the run and at the end ~= 6000 x M - 1 MiB, nothing refused',
          all(b >= a for a, b in zip(s, s[1:])) and len(s) >= 25 and abs(R[l]['peak_rs'] - (6000 * M - MiB)) < 2 * M
          and R[l]['oc'].get('ovl_queue', 0) == 0 and R[l]['oc'].get('ovl_bytes', 0) == 0, f'{len(s)} samples, peak {int(R[l]["peak_rs"])}')
# disallow evidence
for l in ('t0.5', 't0.1', 't0.02'):
    x = R[l]
    lim = THR[l] * 12000
    check(f'{l}: queue-age refusals = RequestDiscarded = chk false, first false within 50 ms after limit {lim:.0f} ms',
          x['oc'].get('ovl_queue', 0) > 0 and x['oc']['ovl_queue'] == x['disc'] == x['falses'] and abs(x['first_false'] - lim) < 50,
          f"{x['oc'].get('ovl_queue')} / {x['disc']} / {x['falses']}, first {x['first_false']} ms")
    info(f"{l}: admitted {x['adm']} vs source estimate 5 + 100 x limit = {5 + 100 * lim / 1000:.1f}")
x = R['d0.1']
check('d0.1: default mode refuses nothing, pauses the connection', x['oc'].get('ovl_queue', 0) == 0 and x['paused'] > 0, f"paused {x['paused']}")
x = R['ctl']
check('ctl: positive control caps RequestsSize at <= 8 MiB, refusals "bytes in flight"', x['peak_rs'] <= 8 * MiB and x['oc'].get('ovl_bytes', 0) > 0,
      f"{int(x['peak_rs'])}, {x['oc'].get('ovl_bytes')}")
# the frozen prediction, R4 edges, on each reading of queued bytes
for obs in ('peak_rs', 'ba_rise', 'live_rise'):
    offs = [R[l][obs] for l in ('off1', 'off2', 'off3')]
    off = statistics.mean(offs); band = max(offs) - min(offs)
    vals = {l: R[l][obs] for l in ('t0.5', 't0.1', 't0.02', 'd0.1', 'ctl')}
    info(f'{obs}: check-off {offs} mean {off:.0f} band {band:.0f}; ' + '; '.join(f'{l} {v:.0f} ({100 * v / off:.2f} %)' for l, v in vals.items()))
    same = all(abs(vals[l] - off) <= band for l in ('t0.5', 't0.1', 't0.02'))
    falls = vals['t0.02'] < 0.5 * off and off - vals['t0.02'] > 3 * band
    info(f'{obs}: R4 "the same" (Confirmed edge) {same}; R4 "falls" (Refuted edge) {falls}; control < 50 % of check-off {vals["ctl"] < 0.5 * off}')
    if obs == 'peak_rs':
        check('frozen observable (R1 RequestsSize): matches exactly one §9a row edge', same != falls)
        VERDICT = 'Refuted' if falls else ('Confirmed' if same else 'neither edge')
info(f'§9a row on the R1 gauge: {VERDICT}')
print(f'SUMMARY {sum(res)} ok / {len(res) - sum(res)} FAIL of {len(res)} checks')
sys.exit(0 if all(res) else 1)
