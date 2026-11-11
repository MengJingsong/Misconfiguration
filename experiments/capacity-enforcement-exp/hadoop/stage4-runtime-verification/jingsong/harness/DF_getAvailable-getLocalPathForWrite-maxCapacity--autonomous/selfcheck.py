"""Independent self-check (results §5) for DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous.
Re-parses the raw files, not the run scripts' summaries:
 unit:    the allocator's own log lines in each surefire output file ("Allocated file ... in <dir>",
          "Could not find any valid local directory ... is N"), per run, and the surefire XML counts;
 cluster: the full map/task syslogs under ldc/nmlogs, the client logs, and the 0.5-s sample CSVs.
Usage: python3 -I selfcheck.py <run-dir>     Prints PASS/FAIL lines and a final count."""
import csv, glob, os, re, sys
from collections import Counter

RUN = sys.argv[1]
MIB = 1024 * 1024
fails = 0


def chk(ok, msg):
    global fails
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails += 1


# ---------------- unit tier
U = f"{RUN}/logs/unit"
per = {}
for v in ("baseline", "ablated"):
    for r in (1, 2):
        d = f"{U}/{v}-rep{r}"
        xml = glob.glob(f"{d}/TEST-*TestLdaMaxCapacity*.xml")
        x = open(xml[0]).read() if xml else ""
        m = re.search(r'tests="(\d+)"[^>]*errors="(\d+)"[^>]*skipped="(\d+)"[^>]*failures="(\d+)"', x) or \
            re.search(r'tests="(\d+)".*?failures="(\d+)"', x)
        chk(bool(xml) and 'failures="0"' in x and 'errors="0"' in x, f"unit {v} rep{r}: surefire XML 0 failures 0 errors")
        out = glob.glob(f"{d}/*TestLdaMaxCapacity-output.txt")
        txt = open(out[0], errors="replace").read() if out else open(f"{d}/mvn-test.log", errors="replace").read()
        alloc = Counter()
        for mm in re.finditer(r"Allocated file \S+ in (\S+)", txt):
            alloc["dir1" if "/ldA1/" in mm.group(1) else "dir0"] += 1
        ns = [int(mm.group(1)) for mm in re.finditer(r"ERROR .*Could not find any valid local directory for \S+ with requested size \d+ .*? is (\d+)", txt)]
        avail = [int(mm.group(1).replace(",", "")) for mm in re.finditer(r"([\d,]+) bytes available under path", txt)]
        per[(v, r)] = (alloc, Counter(ns), max(avail) if avail else None)
        print(f"  unit {v} rep{r}: allocations {dict(alloc)}; failure messages {sum(Counter(ns).values())}, N values {sorted(set(ns))}")
for r in (1, 2):
    b, a = per[("baseline", r)], per[("ablated", r)]
    chk(b[0] == a[0], f"unit rep{r}: allocator log allocations per dir equal baseline vs ablated ({dict(b[0])})")
    chk(sum(b[1].values()) == sum(a[1].values()) == 800, f"unit rep{r}: 800 failures in each variant (4 blocks x 200)")
    chk(set(a[1]) == {0}, f"unit rep{r}: ablated N all 0")
    chk(all(n > 0 for n in b[1]), f"unit rep{r}: baseline N all > 0 {sorted(b[1])}")
# baseline N equals the per-dir availability the allocator itself logged (bytes available notes)
for r in (1, 2):
    txt = open(glob.glob(f"{U}/baseline-rep{r}/*TestLdaMaxCapacity-output.txt")[0], errors="replace").read()
    bad = 0
    ms = list(re.finditer(r"ERROR .*?Could not find any valid local directory .*? is (\d+)", txt))
    for k, m in enumerate(ms):
        # the allocator logs the message first, then the history of the same call (LocalDirAllocator.java:570-571)
        end = ms[k + 1].start() if k + 1 < len(ms) else len(txt)
        av = [int(x.replace(",", "")) for x in re.findall(r"([\d,]+) bytes available under path", txt[m.end():end])]
        if not av or abs(int(m.group(1)) - max(av)) > MIB:
            bad += 1
    chk(bad == 0, f"unit baseline rep{r}: each failure's N within 1 MiB of the max 'bytes available' the same call logged ({bad} bad)")
