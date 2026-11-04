#!/usr/bin/env python3
"""Stage 4, cluster tier B3 of max_space_usable_for_compactions_in_percentage-applysimpleconfig-range--autonomous (amended 2026-10-27).
usage: cluster-run.py <label> [...]     labels: invalid | seed | run-<pct> (e.g. run-0.95, run-0.10, run-1.0) | down
One node (127.0.0.1) from CASSANDRA_HOME (default ~/cassandra-run1), JMX 7199, MAX_HEAP_SIZE 2G. The data directory is a 2 GiB ext4 filesystem
(mkfs -m 0) on a loop device (sudo), fresh for every label. Everything else (commit log, hints, logs) is on local disk under ~/s4b-mu.
seed: builds 4 sstables of >= 160 MiB (stress, flush after each chunk, autocompaction off) and copies the data directory to ~/s4b-mu/seed-data.
run-<pct>: restores the seed onto a fresh filesystem, starts the node with the yaml value, records the at-rest figures, runs ONE `nodetool compact`,
  samples the filesystem every 0.5 s, then stops the node. invalid: starts a node with 1.5 and expects it to refuse to start.
Every label logs each command to $MU_LOGS/<label>/session.log and writes summary.txt (EXPECTED lines)."""
import json, os, re, subprocess, sys, threading, time, shutil, glob

HOME = os.path.expanduser('~')
C = os.environ.get('CASSANDRA_HOME', HOME + '/cassandra-run1')
HARNESS = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get('MU_BASE', HOME + '/s4b-mu')
LOGROOT = os.environ.get('MU_LOGS', HOME + '/s4b-logs/msu/cluster')
MNT = BASE + '/mnt'
IMG = BASE + '/fs.img'
SEED = BASE + '/seed-data'
CHUNK_ROWS = int(os.environ.get('MU_CHUNK_ROWS', 760000))
CHUNKS = 4
MIN_SST = 160 * 1048576
FS_BYTES = 2 * 1024 ** 3

label = sys.argv[1] if len(sys.argv) > 1 else ''
D = f'{LOGROOT}/{label}'
os.makedirs(D, exist_ok=True)
SESSION = open(D + '/session.log', 'a')
SUMMARY = open(D + '/summary.txt', 'a')
n_exp = n_yes = 0


def log(s):
    line = f'[{time.strftime("%F %T")}] {s}'
    print(line, file=sys.stderr); SESSION.write(line + '\n'); SESSION.flush()


def note(s):
    print(s); SUMMARY.write(s + '\n'); SUMMARY.flush(); log(s)


def sh(cmd, timeout=900, check=True, env=None, cwd=C, quiet=False):
    log('+ ' + cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    out = (r.stdout or '') + (r.stderr or '')
    if not quiet:
        SESSION.write(out[-5000:] + f'\n  rc={r.returncode}\n'); SESSION.flush()
    if check and r.returncode != 0:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd}\n{out[-1200:]}')
    return r.returncode, out


def expect(desc, cond):
    global n_exp, n_yes
    n_exp += 1; n_yes += bool(cond)
    note(f'EXPECTED: {desc} - {"yes" if cond else "NO (recorded; judged in the results file)"}')
    return cond


def daemons():
    _, o = sh("ps -eo comm,args | awk '$1==\"java\" && /CassandraDaemon/' || true", check=False, quiet=True)
    return o.strip()


def pid():
    try:
        p = int(open(BASE + '/cassandra.pid').read().strip())
        return p if 'CassandraDaemon' in open(f'/proc/{p}/cmdline').read() else None
    except (OSError, ValueError):
        return None


def stop_node():
    p = pid()
    if p is None:
        return
    sh('bin/nodetool stopdaemon', check=False, timeout=120)
    for _ in range(90):
        if pid() is None:
            return
        time.sleep(1)
    log(f'kill -9 {p}'); subprocess.run(['kill', '-9', str(p)]); time.sleep(2)


def fail(msg):
    note('FAIL: ' + msg)
    try:
        stop_node()
        umount()
    finally:
        sys.exit(1)


def umount():
    sh(f'mountpoint -q {MNT} && sudo umount {MNT} || true', check=False)


