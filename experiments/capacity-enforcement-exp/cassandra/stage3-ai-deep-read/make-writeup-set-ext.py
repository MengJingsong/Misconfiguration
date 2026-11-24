#!/usr/bin/env python3
"""Build the write-up set of the stage-1 extension rows (Cassandra, 2026-11-11).

Joins the extension units (rebuilt from the gitignored stage-1 CSVs by
codeql-queries/scripts/make-stage2-batches.py --extension) with their stage-2 bands in
../stage2-ai-preprocessing/bands.csv (uids starting `E:` or `C:`), and writes
writeup-set-ext.csv: bands A, B, C in that order (band D is not read, as for the `if`
corpus), one row per unit, sorted by uid within a band.

A unit whose target line is already the target of a case file gets that file in
`case_file` and `existing case` in `stage3_record`, so it is not written up twice. A
capacity-set unit whose field name is the constraint of existing case files (by the case
file's name prefix) gets `known constraint: <prefix>` in `stage3_record`: it is a second
entry point to a constraint already traced, and its owner decides whether to write it up.

Usage: python3 make-writeup-set-ext.py --screen          annotate open rows (safe; the normal use now)
       python3 make-writeup-set-ext.py --rebuild [results-dir] [--force]   rebuild from scratch (renumbers;
           refuses to overwrite a CSV that already holds progress unless --force)

Fix 2026-11-24 (Jingsong). The `known constraint` marker matched only when the assigned field's
name equalled a case prefix, so it missed 26 of the 43 rows batch 1 skipped as covered (e.g.
`DatabaseDescriptor.keyCacheSizeInMiB` vs `key_cache_size`, `ChunkCache.cacheSize` vs
`file_cache_size`), and a plain run regenerated the CSV and renumbered it, wiping progress.
`--screen` now writes a `screen` column on open rows only (empty stage3_record), never touching
any other cell, from five signals against every case file in `cases/`:
  strong: constraint name (field or operand name, units stripped, equals a case's constraint prefix),
          operand in case name, field reference `Type.field` in a case body, constraint named after
          the unit's class;
  weak:   same line (`File.java:N` of the target in a case body), same class (`Type.java:N` in at most
          8 case files).
Strong hits read `likely covered: <case> (<signals>)`, weak-only hits `check: <cases> (<signals>)`.
Tested on orders 1-53 (2026-11-24): all 43 rows skipped as covered are flagged (30 strong,
13 weak-only); of the 10 rows that became new cases, 1 has a strong flag and 4 a weak-only flag.
A flag is a prompt to compare constraints before the batch, not a skip by itself.
"""
import csv
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
SCRIPTS = os.path.join(REPO, 'codeql-queries', 'scripts')
BANDS = os.path.join(HERE, '..', 'stage2-ai-preprocessing', 'bands.csv')
OUT = os.path.join(HERE, 'writeup-set-ext.csv')
PILOT = os.path.join(HERE, '..', 'stage1-codeql-preprocessing', 'pilot_report.py')


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


UNIT_SUFFIX = r'(inmib|inkib|ingib|inbytes|inmb|inkb|bytes|mib|kib|gib|inms|inmillis|inseconds|mb|kb)$'
GENERIC = {'size', 'capacity', 'length', 'limit', 'count', 'max', 'min', 'value', 'bytes', 'buffer', 'threshold',
           'total', 'used', 'remaining', 'position', 'index', 'cachesize', 'maxsize', 'queuecapacity', 'limitbytes',
           'ondisklength', 'maxbytes', 'sizeinbytes', 'current', 'offset'}
STRONG = ('constraint name', 'operand in case name', 'field ref', 'constraint named after class')


def norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


def strip_units(n):
    n2 = re.sub(UNIT_SUFFIX, '', n)
    return n2 if len(n2) >= 5 else n


def load_cases():
    d = os.path.join(HERE, 'cases')
    return {f[:-3]: open(os.path.join(d, f), errors='ignore').read() for f in os.listdir(d) if f.endswith('.md')}


def screen_unit(u, cases, prefix):
    """Possible covering case files for one unit: {stem: set(signals)}."""
    hits = {}
    add = lambda st, sig: hits.setdefault(st, set()).add(sig)
    path, line = (u['target'].split(' ')[0].rsplit(':', 1) + [''])[:2]
    base = os.path.basename(path)
    if line:
        pat = re.compile(re.escape(base + ':' + line) + r'(?!\d)')
        for st, body in cases.items():
            if pat.search(body):
                add(st, 'same line ' + base + ':' + line)
    text = u['text']
    ids = set()
    m = re.search(r'\| (\w[\w$]*)\.(\w+) = ', text)
    if m:
        ids.add((m.group(1), m.group(2)))
    tail = text.split('|', 3)[-1] if text.count('|') >= 3 else text
    ids |= {('', t) for t in re.findall(r'[A-Za-z_][A-Za-z0-9_]{5,}', tail)}
    for typ, name in ids:
        n = strip_units(norm(name))
        if len(n) < 6 or n in GENERIC:
            continue
        for st in prefix.get(n, []):
            add(st, 'constraint name ' + name)
        for st, body in cases.items():
            if n in [norm(p) for p in st.split('-')]:
                add(st, 'operand in case name ' + name)
            elif typ and re.search(r'\b' + re.escape(typ.split('$')[-1]) + r'\.' + re.escape(name) + r'\b', body):
                add(st, 'field ref %s.%s' % (typ, name))
    typ = base[:-5] if base.endswith('.java') else ''
    if typ:
        pat = re.compile(r'\b' + re.escape(typ) + r'\.java:\d')
        withc = [st for st, body in cases.items() if pat.search(body)]
        if len(withc) <= 8:
            for st in withc:
                add(st, 'same class ' + typ)
        tn = norm(typ)
        for p, sts in prefix.items():
            if len(tn) >= 10 and p.startswith(tn):
                for st in sts:
                    add(st, 'constraint named after class ' + typ)
    return hits


