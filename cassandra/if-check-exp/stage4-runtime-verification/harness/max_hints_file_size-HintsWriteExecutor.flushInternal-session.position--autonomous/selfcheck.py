#!/usr/bin/env python3
"""Independent self-check for max_hints_file_size-HintsWriteExecutor.flushInternal-session.position--autonomous.
Re-parses the RAW logs (not the run scripts' EXPECTED lines or the test's own checks) and recomputes the amended B2f / B3f
relations. usage: selfcheck.py <run1 log dir>   (the folder holding unit/ and L1/ L16/ L128/ CTRL/). Prints a report.
"""
import collections, csv, math, os, re, statistics, sys

R = sys.argv[1]
MIB = 1 << 20
res = []


def say(s=''):
    print(s)


def verdict(name, cond, detail=''):
    res.append((name, bool(cond)))
    say(f'  [{"ok " if cond else "NO "}] {name} {detail}')


# ---------------------------------------------------------------- unit tier
say('== UNIT ==')
H = open(R + '/unit/harness.out').read().splitlines()
TR = open(R + '/unit/mh.trace').read().splitlines()
roll = collections.defaultdict(list)       # host -> [(position, max)]
sess = collections.defaultdict(list)       # host -> [size]
decide = []
for l in TR:
    m = re.match(r'roll host=(\S+) position=(\d+) max=(\d+) ms=(\d+)$', l)
    if m:
        roll[m.group(1)].append((int(m.group(2)), int(m.group(3)), int(m.group(4)))); continue
    m = re.match(r'sessclose host=(\S+) size=(\d+) ms=(\d+)$', l)
    if m:
        sess[m.group(1)].append(int(m.group(2))); continue
    m = re.match(r'decide ep=(\S+) result=(true|false) checked=(-?\d+) limit=(-?\d+) ms=(\d+)$', l)
    if m:
        decide.append((m.group(1), m.group(2) == 'true', int(m.group(3)), int(m.group(4)), int(m.group(5))))
runs = []
for l in H:
    if l.startswith('STAGE4 run '):
        d = dict(re.findall(r'(\w+)=(\S+)', l))
        d['name'] = re.search(r'name=(.*?) counted=', l).group(1)
        runs.append(d)
say(f'runs parsed: {len(runs)}; hosts with roll lines: {len(roll)}; trace lines: {len(TR)}')
totals = {}
for d in runs:
    host, L, e = d['host'], int(d['L']), int(d['e'])
    rl = roll.get(host, [])
    # independent recomputation of the file count and T from the trace alone
    nroll = len(rl)
    last_sess = sess[host][-1] if sess[host] else 0
    open_file = last_sess if last_sess < L else 0     # a rolled file's last session ends at >= L
    T_trace = sum(p for p, _, _ in rl) + open_file
    # a rolled file's final length is the roll position; the open file's is the last session size after the final roll
    files_trace = nroll + 1
    ok_pos = all(L <= p < L + e and mx == L for p, mx, _ in rl)
    # the last session after the final roll belongs to the open file only when nothing closed after it
    T_harness = int(d['T'])
    verdict(f"{d['name']}: roll lines={nroll} equal files with length >= L ({d['filesGeL']})", nroll == int(d['filesGeL']))
    verdict(f"{d['name']}: every roll at position in [L, L+e) with max=L", ok_pos)
    # T from the trace: the open file's final size is the last sessclose size when its host never rolled again
    sizes_after = sess[host]
    verdict(f"{d['name']}: T (harness {T_harness}) == sum(roll positions) + open file ({open_file}) from the trace",
            T_trace == T_harness, f'trace={T_trace}')
    nlo = math.ceil(T_harness / (L + e)); nhi = T_harness // L + 1
    verdict(f"{d['name']}: files {d['files']} in [{nlo},{nhi}]", nlo <= int(d['files']) <= nhi)
    if d['counted'] == 'true':
        totals[d['name']] = T_harness
c_ref = [int(d['T']) for d in runs if d['counted'] == 'true' and d['L'] == str(128 * MIB) and d['payload'] == '16384']
c_all = [int(d['T']) for d in runs if d['counted'] == 'true' and d['payload'] == '16384']
verdict('totals across L and reps within 0.1%', max(c_all) - min(c_all) <= min(c_all) / 1000, f'min={min(c_all)} max={max(c_all)} spread={max(c_all) - min(c_all)}')
deltas = [int(d['directDelta']) for d in runs if d['counted'] == 'true']
verdict('direct memory deltas within 1 MiB of zero, spread <= 1 MiB', max(abs(x) for x in deltas) <= MIB and max(deltas) - min(deltas) <= MIB, f'deltas min={min(deltas)} max={max(deltas)}')
for d in runs:
    if d['counted'] == 'true' and d['payload'] == '16384':
        pass
