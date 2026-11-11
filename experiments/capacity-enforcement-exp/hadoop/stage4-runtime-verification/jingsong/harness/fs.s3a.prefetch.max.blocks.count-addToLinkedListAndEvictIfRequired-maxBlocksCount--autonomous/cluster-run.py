#!/usr/bin/env python3
"""Cluster tier (case-file B3, amended A4-A7) for
fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.

Usage: python3 -I cluster-run.py <run-dir>     (<run-dir> = /mydata/jingsong-s4/<stem>-run1 on pc29)

moto S3 server on 127.0.0.1:9000 (A4), a 64 MiB object s3a://ifchk-pf/obj64m, SeekReader client runs
N = 1, 4, 16, 1000 (3x each), key unset (1x), sequential -cat (1x), then a pseudo-distributed YARN
(RM + NM) and the distributed-shell container variant N = 2, 1000 (1x each). A sampler counts
fs-cache-*.bin files every 100 ms. Every command and its output go to logs/cluster/cluster-run.log;
any failed step or wait over 180 s stops the run; every process it started is stopped on any exit.
"""
import hashlib, json, os, re, signal, subprocess, sys, time, urllib.request

RUN = os.path.abspath(sys.argv[1])
HERE = os.path.dirname(os.path.abspath(__file__))
JAVA_HOME = "/usr/lib/jvm/java-8-openjdk-amd64"
BASE_DIST = "/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2"
HH = f"{RUN}/hadoop"
CONF, CONF_CTR = f"{RUN}/conf", f"{RUN}/conf-ctr"
OUT = f"{RUN}/logs/cluster"
JARDIR = f"{RUN}/jar"
S3BUF, NMLOCAL = f"{RUN}/s3abuf", f"{RUN}/nm-local"
OBJ = "s3a://ifchk-pf/obj64m"
DS = f"{HH}/share/hadoop/yarn/hadoop-yarn-applications-distributedshell-3.4.2.jar"
TIMEOUT = 180
HOLD = 20
PORTS = [9000, 8088, 8030, 8031, 8032, 8033, 8040, 8042]
CLIENT_RUNS = [(n, r) for n in ("1", "4", "16", "1000") for r in (1, 2, 3)] + [("unset", 1)]
CTR_RUNS = ["2", "1000"]

os.makedirs(OUT, exist_ok=True)
LOG = open(f"{OUT}/cluster-run.log", "a", buffering=1)
procs = {}          # name -> Popen (moto, samplers, clients)
rows = []


class Stop(Exception):
    pass


def log(msg):
    line = f"[{time.strftime('%F %T')}] {msg}"
    print(line, flush=True)
    LOG.write(line + "\n")


