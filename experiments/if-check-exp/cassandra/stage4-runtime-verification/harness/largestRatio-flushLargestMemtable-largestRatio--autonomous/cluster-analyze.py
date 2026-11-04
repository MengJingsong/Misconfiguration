#!/usr/bin/env python3
"""Analysis of the cluster tier (B3f / B3g with amendments R6-R8) of largestRatio-flushLargestMemtable-largestRatio--autonomous.
usage: cluster-analyze.py <run dir>/cluster     reads each arm's arm.json, flushes.txt, jmx.csv, stress-*.out, system.log
Prints one block per arm and EXPECTED lines for B3f's predictions; a NO is recorded, not acted on."""
import json, os, re, statistics, sys

D = sys.argv[1]
MIB, GIB = 1 << 20, 1 << 30
EXP = {'yes': 0, 'no': 0}


def expect(desc, cond):
    EXP['yes' if cond else 'no'] += 1
    print(f'EXPECTED: {desc} — {"yes" if cond else "NO"}')


def arm(name):
    d = f'{D}/{name}'
    if not os.path.exists(d + '/arm.json'):
        return None
    a = json.load(open(d + '/arm.json'))
    L = a['L_MiB'] * MIB
    t0, t1 = a['stress_start_ms'], a['stress_end_ms']
    sel, reasons = [], {}
    for l in open(d + '/flushes.txt', errors='replace'):
        m = re.search(r'Flushing largest (.+?) to free up room\. Used total: ([\d.]+)/([\d.]+), live: ([\d.]+)/([\d.]+), '
                      r'flushing: ([\d.]+)/([\d.]+), this: ([\d.]+)/([\d.]+)', l)
        if m:
            sel.append({'owner': m.group(1), 'a': float(m.group(2)), 'live': float(m.group(4)), 'flushing': float(m.group(6)),
                        'g': float(m.group(8))})
        m = re.search(r'Enqueuing flush of (\S+), Reason: (\w+)', l)
        if m:
            k = (m.group(1).startswith(('ks1.', 'ks2.', 'ks3.', 'ks4.')), m.group(2))
            reasons[k] = reasons.get(k, 0) + 1
    rows = []
    for l in open(d + '/jmx.csv'):
        p = l.strip().split(',')
        if len(p) != 6 or 'ERR' in p:
            continue
        try:
            rows.append((int(p[0]), int(p[1]), int(p[2]), int(p[3]), int(p[4]), None if p[5] == 'null' else int(p[5])))
        except ValueError:
            pass
    win = [r for r in rows if t0 <= r[0] <= t1]
    out = {}
    for f in sorted(os.listdir(d)):
        if f.startswith('stress-ks') and f.endswith('.out'):
            s = open(d + '/' + f, errors='replace').read()
            g = lambda k: (re.search(k + r'\s*:\s*([\d,.]+)', s) or [None, None])[1]
            out[f] = {'op_rate': g('Op rate'), 'partitions': g('Total partitions'), 'errors': g('Total errors'),
                      'timeouts_lines': len(re.findall(r'WriteTimeout|timed out', s)), 'bytes': len(s)}
    syslog = open(d + '/system.log', errors='replace').read()
    r = {'name': name, 'L': L, 'arm': a, 'sel': sel, 'reasons': reasons, 'win': win, 'stress': out,
         'errors': len(re.findall(r'^ERROR', syslog, re.M)), 'oom': 'java.lang.OutOfMemoryError' in syslog}
    am = [x['a'] for x in sel]
    gm = [x['g'] for x in sel]
    r['a_max'] = max(am) if am else None
    r['a_med'] = statistics.median(am) if am else None
    r['g_med'] = statistics.median(gm) if gm else None
    r['n_sel'] = len(sel)
    r['limit_flush_ks'] = reasons.get((True, 'MEMTABLE_LIMIT'), 0)
    r['peak_allmem'] = max((w[1] for w in win), default=None)
    # runbook fix D2: old gen after each collection from gc.log (G1 Old + Humongous regions after the pause, x 16 MiB)
    gcs = []
    for l in open(d + '/gc.log', errors='replace'):
        m = re.match(r'\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}[+-]\d{4})\].*GC\((\d+)\) (Old|Humongous) regions: \d+->(\d+)', l)
        if m:
            import datetime
            ts = int(datetime.datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() * 1000)
            if gcs and gcs[-1][1] == int(m.group(2)):
                gcs[-1][2] += int(m.group(4))
            else:
                gcs.append([ts, int(m.group(2)), int(m.group(4))])
    r['gc_old'] = [(t, n * 16 * MIB) for t, _, n in gcs]
    cu = [b for t, b in r['gc_old'] if t0 <= t <= t1]
    r['old_postgc_med'] = statistics.median(cu) if cu else None
    r['old_postgc_max'] = max(cu) if cu else None
    r['blocked'] = (win[0][2], win[-1][2]) if win else None
    r['heap_max'] = max((w[3] for w in win), default=None)
    print(f'--- {name}: L={a["L_MiB"]} MiB build={a["build"]} workload={a["workload"]} stress {(t1 - t0) / 1000:.0f} s rc={a["stress_rc"]} '
          f'limit_stop={a.get("stress_stopped_by_limit")} samples={len(win)}')
    print(f'  selections (Flushing largest) {len(sel)}; a max {r["a_max"]} median {r["a_med"]}; g median {r["g_med"]}; '
          f'owners {sorted(set(x["owner"] for x in sel))[:6]}')
    print(f'  flush reasons (stress table?, reason): {reasons}')
    if win:
        print(f'  AllMemtablesOnHeapDataSize peak {r["peak_allmem"] / MIB:.1f} MiB = {r["peak_allmem"] / L:.3f} L; '
              f'BlockedOnAllocation {r["blocked"][0]} -> {r["blocked"][1]}; heap used max {r["heap_max"] / MIB:.0f} MiB; '
              f'old-gen post-GC median {r["old_postgc_med"] / MIB if r["old_postgc_med"] else 0:.0f} MiB max '
              f'{r["old_postgc_max"] / MIB if r["old_postgc_max"] else 0:.0f} MiB')
    print(f'  gc.log old+humongous after GC in window: {len(cu)} pauses')
    print(f'  stress: {out}')
    print(f'  system.log ERROR lines {r["errors"]}, OOM {r["oom"]}; du {open(d + "/du.txt").read().split() if os.path.exists(d + "/du.txt") else ""}')
    return r


