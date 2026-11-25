# Stage-4 harness, order 20, cluster tier B3d sampler. Run with python3 -I.
# Usage: sample.py <run> <label> <jn_pid> <outdir>
# Takes: jcmd GC.class_histogram (forces a full GC: live objects) -> [B bytes/count, TreeMap$Entry count,
# Long count; GC.heap_info; jstat -gc; JN JMX Journal-ns1 bean; /proc VmRSS/VmHWM; du -sb jn.
# Appends one CSV row to <outdir>/readings.csv and keeps the raw histogram head in <outdir>/histo/.
import csv, json, os, subprocess, sys, time, urllib.request

run, label, pid, outdir = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
J = "/usr/lib/jvm/java-8-openjdk-amd64/bin/"
os.makedirs(os.path.join(outdir, "histo"), exist_ok=True)
ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def sh(args):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True).stdout

h = sh([J + "jcmd", pid, "GC.class_histogram"])
with open(os.path.join(outdir, "histo", "%s-%s.txt" % (run, label)), "w") as f:
    f.write("\n".join(h.splitlines()[:40]) + "\n")
row = {"bytes_B": "", "count_B": "", "treemap_entry": "", "long": "", "histo_total_bytes": ""}
for line in h.splitlines():
    p = line.split()
    if len(p) >= 4 and p[0].endswith(":"):
        name = p[3]
        if name == "[B":
            row["count_B"], row["bytes_B"] = p[1], p[2]
        elif name == "java.util.TreeMap$Entry":
            row["treemap_entry"] = p[1]
        elif name == "java.lang.Long":
            row["long"] = p[1]
    elif len(p) >= 3 and p[0] == "Total":
        row["histo_total_bytes"] = p[2]
hi = sh([J + "jcmd", pid, "GC.heap_info"])
with open(os.path.join(outdir, "histo", "%s-%s-heapinfo.txt" % (run, label)), "w") as f:
    f.write(hi)
js = sh([J + "jstat", "-gc", pid]).split("\n")
ou = ""
try:
    hdr, val = js[0].split(), js[1].split()
    ou = val[hdr.index("OU")]
except Exception:
    pass
jmx = {}
try:
    with urllib.request.urlopen("http://127.0.0.1:8480/jmx?qry=Hadoop:service=JournalNode,name=Journal-ns1", timeout=10) as r:
        beans = json.load(r).get("beans", [])
        if beans:
            jmx = beans[0]
except Exception as e:
    jmx = {"err": str(e)}
rss = hwm = ""
try:
    for line in open("/proc/%s/status" % pid):
        if line.startswith("VmRSS:"):
            rss = line.split()[1]
        if line.startswith("VmHWM:"):
            hwm = line.split()[1]
except Exception:
    pass
du = sh(["du", "-sb", os.path.join(os.path.dirname(outdir.rstrip("/")), "data", "jn")]).split("\t")[0]
out = {"ts": ts, "run": run, "label": label, **row, "jstat_OU_KB": ou,
       "BytesWritten": jmx.get("BytesWritten", ""), "BatchesWritten": jmx.get("BatchesWritten", ""),
       "TxnsWritten": jmx.get("TxnsWritten", ""),
       "CacheMissNumOps": jmx.get("RpcRequestCacheMissAmountNumOps", ""),
       "CacheMissAvg": jmx.get("RpcRequestCacheMissAmountAvgTxns", jmx.get("RpcRequestCacheMissAmountAvgTime", "")),
       "TxnsServedViaRpc": jmx.get("TxnsServedViaRpc", ""), "RpcEmptyResponses": jmx.get("RpcEmptyResponses", ""),
       "VmRSS_KB": rss, "VmHWM_KB": hwm, "du_jn": du, "jmx_err": jmx.get("err", "")}
fn = os.path.join(outdir, "readings.csv")
new = not os.path.exists(fn)
with open(fn, "a", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out.keys()))
    if new:
        w.writeheader()
    w.writerow(out)
print("SAMPLE " + json.dumps(out))
if label == "baseline" or label == "final":
    with open(os.path.join(outdir, "histo", "%s-%s-jmx.json" % (run, label)), "w") as f:
        json.dump(jmx, f, indent=1)
