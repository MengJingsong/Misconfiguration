#!/usr/bin/env python3
# 3-b confirm C10: victim view per window. before = victim start .. attack start; during = attack start .. node-1 end
# (node 1's OOM = the HeapDumper safepoint in its GC log; else the last valid node-1 JMX sample if node 1 died; else
# attack end); after = from there to the victim's end.
# Prints per session: seconds, issued/s, success %, errors by class, p50/p99 of per-second p50/p99, max latency; then a
# 5-second timeline.   victimsum.py <logs/LABEL>
import csv, sys, os, re, datetime
d = sys.argv[1]
rows = [r for r in csv.DictReader(open(d + '/victim.csv')) if r['t'][:1].isdigit()]
a0 = int(open(d + '/attack.start').read()); a1 = int(open(d + '/attack.end').read())
out = open(d + '/outcome').read() if os.path.exists(d + '/outcome') else ''
end = a1
if 'OOM' in out or 'DEAD' in out:
    s = [r for r in csv.DictReader(open(d + '/samples.csv')) if r.get('heap_used', '').isdigit()]
    if s: end = int(s[-1]['t_ms'])
    g = d.replace('/logs/', '/runs/') + '/n1/gc.log'
    if os.path.exists(g):
        for line in open(g):
            if 'Entering safepoint region: HeapDumper' in line or 'ReportJavaOutOfMemory' in line:
                ts = re.match(r'\[([^\]]+)\]', line).group(1)
                end = int(datetime.datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() * 1000)
                print(f'node-1 OOM (GC log, {line.split("region: ")[1].strip()}) at {ts}'); break
print(f'attack start={a0} node1-end/attack-end={end} ({(end - a0) / 1000:.1f} s after attack start) outcome: {out.strip()}')
ERR = ['e_rto', 'e_wto', 'e_unav', 'e_opto', 'e_nohost', 'e_auth', 'e_other']
def win(rs, lo, hi): return [r for r in rs if lo <= int(r['t']) < hi]
for sess in ('V1', 'V2'):
    rs = [r for r in rows if r['sess'] == sess]
    if not rs: continue
    t_first, t_last = int(rs[0]['t']), int(rs[-1]['t']) + 1
    print(f'\n{sess} ({"node 1 = attacked coordinator" if sess == "V1" else "nodes 2+3"})')
    prev = {k: 0 for k in ERR}
    for name, lo, hi in (('before', t_first, a0), ('during', a0, end), ('after', end, t_last)):
        w = win(rs, lo, hi)
        if not w: print(f'  {name:7s} no samples'); continue
        iss = sum(int(r['issued']) for r in w); ok = sum(int(r['ok']) for r in w); er = sum(int(r['err']) for r in w)
        p50 = sorted(float(r['p50ms']) for r in w if float(r['p50ms']) >= 0); p99 = sorted(float(r['p99ms']) for r in w if float(r['p99ms']) >= 0)
        mx = max([float(r['maxms']) for r in w] + [-1])
        # cumulative error counters: difference over the window
        i0 = rs.index(w[0]); base = rs[i0 - 1] if i0 > 0 else {k: '0' for k in ERR}
        ec = {k: int(w[-1][k]) - int(base[k]) for k in ERR}
        succ = 100.0 * ok / iss if iss else float('nan')
        med = lambda v: v[len(v) // 2] if v else -1
        last = [r['lastErr'] for r in w if r['lastErr']]
        print(f'  {name:7s} {len(w):4d} s issued/s={iss / len(w):5.1f} ok={ok} err={er} success={succ:5.1f}% '
              f'p50(med)={med(p50):.1f}ms p99(med)={med(p99):.1f}ms p99(max)={max(p99 + [-1]):.1f}ms max={mx:.1f}ms '
              f'errors {" ".join(f"{k[2:]}={v}" for k, v in ec.items() if v)}' + (f' | e.g. {last[-1][:140]}' if last else ''))
    print('  timeline (5 s bins, rel. to attack start): t,issued,ok,err,max p99 ms')
    for b in range((t_first - a0) // 5000 - 1, (t_last - a0) // 5000 + 1):
        w = win(rs, a0 + b * 5000, a0 + (b + 1) * 5000)
        if not w: continue
        print(f'    {b * 5:+5d}s {sum(int(r["issued"]) for r in w):4d} {sum(int(r["ok"]) for r in w):4d} {sum(int(r["err"]) for r in w):4d} '
              f'{max(float(r["p99ms"]) for r in w):8.1f}')
