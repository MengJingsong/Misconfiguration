#!/usr/bin/env python3
# 3-b confirm C4: victim view per window from victim.csv (one row per second). Windows: before = first connected second ..
# attack.start; during = attack.start .. the kernel kill (node.kill = last sampler row with the JVM alive; else node.end, else attack.end); after = the rest. Restart lifetimes
# (no attack): before = none; "during" = victim start .. node.end.   vsum.py <logs/LABEL>
import csv, sys, os
d = sys.argv[1]
rows = [r for r in csv.DictReader(open(d + '/victim.csv')) if r['t'][:1].isdigit()]
rd = lambda f: int(open(d + '/' + f).read()) if os.path.exists(d + '/' + f) else None
a0, a1, ne = rd('attack.start'), rd('attack.end'), (rd('node.kill') or rd('node.end'))
end = ne or a1
first_ok = next((int(r['t']) for r in rows if int(r['ok']) > 0), int(rows[0]['t']))
ERR = ['e_rto', 'e_wto', 'e_unav', 'e_opto', 'e_nohost', 'e_auth', 'e_noconn', 'e_other']
print(f'victim rows {len(rows)} s; first ok second {first_ok}; attack.start {a0}; node.end {ne}; attack.end {a1}')
def show(name, lo, hi):
    w = [r for r in rows if lo <= int(r['t']) < hi]
    if not w: print(f'  {name:7s} no samples'); return
    iss = sum(int(r['issued']) for r in w); ok = sum(int(r['ok']) for r in w)
    p99 = sorted(float(r['p99ms']) for r in w if float(r['p99ms']) >= 0); p50 = sorted(float(r['p50ms']) for r in w if float(r['p50ms']) >= 0)
    mx = max([float(r['maxms']) for r in w] + [-1]); i0 = rows.index(w[0]); base = rows[i0 - 1] if i0 > 0 else {k: '0' for k in ERR}
    ec = {k: int(w[-1][k]) - int(base[k]) for k in ERR}; med = lambda v: v[len(v) // 2] if v else -1
    last = [r['lastErr'] for r in w if r['lastErr']]
    print(f'  {name:7s} {len(w):4d} s issued={iss} ok={ok} success={100.0 * ok / iss if iss else float("nan"):5.1f}% p50(med)={med(p50):.1f}ms '
          f'p99(med)={med(p99):.1f}ms p99(max)={max(p99 + [-1]):.1f}ms max={mx:.1f}ms errors {" ".join(f"{k[2:]}={v}" for k, v in ec.items() if v)}'
          + (f' | e.g. {last[-1][:120]}' if last else ''))
if a0 and ne is None or (a0 and ne and ne > a0):
    show('before', first_ok, a0); show('during', a0, end); show('after', end, 10**14)
else:
    show('during', int(rows[0]['t']), end); show('after', end, 10**14)
ref = a0 or int(rows[0]['t'])
print('  timeline (2 s bins rel. to attack start / victim start): t,issued,ok,err,max p99 ms')
for b in range((int(rows[0]['t']) - ref) // 2000 - 1, (int(rows[-1]['t']) - ref) // 2000 + 1):
    w = [r for r in rows if ref + b * 2000 <= int(r['t']) < ref + (b + 1) * 2000]
    if w and (abs(b * 2) <= 30 or (ne and abs(ref + b * 2000 - ne) <= 10000)):
        print(f'    {b * 2:+5d}s {sum(int(r["issued"]) for r in w):4d} {sum(int(r["ok"]) for r in w):4d} {sum(int(r["err"]) for r in w):4d} {max(float(r["p99ms"]) for r in w):8.1f}')
