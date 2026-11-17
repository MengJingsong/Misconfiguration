#!/usr/bin/env python3
"""Readings and conditions (design R5-R7) of the recheck run. usage: analyze.py <out-dir> <run1|shake>
Reads only the raw files run.sh wrote: summary-raw.txt (RESULT/SNAP/HISTO/... lines as logged), snaps/*.tsv, histo/*.txt,
L1-gc.log*, L2-gc.log*. Prints the readings, each condition as PASS/FAIL, and the matched R7 row."""
import glob, os, re, statistics as st, sys

L, scale = sys.argv[1], sys.argv[2]
div = 1 if scale == 'run1' else 100
M = {'Z': 1, 'S5': 100000 // div, 'S6': 1000000 // div, 'S7': 10000000 // div, 'G': 1000000 // div}
raw = open(os.path.join(L, 'summary-raw.txt')).read().splitlines()
checks = []


def chk(name, ok, detail):
    checks.append((name, bool(ok)))
    print('%-4s %-34s %s' % ('PASS' if ok else 'FAIL', name, detail))


def snapfile(name):
    d = {'t': {}}
    for line in open(os.path.join(L, 'snaps', name + '.tsv')):
        f = line.rstrip('\n').split('\t')
        if f[0] == 't':
            d['t'][int(f[1])] = (int(f[2]), f[3])
        elif f[0] == 'gc':
            d.setdefault('gc', {})[f[1]] = (int(f[2]), int(f[3]))
        else:
            d[f[0]] = int(f[1])
    return d


def alloc(a, b):
    A, B = snapfile(a), snapfile(b)
    delta = new = 0
    for tid, (v, _) in B['t'].items():
        if tid in A['t']:
            delta += v - A['t'][tid][0]
        else:
            new += v
    lost = [A['t'][t][1] for t in A['t'] if t not in B['t']]
    gcs = sum(B['gc'][g][0] - A['gc'][g][0] for g in B['gc'])
    return delta + new, (B['epoch_ms'] - A['epoch_ms']) / 1000.0, lost, gcs, A['uptime_ms'], B['uptime_ms']


def lines(prefix):
    return [l for l in raw if l.startswith(prefix)]


def histo(name):
    p = os.path.join(L, 'histo', name + '.txt')
    if not os.path.exists(p):
        return None
    tot = cells = 0; top = []
    for line in open(p):
        m = re.match(r'\s*(\d+):\s+(\d+)\s+(\d+)\s+(\S+)', line)
        if m:
            n, b, cls = int(m.group(2)), int(m.group(3)), m.group(4)
            if re.match(r'org\.apache\.cassandra\.db\.rows\.[A-Za-z]*Cell$', cls):
                cells += n
            if len(top) < 8:
                top.append('%s:%d/%d' % (cls.split('.')[-1], n, b))
        m = re.match(r'Total\s+(\d+)\s+(\d+)', line)
        if m:
            tot = int(m.group(2))
    return tot, cells, top


# gc.log young pauses: uptime and heap after
gcev = {}
for life in ('L1', 'L2'):
    ev = []
    for f in sorted(glob.glob(os.path.join(L, life + '-gc.log*'))):
        for line in open(f, errors='replace'):
            if 'Pause Young' in line or 'Pause Full' in line:
                u = re.search(r'\[(\d+\.\d+)s\]', line); h = re.search(r'(\d+)M->(\d+)M\((\d+)M\)', line)
                if u and h:
                    ev.append((float(u.group(1)) * 1000, int(h.group(1)), int(h.group(2)), 'Full' in line))
    gcev[life] = ev

res = {}
print('== Readings')
for arm in ('Z', 'S5', 'S6', 'S7', 'B', 'G'):
    life = 'L2' if arm == 'G' else 'L1'
    try:
        idle_b, idle_s, idle_lost, _, _, _ = alloc(arm + '-idle0', arm + '-idle1')
    except FileNotFoundError:
        print('arm %s: no snapshots' % arm); continue
    rate = idle_b / idle_s
    nets, reads = [], []
    for r in (1, 2, 3):
        b, s, lost, gcs, u0, u1 = alloc('%s-r%d-a' % (arm, r), '%s-r%d-b' % (arm, r))
        net = b - rate * s
        ha = [e[2] for e in gcev[life] if u0 <= e[0] <= u1 and not e[3]]
        nets.append(net)
        reads.append('r%d alloc=%d net=%d dur=%.2fs gcs=%d lost_threads=%s young_heap_after_max_MB=%s'
                     % (r, b, net, s, gcs, len(lost), max(ha) if ha else '-'))
    rl = [l for l in lines('RESULT read table=') if ' table=%s ' % {'Z': 'z', 'S5': 's5', 'S6': 's6', 'S7': 's7', 'B': 'b6', 'G': 'g6'}[arm] in l][:3]  # the 3 alloc reads (the 4th, if any, is P)
    hb, hp = histo(arm + '-base'), histo(arm + '-pause')
    held = (hp[0] - hb[0]) if (hb and hp) else None
    dcell = (hp[1] - hb[1]) if (hb and hp) else None
    res[arm] = dict(net=st.median(nets), nets=nets, held=held, dcell=dcell, rate=rate, reads=rl,
                    pause=any(l.startswith('PAUSE %s reached' % arm) for l in raw))
    print('arm %s M=%s idle_rate=%.0f B/s (idle lost threads %d)' % (arm, M.get(arm, '-'), rate, len(idle_lost)))
    for x in reads:
        print('   ' + x)
    for x in rl:
        print('   ' + x[:220])
    print('   held: base=%s pause=%s held=%s cell_delta=%s pause_reached=%s' % (hb and hb[:2], hp and hp[:2], held, dcell, res[arm]['pause']))
    if hp:
        print('   pause top classes: ' + ' '.join(hp[2]))
    print('   ' + ' | '.join(l for l in lines('HELDREAD %s ' % arm)))

print('== Sizes')
for l in lines('SIZE '):
    print('   ' + l)
du = {}
for l in lines('SIZE '):
    m = re.match(r'SIZE (\S+) .*du_bytes=(\d+)', l)
    if m:
        du[m.group(1)] = int(m.group(2))

Z = res.get('Z')
a, h = {}, {}
for arm in ('S5', 'S6', 'S7', 'G'):
    if arm in res and Z:
        a[arm] = (res[arm]['net'] - Z['net']) / M[arm]
        if res[arm]['held'] is not None and Z['held'] is not None:
            h[arm] = (res[arm]['held'] - Z['held']) / M[arm]
print('== Per item (minus Z): a = %s' % {k: round(v, 1) for k, v in a.items()})
print('                       h = %s' % {k: round(v, 1) for k, v in h.items()})
for arm, t in (('S5', 's5'), ('S6', 's6'), ('S7', 's7'), ('G', 'g6')):
    if t in du:
        print('   disk %s: %d B, %.2f B/item; serialized 8 B/item; h/serialized = %s' % (t, du[t], du[t] / M[arm], round(h[arm] / 8, 1) if arm in h else '-'))

print('== Conditions')
# validity
loads = lines('RESULT load ') + lines('RESULT loadblob ')
chk('V load all accepted', loads and all(' rejected=0 ' in l or 'outcome=accepted' in l for l in loads), '%d load lines' % len(loads))
sst = [l for l in lines('SIZE ') if 'SSTable count: 1;' not in l]
chk('V one sstable per table', not sst and lines('SIZE '), '%d tables not at 1' % len(sst))
chk('V pause reached (Z,S5,S6,S7,B,G)', all(res.get(x, {}).get('pause') for x in ('Z', 'S5', 'S6', 'S7', 'B', 'G')), '')
mem = lines('MEMORY ')
chk('V no oom_kill', mem and all(l.endswith('oom_kill_last=0') for l in mem), ' ; '.join(mem))
chk('V no daemon left', lines('DAEMONS-LEFT 0'), '')
# P1
ok = True; det = []
for arm in ('S5', 'S6', 'S7'):
    for l in res.get(arm, {}).get('reads', []):
        m = re.search(r'accepted count=(\d+) value_bytes=(\d+)', l)
        good = bool(m) and int(m.group(1)) == M[arm] and int(m.group(2)) == 4 + 8 * M[arm]
        ok &= good
    det.append('%s:%d reads' % (arm, len(res.get(arm, {}).get('reads', []))))
chk('P1 reads accepted, count=M, 4+8M B', ok, ' '.join(det))
chk('P2 a6 in [200,2000]', 'S6' in a and 200 <= a['S6'] <= 2000, a.get('S6'))
chk('P2 a7 in [200,2000]', 'S7' in a and 200 <= a['S7'] <= 2000, a.get('S7'))
chk('P2 a7/a6 in [0.75,1.33]', 'S7' in a and 'S6' in a and 0.75 <= a['S7'] / a['S6'] <= 1.33, a.get('S7', 0) / a['S6'] if a.get('S6') else '-')
chk('P2 a5/a6 in [0.5,2]', 'S5' in a and 'S6' in a and 0.5 <= a['S5'] / a['S6'] <= 2, a.get('S5', 0) / a['S6'] if a.get('S6') else '-')
for arm in ('S5', 'S6', 'S7'):
    chk('P3 h%s in [100,400]' % arm, arm in h and 100 <= h[arm] <= 400, h.get(arm))
chk('P3 h7/h6 in [0.75,1.33]', 'S7' in h and 'S6' in h and 0.75 <= h['S7'] / h['S6'] <= 1.33, h.get('S7', 0) / h['S6'] if h.get('S6') else '-')
for arm in ('S5', 'S6', 'S7'):
    dc = res.get(arm, {}).get('dcell')
    chk('P3 cell delta %s in [0.9M,2.1M]' % arm, dc is not None and 0.9 * M[arm] <= dc <= 2.1 * M[arm], dc)
for arm, t in (('S5', 's5'), ('S6', 's6'), ('S7', 's7')):
    print('INFO P4 %s disk/item=%.2f h/8=%s (recorded relation: disk<=20, h>=80)' % (arm, du.get(t, 0) / M[arm], round(h[arm] / 8, 1) if arm in h else '-'))
if 'B' in res and 'S6' in res:
    ba, sa = res['B']['net'] - Z['net'], res['S6']['net'] - Z['net']
    chk('P5 blob alloc <= 0.5 x S6', ba <= 0.5 * sa, '%d vs %d (%.3f)' % (ba, sa, ba / sa))
    if res['B']['held'] is not None and Z['held'] is not None and res['S6']['held'] is not None:  # shakedown fix S4: guard a missing held reading
        bh, sh = res['B']['held'] - Z['held'], res['S6']['held'] - Z['held']
        chk('P5 blob held <= 0.5 x S6', bh <= 0.5 * sh, '%d vs %d (%.3f)' % (bh, sh, bh / sh if sh else 0))
# P6
rb = lines('READTHRESHOLDS-P ')
chk('P6 read-back true/threshold', rb and 'enabled=true' in rb[0], rb and rb[0])
pr = {t: [l for l in lines('RESULT read table=%s ' % t)] for t in ('s5', 's6', 's7')}
# P read = the 4th RESULT read line of each table (3 alloc reads precede it; the held read is logged as HELDREAD)
pres = {t: (pr[t][3] if len(pr[t]) > 3 else '') for t in pr}
chk('P6 S5 accepted', 'accepted' in pres['s5'], pres['s5'][:160])
chk('P6 S6 rejected', ' error ' in pres['s6'], pres['s6'][:200])
chk('P6 S7 rejected', ' error ' in pres['s7'], pres['s7'][:200])
pp = {re.match(r'PPAUSE (\S+)', l).group(1): int(l.split('=')[-1]) for l in lines('PPAUSE ')}
chk('P6 no pause for S6,S7', pp.get('s6') == 0 and pp.get('s7') == 0, pp)
try:
    p7, s, _, _, _, _ = alloc('P-s7-a', 'P-s7-b')
    p7net = p7 - res['S7']['rate'] * s
    chk('P6 alloc(P S7) < 0.8 x S7 default', p7net < 0.8 * res['S7']['net'], '%d vs %d (%.3f)' % (p7net, res['S7']['net'], p7net / res['S7']['net']))
    print('INFO P6 rejected S7 alloc_net/M = %.1f B (expected > 50)' % (p7net / M['S7']))
    for t, arm in (('s5', 'S5'), ('s6', 'S6')):
        x, s, _, _, _, _ = alloc('P-%s-a' % t, 'P-%s-b' % t)
        print('INFO P6 %s alloc_net=%d (%.1f B/item)' % (t, x - res[arm]['rate'] * s, (x - res[arm]['rate'] * s) / M[arm]))
except FileNotFoundError:
    chk('P6 alloc snapshots', False, 'missing')
for l in lines('PMETRIC '):
    m = re.match(r'PMETRIC (\S+) RESULT get .*?LocalReadSize Max = (\d+)', l)  # shakedown fix S5: first '= N' is the Max
    if m:
        t = m.group(1); arm = {'s5': 'S5', 's6': 'S6', 's7': 'S7'}[t]
        print('INFO P6 LocalReadSize Max %s = %s B -> %.1f B/item (expected [100,400])' % (t, m.group(2), int(m.group(2)) / M[arm]))
# P7
gc_ = lines('RESULT guardcheck ')
chk('P7 T+1 write by app rejected', gc_ and 'rejected' in gc_[0] and 'items_per_collection violated' in gc_[0], gc_ and gc_[0][:220])
gl = [l for l in lines('RESULT load table=g6 ')]
chk('P7 200/200 appends accepted', gl and ' accepted=200 rejected=0 ' in gl[0], gl and gl[0][:160])
ok = bool(res.get('G', {}).get('reads')) and all(re.search(r'accepted count=%d ' % M['G'], l) for l in res['G']['reads'])
chk('P7 G reads accepted, count', ok, '')
chk('P7 aG/a6 in [0.75,1.33]', 'G' in a and 'S6' in a and 0.75 <= a['G'] / a['S6'] <= 1.33, a.get('G', 0) / a['S6'] if a.get('S6') else '-')
chk('P7 hG/h6 in [0.75,1.33]', 'G' in h and 'S6' in h and 0.75 <= h['G'] / h['S6'] <= 1.33, h.get('G', 0) / h['S6'] if h.get('S6') else '-')

print('== Summary')
f = [n for n, ok in checks if not ok]
print('checks=%d pass=%d fail=%d' % (len(checks), len(checks) - len(f), len(f)))
for n in f:
    print('FAILED: ' + n)
