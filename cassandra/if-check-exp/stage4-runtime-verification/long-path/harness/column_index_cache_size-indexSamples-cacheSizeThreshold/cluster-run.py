#!/usr/bin/env python3
"""Stage 4, cluster tier, column_index_cache_size-indexSamples-cacheSizeThreshold (case 9b-9e, amended 2026-10-14).
usage: cluster-run.py instrument | run
  instrument  shakedown (not a reading): a small dataset, the write/read/fetch trace lines, JMX get/set/invoke, the census at
              2 KiB (C1 shape indexed) and at 0 (shallow + fetch lines), then stop. Logs: ~/stage4-logs/cics/instrument/
  run         run 1, one node lifetime: load C1, CB, C2, C3, C4 with flushes at partition boundaries; dataset check; the 9e
              instrument check; the sweep T = 0, 2, 16, 256 KiB with every class read at every value; live flip 256 -> 16 KiB on
              C3; large-cache arm; arm W. Logs: ~/stage4-logs/cics/run1/
One node (~/cassandra-run1), RF 1, MAX_HEAP_SIZE=4G, Byteman agent with index-trace.btm. Every command is logged to session.log;
EXPECTED lines go to summary.txt; one row per pass goes to readings.csv. Exit 1: an instrument/dataset check failed. The node is
stopped on any exit."""
import csv, json, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
BM = C + '/build/lib/jars'
MODE = sys.argv[1]
D = f'{HOME}/stage4-logs/cics/' + ('instrument' if MODE == 'instrument' else 'run1')
os.makedirs(D, exist_ok=True)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'w')
RCSV_F = open(D + '/readings.csv', 'w')
RCSV = csv.writer(RCSV_F)
RCSV.writerow(['arm', 'T', 'class', 'P', 'n', 'S', 'h', 'disk_lines', 'disk_pks', 'cache_lines', 'indexed_lines', 'shallow_lines', 'branch_mismatches',
               'fetch_lines', 'fetch_reads_min', 'entries_before', 'entries_after', 'size_before', 'size_after', 'capacity', 'iireads_delta',
               'census_indexed', 'census_indexed_bytes', 'census_shallow', 'census_indexinfo', 'census_indexinfo_bytes', 'heap_used_kb', 'elapsed_s'])
TRACE = D + '/index.trace'
SYSLOG = C + '/logs/system.log'
KC = 'org.apache.cassandra.metrics:type=Cache,scope=KeyCache,name='
IIR = 'org.apache.cassandra.metrics:type=Index,scope=RowIndexEntry,name=IndexInfoReads'
SS = 'org.apache.cassandra.db:type=StorageService'
CACHES = 'org.apache.cassandra.db:type=Caches'
K = 8 * 1024 * 1024
TS_KIB = [0, 2, 16, 256]

# class: (table, pks, rows per pk (dict pk->rows), read ck, flush every N partitions, target S)
def cls_def(pk_lo, pk_hi, rows, every, target):
    return dict(pks=list(range(pk_lo, pk_hi + 1)), rows={p: rows for p in range(pk_lo, pk_hi + 1)}, ck=rows // 2, every=every, target=target)

if MODE == 'instrument':
    CLASSES = {'C1': cls_def(1, 5, 120, 5, 1024), 'C2': cls_def(10001, 10002, 1000, 2, 8192)}
else:
    CLASSES = {'C1': cls_def(1, 2000, 120, 800, 1024), 'C2': cls_def(10001, 10500, 1000, 100, 8192),
               'C3': cls_def(20001, 20100, 8000, 12, 65536), 'C4': cls_def(30001, 30016, 64000, 1, 524288)}
    CB = dict(pks=list(range(5001, 5022)), rows={5001 + i: 240 + 4 * i for i in range(21)}, ck=120, every=21, target=None)
    CLASSES = {'C1': CLASSES['C1'], 'CB': CB, 'C2': CLASSES['C2'], 'C3': CLASSES['C3'], 'C4': CLASSES['C4']}
ORDER = list(CLASSES)


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr); SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=600, check=True, env=None, cwd=C):
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
    sh('git checkout -q conf/cassandra.yaml', check=False)


def fail(msg):
    note('FAIL: ' + msg); stop_node(); sys.exit(1)


