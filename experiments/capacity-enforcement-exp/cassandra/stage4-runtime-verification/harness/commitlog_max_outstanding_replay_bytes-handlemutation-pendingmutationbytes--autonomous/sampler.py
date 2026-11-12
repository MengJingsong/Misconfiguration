#!/usr/bin/env python3
"""B3d sampler (amendment M5). Usage: sampler.py <pid> <system.log> <out.jsonl>
Every 2 s until 'Log replay complete' is in system.log (or the process is gone): jcmd GC.class_histogram
(forces a full GC: live objects) -> instance count and bytes of org.apache.cassandra.db.Mutation and
org.apache.cassandra.db.partitions.PartitionUpdate (exact names), histogram Total; then jcmd GC.heap_info -> used."""
import json, os, re, subprocess, sys, time
pid, syslog, out = sys.argv[1], sys.argv[2], sys.argv[3]
NAMES = {"org.apache.cassandra.db.Mutation": "mut", "org.apache.cassandra.db.partitions.PartitionUpdate": "pu"}
row = re.compile(r"^\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)")
tot = re.compile(r"^Total\s+(\d+)\s+(\d+)")
used = re.compile(r"garbage-first heap\s+total (\d+)K, used (\d+)K")
def complete():
    try:
        with open(syslog, errors="replace") as f:
            return "Log replay complete" in f.read()
    except FileNotFoundError:
        return False
def alive():
    return os.path.exists(f"/proc/{pid}")
with open(out, "a") as fo:
    while True:
        if complete():
            fo.write(json.dumps({"t_ms": int(time.time() * 1000), "event": "replay_complete_seen"}) + "\n"); break
        if not alive():
            fo.write(json.dumps({"t_ms": int(time.time() * 1000), "event": "process_gone"}) + "\n"); break
        t0 = int(time.time() * 1000)
        rec = {"t_ms": t0, "mut_n": 0, "mut_b": 0, "pu_n": 0, "pu_b": 0}
        try:
            h = subprocess.run(["jcmd", pid, "GC.class_histogram"], capture_output=True, text=True, timeout=120).stdout
            ok = False
            for line in h.splitlines():
                m = row.match(line)
                if m and m.group(3) in NAMES:
                    k = NAMES[m.group(3)]; rec[k + "_n"] = int(m.group(1)); rec[k + "_b"] = int(m.group(2))
                m = tot.match(line)
                if m:
                    rec["total_n"] = int(m.group(1)); rec["total_b"] = int(m.group(2)); ok = True
            rec["t1_ms"] = int(time.time() * 1000)
            hi = subprocess.run(["jcmd", pid, "GC.heap_info"], capture_output=True, text=True, timeout=60).stdout
            m = used.search(hi)
            if m:
                rec["heap_total_k"] = int(m.group(1)); rec["heap_used_k"] = int(m.group(2))
            rec["ok"] = ok
        except Exception as ex:
            rec["error"] = repr(ex); rec["ok"] = False
        rec["complete_after"] = complete()
        fo.write(json.dumps(rec) + "\n"); fo.flush()
        time.sleep(2)
