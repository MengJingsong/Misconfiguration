#!/usr/bin/env python3
"""Runbook defect D1 (B2e.3): the test JVM's System.out goes to logback (build/test/logs/<jdk>/TEST-<class>.log), one log line
per write() call, with newlines dropped, so the PROBE printf arrives as fragments and nothing reaches the junit XML.
This reassembles them: a record starts at a [main] fragment beginning with 'PROBE' and continues while the next [main]
fragments are a ' label=' or a number. usage: collect-probe.py <log>..."""
import re, sys
frag = re.compile(r'^[A-Z]+ +\[main\] \S+ (.*)$')
cont = re.compile(r'^( [A-Za-z0-9]+=|-?[\d.]+)$')
for path in sys.argv[1:]:
    msgs = [m.group(1) for m in (frag.match(l.rstrip('\n')) for l in open(path, errors='replace')) if m]
    i = 0
    while i < len(msgs):
        if msgs[i].startswith('PROBE'):
            rec = msgs[i]; j = i + 1
            while j < len(msgs) and cont.match(msgs[j]):
                rec += msgs[j]; j += 1
            print(rec); i = j
        else:
            i += 1
