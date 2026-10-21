#!/usr/bin/env python3
"""Independent self-check of run 1 for WRITE_BUFFER_SIZE-append-remaining--autonomous (results §5).
usage: selfcheck.py <logs root, e.g. ~/stage4-logs/wbs/run1>
Re-parses the raw files only — unit: test.out (STAGE4 append/case lines, not the check lines); cluster: the per-start
wbs-<n>.trace, samples-jmx-*.csv, hints-*.csv, keys-*.csv of each lifetime, plus the arm time windows (t0/t_w/t1) and
the trace file name from arms.json (timing only; no reading of arms.json is used). Recomputes every B2f/B3f relation the conclusion uses and compares with what the run
scripts printed (summary.txt). Prints "ok"/"FAIL" per check and a total; exit 0 even on FAIL (the AI judges)."""
import json, os, re, statistics, sys

ROOT = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/stage4-logs/wbs/run1')
KIB, MIB, GIB = 1024, 1 << 20, 1 << 30
CAP = 256 * KIB
SLAB = 32 * MIB
res = {'ok': 0, 'FAIL': 0}


def chk(name, cond, detail=''):
    k = 'ok' if cond else 'FAIL'
    res[k] += 1
    print(f'{k:4} {name}  {detail}')


# ------------------------------------------------------------------ unit
def unit():
    f = f'{ROOT}/unit/test.out'
    if not os.path.exists(f):
        print('no unit test.out'); return
    appends, cases = {}, {}
    for l in open(f):
        m = re.match(r'STAGE4 append (\S+(?: \S+)*?) S=(\d+) rep=(\d+) i=(\d+) alloc=(-?\d+) remaining=(\d+) fileLen=(\d+)', l)
        if m:
            key = (m.group(1), int(m.group(2)), int(m.group(3)))
            appends.setdefault(key, []).append((int(m.group(5)), int(m.group(6)), int(m.group(7))))
            continue
        m = re.match(r'STAGE4 case (\S+) S=(\d+) rep=(\d+) (.*)', l)
        if m:
            d = dict(kv.split('=', 1) for kv in m.group(4).split())
            cases[(m.group(1), int(m.group(2)), int(m.group(3)))] = d
    print(f'unit: {len(cases)} cases, {sum(len(v) for v in appends.values())} measured appends')
    for key, d in sorted(cases.items()):
        v, s, rep = key
        a = appends.get(key, [])
        total = int(d['totalSize']); cap = int(d['capacity']); n = int(d['n']); cnt = n + int(d['warmup'])
        allocs = [x[0] for x in a]
        tag = f'{v} S={s} rep={rep}'
        chk(f'unit {tag}: {n} measured appends found', len(a) == n)
        chk(f'unit {tag}: written in full (fileAfterClose = header + {cnt} x totalSize)',
            int(d['fileAfterClose']) == int(d['header']) + cnt * total and int(d['bytesWritten']) == cnt * total,
            f"{d['fileAfterClose']} vs {int(d['header']) + cnt * total}")
        chk(f'unit {tag}: read back {cnt} hints, none of another size', int(d['readBack']) == cnt and d['readBadSize'] == '0')
        # file growth from the per-append file lengths: a large entry grows the file by exactly totalSize at each append
        lens = [x[2] for x in a]
        if total > cap:
            steps = [lens[i] - lens[i - 1] for i in range(1, len(lens))]
            chk(f'unit {tag}: file grows by totalSize at every append (direct write)', all(x == total for x in steps), str(set(steps)))
            chk(f'unit {tag}: buffer left empty after every append (remaining = {cap})', all(x[1] == cap for x in a))
        else:
            k = cap // total
            steps = [lens[i] - lens[i - 1] for i in range(1, len(lens)) if lens[i] != lens[i - 1]]
            chk(f'unit {tag}: file grows only in whole buffers of {k} entries', all(x == k * total for x in steps), str(set(steps)))
        if v.startswith('H') and total > cap:
            chk(f'unit {tag}: append(Hint) allocates >= S+12 per append (min {min(allocs)})', min(allocs) >= s + 12)
            chk(f'unit {tag}: ... and about totalSize: max - totalSize = {max(allocs) - total} B (< 8 KiB)', max(allocs) - total < 8 * KIB)
        elif v.startswith('H'):
            chk(f'unit {tag}: append(Hint) small and independent of S (max {max(allocs)} < 8 KiB)', max(allocs) < 8 * KIB)
        else:
            chk(f'unit {tag}: append(ByteBuffer) ~0 (max {max(allocs)} < 8 KiB)', max(allocs) < 8 * KIB)
    # threshold moves with the buffer: 100 KiB small at 256 KiB, >= S+12 at 64 KiB
    for rep in (1, 2):
        a256 = [x[0] for x in appends.get(('H', 102400, rep), [])]
        a64 = [x[0] for x in appends.get(('H-buf65536', 102400, rep), [])]
        if a256 and a64:
            chk(f'unit rep {rep}: 100 KiB below the 256 KiB threshold ({max(a256)} B) and above the 64 KiB one ({min(a64)} B)',
                max(a256) < 8 * KIB and min(a64) >= 102400 + 12)
    ctl = [l.strip() for l in open(f) if l.startswith('STAGE4 check control')]
    for l in ctl:
        print('     (control line) ' + l)
    def ctl_ok(name):
        return any(l.startswith(f'STAGE4 check {name} ') and l.endswith(' ok') for l in ctl)
    chk('unit control: 600 KiB refused with "maximum size is 524288", 100 KiB admitted, capacity/2 admitted, +1 refused',
        ctl_ok('control_allocate_600KiB_refused') and ctl_ok('control_allocate_100KiB_admitted')
        and ctl_ok('control_allocate_at_capacity/2_admitted') and ctl_ok('control_allocate_at_capacity/2+1_refused'))
    chk('unit control as filed (400 KiB refused) fails as derived in D1 (409,612 B < 524,288 B)',
        any(l.startswith('STAGE4 check control_allocate_400KiB_refused(filed)') and l.endswith('MISMATCH') for l in ctl))


