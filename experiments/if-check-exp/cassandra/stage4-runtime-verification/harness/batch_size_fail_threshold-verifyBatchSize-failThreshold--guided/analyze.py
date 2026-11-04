#!/usr/bin/env python3
"""Analysis of batch_size_fail_threshold-verifyBatchSize-failThreshold--guided, both tiers (case 9a with R3, R5, R7).
usage: analyze.py <tier> <file with req lines> <Byteman trace> [<log with the 'exceeding specified threshold' lines>]
Reads the SendBatches req lines (arm names t<KiB>k-b<MiB>m, ctl16k, C-msg512k-b16m), prints one table row per arm and
EXPECTED lines for every part of the prediction. The primary reading is total = dec + exe (R7); bst is the filed 9d
reading, reported beside it. It prints readings and checks; the AI matches them to a row of 9a in the results file."""
import re, statistics, sys

tier, reqf, tracef = sys.argv[1], sys.argv[2], sys.argv[3]
logf = sys.argv[4] if len(sys.argv) > 4 else None
MiB = 1 << 20
reqs = []
for l in open(reqf):
    if not l.startswith('req '):
        continue
    d = dict(kv.split('=', 1) for kv in l.split()[1:])
    for k in ('k', 'nominal', 'dec', 'exe', 'bst', 'size', 'fail', 'rej'):
        d[k] = int(d[k])
    d['total'] = (max(d['dec'], 0) + max(d['exe'], 0))
    reqs.append(d)
arms = []
for d in reqs:
    if d['arm'] not in arms:
        arms.append(d['arm'])
by = {a: [d for d in reqs if d['arm'] == a] for a in arms}


def med(a, key):
    v = [d[key] for d in by.get(a, [])]
    return statistics.median(v) if v else None


def expect(desc, cond):
    print(f'EXPECTED: {desc} — {"yes" if cond else "NO"}')
    return cond


print(f'tier {tier}: {len(reqs)} requests in {len(arms)} arms')
print('arm | n | outcomes | rej | size med | dec med (min..max) | exe med | bst med | total med (min..max) | total/nominal')
for a in arms:
    rs = by[a]
    oc = {}
    for d in rs:
        o = d['outcome'] if d['outcome'] == 'ok' else d['outcome'].split(':')[1] + ':' + d['outcome'].split(':', 2)[2][:40]
        oc[o] = oc.get(o, 0) + 1
    tot = [d['total'] for d in rs]
    dec = [d['dec'] for d in rs]
    print(f"{a} | {len(rs)} | {oc} | {sum(d['rej'] for d in rs)} | {med(a, 'size'):.0f} | {med(a, 'dec'):.0f} ({min(dec)}..{max(dec)}) | "
          f"{med(a, 'exe'):.0f} | {med(a, 'bst'):.0f} | {med(a, 'total'):.0f} ({min(tot)}..{max(tot)}) | {med(a, 'total') / rs[0]['nominal']:.3f}")

# ---- validity: the check fires iff size > threshold, with the client error and the rej line
bad = []
for d in reqs:
    if d['arm'].startswith('C-'):
        continue
    reached = d['lines'].split('/')[3] == '1'
    rejected_client = d['outcome'].startswith('ERR:InvalidRequestException:Batch_too_large')
    if not reached or (d['size'] > d['fail']) != (d['rej'] == 1) or (d['rej'] == 1) != rejected_client:
        bad.append(d)
expect(f'V1 every batch outside the control reached verifyBatchSize and was rejected (client "Batch too large" and rej line) iff dataSize > threshold — mismatches {len(bad)}', not bad)
for d in bad[:5]:
    print('  mismatch:', d)
lines_ok = all(d['lines'] in ('1/1/1/1/0', '1/1/1/1/1') for d in reqs if not d['arm'].startswith('C-'))
expect('V2 one dec, exe, bst, siz line per request outside the control', lines_ok)
nrej = sum(d['rej'] for d in reqs)
if logf:
    nlog = sum(1 for l in open(logf, errors='replace') if 'exceeding specified threshold' in l and 'batch_size_fail_threshold' in l)
    expect(f'V3 one "exceeding specified threshold … (see batch_size_fail_threshold)" log line per rejection — log {nlog}, rejections {nrej}', nlog == nrej)
