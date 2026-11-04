#!/usr/bin/env python3
"""Stage 4, cluster tier, file_cache_size-allocateMoreChunks-memoryUsageThreshold (case 9b-9e, amended 2026-10-14).
usage: cluster-run.py build | instrument | value <MiB|default> | compare
  build       one node lifetime at the default: wipe, schema, 20 passes of 2,000 partitions x 4 rows each followed by a flush,
              dataset check (20 Data.db files, chunk_length_in_kb 64), stop.           Logs: ~/stage4-logs/fcs/build/
  instrument  shakedown (not a reading), file_cache_size 16 MiB: idle 10 s, A (C=4) 20 s with the reader-demand and SSTables-per-read
              checks, B (C=200) 20 s with O > 0 and the counters moving; stops on any failed check.  Logs: .../fcs/instrument/
  value <v>   run 1, one value, one node lifetime (9e amendment): idle 60 s, A (C=4, 30 s), pause 20 s, B (C=200 until 120 s after
              the first O > 0; 150 s at most for the client, which is launched once), 30 s after, stop.  Logs: .../fcs/run1/<v>/
  compare     reads run1/<v>/result.json for every value and writes run1/compare.txt (the cross-value relations of 9a).
One node (~/cassandra-run1), RF 1, MAX_HEAP_SIZE=4G, NMT summary, MaxDirectMemorySize 8G, Byteman agent with hold.btm. Every command
is logged to session.log; EXPECTED lines go to summary.txt; the sampler writes samples.csv (1 s); phase edges go to phases.csv;
NMT summaries to nmt/; the Byteman trace to bm.trace. Exit 1: an instrument or dataset check failed. The node is stopped on any exit."""
import csv, json, os, re, statistics, subprocess, sys, threading, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
BM = C + '/build/lib/jars'
ROOT = f'{HOME}/stage4-logs/fcs'
MODE = sys.argv[1]
ARG = sys.argv[2] if len(sys.argv) > 2 else None
MIB = 1024 * 1024
M = 8 * MIB                       # MACRO_CHUNK_SIZE
VALUES = ['16', '64', '100', '128', 'default']
D_B = 200 * 20 * 64 * 1024        # 250 MiB
D_A = 4 * 20 * 64 * 1024          # 5 MiB

if MODE == 'build':
    D = ROOT + '/build'
elif MODE == 'instrument':
    D = ROOT + '/instrument'
elif MODE == 'value':
    assert ARG in VALUES, ARG
    D = f'{ROOT}/run1/{ARG}'
elif MODE == 'compare':
    D = ROOT + '/run1'
else:
    raise SystemExit(__doc__)
os.makedirs(D, exist_ok=True)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + ('/compare.txt' if MODE == 'compare' else '/summary.txt'), 'w')
TRACE = D + '/bm.trace'
SAMPLES = D + '/samples.csv'
STOPFILE = D + '/sampler.stop'
PHASES = []
RESULT = {}


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr); SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=900, check=True, env=None, cwd=C):
    log('+ ' + (cmd if isinstance(cmd, str) else ' '.join(cmd)))
    r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = (r.stdout or '') + (r.stderr or '')
    SESSION.write(out[-3000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-800:]}')
    return r.returncode, out


def daemon_pid():
    r = subprocess.run("pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon'", shell=True, capture_output=True, text=True)
    return r.stdout.split()[0] if r.returncode == 0 else None


def stop_node():
    open(STOPFILE, 'w').close()
    if daemon_pid():
        sh('bin/nodetool stopdaemon', check=False)
        for _ in range(90):
            if not daemon_pid():
                break
            time.sleep(1)
        if daemon_pid():
            subprocess.run("pkill -9 -f '[o]rg.apache.cassandra.service.CassandraDaemon'", shell=True)
            time.sleep(2)
    if daemon_pid():
        log('WARNING: a CassandraDaemon is still running')
    for f in ('system.log', 'debug.log'):
        if os.path.exists(f'{C}/logs/{f}'):
            sh(f'cp logs/{f} {D}/', check=False)
    sh('git checkout -q conf/cassandra.yaml', check=False)


def fail(msg):
    note('FAIL: ' + msg); stop_node(); sys.exit(1)


def expect(desc, cond):
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    RESULT.setdefault('expected', []).append([desc, bool(cond)])
    return cond


