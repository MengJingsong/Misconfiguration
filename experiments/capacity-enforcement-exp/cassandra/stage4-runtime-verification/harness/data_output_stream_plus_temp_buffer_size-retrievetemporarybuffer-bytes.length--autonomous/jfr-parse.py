#!/usr/bin/env python3
"""Count JFR allocation events whose stack contains retrieveTemporaryBuffer (B3e, amendment A2).
Input: output of `jfr print --json --events jdk.ObjectAllocationOutsideTLAB,jdk.ObjectAllocationInNewTLAB --stack-depth 64`.
Prints: number of events, temp-buffer events by (event type, allocationSize bytes, thread), largest byte[] allocation overall."""
import json, sys, collections
d = json.load(open(sys.argv[1]))
evs = d['recording']['events']
tb = collections.Counter(); threads = collections.defaultdict(set); callers = collections.Counter()
big = collections.Counter()
for e in evs:
    v = e['values']; size = v.get('allocationSize')
    frames = (v.get('stackTrace') or {}).get('frames') or []
    names = [f"{(f['method']['type']['name'])}.{f['method']['name']}" for f in frames]
    cls = (v.get('objectClass') or {}).get('name')
    if cls in ('byte[]', '[B') and size and size >= (1 << 20):
        big[(size, names[1] if len(names) > 1 else (names[0] if names else '?'))] += 1
    if any(n.endswith('.retrieveTemporaryBuffer') for n in names):
        th = (v.get('eventThread') or {}).get('javaName')
        tb[(e['type'], size)] += 1; threads[size].add(th)
        i = [k for k, n in enumerate(names) if n.endswith('.retrieveTemporaryBuffer')][0]
        callers[' <- '.join(names[i:i+4])] += 1
print(f"events={len(evs)}")
print(f"tempbuf_events={sum(tb.values())}")
for (t, s), n in sorted(tb.items(), key=lambda x: (x[0][1] or 0)):
    print(f"tempbuf type={t} allocationSize={s} arrayLength={s-16} count={n} distinct_threads={len(threads[s])}")
for c, n in callers.most_common(10):
    print(f"tempbuf caller count={n}: {c}")
print(f"tempbuf_max_size={max([s for (_, s) in tb] or [0])}")
print(f"tempbuf_max_len={max([s - 16 for (_, s) in tb] or [0])}  # byte[] header = 16 B (checked with JfrParseCheck)")
for (s, caller), n in sorted(big.items(), reverse=True)[:15]:
    print(f"byte[]>=1MiB size={s} count={n} caller={caller}")
