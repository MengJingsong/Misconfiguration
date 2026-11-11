#!/usr/bin/env python3
"""Cluster tier (case-file B3, amended A4-A8) for
yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous

Usage: python3 -I cluster-run.py <run-dir>      (e.g. /mydata/yang-s4/<stem>-run1)

Pseudo-distributed Hadoop 3.4.2 on this node (NameNode, DataNode, ResourceManager, NodeManager
with 12288 MB), runs C1..C4 of B3b in order, samples every 2 s for 120 s, and writes
<run-dir>/logs/cluster/{cluster-run.log, run-C*.tsv, summary.txt, ...}.
Every command and its output go to cluster-run.log. Any failed step or wait timeout (180 s) stops
the run (runbook stop). Every daemon, app, client and hog process it started is stopped on any exit.
"""
import json, os, signal, statistics, subprocess, sys, time, urllib.request, hashlib, shutil, glob

RUN = os.path.abspath(sys.argv[1])
HERE = os.path.dirname(os.path.abspath(__file__))
JAVA_HOME = "/usr/lib/jvm/java-8-openjdk-amd64"
BASE_DIST = "/mydata/yang-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2"
M2 = os.path.expanduser("~/.m2/repository/org/apache/hadoop")
DS = f"{M2}/hadoop-yarn-applications-distributedshell/3.4.2/hadoop-yarn-applications-distributedshell-3.4.2.jar"
HH = f"{RUN}/hadoop"
CONF = f"{RUN}/conf"
DATA = f"{RUN}/data"
OUT = f"{RUN}/logs/cluster"
NM_MB = 12288
TIMEOUT = 180
WINDOW, STEP = 120, 2
PORTS = [9000, 9870, 9864, 9866, 9867, 8088, 8030, 8031, 8032, 8033, 8040, 8042]
YARN_JARS = ["api", "client", "common", "registry", "server-common", "server-nodemanager",
             "server-resourcemanager", "server-web-proxy", "server-applicationhistoryservice",
             "server-router", "server-sharedcachemanager", "server-timeline-pluginstorage",
             "server-globalpolicygenerator", "services-core", "services-api",
             "applications-distributedshell", "applications-unmanaged-am-launcher"]
# B3b: run -> (P, T, M)
RUNS = [("C1", 20, 50, 100), ("C2", 20, 25, 100), ("C3", 40, 50, 100), ("C4", 20, 50, 25)]
SUBS = [("u1", 1), ("u2", 1), ("u3", 6)]

os.makedirs(OUT, exist_ok=True)
LOG = open(f"{OUT}/cluster-run.log", "a", buffering=1)
clients = []          # Popen of distributed-shell clients


def log(msg):
    line = f"[{time.strftime('%F %T')}] {msg}"
    print(line, flush=True)
    LOG.write(line + "\n")


def env(user=None):
    e = dict(os.environ)
    e.update(JAVA_HOME=JAVA_HOME, HADOOP_HOME=HH, HADOOP_CONF_DIR=CONF, HADOOP_LOG_DIR=f"{RUN}/logs",
             HADOOP_PID_DIR=f"{RUN}/pids", PATH=f"{HH}/bin:{JAVA_HOME}/bin:" + e["PATH"])
    e.pop("HADOOP_USER_NAME", None)
    if user:
        e["HADOOP_USER_NAME"] = user
    return e


def sh(cmd, check=True, quiet=False, user=None, timeout=300):
    log(f"+ {cmd}")
    p = subprocess.run(cmd, shell=True, env=env(user), capture_output=True, text=True, timeout=timeout)
    out = (p.stdout + p.stderr).rstrip()
    if out and not quiet:
        LOG.write(out[-6000:] + "\n")
    LOG.write(f"  rc={p.returncode}\n")
    if check and p.returncode != 0:
        raise Stop(f"command failed rc={p.returncode}: {cmd}\n{out[-2000:]}")
    return out


class Stop(Exception):
    pass


def rest(path):
    with urllib.request.urlopen(f"http://localhost:8088{path}", timeout=10) as r:
        return json.loads(r.read().decode())


def wait(desc, cond, timeout=TIMEOUT, every=2):
    log(f"wait: {desc} (timeout {timeout} s)")
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        try:
            last = cond()
            if last:
                log(f"  ok after {time.time() - t0:.0f} s: {last}")
                return last
        except Exception as ex:          # REST not up yet, etc.
            last = repr(ex)
        time.sleep(every)
    raise Stop(f"RUNBOOK STOP: timeout waiting for {desc}; last={last}")


