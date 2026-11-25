# Stage-4 harness, order 20: cluster-tier evaluation against B3f + AM8 (run with python3 -I).
# Usage: analyze.py <dir holding K*/readings.csv, K*/count.txt>
import csv, os, sys

base = sys.argv[1]
MiB = 1048576
BMAX = 105 * 1024
N_OF = {"K1": 65536, "K2": 8388608, "K3": 67108864, "K4": 268435456, "K6ctl": 1073741824, "K6": 2147483647}

def load(k):
    rows = list(csv.DictReader(open(os.path.join(base, k, "readings.csv"))))
    return rows

for k in sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)) and d.startswith("K")):
    try:
        rows = load(k)
    except FileNotFoundError:
        continue
    bl = [r for r in rows if r["label"] == "baseline"][0]
    b0, e0 = int(bl["bytes_B"]), int(bl["treemap_entry"])
    N = N_OF.get(k)
    capline = ""
    cf = os.path.join(base, k, "jn-capacity-line.txt")
    if os.path.exists(cf):
        t = open(cf).read().strip().splitlines()
        capline = t[-1] if t else ""
        if N is None and "capacity of bytes:" in capline:
            N = int(capline.split("capacity of bytes:")[1].split()[0])
    fin = [r for r in rows if r["label"] == "final"][-1]
    bw, bat = int(fin["BytesWritten"] or 0), int(fin["BatchesWritten"] or 0)
    b = bw / bat if bat else 0
    print("== %s  N=%s  baseline[B=%d  baselineEntry=%d  BytesWritten=%d Batches=%d  b=%.0f" % (k, N, b0, e0, bw, bat, b))
    print("   capacity line: %s" % capline[-120:])
    inband_all = True
    post = 0
    for r in rows:
        if r["label"].startswith("pre"):
            continue
        d = int(r["bytes_B"]) - b0
        de = int(r["treemap_entry"]) - e0
        rbw = int(r["BytesWritten"] or 0)
        flag = ""
        if N and k not in ("K1", "K0") and rbw >= N + 2 * b:
            post += 1
            lo, hi = N - BMAX - 2 * MiB, N + 2 * MiB
            ok = lo <= d <= hi
            inband_all &= ok
            flag = "post-N %s" % ("in-band" if ok else "OUT-OF-BAND")
        print("   %-9s dB=%12d (%8.2f MiB) dEntry=%6d BytesWritten=%11d OU_KB=%s RSS_KB=%s %s" % (
            r["label"], d, d / MiB, de, rbw, r["jstat_OU_KB"], r["VmRSS_KB"], flag))
    dfin = int(fin["bytes_B"]) - b0
    defin = int(fin["treemap_entry"]) - e0
    if N and k not in ("K0",):
        print("   final dB/N = %.4f ; dEntry=%d vs N/b=%.0f (ratio %.3f) ; post-N samples=%d all-in-band=%s" % (
            dfin / N, defin, N / b if b else 0, (defin / (N / b)) if b else 0, post, inband_all))

# AM10 evaluation (attempt 3): heap-dump attribution
import re
print("\n== AM10 heap-dump attribution")
for k in sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)) and d.startswith("K")):
    hf = os.path.join(base, k, "heap-attribution.txt")
    if not os.path.exists(hf):
        continue
    t = open(hf).read()
    m = re.search(r"capacity=(-?\d+) totalSize=(-?\d+) entries=(\d+) sum\(len\)=(\d+)", t)
    if not m:
        print(k, "no cache line"); continue
    cap, ts, E, P = map(int, m.groups())
    R = sum(int(x) for x in re.findall(r"referrers [^\n]*ByteString[^\n]*: (\d+) bytes", t))
    rows = load(k)
    bl = [r for r in rows if r["label"] == "baseline"][0]; fin = [r for r in rows if r["label"] == "final"][-1]
    d = int(fin["bytes_B"]) - int(bl["bytes_B"])
    b = int(fin["BytesWritten"]) / int(fin["BatchesWritten"])
    N = cap
    pin = (N - BMAX) < P <= N
    dband = (N - BMAX - 2 * MiB) <= d <= (N + R + 2 * MiB)
    print("%-6s N=%d P=%d (P/N=%.5f) totalSize=%d (==P %s) E=%d N/b=%.0f (E ratio %.3f) R=%d dB_final=%d  P-in-band=%s dB-in-AM10-band=%s" % (
        k, N, P, P / N, ts, ts == P, E, N / b, E / (N / b), R, d, pin, dband))
