#!/usr/bin/env python3
# Self-check for the stage-4 recheck run (2026-11-17) of native_transport_max_frame_size-decode-bytesToDiscard--autonomous.
# Re-reads the raw per-arm files (config.txt, base/D0/S1/S2/S3/R.txt, client.out, counts.txt) and applies the frozen design's
# predictions P1-P5 (with amendment S1) and conclusions rows I, R1, R2, R3, N1, N2, N3, C, N4 in order.
# usage: selfcheck.py <run dir> [arms, default CTRL:512 H64:64 H256:256 H512:512]
import os, re, sys
U = 16777216; MiB = 1048576; LIMIT = 16642998272
run = sys.argv[1]
arms = [a.split(':') for a in (sys.argv[2:] or ['CTRL:512', 'H64:64', 'H256:256', 'H512:512'])]
arms = [(n, int(k)) for n, k in arms]
SAMPLES = ['base', 'D0', 'S1', 'S2', 'S3', 'R']
HOLD = ['S1', 'S2', 'S3']

def kv(path):
    d = {}
    for line in open(path):
        for tok in line.split():
            if '=' in tok:
                k, v = tok.split('=', 1); d[k] = v
    return d

def num(v):
    return int(v.replace('+', ''))

data, flags, notes = {}, {}, []
def flag(row, cond, msg):
    flags.setdefault(row, False)
    if cond:
        flags[row] = True; notes.append('%s: %s' % (row, msg))

for name, k in arms:
    d = os.path.join(run, name)
    a = {'k': k, 'cfg': kv(os.path.join(d, 'config.txt')), 'counts': kv(os.path.join(d, 'counts.txt'))}
    for s in SAMPLES:
        a[s] = kv(os.path.join(d, s + '.txt'))
        miss = [x for x in ('nettyUsed', 'nettyMax', 'poolDirect', 'held16', 'chunks', 'inflight', 'clients', 'memory.current', 'nmt_other_delta_kib') if x not in a[s]]
        if miss:
            print('ROW Invalid: %s %s lacks %s' % (name, s, miss)); sys.exit(0)
    a['client'] = open(os.path.join(d, 'client.out')).read().splitlines()
    data[name] = a
    a['d'] = lambda key, s, a=a: num(a[s][key]) - num(a['base'][key])
    c = a['cfg']
    ok = (c.get('native_transport_max_frame_size') == '16MiB' and c.get('native_transport_max_concurrent_connections') == '-1'
          and c.get('native_transport_idle_timeout') == '0ms' and c.get('-XX:MaxDirectMemorySize') == str(LIMIT))
    flag('I', not ok, '%s config %s' % (name, c))
    for s in SAMPLES:
        if 'NTFMEM' not in open(os.path.join(d, s + '.txt')).read():
            flag('I', True, '%s %s: no NTFMEM line' % (name, s)); continue
        flag('I', a[s].get('nettyMax') != str(LIMIT) or a[s].get('allocator') != 'PooledByteBufAllocator', '%s %s limit/allocator %s %s' % (name, s, a[s].get('nettyMax'), a[s].get('allocator')))
        flag('I', num(a[s]['memory.events.max']) > 0 or num(a[s]['memory.events.oom_kill']) > 0, '%s %s memory.events max/oom_kill > 0' % (name, s))
    flag('I', abs(a['d']('nettyUsed', 'D0')) > 16 * MiB or abs(a['d']('memory.current', 'D0')) > 256 * MiB,
         '%s drift D0 O1 %d O4 %d' % (name, a['d']('nettyUsed', 'D0'), a['d']('memory.current', 'D0')))
    hold = [l for l in a['client'] if l.startswith('holding')]
    conn_err = sum(l.startswith('connect ') for l in a['client'])
    held_n = int(hold[0].split()[1]) if hold else -1
    a['held_n'], a['conn_err'] = held_n, conn_err
    if name == 'CTRL':
        nresp = sum(l.startswith('ctrlresp ') and 'opcode=6' in l for l in a['client'])
        flag('I', held_n != k or nresp != k, 'CTRL holding %d, SUPPORTED %d' % (held_n, nresp))
    else:
        flag('I', not hold and conn_err == 0, '%s no holding line and no refusal evidence' % name)