def expect(desc, cond):
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def jmx(*args):
    _, out = sh(['java', '-cp', D + '/jmx-classes', 'Jmx', *args], check=False)
    return out


def jmx_get(*pairs):
    out = jmx('get', *[x for p in pairs for x in p])
    vals = {}
    for l in out.splitlines():
        parts = l.split('|')
        if len(parts) == 3:
            vals[(parts[0], parts[1])] = parts[2]
    return vals


def snap():
    v = jmx_get((KC + 'Entries', 'Value'), (KC + 'Size', 'Value'), (KC + 'Capacity', 'Value'), (IIR, 'Count'))
    g = lambda k: int(float(v[k])) if k in v and v[k] not in ('NaN', 'null') else None
    return dict(entries=g((KC + 'Entries', 'Value')), size=g((KC + 'Size', 'Value')), capacity=g((KC + 'Capacity', 'Value')), iir=g((IIR, 'Count')))


def set_t(kib):
    out = jmx('set', SS, 'ColumnIndexCacheSizeInKiB', f'int:{kib}')
    got = jmx_get((SS, 'ColumnIndexCacheSizeInKiB')).get((SS, 'ColumnIndexCacheSizeInKiB'))
    note(f'SET column_index_cache_size {kib} KiB over JMX; read back {got}')
    if str(got) != str(kib):
        fail(f'JMX read-back {got} != {kib}')


def set_cache_mb(mb):
    jmx('setonly', CACHES, 'KeyCacheCapacityInMB', f'long:{mb}')
    cap = snap()['capacity']
    note(f'SET key cache capacity {mb} MiB; Capacity gauge {cap}')
    return cap


def client(*args, timeout=3600):
    r = subprocess.run([sys.executable, f'{HARNESS}/send-cql.py', *args], capture_output=True, text=True, timeout=timeout)
    log('+ send-cql.py ' + ' '.join(args)[:200]); SESSION.write(r.stderr[-500:] + '\n'); SESSION.flush()
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {'ok': False, 'error': 'ClientFailure', 'message': (r.stdout + r.stderr)[-400:]}


trace_seen = 0
KEY = re.compile(r'key=DecoratedKey\((-?\d+), ([0-9a-f]+)\)')


def new_trace():
    global trace_seen
    time.sleep(0.5)
    if not os.path.exists(TRACE):
        return []
    lines = open(TRACE).read().splitlines()
    new = lines[trace_seen:]; trace_seen = len(lines)
    return new


def fields(l):
    d = dict(re.findall(r'(\w+)=(\S+)', KEY.sub('', l)))
    m = KEY.search(l)
    if m:
        d['pk'] = int(m.group(2), 16)
    d['kind'] = l.split(' ', 1)[0]
    return d


def census(tag):
    pid = daemon_pid()
    _, out = sh(f'{HARNESS}/histo.sh {pid} {D}/histo/{tag}.txt')
    d = dict(re.findall(r'(\w+)=(\d+)', out.strip().splitlines()[-1]))
    return {k: int(v) for k, v in d.items()}


def datafiles(table='t'):
    _, ls = sh(f'ls data/data/ks1/{table}-*/ | grep -- -Data.db || true', check=False)
    return sorted(ls.split())


WRITE = {}      # pk -> (n, S, class, T)
H = {}          # class -> set of h observed
SHALLOW_W = []  # per-entry Size delta of shallow passes
PASSES = {}     # (arm, T, class) -> dict


def load_class(name):
    c = CLASSES[name]
    pks = c['pks']
    if len(set(c['rows'].values())) == 1:
        for i in range(0, len(pks), c['every']):
            chunk = pks[i:i + c['every']]
            r = client('load', 'ks1.t', str(chunk[0]), str(chunk[-1]), str(c['rows'][chunk[0]]))
            if not r.get('ok'):
                fail(f'load {name} {chunk[0]}..{chunk[-1]} failed: {r}')
            sh('bin/nodetool flush ks1 t')
    else:
        for pk in pks:
            r = client('load', 'ks1.t', str(pk), str(pk), str(c['rows'][pk]))
            if not r.get('ok'):
                fail(f'load {name} pk {pk} failed: {r}')
        sh('bin/nodetool flush ks1 t')
    note(f'LOADED {name}: {len(pks)} partitions, rows {sorted(set(c["rows"].values()))[:3]}..., flush every {c["every"]}')