R = {n: arm(n) for n in ('L256-skew', 'L256-even', 'L1024-skew', 'L1024-even', 'never')}
print()
for n in ('L256-skew', 'L256-even', 'L1024-skew', 'L1024-even'):
    r = R[n]
    if not r:
        continue
    expect(f'{n}: selections happened (Flushing largest lines) [B3g "not reached" row excluded]', r['n_sel'] > 0)
    expect(f'{n}: every a <= 1.02 (max {r["a_max"]})', r['a_max'] is not None and r['a_max'] <= 1.02)
    expect(f'{n}: peak AllMemtablesOnHeapDataSize <= L ({r["peak_allmem"] / r["L"]:.3f} L)', r['peak_allmem'] <= r['L'])
    expect(f'{n}: median a in [0.33, 0.7] ({r["a_med"]})', r['a_med'] is not None and 0.33 <= r['a_med'] <= 0.7)
    other = {k: v for k, v in r['reasons'].items() if k[0] and k[1] != 'MEMTABLE_LIMIT'}
    expect(f'{n}: B3h — every flush of a stress table is MEMTABLE_LIMIT (others {other})', not other)
for Lv in (256, 1024):
    s, e = R[f'L{Lv}-skew'], R[f'L{Lv}-even']
    if not (s and e):
        continue
    expect(f'L={Lv}: |median a skew - even| <= 0.10 ({s["a_med"]} vs {e["a_med"]})', abs(s['a_med'] - e['a_med']) <= 0.10)
    expect(f'L={Lv}: |max a skew - even| <= 0.10 ({s["a_max"]} vs {e["a_max"]})', abs(s['a_max'] - e['a_max']) <= 0.10)
    ps, pe = s['peak_allmem'] / s['L'], e['peak_allmem'] / e['L']
    expect(f'L={Lv}: |peak AllMem/L skew - even| <= 0.10 ({ps:.3f} vs {pe:.3f})', abs(ps - pe) <= 0.10)
    expect(f'L={Lv}: g median even in [0.08, 0.15] ({e["g_med"]}), skew in [0.33, 0.6] ({s["g_med"]})',
           0.08 <= e['g_med'] <= 0.15 and 0.33 <= s['g_med'] <= 0.6)
    ratio = e['limit_flush_ks'] / s['limit_flush_ks'] if s['limit_flush_ks'] else float('inf')
    expect(f'L={Lv}: MEMTABLE_LIMIT flushes even/skew in [2, 4] ({e["limit_flush_ks"]}/{s["limit_flush_ks"]} = {ratio:.2f})', 2 <= ratio <= 4)
