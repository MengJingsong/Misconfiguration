#!/usr/bin/env python3
"""B3f/B3g (+ amendments R3-R6) checks for the cluster tier. usage: cluster-analyze.py <cluster log dir>
Reads phases.json and rss-<life>.csv; prints a readings table and EXPECTED lines, then the verdict by R5's mapping."""
import csv, json, os, statistics, sys
D = sys.argv[1]
P = json.load(open(os.path.join(D, 'phases.json')))
LT = P['lifetimes']
MiB = 1024 * 1024
ok = {}


def E(name, cond, detail=''):
    ok[name] = bool(cond)
    print(f"EXPECTED: {name}: {'HIT' if cond else 'MISS'} -- {detail}")


def rss(name):
    rows = []
    p = os.path.join(D, f'rss-{name}.csv')
    if os.path.exists(p):
        for r in csv.DictReader(open(p)):
            if r['RssAnon_kB'] not in ('None', ''):
                rows.append((int(r['epoch_ms']), int(r['RssAnon_kB']) / 1024.0))
    return rows


def pre_resize(name, m):
    rows = rss(name); end = m.get('redist_seen_ms')
    w = [v for t, v in rows if end - 20000 <= t <= end - 2000]   # 20 s before the run (the 2-s poll can be up to 2 s late)
    return statistics.median(w) if w else None


if P.get('error'):
    print('RUN ERROR:', P['error'])
print(f"N={P['N']} load sstables={P.get('load_sstables')}")
print('life | pool MB | T_before | T MiB | R MiB | R_pre MiB | dRw | tablestats isc MiB | Summary.db MiB | files | trace keep/resample (isc) | downsample')
F = {}
for name, rec in LT.items():
    for tag in ('first', 'after_alter_max1', 'manual_run'):
        m = rec.get(tag)
        if not m:
            continue
        pre = pre_resize(name, m) if tag == 'first' else None
        m['_pre'] = pre
        print(f"{name}/{tag} | {rec.get('pool_MB')} | {m['T_before_MiB']:.3f} | {m['T_MiB']:.3f} | {m['R_MiB']:.1f} | "
              f"{pre if pre is None else round(pre, 1)} | {None if pre is None else round(pre - m['R_MiB'], 1)} | "
              f"{(m['tablestats_isc_bytes'] or 0)/MiB:.3f} | {m['summary_db_total']/MiB:.3f} | {len(m['summary_db_sizes'])} | "
              f"{m['trace_keep_isc']}/{m['trace_resample_isc']} | {m['downsample']}")
g = lambda n: LT.get(n, {}).get('first')
L1, L2, L3, L4, L5, L6 = (g(n) for n in ('L1-4096', 'L2-default', 'L3-400', 'L4-100', 'L5-0a', 'L6-0b'))
if not (L1 and L5):
    print('incomplete run'); sys.exit(1)
pools = {n: LT[n].get('pool_MB') for n in LT}
E('pool sizes as set (4096, 409 default, 400, 100, 0, 0; L7 100)', [pools.get(n) for n in ('L1-4096', 'L2-default', 'L3-400', 'L4-100', 'L5-0a', 'L6-0b', 'L7-step6')]
  == [4096, 409, 400, 100, 0, 0, 100], str(pools))
E('row 5 (invalid if missed): a Completed resizing line in every lifetime', all(LT[n].get('first') or LT[n].get('manual_run') for n in LT if n != 'L0-load'))
T4 = L1['T_MiB']
rmax = max(L1['summary_db_sizes']) / MiB
print(f"S_full measured T4096 = {T4:.3f} MiB; r_max = {rmax:.3f} MiB (largest Summary.db at 4096); sstables {L1['sstables']}")
E('row 4 positive control: T4096 >= 728 MiB', T4 >= 728, f'{T4:.3f}')
E('B3f sub: T4096 = 808.7 MiB +-2%', abs(T4 - 808.7) <= 0.02 * 808.7, f'{T4:.3f}')
E('B3f: at 4096 nothing downsampled (trace keep = isc sstables, resample 0)', L1['trace_resample_isc'] == 0 and L1['trace_keep_isc'] == L1['sstables'],
  f"{L1['trace_keep_isc']}/{L1['trace_resample_isc']} of {L1['sstables']}")
refuted = False
for nm, m, X in (('default', L2, 409), ('400', L3, 400), ('100', L4, 100)):
    if not m:
        E(f'X={nm}: present', False); continue
    T = m['T_MiB']
    le = T <= X + 0.0625
    refuted |= not le
    E(f'row 1/2 X={nm}: T <= X (+64 KiB)', le, f'T={T:.4f} X={X}')
    E(f'B3f X={nm}: T > X - r_max', T > X - rmax, f'{T:.3f} > {X - rmax:.3f}')
    E(f'B3f X={nm}: tablestats isc <= T', (m['tablestats_isc_bytes'] or 0) / MiB <= T + 1e-9, f"{(m['tablestats_isc_bytes'] or 0)/MiB:.4f}")
    E(f'B3f X={nm}: Summary.db total = T +-5%', abs(m['summary_db_total'] / MiB - T) <= 0.05 * T, f"{m['summary_db_total']/MiB:.3f}")
    if m['downsample'] > 0:
        E(f'R4 X={nm}: line 341 both outcomes seen (trace keep > 0 and resample > 0 for isc)', m['trace_keep_isc'] > 0 and m['trace_resample_isc'] > 0,
          f"{m['trace_keep_isc']}/{m['trace_resample_isc']}")
    else:
        E(f'R4 X={nm}: run changed nothing: no isc sstable re-sampled', m['trace_resample_isc'] == 0, f"{m['trace_keep_isc']}/{m['trace_resample_isc']}")
