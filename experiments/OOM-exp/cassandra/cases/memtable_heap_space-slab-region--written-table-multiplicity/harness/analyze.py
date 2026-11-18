#!/usr/bin/env python3
"""C6 stage-2 analysis (design §2.6-§2.7). usage: python3 -I analyze.py <logs dir> <label> ...
Per lifetime: L0, client outcome, OOM time (heap-dump file birth), N_OOM (rows acknowledged before it), dump scan, K before the
OOM, control activity (BlockedOnAllocation, dropped mutations, ks. flush lines), U_end, GC pause share, and the P-checks of
the frozen predictions. One JSON object per label on stdout."""
import csv, json, os, re, sys

MIB = 1 << 20


def rows(path):
    # Jmx.java poll writes ',' then ',ERR' for a failed attribute: normalise ',,ERR' to ',ERR' so columns do not shift
    try:
        return list(csv.DictReader(l.replace(',,ERR', ',ERR') for l in open(path)))
    except OSError:
        return []


def num(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def gc_pauses(d):
    """(uptime_s_end, pause_ms) for every pause line of gc.log*"""
    out = []
    for f in sorted(os.listdir(d)):
        if not f.startswith('gc.log'):
            continue
        for l in open(os.path.join(d, f), errors='replace'):
            m = re.search(r'\]\[(\d+\.\d+)s\].*\bPause (Young|Full|Remark|Cleanup)[^\n]*?(\d+\.\d+)ms', l)
            if m:
                out.append((float(m.group(1)), float(m.group(3)), m.group(2)))
    return sorted(out)


def analyze(d, label):
    L = os.path.join(d, label)
    s = json.load(open(os.path.join(L, 'summary.json')))
    heap = {'2G': 2048, '4G': 4096, '8G': 8192}.get(s['args'][3] if len(s['args']) > 3 else '', None)
    arm = s['args'][2] if len(s['args']) > 2 else None
    M = int(s['args'][5]) if len(s['args']) > 5 else None
    C = heap / 4 if heap else None
    r = {'label': label, 'arm': arm, 'heap_MiB': heap, 'M': M, 'C_MiB': C, 'FAIL': s.get('FAIL'), 'DONE': s.get('DONE')}
    st = s.get('start', {})
    r['validity'] = {'scope_ok': st.get('scope_ok'), 'flags_ok': st.get('flags_ok'), 'settings_ok': s.get('settings', {}).get('ok'),
                     'tables': (s.get('tablecount') or {}).get('tables'), 'MaxDirectMemorySize': st.get('MaxDirectMemorySize'),
                     'up_s': st.get('up_s')}
    L0 = s.get('L0') or {}
    r['L0_MiB'] = round(L0['total'] / MIB, 1) if L0.get('total') else None
    r['L0_bb_MiB'] = round(L0['bb'] / MIB, 1) if L0.get('bb') else None
    r['K_s0'] = L0.get('K')
    cl = s.get('client') or {}
    r['client'] = {k: cl.get(k) for k in ('ok', 'err', 'timeouts', 'passes', 'stopped', 'unacked_at_end', 'retried', 'first_error', 'seconds')}
    acks = rows(os.path.join(L, 'acks.csv'))
    samp = rows(os.path.join(L, 'sampler.csv'))
    rss = rows(os.path.join(L, 'rss.csv'))
    ok_ms = sorted(num(a['ms']) for a in acks if a['status'] == 'ok')
    r['first_ack_ms'] = ok_ms[0] if ok_ms else None
    r['acked_first_10s'] = sum(1 for m in ok_ms if ok_ms and m <= ok_ms[0] + 10000) if ok_ms else 0
    oom = s.get('oom')
    if oom:
        dumps = oom.get('dumps') or []
        birth = num(dumps[0]['birth_s']) * 1000 if dumps and num(dumps[0]['birth_s']) else None
        r['oom'] = {'stdout': oom.get('stdout_lines'), 'dump_birth_ms': birth, 'dump_bytes': dumps[0]['bytes'] if dumps else None}
        if birth:
            n_ack = sum(1 for m in ok_ms if m <= birth)
            sent = [num(a['idx']) for a in acks if num(a['ms']) <= birth]
            r['N_OOM'] = n_ack
            r['N_OOM_ack_total_end'] = len(ok_ms)
            pre = [x for x in samp if num(x['ms']) and num(x['ms']) <= birth and num(x.get('K')) is not None]
            if pre:
                last = pre[-1]
                r['K_last_before_oom'] = num(last['K'])
                r['K_last_ms_before_dump'] = birth - num(last['ms'])
                r['heap_used_last'] = num(last['heap_used'])
            r['seconds_first_ack_to_oom'] = round((birth - ok_ms[0]) / 1000, 1) if ok_ms else None
    scan = s.get('scan oom') or s.get('scan end')
    if scan:
        r['scan'] = {k: scan.get(k) for k in ('region_arrays', 'region_bytes', 'byte_arrays', 'byte_array_bytes', 'total_shallow_bytes', 'file_bytes')}
        r['scan_kind'] = 'oom' if s.get('scan oom') else 'end'
        if scan.get('region_bytes') is not None:
            r['U_D1_MiB'] = round(scan['region_bytes'] / MIB, 1)
    if samp:
        def col(x, c):
            return num(x.get(c))
        valid = [x for x in samp if col(x, 'blocked') is not None]
        if valid:
            r['blocked_delta'] = col(valid[-1], 'blocked') - col(valid[0], 'blocked')
            r['dropped_delta'] = (col(valid[-1], 'mut_dropped') or 0) - (col(valid[0], 'mut_dropped') or 0)
            r['K_max'] = max(col(x, 'K') or 0 for x in valid)
            r['K_last'] = col(valid[-1], 'K')
            r['mut_completed_delta'] = (col(valid[-1], 'mut_completed') or 0) - (col(valid[0], 'mut_completed') or 0)
            r['old_full_gcs'] = (col(valid[-1], 'old_n') or 0) - (col(valid[0], 'old_n') or 0)
    if rss:
        ks = [num(x['cg_oom_kill']) for x in rss if num(x.get('cg_oom_kill')) is not None]
        r['cg_oom_kill_max'] = max(ks) if ks else None
        rs = [num(x['rss_anon_kb']) for x in rss if num(x.get('rss_anon_kb'))]
        r['rss_anon_max_MiB'] = round(max(rs) / 1024) if rs else None
    r['flush_lines_ks'] = len(s.get('flush_lines_ks') or [])
    ue = s.get('U_end')
    if ue:
        r['U_end_MiB'] = round(ue['total'] / MIB, 1)
        r['U_end_bb_MiB'] = round(ue['bb'] / MIB, 1)
        r['K_end'] = ue.get('K')
        if L0.get('total'):
            r['U_end_minus_L0_MiB'] = round((ue['total'] - L0['total']) / MIB, 1)
            if M:
                r['slope_live_KiB_per_row'] = round((ue['total'] - L0['total']) / (M - 1) / 1024, 2)
        if isinstance(ue.get('K'), int) and isinstance(L0.get('K'), int):
            r['K_growth_MiB'] = round((ue['K'] - L0['K']) / MIB, 2)
    # D8 steps
    steps = {k[len('hist w'):]: v for k, v in s.items() if k.startswith('hist w')}
    if steps:
        pts = [(0, L0['total'], L0.get('bb'), L0.get('K'))] + [(int(k), v['total'], v['bb'], v['K']) for k, v in sorted(steps.items(), key=lambda kv: int(kv[0]))]
        r['D8_points'] = [{'N': n, 'total_MiB': round(t / MIB, 1), 'bb_MiB': round(b / MIB, 1), 'K': k} for n, t, b, k in pts]

        def slope(i):
            xs = [p[0] for p in pts]; ys = [p[i] for p in pts]
            mx = sum(xs) / len(xs); my = sum(ys) / len(ys)
            return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
        r['slope_R_bb_MiB_per_table'] = round(slope(2) / MIB, 4)
        r['slope_total_MiB_per_table'] = round(slope(1) / MIB, 4)
        r['slope_K_KiB_per_table'] = round(slope(3) / 1024, 3)
    # GC: largest share of wall time in pauses over any 60 s window
    gp = gc_pauses(L)
    best = 0.0
    j = 0
    for i, (t, ms, _) in enumerate(gp):
        while gp[j][0] < t - 60:
            j += 1
        best = max(best, sum(p[1] for p in gp[j:i + 1]) / 60000)
    r['gc_max_pause_share_60s'] = round(best, 3)
    r['gc_full_pauses'] = sum(1 for p in gp if p[2] == 'Full')
    # predictions
    P = {}
    if arm == 'T' and heap:
        P['P1_oom'] = bool(oom) and any('java.lang.OutOfMemoryError: Java heap space' in l for l in (oom.get('stdout_lines') or [])) and r.get('N_OOM', M) < M - 1
        if r.get('N_OOM') is not None and r.get('L0_MiB'):
            x = (r['L0_MiB'] + r['N_OOM']) / heap
            P['P2_ratio'] = round(x, 3)
            P['P2'] = 0.70 <= x <= 1.02
        if r.get('scan') and r.get('N_OOM') is not None:
            ra = r['scan']['region_arrays']
            P['P3_regions_in_range'] = 0.90 * r['N_OOM'] <= ra <= 1.10 * r['N_OOM'] + 100
            P['P3_region_bytes_gt_1.5C'] = r['scan']['region_bytes'] > 1.5 * C * MIB
        if r.get('K_last_before_oom') is not None:
            P['P3_K_le_0.02C'] = r['K_last_before_oom'] <= 0.02 * C * MIB
        P['P3_blocked_unchanged'] = r.get('blocked_delta') == 0
        P['P3_no_ks_flush'] = r['flush_lines_ks'] == 0
    if arm in ('C', 'I') and heap:
        P['survived'] = not oom
        P['all_acked'] = r['client'].get('ok') == M - 1 and not r['client'].get('unacked_at_end')
        if r.get('U_end_MiB') and r.get('L0_MiB'):
            P['U_end_le_L0+50'] = r['U_end_MiB'] <= r['L0_MiB'] + 50
            P['U_end_le_0.70heap'] = r['U_end_MiB'] <= 0.70 * heap
        if arm == 'C' and r.get('K_growth_MiB') is not None:
            P['P4_K_growth_2_8MiB'] = 2 <= r['K_growth_MiB'] <= 8
        if arm == 'I' and r.get('slope_live_KiB_per_row') is not None:
            P['P5_slope_le_16KiB'] = r['slope_live_KiB_per_row'] <= 16
        if r.get('scan'):
            P['regions_in_end_dump'] = r['scan']['region_arrays']
            P['regions_ok'] = r['scan']['region_arrays'] <= (100 if arm == 'C' else 30)
    r['P'] = P
    return r


if __name__ == '__main__':
    for lab in sys.argv[2:]:
        try:
            print(json.dumps(analyze(sys.argv[1], lab)))
        except Exception as e:
            print(json.dumps({'label': lab, 'error': repr(e)}))
