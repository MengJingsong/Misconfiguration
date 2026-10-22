#!/usr/bin/env python3
"""B3f/B3g + amendment R8 of index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous.
usage: cluster-analyze.py <cluster dir>   (reads phases.json written by cluster-run.py; prints EXPECTED: lines and the verdict)"""
import json, math, re, statistics, sys

D = sys.argv[1]
PH = json.load(open(f'{D}/phases.json'))
MiB = 1024 * 1024
ok, miss = {}, {}


def exp(name, cond, detail='', sub=False):
    (miss if sub else ok)[name] = bool(cond)
    print(f'EXPECTED{" (sub-prediction)" if sub else ""}: {name}: {"PASS" if cond else "FAIL"} -- {detail}')


if PH.get('error'):
    print('ERROR in run:', PH['error'])
L0 = PH['lifetimes'].get('L0-main', {}); L1 = PH['lifetimes'].get('L1-auto', {})
BATCH, NB = PH['BATCH'], PH['BATCHES']
base = L0.get('baseline')
if not base:
    print('VERDICT: Invalid (no baseline)'); sys.exit(0)
S = base['isr_bytes'] / NB
floor_entries = math.ceil(BATCH / 128)
Fp = math.ceil((S / BATCH) * floor_entries)
SF = NB * Fp
eps = base['T_jmx_MiB'] * MiB - base['isr_bytes']
print(f'S={S:.0f} B ({S/MiB:.3f} MiB) Fp={Fp} B sumF\'={SF/MiB:.3f} MiB S-Fp={(S-Fp)/MiB:.3f} MiB eps(system)={eps/MiB:.3f} MiB')
print(f'baseline: yaml cap {L0.get("pool_MB")} MB (JMX {base.get("cap_jmx")}), T={base["T_jmx_MiB"]} MiB, sstables={base["sstables"]}, '
      f'completed lines {base["completed_lines"]}, RssAnon median {statistics.median(s[1] for s in base["rss"])/1024:.1f} MiB')
exp('format BIG: 20 -big-Summary.db', base['big_summary_files'] == NB and base['summary_db_n'] == NB, f'{base["big_summary_files"]}/{base["summary_db_n"]}')
exp('bypass (a): baseline T >> cap 64 with no run', base['T_jmx_MiB'] > 64 and base['completed_lines'] == 0 and L0.get('pool_MB') == 64,
    f'T={base["T_jmx_MiB"]} cap={L0.get("pool_MB")} completed={base["completed_lines"]}')
TABLE_K = {4096: 20, 1024: 10, 512: 5, 'auto': 4, 64: 0, 8: 0}


