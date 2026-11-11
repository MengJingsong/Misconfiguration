#!/usr/bin/env python3
"""Independent self-check (protocol step 4) for
fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.
Re-parses the RAW files (unit: surefire output; cluster: sampler CSVs and client/container logs),
not readings.tsv, and checks each against the frozen B2f / B3f (+A6) predictions.
Usage: python3 -I selfcheck.py <run-dir>"""
import glob, os, re, sys

RUN = sys.argv[1]
MiB = 1048576
ok_all = True


def say(ok, msg):
    global ok_all
    ok_all &= ok
    print(("HOLDS   " if ok else "FAILS   ") + msg)


# ---------- unit tier ----------
raw = glob.glob(f"{RUN}/logs/unit/*TestBlockCacheLruCap-output.txt")[0]
lines = [l.strip() for l in open(raw, errors="replace") if l.startswith("IFCHK,")]
cap = [list(map(int, l.split(",")[2:])) for l in lines if l.startswith("IFCHK,cap,")]
say(len(cap) == 300, f"unit: 300 put rows ({len(cap)}) from {os.path.basename(raw)}")
bad = []
for mx, rep, b, cs, files, byt, els, peak, ev, add, rem in cap:
    if not (files == min(b + 1, mx) and cs == files == els and byt == files * MiB and peak == min(b + 1, mx + 1)
            and ev == max(0, b + 1 - mx) and add == b + 1):
        bad.append((mx, rep, b))
say(not bad, f"unit: every put row = B2f (files=min(b+1,max), cacheSize=files=entryListSize, bytes, peak, evictions); bad={bad[:5]}")
for mx in (1, 2, 4, 8, 1000):
    last = [r for r in cap if r[0] == mx and r[2] == 19]
    pk = max(r[7] for r in cap if r[0] == mx)
    print(f"        max={mx}: after 20 puts files={[r[4] for r in last]} bytes={[r[5] for r in last]} "
          f"evictions={[r[8] for r in last]} peak={pk}")
closes = [list(map(int, l.split(",")[2:5])) for l in lines if l.startswith("IFCHK,close,")]
say(len(closes) == 15 and all(c[2] == 0 for c in closes), f"unit: files after close all 0 ({[c[2] for c in closes]})")
lru = [l.split(",") for l in lines if l.startswith("IFCHK,lru,")]
say(len(lru) == 3 and all(r[3] == "true" and r[4] == "false" for r in lru), "unit: LRU block 0 kept, block 1 evicted (3 reps)")
byp = [l.split(",") for l in lines if l.startswith("IFCHK,bypass,")]
for rep in ("1", "2", "3"):
    s = {r[3]: r for r in byp if r[2] == rep}
    a2, a4, cl = s["after2"], s["after4"], s["close"]
    # cols after step: ms, contains0, cacheSize, files, bytes, entryListSize, peak, evicted, added, removed
    c2 = 4900 <= int(a2[4]) <= 5600 and a2[6:8] == ["3", "3"] and a2[9] == "3" and a2[11] == "0"
    c4 = a4[5] == "true" and a4[7] == "3" and a4[9] == "3" and a4[11] == "2"
    say(c2 and c4 and cl[6] == "0", f"unit bypass rep {rep}: put2 {a2[4]} ms files {a2[7]} els {a2[9]} ev {a2[11]}; "
        f"after put4 files {a4[7]} els {a4[9]} ev {a4[11]} contains0 {a4[5]}; close files {cl[6]}")
errs = len(re.findall("deletion would not be attempted", open(raw, errors="replace").read()))
say(errs == 3, f"unit: lock-timeout ERROR lines in raw output = {errs} (one per bypass rep)")

# ---------- cluster tier ----------
C = f"{RUN}/logs/cluster"


def samples(csv):
    out = []
    for l in open(csv).read().splitlines()[1:]:
        t, n, b, _ = l.split(",")
        out.append((int(t), int(n), int(b)))
    return out


def stats(text):
    m = re.findall(r"^IFCHK,stats,([^,]+),([^,]+),(-?\d+),(-?\d+),(-?\d+),(\d+)", text, re.M)
    return m[0] if m else None


res = {}
for csv in sorted(glob.glob(f"{C}/client-N*-r*.samples.csv")) + sorted(glob.glob(f"{C}/container-N*.samples.csv")):
    label = os.path.basename(csv).replace(".samples.csv", "")
    if label.startswith("client"):
        text = open(f"{C}/{label}.client.log", errors="replace").read()
    else:
        text = "".join(open(p, errors="replace").read() for p in glob.glob(f"{C}/{label}.container_*"))
    st = stats(text)
    rs = samples(csv)
    if not st or not rs:
        say(False, f"{label}: no stats line or no samples")
        continue
    ts = int(st[5])
    end = [r for r in rs if r[0] <= ts][-1]
    n = st[0]
    N = 4 if n == "unset" else int(n)
    gauge, ev = int(st[2]), int(st[3])
    P = gauge + ev
    mxf, mxb, after = max(r[1] for r in rs), max(r[2] for r in rs), rs[-1][1]
    lock = len(re.findall("deletion would not be attempted", text))
    stream = re.findall(r"^IFCHK,stream,(\S+)", text, re.M)
    res[label] = (N, mxf, end[1], gauge, ev, P, after)
    if N == 1000:
        good = P in (63, 64) and mxf >= P - 1 and end[1] == P and gauge == P and ev == 0 and after == 0
    else:
        good = mxf <= N + 1 and end[1] == N and gauge == N and P in (63, 64) and ev == P - N and after == 0
    say(good and lock == 0 and stream and stream[0].endswith("S3APrefetchingInputStream"),
        f"{label}: N={n} samples={len(rs)} maxFiles={mxf} maxBytes={mxb} endHold={end[1]} ({end[2]} B) gauge={gauge} "
        f"evictions={ev} P={P} afterExit={after} lockErr={lock} stream={stream[:1]}")
sq = f"{C}/client-seqcat.samples.csv"
if os.path.isfile(sq):
    rs = samples(sq)
    say(max(r[1] for r in rs) == 0, f"client-seqcat: max cache files {max(r[1] for r in rs)} (expect 0)")
fin = {k: v for k, v in res.items() if k.startswith("client") and v[0] != 1000}
by = {}
for k, v in fin.items():
    by.setdefault(v[0], set()).add(v[2])
say(len(by) >= 3 and all(len(s) == 1 and list(s)[0] == N for N, s in by.items()),
    f"cluster: end-of-hold files scale with N: {sorted((k, sorted(s)) for k, s in by.items())}")
print("SELFCHECK", "ALL HOLD" if ok_all else "SOME PART DOES NOT HOLD")