def dataset_check():
    lines = [fields(l) for l in new_trace() if l.startswith('write ')]
    by_pk = {}
    for f in lines:
        if f.get('tbl') == 't':
            by_pk.setdefault(f['pk'], []).append(f)
    files = datafiles()
    big = all(re.match(r'nb-\d+-big-Data.db$', x) for x in files)
    note(f'DATASET Data.db files {len(files)}; all nb-*-big: {big}; write lines for ks1.t {sum(len(v) for v in by_pk.values())}')
    if not big:
        fail('an SSTable is not BIG/nb')
    ok = True
    for name in ORDER:
        c = CLASSES[name]
        missing = [p for p in c['pks'] if p not in by_pk]
        dup = [p for p in c['pks'] if len(by_pk.get(p, [])) > 1]
        if missing or dup:
            note(f'DATASET {name}: missing write lines {missing[:5]} ({len(missing)}), more than one line {dup[:5]} ({len(dup)})')
            ok = False
            continue
        for p in c['pks']:
            f = by_pk[p][0]
            WRITE[p] = (int(f['n']), int(f['S']), f['class'], int(f['T']))
        ns = sorted({WRITE[p][0] for p in c['pks']}); ss = sorted({WRITE[p][1] for p in c['pks']})
        if c['target'] is not None:
            # runbook defect 1 (2026-10-14): S may differ by a byte between partitions (a row's timestamp delta, encoded against each
            # flush's minimum, changes a block width's vint); the check is one n per class and an S spread of at most 1 %
            uniform = len(ns) == 1 and (ss[-1] - ss[0]) <= 0.01 * ss[0]
            within = uniform and c['target'] / 2 <= ss[0] and ss[-1] <= c['target'] * 2
            note(f'DATASET {name}: n {ns} S {ss} (target {c["target"]}, rows/4 = {c["rows"][c["pks"][0]] / 4}); one n and S spread <= 1 %: {uniform}; S within x2 of target: {within}')
            ok = ok and uniform and within
        else:
            note(f'DATASET {name}: per pk (rows, n, S): {[(c["rows"][p], WRITE[p][0], WRITE[p][1]) for p in c["pks"]]}')
        wrong = [p for p in c['pks'] if (WRITE[p][2] == 'IndexedEntry') != (WRITE[p][1] <= WRITE[p][3] and WRITE[p][0] > 1)]
        expect(f'{name}: write-path class at load (T = {sorted({WRITE[p][3] for p in c["pks"]})}) is IndexedEntry iff S <= T: classes '
               f'{sorted({WRITE[p][2] for p in c["pks"]})}, mismatches {wrong[:5]}', not wrong)
    if not ok:
        fail('dataset check failed (invalid run: rebuild the dataset, 9c)')


