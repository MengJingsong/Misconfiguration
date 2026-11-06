"""Cluster tier (case-file B3, amended A7-A13) for DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.

Usage: python3 -I cluster-run.py <run-dir>      (pc41; <run-dir>/src-ablated made by unit-run.sh)
Pseudo-distributed NN, DN, RM, NM on default ports, NM local dir on a 1 GiB ext4 loop fs under <run-dir>/mnt/ldc0.
teragen 1,000,000 rows once; terasort (1 map, 1 reduce) at free levels L900, L300, L60, with the baseline and then
the ablated hadoop-common jar. A 0.5-s sampler records df Avail and du of usercache. Every command and its output go
to <run-dir>/logs/cluster/cluster-run.log. Any failed check stops the run; every daemon of this run is stopped and the
loop fs unmounted on any exit.
"""
import os, re, subprocess, sys, threading, time, shutil, hashlib, glob, datetime

RUN = os.path.abspath(sys.argv[1])
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2"
JAVA_HOME = "/usr/lib/jvm/java-8-openjdk-amd64"
HH = f"{RUN}/hadoop"
CONF = f"{RUN}/conf"
OUT = f"{RUN}/logs/cluster"
MNT = f"{RUN}/mnt/ldc0"
IMG = f"{RUN}/ldc/nmlocal.img"
JAR = f"{HH}/share/hadoop/common/hadoop-common-3.4.2.jar"
EX = f"{HH}/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.4.2.jar"
MIB = 1024 * 1024
PORTS = [9000, 9870, 9864, 9866, 9867, 8088, 8030, 8031, 8032, 8033, 8040, 8042, 13562]
LEVELS = [("L900", None, None), ("L300", 300, 15), ("L60", 60, 10)]
os.makedirs(OUT, exist_ok=True)
LOG = open(f"{OUT}/cluster-run.log", "a")
ENV = dict(os.environ, JAVA_HOME=JAVA_HOME, HADOOP_HOME=HH, HADOOP_CONF_DIR=CONF,
           HADOOP_LOG_DIR=f"{RUN}/logs/daemons", HADOOP_PID_DIR=f"{RUN}/pids",
           PATH=f"{JAVA_HOME}/bin:{HH}/bin:{HH}/sbin:" + os.environ["PATH"])
started = []


def log(msg):
    line = f"[{datetime.datetime.now():%F %T}] {msg}"
    print(line, flush=True)
    LOG.write(line + "\n")
    LOG.flush()


def sh(cmd, check=True, timeout=600, quiet=False, outfile=None):
    log("+ " + cmd)
    p = subprocess.run(cmd, shell=True, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, timeout=timeout)
    if outfile:
        open(outfile, "w").write(p.stdout)
    if not quiet:
        LOG.write(p.stdout)
        LOG.flush()
    if check and p.returncode != 0:
        print(p.stdout[-3000:])
        raise SystemExit(f"STOP: command failed rc={p.returncode}: {cmd}")
    return p


def stop(msg):
    raise SystemExit("STOP: " + msg)


def write_xml(name, props):
    body = "".join(f"  <property><name>{k}</name><value>{v}</value></property>\n" for k, v in props.items())
    open(f"{CONF}/{name}", "w").write(f'<?xml version="1.0"?>\n<configuration>\n{body}</configuration>\n')


def avail():
    out = subprocess.run(["df", "-B1", "--output=avail", MNT], stdout=subprocess.PIPE, text=True).stdout
    return int(out.split()[-1])


