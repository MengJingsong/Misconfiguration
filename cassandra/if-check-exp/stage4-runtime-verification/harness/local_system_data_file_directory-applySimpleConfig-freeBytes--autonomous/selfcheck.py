#!/usr/bin/env python3
"""Independent self-check for local_system_data_file_directory-applySimpleConfig-freeBytes--autonomous run 1.
Re-parses the raw files (unit test stdout, DEBUG test logs, cap.csv, node system.log, samples.csv, stress outputs, yaml-effective)
without using the *.stage4 files or the run scripts' summaries. Prints EXPECTED lines against B2f/B2g/B3f/B3g (as amended 2026-10-26).
Usage: selfcheck.py <run-label>   (reads ~/s4-b8-ls-logs/unit-<label> and cluster-<label>)"""
import sys, os, re, glob, gzip, csv
lab = sys.argv[1]
base = os.path.expanduser("~/s4-b8-ls-logs")
U = f"{base}/unit-{lab}"; C = f"{base}/cluster-{lab}"
ok_all = True
def exp(ok, msg):
    global ok_all
    ok_all &= bool(ok)
    print(("EXPECTED OK: " if ok else "EXPECTED FAIL: ") + msg)
def rd(p):
    return (gzip.open(p, "rt", errors="ignore") if p.endswith(".gz") else open(p, errors="ignore")).read()

# ---- unit: raw stdout of each case JVM
cases = {"s05": 536870912, "s10": 1073741824, "s10m": 1073737728, "s15": 1610612736, "unset": None}
want_warn = {"s05": 1, "s10": 0, "s10m": 1, "s15": 0, "unset": 0}
for c, size in cases.items():
    t = rd(f"{U}/{c}.out")
    # a WARN log line: level WARN then the message (independent of the STAGE4 prints)
    warns = [l for l in t.splitlines() if "free in the system data volume" in l and "STAGE4" not in l and re.search(r"\bWARN\b", l)]
    m = re.search(r"unallocated_bytes=(-?\d+)", t)
    exp(len(warns) == want_warn[c], f"[unit {c}] raw WARN lines for the system data volume = {len(warns)} (want {want_warn[c]})")
    exp(re.search(r"^OK \(1 test\)", t, re.M) and "init_returned=true error=none" in t, f"[unit {c}] JVM ran 1 test OK and initialization returned without exception")
    if size is not None:
        exp(m and int(m.group(1)) == size, f"[unit {c}] unallocated_bytes {m.group(1) if m else None} == {size}")
        # compare with the df value the script logged for the mount
    if want_warn[c] == 1:
        v = {"s05": "Only 512.000MiB", "s10m": "Only 1023.996MiB"}[c]
        exp(any(v in w for w in warns), f"[unit {c}] WARN text contains '{v}'")
    # no other kind of ERROR from the init
    exp(not re.search(r"ConfigurationException|Exception in thread", t), f"[unit {c}] no ConfigurationException / uncaught exception in stdout")
    if size is not None and c != "s10m":
        a = re.search(r"probe request=314572800 result=(\w+)", t); b = re.search(r"probe request=\d+ result=threw_(\w+)", t)
        exp(a and a.group(1) == "returned_directory", f"[unit {c}] 300 MiB request admitted: {a.group(1) if a else None}")
        exp(b and b.group(1) == "FSDiskFullWriteError", f"[unit {c}] twice-available request refused: {b.group(1) if b else None}")
cfg = [open(f"{U}/{c}.config.txt").read() for c in ("s05", "s10", "s15", "unset")]
exp(len(set(cfg)) == 1, "[unit] Config dumps identical across 0.5 GiB, 1 GiB, 1.5 GiB, unset (%d fields)" % len(cfg[0].splitlines()))
# commit-log control from cap.csv
def peak(a):
    rows = list(csv.DictReader(open(f"{U}/cl{a}/cap.csv")))
    return max(int(r["onDiskSize"]) for r in rows), max(int(r["dirBytes"]) for r in rows), len(rows)
