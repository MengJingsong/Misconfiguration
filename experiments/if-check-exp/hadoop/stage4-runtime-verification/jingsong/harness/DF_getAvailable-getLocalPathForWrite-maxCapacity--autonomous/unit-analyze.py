"""Unit-tier readings (B2f/B2g, amended A5/A6) from the four CSVs written by TestLdaMaxCapacity.
Usage: python3 -I unit-analyze.py <run-dir>/logs/unit
Per block and run: successes, failures, dir histogram, msgN vs max(before) over the K3 set, written files.
Then baseline vs ablated (chi-square 2x2 for two-dir blocks) and rep 1 vs rep 2 of each variant."""
import csv, math, os, sys
from collections import defaultdict, Counter

D = sys.argv[1]
MIB = 1024 * 1024
runs = {}
for v in ("baseline", "ablated"):
    for r in (1, 2):
        p = os.path.join(D, f"{v}-rep{r}.csv")
        runs[(v, r)] = list(csv.DictReader(open(p)))


def summarize(rows):
    blocks = defaultdict(list)
    for x in rows:
        blocks[int(x["block"])].append(x)
    out = {}
    for b, xs in sorted(blocks.items()):
        k3 = xs[0]["k3"]
        ok = sum(1 for x in xs if x["outcome"].startswith("ok"))
        wf = sum(1 for x in xs if x["outcome"] == "ok-writefail")
        fail = sum(1 for x in xs if x["outcome"] == "DiskErrorException")
        hist = Counter(int(x["dir"]) for x in xs if x["outcome"].startswith("ok"))
        dev = []
        ns = []
        for x in xs:
            if x["outcome"] != "DiskErrorException":
                continue
            n = int(x["msgN"]) if x["msgN"] else None
            ns.append(n)
            mx = max(int(x["a0Before"]), int(x["a1Before"])) if k3 == "dir0+dir1" else int(x["a0Before"])
            dev.append(None if n is None else n - mx)
        writes = [(int(x["written"]), int(x["fileSize"]), int(x["size"])) for x in xs if int(x["written"]) > 0]
        out[b] = dict(label=xs[0]["label"], k3=k3, size=int(xs[0]["size"]), n=len(xs), ok=ok, fail=fail,
                      writefail=wf, hist=dict(hist), ns=ns, dev=dev, writes=writes)
    return out


S = {k: summarize(v) for k, v in runs.items()}


def chi2_p(a, b):
    # 2x2 contingency: rows = variant, cols = dir0/dir1
    t = [[a.get(0, 0), a.get(1, 0)], [b.get(0, 0), b.get(1, 0)]]
    n = sum(map(sum, t))
    if n == 0:
        return 1.0
    rs = [sum(r) for r in t]
    cs = [t[0][j] + t[1][j] for j in range(2)]
    x = 0.0
    for i in range(2):
        for j in range(2):
            e = rs[i] * cs[j] / n
            if e > 0:
                x += (t[i][j] - e) ** 2 / e
    return math.erfc(math.sqrt(x / 2))  # df = 1


print("== per run and block")
for k in sorted(S):
    for b, s in S[k].items():
        nset = sorted(set(s["ns"]))
        devs = [d for d in s["dev"] if d is not None]
        wr = s["writes"]
        wtxt = ""
        if wr:
            eq = all(w == f for w, f, _ in wr)
            gt = all(f > z for _, f, z in wr)
            wtxt = f" writes={len(wr)} fileSize==written:{eq} fileSize>size:{gt} first=({wr[0][1]}B for size {wr[0][2]})"
        ntxt = ""
        if s["fail"]:
            ntxt = (f" msgN distinct={len(nset)} min={min(n for n in nset if n is not None) if any(n is not None for n in nset) else None}"
                    f" maxAbsDev(N-maxBefore)={max(abs(d) for d in devs) if devs else None}B")
        print(f"{k[0]:8s} rep{k[1]} b{b:2d} {s['k3']:9s} {s['label']:9s} size={s['size']:>20d} ok={s['ok']:3d} "
              f"fail={s['fail']:3d} writefail={s['writefail']} hist={s['hist']}{ntxt}{wtxt}")

print("== baseline vs ablated (rep r vs rep r)")
allsame = True
for r in (1, 2):
    for b in S[("baseline", r)]:
        x, y = S[("baseline", r)][b], S[("ablated", r)][b]
        same = (x["ok"], x["fail"]) == (y["ok"], y["fail"])
        p = chi2_p(x["hist"], y["hist"]) if x["k3"] == "dir0+dir1" and x["ok"] else (1.0 if x["hist"] == y["hist"] else 0.0)
        allsame &= same and p > 0.01
        print(f"rep{r} b{b:2d} {x['k3']:9s} {x['label']:9s} okfail {x['ok']}/{x['fail']} vs {y['ok']}/{y['fail']} same={same} "
              f"hist {x['hist']} vs {y['hist']} p={p:.3g}")
print("== rep1 vs rep2 per variant")
repsame = True
for v in ("baseline", "ablated"):
    for b in S[(v, 1)]:
        x, y = S[(v, 1)][b], S[(v, 2)][b]
        same = (x["ok"], x["fail"]) == (y["ok"], y["fail"])
        repsame &= same
        if not same:
            print(f"{v} b{b} rep1 {x['ok']}/{x['fail']} rep2 {y['ok']}/{y['fail']}")
print(f"repeats agree in ok/fail counts: {repsame}")

print("== message number")
bN = [d for r in (1, 2) for s in S[("baseline", r)].values() for d in s["dev"]]
aN = [n for r in (1, 2) for s in S[("ablated", r)].values() for n in s["ns"]]
print(f"baseline failures={len(bN)} unparsed={sum(1 for d in bN if d is None)} max|N-maxBefore|="
      f"{max(abs(d) for d in bN if d is not None) if bN else None} B (limit {MIB})")
print(f"ablated failures={len(aN)} N values={sorted(set(aN))}")
wfail = sum(s["writefail"] for v in S.values() for s in v.values())
print(f"write failures: {wfail}")
print(f"SUMMARY outcomes+histograms equal baseline vs ablated: {allsame}; repeats agree: {repsame}; "
      f"baseline N within 1 MiB: {all(d is not None and abs(d) <= MIB for d in bN)}; ablated N all 0: {set(aN) == {0}}; "
      f"write failures: {wfail}")