def phase(name):
    t = int(time.time() * 1000)
    PHASES.append((name, t))
    with open(D + '/phases.csv', 'a') as f:
        f.write(f'{name},{t}\n')
    sh('bin/nodetool version', check=False)    # Byteman "dump" line (StorageService.getReleaseVersion)
    log(f'PHASE {name} at {t}')
    return t


def client(*args, timeout=900):
    r = subprocess.run([sys.executable, f'{HARNESS}/send-cql.py', *args], capture_output=True, text=True, timeout=timeout)
    log('+ send-cql.py ' + ' '.join(args)); SESSION.write(r.stderr[-600:] + '\n'); SESSION.flush()
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {'ok': False, 'error': 'ClientFailure', 'message': (r.stdout + r.stderr)[-400:]}


def nmt(tag):
    pid = daemon_pid()
    os.makedirs(D + '/nmt', exist_ok=True)
    t = int(time.time() * 1000)
    _, out = sh(f'jcmd {pid} VM.native_memory summary', check=False)
    open(f'{D}/nmt/{tag}.txt', 'w').write(f'# epoch_ms={t}\n' + out)
    m = re.search(r'-\s+Other \(reserved=(\d+)KB, committed=(\d+)KB\)', out)
    tot = re.search(r'Total: reserved=(\d+)KB, committed=(\d+)KB', out)
    r = dict(tag=tag, ms=t, other_kb=int(m.group(2)) if m else None, total_kb=int(tot.group(2)) if tot else None)
    with open(D + '/nmt.csv', 'a') as f:
        f.write(f'{tag},{t},{r["other_kb"]},{r["total_kb"]}\n')
    return r


def start_node(value, wipe):
    sh('git checkout -q conf/cassandra.yaml', check=False)
    note(sh(f'{HARNESS}/make-node-yaml.sh {value}')[1].strip().replace('\n', ' | '))
    if wipe:
        sh('rm -rf data commitlog saved_caches logs hints cdc_raw')
    else:
        sh('rm -rf saved_caches logs')
    for f in (TRACE, SAMPLES, STOPFILE, D + '/phases.csv', D + '/nmt.csv'):
        if os.path.exists(f):
            os.remove(f)
    sh(f'rm -rf {D}/classes {D}/nmt && mkdir -p {D}/classes {D}/nmt && javac -d {D}/classes {HARNESS}/PoolSampler.java')
    _, ts = sh(f'java -classpath {BM}/byteman-4.0.20.jar:build/classes/main:"build/lib/jars/*":"lib/*" org.jboss.byteman.check.TestScript {HARNESS}/hold.btm', check=False)
    open(D + '/testscript.txt', 'w').write(ts)
    note('Byteman TestScript: ' + ('no errors' if 'TestScript: no errors' in ts else 'ERRORS (testscript.txt)'))
    if 'TestScript: no errors' not in ts:
        fail('Byteman TestScript reports errors')
    env = dict(os.environ, MAX_HEAP_SIZE='4G',
               JVM_EXTRA_OPTS=f'-XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=8G '
                              f'-javaagent:{BM}/byteman-4.0.20.jar=script:{HARNESS}/hold.btm,listener:true -Dstage4.byteman.out={TRACE}')
    sh(f'bin/cassandra -p {D}/cassandra.pid > {D}/startup.log 2>&1', env=env)
    for _ in range(120):
        _, st = sh('bin/nodetool statusbinary', check=False)
        _, ns = sh('bin/nodetool status', check=False)
        if 'running' in st and re.search(r'^UN', ns, re.M):
            break
        time.sleep(2)
    else:
        fail('node did not come up')
    _, sl = sh(f'java -cp {BM}/byteman-submit-4.0.20.jar org.jboss.byteman.agent.submit.Submit -l', check=False)
    rules = [l.split()[1] + (' ' + l.split()[2] if len(l.split()) > 2 else '') for l in sl.splitlines() if l.startswith('RULE')]
    note(f'node up; Byteman rules loaded: {len(rules)} ({", ".join(rules)})')
    _, vm = sh(f'jcmd {daemon_pid()} VM.command_line', check=False)
    flags = ' '.join(x for x in vm.split() if x.startswith('-Xm') or 'MaxDirectMemorySize' in x or 'NativeMemoryTracking' in x)
    note('JVM flags: ' + flags)
    RESULT['jvm_flags'] = flags
    _, line = sh("grep -h 'Global buffer pool limit is' logs/system.log | tail -1", check=False)
    note('startup line: ' + line.strip())
    RESULT['startup_line'] = line.strip()


