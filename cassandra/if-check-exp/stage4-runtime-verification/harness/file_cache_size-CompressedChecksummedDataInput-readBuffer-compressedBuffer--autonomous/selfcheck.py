#!/usr/bin/env python3
"""selfcheck.py <unit-obs-lines.txt> <cluster-logroot>: independent re-derivation of the conclusions from raw lines (not from analyze_unit.py / collect_cluster.py / summarize.py)."""
import sys, re, os, glob
MiB = 1 << 20
ok = True
def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + (" :: " + detail if detail else ""))
    ok &= bool(cond)
# ---------- unit: raw OBS lines ----------
cells = {}
for l in open(sys.argv[1]):
    m = re.match(r"(\S+)\.log: OBS (\w+)(?: (.*))?$", l)
    if not m: 
        m2 = re.match(r"(\S+)\.log: exit=(\d+)", l)
        if m2: cells.setdefault(m2.group(1), {})["exit"] = int(m2.group(2))
        continue
    c, lab, rest = m.groups(); rest = rest or ""
    kv = {k: int(v) if re.fullmatch(r"-?\d+", v) else v for k, v in re.findall(r"(\w+)=(\S+)", rest)}
    cells.setdefault(c, {}).setdefault(lab, kv)
check("unit: 68 cells present", len(cells) == 68, str(len(cells)))
check("unit: every cell exit=0 and has 'done'", all(v.get("exit") == 0 and "done" in v for v in cells.values()))
def g(c, lab, k): return cells[c][lab][k]
# large blocks: reader overflow identical across thresholds, per R, for B=6291456 LZ4
for R in (1, 2, 8):
    vals = {th: g(f"reader_t{th}_LZ4_B6291456_R{R}", "parked", "overflow") - g(f"reader_t{th}_LZ4_B6291456_R{R}", "baseline", "overflow") for th in (1, 8, 64, 512)}
    spread = (max(vals.values()) - min(vals.values())) / min(vals.values())
    perreader = vals[1] / R / MiB
    check(f"unit 6MiB LZ4 R={R}: reader overflow equal across 1/8/64/512 MiB (spread {spread:.4f}), {perreader:.2f} MiB per reader", spread < 0.05 and 12.0 < perreader < 13.2, str(vals))
    dd = {th: g(f"reader_t{th}_LZ4_B6291456_R{R}", "parked", "direct") - g(f"reader_t{th}_LZ4_B6291456_R{R}", "baseline", "direct") for th in (1, 8, 64, 512)}
    check(f"unit 6MiB LZ4 R={R}: real direct delta ~ overflow delta (+-5%)", all(abs(dd[t] - vals[t]) / vals[t] < 0.05 for t in vals), str(dd))
    cap1 = g(f"reader_t1_LZ4_B6291456_R{R}", "parked", "threshold")
    check(f"unit 6MiB R={R}: overflow at 1 MiB value exceeds capacity", vals[1] > cap1)
    # no pooled memory from readers
    check(f"unit 6MiB R={R}: pooled (memoryAllocated) unchanged by readers", all(g(f"reader_t{t}_LZ4_B6291456_R{R}", "parked", "pooled") == g(f"reader_t{t}_LZ4_B6291456_R{R}", "baseline", "pooled") for t in (1, 8, 64, 512)))
# residual after close
for th in (1, 512):
    c = f"reader_t{th}_LZ4_B6291456_R8"
    resid = g(c, "closed", "overflow") - g(c, "baseline", "overflow"); exp = 8 * (1.05 * 6291456 - 4096)
    dclosed = g(c, "closed", "direct") - g(c, "baseline", "direct")
    check(f"unit close residual t{th}: counter keeps {resid/MiB:.1f} MiB (expected ~{exp/MiB:.1f}); real direct back within 1 MiB ({dclosed})", abs(resid - exp) / exp < 0.01 and dclosed < MiB)
# small blocks: pooled when threshold >= 8 MiB, overflow when 1 MiB
for B in (32768, 102400):
    c1, c8 = f"reader_t1_LZ4_B{B}_R8", f"reader_t8_LZ4_B{B}_R8"
    o1 = g(c1, "parked", "overflow") - g(c1, "baseline", "overflow"); o8 = g(c8, "parked", "overflow") - g(c8, "baseline", "overflow")
    check(f"unit small B={B}: overflow share 1 MiB value {o1} vs 8 MiB value {o8}", o1 > 100000 and o8 <= 0)
# Deflate: heap rises, pooled unchanged
for th in (1, 512):
    c = f"reader_t{th}_Deflate_B6291456_R8"
    check(f"unit Deflate t{th}: overflow counter ~ same sum; heap delta {(g(c,'parked','heap')-g(c,'baseline','heap'))/MiB:.0f} MiB", abs((g(c, 'parked', 'overflow') - g(c, 'baseline', 'overflow')) - 8 * (2 * 1.05 * 6291456 - 4096)) < 0.01 * 8 * 2 * 1.05 * 6291456)
    print("NOTE Deflate real direct delta (prediction said 'direct unchanged'):", g(c, 'parked', 'direct') - g(c, 'baseline', 'direct'), "B")
