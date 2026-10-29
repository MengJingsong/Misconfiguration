#!/usr/bin/env python3
"""Independent re-parse of run 1's raw files (the unit .out files and the cluster snaps.jsonl / samples.csv / stdout.txt),
checking each claim of the conclusion against B2f/B3f. usage: selfcheck.py <run1 dir>. Prints PASS/FAIL lines."""
import json, os, re, sys
R = sys.argv[1]; ok = bad = 0
def chk(name, cond, detail=''):
    global ok, bad
    if cond: ok += 1
    else: bad += 1
    print(('PASS ' if cond else 'FAIL ') + name + (' | ' + detail if detail else ''))
def kv(line):
    return dict(re.findall(r'(\w+)=(\[[^\]]*\]|\S+)', line))
# ---- unit ----
U = {}
for arm in ('R1024', 'R256'):
    txt = open(f'{R}/unit/{arm}.out').read()
    chk(f'{arm}: constant line', ('1 * 1024 * 1024' if arm == 'R1024' else '256 * 1024') in txt.split('\n')[0], txt.split('\n')[0])
    chk(f'{arm}: every JVM exited 0', txt.count('== rc 0') == 33 and '== rc' in txt and txt.count('== rc') == 33, f"rc0={txt.count('== rc 0')} total={txt.count('== rc')}")
    cur = None; reps = {}
    for l in txt.split('\n'):
        m = re.match(r'== %s (.*?) 20' % arm, l)
        if m: cur = m.group(1)
        if l.startswith('READ '):
            reps.setdefault(cur, []).append(l)
    U[arm] = reps
    for cs, lines in reps.items():
        pass
def one(arm, cs, pre):
    ls = [l for l in U[arm][cs] if l.startswith('READ ' + pre)]
    return [kv(l) for l in ls]
for arm, maxcap in (('R1024', 1048576), ('R256', 262144)):
    c1 = one(arm, 'C1', 'C1 owns')
    chk(f'{arm} C1 x3: owns=used=1280000, capMax={maxcap}, capTotal>owns', len(c1) == 3 and all(int(d['owns']) == int(d['used']) == 1280000 and int(d['capMax']) == maxcap and int(d['capTotal']) > 1280000 for d in c1), str([(d['owns'], d['capMax'], d['capTotal']) for d in c1]))
    c2 = one(arm, 'C2', 'C2 owns')
    chk(f'{arm} C2 x3: owns=limit=10000, capTotal=24576>L', len(c2) == 3 and all(int(d['owns']) == 10000 == int(d['limit']) and int(d['capTotal']) == 24576 for d in c2))
    chk(f'{arm} C2 x3: tryAllocate(1) false', sum('tryAllocate1=false' in l for l in U[arm]['C2']) == 3)
    for size, cap in ((102400, min(524288, maxcap)), (131072, min(1048576, maxcap)), (131073, 131073), (4194304, 4194304)):
        d = one(arm, f'C3 {size}', 'C3 size')
        chk(f'{arm} C3 {size} x3: owns={size}, one region cap={cap}', len(d) == 3 and all(int(x['owns']) == size and int(x['capMax']) == cap and int(x['regions']) == 1 for x in d), str([(x['owns'], x['capMax']) for x in d]))
    for A in (1, 10, 100):
        d = one(arm, f'C4 {A}', 'C4 A')
        chk(f'{arm} C4 A={A} x3: owns={6400*A}, capTotal={8192*A}, slack={1792*A}', len(d) == 3 and all(int(x['owns']) == 6400 * A and int(x['capTotal']) == 8192 * A and int(x['slack']) == 1792 * A for x in d))
    z = one(arm, 'Z', 'Z owns')
    chk(f'{arm} Z x3: zero slack', len(z) == 3 and all(int(x['slack']) == 0 and int(x['owns']) == 8192 for x in z))
    p = U[arm]['P1']
    chk(f'{arm} P1 x3: 32768 calls then writer WAITING, extra call not returned', sum('filled calls=32768' in l for l in p) == 3 and sum('writerState=WAITING extraCallReturned=false calls=32768' in l for l in p) == 3)
    chk(f'{arm} P1 x3: after release writer TERMINATED, extra returned', sum('afterRelease writerState=TERMINATED extraCallReturned=true' in l for l in p) == 3)
    pb = one(arm, 'P1', 'P1 beforeRelease')
    chk(f'{arm} P1 x3: used=limit=2097152 while capTotal>limit', all(int(x['used']) == int(x['limit']) == 2097152 and int(x['capTotal']) > 2097152 for x in pb))
