#!/usr/bin/env python3
"""Read a client JFR recording (case-file B3d (1), amended A4/A5): list the byte[] allocations whose stack
contains DFSOutputStream.createPacket, in time order, plus the client JVM heap actually in force.
Usage: python3 -I jfr-read.py <jfr json from `jfr print --json`> <tag>
Prints one line:  JFR,<tag>,maxHeap=<bytes>,xmx=<arg>,n=<count>,first=<size>,later=<sizes...>,kinds=<event types>"""
import json, sys
p, tag = sys.argv[1], sys.argv[2]
try:
    d = json.load(open(p))
except Exception as e:
    print(f"JFR,{tag},error=unreadable:{type(e).__name__}"); sys.exit(0)
evs = d.get("recording", {}).get("events", [])
maxheap = None; xmx = None; pk = []
for e in evs:
    t = e.get("type"); v = e.get("values", {})
    if t == "jdk.GCHeapConfiguration":
        maxheap = v.get("maxSize")
    elif t == "jdk.JVMInformation":
        args = v.get("jvmArguments", "") or ""
        xs = [a for a in args.split() if a.startswith("-Xmx")]
        xmx = xs[-1] if xs else "none"
    elif t in ("jdk.ObjectAllocationOutsideTLAB", "jdk.ObjectAllocationInNewTLAB"):
        oc = (v.get("objectClass") or {}).get("name")
        if oc not in ("[B", "byte[]"):
            continue
        frames = ((v.get("stackTrace") or {}).get("frames")) or []
        names = [((f.get("method") or {}).get("type") or {}).get("name", "") + "." + (f.get("method") or {}).get("name", "") for f in frames]
        if any(n.endswith("DFSOutputStream.createPacket") for n in names):
            size = v.get("allocationSize") if t.endswith("OutsideTLAB") else v.get("allocationSize")
            pk.append((v.get("startTime"), size, t.split(".")[-1]))
pk.sort(key=lambda x: x[0])
sizes = [s for _, s, _ in pk]
kinds = sorted(set(k for _, _, k in pk))
later = sizes[1:]
# compress later sizes: value x count
from collections import Counter
lc = Counter(later)
print(f"JFR,{tag},maxHeap={maxheap},xmx={xmx},n={len(sizes)},first={sizes[0] if sizes else 'none'},"
      f"later={' '.join(f'{k}x{c}' for k,c in sorted(lc.items())) or 'none'},kinds={'+'.join(kinds) or 'none'}")
