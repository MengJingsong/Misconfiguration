#!/usr/bin/env python3
"""Reads the STAGE4 lines of TombstoneThresholdProbeTest and prints EXPECTED lines for B2f (P1-P4) and the B2d instrument checks."""
import re, struct, sys
cells, bytes_, ctrl, info = [], [], [], []
def kv(l):
    return dict(re.findall(r'(\w+)=(\S+)', l))
for l in open(sys.argv[1]):
    if not l.startswith('STAGE4 '):
        continue
    w = l.split()[1]
    d = kv(l)
    {'cell': cells, 'bytes': bytes_, 'control': ctrl, 'info': info}.get(w, []).append(d)
def f32(x):  # the float constant promoted to double
    return struct.unpack('f', struct.pack('f', float(x)))[0]
ok = {}
def exp(key, desc, cond):
    ok[key] = bool(cond)
    print(f'EXPECTED: {key} {desc} — {"yes" if cond else "NO"}')
bad = []
# instrument checks
exp('I1', 'strategy threshold equals X after every ALTER (%d cells)' % len(cells), all(abs(float(c['thr']) - f32(c['X'])) < 1e-6 for c in cells))
r05 = [float(i['r']) for i in info if i['f'] == '0.5']
exp('I2', 'r within f +/- 0.1 for every table (r: %s)' % ' '.join(f"{i['f']}:{float(i['r']):.3f}" for i in info), all(abs(float(i['r']) - float(i['f'])) <= 0.1 for i in info))
o0 = [c for c in cells if c['gate'] == 'open' and c['X'] == '0.0']
exp('I3', 'known answer: X=0.0, gates open, worth true for every f', len(o0) == 4 and all(c['worth'] == 'true' for c in o0))
# P1
op = [c for c in cells if c['gate'] == 'open']
bad = [c for c in op if (c['worth'] == 'true') != (float(c['r']) > f32(c['X']))]
exp('P1', 'open gates: worth == (r > (double)(float)X) in all %d cells; mismatches %d' % (len(op), len(bad)), not bad)
bad = [c for c in op if c['X'] == '1.5' and c['worth'] == 'true']
exp('P1b', 'X=1.5 false for every f', not bad)
bad = [c for c in op if (c['task'] == 'true') != (c['worth'] == 'true')]
exp('P1c', 'getNextBackgroundTask returns a task exactly when worth is true (single sstable, no bucket); mismatches %d' % len(bad), not bad)
# P2
iv = [c for c in cells if c['gate'] == 'interval']
exp('P2a', 'interval 86400: worth false in all %d cells (r > X in %d of them)' % (len(iv), sum(float(c['r']) > f32(c['X']) for c in iv)), iv and all(c['worth'] == 'false' for c in iv) and any(float(c['r']) > f32(c['X']) for c in iv))
ov = [c for c in cells if c['gate'] == 'overlap']
ovn = [c for c in ov if c['X'] != '0.0']; ov0 = [c for c in ov if c['X'] == '0.0']
exp('P2b', 'overlap + unchecked false: worth false for X>0 (%d cells, r > X in %d) and true at X=0.0 (%d cell)' % (len(ovn), sum(float(c['r']) > f32(c['X']) for c in ovn), len(ov0)),
    ovn and all(c['worth'] == 'false' for c in ovn) and any(float(c['r']) > f32(c['X']) for c in ovn) and len(ov0) == 1 and ov0[0]['worth'] == 'true')
no = [c for c in cells if c['gate'] == 'nooverlap']
exp('P2c', 'unchecked false, no overlap: worth == (r > X) in all %d cells' % len(no), no and all((c['worth'] == 'true') == (float(c['r']) > f32(c['X'])) for c in no))
npg = [c for c in cells if c['gate'] == 'neverpurge']
exp('P2d', 'never-purge: worth false in all %d cells' % len(npg), npg and all(c['worth'] == 'false' for c in npg))
# P3
for b in bytes_:
    b['ratio'] = int(b['after']) / int(b['before'])
bad = [b for b in bytes_ if (b['task'] == 'true') and abs(b['ratio'] - (1 - float(b['f']))) > 0.08]
exp('P3a', 'bytes after an executed task = (1-f) of before +/- 0.08: ' + ' '.join(f"f{b['f']}/X{b['X']}:{b['ratio']:.3f}" for b in bytes_ if b['task'] == 'true'), not bad and any(b['task'] == 'true' for b in bytes_))
bad = [b for b in bytes_ if b['task'] == 'false' and b['before'] != b['after']]
nt = [b for b in bytes_ if b['task'] == 'false']
exp('P3b', 'no task -> bytes unchanged (%d cells, e.g. %s)' % (len(nt), ' '.join(f"f{b['f']}/X{b['X']}" for b in nt)), nt and not bad)
bad = [b for b in bytes_ if (b['task'] == 'true') != (float(b['r']) > f32(b['X']))]
exp('P3c', 'task iff r > X in the byte cells; mismatches %d' % len(bad), not bad)
# P4
exp('P4', 'forced compaction at X=1.5 gives (1-f) +/- 0.08: ' + ' '.join(f"f{c['f']}:{int(c['after'])/int(c['before']):.3f}" for c in ctrl),
    len(ctrl) == 4 and all(abs(int(c['after']) / int(c['before']) - (1 - float(c['f']))) <= 0.08 for c in ctrl) and all(c['worth'] == 'false' for c in ctrl))
print('SUMMARY: ' + ' '.join(f'{k}={"ok" if v else "NO"}' for k, v in ok.items()))
