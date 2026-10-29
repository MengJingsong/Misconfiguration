#!/usr/bin/env python3
"""Independent re-parse of the raw logs of max_offset-createentry-offset--autonomous for results section 5 (not the harness's own
EXPECTED lines: every expectation is recomputed here from the raw READ lines and from the constants).
usage: selfcheck.py <run1 dir with unit/unit.out and cluster/<arm>/...>"""
import os, re, sys
d = sys.argv[1]
ok = fail = 0
def chk(name, cond, detail=''):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print(('PASS ' if cond else 'FAIL ') + name + ('  [' + detail + ']' if detail else ''))
MAX = (1 << 47) - 1
# ---- unit tier
rd = {}
for l in open(d + '/unit/unit.out'):
    m = re.match(r'READ (.*?) -> (.*)$', l.rstrip())
    if m: rd[m.group(1)] = m.group(2)
def val(res, k):
    m = re.search(r'\b%s=(\S*)' % k, res); return m.group(1) if m else None
for o in (1, 2**31 - 1, 2**31, MAX - 1, MAX):
    r = rd['single offset=%d' % o]
    chk('unit: single %d writes, 80 bytes, %s' % (o, 'SIMPLE' if o <= 2**31 - 1 else 'FACTORED'), r.startswith('OK') and val(r, 'bytes') == '80' and val(r, 'types') == ('SIMPLE' if o <= 2**31 - 1 else 'FACTORED'), r)
for lab, o in (('single offset=MAX+1', MAX + 1), ('single offset=Long.MAX_VALUE', 2**63 - 1)):
    r = rd[lab]
    chk('unit: %s throws AssertionError with the limit in the message' % lab, r == 'THROW java.lang.AssertionError: offset %d cannot be greater than %d' % (o, MAX), r)
for lab in ('two offsets {5, MAX+1}', 'three offsets {5, 6, MAX+1}', 'two offsets {5, Long.MAX_VALUE}'):
    r = rd[lab]; n = 2 if lab.startswith('two') else 3
    chk('unit: %s does not throw (bypass), %d slots, size %d' % (lab, n, 64 + 16 + 8 * n), r.startswith('OK') and val(r, 'slots') == str(n) and val(r, 'bytes') == str(80 + 8 * n), r)
sizes = [(int(re.search(r'tokens=(\d+)', k).group(1)), val(v, 'bytes'), val(v, 'numBlocks')) for k, v in rd.items() if k.startswith('size control')]
for n, b, nb in sizes:
    exp = 64 + 16 * n if n <= 248 else int(nb) * 4096
    chk('unit: size control %d tokens -> %s bytes (rule: single block 64+16n, else numBlocks x 4096)' % (n, b), int(b) == exp, 'numBlocks %s' % nb)
chk('unit: sizes strictly grow with token count', [int(b) for _, b, _ in sorted(sizes)] == sorted(int(b) for _, b, _ in sizes) and len({b for _, b, _ in sizes}) == len(sizes))
chk('unit: 8 offsets pass and 9 throw the overflow assertion', rd['8 offsets on one token'].startswith('OK') and rd['9 offsets on one token'] == 'THROW java.lang.AssertionError: cannot have more than 8 overflow collisions per leaf')
passing = [rd['single offset=%d' % o] for o in (1, 2**31 - 1, 2**31, MAX - 1, MAX)]
chk('unit: serialized length identical for every passing single offset', len({val(r, 'bytes') for r in passing}) == 1)
# ---- cluster tier
for arm in ('s1', 's4', 's16', 'n1', 'b1', 'h1', 'p1'):
    p = '%s/cluster/%s' % (d, arm)
    if not os.path.isdir(p): continue
    cmd = open(p + '/cmdlog.txt', errors='replace').read()
    if 'GUARD FAILED' in cmd: print('NOTE %s not run (disk guard)' % arm); continue
    sysl = open(p + '/system.log', errors='replace').read()
    chk('cluster %s: finished and left no daemon' % arm, ('== %s end' % arm) in cmd and 'daemons left: 0' in cmd)
    chk('cluster %s: no "cannot be greater than" and no AssertionError in system.log' % arm, 'cannot be greater than' not in sysl and 'AssertionError' not in sysl)
    chk('cluster %s: stress reported no errors' % arm, re.search(r'Total errors\s*:\s*0\b', open(p + '/stress.txt', errors='replace').read()) is not None)
    sz = open(p + '/sizes.txt').read()
    dat = int(re.search(r'\*-Data.db (\d+)', sz).group(1)); si = int(re.search(r'\*SI_\*.db (\d+)', sz).group(1))
    one = re.search(r'SSTable count: (\d+)', open(p + '/tablestats.txt').read())
    chk('cluster %s: one sstable after compaction; SI files %s' % (arm, 'absent' if arm == 'n1' else 'present'), one.group(1) == '1' and ((si == 0) if arm == 'n1' else (si > 0)), 'Data %d SI %d' % (dat, si))
print('SUMMARY selfcheck pass=%d fail=%d' % (ok, fail))