# written files from the CSV (only source for sizes)
for v in ("baseline", "ablated"):
    for r in (1, 2):
        rows = list(csv.DictReader(open(f"{U}/{v}-rep{r}.csv")))
        w = [x for x in rows if int(x["written"]) > 0]
        chk(all(int(x["fileSize"]) == int(x["written"]) > int(x["size"]) for x in w) and len(w) == 2 * 200 + 4,
            f"unit {v} rep{r}: {len(w)} written files, each as large as written and larger than size")

# ---------------- cluster tier
C = f"{RUN}/logs/cluster"
nm = f"{RUN}/ldc/nmlogs"
if os.path.isdir(C) and glob.glob(f"{C}/*-samples.csv"):
    peaks = {}
    for arm in ("baseline", "ablated"):
        for lv in ("L900", "L300", "L60"):
            tag = f"{arm}-{lv}"
            sp = f"{C}/{tag}-samples.csv"
            if not os.path.exists(sp):
                chk(False, f"cluster {tag}: no samples")
                continue
            S = list(csv.DictReader(open(sp)))
            peak = max(int(x["du_usercache"]) for x in S)
            a0 = int(S[0]["avail"])
            peaks[tag] = peak
            cl = open(f"{C}/{tag}-client.log", errors="replace").read()
            jid = re.search(r"Running job: (job_\d+_\d+)", cl)
            app = jid.group(1).replace("job_", "application_") if jid else None
            ok = "completed successfully" in cl
            maps = []
            for sl in glob.glob(f"{C}/{tag}-applog/container_*/syslog"):
                t = open(sl, errors="replace").read()
                if re.search(r"\] org\.apache\.hadoop\.mapred\.MapTask: ", t):
                    maps.append(t)
            req = [int(x.replace(",", "")) for t in maps for x in re.findall(r"Requested file size is ([\d,]+)", t)]
            msgs = [(int(m.group(2)), int(m.group(3)), m.group(1)) for t in maps for m in
                    re.finditer(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ ERROR \[[^\]]*\] org\.apache\.hadoop\.fs\.LocalDirAllocator\$AllocatorPerContext: Could not find any valid local directory for \S+ with requested size (\d+) .*? is (\d+)", t)]
            print(f"  cluster {tag}: app {app} success={ok} maps={len(maps)} free0={a0 / MIB:.1f} MiB peak du={peak / MIB:.1f} MiB "
                  f"requests(MiB)={[round(x / MIB, 1) for x in req]} failmsgs(S,N)={[(round(s / MIB, 1), n) for s, n, _ in msgs]}")
            lm = re.findall(r"Launched map tasks=(\d+)", cl)
            chk(len(maps) == 1 and lm == ["1"], f"cluster {tag}: exactly 1 map container, counter Launched map tasks={lm}")
            chk(app is not None and os.path.basename(app) in open(f"{C}/cluster-run.log").read(), f"cluster {tag}: application id in the run log")
            if lv in ("L900", "L300"):
                chk(ok and not msgs, f"cluster {tag}: job succeeded, no allocator failure")
            else:
                chk(not ok and len(msgs) >= 1, f"cluster {tag}: job failed with the allocator message")
                if msgs:
                    s, n, ts = msgs[0]
                    chk(60 * MIB < s <= 100 * MIB and s > n, f"cluster {tag}: S={s} in (60,100] MiB and S > N={n}")
                    chk(peak < s / 2, f"cluster {tag}: peak du {peak} < S/2")
                    if arm == "ablated":
                        chk(n == 0, f"cluster {tag}: ablated N = 0")
                    else:
                        prior = [int(x["avail"]) for x in S if x["time"][:19] <= ts]
                        chk(bool(prior) and abs(n - prior[-1]) <= 4 * MIB,
                            f"cluster {tag}: N={n} within 4 MiB of the last df sample before {ts} ({prior[-1] if prior else None})")
    for arm in ("baseline", "ablated"):
        a, b = peaks.get(f"{arm}-L900"), peaks.get(f"{arm}-L300")
        if a and b:
            chk(abs(a - b) <= 0.05 * a, f"cluster {arm}: L300 peak {b / MIB:.1f} within 5 % of L900 peak {a / MIB:.1f} MiB")
else:
    print("cluster: no readings yet")
print(f"selfcheck: {fails} FAIL")