def env(conf=CONF):
    e = dict(os.environ)
    e.update(JAVA_HOME=JAVA_HOME, HADOOP_HOME=HH, HADOOP_CONF_DIR=conf,
             PATH=f"{HH}/bin:{JAVA_HOME}/bin:" + e["PATH"])
    for k in ("HADOOP_USER_NAME", "HADOOP_CLIENT_OPTS", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        e.pop(k, None)
    return e


def sh(cmd, check=True, quiet=False, timeout=300, conf=CONF, extra=None):
    log(f"+ {cmd}")
    e = env(conf)
    if extra:
        e.update(extra)
    p = subprocess.run(cmd, shell=True, env=e, capture_output=True, text=True, timeout=timeout)
    out = (p.stdout + p.stderr).rstrip()
    if out and not quiet:
        LOG.write(out[-6000:] + "\n")
    LOG.write(f"  rc={p.returncode}\n")
    if check and p.returncode != 0:
        raise Stop(f"command failed rc={p.returncode}: {cmd}\n{out[-2000:]}")
    return out


def wait(desc, cond, timeout=TIMEOUT, every=1):
    log(f"wait: {desc} (timeout {timeout} s)")
    t0, last = time.time(), None
    while time.time() - t0 < timeout:
        try:
            last = cond()
            if last:
                log(f"  ok after {time.time() - t0:.0f} s: {last}")
                return last
        except Exception as ex:
            last = repr(ex)
        time.sleep(every)
    raise Stop(f"RUNBOOK STOP: timeout waiting for {desc}; last={last}")


def write(path, text):
    with open(path, "w") as f:
        f.write(text)


def xml(props):
    return ("<?xml version=\"1.0\"?>\n<configuration>\n"
            + "".join(f"  <property><name>{k}</name><value>{v}</value></property>\n" for k, v in props)
            + "</configuration>\n")


def ports_busy():
    ss = subprocess.run(["ss", "-ltnH"], capture_output=True, text=True).stdout
    return [p for p in PORTS if any(len(l.split()) > 3 and l.split()[3].endswith(f":{p}") for l in ss.splitlines())]


def hadoop_daemons():
    return subprocess.run("ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode|[R]esourceManager|[N]odeManager'",
                          shell=True, capture_output=True, text=True).stdout.strip()


def run_procs():
    """Processes of this run (command line mentions the run dir), excluding this script."""
    out = subprocess.run(["ps", "-eo", "pid,cmd"], capture_output=True, text=True).stdout.splitlines()[1:]
    me = os.getpid()
    return [l.strip() for l in out if RUN in l and "cluster-run.py" not in l and int(l.split()[0]) != me]


def prechecks():
    log("=== prechecks")
    sh("hostname; uname -r; nproc; free -m", quiet=False)
    sh(f"{JAVA_HOME}/bin/jps -l", check=False)
    d = hadoop_daemons()
    log(f"hadoop daemons before start: {d or 'none'}")
    if d:
        raise Stop("another Hadoop daemon is running on this node")
    b = ports_busy()
    log(f"ports busy: {b or 'none'}")
    if b:
        raise Stop(f"ports in use: {b}")
    sh(f"df -B1 /mydata")


def setup():
    log("=== setup (B3a, amended A4)")
    if not os.path.isdir(HH):
        sh(f"cp -a {BASE_DIST} {HH}")
    sh(f"{HH}/bin/hadoop version | head -1", conf=f"{HH}/etc/hadoop")
    sh(f"ls {HH}/share/hadoop/tools/lib/ | grep -E 'hadoop-aws|bundle'; ls {DS}")
    for d in ("s3abuf", "htmp", "hlogs", "pids", "nm-local", "nm-logs", "jar", "dshome"):
        os.makedirs(f"{RUN}/{d}", exist_ok=True)
    common = [("hadoop.tmp.dir", f"{RUN}/htmp"),
              ("fs.s3a.endpoint", "http://127.0.0.1:9000"),
              ("fs.s3a.endpoint.region", "us-east-1"),
              ("fs.s3a.path.style.access", "true"),
              ("fs.s3a.connection.ssl.enabled", "false"),
              ("fs.s3a.access.key", "testing"),
              ("fs.s3a.secret.key", "testing"),
              ("fs.s3a.input.stream.type", "prefetch"),
              ("fs.s3a.prefetch.block.size", "1048576")]
    yarn = [("yarn.nodemanager.local-dirs", NMLOCAL),
            ("yarn.nodemanager.log-dirs", f"{RUN}/nm-logs"),
            ("yarn.nodemanager.resource.memory-mb", "4096"),
            ("yarn.nodemanager.vmem-check-enabled", "false"),
            ("yarn.resourcemanager.recovery.enabled", "false"),
            ("yarn.nodemanager.delete.debug-delay-sec", "600")]
    for c, buf in ((CONF, True), (CONF_CTR, False)):
        os.makedirs(c, exist_ok=True)
        sh(f"cp -r {HH}/etc/hadoop/* {c}/", quiet=True)
        with open(f"{c}/hadoop-env.sh", "a") as f:
            f.write(f"\nexport JAVA_HOME={JAVA_HOME}\nexport HADOOP_OPTIONAL_TOOLS=hadoop-aws\n"
                    f"export HADOOP_LOG_DIR={RUN}/hlogs\nexport HADOOP_PID_DIR={RUN}/pids\n"
                    f"export HADOOP_HEAPSIZE_MAX=1g\n")
        props = common + ([("fs.s3a.buffer.dir", S3BUF)] if buf else [])
        write(f"{c}/core-site.xml", xml(props))
        write(f"{c}/yarn-site.xml", xml(yarn))
    sh(f"cat {CONF}/core-site.xml; diff {CONF}/core-site.xml {CONF_CTR}/core-site.xml", check=False)
    # SeekReader jar
    sh(f"cp {HERE}/SeekReader.java {JARDIR}/ && cd {JARDIR} && "
       f"{JAVA_HOME}/bin/javac -cp \"$({HH}/bin/hadoop classpath)\" SeekReader.java && "
       f"{JAVA_HOME}/bin/jar cf seekreader.jar SeekReader.class && ls -l seekreader.jar")
    for n in CTR_RUNS:
        write(f"{RUN}/ds-{n}.sh",
              "#!/bin/bash\n"
              f"export JAVA_HOME={JAVA_HOME}\nexport HADOOP_HOME={HH}\nexport HADOOP_CONF_DIR={CONF_CTR}\n"
              "echo \"IFCHK,ctrenv,LOCAL_DIRS=$LOCAL_DIRS\"\n"
              f"exec {HH}/bin/hadoop jar {JARDIR}/seekreader.jar SeekReader "
              f"-Dfs.s3a.prefetch.max.blocks.count={n} {OBJ} {HOLD}\n")
        os.chmod(f"{RUN}/ds-{n}.sh", 0o755)
    md5 = [f"{hashlib.md5(open(os.path.join(HERE, f), 'rb').read()).hexdigest()}  {f}"
           for f in sorted(os.listdir(HERE)) if os.path.isfile(os.path.join(HERE, f))]
    log("harness md5:\n" + "\n".join(md5))


def start_moto():
    log("=== S3 store: moto server (A4)")
    sh(f"{RUN}/venv/bin/python -I -c 'import moto; print(\"moto\", moto.__version__)'")
    f = open(f"{OUT}/moto.log", "w")
    procs["moto"] = subprocess.Popen([f"{RUN}/venv/bin/moto_server", "-H", "127.0.0.1", "-p", "9000"],
                                     stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
    wait("moto port 9000", lambda: 9000 in ports_busy() and "listening")
    # an unsigned curl PUT is answered 400 by moto (attempt 1); create the bucket with boto3 from the venv
    sh(f"{RUN}/venv/bin/python -I -c \"import boto3; s3=boto3.client('s3', endpoint_url='http://127.0.0.1:9000', "
       f"aws_access_key_id='testing', aws_secret_access_key='testing', region_name='us-east-1'); "
       f"s3.create_bucket(Bucket='ifchk-pf'); print([b['Name'] for b in s3.list_buckets()['Buckets']])\"")


def upload():
    log("=== object (B3c) and access check (B3e step 2, A5c)")
    if not os.path.isfile(f"{RUN}/obj64m"):
        sh(f"dd if=/dev/urandom of={RUN}/obj64m bs=1M count=64 status=none")
    md5 = sh(f"md5sum {RUN}/obj64m").split()[0]
    sh(f"hadoop fs -put -f {RUN}/obj64m {OBJ}")
    sh("hadoop fs -ls s3a://ifchk-pf/")
    got = sh(f"hadoop fs -cat {OBJ} | md5sum").split()[0]
    log(f"INSTRUMENT md5 local={md5} s3a={got}")
    if md5 != got:
        raise Stop("object read back differs")
    leftover = list_cache(S3BUF)
    log(f"cache files in s3abuf after the check: {leftover}")


def list_cache(d):
    n = 0
    for root, _, files in os.walk(d):
        n += sum(1 for f in files if f.startswith("fs-cache-") and f.endswith(".bin"))
    return n


def clear(d):
    for root, _, files in os.walk(d):
        for f in files:
            if f.startswith("fs-cache-"):
                os.remove(os.path.join(root, f))


def start_sampler(name, d):
    csv = f"{OUT}/{name}.samples.csv"
    procs["sampler"] = subprocess.Popen(["python3", "-I", f"{HERE}/sampler.py", d, csv], start_new_session=True)
    time.sleep(1)
    return csv


def stop_sampler():
    p = procs.pop("sampler", None)
    if p:
        p.terminate()
        p.wait(timeout=10)


def samples(csv):
    rs = []
    for l in open(csv).read().splitlines()[1:]:
        t, n, b, du = l.split(",")
        rs.append((int(t), int(n), int(b), du))
    return rs


def parse_client(text):
    st = re.findall(r"^IFCHK,stats,([^,]+),([^,]+),(-?\d+),(-?\d+),(-?\d+),(\d+)", text, re.M)
    stream = re.findall(r"^IFCHK,stream,(\S+)", text, re.M)
    lock = len(re.findall(r"deletion would not be attempted", text))
    disabled = len(re.findall(r"Caching disabled", text))
    cacheerr = len(re.findall(r"error adding block to cache", text))
    readerr = len(re.findall(r"^IFCHK,readerror,", text, re.M))
    return st[0] if st else None, stream[0] if stream else None, lock, disabled, cacheerr, readerr


def summarize_run(label, n, rep, csv, text, extra=""):
    st, stream, lock, disabled, cacheerr, readerr = parse_client(text)
    rs = samples(csv)
    if not rs:
        raise Stop(f"{label}: sampler wrote no samples")
    mx_f = max(r[1] for r in rs)
    mx_b = max(r[2] for r in rs)
    end_f = end_b = None
    gauge = ev = evc = None
    if st:
        ts = int(st[5])
        before = [r for r in rs if r[0] <= ts]
        if before:
            end_f, end_b = before[-1][1], before[-1][2]
        gauge, ev, evc = int(st[2]), int(st[3]), int(st[4])
    after_f = rs[-1][1]
    P = gauge + ev if gauge is not None else None
    row = dict(label=label, N=n, rep=rep, samples=len(rs), maxFiles=mx_f, maxBytes=mx_b, endHoldFiles=end_f,
               endHoldBytes=end_b, gauge=gauge, evictions=ev, evictionDurCount=evc, P=P, filesAfterExit=after_f,
               lockTimeoutErrors=lock, cachingDisabled=disabled, cachePutErrors=cacheerr, readErrors=readerr, stream=stream,
               note=extra)
    rows.append(row)
    log("READING " + json.dumps(row))
    with open(f"{OUT}/readings.tsv", "a") as f:
        if f.tell() == 0:
            f.write("\t".join(row.keys()) + "\n")
        f.write("\t".join(str(v) for v in row.values()) + "\n")
    return row


def client_run(n, rep):
    label = f"client-N{n}-r{rep}"
    log(f"=== {label} (B3e step 3)")
    clear(S3BUF)
    if list_cache(S3BUF):
        raise Stop("s3abuf not empty")
    sh("df -B1 /mydata | tail -1")
    csv = start_sampler(label, S3BUF)
    dopt = "" if n == "unset" else f"-Dfs.s3a.prefetch.max.blocks.count={n} "
    cmd = f"hadoop jar {JARDIR}/seekreader.jar SeekReader {dopt}{OBJ} {HOLD}"
    log(f"+ {cmd} > {label}.client.log")
    t0 = time.time()
    with open(f"{OUT}/{label}.client.log", "w") as f:
        p = subprocess.Popen(cmd, shell=True, env=env(), stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        procs["client"] = p
        try:
            rc = p.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            raise Stop(f"RUNBOOK STOP: {label} client over {TIMEOUT} s")
        procs.pop("client", None)
    log(f"  client rc={rc} after {time.time() - t0:.1f} s")
    time.sleep(5)
    stop_sampler()
    sh("df -B1 /mydata | tail -1")
    text = open(f"{OUT}/{label}.client.log").read()
    if rc != 0:
        LOG.write(text[-4000:] + "\n")
        raise Stop(f"{label}: client rc={rc}")
    return summarize_run(label, n, rep, csv, text)


def sequential_cat():
    label = "client-seqcat"
    log(f"=== {label} (B3h sequential control)")
    clear(S3BUF)
    csv = start_sampler(label, S3BUF)
    sh(f"hadoop fs -cat {OBJ} > /dev/null", timeout=TIMEOUT)
    time.sleep(5)
    stop_sampler()
    rs = samples(csv)
    row = dict(label=label, N="unset", rep=1, samples=len(rs), maxFiles=max(r[1] for r in rs),
               maxBytes=max(r[2] for r in rs), filesAfterExit=rs[-1][1])
    rows.append(row)
    log("READING " + json.dumps(row))


def rest(path):
    with urllib.request.urlopen(f"http://localhost:8088{path}", timeout=10) as r:
        return json.loads(r.read().decode())


def start_yarn():
    log("=== YARN (B3e step 4, A4)")
    sh("yarn --daemon start resourcemanager")
    wait("RM REST up", lambda: rest("/ws/v1/cluster/info")["clusterInfo"]["state"] == "STARTED" and "STARTED")
    sh("yarn --daemon start nodemanager")

    def node_ok():
        nodes = (rest("/ws/v1/cluster/nodes").get("nodes") or {}).get("node") or []
        run = [x for x in nodes if x.get("state") == "RUNNING"]
        return len(run) == 1 and f"1 RUNNING node {run[0].get('totalResource')}"
    wait("NM registered", node_ok)


def container_run(n):
    label = f"container-N{n}"
    log(f"=== {label} (B3e step 4)")
    clear(NMLOCAL)
    csv = start_sampler(label, NMLOCAL)
    cmd = (f"yarn jar {DS} -jar {DS} -shell_script {RUN}/ds-{n}.sh -num_containers 1 -container_memory 1024 "
           f"-master_memory 512 -appname ifchk-{label} -timeout 600000")
    log(f"+ [HADOOP_CLIENT_OPTS=-Duser.home={RUN}/dshome] {cmd} > {label}.dsclient.log")
    e = env()
    e["HADOOP_CLIENT_OPTS"] = f"-Duser.home={RUN}/dshome"
    t0 = time.time()
    with open(f"{OUT}/{label}.dsclient.log", "w") as f:
        p = subprocess.Popen(cmd, shell=True, env=e, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        procs["client"] = p
        try:
            rc = p.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            raise Stop(f"RUNBOOK STOP: {label} DS client over {TIMEOUT} s")
        procs.pop("client", None)
    log(f"  DS client rc={rc} after {time.time() - t0:.1f} s")
    time.sleep(5)
    stop_sampler()
    dslog = open(f"{OUT}/{label}.dsclient.log").read()
    m = re.findall(r"(application_\d+_\d+)", dslog)
    app = m[-1] if m else None
    text = ""
    if app:
        outs = sh(f"ls -d {RUN}/nm-logs/{app}/container_*/ 2>/dev/null", check=False, quiet=True).split()
        for d in outs:
            for fn in ("stdout", "stderr"):
                pth = os.path.join(d, fn)
                if os.path.isfile(pth):
                    t = open(pth).read()
                    write(f"{OUT}/{label}.{os.path.basename(d.rstrip('/'))}.{fn}", t)
                    if "IFCHK" in t or fn == "stderr":
                        text += t + "\n"
    if "IFCHK,stats" not in text:
        LOG.write(dslog[-4000:] + "\n" + text[-4000:] + "\n")
        raise Stop(f"{label}: no IFCHK,stats from the container (DS rc={rc}, app={app})")
    return summarize_run(label, n, 1, csv, text, extra=f"app={app} dsrc={rc}")


def teardown():
    log("=== teardown (B3e step 5, B4)")
    stop_sampler()
    p = procs.pop("client", None)
    if p and p.poll() is None:
        os.killpg(p.pid, signal.SIGKILL)
    try:
        for a in (rest("/ws/v1/cluster/apps").get("apps") or {}).get("app") or []:
            if a["state"] in ("NEW", "NEW_SAVING", "SUBMITTED", "ACCEPTED", "RUNNING"):
                sh(f"yarn application -kill {a['id']}", check=False, quiet=True)
    except Exception as ex:
        log(f"RM not reachable for app kill ({ex!r})")
    for d in ("yarn --daemon stop nodemanager", "yarn --daemon stop resourcemanager"):
        try:
            sh(d, check=False)
        except Exception as ex:
            log(f"{d}: {ex!r}")
    p = procs.pop("moto", None)
    if p:
        os.killpg(p.pid, signal.SIGTERM)
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
    time.sleep(2)
    for l in run_procs():
        log(f"killing leftover {l[:200]}")
        try:
            os.kill(int(l.split()[0]), signal.SIGKILL)
        except ProcessLookupError:
            pass
    time.sleep(1)
    log(f"leftover processes of this run: {run_procs() or 'none'}")
    log(f"hadoop daemons after teardown: {hadoop_daemons() or 'none'}")
    log(f"ports busy after teardown: {ports_busy() or 'none'}")
    sh(f"{JAVA_HOME}/bin/jps -l", check=False)


def on_signal(sig, frm):
    raise Stop(f"signal {sig}")


def main():
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    rc = 0
    log(f"=== cluster-run.py {RUN} on {os.uname().nodename}")
    try:
        prechecks()
        setup()
        start_moto()
        upload()
        for n, r in CLIENT_RUNS:
            client_run(n, r)
        sequential_cat()
        start_yarn()
        for n in CTR_RUNS:
            container_run(n)
    except Stop as ex:
        log(f"STOP: {ex}")
        rc = 2
    except Exception as ex:
        log(f"STOP (unexpected): {ex!r}")
        rc = 3
    finally:
        with open(f"{OUT}/readings.json", "w") as f:
            json.dump(rows, f, indent=1)
        teardown()
        log(f"EXIT rc={rc}")
    sys.exit(rc)


if __name__ == "__main__":
    main()
