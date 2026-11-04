#!/usr/bin/env python3
"""Reads $OUT/*.out and *.log of the unit tier (unit-all.sh) and prints the readings table plus EXPECTED lines for the
frozen predictions of B2f / amendment U3. usage: analyze-unit.py <unit dir>"""
import glob, os, re, sys
d = sys.argv[1]
R = {}
for f in sorted(glob.glob(d + '/*.out')):
    lab = os.path.basename(f)[:-4]
    txt = open(f).read()
    m = re.search(r'^RESULT (.*)$', txt, re.M)
    if not m:
        R[lab] = None; continue
    kv = dict(x.split('=', 1) for x in m.group(1).split() if '=' in x)
    sb = []
    lg = d + '/' + lab + '.log'
    if os.path.exists(lg):
        for l in open(lg):
            mm = re.match(r'SBFLUSH dataBlocksCnt=(\d+) tokens=(\d+) treeBytes=(\d+) liveHeap=(\d+)', l)
            if mm: sb.append(tuple(int(x) for x in mm.groups()))
    kv['sb_lines'] = len(sb)
    kv['max_tokens'] = max([s[1] for s in sb], default=0)
    kv['max_treeBytes'] = max([s[2] for s in sb], default=0)
    kv['max_live'] = max([s[3] for s in sb], default=0)
    kv['full_flushes'] = sum(1 for s in sb if s[0] == int(kv['constant']))
    R[lab] = kv
ok = fail = 0
def expect(name, cond, detail):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print('EXPECTED %s: %s  %s' % (name, detail, 'PASS' if cond else 'FAIL'))
print('%-26s %5s %7s %8s %6s %7s %10s %10s %9s %12s' % ('label', 'const', 'n', 'dataBlk', 'super', 'sbLines', 'maxTokens', 'fileBytes', 'maxTreeB', 'maxLiveHeap'))
for lab, kv in R.items():
    if kv is None: print('%-26s NO RESULT' % lab); continue
    print('%-26s %5s %7s %8s %6s %7s %10s %10s %9s %12s' % (lab, kv['constant'], kv['n'], kv['dataBlocks'], kv['superBlocks'], kv['sb_lines'], kv['max_tokens'], kv['fileBytes'], kv['max_treeBytes'], kv['max_live']))
for lab, kv in R.items():
    if kv and kv['mode'] == 'SPARSE':
        expect('%s superBlocks == floor((dataBlocks-1)/const)+1' % lab, kv['formulaMatches'] == 'true', 'got %s expected %s' % (kv['superBlocks'], kv['expectedSuperBlocksFormula']))
        expect('%s patched print count == superBlocks (when patched)' % lab, kv['sb_lines'] in (0, int(kv['superBlocks'])), 'prints %d' % kv['sb_lines'])
        if kv['sb_lines']:
            tpb = int(kv['n']) / int(kv['dataBlocks'])
            expect('%s max tree tokens <= const x terms/block (+1, 2%%)' % lab, kv['max_tokens'] <= int(kv['constant']) * tpb * 1.02 + 1, 'max %d bound %.0f' % (kv['max_tokens'], int(kv['constant']) * tpb * 1.02 + 1))
def g(lab): return R.get(lab)
for n in ('200000',):
    s = {c: g('sp%d-n%s-r1' % (c, n)) for c in (16, 64, 256)}
    if all(s.values()):
        expect('superBlocks 16/64 ratio about 4 (3.5..4.5)', 3.5 <= int(s[16]['superBlocks']) / int(s[64]['superBlocks']) <= 4.5, '%s/%s' % (s[16]['superBlocks'], s[64]['superBlocks']))
        expect('superBlocks 64/256 ratio about 4 (3.5..4.5)', 3.5 <= int(s[64]['superBlocks']) / int(s[256]['superBlocks']) <= 4.5, '%s/%s' % (s[64]['superBlocks'], s[256]['superBlocks']))
        fb = [int(s[c]['fileBytes']) for c in s]
        expect('file bytes within 5 percent across constants', (max(fb) - min(fb)) / min(fb) <= 0.05, 'min %d max %d spread %.2f%%' % (min(fb), max(fb), 100 * (max(fb) - min(fb)) / min(fb)))
        lv = [s[c]['max_live'] for c in s]
        expect('max live heap at a super-block flush within 10 percent across constants', (max(lv) - min(lv)) / min(lv) <= 0.10, 'min %d max %d spread %.2f%%' % (min(lv), max(lv), 100 * (max(lv) - min(lv)) / min(lv)))
        print('INFO max tree tokens by constant:', {c: s[c]['max_tokens'] for c in s}, 'max tree bytes:', {c: s[c]['max_treeBytes'] for c in s})
for c in (16, 64, 256):
    a, b, e = g('sp%d-n50000' % c), g('sp%d-n200000-r1' % c), g('sp%d-n400000' % c)
    if a and b and e:
        expect('const %d: live heap rises with N (50k<200k<400k)' % c, a['max_live'] < b['max_live'] < e['max_live'], '%d < %d < %d' % (a['max_live'], b['max_live'], e['max_live']))
        expect('const %d: file bytes rise with N' % c, int(a['fileBytes']) < int(b['fileBytes']) < int(e['fileBytes']), '%s < %s < %s' % (a['fileBytes'], b['fileBytes'], e['fileBytes']))
for c in (16, 64, 256):
    md = {r: (g('sp%d-n200000-r%d' % (c, r)) or {}).get('md5') for r in (1, 2, 3)}
    expect('const %d: three repeats give one md5' % c, len(set(md.values())) == 1 and None not in md.values(), str(set(md.values())))
a, b, p = g('sp64-n200000-r1'), g('ov64-unpatched-n200000'), g('pristine-n200000')
if a and b and p:
    expect('patched ov64p, unpatched ov64 and pristine build: identical md5', a['md5'] == b['md5'] == p['md5'], '%s %s %s' % (a['md5'], b['md5'], p['md5']))
x = g('pfx64-n200000')
if x: expect('PREFIX mode writes no super blocks', x['superBlocks'] == '-1' and x['sb_lines'] == 0, 'superBlocks field %s, prints %d' % (x['superBlocks'], x['sb_lines']))
x = g('sp64-n2000')
if x: expect('2,000 terms: exactly the one forced super block', x['superBlocks'] == '1', 'superBlocks %s dataBlocks %s' % (x['superBlocks'], x['dataBlocks']))
for lab in ('sp64-n200000-xmx2g', 'sp64-n200000-xmx64m'):
    x = g(lab)
    print('INFO %s: %s' % (lab, 'no RESULT (see its .log)' if x is None else 'superBlocks %s maxLive %d' % (x['superBlocks'], x['max_live'])))
print('SUMMARY expectations pass=%d fail=%d' % (ok, fail))
