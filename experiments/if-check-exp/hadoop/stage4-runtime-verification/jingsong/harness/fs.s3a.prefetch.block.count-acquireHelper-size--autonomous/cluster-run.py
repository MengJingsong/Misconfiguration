#!/usr/bin/env python3
"""Cluster tier (case-file B3, amended A5-A9) for fs.s3a.prefetch.block.count-acquireHelper-size--autonomous.

Usage (on the stage-4 node): python3 -I cluster-run.py <run-dir> [--only RUN,RUN...]
<run-dir> must hold: hadoop/ (copy of the built distribution), conf/ (HADOOP_CONF_DIR), tools/s3proxy-2.1.0-jar-with-dependencies.jar
and tools/s3proxy.conf. Starts S3Proxy on 127.0.0.1:9000, uploads the objects, runs every read with histogram sampling every 2 s and
a live heap dump, counts arrays offline, stops S3Proxy and checks that no JVM of this run is left. Logs every command and its output
to <run-dir>/logs/cluster/cluster-run.log; per-run files in <run-dir>/out/; summary in <run-dir>/out/summary.tsv.
"""
import os, re, signal, socket, subprocess, sys, time

RUN = os.path.abspath(sys.argv[1])
ONLY = None
if '--only' in sys.argv:
    ONLY = sys.argv[sys.argv.index('--only') + 1].split(',')
HERE = os.path.dirname(os.path.abspath(__file__))
J8 = '/usr/lib/jvm/java-8-openjdk-amd64'
J11 = '/usr/lib/jvm/java-11-openjdk-amd64'
HADOOP = f'{RUN}/hadoop/bin/hadoop'
OUT = f'{RUN}/out'
DUMPS = f'{RUN}/dumps'
LOGD = f'{RUN}/logs/cluster'
for d in (OUT, DUMPS, LOGD, f'{RUN}/data', f'{RUN}/classes'):
    os.makedirs(d, exist_ok=True)
LOG = open(f'{LOGD}/cluster-run.log', 'a')
MiB = 1 << 20
OBJ_LEN = 2048 * MiB
SMALL_LEN = 16 * MiB


def log(msg):
    line = f'[{time.strftime("%F %T")}] {msg}'
    print(line, flush=True)
    LOG.write(line + '\n'); LOG.flush()


def sh(cmd, check=True, timeout=1800, env=None):
    log(f'+ {cmd}')
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env)
    out = (p.stdout + p.stderr).rstrip()
    if out:
        LOG.write(out + '\n'); LOG.flush()
    if check and p.returncode != 0:
        log(f'STOP: rc={p.returncode}: {out[-2000:]}')
        raise SystemExit(2)
    return p.returncode, out


def base_env(xopts):
    e = dict(os.environ)
    e['JAVA_HOME'] = J8
    e['HADOOP_CONF_DIR'] = f'{RUN}/conf'
    e['HADOOP_CLIENT_OPTS'] = xopts
    e['HADOOP_CLASSPATH'] = f'{RUN}/classes'
    return e


def our_jvms():
    """pid -> cmdline of JVMs started from this run folder (S3Proxy or Hadoop client)."""
    res = {}
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        try:
            cmd = open(f'/proc/{pid}/cmdline', 'rb').read().replace(b'\0', b' ').decode(errors='replace')
        except OSError:
            continue
        if 'java' in cmd.split(' ')[0] and RUN in cmd:
            res[int(pid)] = cmd
    return res


def port_open(port):
    s = socket.socket()
    s.settimeout(0.5)
    try:
        return s.connect_ex(('127.0.0.1', port)) == 0
    finally:
        s.close()


S3P = {'pid': None}


