#!/usr/bin/env python3
"""Emit stage-2 banding batches from the stage-1 CSVs.

Stage 2 bands every stage-1 row A-D by AI lexical/semantic judgement
(experiments/if-check-exp/stage2-ai-preprocessing/playbook.md). This script
builds the batch inputs; the bands themselves are a judgement and live in
experiments/if-check-exp/<system>/stage2-ai-preprocessing/bands.csv, which is
committed because it cannot be regenerated.

The stage-1 CSVs are gitignored and rebuilt per machine, so this script is
committed and its output is not.

Per-system settings are in SYSTEMS below:
  - anchors: rows with known verdicts, repeated in every batch so separate
    batches are judged against the same yardstick. All must come back A.
  - done: subtrees consumed by earlier package-by-package triage (Cassandra
    only). By default the script emits the rows outside them; --consumed
    emits the rows inside them. Between them the two scopes cover every
    stage-1 row. A system with no `done` has everything in the default scope.
  - size: default batch size (anchors not counted).

The system is --system=<name>, or else the results directory's basename
(codeql-queries/results/<system>).

Usage: make-stage2-batches.py <results-dir> <out-dir> [batch-size]
                              [--system=<name>] [--consumed]
"""
import csv, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..', '..'))

# Cassandra: anchors identified by uid, not by line: TeeDataInputPlus:58
# carries two comparisons and only the first is the capacity check.
CASSANDRA_ANCHORS = [
    'src/java/org/apache/cassandra/hints/HintsBufferPool.java:113#1',
    'src/java/org/apache/cassandra/utils/memory/MemtablePool.java:156#1',
    'src/java/org/apache/cassandra/net/AbstractMessageHandler.java:419#1',
    'src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java:282#1',
    'src/java/org/apache/cassandra/utils/memory/BufferPool.java:443#1',
    'src/java/org/apache/cassandra/index/sai/plan/QueryController.java:449#1',
    'src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java:204#1',
    'src/java/org/apache/cassandra/io/util/TeeDataInputPlus.java:58#1',
]

HADOOP_ANCHORS_MD = os.path.join(
    REPO, 'experiments', 'if-check-exp', 'hadoop', 'stage2-ai-preprocessing', 'anchors.md')


def hadoop_anchors():
    """Read the anchor table in anchors.md, the single source of truth.

    Rows look like  | 7 | `<moduleDir>` :: `<path under org/apache/hadoop/>:<line>#<n>` | ...
    """
    row = re.compile(r'^\|\s*(\d+)\s*\|\s*`([^`]+)`\s*::\s*`([^`]+)`')
    out = []
    for line in open(HADOOP_ANCHORS_MD):
        m = row.match(line)
        if m:
            module, rel = m.group(2), m.group(3)
            out.append('%s/src/main/java/org/apache/hadoop/%s' % (module, rel))
    return out


SYSTEMS = {
    # Subtrees triaged in September 2026; their verdicts are on record.
    'cassandra': {'anchors': lambda: CASSANDRA_ANCHORS,
                  'done': ('concurrent', 'cache', 'transport', 'db/compaction'),
                  'size': 120},
    # 18 anchors: 200 keeps them near 8% of a batch, as Cassandra's 8/120.
    'hadoop': {'anchors': hadoop_anchors, 'done': (), 'size': 200},
}


def consumed(row, done):
    return any(row['pkg'] == d or row['pkg'].startswith(d + '/') for d in done)


def short(fqn):
    return fqn.split('.')[-1]


def where(r):
    """Location prefix of a unit's text. Hadoop's pkg (e.g. hdfs/server/...)
    recurs across Maven modules, so it is prefixed with moduleDir when the
    CSV has that column."""
    return "%s | %s" % (r['moduleDir'], r['pkg']) if r.get('moduleDir') else r['pkg']


def row_ids(rows):
    """path:line is not unique -- a line can carry more than one comparison.
    Disambiguate with a 1-based index in CSV order, which is stable because
    the queries are order by-ed."""
    seen = {}
    for r in rows:
        key = (r['path'], r['line'])
        seen[key] = seen.get(key, 0) + 1
        r['uid'] = "%s:%s#%d" % (r['path'], r['line'], seen[key])
    return rows


def load(results, cfg, only_consumed=False):
    anchors = cfg['anchors']()
    done = cfg['done']
    narrowed = row_ids(list(csv.DictReader(open(os.path.join(results, 'NarrowedIfStatements.csv')))))
    helper = list(csv.DictReader(open(os.path.join(results, 'HelperGuardedIfStatements.csv'))))

    missing = set(anchors) - {r['uid'] for r in narrowed}
    if missing:
        sys.exit("anchors not in NarrowedIfStatements.csv (stale CSV or anchor list?):\n  "
                 + "\n  ".join(sorted(missing)))

    units = []
    for r in narrowed:
        # Anchors are kept in every scope: they exist to calibrate, and every
        # batch must carry them so the recorder's gate has something to check.
        if r['uid'] not in anchors and consumed(r, done) != only_consumed:
            continue
        units.append({
            'id': r['uid'],
            'anchor': r['uid'] in anchors,
            'kind': 'row',
            'text': "%s | %s.%s | %s %s %s" % (
                where(r), short(r['declaringType']), r['method'],
                r['lhs'], r['op'], r['rhs']),
        })

    # One judgement per distinct helper, applied to all its call sites.
    # Scope is decided by the CALL SITE's package, not the helper's declaring
    # one, so a helper called from both a consumed and a non-consumed subtree
    # appears in both scopes. Eight did (Cassandra); all eight were judged the
    # same band both times. The recorder does not dedupe, so dedupe bands.csv
    # on `uid` after running both scopes. The helper name carries no parameter
    # types, so overloads share one unit (Hadoop: Quota.isViolated()).
    by_helper = {}
    for r in helper:
        if consumed(r, done) != only_consumed:
            continue
        by_helper.setdefault(r['helper'], []).append(r)
    for h, rows in sorted(by_helper.items()):
        r = rows[0]
        units.append({
            'id': "helper:%s" % h,
            'anchor': False,
            'kind': 'helper',
            'text': "%s | helper %s | %s %s %s | %d call sites" % (
                where(r), short(h), r['lhs'], r['op'], r['rhs'], len(rows)),
        })
    return units


def main():
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) < 2:
        sys.exit(__doc__)
    only_consumed = '--consumed' in flags
    results, out = args[0], args[1]
    system = next((f.split('=', 1)[1] for f in flags if f.startswith('--system=')),
                  os.path.basename(os.path.normpath(results)))
    if system not in SYSTEMS:
        sys.exit("unknown system %r (pass --system=, one of: %s)"
                 % (system, ', '.join(sorted(SYSTEMS))))
    cfg = SYSTEMS[system]
    if only_consumed and not cfg['done']:
        sys.exit("%s has no consumed subtrees; --consumed would emit nothing" % system)
    size = int(args[2]) if len(args) > 2 else cfg['size']

    units = load(results, cfg, only_consumed)
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
    print("system: %s, units: %d (%d anchors held out), batches: %d, size: %d"
          % (system, len(units), len(anchors), n, size))


if __name__ == '__main__':
    main()