def read_pass(arm, tkib, name, fresh=True):
    c = CLASSES[name]
    T = tkib * 1024
    if fresh:
        sh('bin/nodetool invalidatekeycache')
    client('probe')
    new_trace()
    before = snap()
    r = client('read', 'ks1.t', str(c['pks'][0]), str(c['pks'][-1]), str(c['ck']))
    time.sleep(0.5)
    after = snap()
    tr = [fields(l) for l in new_trace()]
    ce = census(f'{arm}-{tkib}k-{name}')
    pkset = set(c['pks'])
    reads = [f for f in tr if f['kind'] == 'read' and f.get('tbl') == 't' and f.get('pk') in pkset]
    disk = [f for f in reads if f['src'] == 'disk']
    cache = [f for f in reads if f['src'] == 'cache']
    fetch = [f for f in tr if f['kind'] == 'fetch' and '/ks1/t-' in f.get('path', '')]
    mism = []
    hs = set()
    for f in disk:
        size = int(f['size']); n, S = WRITE[f['pk']][0], WRITE[f['pk']][1]
        hs.add(size - S)
        pred = 'IndexedEntry' if size <= T else 'ShallowIndexedEntry'
        if f['class'] != pred or int(f['n']) != n or int(f['T']) != T:
            mism.append((f['pk'], size, f['class'], f['n'], f['T']))
    H.setdefault(name, set()).update(hs)
    n_set = sorted({WRITE[p][0] for p in c['pks']}); s_set = sorted({WRITE[p][1] for p in c['pks']})
    nidx = sum(1 for f in disk if f['class'] == 'IndexedEntry'); nsh = sum(1 for f in disk if f['class'] == 'ShallowIndexedEntry')
    res = dict(arm=arm, T=T, name=name, P=len(c['pks']), ok=r.get('ok'), disk=len(disk), disk_pks=len({f['pk'] for f in disk}), cache=len(cache),
               nidx=nidx, nsh=nsh, mism=mism, fetch=len(fetch), before=before, after=after, census=ce, elapsed=r.get('elapsed_s'), h=sorted(hs))
    PASSES[(arm, tkib, name)] = res
    RCSV.writerow([arm, T, name, len(c['pks']), n_set if len(n_set) > 1 else n_set[0], s_set if len(s_set) > 1 else s_set[0], sorted(hs), len(disk),
                   res['disk_pks'], len(cache), nidx, nsh, len(mism), len(fetch), None, before['entries'], after['entries'], before['size'],
                   after['size'], after['capacity'], (after['iir'] or 0) - (before['iir'] or 0), ce.get('indexed_inst'), ce.get('indexed_bytes'),
                   ce.get('shallow_inst'), ce.get('indexinfo_inst'), ce.get('indexinfo_bytes'), ce.get('heap_used_kb'), r.get('elapsed_s')])
    RCSV_F.flush()
    note(f'PASS {arm} T={T} {name}: client ok={r.get("ok")} found={r.get("rows_found")}/{len(c["pks"])} elapsed={r.get("elapsed_s")}s; read lines disk={len(disk)} '
         f'(pks {res["disk_pks"]}) cache={len(cache)} indexed={nidx} shallow={nsh} branch mismatches={len(mism)} {mism[:3]}; h={sorted(hs)}; fetch={len(fetch)}; '
         f'cache Entries {before["entries"]}->{after["entries"]} Size {before["size"]}->{after["size"]} Capacity {after["capacity"]}; '
         f'IndexInfoReads +{(after["iir"] or 0) - (before["iir"] or 0)}; census {ce}')
    return res


def judge(res):
    """The per-pass forms of 9a (Prediction, last bullet)."""
    name, T, P = res['name'], res['T'], res['P']
    c = CLASSES[name]
    n = WRITE[c['pks'][0]][0]
    tag = f'{res["arm"]} T={T} {name}'
    expect(f'{tag}: every partition read found its row', bool(res['ok']))
    expect(f'{tag}: a disk read line for every partition ({res["disk_pks"]}/{P}) and every one on the predicted branch (size <= T) — mismatches {len(res["mism"])}',
           res['disk_pks'] == P and not res['mism'])
    allidx = res['nidx'] > 0 and res['nsh'] == 0
    allsh = res['nsh'] > 0 and res['nidx'] == 0
    if allsh:
        expect(f'{tag} (shallow): every read fetched IndexInfo from the index file: fetch lines {res["fetch"]} >= {P}', res['fetch'] >= P)
        de = res['after']['entries'] - res['before']['entries']; ds = res['after']['size'] - res['before']['size']
        expect(f'{tag} (shallow): Entries rose by exactly the partitions read: {de} = {P}', de == P)
        if de > 0:
            SHALLOW_W.append((tag, ds / de))
        note(f'INFO {tag}: Size per shallow entry {ds / de if de else None}')
        expect(f'{tag} (shallow): live ShallowIndexedEntry >= P: {res["census"].get("shallow_inst")} >= {P}', res['census'].get('shallow_inst', 0) >= P)
    elif allidx:
        expect(f'{tag} (indexed): no IndexInfo read from the index file: fetch lines {res["fetch"]}', res['fetch'] == 0)
        ea, sa, cap = res['after']['entries'], res['after']['size'], res['after']['capacity']
        w = sa / ea if ea else 0
        if cap == K:
            expect(f'{tag} (indexed, K = 8 MiB): K - w <= Size <= K with w ~ Size/Entries = {w:.0f}: Size {sa}, fewer entries than partitions ({ea} < {P})',
                   K - 1.05 * w <= sa <= K and ea < P)
        ci, cx = res['census'].get('indexed_inst', 0), res['census'].get('indexinfo_inst', 0)
        expect(f'{tag} (indexed): live IndexInfo = n x live IndexedEntry: {cx} = {n} x {ci} = {n * ci}', cx == n * ci)
        expect(f'{tag} (indexed): live IndexedEntry within the system-table entries of the cache Entries: {ci} <= {ea} and {ea} - {ci} <= 50',
               ci <= ea and ea - ci <= 50)
    else:
        note(f'INFO {tag}: mixed branches (indexed {res["nidx"]}, shallow {res["nsh"]}) — boundary class or a mismatch')
        if name == 'CB':
            expect(f'{tag}: fetch lines >= the shallow reads ({res["fetch"]} >= {res["nsh"]})', res['fetch'] >= res['nsh'])


