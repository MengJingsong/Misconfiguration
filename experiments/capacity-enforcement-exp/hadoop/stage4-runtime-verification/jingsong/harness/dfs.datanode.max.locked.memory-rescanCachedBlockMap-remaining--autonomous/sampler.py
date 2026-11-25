#!/usr/bin/env python3
"""Cluster-tier sampler (B3d + A6/A7) for dfs.datanode.max.locked.memory-rescanCachedBlockMap-remaining--autonomous.

usage: sampler.py <phase> <M_bytes> <t0_epoch> <dnpid> <vmlck_base_kB> <nnlog> <nnlog_off> <dnlog> <dnlog_off>
                  <csv> <mode: plateau|fixed90>
Every 1 s: DataNode VmLck (/proc/<pid>/status), DataNode JMX FSDatasetState (CacheUsed, CacheCapacity,
NumBlocksCached, NumBlocksFailedToCache) and DataNodeActivity CacheReportsNumOps.
Every 5 s (background thread): `hdfs cacheadmin -listDirectives -stats -path /cap/f512` (BYTES_NEEDED,
BYTES_CACHED, FILES_CACHED) and `hdfs dfsadmin -report` (Cache Used / Cache Remaining / Configured Cache Capacity).
plateau: stop when t >= 60 s and the last 10 s of (CacheUsed, NumBlocksCached, VmLck, BYTES_CACHED) are unchanged;
         at most 120 s (settled=False). fixed90: sample 90 s.
Prints one CLCHK line: final and max readings, NN "cannot fit" DEBUG lines (line 534) since the offset, and the
DataNode's DNA_CACHE lines since the offset, split at the first cache report after t0.
Revised 2026-11-25 (pc72 retry, before any run; amendments A11, A12): also counts the DataNode's
"could not reserve more bytes" lines (reserve refusals) and the NameNode's CRM "Scanned" DEBUG lines
(known-answer check that the DEBUG level is in effect).
"""
import calendar, csv, datetime, json, re, subprocess, sys, threading, time, urllib.request

(phase, M, t0, dnpid, base, nnlog, nnoff, dnlog, dnoff, out, mode) = sys.argv[1:12]
M = int(M); t0 = float(t0); base = int(base); nnoff = int(nnoff); dnoff = int(dnoff)
DROP = re.compile(r"^(\S+ \S+) .*Block (\d+): removing from PENDING_CACHED for node \S+ because it cannot fit "
                  r"in remaining cache size (-?\d+)", re.M)
CACHE = re.compile(r"^(\S+ \S+) .*DatanodeCommand action: DNA_CACHE for \S+ of \[([^\]]*)\]", re.M)


def ts_naive_utc(s):
    d = datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S,%f")
    return calendar.timegm(d.timetuple()) + d.microsecond / 1e6


# 2026-11-25 (pc72, before any run): the daemons' JVM takes its zone from /etc/timezone (Etc/UTC) while
# /etc/localtime (python, date) is MST, so log timestamps are not in the sampler's local zone. Detect the
# offset from the newest NameNode log line (CRM DEBUG lines are written every second), rounded to 15 min.
def _detect_offset(path):
    with open(path, "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 65536))
        txt = f.read().decode("utf-8", "replace")
    stamps = re.findall(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}) ", txt, re.M)
    if not stamps:
        return None
    return round((time.time() - ts_naive_utc(stamps[-1])) / 900.0) * 900.0


LOG_OFFSET = _detect_offset(nnlog)


def ts(s):
    return ts_naive_utc(s) + (LOG_OFFSET or 0.0)


def vmlck():
    with open(f"/proc/{dnpid}/status") as f:
        for line in f:
            if line.startswith("VmLck:"):
                return int(line.split()[1])
    return -1


def jmx(q):
    u = "http://localhost:9864/jmx?qry=" + q
    return json.load(urllib.request.urlopen(u, timeout=10))["beans"][0]


cli = {"BYTES_NEEDED": None, "BYTES_CACHED": None, "FILES_CACHED": None, "nnCacheUsed": None,
       "nnCacheRemaining": None, "nnCacheCapacity": None, "cli_t": None}
stop = threading.Event()


def cli_loop():
    while not stop.is_set():
        s = time.time()
        try:
            r = subprocess.run(["hdfs", "cacheadmin", "-listDirectives", "-stats", "-path", "/cap/f512"],
                               capture_output=True, text=True, timeout=60)
            hdr = None
            vals = {}
            for l in r.stdout.splitlines():
                f = l.split()
                if f and f[0] == "ID":
                    hdr = f
                elif hdr and f and f[0].isdigit():
                    vals = dict(zip(hdr, f))
            r2 = subprocess.run(["hdfs", "dfsadmin", "-report"], capture_output=True, text=True, timeout=60)
            rep = {}
            for l in r2.stdout.splitlines():
                m = re.match(r"(Configured Cache Capacity|Cache Used|Cache Remaining): (\d+)", l)
                if m and m.group(1) not in rep:
                    rep[m.group(1)] = int(m.group(2))
            cli.update({"BYTES_NEEDED": vals.get("BYTES_NEEDED", 0) if vals else 0,
                        "BYTES_CACHED": vals.get("BYTES_CACHED", 0) if vals else 0,
                        "FILES_CACHED": vals.get("FILES_CACHED", 0) if vals else 0,
                        "nnCacheUsed": rep.get("Cache Used"), "nnCacheRemaining": rep.get("Cache Remaining"),
                        "nnCacheCapacity": rep.get("Configured Cache Capacity"), "cli_t": round(time.time() - t0, 1)})
        except Exception as e:  # keep sampling; the row shows stale CLI values
            print("cli error:", e, file=sys.stderr)
        stop.wait(max(0.0, 5.0 - (time.time() - s)))