def leaves():
    """The B3d selection: every object whose queuePath starts with root.parent. (jq replaced by python, A4)."""
    res = []

    def walk(o):
        if isinstance(o, dict):
            qp = o.get("queuePath") or ""
            if qp.startswith("root.parent."):
                res.append((qp, o.get("absoluteCapacity"), o.get("absoluteMaxCapacity"),
                            (o.get("resourcesUsed") or {}).get("memory"), o.get("numApplications")))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(rest("/ws/v1/cluster/scheduler"))
    return {r[0]: r for r in res}


def queue_obj(path):
    found = []

    def walk(o):
        if isinstance(o, dict):
            if o.get("queuePath") == path:
                found.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(rest("/ws/v1/cluster/scheduler"))
    return found[0] if found else None


def apps():
    a = rest("/ws/v1/cluster/apps").get("apps") or {}
    return a.get("app") or []


def hog(user):
    """B3d: pgrep -f 'hog.py ifchk-<u>' count and summed RSS in MiB."""
    pids = subprocess.run(["pgrep", "-f", f"hog.py ifchk-{user}"], capture_output=True, text=True).stdout.split()
    if not pids:
        return 0, 0.0
    rss = subprocess.run(["ps", "-o", "rss=", "-p", ",".join(pids)], capture_output=True, text=True).stdout.split()
    return len(pids), sum(int(x) for x in rss) / 1024.0


def hadoop_procs():
    out = subprocess.run(["ps", "-eo", "pid,cmd"], capture_output=True, text=True).stdout.splitlines()
    return [l for l in out if RUN in l and ("java" in l or "hog.py" in l or "python3" in l)
            and "cluster-run.py" not in l]


def write(path, text):
    with open(path, "w") as f:
        f.write(text)


def prop(k, v):
    return f"  <property><name>{k}</name><value>{v}</value></property>\n"


def xml(props):
    return "<?xml version=\"1.0\"?>\n<configuration>\n" + "".join(prop(k, v) for k, v in props) + "</configuration>\n"


def setup():
    log("=== setup (B3a, amended A4)")
    if not os.path.isdir(HH):
        sh(f"cp -a {BASE_DIST} {HH}")
        for j in YARN_JARS:
            src = f"{M2}/hadoop-yarn-{j}/3.4.2/hadoop-yarn-{j}-3.4.2.jar"
            if not os.path.isfile(src):
                raise Stop(f"missing {src}")
            sh(f"cp {src} {HH}/share/hadoop/yarn/", quiet=True)
        # the standard layout keeps this one in yarn/timelineservice/ (on the RM classpath; used only with timeline v2)
        sh(f"cp {M2}/hadoop-yarn-server-timelineservice/3.4.2/hadoop-yarn-server-timelineservice-3.4.2.jar "
           f"{HH}/share/hadoop/yarn/timelineservice/", quiet=True)
    sh(f"ls {HH}/share/hadoop/yarn/*.jar | wc -l")
    os.makedirs(CONF, exist_ok=True)
    for d in ("data", "logs", "pids"):
        os.makedirs(f"{RUN}/{d}", exist_ok=True)
    sh(f"cp -r {HH}/etc/hadoop/* {CONF}/", quiet=True)   # A10
    with open(f"{CONF}/hadoop-env.sh", "a") as f:
        f.write(f"\nexport JAVA_HOME={JAVA_HOME}\nexport HADOOP_HEAPSIZE_MAX=1g\n")
    with open(f"{CONF}/log4j.properties", "a") as f:   # B3d option: policy debug lines
        f.write("\nlog4j.logger.org.apache.hadoop.yarn.server.resourcemanager.scheduler.capacity.queuemanagement=DEBUG\n")
    write(f"{CONF}/core-site.xml", xml([("fs.defaultFS", "hdfs://localhost:9000"),
                                         ("hadoop.tmp.dir", f"{DATA}/tmp")]))
    write(f"{CONF}/hdfs-site.xml", xml([("dfs.replication", "1"), ("dfs.namenode.name.dir", f"{DATA}/nn"),
                                         ("dfs.datanode.data.dir", f"{DATA}/dn"),
                                         ("dfs.permissions.enabled", "false")]))
    cs = "org.apache.hadoop.yarn.server.resourcemanager.scheduler.capacity"
    write(f"{CONF}/yarn-site.xml", xml([
        ("yarn.resourcemanager.scheduler.class", f"{cs}.CapacityScheduler"),
        ("yarn.nodemanager.resource.memory-mb", str(NM_MB)),
        ("yarn.nodemanager.resource.cpu-vcores", "12"),
        ("yarn.scheduler.minimum-allocation-mb", "1024"),
        ("yarn.scheduler.maximum-allocation-mb", "4096"),
        ("yarn.nodemanager.vmem-check-enabled", "false"),
        ("yarn.nodemanager.local-dirs", f"{DATA}/nm-local"),
        ("yarn.nodemanager.log-dirs", f"{DATA}/nm-logs"),
        ("yarn.resourcemanager.scheduler.monitor.enable", "true"),
        ("yarn.resourcemanager.scheduler.monitor.policies", f"{cs}.QueueManagementDynamicEditPolicy"),
        ("yarn.resourcemanager.recovery.enabled", "false")]))
    write(f"{RUN}/hog.py", open(f"{HERE}/hog.py").read())
    write(f"{RUN}/hog.sh", f"#!/bin/bash\nexec python3 {RUN}/hog.py \"$@\"\n")
    os.chmod(f"{RUN}/hog.sh", 0o755)


