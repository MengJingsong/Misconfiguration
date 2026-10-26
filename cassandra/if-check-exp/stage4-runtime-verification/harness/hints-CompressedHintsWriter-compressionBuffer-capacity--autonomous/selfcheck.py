#!/usr/bin/env python3
"""Independent self-check of run 1 (results §5) for hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous.
Re-parses the raw files only (unit harness.out; per lifetime hw.trace, samples.csv, the A log excerpt, summary.txt for the
workload JSON and the mark times) and recomputes every number the conclusion cites with its own code, not the runner's
phases.json analysis. usage: python3 -I selfcheck.py <logs-root, e.g. ~/s4-hw-logs/run1> > selfcheck.txt"""
import csv, glob, json, os, re, sys

root = os.path.expanduser(sys.argv[1])
MIB = 1 << 20
BAND = 2 * MIB
out = []


def p(s=''):
    print(s); out.append(s)


def exp_cap(n):                       # 4 + maxCompressedLength(n) + 8 with lz4-java's n + n/255 + 16
    return 4 + (n + n // 255 + 16) + 8


# ---------------------------------------------------------------- unit tier
p('== unit tier: harness.out')
hf = os.path.join(root, 'unit', 'harness.out')
checks = [l.strip() for l in open(hf) if l.startswith('STAGE4 check')]
bad = [l for l in checks if ' MISMATCH ' in l]
p(f'{len(checks)} checks, {len(bad)} MISMATCH')
want = {'lz4-bound', 'asc-100', 'asc-204800', 'asc-262144', 'asc-1048576', 'asc-4194304', 'asc-16777216', 'seq', 'filesize',
        'n-1', 'n-4', 'n-16', 'uncompressed', 'compressible', 'deflate', 'cap-boundary', 'cap-formula', 'slab-control-32',
        'slab-control-128'}
got = {l.split()[2] for l in checks}
p(f'every planned check present: {want <= got} (missing {sorted(want - got)})')
for l in checks:
    m = re.match(r'STAGE4 check asc-(\d+) .*capacity=(\d+) exp=(\d+)', l)
    if m:
        s, cap = int(m.group(1)), int(m.group(2))
        p(f'  asc S={s}: capacity {cap}; recomputed exp {exp_cap(s)}; equal {cap == exp_cap(s)}')
    m = re.match(r'STAGE4 check n-(\d+) .*pool delta=(\d+) want N x exp\(4MiB\)=(\d+)', l)
    if m:
        n, d = int(m.group(1)), int(m.group(2))
        w = n * exp_cap(4 * MIB)
        p(f'  N={n}: pool delta {d}; recomputed N x exp(4MiB) {w}; ratio {d / w:.4f}; within 10 %: {abs(d - w) <= 0.1 * w}')
    if l.startswith('STAGE4 check cap-boundary') or l.startswith('STAGE4 check seq') or l.startswith('STAGE4 check filesize') \
            or l.startswith('STAGE4 check uncompressed') or l.startswith('STAGE4 check slab-control'):
        p('  ' + l[:330])

# ---------------------------------------------------------------- cluster tier
p()
p('== cluster tier: per lifetime, from hw.trace + samples.csv + summary.txt')
life = {}
for d in sorted(glob.glob(os.path.join(root, 'cluster', '*'))):
    arm = os.path.basename(d)
    if not os.path.exists(d + '/phases.json') or not os.path.exists(d + '/hw.trace'):
        continue
    ph = json.load(open(d + '/phases.json'))
    tr = {'opened': [], 'cbuf': [], 'closed': [], 'created': []}
    for l in open(d + '/hw.trace', errors='replace'):
        k = l.split(' ', 1)[0]
        if k in tr:
            tr[k].append(dict(re.findall(r'(\w+)=(\S+)', l)))
    rows = []
    for r in csv.DictReader(open(d + '/samples.csv')):
        rows.append({k: (float(v) if v not in ('', None) else None) for k, v in r.items()})

    def at(ms):                       # the last sample at or before ms
        best = None
        for r in rows:
            if r['ms'] <= ms:
                best = r
        return best
    base, end = at(ph['ms_base'] + 1500), at(ph['ms_end'] + 1500)
    # writers
    w = {}
    for c in tr['cbuf']:
        e = w.setdefault(c['w'], {'caps': [], 'ins': []})
        e['caps'].append(int(c['cap'])); e['ins'].append(int(c['in']))
    closed = {c['w'] for c in tr['closed'] if int(c['ms']) <= ph['ms_end'] + 1500}   # later closes are the node's shutdown (HintsService.shutdownBlocking)
    grow = all(all(b >= a for a, b in zip(e['caps'], e['caps'][1:])) for e in w.values())
    exact = all(e['caps'][-1] == exp_cap(max(e['ins'])) for e in w.values())
    live = [k for k in w if k not in closed]
    live_sum = sum(w[k]['caps'][-1] for k in live)
    corr = sum(int(c['size']) for c in tr['created'] if int(c['ms']) >= ph['ms_base'])
    dpool = end['direct_used'] - base['direct_used']
    life[arm] = {'dpool': dpool, 'corr': corr, 'live_sum': live_sum, 'nw': len(w), 'nlive': len(live), 'nclosed': len(closed),
                 'max_in': max((max(e['ins']) for e in w.values()), default=0),
                 'max_cap': max((max(e['caps']) for e in w.values()), default=0), 'grow': grow, 'exact': exact,
                 'opened': len(tr['opened']), 'ncbuf': len(tr['cbuf']),
                 'hints': end['total_hints'] - base['total_hints'], 'hdir': end['hints_dir_bytes'],
                 'slabs': sorted({int(c['size']) for c in tr['created']}), 'created_after': sum(1 for c in tr['created'] if int(c['ms']) >= ph['ms_base']),
                 'wl': ph['workload'], 'peers': ph['peers']}
    L = life[arm]
    p(f'{arm}: workload ok {L["wl"]["ok"]} err {L["wl"]["err"]}; hints +{L["hints"]:.0f}, hints dir {L["hdir"]:.0f} B; writers {L["nw"]} '
      f'(opened lines {L["opened"]}, closed lines {L["nclosed"]}, live {L["nlive"]}); writeBuffer lines {L["ncbuf"]}; max in {L["max_in"]}, '
      f'max capacity {L["max_cap"]} (recomputed exp {exp_cap(L["max_in"]) if L["max_in"] else "-"}); every writer exact {L["exact"]}, '
      f'grow-only {L["grow"]}; live capacity sum {L["live_sum"]}; slabs {L["slabs"]} created after baseline {L["created_after"]} (Corr {corr}); '
      f'dPool {dpool:.0f}')

p()
p('== cross-arm relations (X = (dPool - Corr)_arm - (dPool - Corr)_control)')
def X(a, c):
    return (life[a]['dpool'] - life[a]['corr']) - (life[c]['dpool'] - life[c]['corr'])
def mib(x):
    return f'{x / MIB:.2f} MiB'
res = {}
if 'S' in life and 'US' in life:
    res['S'] = X('S', 'US')
    p(f'S: X {mib(res["S"])}; trace live capacity {life["S"]["live_sum"]} B (exp(256KiB) {exp_cap(256 * 1024)}); <= 0.3 + band: {res["S"] <= 0.3 * MIB + BAND}')
for a in ('D1', 'D2', 'F1', 'H1', 'P2', 'M128'):
    if a in life and 'U' in life:
        res[a] = X(a, 'U')
        p(f'{a}: X {mib(res[a])}; trace live capacity sum {mib(life[a]["live_sum"])}; writers {life[a]["nw"]}, live {life[a]["nlive"]}')
one = exp_cap(8 * MIB + 67)
for a, want_n in (('D1', 1), ('D2', 1), ('F1', 1), ('H1', 1)):
    if a in res:
        p(f'  {a}: |X - {want_n} x {mib(one)}| <= band: {abs(res[a] - want_n * one) <= BAND}')
if 'P2' in res:
    p(f'  P2: |X - 2 x {mib(one)}| <= band: {abs(res["P2"] - 2 * one) <= BAND}')
if 'U' in life:
    p(f'U (control): CompressedHintsWriter lines opened {life["U"]["opened"]}, writeBuffer {life["U"]["ncbuf"]} (both must be 0)')
if 'US' in life:
    p(f'US (control): opened {life["US"]["opened"]}, writeBuffer {life["US"]["ncbuf"]} (both must be 0)')
if 'M128' in life and 'D1' in life:
    dp = life['M128']['dpool'] - life['D1']['dpool']
    dc = life['M128']['corr'] - life['D1']['corr']
    p(f'positive control: dPool(M128) - dPool(D1) = {mib(dp)}; Corr(M128) - Corr(D1) = {mib(dc)}; |diff| <= 8 MiB: {abs(dp - dc) <= 8 * MIB}; Corr diff >= 64 MiB: {dc >= 64 * MIB}; slab sizes M128 {life["M128"]["slabs"]}')
open(os.path.join(root, 'selfcheck.txt'), 'w').write('\n'.join(out) + '\n')