def dirty(a):
    n = 0
    for p in glob.glob(f"{U}/cl{a}/testlogs/**/*", recursive=True):
        if os.path.isfile(p): n += rd(p).count("Enqueuing flush of CLCapKS.t, Reason: COMMITLOG_DIRTY")
    return n
(pc, dc, nc), (pu, du, nu) = peak("32"), peak("100000")
mib = 1 << 20
print(f"unit control: capped peak onDisk {pc/mib:.1f} MiB dir {dc/mib:.1f} MiB rows {nc}; uncapped peak {pu/mib:.1f} MiB dir {du/mib:.1f} MiB rows {nu}; dirty flushes capped {dirty('32')} uncapped {dirty('100000')}")
exp(pc <= 52*mib and dc <= 52*mib, "[unit control] capped 32 MiB: peak (counter and directory bytes) <= 52 MiB")
exp(pu > 300*mib and du > 300*mib, "[unit control] uncapped: peak > 300 MiB (counter and directory bytes)")
exp(dirty('32') > 0 and dirty('100000') == 0, "[unit control] COMMITLOG_DIRTY flushes only in the capped arm")
exp(len(glob.glob(f"{U}/cl32/TEST-*.xml")) == 1 and 'failures="0"' in rd(glob.glob(f"{U}/cl32/TEST-*.xml")[0]), "[unit control] JUnit XML 0 failures")

# ---- cluster
def sysog(a): return rd(f"{C}/{a}/logs/system.log")
def samples(a):
    return [dict(r) for r in csv.DictReader(open(f"{C}/{a}/samples.csv"))]
def stress_ok(a):
    out = []
    for p in sorted(glob.glob(f"{C}/{a}/stress-*.out")):
        t = rd(p); m = re.search(r"^Total errors\s*:\s*(\d+)", t, re.M); n = re.search(r"^Total partitions\s*:\s*([\d,]+)", t, re.M)
        out.append((os.path.basename(p), int(m.group(1)) if m else None, n.group(1) if n else None))
    return out
for a, size, nwarn in (("A", 536870912, 1), ("B", 1610612736, 0), ("C", 1610612736, 0), ("D", None, 0)):
    s = sysog(a)
    w = [l for l in s.splitlines() if "free in the system data volume" in l]
    exp(len(w) == nwarn, f"[cluster {a}] whole system.log: {len(w)} 'free in the system data volume' lines (want {nwarn})")
    if nwarn: exp("Only 512.000MiB" in w[0] and "DatabaseDescriptor.java:742" in w[0], f"[cluster {a}] WARN text and source line 742: {w[0][w[0].find('Database'):][:90]}")
    y = open(f"{C}/{a}/yaml-effective.txt").read()
    has = re.search(r"^local_system_data_file_directory: ", y, re.M) is not None
    exp(has == (a != "D"), f"[cluster {a}] yaml sysdata directory set = {has}")
    first = s.find("free in the system data volume"); up = s.find("Starting listening for CQL clients")
    exp(nwarn == 0 or (0 <= first < up), f"[cluster {a}] the WARN precedes 'Starting listening for CQL clients' (startup only)")
    sm = samples(a)
    exp(all(r["node_alive"] == "1" for r in sm), f"[cluster {a}] node alive in all {len(sm)} samples")
    st = stress_ok(a)
    exp(len(st) == 2 and all(e == 0 for _, e, _ in st) and all(n == "200,000" for _, _, n in st), f"[cluster {a}] both stress phases: {st}")
    exp(not re.search(r"^ERROR|FSWriteError|No space left|FSDiskFull", s, re.M), f"[cluster {a}] no ERROR / FSWriteError / ENOSPC in the whole system.log")
    ch = open(f"{C}/{a}/churn/churn.log").read().splitlines()
    ps = [l for l in ch if "pass=" in l]
    exp(len(ps) >= 1 and all("create_rc=0 drop_rc=0" in l for l in ps), f"[cluster {a}] schema churn: {len(ps)} passes, all rc=0")
    sa = [int(r["sys_avail"]) for r in sm if r["sys_avail"]]
    sd = [int(r["sys_dir_bytes"]) for r in sm if r["sys_dir_bytes"]]
    print(f"cluster {a}: sys_avail min {min(sa)} max {max(sa)} ; sysdata dir bytes max {max(sd)} (MiB {max(sd)/mib:.2f})")
    if a == "C":
        ms = re.search(r"SHRINK at \S+ epoch_ms=(\d+)", rd(f"{C}/C/summary.txt")); t0 = int(ms.group(1))
        after = [int(r["sys_avail"]) for r in sm if int(r["epoch_ms"]) > t0 + 6000]
        exp(len(after) >= 3 and max(after) < 110*mib and min(after) > 90*mib, f"[cluster C] after the shrink the volume stays at ~100 MiB: {min(after)}..{max(after)} over {len(after)} samples")
        mx = max(int(r["sys_dir_bytes"]) for r in sm if int(r["epoch_ms"]) > t0 and r["sys_dir_bytes"])
        print(f"cluster C: sysdata dir bytes after shrink max {mx}")
        wl = [l for l in s.splitlines() if "free in the system data volume" in l]
        exp(len(wl) == 0, "[cluster C] no new WARN after the shrink (whole log has none)")
    if a == "D":
        exp(min(sa) == max(sa) == 536870912, "[cluster D] unused 0.5 GiB volume untouched")
