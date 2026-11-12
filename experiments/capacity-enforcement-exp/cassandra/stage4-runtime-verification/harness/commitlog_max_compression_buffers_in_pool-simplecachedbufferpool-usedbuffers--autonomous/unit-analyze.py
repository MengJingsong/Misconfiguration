#!/usr/bin/env python3
"""Unit-tier analyzer: B2f predictions as EXPECTED lines, B2g row per audit amendment M7.
usage: unit-analyze.py <unit-output-dir>   (reads TEST-*.log files with POOL / CAP lines)"""
import glob
import re
import sys

D = sys.argv[1]
MIB = 1 << 20
TOL1, TOL2 = 0.1 * MIB, 0.2 * MIB
n_pass = n_fail = 0


def expect(ok, text):
    global n_pass, n_fail
    print(f"EXPECTED {'PASS' if ok else 'FAIL'}: {text}")
    if ok:
        n_pass += 1
    else:
        n_fail += 1


def kv(line):
    return dict(re.findall(r"(\w+)=([^ \]]+)", line))


def used(pool):
    m = re.search(r"usedBuffers:(\d+)", pool)
    return int(m.group(1)) if m else None


pool_lines, cap_lines = [], []
for f in sorted(glob.glob(f"{D}/TEST-*.log")):
    for ln in open(f, errors="replace"):
        i = ln.find("POOL N=")
        if i >= 0:
            pool_lines.append(ln[i:].strip())
        i = ln.find("CAP CommitLogBufferCap")
        if i >= 0:
            cap_lines.append(ln[i:].strip())

print(f"# Test 1: {len(pool_lines)} POOL lines; Test 2 + control: {len(cap_lines)} CAP lines")

# ---------------- Test 1 ----------------
def pow2(n):
    p = 1
    while p < n:
        p *= 2
    return p

t1 = {}
for ln in pool_lines:
    d = kv(ln)
    d["pool"] = ln[ln.find("pool=[") + 6: ln.find("]", ln.find("pool=["))] if "pool=[" in ln else ""
    t1.setdefault(int(d["N"]), []).append(d)

if 1 in t1:
    first = t1[1][0]
    expect(first.get("step") == "construct" and "IllegalArgumentException" in first.get("exception", ""),
           f"Test1 N=1 throws IllegalArgumentException at construction (got step={first.get('step')} exception={first.get('exception')})")
else:
    expect(False, "Test1 N=1 line present")
for n in (2, 3, 6, 12):
    rows = t1.get(n, [])
    if not rows:
        expect(False, f"Test1 N={n} lines present"); continue
    creates = [r for r in rows if r["step"] == "create"]
    ok_at = all((r["atLimit"] == "true") == (int(r["k"]) >= n) for r in creates)
    ok_used = all(used(r["pool"]) == int(r["k"]) for r in creates) and len(creates) == 2 * n
    ok_dir = all(abs(int(r["directDelta"]) - int(r["k"]) * MIB) <= TOL1 for r in creates)
    expect(ok_at, f"Test1 N={n} atLimit false for k<N, true for k>=N")
    expect(ok_used, f"Test1 N={n} usedBuffers = k for k = 1..2N (class does not refuse); max usedBuffers {max((used(r['pool']) or 0) for r in creates)}")
    expect(ok_dir, f"Test1 N={n} direct delta = k MiB +-0.1 MiB; deltas MiB {[round(int(r['directDelta'])/MIB, 3) for r in creates]}")
    rel = [r for r in rows if r["step"] == "released2N"]
    ret = [r for r in rows if r["step"] == "retakeN"]
    if rel and ret:
        dr, dt = int(rel[0]["directDelta"]), int(ret[0]["directDelta"])
        expect(abs(dr - pow2(n) * MIB) <= TOL1, f"Test1 N={n} retained after releasing 2N = roundUpPow2(N) = {pow2(n)} MiB (got {dr / MIB:.3f} MiB; = N would be {n})")
        expect(abs(dt - dr) <= TOL1, f"Test1 N={n} re-taking N does not change the delta ({dr / MIB:.3f} -> {dt / MIB:.3f} MiB)")
    else:
        expect(False, f"Test1 N={n} released/retake lines present")

# ---------------- Test 2 ----------------
t2 = {}
for ln in cap_lines:
    parts = ln.split()
    cls, label = parts[1], parts[2]
    d = kv(ln)
    p = ln[ln.find("pool=[") + 6: ln.find("]", ln.find("pool=["))]
    t2.setdefault(cls, {})[label] = {"N": int(d["N"]), "active": int(d["active"]), "used": used(p),
                                     "direct": int(d["directUsed"]), "pool": p}

