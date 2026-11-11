#!/usr/bin/env python3
"""Check of the derivation in the case file's B2f amendment "after run 1, authorised by the user" (2026-10-25).

A transcription of IndexSummaryRedistribution.adjustSamplingLevels / distributeRemainingSpace (IndexSummaryRedistribution.java:160-265,
327-356) and IndexSummaryBuilder.calculateSamplingLevel / entriesAtSamplingLevel (IndexSummaryBuilder.java:294-314) at cassandra-5.0.9,
for one table with 44-byte summary entries (32-byte keys), min/max index interval 128/2048 (levels 8..128). It runs the B2e sequence
(R0 at the startup value, C = 4, 2, 1, 0 MiB, control (b) C = 4) on synthetic SSTable sets whose rates are proportional to maxEntries times
a random factor in [1, 1+s], and reports violations of the amended relations: (iv)/control (b) own = S0 with every level 128; at R0 (2 MiB),
C = 2 and C = 1: total <= C + 4096, mean interval within 10 % of 128*S0/own, every level within 0.10*Lbar + 2 of Lbar = 128*own/S0.
Not a source of any bound; no reading is used. The last block feeds run-1-like rates (seven SSTables at 180x) as a check of the transcription.
usage: python3 -I derivation-sim.py
"""
import math
import random

MIB = 1 << 20


def entries(level, max_entries):
    return math.ceil(level * max_entries / 128)


def redistribute(ss, pool):
    order = sorted(range(len(ss)), key=lambda i: ss[i]["rate"])
    total_rate = sum(s["rate"] for s in ss)
    rem = pool
    down, up = [], []
    for i in order:
        s, r = ss[i], ss[i]["rate"]
        ideal = round(rem * (r / total_rate))
        cur = entries(s["L"], s["maxE"])
        target = max(1, round(ideal / 44.0))
        nl = min(128, max(8, int(target * s["L"]) // cur))
        ne = entries(nl, s["maxE"])
        if target >= cur * 1.5 and nl > s["L"]:
            up.append((i, nl)); rem -= 44.0 * ne
        elif target < cur * 0.75 and nl < s["L"]:
            su = math.ceil(44.0 * ne); down.append((i, nl, su)); rem -= su
        else:
            rem -= 44 * cur
        total_rate -= r
    if rem > 0:
        down.sort(key=lambda e: 44 * entries(ss[e[0]]["L"], ss[e[0]]["maxE"]) - e[2])
        keep = 0
        while rem > 0 and keep < len(down):
            e = down[keep]
            extra = 44 * entries(ss[e[0]]["L"], ss[e[0]]["maxE"]) - e[2]
            if extra <= rem:
                rem -= extra; keep += 1
            else:
                break
        down = down[keep:]
    for i, nl, _ in down:
        ss[i]["L"] = nl
    for i, nl in up:
        ss[i]["L"] = nl


def own(ss):
    return sum(44 * entries(s["L"], s["maxE"]) for s in ss)


def stats(ss, s0):
    o = own(ss)
    levels = [s["L"] for s in ss]
    mean_iv = sum(16384 / l for l in levels) / len(levels)
    lbar = 128 * o / s0
    dev = max(abs(l - lbar) - (0.10 * lbar + 2) for l in levels)
    return o, min(levels), max(levels), mean_iv, 128 * s0 / o, dev


def run(max_es, spread, seed, startup, rates=None):
    rnd = random.Random(seed)
    ss = [dict(maxE=m, L=128, rate=(rates[i] if rates else m * (1 + spread * rnd.random()))) for i, m in enumerate(max_es)]
    s0 = own(ss)
    out = []
    for tag, c in [("R0", startup), ("C4", 4), ("C2", 2), ("C1", 1), ("C0", 0), ("B", 4)]:
        redistribute(ss, c * MIB)
        out.append((tag,) + stats(ss, s0))
    return s0, out


def violations(s0, out, startup):
    bad = 0
    for tag, o, lmin, lmax, mi, pred, dev in out:
        if tag in ("C4", "B") and (o != s0 or lmin != 128):
            bad += 1
        if tag in ("C2", "C1") or (tag == "R0" and startup == 2):
            c = 1 if tag == "C1" else 2
            if o > c * MIB + 4096 or abs(mi - pred) > 0.1 * pred or dev > 0:
                bad += 1
    return bad


SETS = {"63 (60x1268+691,695,696)": [1268] * 60 + [691, 695, 696], "3x26042": [26042, 26042, 26041],
        "19 (15x5000,160,3x1000)": [5000] * 15 + [160] + [1000] * 3, "31x2500": [2500] * 31}
for name, max_es in SETS.items():
    for spread in (0.0, 0.02, 0.05, 0.10):
        v = sum(violations(*run(max_es, spread, seed, st), st) for seed in range(20) for st in (50, 2))
        print(f"set {name:28s} s={spread:.2f}: violations {v}")
for spread in (0.15, 0.20, 0.30):
    v = sum(violations(*run(SETS["63 (60x1268+691,695,696)"], spread, seed, st), st) for seed in range(50) for st in (50, 2))
    print(f"set 63, s={spread:.2f}, 100 runs: violations {v}")
m63 = SETS["63 (60x1268+691,695,696)"]
s0, out = run(m63, 0, 0, 50, rates=[m * (180 if i < 7 else 1) for i, m in enumerate(m63)])
print("run-1-like rates (7 SSTables at 180x), startup 50:")
for tag, o, lmin, lmax, mi, pred, dev in out:
    print(f"  {tag}: own={o} levels {lmin}-{lmax} mean interval {mi:.1f} (128*S0/own {pred:.1f})")