def start_sampler():
    p = subprocess.Popen(['java', '-cp', D + '/classes', 'PoolSampler', SAMPLES, STOPFILE, '1000'], stdout=subprocess.DEVNULL, stderr=open(D + '/sampler.err', 'w'))
    log(f'sampler pid {p.pid}')
    for _ in range(30):
        time.sleep(1)
        if os.path.exists(SAMPLES) and len(open(SAMPLES).read().splitlines()) >= 2:
            return p
    fail('sampler wrote no row')


def samples():
    rows = []
    for l in open(SAMPLES).read().splitlines()[1:]:
        f = l.split(',')
        if len(f) == 13 and f[1] != 'ERR':
            rows.append(dict(zip(['t0', 't1', 'capacity', 'size', 'used', 'overflow', 'pooled', 'hits', 'misses', 'net_size', 'net_overflow',
                                  'direct_used', 'direct_count'], map(int, f))))
    return rows


def window(rows, a, b):
    return [r for r in rows if a <= r['t0'] <= b]


def dumps():
    out = []
    if os.path.exists(TRACE):
        for l in open(TRACE).read().splitlines():
            if l.startswith('dump '):
                out.append({k: int(v) for k, v in re.findall(r'(\w+)=(-?\d+)', l)})
    return out


def dump_at(t):
    """the first dump line written at or after epoch ms t (each phase() call writes one)"""
    for d in dumps():
        if d['ms'] >= t:
            return d
    return None


def made_times():
    out = []
    if os.path.exists(TRACE):
        for l in open(TRACE).read().splitlines():
            if l.startswith('made '):
                out.append(int(re.search(r'ms=(\d+)', l).group(1)))
    return sorted(out)


def p_bm(t, made):
    """exact pooled reservation at epoch ms t: chunk-cache macro chunks created by then (Byteman "made" lines) x 8 MiB"""
    return sum(1 for m in made if m <= t) * M


def trace_max_inhold(a, b):
    m = 0
    if os.path.exists(TRACE):
        for l in open(TRACE).read().splitlines():
            if l.startswith('hold '):
                d = {k: int(v) for k, v in re.findall(r'(\w+)=(-?\d+)', l)}
                if a <= d['ms'] <= b:
                    m = max(m, d['inhold'])
    return m


def grep_count(pattern):
    _, out = sh(f"grep -c '{pattern}' logs/system.log || true", check=False)
    try:
        return int(out.strip().splitlines()[-1])
    except Exception:
        return -1


def tablehist():
    _, out = sh('bin/nodetool tablehistograms ks1 t', check=False)
    open(D + '/tablehistograms.txt', 'w').write(out)
    vals = {}
    for l in out.splitlines():   # Percentile, Read Latency, Write Latency, SSTables, Partition Size, Cell Count
        f = l.split()
        if len(f) >= 4 and f[0] in ('50%', '95%', '99%', 'Max'):
            try:
                vals[f[0]] = float(f[3])
            except ValueError:
                pass
    return vals


def read_bg(conc, secs, box):
    box['r'] = client('read', str(conc), str(secs), timeout=int(secs) + 600)


def build():
    if daemon_pid():
        fail('a CassandraDaemon is already running')
    start_node('default', wipe=True)
    p = client('probe')
    if not p.get('ok') or p.get('protocol') != 5:
        fail(f'probe failed or protocol is not 5: {p}')
    sh('bin/cqlsh -e "CREATE KEYSPACE ks1 WITH replication = {\'class\': \'SimpleStrategy\', \'replication_factor\': 1}; '
       'CREATE TABLE ks1.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression = {\'class\': \'LZ4Compressor\', \'chunk_length_in_kb\': 64} '
       'AND compaction = {\'class\': \'SizeTieredCompactionStrategy\', \'enabled\': \'false\'};"')
    for i in range(1, 21):
        r = client('load', str(i))
        if not r.get('ok'):
            fail(f'load pass {i} failed: {r}')
        sh('bin/nodetool flush ks1 t')
    _, ls = sh('ls data/data/ks1/t-*/ | grep -- -Data.db || true', check=False)
    files = sorted(ls.split())
    _, du = sh('du -sb data/data/ks1/', check=False)
    _, desc = sh('bin/cqlsh -e "DESCRIBE TABLE ks1.t"', check=False)
    open(D + '/describe.txt', 'w').write(desc)
    chunk64 = "'chunk_length_in_kb': '64'" in desc
    note(f'DATASET: {len(files)} Data.db files; ks1 on disk {du.split()[0] if du.split() else "?"} B; chunk_length_in_kb 64: {chunk64}')
    if len(files) != 20 or not chunk64:
        fail('dataset check failed')
    _, ts = sh('bin/nodetool tablestats ks1.t', check=False)
    open(D + '/tablestats.txt', 'w').write(ts)
    note('BUILD DONE')
    stop_node()


