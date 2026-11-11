#!/usr/bin/env python3
"""Evaluate the frozen predictions (case file A4/A6 for 'unit', A7 for 'cluster') against IFCHK CSV lines.
Usage: analyze.py unit <ifchk-all.csv> | analyze.py cluster <probe-results.csv>
Prints one PASS/FAIL line per check and a summary; it does not choose the verdict row (that is done in the results file)."""
import sys

def unit(path):
    rows, instr, fails = [], [], []
    for line in open(path):
        p = line.rstrip("\n").split(",")
        if p[1] == "instr":
            instr.append(p)
        elif p[1] == "row":
            rows.append(dict(arm=p[2], M=int(p[3]), id=p[4], cls=p[5], kind=p[6], len=int(p[7]), outcome=p[8],
                             exc=p[9], msg=p[10], remaining=int(p[11]), content=p[12], iters=int(p[13]),
                             same=p[14] == "true", med=int(p[15]), mn=int(p[16]), mx=int(p[17]), base=int(p[18]),
                             medb=int(p[19]), maxb=int(p[20])))
    def chk(ok, what):
        print(("PASS " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)
    for p in instr:
        kv = dict(x.split("=", 1) for x in p[4:] if "=" in x)
        ka = int(kv["knownAnswer1MiB"])
        chk(kv["supported"] == "true" and kv["enabled"] == "true", f"instr {p[2]}: allocated-bytes counter supported+enabled")
        chk(1048576 <= ka <= 1048576 + 4096, f"instr {p[2]}: known answer {ka} in [1048576, 1052672]")
        chk(int(kv["maxMemory"]) <= 256 * 1024 * 1024 and "-Xmx256m" in kv["jvmArgs"], f"instr {p[2]}: maxMemory {kv['maxMemory']} <= 256 MiB, -Xmx256m")
        chk(int(kv["MAX_SIZE"]) == int(p[3]), f"instr {p[2]}: MAX_SIZE {kv['MAX_SIZE']} == M {p[3]}")
    largest = {}
    for r in rows:
        if not r["cls"].startswith("RawPathHandle"):
            continue
        tag = f"{r['arm']} {r['id']} len={r['len']} M={r['M']}"
        chk(r["same"], f"{tag}: same outcome in all {r['iters']} iterations")
        if 0 <= r["len"] <= r["M"]:
            chk(r["outcome"] == "object", f"{tag}: accepted (object)")
            chk(r["remaining"] == r["len"], f"{tag}: remaining {r['remaining']} == len")
            chk(r["content"] == "true", f"{tag}: content equal")
            chk(r["len"] <= r["medb"] <= r["len"] + 4096, f"{tag}: med-b {r['medb']} in [len, len+4096]")
            if r["outcome"] == "object":
                largest[r["arm"]] = max(largest.get(r["arm"], -1), r["len"])
        else:
            chk(r["exc"] == "java.io.IOException" and r["msg"] == f"Illegal buffer length {r['len']}",
                f"{tag}: IOException '{r['msg']}'")
            chk(r["medb"] < 65536, f"{tag}: med-b {r['medb']} < 65536")
            chk(r["maxb"] < 1048576, f"{tag}: max-b {r['maxb']} < 1048576")
            if r["outcome"] == "object":
                largest[r["arm"]] = max(largest.get(r["arm"], -1), r["len"])
    for arm, M in (("D", 1048576), ("K16", 65536), ("K24", 16777216)):
        chk(largest.get(arm) == M, f"arm {arm}: largest accepted len {largest.get(arm)} == M {M}")
    c = {r["id"]: r for r in rows if r["cls"] == "UncheckedHandle"}
    l8 = next((r for r in rows if r["arm"] == "D" and r["id"] == "L8"), None)
    if c:
        chk(c["C5"]["outcome"] == "object" and c["C5"]["medb"] >= 16777216, f"C5: object, med-b {c['C5']['medb']} >= 16777216")
        chk(c["C8"]["exc"] == "java.io.EOFException" and c["C8"]["medb"] >= 67108864, f"C8: {c['C8']['exc']}, med-b {c['C8']['medb']} >= 67108864")
        chk(c["C9"]["exc"] == "java.lang.OutOfMemoryError" and c["C9"]["msg"] == "Java heap space", f"C9: {c['C9']['exc']} '{c['C9']['msg']}'")
        chk(c["C6"]["exc"] == "java.lang.OutOfMemoryError", f"C6: {c['C6']['exc']} '{c['C6']['msg']}'")
        if l8:
            chk(l8["medb"] <= 0 or c["C8"]["medb"] >= 1000 * l8["medb"], f"C8 med-b {c['C8']['medb']} >= 1000 x L8 med-b {l8['medb']}")
    else:
        chk(False, "control rows present")
    print(f"SUMMARY rows={len(rows)} instr={len(instr)} fails={len(fails)}")
    for f in fails:
        print("  FAILED: " + f)

def cluster(path):
    fails = []
    def chk(ok, what):
        print(("PASS " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)
    R = {}
    for line in open(path):
        p = line.rstrip("\n").split(",")
        if p[0] != "PROBE":
            continue
        kv = dict(x.split("=", 1) for x in p[1:] if "=" in x)
        R[kv["id"]] = kv
    MiB = 1 << 20
    for rid, kv in sorted(R.items()):
        chk("hadoop-common-3.4.2.jar" in kv.get("codeSource", "") and "/hadoop/share/hadoop/common/" in kv.get("codeSource", ""),
            f"{rid}: code source {kv.get('codeSource')}")
        chk(int(kv["maxMemory"]) <= 128 * MiB, f"{rid}: maxMemory {kv['maxMemory']} <= 128 MiB")
    def g(i, k):
        return int(R[i][k])
    for rid, ln in (("R1", 1024), ("R3", 1048576)):
        chk(g(rid, "objects") == 1000, f"{rid}: objects {g(rid,'objects')} == 1000")
        chk(1000 * ln <= g(rid, "total") <= 1000 * (ln + 65536), f"{rid}: total {g(rid,'total')} in [{1000*ln}, {1000*(ln+65536)}]")
    for rid, ln in (("R4", 1048577), ("R5", 16777216), ("R6", 2147483647)):
        chk(g(rid, "ioexceptions") == 1000 and R[rid]["msgs"] == f"Illegal buffer length {ln}", f"{rid}: ioexceptions {g(rid,'ioexceptions')}, msgs '{R[rid]['msgs']}'")
        chk(g(rid, "total") < 67108864, f"{rid}: total {g(rid,'total')} < 67108864")
        chk(g(rid, "oom") == 0, f"{rid}: no OOM")
    chk(g("R6", "vmhwmKiB") <= g("R4", "vmhwmKiB") + 32 * 1024, f"VmHWM R6 {g('R6','vmhwmKiB')} kB <= R4 {g('R4','vmhwmKiB')} kB + 32 MiB")
    chk(g("X5", "objects") == 1000 and g("X5", "total") >= 1000 * 16777216, f"X5: objects {g('X5','objects')}, total {g('X5','total')} >= {1000*16777216}")
    for rid in ("X9", "X6"):
        chk(g(rid, "oom") >= 1 and g(rid, "oomAt") == 1, f"{rid}: OOM at iteration {R[rid].get('oomAt')} ('{R[rid].get('oomMsg')}')")
    print(f"SUMMARY rows={len(R)} fails={len(fails)}")
    for f in fails:
        print("  FAILED: " + f)

if __name__ == "__main__":
    {"unit": unit, "cluster": cluster}[sys.argv[1]](sys.argv[2])
