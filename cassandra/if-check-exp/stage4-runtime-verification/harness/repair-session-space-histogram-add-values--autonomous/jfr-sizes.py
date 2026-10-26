#!/usr/bin/env python3
"""usage: jfr-sizes.py <recording.jfr> [--all]. Lists the jdk.ObjectAllocationOutsideTLAB events whose stack has HistogramBuilder.add (top frames within 4),
as exact bytes (jfr print --json), per thread: 'SIZE <bytes> <objectClass> <thread> <startTime>' and a sorted summary 'DISTINCT <bytes> xN'. --all also counts every long[] event (for the instrument check)."""
import json, subprocess, sys, collections
f = sys.argv[1]
out = subprocess.run(['jfr', 'print', '--json', '--events', 'jdk.ObjectAllocationOutsideTLAB', '--stack-depth', '5', f], capture_output=True, text=True, check=True).stdout
ev = json.loads(out)['recording']['events']
sizes = collections.Counter(); total = 0
for e in ev:
    v = e['values']; total += 1
    frames = v.get('stackTrace', {}).get('frames', []) if v.get('stackTrace') else []
    names = [fr['method']['type']['name'].replace('/', '.') + '.' + fr['method']['name'] for fr in frames]
    if any(n == 'org.apache.cassandra.utils.HistogramBuilder.add' for n in names[:4]):
        sz = v['allocationSize']; sizes[sz] += 1
        print('SIZE', sz, v['objectClass']['name'], (v.get('eventThread') or {}).get('javaName'), v['startTime'])
print('TOTAL_OUTSIDE_TLAB_EVENTS', total)
for sz in sorted(sizes): print('DISTINCT', sz, 'x%d' % sizes[sz])