ctrl = data['CTRL']
held = [(n, data[n]) for n, k in arms if n != 'CTRL']
for name, a in held:
    k = a['k']
    alive = [l for l in a['client'] if l.startswith('alive')]
    m = re.match(r'alive (\d+) closed (\d+) unexpected (\d+)', alive[0]) if alive else None
    nsup = sum(l.startswith('resp ') and 'opcode=6' in l for l in a['client'])
    nresp = sum(l.startswith('resp ') for l in a['client'])
    cn = a['counts']
    oom = sum(num(v) for kk, v in cn.items() if 'OutOfDirectMemoryError' in kk or 'OutOfMemoryError' in kk)
    flag('R2', a['conn_err'] > 0 or a['held_n'] != k or not m or int(m.group(1)) != k or int(m.group(2)) > 0
         or num(cn['NTFDISCARD']) > 0 or num(cn['NTFFAIL']) > 0 or nsup != k or nresp != k or oom > 0,
         '%s conn_err=%d holding=%d alive=%s SUPPORTED=%d/%d DISCARD=%s FAIL=%s oom=%d' % (name, a['conn_err'], a['held_n'], alive, nsup, nresp, cn['NTFDISCARD'], cn['NTFFAIL'], oom))
    a['sup'] = nsup
    for s in HOLD:
        flag('R3', num(a[s]['inflight']) > 0, '%s %s inflight %s' % (name, s, a[s]['inflight']))
        h16 = num(a[s]['held16']); d2 = a['d']('poolDirect', s); d1 = a['d']('nettyUsed', s); d4 = a['d']('memory.current', s)
        flag('R1', h16 < 0.5 * k or d2 < 0.5 * k * U, '%s %s held16 %d dO2 %d' % (name, s, h16, d2))
        flag('P1a', h16 != k, '%s %s held16 %d != %d' % (name, s, h16, k))
        flag('P2', not (k * U <= d2 <= (k + 64) * U) or abs(d1 - d2) > 64 * MiB or d4 - ctrl['d']('memory.current', s) < 0.9 * k * U,
             '%s %s dO2 %d (band %d..%d) dO1-dO2 %d dO4-ctrl %d (min %d)' % (name, s, d2, k * U, (k + 64) * U, d1 - d2, d4 - ctrl['d']('memory.current', s), 0.9 * k * U))
    for s in ['base', 'D0']:
        flag('P1a', num(a[s]['held16']) != 0, '%s %s held16 %s' % (name, s, a[s]['held16']))
    flag('P5', num(a['R']['held16']) != 0 or a['d']('poolDirect', 'R') > 64 * U, '%s R held16 %s dO2 %d' % (name, a['R']['held16'], a['d']('poolDirect', 'R')))
for s in HOLD + ['base', 'D0']:
    flag('P1a', num(ctrl[s]['held16']) != 0, 'CTRL %s held16 %s' % (s, ctrl[s]['held16']))
for s in HOLD:
    flag('P3', ctrl['d']('poolDirect', s) > 64 * U or ctrl['d']('memory.current', s) > 512 * MiB,
         'CTRL %s dO2 %d dO4 %d' % (s, ctrl['d']('poolDirect', s), ctrl['d']('memory.current', s)))
# O4 slopes between consecutive held arms
hk = [(n, a['k'], a) for n, a in held]
for s in HOLD:
    for (n1, k1, a1), (n2, k2, a2) in zip(hk, hk[1:]):
        sl = (a2['d']('memory.current', s) - a1['d']('memory.current', s)) / (k2 - k1)
        print('slope O4 %s %s->%s: %.0f B/conn = %.3f U' % (s, n1, n2, sl, sl / U))
        flag('R1', sl < 0.5 * U, 'O4 slope %s %s->%s %.3f U' % (s, n1, n2, sl / U))
        flag('P1b', not (0.9 * U <= sl <= 1.25 * U), 'O4 slope %s %s->%s %.3f U' % (s, n1, n2, sl / U))
        sl1 = (a2['d']('nettyUsed', s) - a1['d']('nettyUsed', s)) / (k2 - k1)
        print('slope O1 %s %s->%s: %.0f B/conn = %.3f U (context)' % (s, n1, n2, sl1, sl1 / U))

print('\nreadings (deltas vs base; MiB):')
for name, k in arms:
    a = data[name]
    for s in ['D0'] + HOLD + ['R']:
        print('  %-5s %-3s O1 %+9.1f O2 %+9.1f O3(NMT Other) %+9.1f O4 %+9.1f held16 %4s chunks %4s inflight %s clients %s' % (
            name, s, a['d']('nettyUsed', s) / MiB, a['d']('poolDirect', s) / MiB, num(a[s]['nmt_other_delta_kib']) / 1024,
            a['d']('memory.current', s) / MiB, a[s]['held16'], a[s]['chunks'], a[s]['inflight'], a[s]['clients']))
print('\nflags:'); [print('  ' + n) for n in notes]
print('  set: %s' % sorted(r for r, v in flags.items() if v))
order = [('I', 'Invalid'), ('R1', 'Refuted (not held)'), ('R2', 'Refuted (refused below the limit)'), ('R3', 'Refuted (counted)'),
         ('P3', 'N1 Not confirmed (control moved)'), ('P1a', 'N2 Not confirmed (size per connection)'), ('P1b', 'N2 Not confirmed (size per connection)'),
         ('P2', 'N2 Not confirmed (size per connection)'), ('P5', 'N3 Not confirmed (release)')]
for key, verdict in order:
    if flags.get(key):
        print('\nROW %s' % verdict); sys.exit(0)
print('\nROW C Confirmed (P1-P5 hold)')