# cross-arm dose-response
def own(arm): return {cs: [kv(l)['owns'] for l in ls if re.match(r'READ (C1|C2|C3|C4|Z) .*owns=', l)] for cs, ls in U[arm].items() if cs not in ('P1',)}
chk('owns identical between R1024 and R256 for every case', own('R1024') == own('R256'))
c1a = one('R1024', 'C1', 'C1 owns')[0]; c1b = one('R256', 'C1', 'C1 owns')[0]
chk('capMax follows the constant (1048576 vs 262144) while owns unchanged', c1a['capMax'] == '1048576' and c1b['capMax'] == '262144' and c1a['owns'] == c1b['owns'])
# ---- cluster ----
C = {}
cdir = f'{R}/cluster'
if os.path.isdir(cdir):
    for arm in sorted(os.listdir(cdir)):
        f = f'{cdir}/{arm}/snaps.jsonl'
        if os.path.exists(f):
            C[arm] = {j['snap']: j for j in map(json.loads, open(f))}
    def dl(arm, k, a='end', b='base'): return C[arm][a][k] - C[arm][b][k]
    def flushes(arm):   # flushes of ks.* tables, from the raw system.log (the JMX switch counter in snaps.jsonl was read with the wrong attribute and is not used)
        L = open(f'{cdir}/{arm}/system.log', errors='replace').read().splitlines()
        return sum(1 for l in L if 'Enqueuing flush of ks.' in l), sum(1 for l in L if 'Enqueuing flush of ks.' in l and 'MEMTABLE_LIMIT' in l)
    for arm in C:
        led = sum(int(l.split()[1]) for l in open(f'{cdir}/{arm}/stdout.txt', errors='replace') if l.startswith('REGION '))
        chk(f'{arm}: last snapshot ledger equals sum of REGION lines in stdout.txt up to then (<=)', led >= list(C[arm].values())[-1]['ledger_bytes'], f'{led}')
    for arm in ('big1', 'big50', 'big150'):
        if arm in C:
            print(arm, 'dCharged_ks', dl(arm, 'charged_ks'), 'dCharged_all', dl(arm, 'charged_all'), 'dLedger', dl(arm, 'ledger_bytes'), 'dVmData_kB', dl(arm, 'VmData_kB'), 'dRssAnon_kB', dl(arm, 'RssAnon_kB'), 'ks flushes', flushes(arm))
            chk(f'{arm}: no flush of any ks table in system.log', flushes(arm)[0] == 0, str(flushes(arm)))
    if all(a in C for a in ('big1', 'big50', 'big150')):
        sl = [dl(a, 'ledger_bytes') - dl(a, 'charged_all') for a in ('big1', 'big50', 'big150')]
        print('slack (ledger-charged) T=1,50,150:', sl)
        chk('big: ledger-charged slack positive and increasing with T', 0 < sl[0] < sl[1] < sl[2])
        ch = [dl(a, 'charged_ks') for a in ('big1', 'big50', 'big150')]
        chk('big: charged grows ~linearly with T (50x and 150x within 20%)', abs(ch[1] / ch[0] / 50 - 1) < .2 and abs(ch[2] / ch[0] / 150 - 1) < .2, str(ch))
    if 'big150' in C and 'blob' in C['big150']:
        b = C['big150']
        print('blob: dCharged', b['blob']['charged_all'] - b['end']['charged_all'], 'dLedger', b['blob']['ledger_bytes'] - b['end']['ledger_bytes'], 'ledger_max', b['blob']['ledger_max'], 'dVmData_kB', b['blob']['VmData_kB'] - b['end']['VmData_kB'])
        chk('blob: ledger_max >= 4194304 (oversize region > 1 MiB)', b['blob']['ledger_max'] >= 4194304)
    if 'small150' in C:
        s = [list(map(int, l.split(','))) for l in open(f'{cdir}/small150/samples.csv') if re.match(r'^\d+,\d+,\d+$', l.strip())]
        mx = max(x[1] for x in s)
        print('small150 samples', len(s), 'max charged_all', mx, 'ks flushes (total, MEMTABLE_LIMIT)', flushes('small150'))
        chk('small150: flushes of ks tables with reason MEMTABLE_LIMIT > 0', flushes('small150')[1] > 0)
        chk('small150: max sampled charged <= 32 MiB + 8 MiB', mx <= 40 * 2**20, str(mx))
        if 'big150' in C:
            chk('small150: max charged < big150 end charged / 2', mx < dl('big150', 'charged_all') / 2)
    if 'heap150' in C:
        print('heap150 dCharged_all', dl('heap150', 'charged_all'), 'dLedger', dl('heap150', 'ledger_bytes'))
        chk('heap150: ledger delta 0 (no NativeAllocator regions under heap_buffers)', dl('heap150', 'ledger_bytes') == 0)
    if 'idle' in C:
        print('idle drift dVmData_kB', dl('idle', 'VmData_kB'), 'dRssAnon_kB', dl('idle', 'RssAnon_kB'), 'dLedger', dl('idle', 'ledger_bytes'))
print(f'{ok} PASS, {bad} FAIL'); sys.exit(1 if bad else 0)
