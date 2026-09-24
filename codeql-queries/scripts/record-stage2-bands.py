#!/usr/bin/env python3
"""Join a batch file with its band verdicts and append to bands.csv.

Verdicts arrive as one line per batch line, in order: "<BAND> <reason>".
Anchor lines are checked (all must be A) and are not written to bands.csv.

Usage: record-stage2-bands.py <batch.txt> <verdicts.txt> <bands.csv> <model> <date>
"""
import csv, os, sys

batch, verdicts, out, model, date = sys.argv[1:6]
rows = [l.rstrip('\n').split('\t') for l in open(batch) if l.strip()]
vs = [l.strip() for l in open(verdicts) if l.strip()]
if len(rows) != len(vs):
    sys.exit("batch has %d lines, verdicts %d" % (len(rows), len(vs)))

bad, new = [], []
for (kind, uid, text), v in zip(rows, vs):
    band, _, reason = v.partition(' ')
    band = band.strip().upper()
    if band not in ('A', 'B', 'C', 'D'):
        sys.exit("bad band %r for %s" % (band, uid))
    if kind == 'ANCHOR':
        if band != 'A':
            bad.append("%s -> %s" % (uid, band))
        continue
    new.append((uid, kind, band, reason.strip(), model, date,
                os.path.basename(batch)))

if bad:
    sys.exit("ANCHOR CHECK FAILED, batch not recorded:\n  " + "\n  ".join(bad))

exists = os.path.exists(out)
with open(out, 'a', newline='') as f:
    w = csv.writer(f, lineterminator='\n')
    if not exists:
        w.writerow(['uid', 'kind', 'band', 'reason', 'model', 'date', 'batch'])
    w.writerows(new)
print("anchors OK; wrote %d rows to %s" % (len(new), out))