reached_limit = any(d['rej'] for d in reqs)
expect('V4 some batch exceeded the threshold (else Invalid run)', reached_limit)
ctl = by.get('ctl16k', [])
expect('V5 control ctl16k: every 16 KiB batch accepted', bool(ctl) and all(d['outcome'] == 'ok' and d['rej'] == 0 for d in ctl))

# ---- prediction on the rejected pairs (R5)
REJ = {1: ['t50k-b1m', 't500k-b1m'], 4: ['t50k-b4m', 't500k-b4m'], 16: ['t50k-b16m', 't500k-b16m', 't5120k-b16m']}


def all_rejected(a):
    return bool(by.get(a)) and all(d['rej'] == 1 for d in by[a])


expect('P0 the rejected pairs of R5 were all rejected, and t5120k-b1m, t5120k-b4m all accepted',
       all(all_rejected(a) for v in REJ.values() for a in v)
       and all(d['outcome'] == 'ok' for a in ('t5120k-b1m', 't5120k-b4m') for d in by.get(a, [{'outcome': 'missing'}])))
for key, name in (('total', 'primary total = dec + exe (R7)'), ('bst', 'secondary bst (the filed 9d reading)')):
    print(f'-- {name}')
    for b, al in REJ.items():
        m = [med(a, key) for a in al]
        spread = (max(m) - min(m)) / min(m) if min(m) > 0 else float('inf')
        expect(f'P1[{key}] {b} MiB: rejected medians across thresholds {dict(zip(al, m))} differ by {spread * 100:.1f} % (< 10 %: "the same", R3)', spread < 0.10)
    m50 = [med(f't50k-b{b}m', key) for b in (1, 4, 16)]
    expect(f'P2[{key}] grows with batch size at 50 KiB: medians 1/4/16 MiB {m50} (ratios 4/1 {m50[1] / m50[0]:.2f}, 16/4 {m50[2] / m50[1]:.2f})',
           m50[0] < m50[1] < m50[2] and m50[2] / m50[0] > 2)
    m500 = [med(f't500k-b{b}m', key) for b in (1, 4, 16)]
    expect(f'P2[{key}] grows with batch size at 500 KiB: medians {m500}', m500[0] < m500[1] < m500[2] and m500[2] / m500[0] > 2)
    f50, f5 = med('t50k-b16m', key), med('t5120k-b16m', key)
    expect(f'R[{key}] "falls with the threshold" (R3): 16 MiB median at 50 KiB {f50:.0f} more than 50 % below the median at 5 MiB {f5:.0f}? ratio {f50 / f5:.3f} — expected NOT',
           not (f50 < 0.5 * f5))
    flat = m50[2] < 1.10 * m50[0]
    expect(f'F[{key}] "flat in batch size": 16 MiB median within 10 % of 1 MiB at 50 KiB ({m50[2]:.0f} vs {m50[0]:.0f}) — expected NOT', not flat)
    acc = [med(f't5120k-b{b}m', key) for b in (1, 4)]
    print(f'INFO[{key}] accepted pairs at 5 MiB (R5, include the build and the hand-off): 1 MiB {acc[0]}, 4 MiB {acc[1]}; '
          f'rejected at 50 KiB: 1 MiB {m50[0]}, 4 MiB {m50[1]}')

# ---- positive control (scenario C)
c = by.get('C-msg512k-b16m', [])
if c:
    disc = all(d['outcome'].startswith('ERR:') and 'Batch_too_large' not in d['outcome'] and d['lines'] == '0/0/0/0/0' for d in c)
    expect(f'C1 control: every 16 MiB batch discarded by the transport before the decode (no dec/exe/bst/siz line, a transport error) — outcomes {set(d["outcome"][:80] for d in c)}', disc)
    cm, um = med('C-msg512k-b16m', 'total'), med('t50k-b16m', 'total')
    expect(f'C2 control cuts the allocation: median total {cm:.0f} vs {um:.0f} without the control (below 50 %)', cm < 0.5 * um)
