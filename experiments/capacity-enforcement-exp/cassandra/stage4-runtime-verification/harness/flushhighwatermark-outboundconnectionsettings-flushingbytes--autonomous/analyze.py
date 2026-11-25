#!/usr/bin/env python3
"""o125 analysis: unit FHWM rows (B2f/B2g + S4-A2) and cluster samples (B3e step 10, B3f/B3g + S4-A3)."""
import sys, os, re, glob, csv, datetime
MiB = 1 << 20
def unit(logdir):
    rows = []
    for r in (1, 2, 3):
        seen = set()
        for f in (f'{logdir}/unit-r{r}.rows',):  # defect fix 1: rejoined rows
            if not os.path.exists(f): continue
            for l in open(f, errors='replace'):
                m = re.search(r'FHWM,(\d+),(\d+),(\d+),(\d+),(\d+),(-?\d+),(\d+),(-?\d+),(-?\d+),(-?\d+),(-?\d+)', l)
                if m and m.group(1) not in seen:
                    seen.add(m.group(1)); rows.append((r,) + tuple(int(x) for x in m.groups()))
    print('UNIT rep,H,L,s,N,W,flushingBytes,isWritable,pendingBytes,poolDelta,received,flushingAfterResume,band_ok,ceil(H/B)*B')
    for row in rows:
        r, H, L, s, N, W, fb, w, pend, pool, rec, after = row
        m = 65515 // s; B = m * s
        if H < W:
            ok = (H <= fb < H + 65515) and w == 0
            exp = -(-H // B) * B
        else:
            ok = (fb >= W - 32 * 1024) and w == 1
            exp = W
        print('UNIT', ','.join(str(x) for x in row), 'OK' if ok else 'MISS', exp, sep=',')
    return rows
def epoch_of_log(line):
    m = re.search(r'(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),(\d{3})', line)
    if not m: return None
    t = datetime.datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)
    return int(t.timestamp() * 1000) + int(m.group(2))
def cluster(rundir):
    print('CLUSTER run,knob,stall,props,base_net,dNet_max,dDirect_max,pend_max,drops_win_end,down_ms_after_stop,win_samples,returned_within_30s,nmt_other_committed')
    for d in sorted(glob.glob(rundir + '/*/')):
        R = os.path.basename(d.rstrip('/'))
        try:
            knob, stall = open(d + 'knob.txt').read().split()
            stop = int(open(d + 'stop.ts').read()); cont = int(open(d + 'cont.ts').read())
            S = [r for r in csv.DictReader(open(d + 'samples.csv'))]
        except Exception as e:
            print('CLUSTER', R, 'incomplete', e); continue
        S = [{k: int(v) for k, v in r.items()} for r in S if all(v.lstrip('-').isdigit() for v in r.values())]
        props = open(d + 'props.txt').read().strip().replace('\n', ' ') if os.path.exists(d + 'props.txt') else ''
        down = None
        if os.path.exists(d + 'systemA.log'):
            for l in open(d + 'systemA.log', errors='replace'):
                if '127.0.0.2' in l and 'is now DOWN' in l:
                    t = epoch_of_log(l)
                    if t and t >= stop: down = t; break
        base = [r for r in S if stop - 10000 <= r['ms'] < stop]
        bn = sum(r['netPoolUsed'] for r in base) / max(1, len(base)); bd = sum(r['directUsed'] for r in base) / max(1, len(base))
        hi = stop + 20000 if down is None else min(stop + 20000, down)
        win = [r for r in S if stop + 5000 <= r['ms'] <= hi]
        dn = max((r['netPoolUsed'] - bn for r in win), default=float('nan'))
        dd = max((r['directUsed'] - bd for r in win), default=float('nan'))
        pm = max((r['pendingBytes'] for r in win), default=float('nan'))
        drops = win[-1]['overloadDrops'] if win else None
        after = [r for r in S if cont <= r['ms'] <= cont + 30000]
        ret = any(r['netPoolUsed'] - bn <= MiB and r['pendingBytes'] <= MiB for r in after)
        other = ''
        if os.path.exists(d + 'nmt.txt'):
            m = re.search(r'-\s+Other \(reserved=(\d+)KB, committed=(\d+)KB\)', open(d + 'nmt.txt').read())
            if m: other = m.group(2) + 'KB'
        print('CLUSTER', R, knob, stall, '"' + props + '"', int(bn), '%.3fMiB' % (dn / MiB), '%.3fMiB' % (dd / MiB), '%.3fMiB' % (pm / MiB), drops,
              (down - stop) if down else 'none', len(win), ret, other, sep=',')
if __name__ == '__main__':
    base = sys.argv[1]
    if os.path.isdir(base + '/logs'): unit(base + '/logs')
    if os.path.isdir(base + '/runs'): cluster(base + '/runs')