def kpred(cap):
    r = cap * MiB - SF - eps
    return (min(NB, int(r // (S - Fp))) if r > 0 else 0), r


runs = [(k, v) for k, v in L0.get('runs', {}).items() if k.startswith('C')] + [(k, v) for k, v in L1.get('runs', {}).items()]
sstables_ok = base['sstables'] == NB
compaction_ok = True
T_at = {}; dR_at = {}
for tag, r in runs:
    cap = r['cap']; label = 'auto' if tag == 'Cauto' else cap
    k, rp = kpred(cap)
    tp = (SF + k * (S - Fp) + eps) / MiB
    T = r['T_MiB']; T_at[label] = T
    r258 = r['r258'][0][1] if r['r258'] else None
    dT = r['T_before_MiB'] - T; dR = r['R_before_MiB'] - r['R_after_MiB']; dR_at[label] = dR
    tol = max(0.15 * abs(dT), 64)
    for st in (r['before'], r['after']):
        sstables_ok &= st['sstables'] == NB
        compaction_ok &= not any(re.search(r'\bCompaction\b|Validation|Cleanup', l) for l in st['compactionstats_lines'])
    print(f'{tag}: cap={cap} k={k} (table {TABLE_K[label]}) Tpred={tp:.3f} T={T:.3f} (before {r["T_before_MiB"]:.3f}) '
          f'R258={r258} pred={rp:.0f} ({(r258 or 0)/MiB:.3f} vs {rp/MiB:.3f} MiB) keep/resample isr {r["keep_isr"]}/{r["resample_isr"]} '
          f'dT={dT:.1f} dRssAnon={dR:.1f} tol={tol:.1f} downsample={r["downsample"]} r258 lines={len(r["r258"])}')
    if label == 8:
        exp('C=8 overshoot: T ~ sumF > 8, R258 < 0, no keep', T > 8 and abs(T - tp) <= 2 and r258 is not None and r258 < 0 and r['keep_isr'] == 0,
            f'T={T:.3f} R258={r258}')
    else:
        exp(f'{tag} row 1: T <= C+1 and T ~ pred (2 MiB)', T <= cap + 1 and abs(T - tp) <= 2, f'T={T:.3f} pred={tp:.3f} C={cap}')
        exp(f'{tag} R258 > 0 (branch taken)', r258 is not None and r258 > 0, f'R258={r258}')
    exp(f'{tag} RssAnon falls by ~dT', abs(dR - dT) <= tol, f'dR={dR:.1f} dT={dT:.1f} tol={tol:.1f}')
    exp(f'{tag} R258 within 2 MiB of C-sumF\'-eps', r258 is not None and abs(r258 - rp) <= 2 * MiB, f'{r258} vs {rp:.0f}', sub=True)
    exp(f'{tag} keep(isr) = k', r['keep_isr'] == k, f'{r["keep_isr"]} vs {k}', sub=True)
    exp(f'{tag} k = B3f table', k == TABLE_K[label], f'{k} vs {TABLE_K[label]}', sub=True)
    mech_bad = r258 is not None and ((r258 <= 0 and r['keep_all'] > 0) or (label == 8 and r258 > 0) or (r258 >= S - Fp and r['keep_isr'] == 0))
    exp(f'{tag} mechanism row not hit', not mech_bad, '')
for tag, r in L0.get('runs', {}).items():
    if tag.startswith('restore'):
        exp(f'{tag} restored full', r.get('restored_ok'), f'T={r["T_MiB"]:.3f} intervals={sorted(set(r["after"]["isr_intervals"]))} n={len(r["after"]["isr_intervals"])} force_upsample={r["force_upsample"]}')
        for st in (r['before'], r['after']):
            sstables_ok &= st['sstables'] == NB
neg = L0.get('negative_control')
if neg:
    rs = [s[1] / 1024 for s in neg['rss']]
    first = statistics.median(rs[:3]); last = statistics.median(rs[-3:])
    dTn = neg['after']['T_jmx_MiB'] - neg['before']['T_jmx_MiB']
    exp('negative control flat (300 s, cap 64, no run)', abs(dTn) <= 1 and abs(last - first) <= 64 and neg['completed_lines'] == 0,
        f'dT={dTn:.3f} RssAnon first {first:.1f} last {last:.1f} range {max(rs)-min(rs):.1f} MiB completed={neg["completed_lines"]} T={neg["before"]["T_jmx_MiB"]}')
    sigma = statistics.pstdev(rs); print(f'sigma(RssAnon, negative control) = {sigma:.1f} MiB')
else:
    exp('negative control flat (300 s, cap 64, no run)', False, 'not run')
if 4096 in T_at and 64 in T_at:
    exp('positive control: T(4096) - T(64) >= 0.9 * 20(S-F)', T_at[4096] - T_at[64] >= 0.9 * NB * (S - Fp) / MiB,
        f'{T_at[4096] - T_at[64]:.1f} vs {NB*(S-Fp)/MiB:.1f} MiB; dRss {dR_at.get(64, 0):.1f}')
exp('auto pool line 409 MB', L1.get('pool_MB') == 409, f'{L1.get("pool_MB")}', sub=True)
exp('sstable count 20 at every reading', sstables_ok, '')
exp('no compaction other than index summary redistribution', compaction_ok, '')

row2 = any(r['T_MiB'] > r['cap'] + 1 for t, r in runs if r['cap'] >= 64)
mech = any(not v for k, v in ok.items() if 'mechanism row' in k)
rss_bad = any(not v for k, v in ok.items() if 'RssAnon falls' in k)
invalid = not ok.get('sstable count 20 at every reading', False) or not ok.get('format BIG: 20 -big-Summary.db', False) or not ok.get('no compaction other than index summary redistribution', False)
if invalid:
    v = 'Invalid'
elif row2 or mech:
    v = 'Refuted (%s)' % ('row 2' if row2 else 'mechanism row')
elif rss_bad:
    v = 'Refuted (row 3: RssAnon does not follow)'
elif all(ok.values()):
    eff = 'caps only on some paths (bypass)' if ok.get('bypass (a): baseline T >> cap 64 with no run') and ok.get('C=8 overshoot: T ~ sumF > 8, R258 < 0, no keep') else 'caps'
    v = f'Confirmed -- Effect: {eff}'
else:
    v = 'Not confirmed (failed: %s)' % ', '.join(k for k, x in ok.items() if not x)
print('missed sub-predictions:', [k for k, x in miss.items() if not x] or 'none')
print('VERDICT:', v)
