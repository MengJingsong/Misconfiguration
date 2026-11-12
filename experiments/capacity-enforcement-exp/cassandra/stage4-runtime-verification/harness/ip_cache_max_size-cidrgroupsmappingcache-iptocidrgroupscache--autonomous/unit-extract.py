#!/usr/bin/env python3
"""The test JVM routes System.out through a logger, and printf's arguments arrive as separate log lines
(`SubstituteLogger.java:222 - <fragment>`). Rebuild the PROBE lines from the fragments, in order.
Usage: unit-extract.py <M> <unit-M.log>   -> prints 'max=M PROBE ...' lines"""
import re, sys
M, path = sys.argv[1], sys.argv[2]
frags = [l.rstrip('\n').split('SubstituteLogger.java:222 - ', 1)[1] for l in open(path, errors='replace') if 'SubstituteLogger.java:222 - ' in l]
text = ''.join(frags)
pats = [r'PROBE policyMaximum=-?\d+', r'PROBE outsideGroups estimatedSize=-?\d+',
        r'PROBE max=-?\d+ n=\d+ estimatedSize=\d+ maxSampledSize=\d+ heapDeltaBytes=-?\d+']
for p in pats:
    found = re.findall(p + r'(?=PROBE|\D|$)', text)
    if not found: print(f'max={M} MISSING {p}')
    for f in found: print(f'max={M} {f}')
