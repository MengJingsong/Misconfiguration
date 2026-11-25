#!/usr/bin/env python3
"""Readings summary for dfs.client.socketcache.capacity-putInternal-capacity--autonomous (A3/A4 unit, A7 cluster).
Usage: summarize.py unit <logs/unit>   |   summarize.py cluster <logs/cluster>"""
import re, sys, os, glob
MiB = 1 << 20
KEYS = {'PeerCache$Key': 'Key', 'PeerCache$Value': 'Value', 'LinkedListMultimap$Node': 'Node',
        'NioInetPeer': 'NioInetPeer', 'SocketChannelImpl': 'SocketChannelImpl'}

def kv(line):
    return dict(re.findall(r'(\w+)=(\S+)', line))

def histo_classes(lines):
    d = {}
    for l in lines:
        m = re.search(r'\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
        if not m:
            continue
        cls = m.group(3)
        for k, short in KEYS.items():
            if cls.endswith(k) and (k != 'SocketChannelImpl' or cls == 'sun.nio.ch.SocketChannelImpl') \
                    and (k != 'LinkedListMultimap$Node' or 'LinkedListMultimap$Node' in cls):
                d[short] = (int(m.group(1)), int(m.group(2)))
    return d

def unit(d):
    lines = open(os.path.join(d, 'part-lines.txt')).read().splitlines()
    print('# PART1'); [print(l) for l in lines if l.startswith('PART1 ')]
    p1ok = True
    for l in lines:
        if l.startswith('PART1 '):
            k = kv(l); c = int(k['C']); e = min(2048, c)
            ok = int(k['maxSize']) == e and int(k['size']) == e and int(k['closed']) == 2048 - e
            p1ok &= ok
    print('part1 exact for every C:', p1ok)
    runs = {}
    for l in lines:
        if l.startswith('PART2 '):
            k = kv(l); runs[(int(k['C']), int(k['rep']))] = k
    hist = {}
    for f in glob.glob(os.path.join(d, 'histo', 'histo-C*-r*.txt')):
        m = re.search(r'histo-C(\d+)-r(\d+)', f)
        hist[(int(m.group(1)), int(m.group(2)))] = histo_classes(open(f).read().splitlines())
    print('\n# PART2 per run')
    print('C rep size sizeOpen dH_closed(MiB) dDirectOpen(MiB) dFdOpen dFdClosed xceivers0 xceiversOpen xceivers | Key Value Node NioInetPeer SocketChannelImpl (instances)')
    for (c, r) in sorted(runs, key=lambda x: (x[1], x[0])):
        k = runs[(c, r)]; h = hist.get((c, r), {})
        print(c, r, k['size'], k['sizeOpen'], '%.3f' % ((int(k['heapClosed']) - int(k['heap0'])) / MiB),
              '%.2f' % ((int(k['directOpen']) - int(k['direct0'])) / MiB), int(k['fdOpen']) - int(k['fd0']),
              int(k['fdClosed']) - int(k['fd0']), k['xceivers0'], k['xceiversOpen'], k['xceivers'], '|',
              ' '.join(str(h.get(x, (0, 0))[0]) for x in ['Key', 'Value', 'Node', 'NioInetPeer', 'SocketChannelImpl']))
    print('\n# A3/A4 derived (relative to C=0 of the same rep)')
    ok_all = {'size': True, 'pc': True, 'dh': True, 'bc': True, 'flags': []}
    rows = {}
    for r in (1, 2):
        if (0, r) not in runs:
            continue
        b = runs[(0, r)]; hb = hist.get((0, r), {})
        base = int(b['heapClosed']) - int(b['heap0'])
        for c in (0, 16, 256, 1024):
            if (c, r) not in runs:
                continue
            k = runs[(c, r)]; h = hist.get((c, r), {})
            size = int(k['size'])
            dH = (int(k['heapClosed']) - int(k['heap0'])) - base
            def db(x): return h.get(x, (0, 0))[1] - hb.get(x, (0, 0))[1]
            bcl = db('Key') + db('Value') + db('Node') + 0.5 * (db('NioInetPeer') + db('SocketChannelImpl'))
            per = bcl / size if size else float('nan')
            pc = (int(k['directOpen']) - int(k['direct0'])) >= 64 * MiB and (int(k['fdOpen']) - int(k['fd0'])) >= 2000
            sz_ok = size == min(1024, c)
            print('rep=%d C=%d size=%d dH=%.3f MiB (%d B) B_client=%d B (%.0f B/entry) posctl=%s size_ok=%s' % (
                r, c, size, dH / MiB, dH, bcl, per, pc, sz_ok))
            rows[(c, r)] = dict(dH=dH, bcl=bcl, size=size)
            ok_all['size'] &= sz_ok; ok_all['pc'] &= pc
            if c == 1024:
                ok_all['dh'] &= dH <= 4 * MiB
                ok_all['bc'] &= bcl <= 4096 * size
            if c == 16 and dH >= 0.5 * MiB:
                ok_all['flags'].append('dH(16) rep%d >= 0.5 MiB' % r)
            if c > 0 and size and bcl > 1536 * size:
                ok_all['flags'].append('B_client C=%d rep%d > 1.5 KiB/entry' % (c, r))
    print('\nA4 row-1 conditions: part1=%s size=%s posctl=%s dH(1024)<=4MiB both reps=%s B_client(1024)<=4KiB*size=%s flags=%s' % (
        p1ok, ok_all['size'], ok_all['pc'], ok_all['dh'], ok_all['bc'], ok_all['flags']))

def cluster(d):
    S = {}
    for l in open(os.path.join(d, 'samples.txt')):
        m = re.match(r'S (\S+) (.*)', l.strip())
        if not m:
            continue
        lbl, rest = m.groups()
        S.setdefault(lbl, []).append(rest)
    P = {}
    for l in open(os.path.join(d, 'phase-lines.txt')):
        parts = l.split()
        tag = parts[0]
        if parts[1] == 'PHASE':
            P.setdefault(tag, {})[parts[2]] = kv(l)
    def val(lbl, key):
        for x in S.get(lbl, []):
            if x.startswith(key + '='):
                return x.split('=', 1)[1]
            if x.startswith(key + ' '):
                return x[len(key) + 1:]
        return None
    def nmt_committed(s):
        if not s: return None
        m = re.search(r'committed=(\d+)KB', s); return int(m.group(1)) * 1024 if m else None
    def hist(lbl):
        return histo_classes([x[len('client_histo '):] for x in S.get(lbl, []) if x.startswith('client_histo ')])
    print('tag | w1: estab fd heap(MiB) NMTint(MiB) rss(MiB) DNxc DNthr | w2: estab size fd heap(MiB) rss(MiB) NMTint(MiB) DNxc DNthr DNthrNMT(MiB) DNrss(MiB) | probe: dDirect(OPEN-START MiB) heapAfterGc CLOSED(MiB) | post10 DNxc')
    R = {}
    for r in (1, 2):
        for c in (0, 16, 256, 1024):
            t = 'C%d-r%d' % (c, r)
            if t not in P: continue
            w1, w2 = t + '-w1', t + '-w2'
            g = lambda l, k: val(l, k)
            ph = P[t]
            dd = (int(ph['OPEN']['direct']) - int(ph['START']['direct'])) / MiB
            row = dict(c=c, r=r, e1=int(g(w1, 'client_estab_9866')), e2=int(g(w2, 'client_estab_9866')),
                       size2=int(ph['CLOSED']['size']), sizeEnd=int(ph['END']['size']),
                       h2=int(g(w2, 'client_heap_used_bytes')), rss2=int(g(w2, 'client_rss_kb')) * 1024,
                       h1=int(g(w1, 'client_heap_used_bytes')), rss1=int(g(w1, 'client_rss_kb')) * 1024,
                       dd=dd, ph2=int(ph['CLOSED']['heapAfterGc']), dnxc2=int(g(w2, 'dn_xceivercount')),
                       dnthr2=int(g(w2, 'dn_dataxceiver_threads')), dnnmt2=nmt_committed(g(w2, 'dn_nmt_thread')),
                       dnrss2=int(g(w2, 'dn_rss_kb')) * 1024, int2=nmt_committed(g(w2, 'client_nmt_internal')),
                       int1=nmt_committed(g(w1, 'client_nmt_internal')), post=g(t + '-post10', 'dn_xceivercount'),
                       fd1=int(g(w1, 'client_fd')), fd2=int(g(w2, 'client_fd')),
                       dnxc1=int(g(w1, 'dn_xceivercount')), dnthr1=int(g(w1, 'dn_dataxceiver_threads')),
                       hist2=hist(w2))
            R[(c, r)] = row
            print(t, '|', row['e1'], row['fd1'], '%.2f' % (row['h1'] / MiB), '%.1f' % (row['int1'] / MiB), '%.1f' % (row['rss1'] / MiB),
                  row['dnxc1'], row['dnthr1'], '|', row['e2'], row['size2'], row['fd2'], '%.2f' % (row['h2'] / MiB), '%.1f' % (row['rss2'] / MiB),
                  '%.1f' % (row['int2'] / MiB), row['dnxc2'], row['dnthr2'], '%.1f' % (row['dnnmt2'] / MiB), '%.1f' % (row['dnrss2'] / MiB),
                  '|', '%.2f' % dd, '%.2f' % (row['ph2'] / MiB), '|', row['post'],
                  '| histo2', {k: v[0] for k, v in row['hist2'].items()})
    # du
    du = {}
    for l in open(os.path.join(d, 'du.txt')):
        p = l.split(); kind, tag = p[0], p[1]
        tot = 0
        for item in p[2:]:
            sz, path = item.split(':', 1)
            if not path.endswith('/logs'): tot += int(sz)
        du.setdefault(tag, {})[kind] = tot
    print('\n# A7 derived (relative to C=0 of the same rep)')
    conds = dict(conn=True, pc=True, dh=True, drss=True, disk=True, flags=[])
    for r in (1, 2):
        if (0, r) not in R: continue
        b = R[(0, r)]
        for c in (0, 16, 256, 1024):
            if (c, r) not in R: continue
            x = R[(c, r)]; t = 'C%d-r%d' % (c, r)
            dH2 = x['h2'] - b['h2']; dR2 = x['rss2'] - b['rss2']; dP2 = x['ph2'] - b['ph2']
            ddisk = du[t]['du-after'] - du[t]['du-before']
            e = min(1024, c)
            conn = abs(x['e2'] - e) <= 2 and abs(x['size2'] - e) <= 2
            pc = x['dd'] >= 64 and x['e1'] >= 1000
            print('rep=%d C=%d conn2=%d size=%d dH2=%.3f MiB dRSS2=%.2f MiB dProbeHeap2=%.3f MiB disk(dn+nn+tmp) after-before=%d B conn_ok=%s posctl=%s DNthreadNMT2-base=%.1f MiB DNrss2-base=%.1f MiB' % (
                r, c, x['e2'], x['size2'], dH2 / MiB, dR2 / MiB, dP2 / MiB, ddisk, conn, pc,
                (x['dnnmt2'] - b['dnnmt2']) / MiB, (x['dnrss2'] - b['dnrss2']) / MiB))
            conds['conn'] &= conn; conds['pc'] &= pc; conds['disk'] &= ddisk <= MiB
            if c == 1024:
                conds['dh'] &= dH2 <= 4 * MiB; conds['drss'] &= dR2 <= 8 * MiB
            if c == 16 and dH2 > 0.5 * MiB:
                conds['flags'].append('dH2(16) rep%d > 0.5 MiB' % r)
    print('\nA7 row-1 conditions:', conds)

if __name__ == '__main__':
    {'unit': unit, 'cluster': cluster}[sys.argv[1]](sys.argv[2])