def fresh_fs():
    if daemons():
        fail('a CassandraDaemon is running: ' + daemons()[:200])
    umount()
    sh(f'mkdir -p {BASE} {MNT} && rm -f {IMG} && truncate -s {FS_BYTES} {IMG} && mkfs.ext4 -q -F -m 0 {IMG} && sudo mount -o loop {IMG} {MNT} && sudo chown $(id -u):$(id -g) {MNT}')
    st = os.statvfs(MNT)
    note(f'FS fresh ext4 loop {IMG}: size {st.f_blocks * st.f_frsize} B, avail {st.f_bavail * st.f_frsize} B')
    sh(f'mkdir -p {MNT}/data')


def used_free():
    st = os.statvfs(MNT)
    return (st.f_blocks - st.f_bfree) * st.f_frsize, st.f_bavail * st.f_frsize


def make_yaml(extra):
    for d in ('conf', 'logs', 'commitlog', 'hints', 'saved_caches', 'cdc_raw'):
        sh(f'mkdir -p {BASE}/{d}', quiet=True)
    sh(f'rm -rf {BASE}/conf && cp -r {C}/conf {BASE}/conf')
    y = open(f'{C}/conf/cassandra.yaml').read()
    add = ['cluster_name: stage4-msu', f'data_file_directories: [{MNT}/data]', f'commitlog_directory: {BASE}/commitlog',
           f'hints_directory: {BASE}/hints', f'saved_caches_directory: {BASE}/saved_caches', f'cdc_raw_directory: {BASE}/cdc_raw',
           'min_free_space_per_drive: 50MiB', 'autocompaction_on_startup_enabled: false'] + extra
    keys = {l.split(':')[0] for l in add}
    out = [l for l in y.splitlines() if l.split(':')[0] not in keys or l.startswith((' ', '#', '-'))]
    open(f'{BASE}/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 msu lines ----\n' + '\n'.join(add) + '\n')
    return add


def start_node(extra, heap='2G'):
    add = make_yaml(extra)
    note('YAML tail: ' + '; '.join(add))
    env = dict(os.environ, CASSANDRA_CONF=BASE + '/conf', CASSANDRA_LOG_DIR=BASE + '/logs', MAX_HEAP_SIZE=heap)
    env.pop('HEAP_NEWSIZE', None)
    sh(f'rm -f {BASE}/cassandra.pid; bin/cassandra -p {BASE}/cassandra.pid > {BASE}/stdout.txt 2>&1', env=env)


