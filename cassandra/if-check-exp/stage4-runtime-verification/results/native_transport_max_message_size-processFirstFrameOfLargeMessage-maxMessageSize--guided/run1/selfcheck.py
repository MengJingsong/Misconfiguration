#!/usr/bin/env python3
"""Independent self-check of run 1, native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided.
usage: selfcheck.py <run root, e.g. ~/stage4-logs/nms/run1>
Re-parses the raw files only (unit/harness.out; cluster/<label>/client.txt, poll.csv, nms.trace, system.log) with its own code,
not the run scripts', recomputes every figure the conclusion uses and compares it with the run script's summary lines where
one exists. Prints one 'ok'/'FAIL' line per check and the 9a row it derives; exit 1 if any check fails."""
import math, os, re, statistics, sys

R = os.path.expanduser(sys.argv[1])
MiB = 1 << 20
FRAME_PAYLOAD = 131071            # largest frame payload (17-bit length)
FRAME_STASH = FRAME_PAYLOAD + 10  # what FrameDecoder stashes per full frame: 6-byte header + payload + 4-byte CRC
res = {'ok': 0, 'fail': 0}


def chk(name, cond, detail=''):
    res['ok' if cond else 'fail'] += 1
    print(f'{"ok  " if cond else "FAIL"} {name} {detail}')
    return cond


def band(x):
    return 'about 8 MiB' if 6 * MiB <= x <= 10 * MiB else ('about one frame' if x <= MiB else 'neither')


# ------------------------------------------------------------------ unit tier
print('== unit tier')
U = f'{R}/unit/harness.out'
rd = [dict(re.findall(r'(\w+)=(\S*)', l)) for l in open(U) if l.startswith('STAGE4 reading ')]
chk('unit readings present', len(rd) == 16, f'{len(rd)} lines')
summ = [l for l in open(U) if l.startswith('STAGE4 summary')]
chk('unit harness instrument checks all ok', bool(summ) and 'mismatches=0' in summ[-1], summ[-1].strip() if summ else 'none')
for r in rd:
    body, lim, fr, sent = int(r['body']), int(r['limit']), int(r['frames']), int(r['sent_frames'])
    env = body + 9
    exp_frames = 1 if env <= FRAME_PAYLOAD else math.ceil(env / FRAME_PAYLOAD)
    chk(f'unit {r["step"]} frame count', fr == exp_frames and sent == fr - 1, f'frames {fr} expected {exp_frames}')
    if fr == 1:
        chk(f'unit {r["step"]} single-frame: no LargeMessage, RESULT', r['lm'] == '0' and r['resp_opcode'] == '8', f'lm {r["lm"]} op {r["resp_opcode"]}')
        continue
    if body > lim:
        want = f'CQL_Message_of_size_{body}_bytes_exceeds_allowed_maximum_of_{lim}_bytes'
        chk(f'unit {r["step"]} refused: tooBig, 0 buffers, discarded +1, oversized error',
            r['toobig'] == '1' and r['buffers'] == '0' and r['buffer_bytes'] == '0' and r['discarded_delta'] == '1'
            and r['resp_opcode'] == '0' and r['resp_code'] == '8704' and r['resp_msg'] == want,
            f'toobig {r["toobig"]} buffers {r["buffers"]} bytes {r["buffer_bytes"]} disc {r["discarded_delta"]} {r["resp_code"]} {r["resp_msg"][:80]}')
    else:
        chk(f'unit {r["step"]} admitted: every sent frame kept, discarded +0, RESULT',
            r['toobig'] == '0' and int(r['buffers']) == sent and int(r['buffer_bytes']) == sent * FRAME_PAYLOAD
            and r['discarded_delta'] == '0' and r['resp_opcode'] == '8',
            f'buffers {r["buffers"]}/{sent} bytes {r["buffer_bytes"]} disc {r["discarded_delta"]} op {r["resp_opcode"]}')