def start_node():
    sh('git checkout -q conf/cassandra.yaml', check=False)
    note(sh(f'{HARNESS}/make-node-yaml.sh {MODE}')[1].strip().replace('\n', ' | '))
    sh('rm -rf data commitlog saved_caches logs hints cdc_raw')
    sh(f'rm -rf {D}/jmx-classes {D}/histo && mkdir -p {D}/jmx-classes {D}/histo && javac -d {D}/jmx-classes {HARNESS}/Jmx.java')
    if os.path.exists(TRACE):
        os.remove(TRACE)
    _, ts = sh(f'java -classpath {BM}/byteman-4.0.20.jar:build/classes/main:"build/lib/jars/*":"lib/*" org.jboss.byteman.check.TestScript {HARNESS}/index-trace.btm', check=False)
    open(D + '/testscript.txt', 'w').write(ts)
    note('Byteman TestScript: ' + ('no errors' if 'TestScript: no errors' in ts else 'ERRORS (testscript.txt)'))
    if 'TestScript: no errors' not in ts:
        fail('Byteman TestScript reports errors')
    env = dict(os.environ, MAX_HEAP_SIZE='4G',
               JVM_EXTRA_OPTS=f'-javaagent:{BM}/byteman-4.0.20.jar=script:{HARNESS}/index-trace.btm,listener:true -Dstage4.byteman.out={TRACE}')
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
    note('node up; Submit -l: ' + ' | '.join(l.strip() for l in sl.splitlines() if l.startswith('# File') or l.startswith('RULE'))[:600])
    _, vm = sh(f'jcmd {daemon_pid()} VM.command_line', check=False)
    note('JVM heap flags: ' + ' '.join(x for x in vm.split() if x.startswith('-Xm') or x.startswith('-Xmn') or 'UseG1' in x or 'UseConcMark' in x))
    sh('bin/cqlsh -e "CREATE KEYSPACE ks1 WITH replication = {\'class\': \'SimpleStrategy\', \'replication_factor\': 1}; '
       'CREATE TABLE ks1.t (pk bigint, ck bigint, v blob, PRIMARY KEY (pk, ck)) WITH compaction = {\'class\': \'SizeTieredCompactionStrategy\', \'enabled\': \'false\'}; '
       'CREATE TABLE ks1.w (pk bigint, ck bigint, v blob, PRIMARY KEY (pk, ck)) WITH compaction = {\'class\': \'SizeTieredCompactionStrategy\', \'enabled\': \'false\'};"')


def instruments():
    p = client('probe')
    if not p.get('ok') or p.get('protocol') != 5:
        fail(f'probe failed or protocol is not 5: {p}')
    note(f'INSTRUMENT probe: release {p["release_version"]} protocol {p["protocol"]}')
    s0 = snap()
    if None in s0.values():
        fail(f'a JMX reading is missing: {s0}')
    note(f'INSTRUMENT jmx: key cache {s0}')
    if s0['capacity'] != K:
        fail(f'key cache capacity {s0["capacity"]} != 8 MiB')
    t0 = jmx_get((SS, 'ColumnIndexCacheSizeInKiB')).get((SS, 'ColumnIndexCacheSizeInKiB'))
    if str(t0) != '2':
        fail(f'column_index_cache_size at start is {t0} KiB, not the shipped 2')
    set_t(2)
    ce = census('instrument-idle')
    note(f'INSTRUMENT census parses: {ce}')


