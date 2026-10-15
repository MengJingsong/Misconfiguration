#!/usr/bin/env python3
"""Stage 4, cluster tier, Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE (case 9b-9e, amended 2026-10-15).
usage: cluster-run.py <run> life1 [table,table,...]   lifetime 1: instrument probe, control c32, big (real limit),
                                                       t8 t32 t32a t32b t32c t128 (moved limit), restart check
       cluster-run.py <run> armE                      lifetimes 2-4: cassandra.index_summary_expected_key_size=65536 (second site)

One node from $CASSANDRA_HOME (default ~/cassandra-run3), CASSANDRA_CONF ~/stage4-imv/conf, every directory under ~/stage4-imv/,
heap 24G, the Byteman agent with summary-trace.btm and its listener on 19091 (9091 may be another session's); moved limits are submitted and unloaded per table.
Writes summary.txt (EXPECTED lines), tables.csv, reads.jsonl, session.log, imv.trace and the node's logs to
~/stage4-logs/imv/<run>/<label>/. Exit 1: a set-up or instrument check failed. The node is stopped on any exit."""
import csv, glob, json, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run3')
HARNESS = os.path.dirname(os.path.abspath(__file__))
N_DIR = HOME + '/stage4-imv'
BM = C + '/build/lib/jars/byteman-4.0.20.jar'
BM_SUBMIT = C + '/build/lib/jars/byteman-submit-4.0.20.jar'
MIB = 1048576
MAXI = 2147483647
JMXPORT = 7199
PROP = '-Dcassandra.index_summary_expected_key_size=65536'
TABLE_OPTS = ("WITH min_index_interval = 1 AND caching = {'keys': 'NONE', 'rows_per_partition': 'NONE'} "
              "AND compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'}")
# name, moved limit in MiB (None = real limit), K, N, seed
LIFE1 = [('c32', None, 1000, 41610, 32), ('big', None, 60000, 40000, 60), ('t8', 8, 1000, 10403, 8), ('t32', 32, 1000, 41610, 32),
         ('t32a', 32, 1000, 33288, 33), ('t32b', 32, 1000, 33289, 33), ('t32c', 32, 1000, 83220, 34), ('t128', 128, 1000, 166440, 128)]

if len(sys.argv) < 3 or sys.argv[2] not in ('life1', 'armE'):
    sys.exit(__doc__)
RUN, label = sys.argv[1], sys.argv[2]
ONLY = set(sys.argv[3].split(',')) if len(sys.argv) > 3 else None
D = f'{HOME}/stage4-logs/imv/{RUN}/{label}'
if os.path.exists(D):
    os.rename(D, D + '.' + time.strftime('%Y%m%d-%H%M%S', time.localtime(os.path.getmtime(D))))
os.makedirs(D)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'w')
TABLES = csv.writer(open(D + '/tables.csv', 'w'))
TABLES.writerow(['table', 'L', 'K', 'N', 'nstar', 'kept_pred', 'count', 'entriesLength', 'capacity', 'refused_keysWritten', 'refused_length',
                 'errors', 'gauge', 'summary_db', 'datadb_files', 'effective', 'entriesCapacity_init', 'warns'])
READS = open(D + '/reads.jsonl', 'w')
TRACE = D + '/imv.trace'
SYSTEM_LOG = N_DIR + '/logs/system.log'
DEBUG_LOG = N_DIR + '/logs/debug.log'


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr)
    SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=900, check=True, env=None, quiet=False):
    if not quiet:
        log('+ ' + (cmd if isinstance(cmd, str) else ' '.join(cmd)))
    r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout, env=env, cwd=C)
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet or r.returncode != 0:
        SESSION.write(out[-4000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-800:]}')
    return r.returncode, out


def pid():
    r = subprocess.run("pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon'", shell=True, capture_output=True, text=True)
    return int(r.stdout.split()[0]) if r.returncode == 0 else None


def stop_node():
    if pid():
        sh('bin/nodetool drain', check=False, quiet=True, timeout=600)
        sh('bin/nodetool stopdaemon', check=False, quiet=True, timeout=120)
        for _ in range(120):
            if not pid():
                break
            time.sleep(1)
        if pid():
            log('stopdaemon did not stop the node: kill -9')
            subprocess.run("pkill -9 -f '[o]rg.apache.cassandra.service.CassandraDaemon'", shell=True)
            time.sleep(2)


def fail(msg):
    note('FAIL: ' + msg)
    stop_node()
    sys.exit(1)


