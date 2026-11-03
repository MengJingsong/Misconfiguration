#!/usr/bin/env python3
"""Unit-tier readings table and row matching (B2f/B2g as amended 2026-10-24) from the raw <jvm>.stage4.out files.
usage: unit-readings.py <unit log dir>"""
import re, sys, os
d = sys.argv[1]; MIB = 1 << 20
def result(lab):
    p = os.path.join(d, lab + '.stage4.out')
    if not os.path.exists(p): return None
    rs = [l for l in open(p) if ' RESULT ' in l]
    return rs
def kv(line):
    line = re.sub(r'firstReject=\[([^\]]*)\]', lambda m: 'firstReject=' + m.group(1).replace(' ', ',').replace('=', ':'), line)
    return dict(x.split('=', 1) for x in line.split() if '=' in x)
rows = []; verdicts = []
print('| JVM | s MiB | mode | rows accepted | accepted MiB | rejected | first rejection: links / link bytes / counter | max links | max link bytes | max idx bytes | links deleted | B2f window | matched B2g row |')
print('|---|---|---|---|---|---|---|---|---|---|---|---|---|')
for lab in ['block-s8', 'block-s16', 'block-s32', 'nonblock-s8', 'nonblock-s16', 'nonblock-s32', 'ctl-plain', 'ctl-1024']:
    rs = result(lab)
    if not rs: print('| %s | missing |' % lab); verdicts.append((lab, 'missing')); continue
    r = kv(rs[-1]); s = int(r['s']); blk = r['blocking'] == 'true'
    acc = int(r['acceptedBytes']); rej = int(r['rejected']); mx = int(r['maxLinkBytes']); dele = int(r['linksDeleted'])
    fr = r['firstReject']
    frd = dict(x.split(':', 1) for x in fr.split(',')) if fr != 'none' else {}
    S = MIB; A = s * MIB
    if lab.startswith('block'):
        win = '[%d, %d] MiB accepted; max ≤ %d MiB' % (s - 4, s + 1, s + 1)
        ok_acc = rej >= 1 and (A - 4 * S) <= acc <= (A + S)
        if rej == 0 and mx <= A + 2 * S: row = '6 rejection path not reached (Not confirmed)'
        elif mx > A + 2 * S: row = '2 cap not binding (Refuted)'
        elif mx > A + S: row = '4 overshoot > 1 segment (Not confirmed)'
        elif rej >= 1 and acc < A - 4 * S: row = '5 cap below knob (Not confirmed)'
        elif ok_acc and mx <= A + S: row = '1 claim confirmed'
        else: row = 'no row'
    elif lab.startswith('nonblock'):
        win = 'no exception; max ≤ %d MiB; ≥ 1 link deleted' % (s + 1)
        if rej > 0: row = '7 exception in non-blocking (Refuted)'
        elif mx > A + 2 * S: row = '2 cap not binding (Refuted)'
        elif dele == 0: row = '8 limit not reached (Invalid)'
        elif mx > A + S: row = '4 overshoot > 1 segment (Not confirmed)'
        else: row = '1 claim confirmed'
    elif lab == 'ctl-plain':
        win = 'no exception; ≤ 2 links after recycle'
        ok = rej == 0 and int(r.get('afterRecycleLinks', '99')) <= 2
        row = 'control holds' if ok else '9 control fails (Invalid)'
    else:
        win = 'no exception with 128 MiB'
        ok = rej == 0 and acc >= 128 * MIB
        row = 'control holds' if ok else '9 control fails (Invalid)'
    verdicts.append((lab, row))
    print('| %s | %d | %s | %s | %.2f | %d | %s | %s | %d (%.2f MiB) | %s | %d | %s | %s |' % (
        lab, s, 'blocking' if blk else 'non-blocking', r['accepted'], acc / MIB, rej,
        ('%s / %s / %s' % (frd.get('links'), frd.get('linkBytes'), frd.get('counterInMessage'))) if frd else 'none',
        r['maxLinks'], mx, mx / MIB, r['maxIdxBytes'], dele, win, row))
    if lab == 'ctl-plain': print('|  | ctl-plain after recycle: links %s, link bytes %s |' % (r.get('afterRecycleLinks'), r.get('afterRecycleLinkBytes')))
hs = result('helper') or []
hv = []
for l in hs:
    r = kv(l); hv.append((int(r['totalBytes']), int(r['result']), int(r['expected'])))
    print('\nhelper: totalBytes=%s result=%s expected=%s %s' % (r['totalBytes'], r['result'], r['expected'], 'exact' if r['result'] == r['expected'] else 'DIFFERS (row 3)'))
helper_ok = len(hv) == 2 and all(a == b for _, a, b in hv) and [x[1] for x in hv] == [512, 4096]
scen = [v for l, v in verdicts if not l.startswith('ctl')]; ctl = [v for l, v in verdicts if l.startswith('ctl')]
if not helper_ok or any('Refuted' in v for v in scen): tier = 'Refuted'
elif all(v.startswith('1 ') for v in scen) and all(v == 'control holds' for v in ctl): tier = 'Confirmed (row 1)'
elif any(v.startswith('9') for v in ctl) or any('Invalid' in v for v in scen): tier = 'Invalid'
else: tier = 'Not confirmed'
print('\nhelper exact: %s; scenario rows: %s; controls: %s\nTIER (B2g amended rule): %s' % (helper_ok, scen, ctl, tier))
