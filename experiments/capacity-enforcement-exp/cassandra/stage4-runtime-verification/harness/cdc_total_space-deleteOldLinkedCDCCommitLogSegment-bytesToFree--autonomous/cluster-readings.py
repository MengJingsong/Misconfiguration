#!/usr/bin/env python3
"""Reads the cluster-tier cell folders and prints one table row per cell (observation only; the AI matches B3g rows).
usage: cluster-readings.py <cluster log dir>"""
import os, re, sys, statistics
MIB = 1 << 20
def rows(path):
    out = []
    with open(path) as f:
        next(f)
        for line in f:
            p = line.strip().split(',')
            ms, links, lb, la, ix, ib = (int(x) for x in p[:6])
            out.append((ms, links, lb, ib))
    return out
def phases(path):
    d = {}
    for line in open(path):
        ms, name = line.strip().split(',', 1); d[name] = int(ms)
    return d
def grab(pat, text, default=''):
    m = re.search(pat, text)
    return m.group(1) if m else default
def main():
    base = sys.argv[1]
    hdr = ['cell', 'cap MiB', 'mode', 'rows MiB', 'stress errors', 'W peak MiB (links+idx, 50 ms)', 'peak-cap (seg)', 'W end MiB', 'plateau median last 30 s MiB', 'peak links', 'W end links',
           'du -sb max (2 s) MiB', 'whole-run peak MiB', 'WARN', 'created', 'forbidden', 'deleteOld', 'Freed up', 'release ms', 'switch ms', 'links before->after switch', 'final links', 'final MiB', 'commitlog MiB (end)']
    print('| ' + ' | '.join(hdr) + ' |'); print('|' + '---|' * len(hdr))
    for name in sorted(os.listdir(base)):
        d = os.path.join(base, name)
        if '.attempt' in name or not os.path.exists(os.path.join(d, 'sampler.csv')) or not os.path.exists(os.path.join(d, 'summary.txt')): continue
        s = open(os.path.join(d, 'summary.txt')).read()
        cap = int(grab(r'cap=(\d+)MiB', s, '0')); mode = grab(r'mode=(\w+)', s)
        r = rows(os.path.join(d, 'sampler.csv')); ph = phases(os.path.join(d, 'phases.csv'))
        w0, w1 = ph.get('W_start', 0), ph.get('W_end', 0)
        W = [x for x in r if w0 <= x[0] <= w1 + 3000]
        tot = lambda x: (x[2] + x[3]) / MIB
        peakW = max((tot(x) for x in W), default=0); endW = tot(min(W, key=lambda x: abs(x[0] - w1))) if W else 0
        last = [tot(x) for x in W if x[0] >= w1 - 30000 and x[0] <= w1]
        plateau = statistics.median(last) if last else 0
        peakLinks = max((x[1] for x in W), default=0)
        endLinks = min(W, key=lambda x: abs(x[0] - w1))[1] if W else 0
        whole = max((tot(x) for x in r), default=0)
        du = 0
        if os.path.exists(os.path.join(d, 'du.txt')):
            for line in open(os.path.join(d, 'du.txt')):
                m = re.search(r'cdc_raw=(\d+)', line)
                if m: du = max(du, int(m.group(1)))
        tr = grab(r'traces: (.*)', s)
        errs = grab(r'stress W:.*?Total errors : ([\d,]+)', s).replace(',', '')
        rel = grab(r'release: accepted=\d+ after \d+ probe\(s\), (\d+) ms', s)
        sw = grab(r'switch: first CDC probe accepted=\d+ after \d+ probe\(s\), (\d+) ms', s)
        swl = grab(r'switch: links before=\[(.*?)\] after=\[(.*?)\]', s)
        sw_links = ''
        m = re.search(r'switch: links before=\[(.*?)\] after=\[(.*?)\]', s)
        if m: sw_links = '%d->%d' % (len(m.group(1).split()), len(m.group(2).split()))
        finl = grab(r'final: links=(\d+)', s); fin = re.search(r'final: links=\d+ (\d+),(\d+),(\d+),(\d+),(\d+),(\d+)', s)
        finmib = '' if not fin else '%.1f' % ((int(fin.group(3)) + int(fin.group(6))) / MIB)
        clog = grab(r'commit log dir: (\d+) bytes', s); clog = '' if not clog else '%.0f' % (int(clog) / MIB)
        rowsmib = grab(r'rows=\d+ \(=(\d+) MiB\)', s)
        print('| %s | %d | %s | %s | %s | %.1f | %.2f | %.1f | %.1f | %d | %d | %.1f | %.1f | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            name, cap, mode, rowsmib, errs, peakW, (peakW - cap) / 32, endW, plateau, peakLinks, endLinks, du / MIB, whole,
            grab(r'WARN=(\d+) FreedUp', s), grab(r'created=(\d+)', tr), grab(r'forbidden=(\d+)', tr), grab(r'deleteOld=(\d+)', tr), grab(r'FreedUp=(\d+)', tr),
            rel, sw, sw_links, finl, finmib, clog))
if __name__ == '__main__':
    main()
