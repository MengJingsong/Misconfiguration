#!/usr/bin/env python3
"""Stage 4, cluster tier, repair_session_space-split-maxsize (case 9b-9e, amended 2026-10-14).
usage: cluster-run.py <label>
  arm M (Murmur3):  m-setup | m-control | m-a | m-b | m-c | m-depth
  arm O (byte order): o-scratch | o-setup | o-run
  down              stop both nodes
Two nodes on this host, N1 = 127.0.0.2 (JMX 7102, runs every repair) and N2 = 127.0.0.3 (JMX 7103), RF 2, one token each.
The nodes stay up between labels of one arm; m-setup and o-setup wipe and start them, m-depth restarts them.
Each label logs every command to ~/stage4-logs/rss/<label>/session.log and writes summary.txt (EXPECTED lines) and
readings.csv. Predictions use the depth table the unit tier printed (~/stage4-logs/rss/unit/harness.out).
Exit 1: an instrument or set-up check failed; on a failure both nodes are stopped.
Environment: RSS_ROWS (default 1048576, the case's 2^20; a smaller value is a shakedown, not a reading)."""
import csv, json, math, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
RSS = os.environ.get('RSS', HOME + '/stage4-rss')
ROWS = int(os.environ.get('RSS_ROWS', 1 << 20))
LOGROOT = os.environ.get('RSS_LOGS', HOME + '/stage4-logs/rss')
UNIT_OUT = os.environ.get('RSS_UNIT_OUT', LOGROOT + '/unit/harness.out')
STATE = RSS + '/state.json'
NODES = {'N1': ('127.0.0.2', 7102), 'N2': ('127.0.0.3', 7103)}
MURMUR = 'org.apache.cassandra.dht.Murmur3Partitioner'
BOP = 'org.apache.cassandra.dht.ByteOrderedPartitioner'
MIN_TOKEN = '-9223372036854775808'
RS_BEAN = 'org.apache.cassandra.db:type=RepairService'
DIRECT_BEAN = 'java.nio:type=BufferPool,name=direct'
BYTEMAN = C + '/build/lib/jars/byteman-4.0.20.jar'
RF = 2
VALUES_A = [1, 4, 16, 64]

label = sys.argv[1] if len(sys.argv) > 1 else ''
D = f'{LOGROOT}/{label}'
os.makedirs(D, exist_ok=True)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'w')
RCSV_F = open(D + '/readings.csv', 'w', newline='')
RCSV = csv.writer(RCSV_F)
RCSV.writerow(['label', 'arm', 'step', 's_MiB', 'node', 'n', 'L', 'L_pred', 'maxsize_trace', 'split_calls', 'refused', 'toodeep',
               'samples', 'offheap_lines', 'offheap_pred', 'leaf_delta', 'inner_delta', 'direct_idle', 'direct_hold'])


# ---------------------------------------------------------------- plumbing

def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr)
    SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=600, check=True, env=None, cwd=C, quiet=False):
    log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-6000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-1200:]}')
    return r.returncode, out


def expect(desc, cond):
    note(f'EXPECTED: {desc} — {"yes" if cond else "NO (recorded; the AI judges it in the results file)"}')
    return cond


def load_state():
    return json.load(open(STATE)) if os.path.exists(STATE) else {}


def save_state(st):
    json.dump(st, open(STATE, 'w'), indent=1)


def pid_of(node):
    f = f'{RSS}/{node}/cassandra.pid'
    if not os.path.exists(f):
        return None
    try:
        pid = int(open(f).read().strip())
        cmd = open(f'/proc/{pid}/cmdline').read()
        return pid if 'CassandraDaemon' in cmd else None
    except (ValueError, OSError):
        return None


def any_daemon():
    _, out = sh("ps -eo cmd | grep '[C]assandraDaemon' || true", check=False, quiet=True)
    return out.strip()


def stop_node(node):
    port = NODES[node][1]
    if pid_of(node) is None:
        return
    sh(f'bin/nodetool -p {port} stopdaemon', check=False, timeout=120)
    for _ in range(90):
        if pid_of(node) is None:
            break
        time.sleep(1)
    pid = pid_of(node)
    if pid is not None:
        log(f'{node} did not stop; kill -9 {pid}')
        subprocess.run(['kill', '-9', str(pid)])
        time.sleep(2)