def wait_up(timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pid() is None:
            fail('node died during start; ' + open(BASE + '/stdout.txt').read()[-600:])
        _, st = sh('bin/nodetool statusbinary', check=False, quiet=True)
        _, ns = sh('bin/nodetool status', check=False, quiet=True)
        if re.search(r'^running\s*$', st, re.M) and re.search(r'^UN\s', ns, re.M):
            note(f'node up after {time.time() - t0:.0f} s'); return
        time.sleep(3)
    fail('node not up')


def logsize(f):
    try:
        return os.path.getsize(f'{BASE}/logs/{f}')
    except OSError:
        return 0


def since(f, off):
    with open(f'{BASE}/logs/{f}', errors='replace') as fh:
        fh.seek(off); return fh.read()


def sstables():
    out = []
    for p in glob.glob(f'{MNT}/data/ks/standard1-*/*-Data.db'):
        out.append(os.path.getsize(p))
    return sorted(out)


def dsize(path):
    _, o = sh(f'du -sb {path} | cut -f1', check=False, quiet=True)
    return int(o.strip() or 0)


def l_invalid():
    fresh_fs()
    off = logsize('system.log')
    start_node(['max_space_usable_for_compactions_in_percentage: 1.5'])
    t0 = time.time()
    while pid() is not None and time.time() - t0 < 120:
        time.sleep(1)
    alive = pid() is not None
    out = open(BASE + '/stdout.txt').read()
    sl = since('system.log', off) if os.path.exists(BASE + '/logs/system.log') else ''
    msg = 'max_space_usable_for_compactions_in_percentage must be between 0 and 1'
    note(f'INVALID 1.5: node alive after {time.time() - t0:.0f} s: {alive}; message in stdout: {msg in out}; in system.log: {msg in sl}')
    note('INVALID stdout tail: ' + out[-700:].replace('\n', ' | '))
    expect('1.5: node refuses to start (process gone) with the line-1017 message', (not alive) and (msg in out or msg in sl))
    if alive:
        stop_node()
    note('INVALID free space on the data fs unchanged by the failed start: used %d B' % used_free()[0])
    umount()


def l_seed():
    fresh_fs()
    # runbook defect D1 (2026-10-27): at 2 GiB heap a memtable flushed every ~38 MB of Data.db (20 small sstables); the seed node gets big memtable pools
    start_node(['memtable_heap_space: 6144MiB', 'memtable_offheap_space: 6144MiB'], heap='12G'); wait_up()
    sh("tools/bin/cassandra-stress write n=1 cl=ONE no-warmup -pop seq=1..1 -schema keyspace=ks 'replication(factor=1)' -rate threads=1 -node 127.0.0.1", timeout=300)
    sh('bin/nodetool disableautocompaction ks standard1')
    sh('bin/nodetool statusautocompaction ks standard1')
    for i in range(CHUNKS):
        lo, hi = 2 + i * CHUNK_ROWS, 1 + (i + 1) * CHUNK_ROWS
        _, o = sh(f"tools/bin/cassandra-stress write n={CHUNK_ROWS} cl=ONE no-warmup -pop seq={lo}..{hi} -schema keyspace=ks 'replication(factor=1)' -rate threads=50 -node 127.0.0.1", timeout=1800)
        e = re.search(r'Total errors\s*:\s*([\d,]+)', o)
        note(f'SEED chunk {i + 1}: seq {lo}..{hi}; errors {e.group(1) if e else "?"}')
        if not e or e.group(1) != '0':
            fail('stress errors')
        sh('bin/nodetool flush ks standard1')
        time.sleep(2)
        note(f'SEED sstables after chunk {i + 1}: {sstables()}')
    ss = sstables()
    expect(f'seed: exactly {CHUNKS} sstables, each Data.db >= 160 MiB; sizes {ss}', len(ss) == CHUNKS and min(ss) >= MIN_SST)
    note(f'SEED du data dir {dsize(MNT + "/data")} B; fs used/avail {used_free()}')
    sh('bin/nodetool drain', check=False)
    stop_node()
    sh(f'rm -rf {SEED} && cp -a {MNT}/data {SEED}')
    note(f'SEED copied to {SEED}: {dsize(SEED)} B')
    umount()
    if ss and (len(ss) != CHUNKS or min(ss) < MIN_SST):
        sys.exit(1)


def heap_used():
    p = pid()
    sh(f'jcmd {p} GC.run', check=False, quiet=True)
    time.sleep(2)
    _, o = sh(f'jcmd {p} GC.heap_info', check=False, quiet=True)
    m = re.search(r'garbage-first heap\s+total (\d+)K, used (\d+)K', o)
    return int(m.group(2)) * 1024 if m else None


def l_run(pct):
    if not os.path.isdir(SEED):
        fail('no seed: run the seed label first')
    fresh_fs()
    sh(f'cp -a {SEED}/. {MNT}/data/')
    note(f'RUN pct={pct}: restored seed; fs used/avail {used_free()}; sstables {sstables()}')
    off_sys, off_dbg = logsize('system.log'), logsize('debug.log')
    start_node([f'max_space_usable_for_compactions_in_percentage: {pct}']); wait_up()
    _, cfg = sh('grep -h "max_space_usable_for_compactions_in_percentage" ' + BASE + '/logs/system.log | tail -1', check=False)
    note('CONFIG line: ' + cfg.strip()[:300])
    ok = f'max_space_usable_for_compactions_in_percentage={pct}' in cfg.replace(' ', '') or f'max_space_usable_for_compactions_in_percentage: {pct}' in cfg or True
    _, sa = sh('bin/nodetool statusautocompaction ks standard1', check=False)
    note('statusautocompaction: ' + sa.strip().replace('\n', ' | ')[-200:])
    sh('bin/nodetool disableautocompaction ks standard1')
    time.sleep(5)
    h = heap_used()
    du0 = dsize(MNT + '/data'); u0, a0 = used_free()
    ss0 = sstables()
    note(f'AT REST pct={pct}: heap used after GC {h} B; data dir du {du0} B; fs used {u0} avail {a0}; sstables {ss0}')
    # one major compaction, sampled
    samples = []
    stop = threading.Event()

    def sampler():
        while not stop.is_set():
            u, a = used_free(); samples.append((int(time.time() * 1000), u, a)); stop.wait(0.5)
    th = threading.Thread(target=sampler, daemon=True); th.start()
    t0 = time.time()
    rc, out = sh('bin/nodetool compact ks standard1', check=False, timeout=1800)
    time.sleep(3)
    stop.set(); th.join(5)
    note(f'COMPACT pct={pct}: nodetool compact rc={rc} in {time.time() - t0:.1f} s; output tail: {out.strip()[-200:]!r}')
    _, cs = sh('bin/nodetool compactionstats', check=False)
    _, ch = sh('bin/nodetool compactionhistory', check=False)
    ss1 = sstables()
    peak = max(s[1] for s in samples); low_avail = min(s[2] for s in samples)
    u1, a1 = used_free()
    sl = since('system.log', off_sys); dl = since('debug.log', off_dbg)
    warn_has_only = len(re.findall(r'has only .* available, but .* is needed', sl))
    reduce_scope = len(re.findall(r'Reducing scope|removing largest SSTable|Not enough space for compaction', sl + dl))
    budgets = re.findall(r'FileStore .* has (\d+) bytes available, checking if we can write (\d+) bytes', dl)
    open(D + f'/samples-{pct}.csv', 'w').write('ms,used,avail\n' + '\n'.join(f'{a},{b},{c}' for a, b, c in samples) + '\n')
    open(D + f'/budget-lines-{pct}.txt', 'w').write('\n'.join(l for l in (sl + dl).splitlines() if re.search(r'has only|has \d+ bytes available|Reducing scope|Not enough space|insufficient space|removing largest', l)) + '\n')
    open(D + f'/compactionhistory-{pct}.txt', 'w').write(cs + '\n' + ch)
    note(f'AFTER pct={pct}: sstables {ss1}; peak fs used {peak} B (rise over at-rest {peak - u0} B); lowest avail {low_avail}; end used {u1}; table total before {sum(ss0)} after {sum(ss1)}')
    note(f'LOG pct={pct}: WARN "has only" lines {warn_has_only}; reduce-scope/not-enough lines {reduce_scope}; DEBUG budget lines {len(budgets)}; first budget/request {budgets[:1]} last {budgets[-1:]}')
    ERR = len(re.findall(r'^ERROR', sl, re.M))
    note(f'LOG pct={pct}: ERROR lines in system.log since start: {ERR}')
    json.dump(dict(pct=pct, heap=h, du0=du0, used0=u0, avail0=a0, ss0=ss0, ss1=ss1, peak=peak, rise=peak - u0, warn=warn_has_only,
                   reduce=reduce_scope, budgets=budgets[:3], budgets_last=budgets[-3:], rc=rc), open(D + f'/result-{pct}.json', 'w'))
    stop_node()
    umount()
    note(f'STOPPED: daemons left: {daemons() or "none"}')


def l_down():
    stop_node(); umount()
    note('down: daemons left: ' + (daemons() or 'none'))


def main():
    note(f'LABEL {label} start {time.strftime("%F %T %Z")}; harness md5 ' + subprocess.run(f'cd {HARNESS} && md5sum cluster-run.py | cut -c1-12', shell=True, capture_output=True, text=True).stdout.strip())
    if label == 'invalid': l_invalid()
    elif label == 'seed': l_seed()
    elif label.startswith('run-'): l_run(label[4:])
    elif label == 'down': l_down()
    else: fail('unknown label')
    note(f'DONE {label} expected {n_yes}/{n_exp} yes')


try:
    main()
except SystemExit:
    raise
except Exception as e:
    import traceback
    log(traceback.format_exc()); fail(f'{type(e).__name__}: {e}')
