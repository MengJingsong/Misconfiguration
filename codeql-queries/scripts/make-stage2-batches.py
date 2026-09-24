#!/usr/bin/env python3
"""Emit stage-2 banding batches from the stage-1 CSVs.

Stage 2 bands every stage-1 row A-D by AI lexical/semantic judgement
(cassandra/if-check-exp/stage2-ai-preprocessing/playbook.md). This script
builds the batch inputs; the bands themselves are a judgement and live in
that folder's bands.csv, which is committed because it cannot be regenerated.

The stage-1 CSVs are gitignored and rebuilt per machine, so this script is
committed and its output is not.

Usage: make-stage2-batches.py <results-dir> <out-dir> [batch-size]
"""
import csv, os, sys

# Subtrees already consumed by earlier triage; their verdicts are on record.
DONE = ('concurrent', 'cache', 'transport', 'db/compaction')

# Rows with known stage-3 verdicts, repeated in every batch so that separate
# batches are judged against the same yardstick. All eight must come back A.
# Identified by uid, not by line: TeeDataInputPlus:58 carries two comparisons
# and only the first is the capacity check.
ANCHORS = [
    'src/java/org/apache/cassandra/hints/HintsBufferPool.java:113#1',
    'src/java/org/apache/cassandra/utils/memory/MemtablePool.java:156#1',
    'src/java/org/apache/cassandra/net/AbstractMessageHandler.java:419#1',
    'src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java:282#1',
    'src/java/org/apache/cassandra/utils/memory/BufferPool.java:443#1',
    'src/java/org/apache/cassandra/index/sai/plan/QueryController.java:449#1',
    'src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java:204#1',
    'src/java/org/apache/cassandra/io/util/TeeDataInputPlus.java:58#1',
]


def consumed(row):
    return any(row['pkg'] == d or row['pkg'].startswith(d + '/') for d in DONE)


def short(fqn):
    return fqn.split('.')[-1]


def row_ids(rows):
    """path:line is not unique -- 340 lines carry more than one comparison.
    Disambiguate with a 1-based index in CSV order, which is stable because
    the queries are order by-ed."""
    seen = {}
    for r in rows:
        key = (r['path'], r['line'])
        seen[key] = seen.get(key, 0) + 1
        r['uid'] = "%s:%s#%d" % (r['path'], r['line'], seen[key])
    return rows


def load(results):
    narrowed = row_ids(list(csv.DictReader(open(os.path.join(results, 'NarrowedIfStatements.csv')))))
    helper = list(csv.DictReader(open(os.path.join(results, 'HelperGuardedIfStatements.csv'))))

    units = []
    for r in narrowed:
        # Anchors are kept whatever their subtree: they exist to calibrate.
        if consumed(r) and r['uid'] not in ANCHORS:
            continue
        units.append({
            'id': r['uid'],
            'anchor': r['uid'] in ANCHORS,
            'kind': 'row',
            'text': "%s | %s.%s | %s %s %s" % (
                r['pkg'], short(r['declaringType']), r['method'],
                r['lhs'], r['op'], r['rhs']),
        })

    # One judgement per distinct helper, applied to all its call sites.
    by_helper = {}
    for r in helper:
        if consumed(r):
            continue
        by_helper.setdefault(r['helper'], []).append(r)
    for h, rows in sorted(by_helper.items()):
        r = rows[0]
        units.append({
            'id': "helper:%s" % h,
            'anchor': False,
            'kind': 'helper',
            'text': "%s | helper %s | %s %s %s | %d call sites" % (
                r['pkg'], short(h), r['lhs'], r['op'], r['rhs'], len(rows)),
        })
    return units


def main():
    results, out = sys.argv[1], sys.argv[2]
    size = int(sys.argv[3]) if len(sys.argv) > 3 else 120

    units = load(results)
    anchors = [u for u in units if u['anchor']]
    body = [u for u in units if not u['anchor']]

    os.makedirs(out, exist_ok=True)
    n = 0
    for i in range(0, len(body), size):
        n += 1
        with open(os.path.join(out, 'batch-%02d.txt' % n), 'w') as f:
            for u in anchors:
                f.write("ANCHOR\t%s\t%s\n" % (u['id'], u['text']))
            for u in body[i:i + size]:
                f.write("%s\t%s\t%s\n" % (u['kind'], u['id'], u['text']))
    print("units: %d (%d anchors held out), batches: %d, size: %d"
          % (len(units), len(anchors), n, size))


if __name__ == '__main__':
    main()
