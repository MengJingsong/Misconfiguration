#!/usr/bin/env python3
# Summarise the cluster-tier arms (B3d observables) against B3f.
# Usage: python3 -I analyze.py <cluster-out-dir>   (contains arm-<name>/)
import os, re, sys

UPD = re.compile(r"Update nonSequentialWriteInMemory by (-?\d+) new value: (\d+)")
REQ = re.compile(r"requested offset=(\d+) and current offset=(\d+)")
BEFORE = re.compile(r"Start dump\. Before dump, nonSequentialWriteInMemory == (\d+)")
AFTER = re.compile(r"After dump, nonSequentialWriteInMemory == (\d+)")
TOTAL = 4095 * 65536
MARK = {"m1": 1 << 20, "m8": 8 << 20, "m64": 64 << 20, "inf": None, "seq": 1 << 20}


def read(p):
    try:
        with open(p, errors="replace") as f:
            return f.read()
    except OSError:
        return ""


base = sys.argv[1]
for arm in ["m1", "m8", "m64", "inf", "seq"]:
    d = os.path.join(base, "arm-" + arm)
    if not os.path.isdir(d):
        continue
    log = read(os.path.join(d, "nfs3.log"))
    hold = read(os.path.join(d, "nfs3-at-hold.log"))
    ups = [(int(a), int(b)) for a, b in UPD.findall(log)]
    inc = [by for by, v in ups if by > 0]
    dec = [by for by, v in ups if by < 0]
    hv = [int(b) for a, b in UPD.findall(hold)]
    reqs = [(int(a), int(b)) for a, b in REQ.findall(log)]
    offs = [a for a, b in reqs]
    asc = all(offs[i] < offs[i + 1] for i in range(len(offs) - 1))
    befores = [int(x) for x in BEFORE.findall(log)]
    afters = [int(x) for x in AFTER.findall(log)]
    hs = read(os.path.join(d, "histo-summary.txt"))
    bb = [int(x) for x in re.findall(r"\[B_bytes=(\d+)", hs)]
    wc = re.findall(r"WriteCtx=(\d+)", hs)
    dh = read(os.path.join(d, "dump-hold.txt"))
    m = re.search(r"\n-\S+\s+\d+\s+\S+\s+\S+\s+(\d+)\s", dh)
    dump_hold = int(m.group(1)) if m else 0
    samples = [l.split(",") for l in read(os.path.join(d, "samples.csv")).splitlines() if l.count(",") == 3]
    rss = [int(s[3]) for s in samples if s[3].isdigit()]
    dsz = [int(s[1]) for s in samples if s[1].isdigit()]
    M = MARK[arm]
    if arm == "seq":
        pred_mem, pred_dump = 0, 0
    elif M is None:
        pred_mem, pred_dump = TOTAL, 0
    else:
        q = M // 65536
        pred_mem, pred_dump = (4095 % q) * 65536, (4095 - 4095 % q) * 65536
    print("ARM", arm, "mark", M)
    print("  jar constant           :", read(os.path.join(d, "jar-const.txt")).strip())
    print("  WRITE requests (log)   : %d, offsets ascending=%s, first=%s last=%s" % (
        len(offs), asc, offs[:2], offs[-1:]))
    print("  increments             : %d, sizes=%s" % (len(inc), sorted(set(inc))))
    print("  log peak counter       :", max([v for by, v in ups] or [0]))
    print("  counter at hold (log)  :", hv[-1] if hv else "-", " predicted in-memory:", pred_mem)
    print("  dump rounds            : %d, 'before dump' values=%s, 'after dump' values=%s" % (
        len(befores), sorted(set(befores)), sorted(set(afters))))
    print("  dump file at hold      : %d (predicted %d), mod M = %s" % (
        dump_hold, pred_dump, (dump_hold % M) if M else "-"))
    print("  in memory = TOTAL-dump :", TOTAL - dump_hold if arm != "seq" else "-")
    print("  [B base/hold/delta     :", bb[0] if bb else "-", bb[1] if len(bb) > 1 else "-",
          (bb[1] - bb[0]) if len(bb) > 1 else "-")
    print("  WriteCtx base/hold     :", wc)
    print("  'Create dump file'     :", log.count("Create dump file"))
    print("  stable->unstable lines :", log.count("Have to change stable write to unstable write"))
    print("  OOM in log             :", log.count("OutOfMemoryError"))
    print("  samples                : n=%d, dump max=%s, RSS kB min/max=%s/%s" % (
        len(samples), max(dsz) if dsz else "-", min(rss) if rss else "-", max(rss) if rss else "-"))
    print("  md5                    :", " ".join(read(os.path.join(d, "md5.txt")).split()))