def cs_xml(P, T, M):
    return xml([("yarn.scheduler.capacity.root.queues", "default,parent"),
                ("yarn.scheduler.capacity.root.default.capacity", str(100 - P)),
                ("yarn.scheduler.capacity.root.parent.capacity", str(P)),
                ("yarn.scheduler.capacity.root.parent.auto-create-child-queue.enabled", "true"),
                ("yarn.scheduler.capacity.root.parent.leaf-queue-template.capacity", str(T)),
                ("yarn.scheduler.capacity.root.parent.leaf-queue-template.maximum-capacity", str(M)),
                ("yarn.scheduler.capacity.root.parent.leaf-queue-template.user-limit-factor", "100"),
                ("yarn.scheduler.capacity.queue-mappings", "u:%user:root.parent.%user"),
                ("yarn.scheduler.capacity.queue-mappings-override.enable", "true")])


def prechecks():
    log("=== prechecks")
    sh(f"{JAVA_HOME}/bin/jps -l", check=False)
    procs = subprocess.run("ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode|[R]esourceManager|[N]odeManager'",
                           shell=True, capture_output=True, text=True).stdout.strip()
    log(f"hadoop daemons before start: {procs or 'none'}")
    if procs:
        raise Stop("another Hadoop daemon is running on this node")
    ss = subprocess.run(["ss", "-ltnH"], capture_output=True, text=True).stdout
    busy = [p for p in PORTS if any(l.split()[3].endswith(f":{p}") for l in ss.splitlines() if len(l.split()) > 3)]
    log(f"ports busy: {busy or 'none'}")
    if busy:
        raise Stop(f"ports in use: {busy}")
    sh("free -m")
    sh(f"df -h {RUN}")


def instrument_check_hog():
    log("=== instrument check: hog.py standalone RSS (sampler known-answer, not a reading)")
    p = subprocess.Popen(["python3", f"{RUN}/hog.py", "ifchk-calib"])
    try:
        n, rss = 0, 0.0
        for _ in range(30):
            time.sleep(1)
            n, rss = hog("calib")
            if rss > 590:
                break
        time.sleep(2)
        n, rss = hog("calib")
        log(f"INSTRUMENT hog calib: count={n} rss_mib={rss:.1f} (expect 1 process, ~600-620 MiB)")
        if n != 1 or not (590 <= rss <= 640):
            raise Stop("instrument check failed: hog RSS sampler")
    finally:
        p.kill()
        p.wait()


def start_hdfs():
    log("=== HDFS (B3e step 1)")
    sh("hdfs namenode -format -nonInteractive", quiet=True)
    sh("hdfs --daemon start namenode")
    sh("hdfs --daemon start datanode")
    wait("1 live datanode", lambda: "Live datanodes (1)" in sh("hdfs dfsadmin -report", check=False, quiet=True)
         and "Live datanodes (1)")
    wait("safemode off", lambda: "OFF" in sh("hdfs dfsadmin -safemode get", check=False, quiet=True) and "OFF")


def start_rm():
    sh("yarn --daemon start resourcemanager")
    wait("RM REST up", lambda: rest("/ws/v1/cluster/info")["clusterInfo"]["state"] == "STARTED" and "STARTED")


