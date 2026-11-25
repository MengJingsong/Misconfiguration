#!/usr/bin/env python3
"""B3d sampler for case o100 (S4-A4). Usage: sampler.py <pid> <system.log> <out.jsonl> <raw.txt> <nodetool cmd>
Waits for the first 'Replaying' line, then every 5 s (start to start) until 'Log replay complete' (or the process is gone):
jmap -histo:live <pid> (forces a full GC) -> count/bytes of CommitLogReplayer$MutationInitiator$1, db.Mutation,
PartitionUpdate, and the histogram Total; jcmd GC.heap_info -> used; nodetool tpstats MutationStage (run in parallel)."""
import json, os, re, subprocess, sys, time
pid, syslog, out, raw, nt = sys.argv[1:6]
NAMES = {"org.apache.cassandra.db.commitlog.CommitLogReplayer$MutationInitiator$1": "task",
         "org.apache.cassandra.db.Mutation": "mut",
         "org.apache.cassandra.db.partitions.PartitionUpdate": "pu"}
row = re.compile(r"^\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)")
tot = re.compile(r"^Total\s+(\d+)\s+(\d+)")
used = re.compile(r"garbage-first heap\s+total (\d+)K, used (\d+)K")


def text():
    try:
        with open(syslog, errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def alive():
    return os.path.exists(f"/proc/{pid}")


fo = open(out, "a")
fr = open(raw, "a")


def ev(name):
    fo.write(json.dumps({"t_ms": int(time.time() * 1000), "event": name}) + "\n")
    fo.flush()


t_start = time.time()
while "Replaying" not in text():
    if not alive():
        ev("process_gone_before_replay"); sys.exit(1)
    if time.time() - t_start > 600:
        ev("no_replaying_line_600s"); sys.exit(2)
    time.sleep(0.2)
ev("replaying_seen")
while True:
    if "Log replay complete" in text():
        ev("replay_complete_seen"); break
    if not alive():
        ev("process_gone"); break
    t0 = time.time()
    rec = {"t_ms": int(t0 * 1000)}
    for k in NAMES.values():
        rec[k + "_n"] = 0; rec[k + "_b"] = 0
    tp = subprocess.Popen(nt + " tpstats", shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        h = subprocess.run(["jmap", "-histo:live", pid], capture_output=True, text=True, timeout=120).stdout
        rec["t1_ms"] = int(time.time() * 1000)
        fr.write(f"## sample t_ms={rec['t_ms']}\n")
        for line in h.splitlines():
            m = row.match(line)
            if m and m.group(3) in NAMES:
                k = NAMES[m.group(3)]
                rec[k + "_n"] = int(m.group(1)); rec[k + "_b"] = int(m.group(2)); fr.write(line + "\n")
            m = tot.match(line)
            if m:
                rec["total_n"] = int(m.group(1)); rec["total_b"] = int(m.group(2)); fr.write(line + "\n")
        hi = subprocess.run(["jcmd", pid, "GC.heap_info"], capture_output=True, text=True, timeout=60).stdout
        m = used.search(hi)
        if m:
            rec["heap_total_k"] = int(m.group(1)); rec["heap_used_k"] = int(m.group(2)); fr.write(m.group(0) + "\n")
        try:
            o = tp.communicate(timeout=30)[0]
            for line in o.splitlines():
                if line.startswith("MutationStage"):
                    rec["mutstage"] = line.split(); fr.write(line + "\n")
        except subprocess.TimeoutExpired:
            tp.kill(); rec["mutstage"] = "timeout"
    except Exception as ex:
        rec["error"] = repr(ex)
    rec["complete_after"] = "Log replay complete" in text()
    fo.write(json.dumps(rec) + "\n"); fo.flush(); fr.flush()
    time.sleep(max(0.0, 5.0 - (time.time() - t0)))