def screen_note(hits):
    if not hits:
        return ''
    strong = sorted(st for st, sig in hits.items() if any(x.startswith(STRONG) for x in sig))
    if strong:
        return 'likely covered: ' + '; '.join('%s (%s)' % (st, ', '.join(sorted(hits[st]))) for st in strong[:3])
    weak = sorted(hits)
    return 'check: ' + '; '.join('%s (%s)' % (st, ', '.join(sorted(hits[st]))) for st in weak[:3])


def case_prefixes(cases):
    prefix = {}
    for st in cases:
        prefix.setdefault(strip_units(norm(st.split('-')[0])), []).append(st)
    return prefix


def known_note(unit, known):
    m = re.search(r'\| (\w+)\.(\w+) = ', unit['text']) if unit['kind'] == 'capacity-set' else None
    if m:
        key = strip_units(norm(m.group(2)))
        if key in known:
            return 'known constraint: %s' % known[key]
    return ''


def screen_main():
    rows = list(csv.DictReader(open(OUT)))
    fields = list(rows[0].keys())
    if 'screen' not in fields:
        fields.append('screen')
    cases = load_cases()
    prefix = case_prefixes(cases)
    n = flagged = strong = 0
    for r in rows:
        if r.get('stage3_record', '').strip() or r.get('case_file', '').strip():
            r.setdefault('screen', '')
            continue
        n += 1
        note = screen_note(screen_unit(r, cases, prefix))
        r['screen'] = note
        flagged += bool(note)
        strong += note.startswith('likely')
    with open(OUT, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fields, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    print('screened %d open rows: %d likely covered, %d check, %d no flag' % (n, strong, flagged - strong, n - flagged))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if '--screen' in sys.argv:
        return screen_main()
    if '--rebuild' not in sys.argv:
        sys.exit(__doc__)
    if os.path.exists(OUT) and '--force' not in sys.argv:
        with open(OUT) as fh:
            if any(r.get('stage3_record') or r.get('case_file') for r in csv.DictReader(fh)):
                sys.exit('refusing to rebuild: %s already holds progress (use --screen, or --force)' % OUT)
    results = args[0] if args else os.path.join(REPO, 'codeql-queries', 'results', 'cassandra')
    mk = module(os.path.join(SCRIPTS, 'make-stage2-batches.py'), 'mk')
    units = {u['id']: u for u in mk.load_extension(results, mk.SYSTEMS['cassandra'])
             if u['id'].startswith(('E:', 'C:'))}
    bands = {r['uid']: r for r in csv.DictReader(open(BANDS)) if r['uid'].startswith(('E:', 'C:'))}
    missing = set(units) - set(bands)
    if missing:
        sys.exit('%d extension units have no band yet (e.g. %s)' % (len(missing), sorted(missing)[0]))

    targets = {}
    for fn, t in module(PILOT, 'pilot').case_targets().items():
        if t:
            targets.setdefault('%s:%d' % t, []).append(fn)

    known = {strip_units(norm(f.split('-')[0])): f.split('-')[0]
             for f in os.listdir(os.path.join(HERE, 'cases')) if f.endswith('.md')}

    rows = []
    for uid, b in bands.items():
        if b['band'] not in ('A', 'B', 'C') or b['batch'] == 'ext-anchors':
            continue
        u = units[uid]
        first = u['target'].split(' ')[0]
        existing = targets.get(first, [])
        rows.append({'uid': uid, 'kind': u['kind'], 'band': b['band'], 'target': u['target'],
                     'text': u['text'], 'stage2_reason': b['reason'],
                     'stage3_record': 'existing case' if existing else known_note(u, known),
                     'case_file': ' '.join(f[:-3] for f in existing), 'estimate': '', 'stage4': ''})
    rows.sort(key=lambda r: ('ABC'.index(r['band']), r['uid']))
    with open(OUT, 'w', newline='') as fh:
        w = csv.DictWriter(fh, ['order', 'uid', 'kind', 'band', 'target', 'text', 'stage2_reason',
                                'stage3_record', 'case_file', 'estimate', 'stage4'], lineterminator='\n')
        w.writeheader()
        for i, r in enumerate(rows, 1):
            w.writerow(dict(r, order=i))
    by = {}
    for r in rows:
        by[(r['band'], r['kind'])] = by.get((r['band'], r['kind']), 0) + 1
    print('wrote %d units to %s' % (len(rows), OUT))
    for k in sorted(by):
        print('  %s %-13s %d' % (k[0], k[1], by[k]))
    print('  already a case target: %d' % sum(1 for r in rows if r['case_file']))
    print('  known constraint (capacity-set): %d' % sum(1 for r in rows if r['stage3_record'].startswith('known')))


if __name__ == '__main__':
    main()