def node_ok():
    nodes = (rest("/ws/v1/cluster/nodes").get("nodes") or {}).get("node") or []
    run = [n for n in nodes if n.get("state") == "RUNNING"]
    if len(run) == 1 and (run[0].get("totalResource") or {}).get("memory") == NM_MB:
        return f"1 RUNNING node, {NM_MB} MB"
    return None


def submit(run, user, n):
    cmd = (f"yarn jar {DS} -jar {DS} -shell_script {RUN}/hog.sh -shell_args ifchk-{user} "
           f"-num_containers {n} -container_memory 1024 -master_memory 1024 -queue default -timeout 1800000")
    log(f"+ [HADOOP_USER_NAME={user}] nohup {cmd} > client-{run}-{user}.log")
    f = open(f"{OUT}/client-{run}-{user}.log", "w")
    p = subprocess.Popen(cmd, shell=True, env=env(user), stdout=f, stderr=subprocess.STDOUT,
                         start_new_session=True)
    clients.append(p)
    return p


def kill_apps():
    try:
        for a in apps():
            if a["state"] in ("NEW", "NEW_SAVING", "SUBMITTED", "ACCEPTED", "RUNNING"):
                sh(f"yarn application -kill {a['id']}", check=False, quiet=True)
    except Exception as ex:
        log(f"kill_apps: RM not reachable ({ex!r})")


def stop_clients():
    for p in clients:
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    for p in clients:
        try:
            p.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
    clients.clear()


def one_run(name, P, T, M, first):
    log(f"=== run {name}: P={P} T={T} M={M}")
    write(f"{CONF}/capacity-scheduler.xml", cs_xml(P, T, M))
    sh(f"cat {CONF}/capacity-scheduler.xml")
    if not first:
        sh("yarn --daemon stop resourcemanager")
    start_rm()
    if first:
        sh("yarn --daemon start nodemanager")
    wait("1 RUNNING node with 12288 MB", node_ok)
    par = queue_obj("root.parent")
    log(f"INSTRUMENT REST: root.parent capacity={par and par.get('capacity')} absoluteCapacity={par and par.get('absoluteCapacity')} "
        f"(expect {P}); leaves before submit: {list(leaves())}")
    if par is None:
        raise Stop("REST: root.parent not found")
    for user, n in SUBS:
        submit(name, user, n)
        if user != "u3":
            want = 2048
            wait(f"root.parent.{user} resourcesUsed.memory={want}" + (" (first-trigger check, A6c)" if user == "u1" else ""),
                 lambda: (leaves().get(f"root.parent.{user}") or (0, 0, 0, 0))[3] == want and leaves()[f"root.parent.{user}"])
        # first-trigger check (A6c): the leaf must exist under the managed parent
        if user == "u1" and "root.parent.u1" not in leaves():
            raise Stop("RUNBOOK STOP: first-trigger check failed, root.parent.u1 not created")

    def u3_running():
        a = [x for x in apps() if x["user"] == "u3" and x["state"] == "RUNNING"]
        return a and a[0]["id"]
    u3id = wait("u3 app RUNNING", u3_running)
    t_run = time.time()
    last, since = None, time.time()
    while time.time() - t_run < 60:                        # A6d: window starts when stable 10 s
        cur = (leaves().get("root.parent.u3") or (0, 0, 0, None))[3]
        if cur != last:
            last, since = cur, time.time()
        elif time.time() - since >= 10:
            break
        time.sleep(1)
    log(f"window start: u3 allocation {last} MB, {time.time() - t_run:.0f} s after RUNNING")
    sh("free -m")
    sh(f"curl -s http://localhost:8088/ws/v1/cluster/scheduler -o {OUT}/scheduler-{name}-start.json", check=False)
    tsv = open(f"{OUT}/run-{name}.tsv", "w")
    tsv.write("t\tqueuePath\tabsoluteCapacity\tabsoluteMaxCapacity\tusedMB\tnumApps\thogCount\thogRssMiB\n")
    t0 = time.time()
    k = 0
    while True:
        tgt = t0 + k * STEP
        if tgt > t0 + WINDOW:
            break
        time.sleep(max(0, tgt - time.time()))
        L = leaves()
        t = time.time() - t0
        for u in ("u1", "u2", "u3"):
            r = L.get(f"root.parent.{u}") or (f"root.parent.{u}", None, None, None, None)
            c, rss = hog(u)
            tsv.write(f"{t:.1f}\t{r[0]}\t{r[1]}\t{r[2]}\t{r[3]}\t{r[4]}\t{c}\t{rss:.1f}\n")
        tsv.flush()
        k += 1
    tsv.close()
    sh(f"curl -s http://localhost:8088/ws/v1/cluster/scheduler -o {OUT}/scheduler-{name}-end.json", check=False)
    sh(f"curl -s http://localhost:8088/ws/v1/cluster/apps -o {OUT}/apps-{name}.json", check=False)
    sh("yarn application -list -appStates ALL", check=False)
    kill_apps()
    wait("all apps killed", lambda: not [a for a in apps() if a["state"] in ("ACCEPTED", "RUNNING", "SUBMITTED")] and "none active")
    wait("no hog.py processes (30 s)", lambda: not subprocess.run(["pgrep", "-f", "hog.py ifchk-"],
                                                                     capture_output=True).stdout and "empty", timeout=30)
    stop_clients()
    return u3id