row1 = row2 = True
row4 = False
plateaus = {}
for n in (2, 3, 6):
    c = t2.get(f"CommitLogBufferCap{n}Test", {})
    for lab in ("pre-writer", "plateau1", "after-sleep", "plateau2", "final"):
        if lab in c:
            r = c[lab]
            print(f"# N={n} {lab:12s} active={r['active']} usedBuffers={r['used']} direct-pre={(r['direct'] - c['pre-writer']['direct']) / MIB if 'pre-writer' in c else float('nan'):.3f} MiB")
    have = all(l in c for l in ("pre-writer", "plateau1", "after-sleep", "plateau2"))
    if not have:
        expect(False, f"Test2 N={n} all print points present (have {sorted(c)})")
        row1 = False
        if "plateau1" not in c and "final" in c and c["final"]["active"] < n:
            row4 = True
        continue
    pre = c["pre-writer"]["direct"]
    expect(c["pre-writer"]["used"] == 2, f"Test2 N={n} two buffers exist before the writer (usedBuffers={c['pre-writer']['used']})")
    ok_cnt = all(c[l]["active"] == n and c[l]["used"] == n for l in ("plateau1", "after-sleep", "plateau2"))
    expect(ok_cnt, f"Test2 N={n} active = usedBuffers = N at plateau1/after-sleep/plateau2: "
           + ", ".join(f"{l}:{c[l]['active']}/{c[l]['used']}" for l in ("plateau1", "after-sleep", "plateau2")))
    d1 = c["plateau1"]["direct"] - pre
    ok_d1 = abs(d1 - (n - 2) * MIB) <= TOL2
    expect(ok_d1, f"Test2 N={n} direct(plateau1) - pre-writer = (N-2) MiB +-0.2 = {n - 2} MiB (got {d1 / MIB:.3f})")
    d2 = c["plateau2"]["direct"] - c["plateau1"]["direct"]
    ok_d2 = abs(d2) <= TOL2
    expect(ok_d2, f"Test2 N={n} refill after archiveAndDiscard: direct flat +-0.2 MiB (got {d2 / MIB:+.3f})")
    row1 = row1 and ok_cnt and ok_d1 and ok_d2
    over = any(c[l]["active"] > n or (c[l]["used"] or 0) > n for l in c) or \
        any(c[l]["direct"] - pre > (n - 2) * MIB + TOL2 for l in c)
    if over:
        row2 = row2 and True
    row2_hit = over
    t2[f"_over{n}"] = over
    plateaus[n] = c["plateau1"]["active"]
    if c["plateau1"]["active"] < n:
        row4 = True

row2 = any(t2.get(f"_over{n}", False) for n in (2, 3, 6))
row3 = len(plateaus) == 3 and len(set(plateaus.values())) == 1

ctl = t2.get("CommitLogBufferCapCtlTest", {})
for lab in ("pre-writer", "ctl-5s", "ctl-6s", "ctl-after-discard", "final"):
    if lab in ctl:
        r = ctl[lab]
        print(f"# control {lab:18s} active={r['active']} pool={r['pool']} direct-pre={(r['direct'] - ctl['pre-writer']['direct']) / MIB if 'pre-writer' in ctl else float('nan'):.3f} MiB")
ctl_moved = "ctl-5s" in ctl and ctl["ctl-5s"]["active"] > 3
expect(ctl_moved, f"control (N=3, no compression, mmap): active > 3 at ctl-5s (got {ctl.get('ctl-5s', {}).get('active')}), pool {ctl.get('ctl-5s', {}).get('pool')}")
if "ctl-5s" in ctl and "pre-writer" in ctl:
    dd = ctl["ctl-5s"]["direct"] - ctl["pre-writer"]["direct"]
    expect(dd < 1 * MIB, f"control: no segment-buffer direct growth (direct delta {dd / MIB:.3f} MiB < 1 MiB)")

print(f"# summary: {n_pass} PASS, {n_fail} FAIL")
if not ctl_moved:
    print("MATCHED B2g: none - control did not move -> Not confirmed")
elif row2:
    print("MATCHED B2g row 2 (claim wrong: check bypassed or racy)")
elif row3:
    print("MATCHED B2g row 3 (claim wrong: knob does not govern)")
elif row4:
    print("MATCHED B2g row 4 (limit not reached: not confirmed)")
elif row1:
    print("MATCHED B2g row 1 (claim holds at unit level)")
else:
    print("MATCHED B2g: no matching row -> Not confirmed (no matching row)")