def start_s3proxy():
    if port_open(9000):
        log('STOP: port 9000 already in use'); raise SystemExit(3)
    os.makedirs(f'{RUN}/s3store/prefetch', exist_ok=True)
    cmd = [f'{J11}/bin/java', '-Xmx1g', '-jar', f'{RUN}/tools/s3proxy-2.1.0-jar-with-dependencies.jar',
           '--properties', f'{RUN}/tools/s3proxy.conf']
    log('+ ' + ' '.join(cmd) + f' > {LOGD}/s3proxy.log')
    p = subprocess.Popen(cmd, stdout=open(f'{LOGD}/s3proxy.log', 'a'), stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    S3P['pid'] = p.pid
    for _ in range(60):
        if port_open(9000):
            log(f's3proxy up, pid {p.pid}')
            return
        time.sleep(0.5)
    log('STOP: s3proxy did not start'); raise SystemExit(3)


def teardown():
    pid = S3P['pid']
    if pid:
        log(f'stopping s3proxy pid {pid}')
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        for _ in range(30):
            if not port_open(9000):
                break
            time.sleep(0.5)
    for pid, cmd in our_jvms().items():
        log(f'killing leftover JVM {pid}: {cmd[:150]}')
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    time.sleep(1)
    left = our_jvms()
    log(f'leftover JVMs of this run after teardown: {len(left)}; port 9000 open: {port_open(9000)}')


def hist_B(pid):
    p = subprocess.run(f'{J8}/bin/jcmd {pid} GC.class_histogram', shell=True, capture_output=True, text=True)
    m = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+\[B\s*$', p.stdout, re.M)
    t = re.search(r'^Total\s+(\d+)\s+(\d+)', p.stdout, re.M)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), (int(t.group(2)) if t else -1)


def jstat_used(pid):
    p = subprocess.run(f'{J8}/bin/jstat -gc {pid}', shell=True, capture_output=True, text=True)
    lines = p.stdout.strip().splitlines()
    if len(lines) < 2:
        return None
    h = lines[0].split(); v = lines[1].split()
    d = dict(zip(h, v))
    try:
        return sum(float(d[k]) for k in ('S0U', 'S1U', 'EU', 'OU')) * 1024
    except (KeyError, ValueError):
        return None


def run_read(name, cmd, xopts, dump_at=None, main_cls='org.apache.hadoop.fs.FsShell', timeout=300):
    """Start one client pipeline, sample it, return a dict of raw readings."""
    env = base_env(xopts)
    tsv = open(f'{OUT}/{name}.tsv', 'w')
    tsv.write('t_s\tpid\tB_instances\tB_bytes\theap_total_live\tjstat_used\n')
    before = set(our_jvms())
    full = f'{cmd}; echo "PIPESTATUS=${{PIPESTATUS[*]}}" > {OUT}/{name}.status'
    log(f'RUN {name}: HADOOP_CLIENT_OPTS="{xopts}" bash -c \'{full}\'')
    p = subprocess.Popen(['bash', '-c', full], env=env, start_new_session=True)
    t0 = time.monotonic()
    pid = None
    dumped = None
    while p.poll() is None:
        el = time.monotonic() - t0
        if el > timeout:
            log(f'{name}: TIMEOUT {timeout}s, jstack then kill (A11)')
            if pid is not None:
                subprocess.run(f'{J8}/bin/jstack {pid} > {OUT}/{name}.jstack 2>&1', shell=True)
                h = hist_B(pid)
                log(f'{name}: jstack saved; last [B {h}')
            os.killpg(p.pid, signal.SIGKILL)
            break
        if pid is None:
            for q, c in our_jvms().items():
                if q not in before and main_cls in c:
                    pid = q
                    log(f'{name}: client pid {pid}')
        if pid is not None:
            if dump_at is not None and dumped is None and el >= dump_at:
                f = f'{DUMPS}/{name}.hprof'
                rc = subprocess.run(f'{J8}/bin/jcmd {pid} GC.heap_dump {f}', shell=True, capture_output=True,
                                    text=True)
                dumped = (round(el, 1), f, rc.returncode, (rc.stdout + rc.stderr).strip()[-200:])
                log(f'{name}: heap dump at {el:.1f}s rc={rc.returncode} {dumped[3]}')
            h = hist_B(pid)
            u = jstat_used(pid)
            if h:
                tsv.write(f'{el:.1f}\t{pid}\t{h[0]}\t{h[1]}\t{h[2]}\t{u if u is not None else ""}\n'); tsv.flush()
        time.sleep(2)
    p.wait()
    tsv.close()
    el = time.monotonic() - t0
    status = open(f'{OUT}/{name}.status').read().strip() if os.path.exists(f'{OUT}/{name}.status') else 'none'
    log(f'{name}: finished after {el:.1f}s, {status}')
    return {'pid': pid, 'dump': dumped, 'status': status, 'elapsed': round(el, 1)}


def main():
    log(f'=== cluster-run.py on {socket.gethostname()} run={RUN}')
    sh(f'md5sum {HERE}/*')
    sh(f'{J8}/bin/java -version')
    sh(f'JAVA_HOME={J8} HADOOP_CONF_DIR={RUN}/conf {HADOOP} version | head -1')
    sh(f'df -h {RUN} | tail -1; free -g | head -2')
    sh("ss -ltn | grep -E ':9000 ' || echo 'port 9000 free'")
    if our_jvms():
        log(f'STOP: JVMs of this run already running: {our_jvms()}'); raise SystemExit(3)
    sh(f'cat {RUN}/conf/core-site.xml')
    sh(f'grep -E "^export (JAVA_HOME|HADOOP_OPTIONAL_TOOLS|HADOOP_LOG_DIR)" {RUN}/conf/hadoop-env.sh')
    # RandomReads class (A7)
    sh(f'{J8}/bin/javac -d {RUN}/classes -cp "$(JAVA_HOME={J8} HADOOP_CONF_DIR={RUN}/conf {HADOOP} classpath)" '
       f'{HERE}/RandomReads.java')
    start_s3proxy()
    try:
        env = base_env('-Xmx1g')
        # B3c data: one 2 GiB object, one 16 MiB object (A6d)
        if not os.path.exists(f'{RUN}/data/obj.bin'):
            sh(f'dd if=/dev/urandom of={RUN}/data/obj.bin bs=1M count=2048 status=none')
            sh(f'dd if=/dev/urandom of={RUN}/data/small.bin bs=1M count=16 status=none')
        sh(f'md5sum {RUN}/data/obj.bin {RUN}/data/small.bin; ls -l {RUN}/data')
        rc, out = sh(f'{HADOOP} fs -ls s3a://prefetch/', check=False, env=env)
        if 'obj.bin' not in out:
            sh(f'{HADOOP} fs -put {RUN}/data/obj.bin s3a://prefetch/obj.bin', env=env)
        if 'small.bin' not in out:
            sh(f'{HADOOP} fs -put {RUN}/data/small.bin s3a://prefetch/small.bin', env=env)
        sh(f'{HADOOP} fs -ls s3a://prefetch/', env=env)

        X1 = '-Xms64m -Xmx1g -XX:+UseParallelGC -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=' + DUMPS
        XT = '-Xms64m -Xmx256m -Xmn32m -XX:+UseParallelGC -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=' + DUMPS
        T = f'python3 -I {HERE}/throttle.py'
        CAT = f'{HADOOP} fs -Dfs.iostatistics.logging.level=info'
        runs = []
        # controls first: classic (A8b baseline) and local baseline
        for n in (1, 16):
            runs.append((f'classic-n{n}', f'{CAT} -Dfs.s3a.prefetch.block.count={n} -Dfs.s3a.input.stream.type=classic '
                         f'-cat s3a://prefetch/obj.bin 2> {OUT}/classic-n{n}.err | {T} 40 > {OUT}/classic-n{n}.throttle',
                         X1, 10, 'org.apache.hadoop.fs.FsShell'))
        runs.append(('local', f'{CAT} -cat file://{RUN}/data/obj.bin 2> {OUT}/local.err | {T} 40 > {OUT}/local.throttle',
                     X1, None, 'org.apache.hadoop.fs.FsShell'))
        for n in (1, 4, 8, 16):
            runs.append((f'seq-n{n}', f'{CAT} -Dfs.s3a.prefetch.block.count={n} -cat s3a://prefetch/obj.bin '
                         f'2> {OUT}/seq-n{n}.err | {T} 40 > {OUT}/seq-n{n}.throttle', X1, 10, 'org.apache.hadoop.fs.FsShell'))
        for n in (4, 8):
            runs.append((f'tight-n{n}', f'{CAT} -Dfs.s3a.prefetch.block.count={n} -cat s3a://prefetch/obj.bin '
                         f'2> {OUT}/tight-n{n}.err | {T} 40 > {OUT}/tight-n{n}.throttle', XT, None,
                         'org.apache.hadoop.fs.FsShell'))
        for n in (1, 16):
            runs.append((f'small-n{n}', f'{CAT} -Dfs.s3a.prefetch.block.count={n} -cat s3a://prefetch/small.bin '
                         f'2> {OUT}/small-n{n}.err | {T} 1 > {OUT}/small-n{n}.throttle', X1, 5,
                         'org.apache.hadoop.fs.FsShell'))
        for n in (1, 8):
            runs.append((f'rr-n{n}', f'{HADOOP} ifchk.RandomReads s3a://prefetch/obj.bin {RUN}/data/obj.bin {n} 100 {MiB} '
                         f'> {OUT}/rr-n{n}.out 2> {OUT}/rr-n{n}.err', X1, None, 'ifchk.RandomReads'))
        results = {}
        for name, cmd, xo, dump_at, cls in runs:
            if ONLY and name not in ONLY:
                continue
            r = run_read(name, cmd, xo, dump_at, cls)
            if our_jvms().keys() - {S3P['pid']}:
                time.sleep(3)
            left = {q: c for q, c in our_jvms().items() if 's3proxy' not in c}
            if left:
                log(f'STOP: client JVM left after {name}: {left}'); raise SystemExit(4)
            if r['dump']:
                f = r['dump'][1]
                rc, out = sh(f'python3 -I {HERE}/hprof_count.py {f} {32 * MiB} {16 * MiB}', check=False)
                r['arrays'] = out.strip().splitlines()[-1] if out else ''
                sh(f'ls -l {f}; rm -f {f}')
            results[name] = r
            with open(f'{OUT}/{name}.readings', 'w') as fh:
                fh.write(repr(r) + '\n')
            log(f'{name}: {r}')
        sh(f'ls -l {DUMPS}', check=False)
    finally:
        teardown()
    log('=== done')


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        teardown()
        raise