unit8 = {int(r['limit']) // MiB: int(r['buffer_bytes']) for r in rd if r['step'].endswith('req8m')}
for k, v in sorted(unit8.items()):
    print(f'     unit 8 MiB request kept at {k} MiB: {v} B ({v / MiB:.3f} MiB) -> {band(v)}')
ub = {k: band(v) for k, v in unit8.items()}
if ub.get(1) == ub.get(4) == 'about one frame' and ub.get(16) == 'about 8 MiB':
    urow = 'Refuted'
elif all(v == 'about 8 MiB' for v in ub.values()):
    urow = 'Confirmed-shape (no control at the unit tier)'
else:
    urow = 'other: ' + str(ub)
print(f'UNIT ROW (derived): {urow}')

# ------------------------------------------------------------------ cluster tier
print('== cluster tier')
CL = f'{R}/cluster'
summary = open(f'{CL}/summary.txt').read()
cres = {}
for label in ('k16', 'k4', 'k1', 'kdef', 'ref', 'ctl'):
    d = f'{CL}/{label}'
    if not os.path.isdir(d):
        chk(f'{label} present', False)
        continue
    ev = {}
    for l in open(f'{d}/client.txt'):
        if l.strip():
            m = re.search(r' ms=(\d+)', l)
            ev.setdefault(l.split()[0], []).append((int(m.group(1)) if m else None, l.strip()))
    rows = []
    for l in open(f'{d}/poll.csv'):
        p = l.strip().split(',')
        if len(p) == 7 and p[0].isdigit() and 'ERR' not in p:
            rows.append([int(x) for x in p])
    t_idle, t_send, t_held = ev['IDLE'][0][0], ev['SEND'][0][0], ev['HELD'][0][0]
    base = [r for r in rows if t_idle + 2000 <= r[0] <= t_send]
    bsize = statistics.median(r[1] for r in base)
    s5 = [r for r in rows if r[0] <= t_held + 5000][-1]
    ret = s5[1] - bsize
    m = re.search(rf'READING \[{label}\] retained \(Size at 5 s - baseline\) = (-?\d+) B', summary)
    chk(f'{label} retained recomputed = run script', m is not None and int(m.group(1)) == round(ret), f'{ret:.0f} vs {m.group(1) if m else None}')
    ovf = s5[3] - statistics.median(r[3] for r in base)
    dirr = s5[4] - statistics.median(r[4] for r in base)
    chk(f'{label} pool rise is all overflow (frame stashes); direct memory rises the same', ovf == ret and dirr == ret,
        f'Size +{ret:.0f} Overflow +{ovf:.0f} direct +{dirr:.0f}')
    # the trace: buffers kept per connection at 5 s of the hold
    tr = open(f'{d}/nms.trace').read().splitlines()
    last = {}
    for l in tr:
        if l.startswith('frm '):
            q = dict(re.findall(r'(\w+)=(\S+)', l))
            if int(q['ms']) <= t_held + 5000:
                last[q['h']] = q
    kept = sum(int(q['n']) for q in last.values())
    print(f'     {label}: retained {ret:.0f} B = {ret / FRAME_STASH:.2f} frame stashes of {FRAME_STASH} B; trace buffers kept {kept} '
          f'({", ".join(q["h"] + ":n=" + q["n"] + ",toobig=" + q["toobig"] for q in last.values())})')
    resp = [l for _, l in ev.get('RESP', [])]
    disc = rows[-1][6] - statistics.median(r[6] for r in base)
    lm = [l for l in tr if l.startswith('lm ')]
    sizes = sorted({int(dict(re.findall(r'(\w+)=(\S+)', l))['size']) for l in lm})
    cfg = re.search(r'native_transport_max_message_size=([^;\]]*)', open(f'{d}/system.log').read())
    print(f'     {label}: knob in config dump {cfg.group(1) if cfg else None}; LargeMessage sizes {sizes}; RequestDiscarded +{disc:.0f}; responses: '
          + ' | '.join(r.split(' ', 2)[2][:110] for r in resp))
    cres[label] = dict(ret=ret, kept=kept, resp=resp, disc=disc, last=last, tr=tr, held=ev['HELD'][0][1], ev=ev)

if all(k in cres for k in ('k16', 'k4', 'k1', 'ref', 'ctl')):
    for k in ('k4', 'k1'):
        c = cres[k]
        chk(f'{k}: refused by the check (toobig trace, discarded +1, oversized error, nothing kept)',
            all(q['toobig'] == 'true' and q['n'] == '0' for q in c['last'].values()) and c['disc'] == 1
            and len(c['resp']) == 1 and 'code=8704' in c['resp'][0] and 'exceeds_allowed_maximum' in c['resp'][0], c['resp'][0][:120] if c['resp'] else '')
    for k in ('k16', 'kdef', 'ref', 'ctl'):
        if k in cres:
            c = cres[k]
            chk(f'{k}: every request admitted and answered RESULT, discarded +0',
                all('opcode=8 code=1' in r for r in c['resp']) and c['disc'] == 0, ' | '.join(r[:60] for r in c['resp']))
            chk(f'{k}: retained = kept frame stashes (+ at most 8 paused stashes)',
                0 <= c['ret'] - c['kept'] * FRAME_STASH <= 8 * FRAME_STASH, f'{c["ret"]:.0f} vs {c["kept"]} x {FRAME_STASH}')
    acq = [dict(re.findall(r'(\w+)=(\S+)', l)) for l in cres['ctl']['tr'] if l.startswith('acq ')]
    t_held = cres['ctl']['ev']['HELD'][0][0]
    before = [a['out'] for a in acq if int(a['ms']) <= t_held + 5000]
    chk('ctl: during the hold one request admitted, the other refused capacity (R1 binds)',
        sorted(before)[:1] != [] and before.count('SUCCESS') == 1 and any(o.startswith('INSUFFICIENT') for o in before), str(before))
    chk('ref: both requests admitted with no reserve failure',
        all(dict(re.findall(r'(\w+)=(\S+)', l))['out'] == 'SUCCESS' for l in cres['ref']['tr'] if l.startswith('acq ')))
    b = {k: band(cres[k]['ret']) for k in ('k16', 'k4', 'k1')}
    lowers = cres['ctl']['ret'] < cres['ref']['ret'] and band(cres['ctl']['ret']) == 'about 8 MiB'
    print(f'     bands {b}; ref {cres["ref"]["ret"] / MiB:.3f} MiB, ctl {cres["ctl"]["ret"] / MiB:.3f} MiB, control lowers: {lowers}')
    if cres['k16']['ret'] <= MiB:
        row = 'Invalid run'
    elif all(v == 'about 8 MiB' for v in b.values()):
        row = 'Confirmed' if lowers else 'Not confirmed (control flat)'
    elif b['k1'] == b['k4'] == 'about one frame' and b['k16'] == 'about 8 MiB':
        row = 'Refuted'
    elif all(v == 'about one frame' for v in b.values()):
        row = 'Not confirmed (one frame everywhere)'
    else:
        row = 'no row fits'
    m = re.search(r'ROW \(computed by the run script[^:]*\): ([A-Za-z ]+)', summary)
    chk('cluster row derived here = run script row', m is not None and m.group(1).split()[0] == row.split()[0], f'{row} vs {m.group(1) if m else None}')
    print(f'CLUSTER ROW (derived): {row}')
print(f'checks ok {res["ok"]} fail {res["fail"]}')
sys.exit(1 if res['fail'] else 0)
