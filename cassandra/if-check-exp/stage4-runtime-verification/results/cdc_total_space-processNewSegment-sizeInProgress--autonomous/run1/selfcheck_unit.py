#!/usr/bin/env python3 -I
"""Independent re-parse of the committed unit-tier excerpts (unit/<cell>/readings-excerpt.txt, cdc-verdict.txt, freed-up.txt)
against every sub-prediction of the frozen B2f / B2g. Prints PASS / MISS per sub-prediction. usage: selfcheck_unit.py <run1 dir>"""
import os, re, sys
MIB = 1 << 20; S = 32 * MIB
base = os.path.join(sys.argv[1], 'unit')
def kv(line): return dict(re.findall(r'(\w+)=("[^"]*"|\S+)', line))
cells = {}
for name in sorted(os.listdir(base)):
    d = os.path.join(base, name)
    if not os.path.isdir(d): continue
    r = {'name': name}
    for line in open(d + '/readings-excerpt.txt'):
        for tag in ('config', 'idle', 'writesDone', 'afterFlush2s', 'final', 'sampler', 'EXCERPT'):
            if (' ' + tag + ' ') in line or line.startswith(tag + ' '): r[tag] = kv(line)
        if ' walkSum ' in line: r['walk'] = int(line.split()[-1])
    tr = open(d + '/cdc-verdict.txt').read().splitlines()
    r['created'] = sum(1 for l in tr if l.startswith('pre '))
    r['forbidden'] = sum(1 for l in tr if l.startswith('post') and 'FORBIDDEN' in l)
    r['deleteOld'] = [int(re.search(r'remaining=(\d+)', l).group(1)) for l in tr if l.startswith('deleteOld')]
    fu = d + '/freed-up.txt'
    r['freed'] = [int(x) for x in re.findall(r'Total on-disk CDC size: (\d+)', open(fu).read())] if os.path.exists(fu) else []
    r['acc'] = int(r['writesDone']['accepted']); r['rej'] = int(r['writesDone']['rejected'])
    r['peak'] = int(r['sampler']['peakBytes']); r['peakLinkBytes'] = int(r['sampler']['peakLinkBytes'])
    r['finalLinkBytes'] = int(r['final']['linkBytes']); r['finalLinks'] = int(r['final']['links'])
    r['flushLinks'] = int(r['afterFlush2s']['links']); r['n'] = int(r['config']['totalSpaceMiB']) * MIB
    r['mode'] = r['config']['mode']; r['table'] = r['config']['table']
    r['rowmax'] = int(r['EXCERPT']['rowMaxDuBytes'])
    r['trk'] = int(r['final']['tracker']); r['du'] = int(r['final']['duBytes'])
    cells[name] = r
out = []
def chk(ok, text): out.append(('PASS ' if ok else 'MISS ') + text)
IDX_ALLOWANCE = 4096  # index files (_cdc.idx, 18 B each) are counted in the byte total; allow 4 KiB over a stated segment bound
def mx(c): return max(c['peak'], c['rowmax']) - IDX_ALLOWANCE
for n in (96, 192):
    for rep in (1, 2, 3):
        c = cells['nb%d-r%d' % (n, rep)]
        chk(mx(c) <= n * MIB + 3 * S, 'B2f NB N=%d r%d: max cdc_raw bytes %.1f MiB <= N+3S = %d' % (n, rep, mx(c) / MIB, n + 96))
        chk(c['finalLinkBytes'] <= n * MIB + S, 'B2f NB N=%d r%d: final link bytes %.1f MiB <= about N+S = %d' % (n, rep, c['finalLinkBytes'] / MIB, n + 32))
        chk(len(c['freed']) >= 1 and min(c['freed']) <= n * MIB + S, 'B2f NB N=%d r%d: DEBUG "Freed up" lines %d, smallest remaining %.1f MiB <= N+S' % (n, rep, len(c['freed']), min(c['freed'] or [0]) / MIB))
        chk(len(c['deleteOld']) >= 1 and c['rej'] == 0 and c['forbidden'] == 0, 'B2g NB N=%d r%d: cap reached (deleteOld passes %d), no rejection' % (n, rep, len(c['deleteOld'])))
        chk(abs(c['trk'] - c['du']) <= S, 'B2g tracker vs walk NB N=%d r%d: gap %d B <= S' % (n, rep, c['trk'] - c['du']))