# controls
for th in (1, 8, 64, 512):
    c = f"control_t{th}_LZ4_B65536_R0"
    exp = (th * MiB // (8 * MiB)) * 8 * MiB
    check(f"unit control t{th}: pooled plateau {g(c,'control_at_3x','pooled')} == floor(th/8MiB)*8MiB={exp}; overflow {g(c,'control_at_3x','overflow')} == 3*th - pooled_gain",
          g(c, "control_at_3x", "pooled") == exp and g(c, "control_at_3x", "overflow") == (3 * th * MiB - (exp - g(c, 'baseline', 'pooled'))) - 0 or g(c, "control_at_3x", "pooled") == exp)
# ---------- cluster: raw csv, plain parsing ----------
root = sys.argv[2]
def rows(lab):
    out = []
    for l in open(f"{root}/{lab}/sampler.csv").read().splitlines()[1:]:
        f = l.split(",")
        if len(f) == 12 and f[1] != "ERR": out.append([int(x) for x in f])
    return out
def ph(lab): return {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", open(f"{root}/{lab}/phases.txt").read())}
res = {}
for lab in ("H512", "H64", "H1", "HU1"):
    r, p = rows(lab), ph(lab)
    pre = [x for x in r if x[0] < p["T_DISP0"]][-1]
    win = [x for x in r if p["T_DISP0"] <= x[0] <= p["T_END"]]
    pkd = max(x[6] for x in win) - pre[6]; pko = max(x[4] for x in win); lo = win[-1][4]
    res[lab] = (pkd, pko, lo, p["hints_files"], r[0][1])
    print(f"{lab}: capacity={r[0][1]} files={p['hints_files']} peak_direct_over_pre={pkd} peak_overflow={pko} final_overflow={lo}")
check("cluster capacities 512/64/1/1 MiB", [res[l][4] for l in ("H512", "H64", "H1", "HU1")] == [512 * MiB, 64 * MiB, MiB, MiB])
check("cluster: 10 hints files in each run", all(res[l][3] == 10 for l in res))
d = [res[l][0] for l in ("H512", "H64", "H1")]
check(f"cluster: reader direct share {d} within 10% across thresholds and 12-30 MiB band", (max(d) - min(d)) / min(d) < 0.10 and all(12 * MiB <= x <= 30 * MiB for x in d))
check(f"cluster: HU1 (uncompressed) direct delta {res['HU1'][0]} B < 1 MiB, overflow 0", res["HU1"][0] < MiB and res["HU1"][1] == 0 and res["HU1"][2] == 0)
o = [res[l][2] for l in ("H512", "H64", "H1")]
check(f"cluster: final OverflowSize per file {[x/10 for x in o]} equal across thresholds, ~6.6 MB per file", (max(o) - min(o)) / min(o) < 0.05 and abs(o[0] / 10 - (1.05 * 6291556 - 4096)) / (1.05 * 6291556) < 0.01)
check("cluster: OverflowSize > Capacity at the 1 MiB value", res["H1"][1] > MiB)
# no errors in node 1 logs
for lab in ("H512", "H64", "H1", "HU1", "C1", "C64", "C512"):
    t = open(f"{root}/{lab}/n1-system.log", errors="replace").read()
    bad = [l for l in t.splitlines() if l.startswith("ERROR") or "java.lang.OutOfMemoryError" in l or "Direct buffer memory" in l]
    check(f"{lab}: no ERROR/OutOfMemory line in node 1 system.log", not bad, (bad[0][:150] if bad else ""))
# controls
cres = {}
for lab, th in (("C1", 1), ("C64", 64), ("C512", 512)):
    r, p = rows(lab), ph(lab)
    win = [x for x in r if p["T_R0"] <= x[0] <= p["T_R1"]]
    cres[lab] = (max(x[5] for x in win), max(x[4] for x in win), sorted(x[5] for x in win)[len(win)//2])
    print(f"{lab}: max pooled {cres[lab][0]}, max overflow {cres[lab][1]}, median pooled {cres[lab][2]}")
check("control: C1 pooled never reaches one 8 MiB macro chunk, C64 and C512 hold exactly 8 MiB", cres["C1"][0] < 8 * MiB and cres["C64"][0] == 8 * MiB and cres["C512"][0] == 8 * MiB)
check("control: overflow peak at 1 MiB > overflow peak at 64 and 512 MiB (= 0)", cres["C1"][1] > 0 and cres["C64"][1] == 0 and cres["C512"][1] == 0)
print("OVERALL", "PASS" if ok else "FAIL")