th = threading.Thread(target=cli_loop, daemon=True)
th.start()
rows = []
w = open(out, "w", newline="")
cw = csv.writer(w)
hdr = ["phase", "t_s", "VmLck_kB", "VmLck_delta_kB", "CacheUsed", "CacheCapacity", "NumBlocksCached",
       "NumBlocksFailedToCache", "CacheReportsNumOps", "BYTES_NEEDED", "BYTES_CACHED", "FILES_CACHED",
       "nnCacheCapacity", "nnCacheUsed", "nnCacheRemaining", "cli_t"]
cw.writerow(hdr)
settled = False
while True:
    s = time.time()
    v = vmlck()
    b = jmx("Hadoop:service=DataNode,name=FSDatasetState*")
    a = jmx("Hadoop:service=DataNode,name=DataNodeActivity*")
    el = s - t0
    row = [phase, round(el, 1), v, v - base, b["CacheUsed"], b["CacheCapacity"], b["NumBlocksCached"],
           b["NumBlocksFailedToCache"], a.get("CacheReportsNumOps"), cli["BYTES_NEEDED"], cli["BYTES_CACHED"],
           cli["FILES_CACHED"], cli["nnCacheCapacity"], cli["nnCacheUsed"], cli["nnCacheRemaining"], cli["cli_t"]]
    rows.append(row); cw.writerow(row); w.flush()
    if mode == "plateau":
        key = lambda r: (r[4], r[6], r[2], r[10])
        if el >= 60 and len(rows) >= 11 and len({key(r) for r in rows[-11:]}) == 1:
            settled = True
            break
        if el >= 120:
            break
    else:
        if el >= 90:
            settled = True
            break
    time.sleep(max(0.0, 1.0 - (time.time() - s)))
stop.set()
th.join(timeout=30)
w.close()


def tail(path, off):
    with open(path, "rb") as f:
        f.seek(off)
        return f.read().decode("utf-8", "replace")


nn = tail(nnlog, nnoff)
dn = tail(dnlog, dnoff)
reserve_fail = len(re.findall(r"could not reserve more bytes in the cache", dn))
scan_lines = len(re.findall(r"Scanned \d+ directive\(s\) and \d+ block\(s\)", nn))
drops = [(ts(m.group(1)), m.group(2), int(m.group(3))) for m in DROP.finditer(nn)]
cmds = [(ts(m.group(1)), [x.strip() for x in m.group(2).split(",") if x.strip()]) for m in CACHE.finditer(dn)]
# first cache report after t0: first sample whose CacheReportsNumOps exceeds the value of the first sample
cr0 = rows[0][8]
crt = next((r[1] for r in rows if r[8] is not None and cr0 is not None and r[8] > cr0), None)
crabs = t0 + crt if crt is not None else None
inwin = [c for c in cmds if crabs is None or c[0] <= crabs]
ids_all = sorted({i for _, l in cmds for i in l})
ids_win = sorted({i for _, l in inwin for i in l})
last = rows[-1]
fd = [round(d[0] - t0, 1) for d in drops]
print(f"CLCHK,{phase},M={M},mode={mode},settled={settled},t={last[1]},samples={len(rows)},"
      f"VmLck_kB={last[2]},VmLckDelta_kB={last[3]},CacheUsed={last[4]},CacheCapacity={last[5]},"
      f"NumBlocksCached={last[6]},NumBlocksFailedToCache={last[7]},CacheReportsNumOps={last[8]},"
      f"BYTES_NEEDED={last[9]},BYTES_CACHED={last[10]},FILES_CACHED={last[11]},"
      f"nnCacheCapacity={last[12]},nnCacheUsed={last[13]},nnCacheRemaining={last[14]},"
      f"maxCacheUsed={max(r[4] for r in rows)},maxVmLckDelta_kB={max(r[3] for r in rows)},"
      f"maxBlocks={max(r[6] for r in rows)},"
      f"firstCacheReport_t={crt},dropLines={len(drops)},dropIds={len({d[1] for d in drops})},"
      f"dropFirst_t={fd[0] if fd else '-'},dropLast_t={fd[-1] if fd else '-'},"
      f"dnaCacheLines={len(cmds)},dnaCacheIds={len(ids_all)},dnaCacheLinesBeforeCR={len(inwin)},"
      f"dnaCacheIdsBeforeCR={len(ids_win)},dnCouldNotReserveLines={reserve_fail},nnScanLines={scan_lines},"
      f"logOffset_s={LOG_OFFSET},"
      f"dnaCache_t={';'.join(str(round(c[0] - t0, 1)) for c in cmds[:20]) or '-'}")