def du_usercache():
    p = f"{MNT}/usercache"
    if not os.path.isdir(p):
        return 0
    out = subprocess.run(["du", "-sb", p], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout
    return int(out.split()[0]) if out.strip() else 0


def mine():
    out = subprocess.run(["ps", "-eo", "pid,cmd"], stdout=subprocess.PIPE, text=True).stdout
    return [l for l in out.splitlines() if RUN in l and "java" in l and "cluster-run.py" not in l]


def daemons(action):
    for kind, d in (("hdfs", "namenode"), ("hdfs", "datanode"), ("yarn", "resourcemanager"), ("yarn", "nodemanager")):
        if action == "stop":
            sh(f"{kind} --daemon stop {d}", check=False)
        else:
            sh(f"{kind} --daemon start {d}")


def wait_cluster():
    t0 = time.time()
    while time.time() - t0 < 120:
        a = sh("hdfs dfsadmin -report", check=False, quiet=True).stdout
        b = sh("yarn node -list", check=False, quiet=True).stdout
        if "Live datanodes (1)" in a and "Total Nodes:1" in b and "RUNNING" in b:
            log("cluster up: 1 live DataNode, 1 RUNNING NodeManager")
            LOG.write(b)
            sh("hdfs dfsadmin -safemode wait", timeout=180)  # A14
            return
        time.sleep(3)
    stop("cluster not up within 120 s")


def wait_appcache_empty():
    t0 = time.time()
    while time.time() - t0 < 120:
        left = glob.glob(f"{MNT}/usercache/*/appcache/application_*")
        if not left:
            return
        time.sleep(2)
    stop(f"application directories not removed within 120 s: {left}")


class Sampler(threading.Thread):
    def __init__(self, path):
        super().__init__(daemon=True)
        self.f = open(path, "w")
        self.f.write("time,epoch,avail,du_usercache\n")
        self.halt = threading.Event()

    def run(self):
        while not self.halt.is_set():
            t = time.time()
            self.f.write(f"{datetime.datetime.fromtimestamp(t):%F %T.%f},{t:.3f},{avail()},{du_usercache()}\n")
            self.f.flush()
            self.halt.wait(max(0.0, 0.5 - (time.time() - t)))
        self.f.close()


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def job(arm, level, target, tol):
    tag = f"{arm}-{level}"
    wait_appcache_empty()
    filler = f"{MNT}/filler"
    if os.path.exists(filler):
        os.remove(filler)
    sh("sync")
    a = avail()
    if target is not None:
        sh(f"fallocate -l {a - target * MIB} {filler}")
        sh("sync")
    a = avail()
    log(f"{tag}: free before job = {a} B = {a / MIB:.1f} MiB")
    if target is not None and abs(a / MIB - target) > tol:
        stop(f"{tag}: free {a / MIB:.1f} MiB outside {target} +- {tol}")
    if target is None and not (850 <= a / MIB <= 950):
        log(f"{tag}: note, L900 free {a / MIB:.1f} MiB outside the expected 850-950 MiB")
    sh(f"df -B1 {MNT}")
    before = set(glob.glob(f"{RUN}/ldc/nmlogs/application_*"))
    s = Sampler(f"{OUT}/{tag}-samples.csv")
    s.start()
    t0 = time.time()
    p = sh(f"timeout 900 yarn jar {EX} terasort -Dmapreduce.job.reduces=1 -Dmapreduce.map.log.level=DEBUG "
           f"/tg /ts-{tag}", check=False, outfile=f"{OUT}/{tag}-client.log")
    time.sleep(2)
    s.halt.set()
    s.join()
    log(f"{tag}: client rc={p.returncode} after {time.time() - t0:.0f} s")
    for l in p.stdout.splitlines():
        if re.search(r"Running job|completed successfully|failed with state|Job .* failed|Launched map tasks|"
                     r"Launched reduce tasks|Failed map tasks|Local disk|FILE: Number of bytes written|Diagnostics", l):
            LOG.write("  | " + l + "\n")
    new = sorted(set(glob.glob(f"{RUN}/ldc/nmlogs/application_*")) - before)
    if len(new) != 1:
        stop(f"{tag}: expected 1 new application log dir, got {new}")
    app = new[0]
    # A15: keep the full application logs (the NM deletes them when it restarts)
    shutil.copytree(app, f"{OUT}/{tag}-applog")
    app = f"{OUT}/{tag}-applog"
    maps = []
    for c in sorted(glob.glob(f"{app}/container_*")):
        sl = f"{c}/syslog"
        if os.path.exists(sl) and re.search(r"\] org\.apache\.hadoop\.mapred\.MapTask: ", open(sl, errors="replace").read()):
            maps.append(sl)
    lm = re.findall(r"Launched map tasks=(\d+)", p.stdout)
    log(f"{tag}: counter Launched map tasks={lm}")
    log(f"{tag}: app {os.path.basename(app)}, map containers {len(maps)}")
    keys = re.compile(r"Requested file size is|bytes available under path|Could not find any valid local directory|"
                      r"Allocated file|Spilling map output|Finished spill|soft limit at|DiskErrorException|"
                      r"Searching for a directory")
    with open(f"{OUT}/{tag}-map-keylines.txt", "w") as kf:
        for sl in maps:
            kf.write(f"== {sl}\n")
            for l in open(sl, errors="replace"):
                if keys.search(l):
                    kf.write(l if len(l) < 2000 else l[:2000] + "...\n")
    sh(f"hdfs dfs -rm -r -f -skipTrash /ts-{tag}", check=False)
    if os.path.exists(filler):
        os.remove(filler)
    return dict(rc=p.returncode, maps=len(maps), app=app)


def main():
    log(f"=== cluster-run.py on {os.uname().nodename}, RUN={RUN}")
    if not os.uname().nodename.startswith("node0"):
        stop("not pc41/node0")
    for f in sorted(os.listdir(HERE)):
        if os.path.isfile(f"{HERE}/{f}"):
            log(f"md5 {md5(f'{HERE}/{f}')} {f}")
    sh("ss -ltn")
    listen = sh("ss -ltnH", quiet=True).stdout
    busy = [p for p in PORTS if re.search(rf":{p}\s", listen)]
    if busy:
        stop(f"default ports busy: {busy}")
    sh("jps -l", check=False)
    sh("ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode|[R]esourceManager|[N]odeManager' | cut -c1-250", check=False)
    if mine():
        stop("processes of this run already running")
    # A7: distribution copy and configuration
    if not os.path.isdir(HH):
        sh(f"cp -a {BASE} {HH}")
    sh(f"{HH}/bin/hadoop version | head -1")
    if os.path.isdir(CONF):
        shutil.rmtree(CONF)
    os.makedirs(CONF)
    sh(f"cp -r {HH}/etc/hadoop/* {CONF}/")
    for d in ("logs/daemons", "pids", "ldc/tmp", "ldc/dfs/name", "ldc/dfs/data", "ldc/nmlogs", "mnt/ldc0"):
        os.makedirs(f"{RUN}/{d}", exist_ok=True)
    with open(f"{CONF}/hadoop-env.sh", "a") as f:
        f.write(f"\nexport JAVA_HOME={JAVA_HOME}\nexport HADOOP_HEAPSIZE_MAX=1g\n"
                f"export HADOOP_LOG_DIR={RUN}/logs/daemons\nexport HADOOP_PID_DIR={RUN}/pids\n")
    write_xml("core-site.xml", {"fs.defaultFS": "hdfs://localhost:9000", "hadoop.tmp.dir": f"{RUN}/ldc/tmp"})
    write_xml("hdfs-site.xml", {"dfs.replication": "1", "dfs.namenode.name.dir": f"{RUN}/ldc/dfs/name",
                                "dfs.datanode.data.dir": f"{RUN}/ldc/dfs/data"})
    write_xml("yarn-site.xml", {
        "yarn.nodemanager.local-dirs": MNT,
        "yarn.nodemanager.log-dirs": f"{RUN}/ldc/nmlogs",
        "yarn.nodemanager.disk-health-checker.max-disk-utilization-per-disk-percentage": "100.0",
        "yarn.nodemanager.disk-health-checker.min-free-space-per-disk-mb": "0",
        "yarn.nodemanager.resource.memory-mb": "4096",
        "yarn.nodemanager.aux-services": "mapreduce_shuffle",
        "yarn.nodemanager.vmem-check-enabled": "false",
        "yarn.log-aggregation-enable": "false",
        "yarn.nodemanager.delete.debug-delay-sec": "0"})
    write_xml("mapred-site.xml", {
        "mapreduce.framework.name": "yarn",
        "mapreduce.map.memory.mb": "1024",
        "mapreduce.task.io.sort.mb": "100",
        "mapreduce.map.maxattempts": "1",
        "yarn.app.mapreduce.am.env": f"HADOOP_MAPRED_HOME={HH}",
        "mapreduce.map.env": f"HADOOP_MAPRED_HOME={HH}",
        "mapreduce.reduce.env": f"HADOOP_MAPRED_HOME={HH}"})
    sh(f"cat {CONF}/core-site.xml {CONF}/hdfs-site.xml {CONF}/yarn-site.xml {CONF}/mapred-site.xml")
    # loop filesystem
    if subprocess.run(["mountpoint", "-q", MNT]).returncode != 0:
        if not os.path.exists(IMG):
            sh(f"truncate -s 1G {IMG}")
            sh(f"mkfs.ext4 -q -F {IMG}")
        sh(f"sudo mount -o loop {IMG} {MNT}")
        sh(f"sudo chown jason92 {MNT}")
    sh(f"df -B1 {MNT}")
    sh("hdfs namenode -format -nonInteractive -force", quiet=True)
    log(f"md5 baseline jar {md5(JAR)}")
    daemons("start")
    started.append(1)
    wait_cluster()
    sh(f"yarn jar {EX} teragen -Dmapreduce.job.maps=1 1000000 /tg", outfile=f"{OUT}/teragen-client.log", timeout=900)
    sh("hdfs dfs -ls /tg")
    results = {}
    for arm in ("baseline", "ablated"):
        if arm == "ablated":
            src = f"{RUN}/src-ablated/hadoop-common-project/hadoop-common"
            sh(f"git -C {RUN}/src-ablated diff --numstat")
            sh(f"cd {src} && mvn -o -B package -DskipTests -Dmaven.javadoc.skip=true > {OUT}/ablated-jar-build.log 2>&1",
               timeout=1800)
            sh(f"grep -E 'BUILD SUCCESS|BUILD FAILURE' {OUT}/ablated-jar-build.log")
            newjar = f"{src}/target/hadoop-common-3.4.2.jar"
            daemons("stop")
            time.sleep(5)
            if mine():
                stop(f"processes left after stop: {mine()}")
            if not os.path.exists(f"{RUN}/hadoop-common-3.4.2.jar.orig"):
                shutil.copy2(JAR, f"{RUN}/hadoop-common-3.4.2.jar.orig")
            shutil.copy2(newjar, JAR)
            log(f"md5 orig {md5(RUN + '/hadoop-common-3.4.2.jar.orig')} ablated(src) {md5(newjar)} installed {md5(JAR)}")
            if md5(JAR) == md5(f"{RUN}/hadoop-common-3.4.2.jar.orig"):
                stop("ablated jar identical to the original")
            daemons("start")
            wait_cluster()
        for level, target, tol in LEVELS:
            r = job(arm, level, target, tol)
            results[(arm, level)] = r
            if r["maps"] != 1:
                log(f"{arm}-{level}: {r['maps']} map containers (A13e: invalid job)")
            if arm == "baseline" and level == "L900":
                kl = open(f"{OUT}/baseline-L900-map-keylines.txt").read()
                if "Requested file size is" not in kl:
                    stop("first-trigger check: no 'Requested file size is' note in the baseline L900 map syslog")
    log("results: " + repr({f"{a}-{l}": (r["rc"], r["maps"]) for (a, l), r in results.items()}))


def teardown():
    if started:
        daemons("stop")
        time.sleep(5)
    for _ in range(10):
        if not mine():
            break
        time.sleep(3)
    left = mine()
    log(f"processes of this run left: {left if left else 'none'}")
    if subprocess.run(["mountpoint", "-q", MNT]).returncode == 0:
        sh(f"sudo umount {MNT}", check=False)
    sh("ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode|[R]esourceManager|[N]odeManager|[Y]arnChild|[M]RAppMaster' | cut -c1-200",
       check=False)


if __name__ == "__main__":
    try:
        main()
        log("=== done")
    finally:
        teardown()