# ------------------------------------------------------------------ cluster
def csv(path):
    rows = []
    with open(path) as f:
        hdr = f.readline().strip().split(',')
        for l in f:
            p = l.strip().split(',')
            if len(p) == len(hdr) and p[0].isdigit():
                rows.append(dict(zip(hdr, p)))
    return rows


def lifetime(name):
    d = f'{ROOT}/cluster/{name}'
    if not os.path.exists(f'{d}/arms.json'):
        return None
    arms = json.load(open(f'{d}/arms.json'))
    windows = [{k: a[k] for k in ('name', 'size', 't0', 't1', 't_w', 'trace_file') if k in a} for a in arms]
    import glob

    def merged(pattern):
        rows = []
        for fn in glob.glob(f'{d}/{pattern}'):
            rows += csv(fn)
        return sorted(rows, key=lambda r: int(r['ms']))
    jmx = merged('samples-jmx-*.csv')
    hints = merged('hints-*.csv')
    out = {}
    for w in windows:
        if w['name'] == 'control':
            continue
        t0, t1 = w['t0'], w['t1']
        trace = open(f"{d}/{w['trace_file']}", errors='replace').read().splitlines()
        # baseline: median direct_used of the samples in the 14 s before the arm (the run's GC + 10 s window sits there)
        pre = [float(r['direct_used']) for r in jmx if t0 - 14000 <= int(r['ms']) < t0 and r['direct_used'] not in ('', 'ERR')]
        base_direct = statistics.median(pre) if pre else None
        kf = f'{d}/keys-{w["name"]}.csv'
        keys = [l.strip().split(',') for l in open(kf)] if os.path.exists(kf) else []
        written = len(keys); okw = sum(1 for k in keys if k[3] == 'ok')
        app = []
        wr_direct = 0
        created = 0
        waiting = 0
        refuse = []
        for l in trace:
            m = re.search(r' ms=(\d+)', l)
            ms = int(m.group(1)) if m else None
            if l.startswith('created=') and ms is not None and ms <= t1:
                created += 1
            if ms is None or not (t0 <= ms <= t1):
                continue
            if l.startswith('app '):
                app.append(int(re.search(r'sz=(\d+)', l).group(1)))
            elif l.startswith('wr ') and 'buf=false' in l:
                wr_direct += 1
            elif l.startswith('waiting'):
                waiting += 1
            elif l.startswith('refuse'):
                refuse.append((int(re.search(r'checked=(\d+)', l).group(1)), int(re.search(r'limit=(\d+)', l).group(1))))
        hw = [r for r in hints if t0 <= int(r['ms']) <= t1]
        end_bytes = int(hw[-1]['hints_bytes']) if hw else None
        files = int(hw[-1]['hints_files']) if hw else None
        largest = max(int(r['largest_file']) for r in hw) if hw else None
        jw = [r for r in jmx if t0 <= int(r['ms']) <= t1 and r['direct_used'] not in ('', 'ERR')]
        peak = max(float(r['direct_used']) for r in jw) if jw else None
        th = [float(r['total_hints']) for r in jw if r['total_hints'] not in ('', 'ERR')]
        late = None
        if 't_w' in w and hw:
            cut = t0 + 0.6 * (w['t_w'] - t0)
            lv = [int(r['hints_bytes']) for r in hints if cut <= int(r['ms']) <= w['t_w']]
            late = max(lv) - min(lv) if lv else None
        out[w['name']] = dict(size=w['size'], written=written, ok=okw, app=len(app), app_over=sum(1 for x in app if x > CAP),
                              wr_direct=wr_direct, created=created, waiting=waiting, refuse=refuse, end_bytes=end_bytes,
                              files=files, largest=largest, peak=peak, base=base_direct,
                              th_delta=(th[-1] - th[0]) if len(th) > 1 else None, late=late)
    return out