def stop_all():
    for n in ('N2', 'N1'):
        stop_node(n)
    left = any_daemon()
    if left:
        log('WARNING: a CassandraDaemon is still running: ' + left[:300])


def fail(msg):
    note('FAIL: ' + msg)
    stop_all()
    sys.exit(1)


def helper_jar():
    out = f'{RSS}/helper'
    jar = out + '/stage4-rss.jar'
    sh(f'rm -rf {out} && mkdir -p {out}/classes && javac -d {out}/classes {HARNESS}/Rss.java && jar cf {jar} -C {out}/classes .')
    return jar


def start_node(node, st, tag=''):
    if pid_of(node) is not None:
        fail(f'{node} is already running')
    tok = st['tokens'][node]
    extras = ' '.join(f'{k}={v}' for k, v in st.get('extras', {}).items())
    _, y = sh(f'{HARNESS}/make-node-yaml.sh {node} {st["partitioner"]} {tok} {extras}')
    note(y.strip().splitlines()[-1][:600])
    N = f'{RSS}/{node}'
    scripts = f'script:{HARNESS}/split-trace.btm' + (f',script:{HARNESS}/hold-trees.btm' if node == 'N2' else '')
    jopts = (f'-javaagent:{BYTEMAN}={scripts} -Xbootclasspath/a:{st["helper"]} '
             f'-Dstage4.trace={N}/rss.trace -Dstage4.holdflag={N}/hold.flag')
    env = dict(os.environ, CASSANDRA_CONF=N + '/conf', CASSANDRA_LOG_DIR=N + '/logs', MAX_HEAP_SIZE='2G', JVM_EXTRA_OPTS=jopts)
    env.pop('HEAP_NEWSIZE', None)
    sh(f'bin/cassandra -p {N}/cassandra.pid > {N}/stdout{tag}.txt 2>&1', env=env)
    time.sleep(4)
    if pid_of(node) is None:
        fail(f'{node} did not start; see {N}/stdout{tag}.txt')


def wait_up(node, want_un, timeout=300):
    port = NODES[node][1]
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pid_of(node) is None:
            fail(f'{node} died during start')
        _, st = sh(f'bin/nodetool -p {port} statusbinary', check=False, quiet=True)
        _, ns = sh(f'bin/nodetool -p {port} status', check=False, quiet=True)
        un = re.findall(r'^UN\s+(\S+)', ns, re.M)
        if re.search(r'^running\s*$', st, re.M) and len(un) >= want_un:   # not 'not running'
            note(f'{node} up: statusbinary running, UN {un} after {time.time() - t0:.0f} s')
            return
        time.sleep(3)
    fail(f'{node} not up after {timeout} s')


def cql(stmt, host='127.0.0.2'):
    _, out = sh(f'bin/cqlsh {host} -e "{stmt}"', timeout=120)
    return out


def jmx(port, *args):
    _, out = sh(f'java -cp {RSS}/jmxcls Jmx {port} ' + ' '.join(f"'{a}'" for a in args), check=False, timeout=60)
    return out


def jmx_build():
    sh(f'mkdir -p {RSS}/jmxcls && javac -d {RSS}/jmxcls {HARNESS}/Jmx.java')


def jmx_get_int(port, bean, attr):
    out = jmx(port, 'get', bean, attr)
    m = re.search(re.escape(attr) + r'\|(-?\d+)', out)
    return int(m.group(1)) if m else None


def set_space(s):
    """Sets RepairSessionSpaceInMiB on both nodes and reads it back; an invalid run if it did not take (9a)."""
    for node, (_, port) in NODES.items():
        out = jmx(port, 'setint', RS_BEAN, 'RepairSessionSpaceInMiB', str(s))
        m = re.search(r'RepairSessionSpaceInMiB\|(-?\d+)', out)
        back = int(m.group(1)) if m else None
        back2 = jmx_get_int(port, RS_BEAN, 'RepairSessionSpaceInMiB')
        note(f'KNOB {node} set {s} read back {back} / {back2}')
        if back != s or back2 != s:
            fail(f'{node}: RepairSessionSpaceInMiB read back {back}/{back2}, set {s} (invalid run, 9a)')


