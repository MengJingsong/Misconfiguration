#!/usr/bin/env python3
"""B18 stage-2 analysis (design §2.6/§2.7). usage: python3 -I analyze.py <logs dir> <label> [<label> ...]
Per lifetime one JSON line: outcome, first-trigger check, workload (requests/rows/errors, MiB/s in the first 60 s), K max
(all tables and ks.t, MiB, and as a multiple of C), heap/old-gen peaks from the sampler, BlockedOnAllocation and dropped/timeouts
deltas, max MutationStage active/pending, Enqueuing/Writing flush lines (on-heap MiB and %), 'High update contention' lines,
gc.log: post-GC heap peak (MiB), number of full GCs, the max share of wall time in GC pauses over any 60 s window (service-loss
criterion), L0 and U_end histogram totals, OOM lines, and the dump scan (regions, top classes)."""
import json, os, re, sys

MiB = 1048576.0


def load_csv(p):
    try:
        lines = open(p).read().splitlines()
    except OSError:
        return []
    cols = lines[0].split(',')
    out = []
    for l in lines[1:]:
        q = l.split(',')
        if len(q) == len(cols):
            out.append(dict(zip(cols, q)))
    return out


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def gc_stats(d):
    files = sorted([f for f in os.listdir(d) if f.startswith('gc.log')], key=lambda f: (len(f), f))
    pauses, after, full = [], [], 0
    rx = re.compile(r'\[([\d.]+)s\].*GC\((\d+)\) Pause (\S+(?: \([^)]*\))*) (\d+)M->(\d+)M\((\d+)M\) ([\d.]+)ms')
    for f in files:
        try:
            for l in open(os.path.join(d, f), errors='replace'):
                if 'Pause' not in l:
                    continue
                m = rx.search(l)
                if not m:
                    continue
                up, kind, a, ms = float(m.group(1)), m.group(3), int(m.group(5)), float(m.group(7))
                pauses.append((up, ms / 1000.0))
                after.append((up, a, kind))
                if kind.startswith('Full'):
                    full += 1
        except OSError:
            pass
    pauses.sort()
    best = 0.0
    j = 0
    s = 0.0
    for i in range(len(pauses)):
        s += pauses[i][1]
        while pauses[i][0] - pauses[j][0] > 60:
            s -= pauses[j][1]
            j += 1
        span = 60.0
        best = max(best, s / span)
    young_after = [a for _, a, k in after if not k.startswith('Full')]
    full_after = [a for _, a, k in after if k.startswith('Full')]
    return {'pauses': len(pauses), 'full_gcs': full, 'max_after_MiB': max([a for _, a, _ in after], default=None),
            'max_full_after_MiB': max(full_after, default=None), 'last_full_after_MiB': full_after[-1] if full_after else None,
            'max_gc_share_60s': round(best, 3), 'total_pause_s': round(sum(p for _, p in pauses), 1),
            'first_up_s': pauses[0][0] if pauses else None, 'last_up_s': pauses[-1][0] if pauses else None,
            'min_young_after_last20_MiB': min(young_after[-20:], default=None)}


def flushes(d):
    out = {'enq': [], 'wri': [], 'contention': []}
    try:
        for l in open(os.path.join(d, 'debug.log'), errors='replace'):
            if 'Enqueuing flush of t' in l:
                m = re.search(r'Usage: ([\d.]+)(\w+) \((\d+)%\) on-heap', l)
                if m:
                    out['enq'].append([l[6:40].split(' ')[-1] if False else l.split(' ')[2], m.group(1) + m.group(2), int(m.group(3))])
            elif 'Writing Memtable-t@' in l:
                m = re.search(r'\(([\d.]+)(\w+) serialized bytes, (\d+) ops, ([\d.]+)(\w+) \((\d+)%\) on-heap', l)
                if m:
                    out['wri'].append([l.split(' ')[2], m.group(4) + m.group(5), int(m.group(6)), int(m.group(3))])
            elif 'High update contention' in l:
                m = re.search(r'contention in (\d+)/(\d+) partitions of (\S+)', l)
                out['contention'].append(m.group(0) if m else l.strip()[-120:])
    except OSError:
        pass
    return out


def to_mib(s):
    m = re.match(r'([\d.]+)(\w+)', s)
    v, u = float(m.group(1)), m.group(2)
    return v * {'B': 1 / MiB, 'KiB': 1 / 1024, 'MiB': 1, 'GiB': 1024}.get(u, 1)


