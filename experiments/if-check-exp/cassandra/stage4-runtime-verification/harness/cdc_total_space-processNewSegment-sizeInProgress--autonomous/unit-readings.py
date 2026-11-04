#!/usr/bin/env python3
"""Reads the unit-tier cell folders (readings.txt, cdc-verdict.txt) and prints one table row per cell.
usage: unit-readings.py <unit log dir>
Pure reading: it matches nothing to the case's B2g rows; the AI does that in the results file."""
import os, re, sys
MIB = 1 << 20
def kv(line):
    return dict(re.findall(r'(\w+)=("[^"]*"|\S+)', line))
def cell(d):
    r = {}
    rows = []
    for line in open(os.path.join(d, 'readings.txt')):
        if ' config ' in line: r['config'] = kv(line)
        elif ' idle ' in line: r['idle'] = kv(line)
        elif ' writesDone ' in line: r['wd'] = kv(line)
        elif ' final ' in line and 'afterUpdate' not in line: r['final'] = kv(line)
        elif ' afterUpdateCDCTotalSize ' in line: r['upd'] = kv(line)
        elif ' sampler ' in line: r['sam'] = kv(line)
        elif ' row i=' in line: rows.append(kv(line))
        elif ' boundary ' in line: r.setdefault('bnd', []).append(kv(line))
        elif ' listing ' in line: r['listing'] = line
        elif ' RESULT ' in line: r['res'] = kv(line)
    r['rows'] = rows
    tr = os.path.join(d, 'cdc-verdict.txt')
    pre = post = forb = dele = rej = 0
    zero_after_free = 0
    last_dele = None
    freed = []
    if os.path.exists(tr):
        for line in open(tr):
            if line.startswith('pre '): pre += 1
            elif line.startswith('post '):
                post += 1
                if 'state=FORBIDDEN' in line: forb += 1
                if last_dele is not None:
                    sip = int(re.search(r'sip=(\d+)', line).group(1))
                    freed.append((last_dele, sip))
                    last_dele = None
            elif line.startswith('deleteOld'):
                dele += 1
                last_dele = kv(line)
            elif line.startswith('reject '): rej += 1
    r['trace'] = dict(pre=pre, forbidden=forb, deleteOld=dele, reject=rej, freed=freed)
    return r
def main():
    base = sys.argv[1]
    print('| cell | n MiB | mode | enabled/table | attempted MiB | accepted rows | rejected | final du MiB | final du - n (segments) | peak du MiB (5 ms) | peak - n (segments) | peak links | final links | tracker final MiB | tracker - du (B) | segments created | forbidden | deleteOld calls | min tracker after a deleteOld (MiB) | max rows tick du MiB |')
    print('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
    for name in sorted(os.listdir(base)):
        d = os.path.join(base, name)
        if not os.path.exists(os.path.join(d, 'readings.txt')): continue
        r = cell(d)
        if 'final' not in r or 'sam' not in r:
            print('| %s | incomplete (no final/sampler line) |' % name); continue
        c, wd, fin, sam, upd, t = r['config'], r['wd'], r['final'], r['sam'], r.get('upd', {}), r['trace']
        n = int(c['totalSpaceMiB'])
        S = 32
        du = int(fin['duBytes']) / MIB
        peak = int(sam['peakBytes']) / MIB
        tracker = fin.get('tracker', 'na')
        trk = '' if tracker == 'na' else '%.2f' % (int(tracker) / MIB)
        diff = '' if tracker == 'na' else str(int(tracker) - int(fin['duBytes']))
        mn = min([s for _, s in t['freed']], default=None)
        rowmax = max([int(x['duBytes']) for x in r['rows']] or [0]) / MIB
        print('| %s | %d | %s | %s/%s | %s | %s | %s | %.1f | %.2f | %.1f | %.2f | %s | %s | %s | %s | %d | %d | %d | %s | %.1f |' % (
            name, n, c['mode'], c['cdcEnabled'], c['table'], c['volumeMiB'], wd['accepted'], wd['rejected'], du, (du - n) / S, peak, (peak - n) / S,
            sam['peakLinks'], fin['links'], trk, diff, t['pre'], t['forbidden'], t['deleteOld'], '' if mn is None else '%.1f' % (mn / MIB), rowmax))
if __name__ == '__main__':
    main()
