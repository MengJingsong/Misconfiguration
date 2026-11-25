#!/usr/bin/env python3
"""Reassemble the O72* records of DeletingArchiverBoundTest from an `ant testsome` console log.
The test JVM routes System.out through a logger that logs each print fragment as its own line
(`... SubstituteLogger.java:222 - <fragment>`); a record starts at a fragment beginning with `O72`.
Usage: extract_o72.py <ant-log>  > readings.txt"""
import sys, re
MARK = 'SubstituteLogger.java:222 - '
recs, cur = [], None
for line in open(sys.argv[1], errors='replace'):
    line = line.rstrip('\n')
    i = line.find(MARK)
    if i < 0 or '[main]' not in line:
        continue
    frag = line[i + len(MARK):]
    if frag.startswith('O72'):
        if cur is not None: recs.append(cur)
        cur = frag
    elif cur is not None:
        cur += frag
if cur is not None: recs.append(cur)
for r in recs: print(r.strip())
