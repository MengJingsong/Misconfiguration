# Applies B3f and B3g (S4-A5) to cluster/run1/<cell>/. usage: python3 analyze_cluster.py <run1 dir>
import sys, re, os
R = sys.argv[1]; MiB = 1 << 20
def sess(c):
    ev = {}
    for l in open(os.path.join(R, c, 'session.txt')):
        m = re.match(r'### (\S+) (\d+) (.*)', l)
        if not m: continue
        t, ms, msg = m.group(1), int(m.group(2)), m.group(3)
        for k in ('client start', 'end-of-hold readings start', 'cell done'):
            if msg.startswith(k): ev[k] = ms
        m2 = re.match(r'BytesSent (pre|endhold|post)=(\d*)', msg)
        if m2 and m2.group(2): ev['bs_' + m2.group(1)] = int(m2.group(2))
        if msg.startswith('client exit'): ev['client exit'] = ms; ev['exitmsg'] = msg
    return ev
def samples(c):
    out = []
    for l in open(os.path.join(R, c, 'samples.txt')):
        if l.startswith('#'): continue
        f = l.split()
        if len(f) == 5 and f[1] != 'NA': out.append(tuple(int(x) for x in f))
    return out
def heap(c, f):
    p = os.path.join(R, c, f)
    if not os.path.exists(p): return None
    m = re.search(r'used (\d+)K', open(p).read()); return int(m.group(1)) * 1024 if m else None
res = {}
for c in ['A', 'B', 'C', 'D', 'B-rep']:
    if not os.path.isdir(os.path.join(R, c)): continue
    e = sess(c); s = samples(c)
    pre = [x for x in s if x[0] < e['client start']][-1]
    if 'end-of-hold readings start' in e:
        end = [x for x in s if x[0] < e['end-of-hold readings start']][-1]
        bs_end = e.get('bs_endhold')
    else:
        during = [x for x in s if e['client start'] <= x[0] <= e['client exit']]
        end = max(during, key=lambda x: x[1]); bs_end = e.get('bs_post')
    d_other = (end[1] - pre[1]) * 1024; d_rss = (end[2] - pre[2]) * 1024
    produced_end = bs_end - e['bs_pre'] if bs_end is not None else None
    produced_post = e['bs_post'] - e['bs_pre']
    backlog = produced_end - end[3] - end[4] if produced_end is not None else None
    peak_other = (max(x[1] for x in s if x[0] >= e['client start']) - pre[1]) * 1024
    res[c] = dict(dOther=d_other, dRSS=d_rss, prodEnd=produced_end, prodPost=produced_post, backlog=backlog,
                  sendq=end[3], recvq=end[4], peakOther=peak_other, heapPre=heap(c, 'heapinfo-pre.txt'), heapEnd=heap(c, 'heapinfo-endhold.txt'),
                  client=e.get('exitmsg'), otherPre=pre[1]*1024, otherEnd=end[1]*1024)
    r = res[c]
    print('%-5s dOther=%7.1f MiB peak=%7.1f dRSS=%7.1f MiB  produced(endhold)=%s produced(post)=%d  SendQ=%d RecvQ=%d  backlog=%s  heapPre=%s heapEnd=%s  Other pre/end=%.1f/%.1f MiB' % (
        c, d_other/MiB, peak_other/MiB, d_rss/MiB, produced_end, produced_post, end[3], end[4], backlog,
        r['heapPre'] and '%.1fMiB' % (r['heapPre']/MiB), r['heapEnd'] and '%.1fMiB' % (r['heapEnd']/MiB), pre[1]/1024, end[1]/1024))
    print('      ', r['client'])
A, B, C, D = res['A'], res['B'], res['C'], res['D']
row1 = A['dOther'] >= 48*MiB and B['dOther'] >= 200*MiB and 3 <= B['backlog']/A['backlog'] <= 5 and 2.5 <= B['dOther']/A['dOther'] <= 6
row3 = C['dOther'] <= B['dOther']/7 and D['dOther'] <= 32*MiB
print('\nratios: backlog B/A=%.3f dOther B/A=%.3f dOther B/C=%.2f; D dOther(peak during read)=%.1f MiB' % (B['backlog']/A['backlog'], B['dOther']/A['dOther'], B['dOther']/max(1, C['dOther']), D['dOther']/MiB))
print('row1(scales, hundreds of MiB)=%s row3(controls)=%s' % (row1, row3))
if 'B-rep' in res: print('repeat B vs B-rep dOther %.1f / %.1f MiB, backlog %d / %d' % (B['dOther']/MiB, res['B-rep']['dOther']/MiB, B['backlog'], res['B-rep']['backlog']))