def summarize():
    lines = []
    exp = {"C1": (0, 100, 7168, 6, 3650), "C2": (5, 100, 7168, 6, 3650), "C3": (0, 100, 7168, 6, 3650),
           "C4": (0, 25, "<=3072", "<=2", "<=~1220")}
    for name, P, T, M in RUNS:
        f = f"{OUT}/run-{name}.tsv"
        if not os.path.exists(f):
            continue
        rows = [l.rstrip("\n").split("\t") for l in open(f)][1:]
        lines.append(f"EXPECTED {name} u3: absCap={exp[name][0]} absMax={exp[name][1]} usedMB={exp[name][2]} "
                     f"hog={exp[name][3]} rssMiB={exp[name][4]}; u1,u2 2048 MB each")
        for u in ("u1", "u2", "u3"):
            R = [r for r in rows if r[1] == f"root.parent.{u}"]
            def col(i, cast=float):
                v = [cast(r[i]) for r in R if r[i] not in ("None", "")]
                return v
            used, cnt, rss = col(4), col(6, int), col(7)
            absc, absm = sorted(set(col(2))), sorted(set(col(3)))
            med = lambda v: statistics.median(v) if v else None
            lines.append(f"READING {name} {u}: n={len(R)} absCap={absc} absMax={absm} usedMB median={med(used)} "
                         f"min={min(used) if used else None} max={max(used) if used else None} "
                         f"hogCount median={med(cnt)} rssMiB median={med(rss)} min={min(rss) if rss else None} "
                         f"max={max(rss) if rss else None}")
    md5 = []
    for fn in sorted(os.listdir(HERE)):
        p = os.path.join(HERE, fn)
        if os.path.isfile(p):
            md5.append(f"{hashlib.md5(open(p, 'rb').read()).hexdigest()}  {fn}")
    write(f"{OUT}/summary.txt", "\n".join(lines + ["", "harness md5:"] + md5) + "\n")
    for l in lines:
        log(l)


def teardown():
    log("=== teardown")
    try:
        kill_apps()
    except Exception:
        pass
    stop_clients()
    for d in ("yarn --daemon stop nodemanager", "yarn --daemon stop resourcemanager",
              "hdfs --daemon stop datanode", "hdfs --daemon stop namenode"):
        try:
            sh(d, check=False)
        except Exception as ex:
            log(f"{d}: {ex!r}")
    subprocess.run(["pkill", "-u", str(os.getuid()), "-f", "hog.py ifchk-"])
    time.sleep(3)
    left = hadoop_procs()
    for l in left:                       # anything of this run left (AM JVMs, daemons): kill
        pid = int(l.split()[0])
        log(f"killing leftover {l[:200]}")
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    time.sleep(2)
    log(f"leftover processes of this run: {hadoop_procs() or 'none'}")
    sh(f"{JAVA_HOME}/bin/jps -l", check=False)
    procs = subprocess.run("ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode|[R]esourceManager|[N]odeManager'",
                           shell=True, capture_output=True, text=True).stdout.strip()
    log(f"hadoop daemons after teardown: {procs or 'none'}")


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
        instrument_check_hog()
        start_hdfs()
        for i, (name, P, T, M) in enumerate(RUNS):
            one_run(name, P, T, M, first=(i == 0))
    except Stop as ex:
        log(f"STOP: {ex}")
        rc = 2
    except Exception as ex:
        log(f"STOP (unexpected): {ex!r}")
        rc = 3
    finally:
        try:
            summarize()
        except Exception as ex:
            log(f"summarize failed: {ex!r}")
        teardown()
        log(f"EXIT rc={rc}")
    sys.exit(rc)


if __name__ == "__main__":
    main()
