#!/usr/bin/env python3
"""U14 per-lifetime readings (design §2.6/§2.7). usage: analyze.py <logs dir> [<label> ...]  -> one JSON line per label.
Readings: b (least-squares slope of L on n over checkpoints, MiB/table), per-class slopes (top 15), MBeans/table, K vs ok
count, N_OOM (last ok CREATE before the dump's birth time), f (last checkpoint L / heap; old-gen CollectionUsage / heap at the
last sample), D3 max, DDL latency (median of the first/last 200 CREATEs), first OutOfMemoryError lines, worst 60 s GC
fraction, oom_kill, RSS and Shmem peaks."""
import json, os, re, statistics, sys

MiB = 1048576.0


def slope(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    d = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / d if d else None


def rd(p):
    try:
        return open(p).read()
    except OSError:
        return ''


def one(d, label):
    L = os.path.join(d, label)
    S = json.loads(rd(L + '/summary.json') or '{}')
    heap = {'2G': 2048, '4G': 4096, '8G': 8192}.get((S.get('args') or [None] * 4)[3] if S.get('mode') == 'life' else '2G', 2048)
    r = {'label': label, 'args': S.get('args'), 'heap_MiB': heap}
    allcp = [json.loads(l) for l in rd(L + '/checkpoints.jsonl').splitlines() if l.strip()]
    cps = [c for c in allcp if c.get('n_ok') is not None]
    s0 = S.get('checkpoint s0') or {}
    pts = [(0, s0.get('L'))] if s0.get('L') else []
    pts += [(c['n_ok'], c['L']) for c in cps if c.get('n_ok') is not None and c.get('L')]
    r['checkpoints'] = [[n, round(l / MiB, 1)] for n, l in pts]
    r['K_vs_ok'] = [[c.get('n_ok'), c.get('K'), c.get('mbeans')] for c in cps]
    if len(pts) >= 2:
        r['b_MiB_per_table'] = round(slope([p[0] for p in pts], [p[1] / MiB for p in pts]), 4)
        r['b_from_500_MiB_per_table'] = (round(slope([p[0] for p in pts[1:]], [p[1] / MiB for p in pts[1:]]), 4)
                                         if len(pts) >= 3 else None)
        mb = [(c['n_ok'], c['mbeans']) for c in cps if isinstance(c.get('mbeans'), int)]
        if s0.get('mbeans') is not None and isinstance(s0.get('mbeans'), int):
            mb = [(0, s0['mbeans'])] + mb
        r['mbeans_per_table'] = round(slope([a for a, _ in mb], [b for _, b in mb]), 2) if len(mb) >= 2 else None
        # per-class slopes from top40 lists of the first (s0 or first cp) and last checkpoints
        def classes(path):
            out = {}
            for l in rd(path).splitlines():
                m = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
                if m:
                    out[m.group(3)] = (int(m.group(1)), int(m.group(2)))
            return out
        last_tag = cps[-1]['tag'] if cps else None
        a, b = classes(L + '/hist-s0-2.txt'), classes(L + f'/hist-{last_tag}-2.txt') if last_tag else {}
        nlast = cps[-1]['n_ok'] if cps else None
        if a and b and nlast:
            sl = []
            for k, (cnt, by) in b.items():
                c0, b0 = a.get(k, (0, 0))
                sl.append((k, (by - b0) / nlast, (cnt - c0) / nlast))
            sl.sort(key=lambda x: -x[1])
            r['per_class_per_table'] = [[k, round(bb), round(cc, 1)] for k, bb, cc in sl[:15]]
            tot = sum(x[1] for x in sl)
            r['per_class_total_B_per_table'] = round(tot)
    # client
    rows = []
    for l in rd(L + '/client.csv').splitlines():
        p = l.split(',', 5)
        if p and p[0].isdigit():
            rows.append(p)
    cr = [p for p in rows if p[2] == 'create']
    ok = [p for p in cr if p[4] == 'ok']
    r['creates_ok'] = len(ok)
    r['creates_rejected'] = sum(1 for p in cr if p[4] == 'rejected')
    r['creates_other'] = {k: sum(1 for p in cr if p[4] == k) for k in ('timeout', 'nohost', 'error')}
    r['drops_ok'] = sum(1 for p in rows if p[2] == 'drop' and p[4] == 'ok')
    if ok:
        lat = [float(p[3]) for p in ok]
        r['lat_ms_first200_median'] = round(statistics.median(lat[:200]), 1)
        r['lat_ms_last200_median'] = round(statistics.median(lat[-200:]), 1)
        r['last_ok_i'] = int(ok[-1][1])
        r['ddl_wall_s'] = round((int(rows[-1][0]) - int(rows[0][0])) / 1000)
    oom = S.get('oom')
    if oom:
        r['oom'] = True
        di = oom.get('dumps') or []
        if di:
            birth = int(di[0]['birth_s']) if di[0]['birth_s'] not in ('0', '-') else int(di[0]['mtime_s'])
            before = [p for p in ok if int(p[0]) <= birth * 1000]
            r['N_OOM'] = int(before[-1][1]) if before else None
            r['N_OOM_ok_count'] = len(before)
            r['dump_bytes'] = int(di[0]['bytes'])
        r['stdout_oom_lines'] = oom.get('stdout_lines')
    else:
        r['oom'] = False
    syslog = rd(L + '/system.log')
    m = re.search(r'^(ERROR|WARN).*\n(?:.*\n){0,1}.*OutOfMemoryError.*$', syslog, re.M)
    idx = syslog.find('java.lang.OutOfMemoryError')
    if idx >= 0:
        st = syslog.rfind('\n', 0, max(0, idx - 400))
        r['first_oom_syslog'] = syslog[st + 1: idx + 1600]
    # sampler
    smp = []
    for l in rd(L + '/sampler.csv').splitlines():
        p = l.split(',')
        if p and p[0].isdigit():
            smp.append(p)
    def num(x):
        try:
            return int(x)
        except ValueError:
            return None
    if smp:
        d3 = [num(p[9]) for p in smp if len(p) > 9 and num(p[9]) is not None]
        r['D3_max_MiB'] = round(max(d3) / MiB, 1) if d3 else None
        oc = [num(p[3]) for p in smp if len(p) > 3 and num(p[3]) is not None]
        r['old_coll_used_last_MiB'] = round(oc[-1] / MiB, 1) if oc else None
        r['old_coll_used_max_MiB'] = round(max(oc) / MiB, 1) if oc else None
        r['f_oldcoll'] = round(oc[-1] / MiB / heap, 3) if oc else None
        g = [(int(p[0]), num(p[5]), num(p[7])) for p in smp if len(p) > 7 and num(p[5]) is not None and num(p[7]) is not None]
        best = 0.0
        j = 0
        for i in range(len(g)):
            while j < i and g[i][0] - g[j][0] > 60000:
                j += 1
            if g[i][0] - g[j][0] >= 55000:
                fr = ((g[i][1] + g[i][2]) - (g[j][1] + g[j][2])) / (g[i][0] - g[j][0])
                best = max(best, fr)
        r['gc_frac_max_60s'] = round(best, 3)
        mbs = [num(p[8]) for p in smp if len(p) > 8 and num(p[8]) is not None]
        r['mbeans_max'] = max(mbs) if mbs else None
        r['sampler_last_ms'] = int(smp[-1][0])
    if cps or pts:
        lastL = pts[-1][1] / MiB if pts else None
        r['f_last_checkpoint'] = round(lastL / heap, 3) if lastL else None
    rss = [l.split(',') for l in rd(L + '/rss.csv').splitlines() if l[:1].isdigit()]
    rv = [int(p[1]) for p in rss if p[1].isdigit()]
    sv = [int(p[2]) for p in rss if len(p) > 2 and p[2].isdigit()]
    r['rss_anon_max_MiB'] = round(max(rv) / 1024) if rv else None
    r['shmem_max_MiB'] = round(max(sv) / 1024) if sv else None
    ev = rd(L + '/memory.events')
    m = re.search(r'oom_kill (\d+)', ev)
    r['cg_oom_kill'] = int(m.group(1)) if m else None
    for tag in ('oom', 'end'):
        sc = rd(L + f'/scan-{tag}.json')
        if sc:
            j = json.loads(sc)
            if 'error' in j:
                r[f'scan_{tag}'] = j
                continue
            r[f'scan_{tag}'] = {k: j.get(k) for k in ('total_shallow_bytes', 'marker_byte_arrays', 'marker_byte_array_bytes',
                                                       'long330_arrays', 'long330_bytes', 'named')}
            r[f'scan_{tag}']['top12'] = j.get('top40', [])[:12]
            r[f'scan_{tag}']['traces'] = [t['frames'][:12] for t in j.get('traces', [])[:3]]
    for k in ('settings', 'start', 'namecheck', 'setup', 'intervention_path_check', 'FAIL', 'U_end', 'not_started'):
        if k in S:
            r['s_' + k] = S[k]
    for k, v in S.items():
        if k.startswith('client '):
            r['s_' + k] = v
    return r


if __name__ == '__main__':
    d = sys.argv[1]
    labels = sys.argv[2:] or sorted(os.listdir(d))
    for lb in labels:
        if os.path.isdir(os.path.join(d, lb)):
            print(json.dumps(one(d, lb)))