for rep in (1, 2, 3):
    d = max(mx(cells['nb192-r%d' % rep]), 0) - max(mx(cells['nb96-r%d' % rep]), 0)
    chk(abs(d - 96 * MIB) <= S, 'B2f NB scaling r%d: max(192) - max(96) = %.1f MiB, 96 +- 32' % (rep, d / MIB))
for n in (96, 192):
    for rep in (1, 2, 3):
        c = cells['b%d-r%d' % (n, rep)]
        chk(c['rej'] > 0 and c['forbidden'] >= 1, 'B2f B N=%d r%d: CDCWriteException raised (%d rejected), FORBIDDEN segments %d' % (n, rep, c['rej'], c['forbidden']))
        chk(mx(c) <= n * MIB + S, 'B2f B N=%d r%d: max cdc_raw bytes %.1f MiB <= N+S = %d' % (n, rep, mx(c) / MIB, n + 32))
        chk(len(c['deleteOld']) == 0, 'B2f B N=%d r%d: no deleteOld pass (nothing trimmed)' % (n, rep))
        k = n // 32
        chk(c['finalLinkBytes'] in ((k - 1) * S, k * S), 'B2f accounting B N=%d r%d: final link bytes %.0f MiB in {(k-1)S, kS} = {%d, %d}' % (n, rep, c['finalLinkBytes'] / MIB, (k - 1) * 32, k * 32))
        chk(2 * (k - 1) <= c['acc'] <= 2 * k, 'B2f accounting B N=%d r%d: accepted %d in [%d, %d]' % (n, rep, c['acc'], 2 * (k - 1), 2 * k))
        chk(abs(c['trk'] - c['du']) <= S, 'B2g tracker vs walk B N=%d r%d: gap %d B <= S' % (n, rep, c['trk'] - c['du']))
for mode in ('b', 'nb'):
    for rep in (1, 2, 3):
        c = cells['%s1024-r%d' % (mode, rep)]
        chk(len(c['deleteOld']) == 0 and c['rej'] == 0 and c['forbidden'] == 0 and not c['freed'], 'B2f control %s N=1024 r%d: no trim, no exception' % (mode, rep))
        chk(c['finalLinkBytes'] >= 12 * S and mx(c) > 192 * MIB, 'B2f control %s N=1024 r%d: cdc_raw %.1f MiB >= 384 and > 192' % (mode, rep, c['finalLinkBytes'] / MIB))
for mode in ('b', 'nb'):
    for rep in (1, 2):
        c = cells['plain-%s96-r%d' % (mode, rep)]
        chk(c['rej'] == 0, 'B2f plain %s r%d: zero rejections (%d)' % (mode, rep, c['rej']))
        chk(c['peakLinkBytes'] <= 96 * MIB + S, 'B2f plain %s r%d: peak link bytes %.1f MiB <= N+S = 128' % (mode, rep, c['peakLinkBytes'] / MIB))
        chk(c['flushLinks'] <= 2, 'B2f plain %s r%d: links after flush %d <= 2' % (mode, rep, c['flushLinks']))
        cd = cells['%s96-r%d' % (mode, rep)]
        chk(cd['finalLinkBytes'] >= 64 * MIB, 'B2f CDC table at N=96 %s r%d keeps final link bytes %.1f MiB >= 64' % (mode, rep, cd['finalLinkBytes'] / MIB))
print('\n'.join(out))
print('TOTAL PASS %d MISS %d' % (sum(l.startswith('PASS') for l in out), sum(l.startswith('MISS') for l in out)))