byL = collections.defaultdict(list)
for d in runs:
    if d['counted'] == 'true' and d['payload'] == '16384':
        byL[int(d['L']) // MIB].append(int(d['files']))
say('  files by L (3 reps): ' + str(dict(byL)))
verdict('files nominally 64/17/5/1 (+-1)', all(abs(v - n) <= 1 for L, n in ((1, 64), (4, 17), (16, 5), (128, 1)) for v in byL[L]))
verdict('files scale inversely with L (L=1 > L=4 > L=16 > L=128)', byL[1][0] > byL[4][0] > byL[16][0] > byL[128][0])
# control
ctl = [l for l in H if l.startswith('STAGE4 control ')]
say('  control line: ' + (ctl[0][:260] if ctl else 'MISSING'))
if ctl:
    c = dict(re.findall(r'(\w+)=(\S+)', ctl[0]))
    cap = int(c['cap']); Tstop = int(c['Tstop']); e = int(c['e'])
    ep = [x for x in decide if x[3] == cap]
    f = [x for x in ep if not x[1]]; t = [x for x in ep if x[1]]
    verdict('control: decide lines with limit=16 MiB exist (false and true)', f and t, f'false={len(f)} true={len(t)}')
    verdict('control: every false has checked > cap', all(x[2] > cap for x in f))
    verdict('control: every true has checked <= cap', all(x[2] <= cap for x in t))
    verdict('control: Tstop in (cap, cap + one batch + 200]', cap < Tstop <= cap + 64 * e + 200, f'Tstop={Tstop} over={Tstop - cap}')
    verdict('control: the largest true-checked operand is the one before the first refusal', max(x[2] for x in t) <= cap and min(x[2] for x in f) == Tstop, f'maxTrue={max(x[2] for x in t)} minFalse={min(x[2] for x in f)}')
    verdict('control: the control host never rolled by the file limit', len(roll.get(c['host'], [])) == 0)

# ---------------------------------------------------------------- cluster tier
say()
say('== CLUSTER ==')
arms = {}
for label, L, cap in (('L1', 1, 0), ('L16', 16, 0), ('L128', 128, 0), ('CTRL', 128, 100)):
    d = f'{R}/{label}'
    if not os.path.isdir(d):
        say(f'{label}: no folder'); continue
    A = {'label': label, 'L': L * MIB, 'cap': cap * MIB}
    files = [(l.split()[0], int(l.split()[1])) for l in open(d + '/files.txt') if l.strip()]
    A['files'] = files
    A['T'] = sum(s for _, s in files)
    du = list(csv.DictReader(open(d + '/du.csv')))
    A['du_last'] = int(du[-1]['bytes']); A['du_files_last'] = int(du[-1]['files']); A['du_max'] = max(int(r['bytes']) for r in du)
    # growth over the last 60 s of the sampler
    tl = int(du[-1]['ms'])
    last60 = [int(r['bytes']) for r in du if int(r['ms']) >= tl - 60000]
    A['growth60'] = last60[-1] - last60[0]
    last3 = [int(r['bytes']) for r in du if int(r['ms']) >= tl - 3000]
    A['growth3'] = last3[-1] - last3[0]
    mem = list(csv.DictReader(open(d + '/mem.csv')))
    A['direct_max'] = max(int(r['direct_used']) for r in mem); A['direct_min'] = min(int(r['direct_used']) for r in mem)
    A['rss_end'] = int(mem[-1]['rss_anon']); A['rss_max'] = max(int(r['rss_anon']) for r in mem)
    A['roll'] = []; A['decide'] = []; A['sess'] = 0
    for l in open(d + '/mh.trace'):
        m = re.match(r'roll host=(\S+) position=(\d+) max=(\d+) ms=(\d+)$', l)
        if m:
            A['roll'].append((int(m.group(2)), int(m.group(3)), int(m.group(4)))); continue
        m = re.match(r'decide ep=(\S+) result=(true|false) checked=(-?\d+) limit=(-?\d+) ms=(\d+)$', l)
        if m:
            A['decide'].append((m.group(1), m.group(2) == 'true', int(m.group(3)), int(m.group(4)), int(m.group(5)))); continue
        if l.startswith('sessclose '):
            A['sess'] += 1
    ctr = open(d + '/counters.txt').read()
    A['totalhints'] = int(re.search(r'TotalHints\|Count\|(\d+)', ctr).group(1))
    keys = collections.Counter(l.strip().split(',')[2] for l in open(d + '/keys.csv') if l.strip())
    A['rows'] = dict(keys)
    arms[label] = A
for label, A in arms.items():
    L, e_avg = A['L'], None
    n = len(A['files'])
    e_avg = A['T'] / A['totalhints']
    say(f'{label}: files={n} T={A["T"]} du_last={A["du_last"]} du_max={A["du_max"]} hints={A["totalhints"]} e_avg={e_avg:.1f} '
        f'roll={len(A["roll"])} rows={A["rows"]} growth60={A["growth60"]} direct_max={A["direct_max"]} rss_end={A["rss_end"]}')
    verdict(f'{label}: writer rows ok=400000, err=0', A['rows'].get('ok') == 400000 and A['rows'].get('err', 0) == 0)
    if label != 'CTRL':
        verdict(f'{label}: TotalHints == 400000', A['totalhints'] == 400000)
    else:
        ntrue = sum(1 for x in A['decide'] if x[1])
        verdict(f'{label}: TotalHints ({A["totalhints"]}) == number of decide true lines ({ntrue}): only permitted hints are stored', A['totalhints'] == ntrue)
    verdict(f'{label}: sampler last du == files.txt total', A['du_last'] == A['T'])
    if label != 'CTRL':
        closed = sorted(A['files'])[:-1]
        e_hi = max(s - L for _, s in closed) + 1 if closed else 0
        sizes = [s for _, s in sorted(A['files'])]
        ge = sum(1 for s in sizes if s >= L)
        verdict(f'{label}: roll lines ({len(A["roll"])}) == files with length >= L ({ge})', len(A['roll']) == ge)
        verdict(f'{label}: every roll position in [L, L+4 KiB) with max=L', all(L <= p < L + 4096 and mx == L for p, mx, _ in A['roll']))
        verdict(f'{label}: every closed file in [L, L+4 KiB)', all(L <= s < L + 4096 for s in sizes[:-1]), f'min={min(sizes[:-1]) if len(sizes) > 1 else None} max={max(sizes[:-1]) if len(sizes) > 1 else None}')
        verdict(f'{label}: last file < L + 4 KiB', sizes[-1] < L + 4096, f'last={sizes[-1]}')
        e = 2200
        nlo = math.ceil(A['T'] / (L + e)); nhi = A['T'] // L + 1
        verdict(f'{label}: files {n} in [ceil(T/(L+e)), T//L+1] = [{nlo},{nhi}] (e=2200)', nlo <= n <= nhi)
    else:
        L = 128 * MIB; cap = A['cap']
        f = [x for x in A['decide'] if not x[1]]; t = [x for x in A['decide'] if x[1]]
        verdict('CTRL: T_end in (100 MiB, 108 MiB]', cap < A['T'] <= cap + 8 * MIB, f'T={A["T"]} over={A["T"] - cap}')
        verdict('CTRL: some decide false, every false with checked > cap and limit == cap', f and all(x[2] > cap and x[3] == cap for x in f), f'false={len(f)}')
        verdict('CTRL: every decide true has checked <= cap (or -1 before any operand)', all(x[2] <= cap for x in t), f'true={len(t)}')
        minf = min(y[4] for y in f) if f else None
        verdict('CTRL: no true after the first false', (not any(x[4] > minf for x in t)) if f else False)
        verdict('CTRL: no roll by the file limit (128 MiB not reached)', len(A['roll']) == 0)
    if label == 'CTRL':
        verdict('CTRL: zero growth over the last 60 s', A['growth60'] == 0, f'growth60={A["growth60"]}')
    else:
        verdict(f'{label}: no growth over the last 3 s (writer done, last flush landed)', A['growth3'] == 0, f'growth3={A["growth3"]}')
if all(k in arms for k in ('L1', 'L16', 'L128')):
    Ts = [arms[k]['T'] for k in ('L1', 'L16', 'L128')]
    verdict('T equal across L=1,16,128 within 1%', (max(Ts) - min(Ts)) <= 0.01 * min(Ts), f'T={Ts} spread={(max(Ts) - min(Ts)) / min(Ts) * 100:.3f}%')
    dm = [arms[k]['direct_max'] for k in ('L1', 'L16', 'L128')]
    verdict('direct MemoryUsed max across L within 10 MiB', max(dm) - min(dm) <= 10 * MIB, f'max per arm={dm}')
    rs = [arms[k]['rss_end'] for k in ('L1', 'L16', 'L128')]
    verdict('RssAnon at the end across L within 128 MiB', max(rs) - min(rs) <= 128 * MIB, f'end per arm={rs}')
    nf = [len(arms[k]['files']) for k in ('L1', 'L16', 'L128')]
    verdict('file counts fall with L (L=1 > L=16 > L=128)', nf[0] > nf[1] > nf[2], f'files={nf}')
say()
say(f'SELFCHECK SUMMARY: {sum(1 for _, c in res if c)} ok, {sum(1 for _, c in res if not c)} NO')
for n, c in res:
    if not c:
        say('  NO: ' + n)