def read_space():
    return {node: jmx_get_int(port, RS_BEAN, 'RepairSessionSpaceInMiB') for node, (_, port) in NODES.items()}


def stress(n, pop=None):
    popopt = f' -pop seq={pop}' if pop else ''
    _, out = sh(f"tools/bin/cassandra-stress write n={n} cl=ALL no-warmup -col 'n=FIXED(1)' 'size=FIXED(16)' "
                f"-rate threads=32 -node 127.0.0.2,127.0.0.3{popopt}", timeout=3600)
    errs = re.search(r'Total errors\s*:\s*([\d,]+)', out)
    parts = re.search(r'Total partitions\s*:\s*([\d,]+)', out)
    note(f'STRESS n={n}{popopt}: partitions {parts.group(1) if parts else "?"}, errors {errs.group(1) if errs else "?"}')
    if not errs or int(errs.group(1).replace(',', '')) != 0:
        fail('stress reported errors or no summary')


def flush_both():
    for node, (_, port) in NODES.items():
        sh(f'bin/nodetool -p {port} flush keyspace1 standard1')
    time.sleep(2)
    for node in NODES:
        _, ls = sh(f'ls {RSS}/{node}/data/keyspace1/standard1-*/*-Data.db 2>/dev/null || true', check=False)
        note(f'SSTABLES {node}: {len(ls.split())} Data.db files')


def create_schema():
    cql("CREATE KEYSPACE keyspace1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': %d}; "
        "CREATE TABLE keyspace1.standard1 (key blob PRIMARY KEY, \\\"C0\\\" blob) WITH compaction = "
        "{'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'};" % RF)
    note('SCHEMA keyspace1 RF %d, standard1 with autocompaction disabled' % RF)


# ---------------------------------------------------------------- prediction (9a, from the unit tier's depth table)

def depth_table():
    want = {'Murmur3Partitioner': MURMUR, 'ByteOrderedPartitioner': BOP}
    t = {}
    if not os.path.exists(UNIT_OUT):
        fail(f'no unit-tier output {UNIT_OUT}: run the unit tier first (the prediction uses its depth table)')
    for line in open(UNIT_OUT):
        m = re.match(r'STAGE4 value U3 depth_table (\S+) leaf=(\d+) inner=(\d+) leaf\+inner=\d+ (.*)', line.strip())
        if m and m.group(1) in want:
            d = {int(k) * 1024: int(v) for k, v in re.findall(r'd\((\d+)KiB\)=(\d+)', m.group(4))}
            t[want[m.group(1)]] = dict(leaf=int(m.group(2)), inner=int(m.group(3)), d=d)
    for p in want.values():
        if p not in t:
            fail(f'depth table for {p} missing from {UNIT_OUT}')
        for b, dv in t[p]['d'].items():      # the Python recomputation must agree with what Java printed
            if dfun(t[p], b) != dv:
                fail(f'depth recomputation disagrees with the unit table for {p} b={b}: {dfun(t[p], b)} vs {dv}')
    return t


