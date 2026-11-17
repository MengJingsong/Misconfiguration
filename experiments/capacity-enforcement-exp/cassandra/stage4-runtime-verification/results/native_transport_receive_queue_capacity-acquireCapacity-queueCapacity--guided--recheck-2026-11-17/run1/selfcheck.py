#!/usr/bin/env python3
"""Independent self-check of run 1 (written after run 1, separate code from recheck-run.py's analysis).
usage: selfcheck.py <run folder on pc72, e.g. /mydata/s4/ntq-recheck/logs/run1>
Re-parses ntq.trace with its own tokenizer (key=value split, not the run script's regexes), ties handlers to arms by the
client's ports in each flood.out, and recomputes per arm: refusals, decodes with backpressure, per-handler final queueSize,
peak sum of queueSize (by time order of the file), the time-weighted mean of the decoded sum over the last third of the
client's sending window (event-weighted by elapsed ms, not per-second samples), the per-IP/global limits, and compares
the histogram counts and arms.csv."""
import csv, re, sys

run = sys.argv[1]
arms = ['U10', 'D20', 'D30', 'D40', 'T40', 'L20']
port2arm, win = {}, {}
for a in arms:
    s = e = None
    for l in open(f'{run}/{a}/flood.out'):
        m = re.match(r'conn \d+ local=/?(\S+) ', l)
        if m:
            port2arm[m.group(1)] = a
        if l.startswith('start ms='):
            s = int(l.split('=')[1].split()[0])
        if l.startswith('stop ms='):
            e = int(l.split('=')[1].split()[0])
    win[a] = (s, e)
h2arm = {}
st = {a: dict(ref=0, decbp=0, dec=0, succ=0, disc=0, q={}, d={}, sumA=0, sumD=0, peakA=0, peakD=0, lim=set(),
              last=None, wsum=0.0, wt=0.0, M=set()) for a in arms}
for l in open(f'{run}/ntq.trace', errors='replace'):
    t = l.split()
    if not t:
        continue
    kv = dict(x.split('=', 1) for x in t[1:] if '=' in x)
    kind = t[0]
    if kind == 'new':
        a = port2arm.get(kv['remote'].lstrip('/'))
        if a:
            h2arm[kv['id']] = a
        continue
    a = h2arm.get(kv.get('id'))
    if a is None:
        continue
    S = st[a]
    i = kv['id']
    ms = int(kv['ms'])
    s0, e0 = win[a]
    lt0 = s0 + (e0 - s0) * 2 // 3
    # time-weighted decoded sum over [lt0, e0]
    if S['last'] is not None:
        lo, hi = max(S['last'], lt0), min(ms, e0)
        if hi > lo:
            S['wsum'] += S['sumD'] * (hi - lo); S['wt'] += hi - lo
    S['last'] = ms
    if kind == 'acq':
        if kv['out'] == 'SUCCESS':
            S['succ'] += 1
        else:
            S['ref'] += 1
        q = int(kv['q']); S['sumA'] += q - S['q'].get(i, 0); S['q'][i] = q
        S['lim'].add((kv['ep'].split('/')[1], kv['gl'].split('/')[1]))
    elif kind == 'rel':
        q = int(kv['q']); S['sumA'] += q - S['q'].get(i, 0); S['q'][i] = q
    elif kind == 'dec':
        b = int(kv['b']); S['dec'] += 1; S['M'].add(b)
        if kv['bp'] == 'BYTES_IN_FLIGHT':
            S['decbp'] += 1
        S['d'][i] = S['d'].get(i, 0) + b; S['sumD'] += b
    elif kind == 'rls':
        b = int(kv['b']); S['d'][i] = S['d'].get(i, 0) - b; S['sumD'] -= b
    elif kind == 'disc':
        S['disc'] += 1
    S['peakA'] = max(S['peakA'], S['sumA']); S['peakD'] = max(S['peakD'], S['sumD'])
rows = {r['arm']: r for r in csv.DictReader(open(f'{run}/arms.csv'))}
ok = bad = 0


def chk(desc, c):
    global ok, bad
    ok += bool(c); bad += (not c)
    print(('ok   ' if c else 'FAIL ') + desc)


for a in arms:
    S = st[a]
    M = max(S['M'])
    lims = sorted(S['lim'], key=lambda x: -sum(1 for _ in x))
    endq = sum(S['q'].values())
    lt = S['wsum'] / S['wt'] if S['wt'] else None
    print(f'{a}: handlers {len(S["q"])}, M {sorted(S["M"])}, refusals {S["ref"]}, dec {S["dec"]}, dec_bp {S["decbp"]}, '
          f'disc {S["disc"]}, end sum q {endq}, peak sumA {S["peakA"]}, peak sumD {S["peakD"]}, '
          f'time-weighted last-third sumD {lt}, (ep,gl) limits seen {len(S["lim"])}')
    r = rows[a]
    chk(f'{a}: refusals agree with arms.csv ({S["ref"]} vs {r["refusals"]})', S['ref'] == int(r['refusals']))
    chk(f'{a}: peak sumA agrees ({S["peakA"]} vs {r["peak_sumA"]})', S['peakA'] == int(r['peak_sumA']))
    chk(f'{a}: peak sumD agrees ({S["peakD"]} vs {r["peak_sumD"]})', S['peakD'] == int(r['peak_sumD']))
    chk(f'{a}: end sum q agrees ({endq} vs {r["end_q_sum"]})', endq == int(r['end_q_sum']))
    if lt is not None and r['lastthird_sumD'] not in ('', 'None'):
        chk(f'{a}: time-weighted last-third sumD {lt:.0f} within 1 % of the run script\'s per-second mean '
            f'{float(r["lastthird_sumD"]):.0f}', abs(lt - float(r['lastthird_sumD'])) <= 0.01 * lt)
    if a.startswith('D'):
        chk(f'{a}: end sum q = -refusals*M ({endq} = {-S["ref"] * M})', endq == -S['ref'] * M)
        chk(f'{a}: decodes with BYTES_IN_FLIGHT = refusals ({S["decbp"]} = {S["ref"]})', S['decbp'] == S['ref'])
        chk(f'{a}: time-weighted last-third sumD {lt:.0f} > G 214748364', lt > 214748364)
print(f'selfcheck: {ok} ok, {bad} FAIL')
