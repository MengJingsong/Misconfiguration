#!/usr/bin/env python3
"""Independent self-check of run 1, networking_cache_size-allocateMoreChunks-memoryUsageThreshold (results §5).
usage: selfcheck.py [<run dir>, default ~/stage4-logs/ncs/run1]
Uses none of the run script's code. Per value: the knob from cassandra.yaml and the startup line in system.log; the phase
times from session.log ("PHASE <name>" lines, local time); P from the 'made' lines of bm.trace (8 MiB each, by their ms);
the counters from the 'dump' line nearest each phase time; O, the java.nio direct reading and the chunk-cache size from
samples.csv; S from ss/<scenario>.txt (server Send-Q + client Recv-Q). Arm L from its own folder. Exit 1 if any check fails."""
import csv, glob, os, re, statistics, sys, time

RUN = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/stage4-logs/ncs/run1')
MIB = 1048576
FRAME = 131070
fails = 0
table = []


def ck(desc, cond, detail=''):
    global fails
    if not cond:
        fails += 1
    print(f'{"ok  " if cond else "FAIL"} {desc}{" — " + detail if detail else ""}')
    return cond


def load(d):
    made = [(int(m.group(2)) / 1000, int(m.group(1))) for m in re.finditer(r'^made n=(\d+) ms=(\d+)', open(f'{d}/bm.trace').read(), re.M)]
    dumps = []
    for l in open(f'{d}/bm.trace'):
        if l.startswith('dump '):
            kv = {k: int(v) for k, v in re.findall(r'(\w+)=(-?\d+)', l)}
            dumps.append((kv['ms'] / 1000, kv))
    smp = []
    for r in csv.DictReader(open(f'{d}/samples.csv')):
        if r['t1_ms'] != 'ERR':
            smp.append({k: int(v) for k, v in r.items()})
    phases = {}
    for m in re.finditer(r'^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] PHASE (\S+):', open(f'{d}/session.log').read(), re.M):
        phases[m.group(2)] = time.mktime(time.strptime(m.group(1), '%Y-%m-%d %H:%M:%S'))
    return made, dumps, smp, phases


def P_at(made, t):
    return 8 * MIB * max([n for (tm, n) in made if tm <= t] or [0])


def dump_at(dumps, t):
    # t is a session-log second (truncated); the phase's own dump came within the second before the line, and the counters are
    # flat during an idle or a hold, so the last dump at or before t is that phase's (t + 1 can reach into the next scenario)
    before = [kv for tm, kv in dumps if tm <= t]
    return before[-1] if before else {}


def window(smp, t0, t1):
    return [r for r in smp if t0 <= r['t0_ms'] / 1000 <= t1]


def S_of(d, name):
    txt = open(f'{d}/ss/{name}.txt').read()
    srv, cli = txt.split('----client----')
    sq = sum(int(m.group(2)) for m in re.finditer(r'^\s*(\d+)\s+(\d+)\s+\S+:9042\s', srv, re.M))
    rq = sum(int(m.group(1)) for m in re.finditer(r'^\s*(\d+)\s+(\d+)\s+\S+\s+\S+:9042\s*$', cli, re.M))
    return sq + rq