T0 = L5['T_MiB']
E('row 6: T ~ F at X=0 (3 <= T0 <= 12 MiB)', 3 <= T0 <= 12, f'{T0:.3f}')
E('row 6: X=0 keeps nothing (trace keep 0)', L5['trace_keep_isc'] == 0, f"{L5['trace_keep_isc']}/{L5['trace_resample_isc']}")
nofall = L4 and L4['T_MiB'] > 0.9 * T4
refuted |= bool(nofall)
E('R5 "T does not fall" row absent: T(100) <= 0.9*T4096', not nofall, f"{L4['T_MiB'] if L4 else None}")
R4096 = L1['R_MiB']
sigma = abs(L6['R_MiB'] - L5['R_MiB']) if L6 else None
E('R5 noise: sigma <= 0.25*(T4096 - T0)', sigma is not None and sigma <= 0.25 * (T4 - T0), f'sigma={sigma}')
partial = False; disagree = False
for nm, m in (('default', L2), ('400', L3), ('100', L4), ('0', L5)):
    if not m:
        continue
    dT = T4 - m['T_MiB']; fall = R4096 - m['R_MiB']
    side = fall >= 0.5 * dT
    if not side and sigma is not None and (0.5 * dT - fall) > 3 * sigma:
        partial = True
    E(f'row 1 RSS X={nm}: across-lifetime fall >= 0.5*dT', side, f'fall={fall:.1f} dT={dT:.1f}')
    E(f'B3f sub X={nm}: |fall - dT| <= max(3 sigma, 0.15 dT)', sigma is not None and abs(fall - dT) <= max(3 * sigma, 0.15 * dT), f'|{fall:.1f}-{dT:.1f}|')
    if m.get('_pre') is not None:
        dTw = m['T_before_MiB'] - m['T_MiB']; dRw = m['_pre'] - m['R_MiB']
        if dTw >= 16:   # D3
            sw = dRw >= 0.5 * dTw
            E(f'R5/D3 within-lifetime X={nm}: dRw={dRw:.1f} vs 0.5*dTw={0.5*dTw:.1f}, same side as the across-lifetime fall', sw == side)
            disagree |= (sw != side)
        else:
            okz = sigma is not None and abs(dRw) <= 3 * sigma
            E(f'R5/D3 within-lifetime X={nm}: run changed T by {dTw:.1f} < 16 MiB, so |dRw|={abs(dRw):.1f} <= 3 sigma', okz)
            disagree |= not okz
A = LT.get('L6-0b', {}).get('after_alter_max1')
if A:
    E('step 5 floor control moved: T after max_index_interval=1 > 2*T0', A['T_MiB'] > 2 * T0, f"{A['T_MiB']:.3f}; force upsample {A['force_upsample']}")
    E('B3f sub step 5: T ~ S_full again (+-5% of T4096)', abs(A['T_MiB'] - T4) <= 0.05 * T4, f"{A['T_MiB']:.3f}")
    E('B3f sub step 5: RssAnon back to about R4096 (within 0.25*T4096)', abs(A['R_MiB'] - R4096) <= 0.25 * T4, f"{A['R_MiB']:.1f} vs {R4096:.1f}")
else:
    E('step 5 floor control moved', False, 'missing')
s6 = LT.get('L7-step6', {})
bypass = None
if s6.get('manual_run'):
    tt = s6['manual_run']['T_MiB']
    E('step 6: manual run T_trig <= 100 MiB (+64 KiB)', tt <= 100.0625, f'{tt:.3f}')
    ta = s6.get('T_after_jmx_MiB')
    bypass = ta is not None and ta > 100
    E('step 6 (A3 7b): T_after > 100 MiB with no run', bypass, f'T_after={ta}, tablestats={s6.get("T_after_tablestats_isc_bytes")}, Completed lines after manual run={s6.get("completed_lines_after_manual")}')
    E('step 6: no Completed resizing after the manual run', s6.get('completed_lines_after_manual') == 0)
    E('B3f sub step 6: T_after ~ T_trig + N2*212 B (+-10%)', ta is not None and abs(ta - (tt + P['N2'] * 212 / MiB)) <= 0.1 * (P['N2'] * 212 / MiB), f'{ta} vs {tt + P["N2"]*212/MiB:.1f}')
else:
    E('step 6 present', False)
invalid = not ok.get('row 4 positive control: T4096 >= 728 MiB') or not ok.get('row 5 (invalid if missed): a Completed resizing line in every lifetime')
row1 = all(ok.get(f'row 1/2 X={x}: T <= X (+64 KiB)') for x in ('default', '400', '100')) and all(ok.get(f'row 1 RSS X={x}: across-lifetime fall >= 0.5*dT') for x in ('default', '400', '100', '0'))
notconf = (not ok.get('R5 noise: sigma <= 0.25*(T4096 - T0)')) or disagree or not ok.get('step 5 floor control moved: T after max_index_interval=1 > 2*T0', False) \
          or not ok.get('row 6: T ~ F at X=0 (3 <= T0 <= 12 MiB)')
if invalid:
    v = 'Invalid'
elif refuted:
    v = 'Refuted'
elif partial:
    v = 'Refuted (partial)'
elif notconf or not row1:
    v = 'Not confirmed'
else:
    v = 'Confirmed'
eff = {'Confirmed': 'caps only on some paths (bypass)' if bypass else 'caps', 'Refuted': 'does not cap',
       'Refuted (partial)': 'caps only on some paths (bypass)'}.get(v, 'undetermined')
print(f'CLUSTER VERDICT (R5 mapping): {v}; Effect: {eff}')