def expect(desc, cond):
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def size_of(p):
    try:
        return os.path.getsize(p)
    except FileNotFoundError:
        return 0


def read_since(p, off):
    try:
        with open(p, 'rb') as f:
            f.seek(off)
            return f.read().decode('utf-8', 'replace')
    except FileNotFoundError:
        return ''


def make_yaml():
    sh(f'rm -rf {N_DIR}/conf && mkdir -p {N_DIR}/logs && cp -r {C}/conf {N_DIR}/conf && git -C {C} show HEAD:conf/cassandra.yaml > {N_DIR}/shipped.yaml')
    lines = ['cluster_name: stage4-imv', 'data_file_directories:', f'    - {N_DIR}/data', f'commitlog_directory: {N_DIR}/commitlog',
             f'hints_directory: {N_DIR}/hints', f'saved_caches_directory: {N_DIR}/saved_caches', f'cdc_raw_directory: {N_DIR}/cdc_raw',
             'index_summary_resize_interval:', 'memtable_heap_space: 12GiB', 'commitlog_total_space: 8192MiB',
             'read_request_timeout: 60000ms', 'native_transport_timeout: 120000ms']
    keys = {l.split(':', 1)[0] for l in lines if re.match(r'^[A-Za-z_]+:', l)}
    out, skip = [], False
    for l in open(N_DIR + '/shipped.yaml').read().splitlines():
        m = re.match(r'^([A-Za-z_]+):', l)
        if m:
            skip = m.group(1) in keys
            if skip:
                continue
        elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == '' or l.lstrip().startswith('#')):
            continue
        else:
            skip = False
        out.append(l)
    open(N_DIR + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 imv lines ----\n' + '\n'.join(lines) + '\n')
    note('YAML lines: ' + '; '.join(lines))


def start_node(tag, prop=False):
    if pid():
        fail('a CassandraDaemon is already running')
    jopts = f'-javaagent:{BM}=script:{HARNESS}/summary-trace.btm,listener:true,port:19091 -Dstage4.trace={TRACE}' + (f' {PROP}' if prop else '')
    env = dict(os.environ, CASSANDRA_CONF=N_DIR + '/conf', CASSANDRA_LOG_DIR=N_DIR + '/logs', MAX_HEAP_SIZE='24G', JVM_EXTRA_OPTS=jopts)
    env.pop('HEAP_NEWSIZE', None)
    off = size_of(DEBUG_LOG)
    sh(f'bin/cassandra -p {N_DIR}/cassandra.pid > {D}/startup-{tag}.log 2>&1', env=env)
    t0 = time.time()
    while time.time() - t0 < 600:
        if not pid() and time.time() - t0 > 5:
            fail(f'the node died during start ({tag})')
        _, st = sh('bin/nodetool statusbinary', check=False, quiet=True)
        _, ns = sh('bin/nodetool status', check=False, quiet=True)
        if re.search(r'^running\s*$', st, re.M) and re.search(r'^UN', ns, re.M):
            break
        time.sleep(2)
    else:
        fail(f'node did not come up ({tag})')
    _, sl = sh(f'java -cp {BM_SUBMIT} org.jboss.byteman.agent.submit.Submit -p 19091 -l', check=False)
    rules = re.findall(r'^RULE (.*)$', sl, re.M)
    note(f'node up ({tag}) after {time.time() - t0:.0f} s, pid {pid()}, property {"set" if prop else "not set"}; Submit -l rules {rules}')
    if sum(1 for r in rules if r.startswith('imv ')) != 8:
        fail('the trace rules are not all loaded')
    return off


def jmx_get(*pairs):
    args = ' '.join(f"'{x}'" for p in pairs for x in p)
    _, out = sh(f'java -cp {D}/jmxcls Jmx {JMXPORT} get {args}', check=False, quiet=True)
    v = {}
    for l in out.splitlines():
        p = l.split('|', 2)
        if len(p) == 3:
            v[(p[0], p[1])] = p[2]
    return v


def gauge(ks, t):
    b = f'org.apache.cassandra.metrics:type=Table,keyspace={ks},scope={t},name=IndexSummaryOffHeapMemoryUsed'
    v = jmx_get((b, 'Value')).get((b, 'Value'))
    return int(v) if v is not None and v.lstrip('-').isdigit() else None


def rss():
    try:
        return int(re.search(r'RssAnon:\s+(\d+) kB', open(f'/proc/{pid()}/status').read()).group(1)) * 1024
    except Exception:
        return None


def submit(args):
    return sh(f'java -cp {BM_SUBMIT} org.jboss.byteman.agent.submit.Submit -p 19091 {args}', check=False)


def cql(stmt):
    return sh(['bin/cqlsh', '-e', stmt], timeout=120)


def trace_lines(off):
    return [l.strip() for l in read_since(TRACE, off).splitlines() if l.strip()]


def kv(line):
    return dict(re.findall(r'(\w+)=(\S+)', line))


def flush_and_read(ks, t, L, K, N, seed, do_reads=True, rule=None):
    """Load (done by the caller), flush, the readings of 9d; returns the parsed record."""
    path_frag = f'/{ks}/{t}-'
    datadir = glob.glob(f'{N_DIR}/data/{ks}/{t}-*')
    pre = len(glob.glob(f'{N_DIR}/data/{ks}/{t}-*/*-Data.db'))
    if pre:
        note(f'NOTE {t}: {pre} Data.db before the manual flush (an automatic flush ran)')
    off_tr, off_sys = size_of(TRACE), size_of(SYSTEM_LOG)
    sh(f'bin/nodetool flush {ks} {t}', timeout=1800)
    time.sleep(3)
    tl = trace_lines(off_tr)
    writers = [kv(l) for l in tl if l.startswith('writer ') and path_frag in l]
    ids = {w['id'] for w in writers}
    init = [kv(l) for l in tl if l.startswith('init ') and kv(l).get('id') in ids]
    refused = [kv(l) for l in tl if l.startswith('refused ') and kv(l).get('id') in ids]
    built = [kv(l) for l in tl if l.startswith('built ') and kv(l).get('id') in ids]
    sysnew = read_since(SYSTEM_LOG, off_sys)
    errors = sysnew.count('Memory capacity of index summary exceeded')
    warns = sysnew.count('is too low for')
    files = glob.glob(f'{N_DIR}/data/{ks}/{t}-*/*-Data.db')
    summ = glob.glob(f'{N_DIR}/data/{ks}/{t}-*/*-Summary.db')
    g = gauge(ks, t)
    rec = dict(table=t, L=L, K=K, N=N, writers=len(writers), init=init, refused=refused, built=built, errors=errors, warns=warns,
               datadb=len(files), names=[os.path.basename(f) for f in files], summary_db=size_of(summ[0]) if summ else None, gauge=g)
    note(f'OBSERVED {t}: writer lines {len(writers)}; init {init}; refused {refused}; built {built}; ERROR lines {errors}; WARN lines {warns}; '
         f'Data.db files {[os.path.basename(f) for f in files]}; Summary.db {rec["summary_db"]}; gauge {g}')
    return rec


def judge(rec, nstar, kept, refuse, prop_e=None):
    t, K, N = rec['table'], rec['K'], rec['N']
    b = rec['built'][0] if rec['built'] else {}
    r = rec['refused'][0] if rec['refused'] else {}
    i0 = rec['init'][0] if rec['init'] else {}
    TABLES.writerow([t, rec['L'], K, N, nstar, kept, b.get('count'), b.get('entriesLength'), b.get('capacity'), r.get('keysWritten'), r.get('length'),
                     rec['errors'], rec['gauge'], rec['summary_db'], rec['datadb'], i0.get('effective'), i0.get('entriesCapacity'), rec['warns']])
    same = [{k: v for k, v in x.items() if k != 'ms'} for x in rec['built']]
    expect(f'{t}: one SSTable (one Data.db), one writer and init line, built lines ({len(rec["built"])}) all identical',
           rec['datadb'] == 1 and rec['writers'] == 1 and len(rec['init']) == 1 and len(rec['built']) >= 1 and all(x == same[0] for x in same))
    if not rec['built']:
        return
    expect(f'{t}: entries kept {kept} (built count)', int(b['count']) == kept)
    eL = kept * (K + 8)
    expect(f'{t}: entriesLength {eL} and the trimmed capacity equal to it', int(b['entriesLength']) == eL and int(b['capacity']) == eL)
    expect(f'{t}: gauge = kept x (K + 12) = {kept * (K + 12)}', rec['gauge'] == kept * (K + 12))
    expect(f'{t}: Summary.db = 24 + gauge + 2 (K + 4) = {24 + kept * (K + 12) + 2 * (K + 4)}', rec['summary_db'] == 24 + kept * (K + 12) + 2 * (K + 4))
    if refuse:
        expect(f'{t}: one refused line at keysWritten = n* = {nstar} with length {nstar * (K + 8)}, and one ERROR line',
               len(rec['refused']) == 1 and int(r['keysWritten']) == nstar and int(r['length']) == nstar * (K + 8) and rec['errors'] == 1)
    else:
        expect(f'{t}: no refused line and no ERROR line', not rec['refused'] and rec['errors'] == 0)


def reads(ks, t, K, N, seed, nstar):
    _, out = sh(['python3', f'{HARNESS}/read-keys.py', f'{ks}.{t}', str(N), str(K), str(seed), str(nstar), TRACE], timeout=1800, check=False)
    lines = [json.loads(l) for l in out.splitlines() if l.startswith('{')]
    for l in lines:
        READS.write(json.dumps(dict(l, table=t)) + '\n')
    READS.flush()
    head = lines[0] if lines else {}
    rd = [l for l in lines if 'rank' in l]
    ok_found = all(l['found'] and l['v'] == l['index'] for l in rd)
    skips = [(l['rank'], [int(kv(s).get('skips', -1)) for s in l['scan']], l['predicted_skips']) for l in rd]
    note(f'READS {t}: scan rows {head.get("scan_rows")} of {N} (distinct {head.get("distinct")}); per read (rank, scan skips, predicted): {skips}')
    expect(f'{t}: the token scan returned all {N} rows', head.get('scan_rows') == N and head.get('distinct') == N)
    expect(f'{t}: every point read returned its row (v = index)', bool(rd) and ok_found)
    expect(f'{t}: every point read has exactly one scan line with skips = predicted (r < n*: 0; else r - n* + 1)',
           bool(rd) and all(len(s) == 1 and s[0] == p for _, s, p in skips))
    return rd


def table_cycle(ks, t, Lmib, K, N, seed):
    L = Lmib * MIB if Lmib else MAXI
    nstar = L // (K + 8)
    kept = min(N, nstar)
    refuse = N > nstar
    note(f'TABLE {ks}.{t}: L {L}{" (moved, " + str(Lmib) + " MiB)" if Lmib else " (real)"}; K {K}; N {N}; seed {seed}; n* {nstar}; kept {kept}; refusal {refuse}')
    cql(f'CREATE TABLE {ks}.{t} (k blob PRIMARY KEY, v int) {TABLE_OPTS}')
    if Lmib:
        rc, o = submit(f'{HARNESS}/moved-limit-{Lmib}.btm')
        _, sl = submit('-l')
        moved = re.findall(r'^RULE (moved limit .*)$', sl, re.M)
        note(f'RULE submitted moved-limit-{Lmib}.btm rc {rc}; moved rules listed {moved}')
        if moved != [f'moved limit {Lmib} MiB']:
            fail(f'the moved-limit rule in force is {moved}, not {Lmib} MiB')
    else:
        _, sl = submit('-l')
        if re.findall(r'^RULE (moved limit .*)$', sl, re.M):
            fail('a moved-limit rule is loaded for a real-limit table')
    if t == 'big':
        note(f'RSS big: before load {rss()}')
    _, o = sh(['python3', f'{HARNESS}/load-keys.py', f'{ks}.{t}', str(N), str(K), str(seed)], timeout=3600)
    note(o.strip().splitlines()[-1])
    rec = flush_and_read(ks, t, L, K, N, seed)
    judge(rec, nstar, kept, refuse)
    t_flush = time.time()
    if t == 'big':
        note(f'RSS big: after the flush {rss()}')
    reads(ks, t, K, N, seed, nstar)
    if Lmib:
        rc, o = submit(f'-u {HARNESS}/moved-limit-{Lmib}.btm')
        _, sl = submit('-l')
        note(f'RULE unloaded rc {rc}; moved rules left {re.findall(r"^RULE (moved limit .*)$", sl, re.M)}')
    if t == 'big':
        wait = 300 - (time.time() - t_flush)
        if wait > 0:
            time.sleep(wait)
        note(f'RSS big: {time.time() - t_flush:.0f} s after the flush {rss()}; gauge {gauge(ks, t)}')
    return rec, nstar


def probe():
    note('INSTRUMENT CHECK (not a reading): probe, 9,000 keys of 1,000 B, moved-limit-8 rule')
    cql(f'CREATE TABLE ks.probe (k blob PRIMARY KEY, v int) {TABLE_OPTS}')
    submit(f'{HARNESS}/moved-limit-8.btm')
    sh(['python3', f'{HARNESS}/load-keys.py', 'ks.probe', '9000', '1000', '9'], timeout=600)
    rec = flush_and_read('ks', 'probe', 8 * MIB, 1000, 9000, 9)
    rd = reads('ks', 'probe', 1000, 9000, 9, 8322)
    submit(f'-u {HARNESS}/moved-limit-8.btm')
    cql('DROP TABLE ks.probe')
    ok = rec['writers'] == 1 and rec['init'] and rec['refused'] and rec['built'] and rec['errors'] == 1 \
        and int(rec['refused'][0]['keysWritten']) == 8322 and rd and all(len(l['scan']) == 1 for l in rd)
    note(f'INSTRUMENT CHECK {"passed" if ok else "FAILED"}')
    if not ok:
        fail('a silent or wrong instrument in the probe (9e "Before the cluster tier" 2)')


def life1():
    make_yaml()
    sh(f'rm -rf {N_DIR}/data {N_DIR}/commitlog {N_DIR}/hints {N_DIR}/saved_caches {N_DIR}/cdc_raw {N_DIR}/logs && mkdir -p {N_DIR}/logs')
    start_node('life1')
    v = jmx_get(('org.apache.cassandra.db:type=IndexSummaries', 'ResizeIntervalInMinutes'))
    ri = list(v.values())[0] if v else None
    note(f'ResizeIntervalInMinutes {ri}')
    if ri != '-1':
        fail('index summary redistribution is not off')
    cql("CREATE KEYSPACE ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
    probe()
    note(f'IDLE: RssAnon {rss()}')
    recs = {}
    for t, Lmib, K, N, seed in LIFE1:
        if ONLY and t not in ONLY:
            continue
        recs[t] = table_cycle('ks', t, Lmib, K, N, seed)
    ns = {t: recs[t][1] for t in recs}
    if all(x in ns for x in ('t8', 't32', 't128')):
        expect(f'dose-response: n* 8,322 : 33,288 : 133,152 across 8, 32, 128 MiB (observed {[int(recs[x][0]["built"][0]["count"]) for x in ("t8", "t32", "t128") if recs[x][0]["built"]]})',
               [int(recs[x][0]['built'][0]['count']) for x in ('t8', 't32', 't128') if recs[x][0]['built']] == [8322, 33288, 133152])
    if 'big' in recs:
        g0 = recs['big'][0]['gauge']
        stop_node()
        off = start_node('life1-restart')
        time.sleep(5)
        dbg = read_since(DEBUG_LOG, off)
        corrupted = [l for l in dbg.splitlines() if 'Index summary file is corrupted' in l and '/ks/big-' in l]
        tl = [l for l in read_since(TRACE, 0).splitlines()]
        g1 = gauge('ks', 'big')
        note(f'RESTART: big corrupted lines {len(corrupted)}; gauge before {g0} after {g1}')
        expect('restart: big loads from Summary.db without a rebuild (no corrupted line) with the same gauge', not corrupted and g1 == g0)
        reads('ks', 'big', 60000, 40000, 60, MAXI // 60008)


def armE():
    make_yaml()
    sh(f'rm -rf {N_DIR}/data {N_DIR}/commitlog {N_DIR}/hints {N_DIR}/saved_caches {N_DIR}/cdc_raw {N_DIR}/logs && mkdir -p {N_DIR}/logs')
    start_node('life2', prop=True)
    cql("CREATE KEYSPACE ks2 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
    pred = {'e41': (41610, 2, 1363642920, 20805), 'e30': (30000, 1, 1966320000, 30000)}
    for t, seed in (('e41', 41), ('e30', 30)):
        N, e, cap, kept = pred[t]
        cql(f'CREATE TABLE ks2.{t} (k blob PRIMARY KEY, v int) {TABLE_OPTS}')
        _, o = sh(['python3', f'{HARNESS}/load-keys.py', f'ks2.{t}', str(N), '1000', str(seed)], timeout=1800)
        note(o.strip().splitlines()[-1])
        rec = flush_and_read('ks2', t, MAXI, 1000, N, seed)
        judge(rec, kept, kept, False)
        i0 = rec['init'][0] if rec['init'] else {}
        expect(f'{t}: init effective interval {e}, entriesCapacity {cap}, WARN lines {1 if e == 2 else 0}',
               i0.get('effective') == str(e) and i0.get('entriesCapacity') == str(cap) and rec['warns'] == (1 if e == 2 else 0))
    note('IndexIntervals ' + str(jmx_get(('org.apache.cassandra.db:type=IndexSummaries', 'IndexIntervals'))))
    for tag, prop in (('life3', True), ('life4', False), ('life4b', False)):
        stop_node()
        off_tr, off_dbg, off_sys = size_of(TRACE), size_of(DEBUG_LOG), size_of(SYSTEM_LOG)
        start_node(tag, prop=prop)
        time.sleep(5)
        dbg, sysn = read_since(DEBUG_LOG, off_dbg), read_since(SYSTEM_LOG, off_sys)
        tl = trace_lines(off_tr)
        reb = [l for l in tl if l.startswith('rebuild ') and '/ks2/' in l]
        corrupted = {t: [l for l in dbg.splitlines() if 'Index summary file is corrupted' in l and f'/ks2/{t}-' in l] for t in ('e41', 'e30')}
        cause = re.findall(r'min_index_interval changed from \d+ to \d+', dbg)
        warns = sysn.count('is too low for')
        inits = [l for l in tl if l.startswith('init ')]
        builts = [l for l in tl if l.startswith('built ')]
        g = {t: gauge('ks2', t) for t in ('e41', 'e30')}
        note(f'{tag}: rebuild lines {reb}; corrupted e41 {len(corrupted["e41"])} e30 {len(corrupted["e30"])}; causes {cause}; WARN {warns}; '
             f'init lines {inits[-4:]}; built lines {builts[-4:]}; gauges {g}')
        note(f'{tag}: IndexIntervals ' + str(jmx_get(('org.apache.cassandra.db:type=IndexSummaries', 'IndexIntervals'))))
        if tag == 'life3':
            expect('life3 (property): e41 Summary.db refused (corrupted, min_index_interval changed from 2 to 1) and rebuilt; e30 loaded',
                   len(corrupted['e41']) >= 1 and not corrupted['e30'] and 'min_index_interval changed from 2 to 1' in cause)
            expect('life3: one WARN line for the rebuild (interval 2) and e41 gauge back to 21,054,660', warns == 1 and g['e41'] == 21054660)
        elif tag == 'life4':
            expect('life4 (no property): e41 refused again and rebuilt at interval 1 with no WARN; gauge 41,610 x 1,012 = 42,109,320',
                   len(corrupted['e41']) >= 1 and warns == 0 and g['e41'] == 42109320)
        else:
            expect('life4b: e41 loads without a rebuild (no corrupted line), gauge unchanged', not corrupted['e41'] and g['e41'] == 42109320)


try:
    note(f'RUN {RUN} LABEL {label}{" ONLY " + ",".join(sorted(ONLY)) if ONLY else ""}; date {time.strftime("%F %T %Z")}; host {os.uname().nodename}')
    note('CLONE ' + sh('git describe --tags && git rev-parse --short HEAD')[1].replace('\n', ' ').strip() + ' | HARNESS md5 ' +
         sh(f'cd {HARNESS} && md5sum *.btm *.py *.sh *.java | md5sum')[1].split()[0])
    if pid():
        fail('a CassandraDaemon is already running')
    _, ts = sh(f'java -classpath {BM}:build/classes/main:"build/lib/jars/*":"lib/*" org.jboss.byteman.check.TestScript {HARNESS}/summary-trace.btm '
               f'{HARNESS}/moved-limit-8.btm {HARNESS}/moved-limit-32.btm {HARNESS}/moved-limit-128.btm', check=False)
    note('Byteman TestScript: ' + ('no errors' if 'TestScript: no errors' in ts else 'ERRORS'))
    if 'TestScript: no errors' not in ts:
        fail('Byteman TestScript reports errors')
    sh(f'mkdir -p {D}/jmxcls && javac -d {D}/jmxcls {HARNESS}/Jmx.java')
    life1() if label == 'life1' else armE()
    note('DONE')
except SystemExit:
    raise
except Exception as e:
    import traceback
    note(f'FAIL (exception): {e!r}')
    SESSION.write(traceback.format_exc()); SESSION.flush()
    sys.exit(1)
finally:
    stop_node()
    subprocess.run(f'cp {N_DIR}/logs/system.log {N_DIR}/logs/debug.log {N_DIR}/conf/cassandra.yaml {D}/ 2>/dev/null; '
                   f'ls -laR {N_DIR}/data/ks {N_DIR}/data/ks2 > {D}/data-final.txt 2>&1', shell=True)