def dfun(tab, num_bytes):
    """MerkleTree.estimatedMaxDepthForBytes():1538-1540 with the unit tier's leaf and inner sizes."""
    adjusted = max(1, (num_bytes + tab['inner']) // (tab['leaf'] + tab['inner']))
    return max(1, int(math.floor(math.log(adjusted) / math.log(2))))


def int32(x):
    x &= 0xFFFFFFFF
    return x - (1 << 32) if x >= (1 << 31) else x


def predict(tab, s, n, depth_cap=20):
    """ValidationManager.createMerkleTrees():62-80 for one range, share 1, RF 2."""
    prod = int32(s * 1048576)                    # :62, int * int
    avail = int(prod / RF)                       # long division truncates toward zero
    range_avail = max(1, int(1.0 * avail))       # :71
    d = dfun(tab, range_avail)                   # :74
    max_depth = min(d, depth_cap)                # :75-77
    depth = int(min(math.ceil(math.log(n) / math.log(2)), max_depth)) if n > 0 else 0   # :79
    return 2 ** depth, dict(prod=prod, b=range_avail, d=d, max_depth=max_depth, depth=depth)


# ---------------------------------------------------------------- reading one repair

def size_of(path):
    return os.path.getsize(path) if os.path.exists(path) else 0


def tail_from(path, off):
    if not os.path.exists(path):
        return ''
    with open(path, errors='replace') as f:
        f.seek(off)
        return f.read()


def save_raw(name, text):
    """Raw evidence for the self-check, kept under the label's log folder (the node folders are wiped by the next arm's set-up)."""
    os.makedirs(D + '/raw', exist_ok=True)
    with open(f'{D}/raw/{name}', 'w') as f:
        f.write(text)


def histo(pid, save=None):
    _, out = sh(f'jmap -histo:live {pid}', timeout=300, quiet=True)
    if save:
        save_raw(save, out)
    counts = {}
    for m in re.finditer(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+(org\.apache\.cassandra\.utils\.MerkleTree\$\S+)', out, re.M):
        counts[m.group(3)] = (int(m.group(1)), int(m.group(2)))
    leaf = counts.get('org.apache.cassandra.utils.MerkleTree$OnHeapLeaf', (0, 0))
    inner = counts.get('org.apache.cassandra.utils.MerkleTree$OnHeapInner', (0, 0))
    log(f'histo pid {pid}: OnHeapLeaf {leaf} OnHeapInner {inner} (all MerkleTree classes: {counts})')
    return leaf, inner


def repair(arm, step, s_label, tab, hold=False, depth_cap=20, judge=True):
    """judge=False: a set-up repair (o-setup's n check); its readings are logged and kept, not compared with 9a."""
    st = load_state()
    files = {n: (f'{RSS}/{n}/logs/debug.log', f'{RSS}/{n}/rss.trace') for n in NODES}
    marks = {n: (size_of(a), size_of(b)) for n, (a, b) in files.items()}
    flag = f'{RSS}/N2/hold.flag'
    extra = {}
    tag = re.sub(r'[^A-Za-z0-9]+', '-', f'{step}-s{s_label}').strip('-')
    cmd = 'bin/nodetool -p 7102 repair -full -pr keyspace1 standard1'
    if hold:
        extra['leaf0'], extra['inner0'] = histo(pid_of('N2'), save=f'{tag}-N2-histo-idle.txt')
        extra['direct_idle'] = jmx_get_int(7102, DIRECT_BEAN, 'MemoryUsed')
        save_raw(f'{tag}-N1-direct-idle.txt', f'{DIRECT_BEAN} MemoryUsed {extra["direct_idle"]} ms={int(time.time() * 1000)}\n')
        open(flag, 'w').write('hold\n')
        log('+ ' + cmd + '   (background; hold flag set on N2)')
        p = subprocess.Popen(cmd, shell=True, cwd=C, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        t0 = time.time()
        while time.time() - t0 < 600:
            if 'hold start' in tail_from(files['N2'][1], marks['N2'][1]):
                break
            if p.poll() is not None:
                break
            time.sleep(0.5)
        held = 'hold start' in tail_from(files['N2'][1], marks['N2'][1])
        if held:
            extra['direct_hold'] = jmx_get_int(7102, DIRECT_BEAN, 'MemoryUsed')
            save_raw(f'{tag}-N1-direct-hold.txt', f'{DIRECT_BEAN} MemoryUsed {extra["direct_hold"]} ms={int(time.time() * 1000)}\n')
            extra['leaf1'], extra['inner1'] = histo(pid_of('N2'), save=f'{tag}-N2-histo-hold.txt')
        os.remove(flag)
        out, _ = p.communicate(timeout=900)
        rc = p.returncode
        SESSION.write(out[-4000:] + f'\n  rc={rc}\n'); SESSION.flush()
        if not held:
            fail(f'{step} s={s_label}: the hold never started on N2 (instrument silent; invalid for this reading, 9a)')
    else:
        rc, out = sh(cmd, check=False, timeout=900)
    save_raw(f'{tag}-repair.out', out)
    if rc != 0 or re.search(r'error|failed', out, re.I):
        fail(f'{step} s={s_label}: repair rc={rc}: {out[-600:]}')
    time.sleep(4)          # debug.log is written by an async appender
    res = {}
    for n in NODES:
        dl = tail_from(files[n][0], marks[n][0])
        tr = tail_from(files[n][1], marks[n][1])
        save_raw(f'{tag}-{n}-debug.log', dl)
        save_raw(f'{tag}-{n}-trace.log', tr)
        created = re.findall(r'Created (\d+) merkle trees with merkle trees size (\d+), (\d+) partitions, (\d+) bytes', dl)
        prepared = [int(x) for x in re.findall(r'Prepared AEService trees of size (\d+) for', dl)]
        offheap = [int(x) for x in re.findall(r'Allocating direct buffer of size (\d+) for an off-heap merkle tree', dl)]
        calls = [int(x) for x in re.findall(r'split calls=(\d+)', tr)]
        refused = [(int(a), int(b)) for a, b in re.findall(r'split refused size=(\d+) maxsize=(\d+)', tr)]
        toodeep = [(int(a), int(b)) for a, b in re.findall(r'split toodeep size=(\d+) maxsize=(\d+)', tr)]
        samples = [int(x) for x in re.findall(r'samples=(\d+)', tr)]
        if len(created) != 1 or len(prepared) != 1 or len(calls) != 1:
            fail(f'{step} s={s_label} {n}: expected one Created, one Prepared and one split-calls line, got '
                 f'{len(created)}/{len(prepared)}/{len(calls)} (instrument silent; invalid, 9a)')
        n_est = int(created[0][2])
        L = prepared[0]
        Lp, parts = predict(tab, s_label if isinstance(s_label, int) else st['default_s'], n_est, depth_cap)
        res[n] = dict(n=n_est, L=L, Lp=Lp, parts=parts, calls=calls[0], refused=refused, toodeep=toodeep, samples=samples, offheap=offheap)
        note(f'READ {arm} {step} s={s_label} {n}: n={n_est} L={L} predicted={Lp} {parts} split_calls={calls[0]} '
             f'refused={refused} toodeep={toodeep} samples={samples} offheap={offheap}')
    # off-heap (arm M, coordinator N1): two buffers, 82 L + 32 each (9a, amended)
    off = res['N1']['offheap']
    off_pred = sorted(82 * res[n]['L'] + 32 for n in NODES)
    for n in NODES:
        r = res[n]
        RCSV.writerow([label, arm, step, s_label, n, r['n'], r['L'], r['Lp'], ';'.join(f'{a}/{b}' for a, b in r['refused']),
                       r['calls'], len(r['refused']), len(r['toodeep']), ';'.join(map(str, r['samples'])),
                       ';'.join(map(str, off)) if n == 'N1' else '', ';'.join(map(str, off_pred)) if n == 'N1' else '',
                       (extra.get('leaf1', (0, 0))[0] - extra.get('leaf0', (0, 0))[0]) if hold and n == 'N2' else '',
                       (extra.get('inner1', (0, 0))[0] - extra.get('inner0', (0, 0))[0]) if hold and n == 'N2' else '',
                       extra.get('direct_idle', '') if n == 'N1' else '', extra.get('direct_hold', '') if n == 'N1' else ''])
    RCSV_F.flush()
    if not judge:
        note(f'SET-UP repair {step}: readings above recorded as observations, not compared with the 9a prediction')
        return res
    for n in NODES:
        expect(f'{arm} {step} s={s_label} {n}: L = {res[n]["Lp"]} (2^min(ceil log2 n, d(b), D)); read {res[n]["L"]}',
               res[n]['L'] == res[n]['Lp'])
    if arm == 'M':
        for n in NODES:
            expect(f'M {step} s={s_label} {n}: split() never called (split calls=0); read {res[n]["calls"]}', res[n]['calls'] == 0)
        expect(f'M {step} s={s_label} N1: two off-heap buffers of 82 L + 32 = {off_pred}; read {sorted(off)}', sorted(off) == off_pred)
    else:
        for n in NODES:
            r = res[n]
            expect(f'O {step} s={s_label} {n}: one refusal at size == maxsize == L, no toodeep; read refused={r["refused"]} toodeep={r["toodeep"]}',
                   len(r['refused']) == 1 and r['refused'][0][0] == r['refused'][0][1] == r['L'] and not r['toodeep'])
            expect(f'O {step} s={s_label} {n}: split calls = L (L - 1 splits and the refused call) = {r["L"]}; read {r["calls"]}', r['calls'] == r['L'])
            expect(f'O {step} s={s_label} {n}: one samples line, about n/128 = {r["n"] // 128}; read {r["samples"]}', len(r['samples']) == 1)
            expect(f'O {step} s={s_label} {n}: no off-heap buffer line; read {r["offheap"]}', not r['offheap'])
    if hold:
        L2 = res['N2']['L']
        dl = extra['leaf1'][0] - extra['leaf0'][0]
        di = extra['inner1'][0] - extra['inner0'][0]
        note(f'HEAP N2 s={s_label}: OnHeapLeaf {extra["leaf0"]} -> {extra["leaf1"]} (delta {dl}), OnHeapInner {extra["inner0"]} -> '
             f'{extra["inner1"]} (delta {di}); bytes delta leaf {extra["leaf1"][1] - extra["leaf0"][1]} inner {extra["inner1"][1] - extra["inner0"][1]}')
        expect(f'{arm} {step} s={s_label} N2 heap: OnHeapLeaf +{L2}, OnHeapInner +{L2 - 1}; read +{dl}, +{di}', dl == L2 and di == L2 - 1)
        if extra.get('direct_idle') is not None and extra.get('direct_hold') is not None:
            note(f'DIRECT N1 s={s_label}: MemoryUsed idle {extra["direct_idle"]} during hold {extra["direct_hold"]} '
                 f'(rise {extra["direct_hold"] - extra["direct_idle"]}; one buffer would be {82 * res["N1"]["L"] + 32}) — support only')
    return res


# ---------------------------------------------------------------- labels

def archive_nodes():
    """Copies the node logs and traces of whatever ran before into this label's folder before a wipe."""
    for node in NODES:
        src = f'{RSS}/{node}'
        if os.path.isdir(src):
            sh(f'mkdir -p {D}/prev-{node} && cp -a {src}/logs {src}/rss.trace {src}/stdout*.txt {src}/conf/cassandra.yaml {D}/prev-{node}/ 2>/dev/null; true', check=False)


def setup(arm):
    if any_daemon():
        fail('a CassandraDaemon is already running: ' + any_daemon()[:300])
    st = load_state()
    if arm == 'M':
        st = dict(arm='M', partitioner=MURMUR, tokens={'N1': MIN_TOKEN, 'N2': '0'}, extras={})
    else:
        tok = json.load(open(f'{RSS}/o-tokens.json'))
        st = dict(arm='O', partitioner=BOP, tokens={'N1': tok['median'], 'N2': '00'}, extras={})
    archive_nodes()
    sh(f'rm -rf {RSS}/N1 {RSS}/N2')
    os.makedirs(RSS, exist_ok=True)
    st['helper'] = helper_jar()
    jmx_build()
    save_state(st)
    note(f'SETUP arm {arm}: partitioner {st["partitioner"]}, tokens {st["tokens"]}, rows {ROWS}')
    start_node('N1', st); wait_up('N1', 1)
    start_node('N2', st); wait_up('N2', 2); wait_up('N1', 2)
    create_schema()
    stress(ROWS)
    flush_both()
    sp = read_space()
    st['default_s'] = sp['N1']
    save_state(st)
    note(f'DEFAULT repair_session_space read back {sp} (expected 128 at -Xmx2G, G1)')
    expect('default repair_session_space = 128 MiB on both nodes', sp == {'N1': 128, 'N2': 128})


def main():
    if label == 'down':
        stop_all()
        note('both nodes stopped; daemons left: ' + (any_daemon() or 'none'))
        return
    st = load_state()
    if label == 'm-setup':
        setup('M'); return
    if label == 'o-setup':
        setup('O')
        tab = depth_table()[BOP]
        r = repair('O', 'o-setup first repair', 'default', tab, judge=False)
        expect(f'O: node 1 n above 2^16 ({1 << 16}); read {r["N1"]["n"]}', r['N1']['n'] > (1 << 16))
        if r['N1']['n'] <= (1 << 16) and ROWS == 1 << 20:
            fail('node 1 range too small: move node 1 token (9e arm O) and reload')
        return
    if label == 'o-scratch':
        if any_daemon():
            fail('a CassandraDaemon is already running')
        archive_nodes()
        sh(f'rm -rf {RSS}/N1 {RSS}/N2'); os.makedirs(RSS, exist_ok=True)
        stt = dict(arm='O-scratch', partitioner=BOP, tokens={'N1': '00'}, extras={}, helper=helper_jar())
        save_state(stt)
        start_node('N1', stt); wait_up('N1', 1)
        cql("CREATE KEYSPACE keyspace1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}; "
            "CREATE TABLE keyspace1.standard1 (key blob PRIMARY KEY, \\\"C0\\\" blob);")
        _, out = sh("tools/bin/cassandra-stress write n=1000 cl=ONE no-warmup -col 'n=FIXED(1)' 'size=FIXED(16)' -rate threads=8 -node 127.0.0.2", timeout=600)
        out = cql('PAGING OFF; SELECT token(key) FROM keyspace1.standard1;')
        save_raw('scratch-tokens.txt', out)
        toks = re.findall(r'^\s*0x([0-9a-f]+)\s*$', out, re.M)
        note(f'SCRATCH tokens read: {len(toks)}; smallest {min(toks) if toks else None}; largest {max(toks) if toks else None}')
        if len(toks) != 1000:
            fail(f'expected 1000 tokens, read {len(toks)}')
        toks.sort()
        median = toks[499]
        json.dump(dict(median=median, smallest=toks[0], largest=toks[-1], n=len(toks)), open(f'{RSS}/o-tokens.json', 'w'))
        note(f'SCRATCH node 1 token = median {median}; node 2 token = 00')
        expect('every sampled token is above 00', toks[0] > '00')
        stop_all()
        sh(f'rm -rf {RSS}/N1')
        return
    # the remaining labels run on the started arm
    if not st or pid_of('N1') is None or pid_of('N2') is None:
        fail(f'nodes not running for {label}; run the arm setup first (state {st})')
    tab = depth_table()[st['partitioner']]
    note(f'DEPTH TABLE {st["partitioner"]}: leaf {tab["leaf"]} inner {tab["inner"]} d {tab["d"]}')
    if label == 'm-control':
        h = histo(pid_of('N2'))
        note(f'IDLE N2 histogram: OnHeapLeaf {h[0]} OnHeapInner {h[1]}')
        sp = read_space()
        note(f'KNOB read back {sp}')
        repair('M', 'control', 'default', tab)
        repair('M', 'control-hold', 'default', tab, hold=True)
    elif label == 'm-a':
        for s in VALUES_A:
            set_space(s)
            repair('M', 'A', s, tab)
            repair('M', 'A-hold', s, tab, hold=True)
    elif label == 'm-b':
        stress(ROWS, pop=f'{ROWS + 1}..{2 * ROWS}')
        flush_both()
        for s in (4, 16):
            set_space(s)
            repair('M', 'B', s, tab)
    elif label == 'm-c':
        for s in (2048, 4097):
            set_space(s)
            repair('M', 'C-overflow', s, tab)
    elif label == 'm-depth':
        stop_all()
        st['extras'] = {'repair_session_max_tree_depth': 15}
        save_state(st)
        start_node('N1', st, '-depth'); wait_up('N1', 1)
        start_node('N2', st, '-depth'); wait_up('N2', 2); wait_up('N1', 2)
        _, w = sh(f'grep -h "repair_session_max_tree_depth has been deprecated" {RSS}/N1/logs/system.log {RSS}/N2/logs/system.log || true', check=False)
        note(f'DEPTH deprecation warnings: {len(w.strip().splitlines())}')
        set_space(64)
        repair('M', 'C-depthcap15', 64, tab, depth_cap=15)
        st['extras'] = {}
        save_state(st)
    elif label == 'o-run':
        if st['arm'] != 'O':
            fail('o-run needs the arm-O cluster (o-setup)')
        for s in (4, 16):
            set_space(s)
            repair('O', 'A', s, tab)
    else:
        fail(f'unknown label {label}')


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        log(traceback.format_exc())
        fail(f'{type(e).__name__}: {e}')
    finally:
        try:
            os.remove(f'{RSS}/N2/hold.flag')
        except OSError:
            pass
