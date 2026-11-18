#!/usr/bin/env python3
# C5 stage 2: per-run summary from client.csv, samples.csv, marks.txt and the Byteman trace.
#   summary.py <run dir>
# trace: writers opened/closed; per writer the last cap and buffer identity; U_cbuf = sum of cap over distinct
# buffers of writers still open at the end (or at the last cbuf before death); slabs created; caps seen.
import sys, os, re, csv, collections
R = sys.argv[1]; MiB = 1048576.0
def rd(p):
    try: return open(os.path.join(R, p)).read().splitlines()
    except Exception: return []
# client
rows = list(csv.DictReader(rd('client.csv')))
oc = collections.Counter(r['outcome'].split(':')[0] for r in rows)
lat = [int(r['latency_ms']) for r in rows if r['outcome'] == 'ok']
print("clients: writes=%d %s lat_ms_med=%s lat_ms_max=%s last_i=%s" % (len(rows), dict(oc), sorted(lat)[len(lat)//2] if lat else 'NA', max(lat) if lat else 'NA', rows[-1]['i'] if rows else 'NA'))
# samples
S = [r for r in csv.DictReader(rd('samples.csv')) if r['direct_used'] not in ('NA', '-1')]
marks = dict((l.split(' ', 1)[0], l.split(' ', 1)[1]) for l in rd('marks.txt') if ' ' in l)
if S:
    mx = max(S, key=lambda r: int(r['direct_used']))
    last = S[-1]
    print("samples: n=%d max_direct=%.1fMiB (count %s) at %s; last_direct=%.1fMiB at %s; max_heap=%.0fMiB; last_total_hints=%s" % (
        len(S), int(mx['direct_used'])/MiB, mx['direct_count'], mx['epoch_ms'], int(last['direct_used'])/MiB, last['epoch_ms'],
        max(int(r['heap_used']) for r in S)/MiB, last['total_hints']))
b0 = marks.get('B0', 'NA').split(); m1 = marks.get('M1', 'NA').split()
B0 = int(b0[0])/MiB if b0 and b0[0] != 'NA' else None; M1 = int(m1[0])/MiB if m1 and m1[0] != 'NA' else None
print("marks: B0=%s M1=%s M1-B0=%s hints_B0=%s hints_M1=%s dc2_DN=%s" % (
    '%.1f' % B0 if B0 is not None else 'NA', '%.1f' % M1 if M1 is not None else 'NA',
    '%.1f' % (M1 - B0) if (B0 is not None and M1 is not None) else 'NA', b0[4] if len(b0) > 4 else 'NA', m1[4] if len(m1) > 4 else 'NA', marks.get('dc2_DN_M0')))
# trace
T = rd('c5.trace')
if T:
    cut = int(marks['m1_ms']) if 'm1_ms' in marks else 1 << 62   # writers closed by the shutdown after M1 do not count
    opened = {}; closed = set(); cap = {}; buf = {}; caps = collections.Counter(); ins = collections.Counter(); slabs = 0; slabn = 0; big = collections.Counter()
    for l in T:
        f = dict(x.split('=', 1) for x in l.split(' ')[1:] if '=' in x and not x.startswith('at='))
        k = l.split(' ', 1)[0]
        if k == 'opened': opened[f['w']] = f.get('host')
        elif k == 'closed':
            if int(f['ms']) <= cut: closed.add(f['w'])
        elif k == 'cbuf': cap[f['w']] = int(f['cap']); buf[f['w']] = f['buf']; caps[int(f['cap'])] += 1; ins[int(f['in'])] += 1
        elif k == 'created': slabs += 1; slabn = int(f['n'])
        elif k == 'direct':
            m = re.search(r'at=\[([^\]]*)\]', l); st = m.group(1).split(', ') if m else []
            who = next((s for s in st if 'cassandra' in s and 'Byteman' not in s), st[2] if len(st) > 2 else '?')
            big[(int(f['size']), re.sub(r'\(.*', '', who))] += 1
    openw = [w for w in opened if w not in closed]
    dist = {}
    for w in openw:
        if w in buf: dist[buf[w]] = cap[w]
    allb = {}
    for w in buf: allb[buf[w]] = cap[w]
    print("trace: opened=%d closed=%d open=%d open_with_buf=%d distinct_buf_open=%d U_cbuf=%.2fMiB distinct_buf_all=%d caps=%s ins=%s slabs_created=%d (n=%d) hosts=%d" % (
        len(opened), len(closed), len(openw), sum(1 for w in openw if w in buf), len(dist), sum(dist.values())/MiB, len(allb),
        dict(caps.most_common(3)), dict(ins.most_common(3)), slabs, slabn, len(set(opened.values()))))
    for (sz, who), c in sorted(big.items(), key=lambda x: -x[1]): print("  direct>=1MiB %d B x%d via %s" % (sz, c, who))
else:
    print("trace: none")