for w in ('skew', 'even'):
    a, b = R[f'L256-{w}'], R[f'L1024-{w}']
    if not (a and b):
        continue
    k = b['peak_allmem'] / a['peak_allmem']
    expect(f'PC {w}: peak AllMem L1024 / L256 in [3, 5] ({b["peak_allmem"] / MIB:.0f} / {a["peak_allmem"] / MIB:.0f} MiB = {k:.2f})', 3 <= k <= 5)
    dg = (b['old_postgc_med'] - a['old_postgc_med']) / GIB
    expect(f'PC {w}: old-gen post-GC baseline L1024 - L256 = 0.5 +- 0.3 GiB ({dg:.2f} GiB)', 0.2 <= dg <= 0.8)
n = R['never']
if n:
    L = n['L']
    expect(f'never: no Flushing largest lines ({n["n_sel"]}) and no MEMTABLE_LIMIT flush of ks1 ({n["limit_flush_ks"]}) [R8 invalid row excluded]',
           n['n_sel'] == 0 and n['limit_flush_ks'] == 0)
    expect(f'never: AllMem plateau <= 1.02 L ({n["peak_allmem"] / L:.3f} L)', n['peak_allmem'] <= 1.02 * L)
    expect(f'never: AllMem plateau >= 0.9 L [R8 not-reached row excluded] ({n["peak_allmem"] / L:.3f} L)', n['peak_allmem'] >= 0.9 * L)
    expect(f'never: BlockedOnAllocation count rises ({n["blocked"]})', n['blocked'][1] > n['blocked'][0])
    st = list(n['stress'].values())[0] if n['stress'] else {}
    expect(f'never: stress shows timeouts or zero throughput after the plateau ({st})', st.get('timeouts_lines', 0) > 0 or st.get('op_rate') in (None, '0'))
    expect(f'never: no OOM ({n["oom"]})', not n['oom'])
    win = n['win']
    plateau = [w for w in win if w[1] >= 0.9 * L]
    if plateau:
        tp = plateau[0][0]
        cu = [b for t, b in n['gc_old'] if tp <= t <= n['arm']['stress_end_ms']]
        if cu:
            expect(f'never: R8 — old-gen post-GC after the plateau does not end > 1.5 L above its first post-plateau sample '
                   f'({cu[0] / MIB:.0f} -> {cu[-1] / MIB:.0f} MiB)', cu[-1] - cu[0] <= 1.5 * L)
        t_pl = (plateau[0][0] - n['arm']['stress_start_ms']) / 1000
        print(f'never: plateau (>= 0.9 L) first reached {t_pl:.0f} s after stress start; AllMem at end {win[-1][1] / MIB:.1f} MiB')
print(f'EXPECTED totals: {EXP["yes"]} yes, {EXP["no"]} NO')
