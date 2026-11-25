#!/usr/bin/env python3
"""Summarise `jfr print --json --events jdk.ObjectAllocationOutsideTLAB` output (B3d).

Usage: jfrsum.py <json file>
Prints: total event count, then one line per event whose stack contains
Server.setupResponseForProtobuf (or any Server.setupResponse*), with allocationSize in bytes
and objectClass; then a summary (count, min, max, sizes histogram).
"""
import collections
import json
import sys


def main(path):
    with open(path) as f:
        doc = json.load(f)
    events = doc.get("recording", {}).get("events", [])
    hits = []
    for ev in events:
        v = ev.get("values", {})
        frames = ((v.get("stackTrace") or {}).get("frames")) or []
        names = []
        for fr in frames:
            m = fr.get("method") or {}
            t = (m.get("type") or {}).get("name", "").replace("/", ".")  # JFR JSON uses slashes
            names.append(t + "." + m.get("name", ""))
        if any(n.endswith("ipc.Server.setupResponseForProtobuf") or
               "ipc.Server.setupResponse" in n for n in names):
            cls = ((v.get("objectClass") or {}).get("name")) or "?"
            hits.append((int(v.get("allocationSize", 0)), cls, names[:3]))
    print("events_total", len(events))
    for size, cls, top in hits:
        print("setupResponse_alloc", size, cls, " <- ".join(top))
    sizes = [h[0] for h in hits]
    print("setupResponse_count", len(sizes))
    if sizes:
        print("setupResponse_min", min(sizes), "max", max(sizes))
        print("setupResponse_hist", dict(collections.Counter(sizes).most_common(10)))


if __name__ == "__main__":
    main(sys.argv[1])