# commit-log control
pk = {}
for a in ("P", "U"):
    s = sysog(a); sm = samples(a)
    pk[a] = max(int(r["commitlog_bytes"]) for r in sm)
    exp(all(r["node_alive"] == "1" for r in sm), f"[cluster {a}] node alive in all {len(sm)} samples")
    st = stress_ok(a); exp(len(st) == 1 and st[0][1] == 0 and st[0][2] == "1,000,000", f"[cluster {a}] stress {st}")
    cfgv = re.search(r"commitlog_total_space=(\S+?)[,;]", s); print(f"cluster {a}: commitlog_total_space in log {cfgv.group(1) if cfgv else None}; peak commitlog bytes {pk[a]} ({pk[a]/mib:.0f} MiB)")
    if a == "P": 
        fl = [l for l in s.splitlines() if "Enqueuing flush of" in l and "COMMITLOG_DIRTY" in l]
        print(f"cluster P: COMMITLOG_DIRTY flush lines {len(fl)}"); exp(len(fl) > 0, "[cluster P] COMMITLOG_DIRTY flushes occurred")
    else:
        fl = [l for l in s.splitlines() if "Enqueuing flush of" in l and "COMMITLOG_DIRTY" in l]
        exp(len(fl) == 0, f"[cluster U] no COMMITLOG_DIRTY flushes ({len(fl)})")
exp(pk["P"] <= 192*mib, f"[cluster control] capped peak {pk['P']/mib:.0f} MiB <= 192 MiB")
exp(pk["U"] >= 400*mib, f"[cluster control] uncapped peak {pk['U']/mib:.0f} MiB >= 400 MiB (control moved)")
exp(pk["P"] < 0.5*pk["U"], "[cluster control] capped peak < 0.5 x uncapped peak")
# leftovers
import subprocess
pl = subprocess.run(["ps", "-eo", "pid,comm,args"], capture_output=True, text=True).stdout.splitlines()
ps = str(sum(1 for l in pl if len(l.split(None, 2)) == 3 and l.split(None, 2)[1] == "java" and "CassandraDaemon" in l and "s4-b8-ls-n" in l))
mt = subprocess.run("mount | grep -c s4-b8-ls", shell=True, capture_output=True, text=True).stdout.strip()
exp(ps == "0" and mt == "0", f"[leftovers] my daemons {ps}, my mounts {mt}")
print("SELFCHECK", "ALL OK" if ok_all else "HAS FAILURES")
sys.exit(0 if ok_all else 1)