directs_B, directs_after = {}, {}
for v in ('16', '32', '64', '100', 'default'):
    d = os.path.join(RUN, f'value-{v}')
    if not os.path.isdir(d):
        ck(f'value {v}: folder present', False)
        continue
    yaml = open(f'{d}/cassandra.yaml').read()
    knob = re.findall(r'^networking_cache_size:\s*(\d+)MiB', yaml, re.M)
    T = int(knob[-1]) * MIB if knob else 128 * MIB
    Tq = (T // (8 * MIB)) * 8 * MIB
    ck(f'value {v}: yaml knob', (v == 'default' and not knob) or (knob and int(knob[-1]) == int(v)))
    sl = open(f'{d}/system.log').read()
    ck(f'value {v}: startup line names {T // MIB}.000MiB for networking', f'and {T // MIB}.000MiB for networking' in sl)
    made, dumps, smp, ph = load(d)
    ck(f'value {v}: Capacity gauge = T in every sample', smp and all(r['capacity'] == T for r in smp))
    ck(f'value {v}: P never above T\' ({Tq}) in the lifetime', max(n for _, n in made) * 8 * MIB <= Tq, str(max(n for _, n in made)))
    t_idle_end = ph['idle']
    idle = window(smp, t_idle_end - 31, t_idle_end)
    base = statistics.median(r['direct_used'] - r['cc_size'] for r in idle)
    P_idle = P_at(made, t_idle_end)
    ck(f'value {v}: idle P = 8 MiB, O = 0', P_idle == 8 * MIB and all(r['overflow'] == 0 for r in idle), f'P {P_idle}')
    res = {}
    for name, R in (('A', 4), ('M', 48), ('B', 192)):
        t0, tp, ta = ph[f'{name}-before'], ph[f'{name}-peak'], ph[f'{name}-after']
        w = window(smp, t0, tp + 1)
        d0, dp, da = dump_at(dumps, t0), dump_at(dumps, tp), dump_at(dumps, ta)
        o_peak = max(r['overflow'] for r in w)
        rise = max(r['direct_used'] - r['cc_size'] for r in w) - base
        S = S_of(d, name)
        res[name] = dict(P=P_at(made, tp), O=o_peak, S=S, refuse=dp['refuse'] - d0['refuse'], n_o=dp['overflow'] - d0['overflow'],
                         ob=dp['overflow_bytes'] - d0['overflow_bytes'], held=dp['encoded'] - dp['freed'], held_after=da['encoded'] - da['freed'],
                         full=dp['payload_full'] - d0['payload_full'], rise=rise)
    a, m, b = res['A'], res['M'], res['B']
    ck(f'value {v} A: no refusal, O = 0, P <= 16 MiB, all 32 full frames framed', a['refuse'] == 0 and a['O'] == 0 and a['P'] <= 16 * MIB and a['full'] == 32, str(a))
    if T <= 32 * MIB:
        ck(f'value {v} M: P = T\' and P + O_peak in [D - S - 1 MiB, D + 1 MiB]', m['P'] == Tq and 48 * MIB - m['S'] - MIB <= m['P'] + m['O'] <= 49 * MIB, str(m))
    else:
        ck(f'value {v} M: P in [48, 56] MiB, O = 0, no refusal (not T\')', 48 * MIB <= m['P'] <= 56 * MIB and m['O'] == 0 and m['refuse'] == 0, str(m))
    ck(f'value {v} B: P = T\' exactly', b['P'] == Tq, f'{b["P"]} vs {Tq}')
    ck(f'value {v} B: P + O_peak in [D - S - 1 MiB, D + 1 MiB]', 192 * MIB - b['S'] - MIB <= b['P'] + b['O'] <= 193 * MIB, f'P+O {b["P"] + b["O"]} S {b["S"]}')
    ck(f'value {v} B: refusals > 0; overflow bytes = 131,070 x full + < 1 KiB per response', b['refuse'] > 0 and (b['ob'] - FRAME * (b['ob'] // FRAME)) <= 192 * 1024,
       f'refuse {b["refuse"]} n_o {b["n_o"]} bytes {b["ob"]}')
    ck(f'value {v} B: held frames > 64 at the peak, 0 after the close', b['held'] > 64 and b['held_after'] == 0, f'{b["held"]} {b["held_after"]}')
    ck(f'value {v} B: direct rise in [D - S - 10 MiB, D + 10 MiB]', 192 * MIB - b['S'] - 10 * MIB <= b['rise'] <= 202 * MIB, f'{b["rise"] / MIB:.1f} MiB')
    ta = ph['after-B']
    aft = window(smp, ta - 15, ta + 1)
    rise_after = statistics.median(r['direct_used'] - r['cc_size'] for r in aft) - base
    o_after = aft[-1]['overflow'] if aft else None
    ck(f'value {v} after B: O within 64 KiB of zero (−6 B per overflowed full frame)', o_after is not None and -64 * 1024 <= o_after <= 0, str(o_after))
    ck(f'value {v} after B: direct rise = T\' − P_idle ± 2 MiB ({(Tq - P_idle) / MIB:.0f} MiB)', abs(rise_after - (Tq - P_idle)) <= 2 * MIB, f'{rise_after / MIB:.2f} MiB')
    directs_B[v], directs_after[v] = b['rise'], rise_after
    table.append((v, T // MIB, Tq // MIB, a['P'] // MIB, m['P'] / MIB, m['O'] / MIB, b['P'] / MIB, b['O'] / MIB, b['S'] / MIB, b['refuse'], b['n_o'],
                  round(b['rise'] / MIB, 1), round(rise_after / MIB, 1), o_after))
if len(directs_B) == 5:
    spread = (max(directs_B.values()) - min(directs_B.values())) / MIB
    ck(f'flat: B direct rise spread across the five values <= 12 MiB', spread <= 12, f'{spread:.1f} MiB')

dL = os.path.join(RUN, 'leak')
if os.path.isdir(dL):
    made, dumps, smp, ph = load(dL)
    t0, t1, t2 = ph['L-idle'], ph['L-after-30s'], ph['L-after-GC']
    r0, r1, r2 = window(smp, t0 - 2, t0)[-1], window(smp, t1 - 2, t1)[-1], window(smp, t2 - 2, t2)[-1]
    d0, d1 = dump_at(dumps, t0), dump_at(dumps, t1)
    ovf = r1['overflow'] - r0['overflow']
    pooled = (r1['used'] - r1['overflow']) - (r0['used'] - r0['overflow'])
    short = (d1['ovfadd_bytes'] - d0['ovfadd_bytes']) - (d1['ovfsub_bytes'] - d0['ovfsub_bytes'])
    print(f'arm L: OverflowSize residual {ovf}; UsedSize-OverflowSize residual {pooled}; subtracted short of added by {short}; '
          f'direct {r0["direct_used"]} -> {r1["direct_used"]} -> {r2["direct_used"]}; OverflowSize after GC {r2["overflow"]}')
    ck('arm L: OverflowSize residual 58,724,288 B', ovf == 58724288)
    ck('arm L: UsedSize - OverflowSize residual 5,373,952 ± 131,072 B', abs(pooled - 5373952) <= 64 * 2048)
    ck('arm L: subtracted short of added by 58,724,288 B', short == 58724288)
    ck('arm L: direct falls after GC.run while OverflowSize does not', r2['direct_used'] < r1['direct_used'] and r2['overflow'] == r1['overflow'])

print('\nvalue | T MiB | T\' MiB | A P | M P | M O | B P | B O | B S | B refuse | B n_o | B direct rise | after rise | after O  (MiB unless noted)')
for r in table:
    print(' | '.join(str(x) for x in r))
print(f'\n{fails} check(s) failed')
sys.exit(1 if fails else 0)
