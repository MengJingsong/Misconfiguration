#!/usr/bin/env python3
"""Independent re-parse of the raw jcmd histogram files (hist-*.txt), not readings.jsonl, for the numbers the conclusion cites. usage: selfcheck.py <logroot>"""
import os, sys
root = sys.argv[1]; MiB = 1048576.0
def hist(p):
    d = {}
    for l in open(p):
        t = l.split()
        if len(t) >= 4 and t[0].endswith(':'):
            d[t[3]] = (int(t[1]), int(t[2]))
    return d
def get(a, lab):
    h = hist(os.path.join(root, a, 'hist-%s.txt' % lab))
    return h.get('org.apache.cassandra.audit.AuditEvent', (0, 0))[0], h['[B'][1]
for a in ('S-50', 'S-200', 'S-1000', 'L-50', 'L-200', 'L-1000', 'OFF', 'Q-50', 'Q-200', 'Q-1000', 'QOFF'):
    b0 = get(a, '01-baseline-after-schema')[1]
    last = 'N20000' if a == 'S-200' else ('N03000' if a.startswith('S-') else 'N02000')
    n, b = get(a, last)
    print('%-7s %-7s liveAuditEvent=%-5d dBytes[]=%9.2f MiB (per live event %.1f KiB)' % (a, last, n, (b - b0) / MiB, ((b - b0) / n / 1024) if n else 0))
for m in ('50', '200', '1000'):
    b0l = get('L-' + m, '01-baseline-after-schema')[1]; b0o = get('OFF', '01-baseline-after-schema')[1]
    for lab in ('N00400', 'N02000'):
        nl, bl = get('L-' + m, lab); _, bo = get('OFF', lab)
        print('PAIRED L-%s %s: (ON-OFF) = %.2f MiB; live AuditEvent %d x 256 KiB = %.2f MiB' % (m, lab, ((bl - b0l) - (bo - b0o)) / MiB, nl, nl * 0.25))