def lifetime(value, idle_s, a_s, pause_s, b_client_s, b_after_first_o_s, after_s, instrument):
    if daemon_pid():
        fail('a CassandraDaemon is already running')
    T = None if value == 'default' else int(value) * MIB
    start_node(value, wipe=False)
    p = client('probe')
    if not p.get('ok') or p.get('protocol') != 5:
        fail(f'probe failed or protocol is not 5: {p}')
    note(f'INSTRUMENT probe: release {p["release_version"]} protocol {p["protocol"]}')
    sampler = start_sampler()
    nmt('start')

    # idle control
    t_idle = phase('idle')
    time.sleep(idle_s)
    n_idle = nmt('idle')
    t_a = phase('A')
    ra = client('read', '4', str(a_s), timeout=a_s + 300)
    t_a_end = phase('A_end')
    n_a = nmt('after_A')
    hist_a = tablehist() if instrument else None
    time.sleep(pause_s)

    # B: the client runs in a thread; NMT every 10 s; the main loop watches for the first O > 0
    t_b = phase('B')
    box = {}
    th = threading.Thread(target=read_bg, args=(200, b_client_s, box)); th.start()
    first_o = None
    nmts_b = []
    last_nmt = 0
    while th.is_alive():
        time.sleep(1)
        rows = window(samples(), t_b, 1 << 62)
        if first_o is None:
            for r in rows:
                if r['overflow'] > 0:
                    first_o = r['t0']; log(f'first O > 0 at {first_o} (+{(first_o - t_b) / 1000:.1f} s into B)'); break
        if time.time() - last_nmt >= 10:
            last_nmt = time.time(); nmts_b.append(nmt(f'B_{len(nmts_b):02d}'))
    th.join()
    t_b_end = phase('B_end')
    rb = box.get('r', {})
    time.sleep(after_s)
    t_after = phase('after')
    n_after = nmt('after')
    hist = tablehist()
    info = grep_count('Maximum memory usage reached')
    info_cc = grep_count('Maximum memory usage reached .* for chunk-cache buffer pool, cannot allocate chunk of 8.000MiB')
    oom = grep_count('buffer pool failed to allocate chunk')
    errors = grep_count('^ERROR')
    _, infol = sh("grep -h 'Maximum memory usage reached' logs/system.log || true", check=False)
    open(STOPFILE, 'w').close(); time.sleep(2)
    rows = samples()
    made = made_times()
    for r in rows:
        r['pbm'] = p_bm(r['t0'], made)

    # ---- readings
    idle = window(rows, t_idle, t_a)
    A = window(rows, t_a, t_a_end)
    B = window(rows, t_b, t_b_end)
    post = window(rows, t_after - 5000, t_after + 5000)
    cap = rows[-1]['capacity']
    T = T if T is not None else cap
    ceiling = (T // M) * M
    idle_direct = statistics.median(r['direct_used'] for r in idle)
    idle_pooled = max(r['pooled'] for r in idle)
    idle_pbm = max(r['pbm'] for r in idle)
    dA0, dA1, dB0, dB1 = dump_at(t_a), dump_at(t_a_end), dump_at(t_b), dump_at(t_b_end)
    Bafter = [r for r in B if first_o is not None and r['t0'] >= first_o]
    res = dict(value=value, T=T, capacity=cap, ceiling=ceiling,
               idle_pooled_max=idle_pooled, idle_pbm_max=idle_pbm, made_total=len(made),
               A_pbm_max=max(r['pbm'] for r in A), B_pbm_max=max(r['pbm'] for r in B),
               B_pbm_min_after_first_o=min((r['pbm'] for r in Bafter), default=None), B_pbm_max_after_first_o=max((r['pbm'] for r in Bafter), default=None),
               post_pbm=[r['pbm'] for r in post], A_reads_x20=20 * (ra.get('reads') or 0), idle_overflow_max=max(r['overflow'] for r in idle), idle_direct_median=idle_direct,
               A_pooled_max=max(r['pooled'] for r in A), A_overflow_max=max(r['overflow'] for r in A),
               A_size_max=max(r['size'] for r in A), A_misses_delta=A[-1]['misses'] - A[0]['misses'], A_hits_delta=A[-1]['hits'] - A[0]['hits'],
               A_client=ra,
               B_samples=len(B), B_first_o_ms=first_o, B_first_o_after_s=None if first_o is None else round((first_o - t_b) / 1000, 1),
               B_after_first_o_s=None if first_o is None else round((t_b_end - first_o) / 1000, 1),
               B_pooled_max=max(r['pooled'] for r in B), B_pooled_min_after_first_o=min((r['pooled'] for r in Bafter), default=None),
               B_pooled_max_after_first_o=max((r['pooled'] for r in Bafter), default=None),
               B_overflow_max=max(r['overflow'] for r in B), B_size_max=max(r['size'] for r in B),
               B_used_max=max(r['used'] for r in B),
               B_direct_max=max(r['direct_used'] for r in B), B_direct_rise=max(r['direct_used'] for r in B) - idle_direct,
               B_misses_delta=B[-1]['misses'] - B[0]['misses'], B_hits_delta=B[-1]['hits'] - B[0]['hits'],
               B_net_size_max=max(r['net_size'] for r in B), B_client=rb,
               B_max_inhold=trace_max_inhold(t_b, t_b_end),
               post_pooled=[r['pooled'] for r in post], post_overflow=[r['overflow'] for r in post],
               nmt_idle_other_kb=n_idle['other_kb'], nmt_B_other_max_kb=max((n['other_kb'] or 0) for n in nmts_b) if nmts_b else None,
               nmt_after_other_kb=n_after['other_kb'],
               dump_A0=dA0, dump_A1=dA1, dump_B0=dB0, dump_B1=dB1,
               info_lines=info, info_lines_chunk_cache=info_cc, info_text=infol.strip()[:400], oom_lines=oom, error_lines=errors,
               sstables_per_read=hist, sstables_per_read_A=hist_a)
    res['B_total_peak'] = res['B_size_max']
    res['nmt_B_other_rise_mib'] = None if res['nmt_B_other_max_kb'] is None else round((res['nmt_B_other_max_kb'] - n_idle['other_kb']) / 1024, 1)
    for k in ('A', 'B'):
        d0, d1 = (dA0, dA1) if k == 'A' else (dB0, dB1)
        if d0 and d1:
            for c in ('holds', 'made', 'refuse', 'overflow', 'overflow_bytes'):
                res[f'{k}_bm_{c}'] = d1[c] - d0[c]
    RESULT.update(res)
    mib = lambda x: None if x is None else round(x / MIB, 2)
    note(f'READINGS {value}: Capacity {cap} (T {T}); ceiling {mib(ceiling)} MiB; macro chunks made {len(made)}; '
         f'P (made x 8 MiB) idle {mib(idle_pbm)}, A max {mib(res["A_pbm_max"])}, B max {mib(res["B_pbm_max"])} '
         f'(after first O: {mib(res["B_pbm_min_after_first_o"])}..{mib(res["B_pbm_max_after_first_o"])}) MiB; sampler Size-OverflowSize idle {mib(idle_pooled)}, '
         f'A max {mib(res["A_pooled_max"])}, B max {mib(res["B_pooled_max"])} MiB; idle direct {mib(idle_direct)} MiB; O max A {res["A_overflow_max"]}, '
         f'O peak B {mib(res["B_overflow_max"])} MiB, '
         f'Size peak {mib(res["B_size_max"])} MiB, direct rise {mib(res["B_direct_rise"])} MiB, NMT Other rise {res["nmt_B_other_rise_mib"]} MiB; '
         f'first O at +{res["B_first_o_after_s"]} s, B lasted {res["B_after_first_o_s"]} s after it; max in hold {res["B_max_inhold"]}; '
         f'INFO lines {info} (chunk-cache {info_cc}); OOM lines {oom}; ERROR lines {errors}; SSTables/read {hist}')
    note(f'COUNTERS {value}: A {[res.get("A_bm_" + c) for c in ("holds", "made", "refuse", "overflow")]} B {[res.get("B_bm_" + c) for c in ("holds", "made", "refuse", "overflow", "overflow_bytes")]} '
         f'(holds, made, refuse, overflow[, bytes]); Misses A +{res["A_misses_delta"]} B +{res["B_misses_delta"]}; Hits A +{res["A_hits_delta"]} B +{res["B_hits_delta"]}')
    note(f'CLIENT {value}: A {json.dumps(ra)[:250]} | B {json.dumps(rb)[:250]}')

    # ---- expectations (9a as amended)
    if instrument:
        ok = True
        ok &= expect('instrument: SSTables per read 20 at 50% and 99%', hist_a and hist_a.get('50%') == 20 and hist_a.get('99%') == 20)
        ok &= expect('instrument: reader-demand check, Hits in A >= 0.9 x 20 x A reads (the pool serves the readers)', res['A_hits_delta'] >= 0.9 * res['A_reads_x20'])
        ok &= expect('instrument: O > 0 in B', res['B_overflow_max'] > 0)
        ok &= expect('instrument: refusal and overflow counters move in B', (res.get('B_bm_refuse') or 0) > 0 and (res.get('B_bm_overflow') or 0) > 0)
        ok &= expect('instrument: reads held at once in B >= 150', res['B_max_inhold'] >= 150)
        ok &= expect('instrument: NMT Other parses', n_idle['other_kb'] is not None)
        ok &= expect('instrument: client reads succeed', ra.get('ok') and rb.get('ok'))
        note('INSTRUMENT CHECK ' + ('PASSED' if ok else 'FAILED'))
        json.dump(RESULT, open(D + '/result.json', 'w'), indent=1)
        stop_node()
        sys.exit(0 if ok else 1)

    expect(f'Capacity = T ({T})', cap == T)
    expect('startup line names the value for chunk-cache', ('chunk-cache' in res.get('startup_line', RESULT.get('startup_line', ''))))
    expect('A: P (made x 8 MiB) max <= 16 MiB', res['A_pbm_max'] <= 16 * MIB)
    expect('A: O = 0 at every sample', res['A_overflow_max'] == 0)
    expect('A: no overflow allocation in the trace', res.get('A_bm_overflow') == 0)
    expect('A and B: client reads all succeed with 4 rows', ra.get('ok') and rb.get('ok'))
    expect('B: SSTables per read = 20 (50% and 99%)', hist.get('50%') == 20 and hist.get('99%') == 20)
    expect('B: reads held at once >= 180 (C = 200)', res['B_max_inhold'] >= 180)
    expect('no OOM fallback line', oom == 0)
    if value != 'default' and T < D_B:
        expect(f'B: P (made x 8 MiB) = floor(T/M)*M = {ceiling} at every sample after the first O > 0',
               res['B_pbm_min_after_first_o'] == ceiling and res['B_pbm_max_after_first_o'] == ceiling)
        expect('B: P never above T (made trace, whole lifetime)', len(made) * M <= T)
        expect('B: O > 0', res['B_overflow_max'] > 0)
        expect('B: 120 s or more sampled after the first O > 0', (res['B_after_first_o_s'] or 0) >= 120)
        expect(f'B: P + O_peak in [0.9 D_B, D_B + 16 MiB] = [{0.9 * D_B / MIB:.0f}, {(D_B + 16 * MIB) / MIB:.0f}] MiB',
               0.9 * D_B <= ceiling + res['B_overflow_max'] <= D_B + 16 * MIB)
        expect('B: refusals and overflow allocations counted (trace)', (res.get('B_bm_refuse') or 0) > 0 and (res.get('B_bm_overflow') or 0) > 0)
        expect('B: Misses rises', res['B_misses_delta'] > 0)
        expect('INFO line exactly once, naming chunk-cache and 8MiB', info == 1 and info_cc == 1)
        expect('direct rise in [P + O_peak - 8 MiB, P + O_peak + 40 MiB]',
               ceiling + res['B_overflow_max'] - 8 * MIB <= res['B_direct_rise'] <= ceiling + res['B_overflow_max'] + 40 * MIB)
    else:
        expect('default: B P (made x 8 MiB) max in [248, 264] MiB', 248 * MIB <= res['B_pbm_max'] <= 264 * MIB)
        expect('default: O = 0 at every B sample', res['B_overflow_max'] == 0)
        expect('default: no overflow allocation and no refusal (trace)', res.get('B_bm_overflow') == 0 and res.get('B_bm_refuse') == 0)
        expect('default: no INFO line', info == 0)
        expect('default: direct rise in [P - 8 MiB, P + 40 MiB]',
               res['B_pbm_max'] - 8 * MIB <= res['B_direct_rise'] <= res['B_pbm_max'] + 40 * MIB)
    expect('after B: overflow back to 0 and P unchanged (reservation kept; made trace, and sampler Size-OverflowSize)',
           all(o == 0 for o in res['post_overflow']) and all(p == res['B_pbm_max'] for p in res['post_pbm'])
           and all(p == res['B_pbm_max'] for p in res['post_pooled']))
    json.dump(RESULT, open(D + '/result.json', 'w'), indent=1)
    stop_node()
    if daemon_pid():
        note('WARNING: daemon still running after stop')
    else:
        note('node stopped; no CassandraDaemon left')


def compare():
    rs = {}
    for v in VALUES:
        p = f'{D}/{v}/result.json'
        if os.path.exists(p):
            rs[v] = json.load(open(p))
    if len(rs) != len(VALUES):
        note(f'compare: only {sorted(rs)} present')
    mib = lambda x: round(x / MIB, 2)
    note('value | Capacity | ceiling | P idle | P A max | P B max (min after first O) | O peak | Size peak | direct rise | NMT Other rise | INFO | refuse | overflow')
    for v, r in rs.items():
        note(f'{v} | {r["capacity"]} | {mib(r["ceiling"])} | {mib(r["idle_pbm_max"])} | {mib(r["A_pbm_max"])} | {mib(r["B_pbm_max"])} '
             f'({None if r["B_pbm_min_after_first_o"] is None else mib(r["B_pbm_min_after_first_o"])}) | {mib(r["B_overflow_max"])} | '
             f'{mib(r["B_size_max"])} | {mib(r["B_direct_rise"])} | {r["nmt_B_other_rise_mib"]} | {r["info_lines"]} | {r.get("B_bm_refuse")} | {r.get("B_bm_overflow")}')
    sat = [v for v in ('16', '64', '100', '128') if v in rs]
    if len(sat) == 4:
        steps = [rs[v]['B_pbm_max'] for v in sat]
        expect('pooled plateau moves with T: 16, 64, 96, 128 MiB', [mib(s) for s in steps] == [16, 64, 96, 128])
        tot = [rs[v]['ceiling'] + rs[v]['B_overflow_max'] for v in sat]
        expect(f'total P + O_peak spread across the saturated values <= 28 MiB (got {mib(max(tot) - min(tot))})', max(tot) - min(tot) <= 28 * MIB)
    have = [v for v in VALUES if v in rs]
    rises = [rs[v]['B_direct_rise'] for v in have]
    expect(f'direct rise spread across all values <= 28 MiB (got {mib(max(rises) - min(rises))})', max(rises) - min(rises) <= 28 * MIB)
    nm = [rs[v]['nmt_B_other_rise_mib'] for v in have if rs[v]['nmt_B_other_rise_mib'] is not None]
    if nm:
        expect(f'NMT Other rise spread across all values <= 28 MiB (got {max(nm) - min(nm):.1f})', max(nm) - min(nm) <= 28)
    if '16' in rs and '128' in rs:
        note(f'pooled change 16 -> 128: {mib(rs["128"]["B_pbm_max"] - rs["16"]["B_pbm_max"])} MiB; direct-rise change: '
             f'{mib(rs["128"]["B_direct_rise"] - rs["16"]["B_direct_rise"])} MiB')


try:
    if MODE == 'build':
        build()
    elif MODE == 'instrument':
        lifetime('16', idle_s=10, a_s=20, pause_s=5, b_client_s=20, b_after_first_o_s=0, after_s=5, instrument=True)
    elif MODE == 'value':
        lifetime(ARG, idle_s=60, a_s=30, pause_s=20, b_client_s=150, b_after_first_o_s=120, after_s=30, instrument=False)
    else:
        compare()
except SystemExit:
    raise
except BaseException as e:
    note(f'FAIL: exception {e!r}')
    stop_node()
    sys.exit(1)