def one(logs, label):
    d = os.path.join(logs, label)
    S = json.load(open(os.path.join(d, 'summary.json')))
    heap = S['args'][3] if len(S['args']) > 3 else '2G'
    C = {'2G': 512, '4G': 1024, '8G': 2048}.get(heap, 512)
    r = {'label': label, 'arm': S['args'][2] if len(S['args']) > 2 else None, 'heap': heap, 'C_MiB': C}
    wo = S.get('workload_outcome', {})
    r['outcome'] = wo.get('outcome')
    r['outcome_at_s'] = wo.get('at_s')
    r['FAIL'] = S.get('FAIL')
    ft = S.get('first_trigger') or {}
    r['first_trigger'] = {k: ft.get(k) for k in ('ok', 'req_ok', 'max_mut_active', 'client_ips')}
    ws = S.get('workload_start', {})
    t0 = ws.get('ms')
    r['R'] = ws.get('R')
    hg = load_csv(os.path.join(d, 'hotgen.csv'))
    if hg:
        last = hg[-1]
        r['req_ok'] = int(last['req_ok']); r['rows_ok'] = int(last['rows_ok'])
        r['errs'] = {k: int(last[k]) for k in ('err_wto', 'err_ovl', 'err_tra', 'err_nha', 'err_oth')}
        S_b = (r['R'] or 0) * 8192
        f60 = [x for x in hg if t0 and int(x['ms']) <= t0 + 61000]
        if f60:
            r['MiBps_first60'] = round(int(f60[-1]['req_ok']) * S_b / MiB / max(1, (int(f60[-1]['ms']) - t0) / 1000), 1)
            r['req_first60'] = int(f60[-1]['req_ok'])
        dur = (int(last['ms']) - t0) / 1000 if t0 else None
        r['MiBps_all'] = round(r['req_ok'] * S_b / MiB / dur, 1) if dur else None
        okt = [int(x['ms']) for i, x in enumerate(hg[1:], 1) if x['req_ok'] != hg[i - 1]['req_ok']]
        r['last_ok_s'] = round((okt[-1] - t0) / 1000) if okt and t0 else None
    sp = load_csv(os.path.join(d, 'sampler.csv'))
    w = [x for x in sp if t0 and int(x['ms']) >= t0]
    def col(name, rows=w):
        return [v for v in (num(x[name]) for x in rows) if v is not None]
    if w:
        K, Kt = col('K'), col('K_t')
        r['K_max_MiB'] = round(max(K) / MiB, 1) if K else None
        r['K_max_xC'] = round(max(K) / MiB / C, 2) if K else None
        r['Kt_max_MiB'] = round(max(Kt) / MiB, 1) if Kt else None
        r['K_last_MiB'] = round(K[-1] / MiB, 1) if K else None
        r['samples'] = len(w)
        r['samples_K_gt_1.3C'] = sum(1 for k in K if k / MiB > 1.3 * C)
        r['heap_used_max_MiB'] = round(max(col('heap_used')) / MiB)
        oc = col('old_coll_used')
        r['old_coll_used_max_MiB'] = round(max(oc) / MiB) if oc else None
        for k in ('blocked', 'mut_dropped', 'write_timeouts', 'old_n', 'young_n'):
            v = col(k)
            pre = [num(x[k]) for x in sp if t0 and int(x['ms']) < t0 and num(x[k]) is not None]
            r[k + '_delta'] = (v[-1] - (pre[-1] if pre else 0)) if v else None
        r['mut_active_max'] = max(col('mut_active'), default=None)
        r['mut_pending_max'] = max(col('mut_pending'), default=None)
        r['pending_flush_max'] = max(col('pending_flush'), default=None)
        r['sampler_last_ms_rel_s'] = round((int(w[-1]['ms']) - t0) / 1000)
    fl = flushes(d)
    r['flush_enq'] = [[e[1], e[2]] for e in fl['enq']]
    r['flush_writing'] = [[e[1], e[2]] for e in fl['wri']]
    r['writing_max_pct'] = max([e[2] for e in fl['wri']], default=None)
    r['writing_max_MiB'] = round(max([to_mib(e[1]) for e in fl['wri']], default=0), 1) if fl['wri'] else None
    r['contention_lines'] = fl['contention'][:6]
    r['contention_n'] = len(fl['contention'])
    r['gc'] = gc_stats(d)
    L0 = S.get('L0') or S.get('hist s0') or {}
    r['L0_MiB'] = round(L0['total'] / MiB) if L0.get('total') else None
    ue = S.get('U_end') or {}
    r['U_end_MiB'] = round(ue['total'] / MiB) if ue.get('total') else None
    r['U_end_bytearr_MiB'] = round(ue['bb'] / MiB) if ue.get('bb') else None
    o = S.get('oom')
    if o:
        r['oom'] = {'lines': o.get('stdout_lines', [])[:6], 'dumps': o.get('dumps'), 'since_workload_s': o.get('since_workload_s')}
    for tag in ('oom', 'end'):
        p = os.path.join(d, f'scan-{tag}.json')
        if os.path.exists(p):
            sc = json.load(open(p))
            tot = sc.get('total_shallow_bytes') or 1
            named = {x['class'].rsplit('.', 1)[-1]: [round(x['bytes'] / MiB, 1), x['count']] for x in sc.get('classes_named', [])}
            d2 = sum(named.get(k, [0])[0] for k in ('Mutation', 'PartitionUpdate', 'BufferCell'))
            r['scan_' + tag] = {'regions': sc.get('region_arrays'), 'region_MiB': round(sc.get('region_bytes', 0) / MiB, 1),
                                'region_share': round(sc.get('region_bytes', 0) / tot, 3), 'total_MiB': round(tot / MiB),
                                'region_xC': round(sc.get('region_bytes', 0) / MiB / C, 2),
                                'top': [[x['class'], round(x['bytes'] / MiB, 1), x['count']] for x in sc.get('classes_top', [])[:10]],
                                'named': named, 'D2_named_MiB': round(d2, 1), 'slab_traces': sc.get('slab_traces'),
                                'trace_sample': (sc.get('slab_trace_samples') or [{}])[0].get('frames', [])[:10]}
    r['memory_events'] = open(os.path.join(d, 'memory.events')).read().split() if os.path.exists(os.path.join(d, 'memory.events')) else None
    return r


if __name__ == '__main__':
    logs = sys.argv[1]
    for lb in sys.argv[2:]:
        try:
            print(json.dumps(one(logs, lb)))
        except Exception as e:
            print(json.dumps({'label': lb, 'error': repr(e)}))