def cluster():
    main = lifetime('main')
    if not main:
        print('no cluster main'); return
    mhb = {}
    for dn in sorted(os.listdir(f'{ROOT}/cluster')):
        if dn.startswith('mhb1-'):
            r = lifetime(dn)
            if r:
                mhb.update({f'{dn}/{k}': v for k, v in r.items()})
    ratios = {}
    for n, a in main.items():
        print(f'     {n}: {json.dumps({k: v for k, v in a.items() if k != "refuse"})} refuse={len(a["refuse"])}')
        if n.startswith('limit'):
            lim = 64 * MIB
            chk(f'cluster {n}: disk ends in [64, 224] MiB ({a["end_bytes"] / MIB:.1f} MiB)', lim <= a['end_bytes'] <= lim + 128 * MIB + SLAB)
            chk(f'cluster {n}: growth in the last 40 % of the write window < 32 MiB ({(a["late"] or 0) / MIB:.2f})',
                a['late'] is not None and a['late'] < SLAB)
            chk(f'cluster {n}: refusals ({len(a["refuse"])}), every operand above the limit',
                len(a['refuse']) > 0 and all(c > l for c, l in a['refuse']))
            chk(f'cluster {n}: every write succeeded ({a["ok"]}/{a["written"]})', a['ok'] == a['written'] > 0)
            continue
        vals = a['written'] * a['size']
        ratios[n] = a['end_bytes'] / vals
        chk(f'cluster {n}: hints on disk / values written = {ratios[n]:.4f} in [0.95, 1.10]', 0.95 <= ratios[n] <= 1.10)
        chk(f'cluster {n}: {a["files"]} files, largest {a["largest"]} >= 128 MiB, count 14-18',
            a['largest'] >= 128 * MIB and 14 <= a['files'] <= 18)
        chk(f'cluster {n}: entries appended {a["app"]} = keys written {a["written"]}', a['app'] == a['written'])
        if a['size'] > CAP:
            chk(f'cluster {n}: every entry > 256 KiB bypasses the buffer: over-cap {a["app_over"]}, direct writes {a["wr_direct"]}',
                a['app_over'] == a['written'] == a['wr_direct'])
        else:
            chk(f'cluster {n}: no entry bypasses ({a["app_over"]}, {a["wr_direct"]})', a['app_over'] == 0 == a['wr_direct'])
        att = a['created'] * SLAB + CAP
        chk(f'cluster {n}: attributable {att / MIB:.2f} MiB in [32.25, 96.25] MiB and >= 25 MiB', SLAB + CAP <= att <= 3 * SLAB + CAP)
        chk(f'cluster {n}: direct peak above baseline by {(a["peak"] - a["base"]) / MIB:.2f} MiB (not within 1 MiB with one slab)',
            not (abs(a['peak'] - a['base']) <= MIB and a['created'] <= 1))
    if ratios:
        r = [v for k, v in ratios.items()]
        chk(f'cluster X1: du ratios within 5 % across sizes ({[round(x, 4) for x in r]})', max(r) / min(r) <= 1.05)
    hint_arms = [a for n, a in main.items() if not n.startswith('limit')]
    lim_arms = [a for n, a in main.items() if n.startswith('limit')]
    m1 = [a for a in hint_arms if a['size'] == MIB]
    if lim_arms and m1:
        chk('cluster X2: the limit arms end far below the limit-0 1 MiB arms',
            max(a['end_bytes'] for a in lim_arms) < min(a['end_bytes'] for a in m1) / 4)
    for n, a in mhb.items():
        print(f'     {n}: {json.dumps({k: v for k, v in a.items() if k != "refuse"})}')
        chk(f'cluster {n}: one slab only (created {a["created"]}): attributable <= 32.25 MiB', a['created'] * SLAB + CAP <= SLAB + CAP)
    if mhb and hint_arms:
        d_def = max(a['peak'] - a['base'] for a in hint_arms)
        d_m1 = max(a['peak'] - a['base'] for a in mhb.values())
        chk(f'cluster X3 (R1): MAX_HINT_BUFFERS=1 peak delta {d_m1 / MIB:.2f} MiB < default {d_def / MIB:.2f} MiB', d_m1 < d_def)
        chk('cluster X4: slabs MAX_HINT_BUFFERS=1 < default', max(a['created'] for a in mhb.values()) < max(a['created'] for a in hint_arms))
    # compare with the run script's own figures
    for dn in ['main'] + [x for x in sorted(os.listdir(f'{ROOT}/cluster')) if x.startswith('mhb1-')]:
        p = f'{ROOT}/cluster/{dn}/arms.json'
        if not os.path.exists(p):
            continue
        for a in json.load(open(p)):
            if a['name'] == 'control':
                continue
            mine = (main if dn == 'main' else {k.split('/', 1)[1]: v for k, v in mhb.items() if k.startswith(dn + '/')}).get(a['name'])
            if not mine:
                continue
            chk(f'agree {dn}/{a["name"]}: written {mine["written"]}={a["written"]}, app {mine["app"]}={a["trace"]["app"]}, '
                f'hints end {mine["end_bytes"]}={a["hints_bytes_end"]}, slabs {mine["created"]}={a["slabs_total"]}, '
                f'peak {mine["peak"]}={a["direct_peak"]}',
                mine['written'] == a['written'] and mine['app'] == a['trace']['app'] and mine['end_bytes'] == a['hints_bytes_end']
                and mine['created'] == a['slabs_total'] and mine['peak'] == a['direct_peak'])


unit()
cluster()
print(f'selfcheck: ok={res["ok"]} FAIL={res["FAIL"]}')
