#!/usr/bin/env python3
"""B20: one line per lifetime from runs/<label>/summary.txt (+ hprofstacks.txt): table.py <runs dir> <label> ..."""
import os, re, sys
R = sys.argv[1]
for L in sys.argv[2:]:
    p = os.path.join(R, L, 'summary.txt')
    if not os.path.exists(p): print(L, 'missing'); continue
    s = open(p).read(); g = lambda pat, d='-': (re.search(pat, s, re.M).group(1) if re.search(pat, s, re.M) else d)
    st = os.path.join(R, L, 'hprofstacks.txt'); top = '-'
    if os.path.exists(st):
        fr = [l.strip() for l in open(st) if l.startswith('  ')]
        top = 'stack:' + ('ImmutableBTreePartition.create<-SIM.indexPartition:1066<-CollatedViewIndexBuilder.build'
                         if any('indexPartition' in f for f in fr) and any('ImmutableBTreePartition.create' in f for f in fr) else fr[1] if len(fr) > 1 else '?')
    print(' | '.join([L, g(r'^outcome=(\S+)'), 't=' + g(r'^endpoint_seconds=(\S+)') + 's',
                      'K=' + g(r'Calculated page size (\d+)', g(r'original=(\d+) returned=(\d+)')),
                      'btm=' + g(r'^btm: (.*)$'), 'ck1=' + g(r'"rows": \[\["(\d+)"\]\]'),
                      'base=' + g(r'baseline_used=(\d+)'), 'peakUsed=' + g(r'peak_sampled_used_after_trigger=(\d+)'),
                      'maxPostGC=' + g(r'max_post_gc=(\S+) MiB'), 'gc=' + g(r'gc_after_trigger: (pauses=\d+ full=\d+)'),
                      'arr1MiB=' + g(r'B20 byte\[1048576\]: (\d+ arrays, [0-9.]+ MiB = [0-9.]+ GB)'),
                      'BTreeRow=' + g(r'BTreeRow: (\d+)'), 'shallow=' + g(r'total shallow (\d+ MiB)'),
                      'hprofB=' + g(r'size=(\d+)'), 'firstOOM=' + g(r'first_oom: \S+:\d+:(.*)$'), top,
                      'gcwin=' + g(r'gcwin: .*?(max60=\S+ longest>=90%win=\S+)'), g(r'(oom_marks=\S+)')]))
