#!/usr/bin/env python3
"""Emit stage-2 banding batches from the stage-1 CSVs.

Stage 2 bands every stage-1 row A-D by AI lexical/semantic judgement
(experiments/capacity-enforcement-exp/stage2-ai-preprocessing/playbook.md). This script
builds the batch inputs; the bands themselves are a judgement and live in
experiments/capacity-enforcement-exp/<system>/stage2-ai-preprocessing/bands.csv, which is
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

--extension (2026-11-11) bands the rows of the stage-1 extension beyond `if`
(EnforcementPlaces.csv, CapacitySetPlaces.csv) instead of the `if` corpus. Its
uids carry a prefix so they cannot collide with the `if` uids already in
bands.csv: `E:<path>:<line>#<n>` for an enforcement row, `E:verdict:<Type.method()>`
for a method verdict judged once for all its use sites, `C:<path>:<line>#<n>` for a
capacity-set row. Its batches carry the `if` anchors plus EXT_ANCHORS (known true
positives in the new forms), and are named `ext-batch-NN.txt` so their labels do
not collide with the `if` run's `batch-NN.txt`.

Usage: make-stage2-batches.py <results-dir> <out-dir> [batch-size]
                              [--system=<name>] [--consumed] [--extension]
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
    REPO, 'experiments', 'capacity-enforcement-exp', 'hadoop', 'stage2-ai-preprocessing', 'anchors.md')


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
                  'ext_anchors': lambda: CASSANDRA_EXT_ANCHORS,
                  'done': ('concurrent', 'cache', 'transport', 'db/compaction'),
                  'size': 120},
    # 18 anchors: 200 keeps them near 8% of a batch, as Cassandra's 8/120.
    'hadoop': {'anchors': hadoop_anchors, 'done': (), 'size': 200,
               'ext_anchors': lambda: HADOOP_EXT_ANCHORS,
               'foreign_anchors': lambda: CASSANDRA_EXT_ANCHOR_ROWS},
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


# --extension anchors (Cassandra): stage-4 true positives whose check or capacity
# is in one of the new forms. (prefix, path suffix, line, lhs-or-target or verdict method)
CASSANDRA_EXT_ANCHORS = [
    ('E', 'db/commitlog/CommitLogSegmentManagerCDC.java', '335', '... + ...'),   # cdc_total_space, ternary
    ('E', 'cql3/selection/ResultSetBuilder.java', '97', 'size'),                  # coordinator_read_size_fail_threshold, return
    ('V', '', '', 'OutboundConnection.acquireCapacity()'),                          # internode_application_send_queue_capacity, switch
    ('C', 'utils/memory/MemtablePool.java', '119', 'SubPool.limit'),               # memtable_heap_space
    ('C', 'hints/HintsBufferPool.java', '41', 'HintsBufferPool.MAX_ALLOCATED_BUFFERS'),  # MAX_HINT_BUFFERS
    ('C', 'cache/CaffeineCache.java', '53', 'weightedCapacity'),                    # key_cache_size, Caffeine.maximumWeight
]

# --extension anchors (Hadoop, 2026-11-11): the two Hadoop stage-4 true positives with a
# new-form row, both capacity-set rows.
HADOOP_EXT_ANCHORS = [
    ('C', 'hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/RawPathHandle.java',
     '40', 'RawPathHandle.MAX_SIZE'),                                   # RawPathHandle_MAX_SIZE
    ('C', 'hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/impl/prefetch/SingleFilePerBlockCache.java',
     '228', 'SingleFilePerBlockCache.maxBlocksCount'),                  # fs.s3a.prefetch.max.blocks.count
]

# Cassandra extension anchors as text, carried in Hadoop extension batches for cross-system
# calibration (Hadoop has no verified enforcement-form anchor). Uids get an `X:cassandra:` prefix.
CASSANDRA_EXT_ANCHOR_ROWS = [
    ('X:cassandra:E:src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java:97#1',
     'cql3/selection | ResultSetBuilder.shouldReject | comparison/return | size > thresholdBytes'),
    ('X:cassandra:E:src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java:335#1',
     'db/commitlog | CommitLogSegmentManagerCDC$CDCSizeTracker.processNewSegment | comparison/ternary | ... + ... > allowance'),
    ('X:cassandra:E:verdict:OutboundConnection.acquireCapacity()',
     'net | verdict of OutboundConnection.acquireCapacity() used in switch | 1 use sites | impls=1 minDepth=1'),
    ('X:cassandra:C:src/java/org/apache/cassandra/cache/CaffeineCache.java:53#1',
     'cache | CaffeineCache.create | capacity-set create Caffeine.maximumWeight | size = weightedCapacity | sizeSource parameter'),
    ('X:cassandra:C:src/java/org/apache/cassandra/hints/HintsBufferPool.java:41#1',
     'hints | HintsBufferPool.<clinit> | capacity-set field/field-initializer | HintsBufferPool.MAX_ALLOCATED_BUFFERS = getInt() | compared in 1 comparison(s) | sizeSource no-arg-call'),
    ('X:cassandra:C:src/java/org/apache/cassandra/utils/memory/MemtablePool.java:119#1',
     'utils/memory | MemtablePool$SubPool.SubPool | capacity-set field/constructor | SubPool.limit = limit | compared in 1 comparison(s) | sizeSource parameter'),
]

# README §3.7.2 order: a comparison with several contexts keeps the first.
CONTEXT_ORDER = ['ternary', 'loop-condition', 'switch-selector', 'lambda', 'assert', 'return',
                 'argument', 'assignment', 'declaration', 'field-initializer']


def load_extension(results, cfg):
    """Units for the stage-1 extension rows (see --extension in the module doc)."""
    enf = list(csv.DictReader(open(os.path.join(results, 'EnforcementPlaces.csv'))))
    cap = list(csv.DictReader(open(os.path.join(results, 'CapacitySetPlaces.csv'))))

    def rank(r):
        p = r['pattern']
        return CONTEXT_ORDER.index(p.split('/', 1)[1]) if p.startswith('comparison/') else 0

    units = []
    # enforcement rows: one unit per comparison or call, first context kept
    prim, verdicts = {}, {}
    for r in enf:
        if r['pattern'].startswith('verdict-'):
            m = r['detail'].split(' ')[0]
            verdicts.setdefault(m, []).append(r)
            continue
        key = (r['path'], int(r['line']), r['pattern'].split('/')[0], r['lhs'], r['op'], r['rhs'],
               '' if r['pattern'].startswith('comparison/') else r['detail'])
        if key not in prim or rank(r) < rank(prim[key]):
            prim[key] = r
    rows = sorted(prim.values(), key=lambda r: (r['path'], int(r['line']), r['pattern'], r['lhs'],
                                                r['op'], r['rhs'], r['detail']))
    seen = {}
    for r in rows:
        k = (r['path'], r['line'])
        seen[k] = seen.get(k, 0) + 1
        how = r['pattern'] + (' ' + r['detail'] if r['detail'] else '')
        cmpx = ' '.join(x for x in (r['lhs'], r['op'], r['rhs']) if x)
        units.append({'id': 'E:%s:%s#%d' % (r['path'], r['line'], seen[k]), 'kind': 'enforcement',
                      'match': ('E', r['path'], r['line'], r['lhs']), 'anchor': False,
                      'target': '%s:%s' % (r['path'], r['line']),
                      'text': '%s | %s.%s | %s | %s' % (where(r), short(r['declaringType']),
                                                        r['method'], how, cmpx)})
    # method verdicts: one unit per verdict method, all its use sites
    for m, rs in sorted(verdicts.items()):
        r = rs[0]
        ctxs = sorted({x['pattern'][len('verdict-'):] for x in rs})
        meta = ' '.join(r['detail'].split(' ')[1:])
        units.append({'id': 'E:verdict:%s' % m, 'kind': 'verdict', 'match': ('V', '', '', m),
                      'anchor': False,
                      'target': ' '.join('%s:%s' % (x['path'], x['line']) for x in rs),
                      'text': '%s | verdict of %s used in %s | %d use sites | %s' % (
                          where(r), m, '/'.join(ctxs), len(rs), meta)})
    # capacity-set rows
    rows = sorted(cap, key=lambda r: (r['path'], int(r['line']), r['pattern'], r['detail'],
                                      r['target'], r['value']))
    seen = {}
    for r in rows:
        k = (r['path'], r['line'])
        seen[k] = seen.get(k, 0) + 1
        if r['pattern'] == 'create':
            what = 'capacity-set create %s | size = %s' % (r['detail'], r['value'])
            m = r['value']
        else:
            what = 'capacity-set %s | %s = %s | compared in %s' % (
                r['pattern'], r['target'], r['value'], r['detail'])
            m = r['target']
        units.append({'id': 'C:%s:%s#%d' % (r['path'], r['line'], seen[k]), 'kind': 'capacity-set',
                      'match': ('C', r['path'], r['line'], m), 'anchor': False,
                      'target': '%s:%s' % (r['path'], r['line']),
                      'text': '%s | %s.%s | %s | sizeSource %s' % (
                          where(r), short(r['declaringType']), r['method'], what, r['sizeSource'])})

    # anchors: the `if` anchors (same yardstick as the `if` run) plus the extension anchors
    for spec in cfg.get('ext_anchors', lambda: [])():
        hits = [u for u in units if u['match'][0] == spec[0] and u['match'][1].endswith(spec[1])
                and u['match'][2] == spec[2] and u['match'][3] == spec[3]]
        if len(hits) != 1:
            sys.exit('extension anchor %r matches %d units (stale CSV or anchor list?)' % (spec, len(hits)))
        hits[0]['anchor'] = True
    for uid, text in cfg.get('foreign_anchors', lambda: [])():
        units.append({'id': uid, 'kind': 'foreign-anchor', 'anchor': True, 'text': text})
    if_units = {u['id']: u for u in load(results, cfg)}
    for a in cfg['anchors']():
        u = dict(if_units[a])
        units.append(u)
    return units


def main():
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) < 2:
        sys.exit(__doc__)
    only_consumed = '--consumed' in flags
    extension = '--extension' in flags
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

    units = load_extension(results, cfg) if extension else load(results, cfg, only_consumed)
    prefix = 'ext-batch' if extension else 'batch'
    anchors = [u for u in units if u['anchor']]
    body = [u for u in units if not u['anchor']]

    os.makedirs(out, exist_ok=True)
    n = 0
    for i in range(0, len(body), size):
        n += 1
        with open(os.path.join(out, '%s-%02d.txt' % (prefix, n)), 'w') as f:
            for u in anchors:
                f.write("ANCHOR\t%s\t%s\n" % (u['id'], u['text']))
            for u in body[i:i + size]:
                f.write("%s\t%s\t%s\n" % (u['kind'], u['id'], u['text']))
    print("system: %s, units: %d (%d anchors held out), batches: %d, size: %d"
          % (system, len(units), len(anchors), n, size))


if __name__ == '__main__':
    main()
