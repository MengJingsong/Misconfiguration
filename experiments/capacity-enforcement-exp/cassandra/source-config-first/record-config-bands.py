#!/usr/bin/env python3
"""Config-first source, step 2 output: merge the banding agents' files into config-bands.csv.

Refuses a batch whose anchors do not all come back A, or whose rows do not match its input batch
(the same check stage 2's record-stage2-bands.py makes).

Usage (from the repository root):
    python3 .../record-config-bands.py BATCHDIR MODEL DATE
BATCHDIR holds config-batch-NN.csv (from make-band-batches.py) and config-bands-NN.csv (from the agents).
"""
import csv, glob, os, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "config-bands.csv")
ANCHORS = {"memtable_heap_space", "key_cache_size", "native_transport_max_frame_size",
           "commitlog_segment_size", "MAX_HINT_BUFFERS"}


def main():
    bdir, model, date = sys.argv[1:4]
    tiers = {r["name"]: r["tier"] for r in csv.DictReader(open(os.path.join(HERE, "config-coverage.csv")))}
    out, bad = [], []
    for inp in sorted(glob.glob(os.path.join(bdir, "config-batch-*.csv"))):
        n = inp.rsplit("-", 1)[1][:-4]
        res = os.path.join(bdir, f"config-bands-{n}.csv")
        want = [r["name"] for r in csv.DictReader(open(inp))]
        got = list(csv.DictReader(open(res)))
        names = [r["name"] for r in got]
        if sorted(names) != sorted(want):
            bad.append(f"batch {n}: rows differ (missing {set(want) - set(names)}, extra {set(names) - set(want)})")
            continue
        if any(r["band"] not in "ABCD" or len(r["band"]) != 1 for r in got):
            bad.append(f"batch {n}: a band outside A-D")
            continue
        miss = [r["name"] for r in got if r["name"] in ANCHORS and r["band"] != "A"]
        if miss:
            bad.append(f"batch {n}: anchors not A: {miss}")
            continue
        for r in got:
            if r["name"] not in ANCHORS:
                out.append(dict(kind=r["kind"], name=r["name"], tier=tiers[r["name"]], band=r["band"],
                                reason=r["reason"].strip(), model=model, date=date, batch=f"config-batch-{n}"))
    if bad:
        sys.exit("refused:\n  " + "\n  ".join(bad))
    out.sort(key=lambda r: (r["band"], r["kind"], r["name"]))
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    c = collections.Counter((r["kind"], r["band"]) for r in out)
    for k in ("yaml", "jvm"):
        print(k, {b: c[(k, b)] for b in "ABCD"})
    print("total", len(out), dict(collections.Counter(r["band"] for r in out)))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