def main():
    if daemon_pid():
        fail('a CassandraDaemon is already running')
    start_node()
    instruments()
    for name in ORDER:
        load_class(name)
    dataset_check()

    # 9e "Before the cluster tier" 2: instrument check (not a reading)
    c1 = CLASSES['C1']['pks'][0]
    sh('bin/nodetool invalidatekeycache'); new_trace()
    r = client('read', 'ks1.t', str(c1), str(c1), str(CLASSES['C1']['ck']))
    tr = [fields(l) for l in new_trace()]; ce = census('instrument-c1-2k')
    ok1 = any(f['kind'] == 'read' and f.get('class') == 'IndexedEntry' for f in tr) and ce.get('indexed_inst', 0) >= 1 and ce.get('indexinfo_inst', 0) > 0
    set_t(0); sh('bin/nodetool invalidatekeycache'); new_trace()
    r = client('read', 'ks1.t', str(c1), str(c1), str(CLASSES['C1']['ck']))
    tr2 = [fields(l) for l in new_trace()]; ce2 = census('instrument-c1-0k')
    ok2 = any(f['kind'] == 'read' and f.get('class') == 'ShallowIndexedEntry' for f in tr2) and ce2.get('shallow_inst', 0) >= 1 and any(f['kind'] == 'fetch' for f in tr2)
    note(f'INSTRUMENT CHECK 9e: at 2 KiB read {[ (f["kind"], f.get("class")) for f in tr if f["kind"] == "read"]} census {ce}; '
         f'at 0 read {[(f["kind"], f.get("class")) for f in tr2 if f["kind"] == "read"]} fetch {sum(1 for f in tr2 if f["kind"] == "fetch")} census {ce2}')
    if not (ok1 and ok2):
        fail('instrument check: the census or the trace did not show IndexedEntry at 2 KiB and ShallowIndexedEntry at 0')
    note('INSTRUMENT CHECK PASSED')
    if MODE == 'instrument':
        set_t(256); judge(read_pass('instrument', 256, 'C2'))
        set_t(0); judge(read_pass('instrument', 0, 'C2'))
        cap = set_cache_mb(256); set_cache_mb(8)
        note(f'INSTRUMENT large-cache set: capacity {cap}')
        if cap != 256 * 1024 * 1024:
            fail('the key cache capacity did not change over JMX')
        note('DONE (instrument)')
        return

    # sweep
    for tkib in TS_KIB:
        set_t(tkib)
        sh('bin/nodetool invalidatekeycache'); client('probe'); time.sleep(2); new_trace()
        s = snap(); ce = census(f'sweep-{tkib}k-idle')
        RCSV.writerow(['idle', tkib * 1024, '-', 0, '', '', '', '', '', '', '', '', '', '', '', s['entries'], s['entries'], s['size'], s['size'], s['capacity'],
                       0, ce.get('indexed_inst'), ce.get('indexed_bytes'), ce.get('shallow_inst'), ce.get('indexinfo_inst'), ce.get('indexinfo_bytes'),
                       ce.get('heap_used_kb'), '']); RCSV_F.flush()
        note(f'IDLE T={tkib * 1024}: cache {s}; census {ce}')
        for name in ORDER:
            judge(read_pass('sweep', tkib, name))

    # live flip 256 -> 16 KiB on C3, no flush, no restart
    files0 = datafiles(); new_trace()
    set_t(256); a = read_pass('flip', 256, 'C3')
    set_t(16); b = read_pass('flip', 16, 'C3')
    files1 = datafiles(); wl = [l for l in new_trace() if l.startswith('write ') and ' tbl=t ' in l]
    expect(f'live flip: C3 indexed at 256 KiB ({a["nidx"]}/{a["disk"]}) and shallow at 16 KiB ({b["nsh"]}/{b["disk"]}) with no new SSTable '
           f'({len(files0)} -> {len(files1)} Data.db) and no new ks1.t write line ({len(wl)})',
           a['nidx'] == a['disk'] > 0 and b['nsh'] == b['disk'] > 0 and files0 == files1 and not wl)
    judge(a); judge(b)

    # large-cache arm
    set_t(256)
    cap = set_cache_mb(256)
    big = read_pass('large', 256, 'C3')
    capped = PASSES[('sweep', 256, 'C3')]
    n3 = WRITE[CLASSES['C3']['pks'][0]][0]
    de = big['after']['entries'] - big['before']['entries']; ds = big['after']['size'] - big['before']['size']
    expect(f'large cache (capacity {cap}): all 100 C3 entries cached indexed: Entries +{de}, Size +{ds} (w = {ds / max(de, 1):.0f} per entry)', de == 100 and big['nidx'] == 100)
    ci, cx = big['census'].get('indexed_inst', 0), big['census'].get('indexinfo_inst', 0)
    expect(f'large cache: live IndexInfo = n x IndexedEntry: {cx} = {n3} x {ci}', cx == n3 * ci and ci >= 100)
    noise_kb = None
    idle_heaps = []
    for l in open(D + '/summary.txt'):
        m = re.search(r"^IDLE T=\d+: .*'heap_used_kb': (\d+)", l)
        if m:
            idle_heaps.append(int(m.group(1)))
    if idle_heaps:
        noise_kb = max(idle_heaps) - min(idle_heaps)
    dheap = (big['census'].get('heap_used_kb', 0) - capped['census'].get('heap_used_kb', 0)) * 1024
    dsize = big['after']['size'] - capped['after']['size']
    note(f'LARGE vs CAPPED C3 at 256 KiB: heap after GC +{dheap} B, cache Size +{dsize} B; idle heap spread {noise_kb} KiB over {idle_heaps}')
    expect(f'large cache: heap after a full collection higher than the capped C3 pass by about the Size difference: +{dheap} vs +{dsize} B (noise {noise_kb} KiB)',
           noise_kb is not None and dheap > noise_kb * 1024 and abs(dheap - dsize) <= noise_kb * 1024 + 0.2 * dsize)
    set_t(16)
    bs = read_pass('large', 16, 'C3')
    de2 = bs['after']['entries'] - bs['before']['entries']; ds2 = bs['after']['size'] - bs['before']['size']
    expect(f'large cache at 16 KiB: C3 shallow, Entries +{de2} = 100, Size per entry {ds2 / max(de2, 1):.1f} = the shallow constant {SHALLOW_W[0][1] if SHALLOW_W else None}',
           de2 == 100 and bs['nsh'] == 100 and SHALLOW_W and ds2 / max(de2, 1) == SHALLOW_W[0][1])
    set_cache_mb(8)

    # arm W: write path on the node at 16 then 2 KiB
    new_trace()
    set_t(16)
    if not client('load', 'ks1.w', '1', '5', '1000').get('ok'):
        fail('arm W load 1 failed')
    sh('bin/nodetool flush ks1 w')
    set_t(2)
    if not client('load', 'ks1.w', '6', '10', '1000').get('ok'):
        fail('arm W load 2 failed')
    sh('bin/nodetool flush ks1 w')
    wl = [fields(l) for l in new_trace() if l.startswith('write ')]
    w = {f['pk']: f for f in wl if f.get('tbl') == 'w'}
    note(f'ARM W write lines: {[(p, w[p]["n"], w[p]["S"], w[p]["class"], w[p]["T"]) for p in sorted(w)]}')
    expect('arm W: the 5 partitions flushed at 16 KiB are IndexedEntry (T=16384 in the line) and the 5 flushed at 2 KiB are ShallowIndexedEntry (T=2048)',
           sorted(w) == list(range(1, 11)) and all(w[p]['class'] == 'IndexedEntry' and w[p]['T'] == '16384' for p in range(1, 6))
           and all(w[p]['class'] == 'ShallowIndexedEntry' and w[p]['T'] == '2048' for p in range(6, 11)))
    expect(f'arm W: ks1.t not rewritten (write lines for ks1.t: {sum(1 for f in wl if f.get("tbl") == "t")})', not any(f.get('tbl') == 't' for f in wl))

    # end-of-run forms
    ws = sorted({round(x[1], 6) for x in SHALLOW_W})
    expect(f'every shallow pass added the same Size per entry, whatever the class and T: {ws} over {len(SHALLOW_W)} passes', len(ws) == 1)
    note(f'h per class (size - S): { {k: sorted(v) for k, v in H.items()} }')
    for name in ORDER:
        c = CLASSES[name]
        cls_by_t = {t: PASSES[('sweep', t, name)]['nidx'] for t in TS_KIB}
        note(f'MATRIX {name}: indexed reads per T (KiB) {cls_by_t} of {len(c["pks"])}')
    note('DONE')


try:
    main()
    stop_node()
    sh(f'cp {SYSLOG} {D}/system.log', check=False)
except SystemExit:
    raise
except Exception as e:
    note(f'FAIL (exception): {e!r}')
    stop_node()
    sys.exit(1)
