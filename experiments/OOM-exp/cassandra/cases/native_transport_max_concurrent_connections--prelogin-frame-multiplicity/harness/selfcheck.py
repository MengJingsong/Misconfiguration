# U2 stage 2 (2026-11-17) self-check / per-run summary (case §2.5 item 5, §2.6 readings, §2.7 outcome rows).
# Written before the first reading. usage: python3 selfcheck.py <run-log-dir> [<run-log-dir> ...]
# Re-parses each run's files and prints the readings and one "OUTCOME <run> <row> <reason>" line.
import glob, os, re, sys, datetime

def rd(p):
    try:
        return open(p, errors='replace').read()
    except OSError:
        return ''

def kv(text):
    d = {}
    for line in text.splitlines():
        if '=' in line:
            k, v = line.split('=', 1); d[k.strip()] = v.strip()
    return d

LOGTS = re.compile(r'^(?:ERROR|WARN|INFO|DEBUG|TRACE)\s+\[[^\]]*\] (\d{4}-\d\d-\d\d)T(\d\d:\d\d:\d\d),(\d{3})')

def log_ms(line):
    # system.log timestamps are ISO-8601 UTC ("2026-11-18T03:55:22,807"; seen in the SH shakedown).
    m = LOGTS.search(line)
    if not m:
        return None
    t = datetime.datetime.strptime(m.group(1) + ' ' + m.group(2), '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)
    return int(t.timestamp() * 1000) + int(m.group(3))

def ntfmem(line):
    return {k: v for k, v in re.findall(r'(\w+)=(\S+)', line)}

def longest_err_run(lines, t_lo, t_hi):
    # longest span (ms) of consecutive err lines within [t_lo, t_hi]
    best = 0; start = None; last = None
    for t, ok in lines:
        if t < t_lo or t > t_hi:
            continue
        if not ok:
            if start is None:
                start = t
            last = t
            best = max(best, last - start)
        else:
            start = None
    return best

def one(R):
    out = []
    P = lambda *a: out.append(' '.join(str(x) for x in a))
    run = os.path.basename(R.rstrip('/'))
    ex = kv(rd(os.path.join(R, 'exit.txt')))
    cfg = rd(os.path.join(R, 'config.txt')); args = rd(os.path.join(R, 'jvm-args.txt'))
    P('run', run, '| cond', ex.get('cond'), 'mode', ex.get('mode'), 'k', ex.get('k'), 'yaml_extra', ex.get('yaml_extra'), 'btm', ex.get('btm'), 'arm_test', ex.get('arm_test'))
    xmx = re.findall(r'-Xmx(\S+)', args); mdm = re.findall(r'MaxDirectMemorySize=(\S+)', args)
    P('resolved: -Xmx', xmx, 'MaxDirectMemorySize(args)', mdm, '| flags:', ' '.join(l for l in cfg.splitlines() if 'MaxDirect' in l or 'MaxHeapSize' in l))
    P('config:', ' '.join(l for l in cfg.splitlines() if l.startswith(('native_transport_max_concurrent', 'native_transport_idle', 'native_transport_max_frame', 'client_error'))))
    # endpoint
    syslogs = sorted(glob.glob(os.path.join(R, 'system*.log*')))
    sysl = ''.join(rd(f) for f in syslogs); stdo = rd(os.path.join(R, 'node-stdout.log'))
    oodme = [l for l in sysl.splitlines() if 'OutOfDirectMemoryError' in l]
    oodme_std = [l for l in stdo.splitlines() if 'OutOfDirectMemoryError' in l]
    t_oom_ms = None
    first_err = next((l for l in sysl.splitlines() if re.search(r'OutOfDirectMemoryError|java.lang.OutOfMemoryError|OutOfMemory error letting', l)), None)
    if first_err:
        # the timestamp is on the ERROR header line preceding a stack line; search back
        lines = sysl.splitlines(); i = lines.index(first_err)
        while i >= 0 and log_ms(lines[i]) is None:
            i -= 1
        t_oom_ms = log_ms(lines[i]) if i >= 0 else None
    if t_oom_ms is None and ex.get('t_oom'):
        t_oom_ms = int(ex['t_oom']) * 1000
    P('first OOM line (system.log):', (first_err or 'none')[:300], '| t_oom_ms', t_oom_ms)
    P('OutOfDirectMemoryError lines: system.log', len(oodme), 'stdout', len(oodme_std))
    if oodme or oodme_std:
        P('first OODME:', (oodme or oodme_std)[0][:400])
    esc = {}
    for key, pat in [('letting_jvm', 'OutOfMemory error letting the JVM handle'), ('force_heap', 'Force heap space OutOfMemoryError'),
                     ('java_heap_space', 'Java heap space'), ('dumping_heap', 'Dumping heap to'), ('heap_dump_done', 'Heap dump file created'),
                     ('kill9', 'kill -9'), ('limit_exceeded', 'Exceeded maximum native connection limit')]:
        esc[key] = (sysl + '\n' + stdo).count(pat)
    P('escalation counts:', ' '.join('%s=%d' % kv_ for kv_ in esc.items()))
    rc = ex.get('rc', ''); t_exit = ex.get('t_exit', '')
    P('exit: rc', rc or 'none', 't_exit', t_exit or 'none', 't_exit - t_oom (s):', (int(t_exit) - t_oom_ms // 1000) if (t_exit and t_oom_ms) else 'NA', '| end:', ex.get('end'), '| node_alive_at_end', ex.get('node_alive_at_end'))
    # client
    cl = rd(os.path.join(R, 'client.out')).splitlines()
    conns = [(int(m.group(2)), m.group(3) == 'ok') for m in (re.match(r'conn (\d+) (\d+) (ok|err)', l) for l in cl) if m]
    n_ok = sum(1 for t, ok in conns if ok); n_err = sum(1 for t, ok in conns if not ok)
    ok_before = sum(1 for t, ok in conns if ok and (t_oom_ms is None or t <= t_oom_ms))
    first_err_conn = next(((t, l) for (t, ok), l in zip(conns, [l for l in cl if l.startswith('conn ')]) if not ok), None)
    P('client: attempted', len(conns), 'ok', n_ok, 'err', n_err, 'ok before t_oom', ok_before, '|', ' '.join(l for l in cl if l.startswith(('holding', 'alive', 'stop', 'done'))))
    if first_err_conn:
        P('client first err:', first_err_conn[1][:200])
    # NTFMEM
    mem = [ntfmem(l) for l in rd(os.path.join(R, 'btm-lines.txt')).splitlines() if l.startswith('NTFMEM')]
    if mem:
        P('first NTFMEM: nettyMax', mem[0].get('nettyMax'), 'arenas', mem[0].get('arenas'), 'chunk', mem[0].get('chunk'), 'nettyUsed', mem[0].get('nettyUsed'))
        before = [m for m in mem if t_oom_ms is None or int(m['t']) <= t_oom_ms]
        if before:
            m = before[-1]
            P('last NTFMEM before t_oom: t', m['t'], 'nettyUsed', m.get('nettyUsed'), 'nettyMax', m.get('nettyMax'), 'held16', m.get('held16'), 'chunks', m.get('chunks'),
              'inflight', m.get('inflight'), 'clients', m.get('clients'), 'headroom_MiB', (int(m['nettyMax']) - int(m['nettyUsed'])) // 1048576)
        P('max held16', max(int(m.get('held16', 0)) for m in mem), 'max nettyUsed MiB', max(int(m['nettyUsed']) for m in mem) // 1048576,
          'max inflight', max(int(m.get('inflight', 0)) for m in mem), 'max clients', max(int(m.get('clients', 0)) for m in mem), 'NTFMEM lines', len(mem))
    btm = rd(os.path.join(R, 'btm-lines.txt'))
    P('NTFDISCARD', btm.count('NTFDISCARD'), 'NTFFAIL', btm.count('NTFFAIL'))
    # samples
    sm = [l.split('\t') for l in rd(os.path.join(R, 'samples.tsv')).splitlines()[1:]]
    sm = [r for r in sm if len(r) == 7]
    num = lambda x: int(x) if x.isdigit() else None
    mc = [num(r[2]) for r in sm if num(r[2])]; ra = [num(r[5]) for r in sm if num(r[5])]; es = [num(r[6]) for r in sm if num(r[6]) is not None]
    evmax = max([num(r[3]) or 0 for r in sm] or [0]); evoom = max([num(r[4]) or 0 for r in sm] or [0])
    P('peak memory.current GiB %.2f' % (max(mc) / 2**30) if mc else 'peak memory.current NA', '| peak RssAnon GiB %.2f' % (max(ra) / 2**20) if ra else '| RssAnon NA',
      '| max established 9042', max(es) if es else 'NA', '| memory.events max', evmax, 'oom_kill', evoom)
    nmt = [l.split('\t') for l in rd(os.path.join(R, 'nmt.tsv')).splitlines()[1:]]
    nmtv = [int(r[1]) for r in nmt if len(r) == 2 and re.match(r'^[+-]?\d+$', r[1])]
    if nmtv:
        P('NMT Other committed delta max MiB %.0f' % (max(nmtv) / 1024))
    # probe
    pr = rd(os.path.join(R, 'probe.out')).splitlines()
    Pl = [(int(m.group(1)), m.group(2) == 'ok') for m in (re.match(r'P (\d+) (ok|err)', l) for l in pr) if m]
    Nl = [(int(m.group(1)), m.group(2) == 'ok') for m in (re.match(r'N (\d+) (ok|err)', l) for l in pr) if m]
    t_end_alive = int(t_exit) * 1000 if t_exit else (Pl[-1][0] if Pl else 0)
    last_ok_before = max([t for t, ok in Pl if ok and (t_oom_ms is None or t <= t_oom_ms)] or [0])
    first_err_after = min([t for t, ok in Pl if not ok and t_oom_ms is not None and t >= t_oom_ms] or [0])
    P('probe P ok/err', sum(ok for _, ok in Pl), '/', sum(not ok for _, ok in Pl), 'N ok/err', sum(ok for _, ok in Nl), '/', sum(not ok for _, ok in Nl),
      '| last P ok before t_oom', last_ok_before, 'first P err after t_oom', first_err_after or 'none')
    lo = t_oom_ms if t_oom_ms else 0
    lP = longest_err_run(Pl, lo, t_end_alive); lN = longest_err_run(Nl, lo, t_end_alive)
    P('longest consecutive err span while alive after t_oom (ms): P', lP, 'N', lN)
    if not t_oom_ms:
        P('longest consecutive err span whole run (ms): P', longest_err_run(Pl, 0, 1 << 62), 'N', longest_err_run(Nl, 0, 1 << 62))
    perr = [l for l in pr if ' err ' in l]
    if perr:
        P('first probe err:', perr[0][:200])
    kern = rd(os.path.join(R, 'kernel.txt')).strip()
    P('kernel oom lines:', len(kern.splitlines()) if kern else 0)
    # outcome
    test = ex.get('arm_test') == '1'
    probe_ready = any(ok for _, ok in Pl)
    invalid = []
    if evmax > 0 or evoom > 0:
        invalid.append('guard bound (memory.events)')
    if not probe_ready:
        invalid.append('probe never got READY/RESULT')
    if ex.get('mode') == 'partial' and n_ok < 100 and not (test and t_oom_ms):
        invalid.append('client reached < 100 connections')
    has_oodme = bool(oodme or oodme_std)
    any_oom = bool(first_err)
    exited = bool(t_exit)
    if invalid:
        row = 'I'; why = '; '.join(invalid)
    elif test:
        if has_oodme and exited:
            row = 'E1'; why = 'OODME after %d stalled connections, node exited rc=%s' % (ok_before, rc)
        elif has_oodme and not exited:
            if lP >= 60000 and lN >= 60000:
                row = 'E2a'; why = 'OODME, node alive, probe P and N failing >= 60 s'
            else:
                row = 'E2b'; why = 'OODME, node alive, probe served (P gap %d ms, N gap %d ms)' % (lP, lN)
        elif exited and not has_oodme:
            row = 'E5'; why = 'node exited without OODME first (first OOM line: %s)' % ((first_err or 'none')[:120])
        elif any_oom:
            row = 'E5'; why = 'OOM line without OODME: %s' % first_err[:120]
        elif n_err > 0 and n_ok < int(ex.get('k', '0')):
            row = 'E4'; why = 'connections refused/closed (%d err) without OOM' % n_err
        else:
            row = 'E3'; why = 'no OOM line by k_max'
    else:
        if any_oom or exited:
            row = 'CONTROL-FAILED'; why = 'OOM line or node exit in a control/intervention arm'
        else:
            row = 'CONTROL-SURVIVED'; why = 'no OOM line, node alive; held16 max %s; client ok %d err %d; limit-exceeded %d' % (
                max([int(m.get('held16', 0)) for m in mem] or [0]), n_ok, n_err, esc['limit_exceeded'])
    P('OUTCOME', run, row, why)
    return '\n'.join(out)

if __name__ == '__main__':
    for R in sys.argv[1:]:
        print(one(R)); print()
