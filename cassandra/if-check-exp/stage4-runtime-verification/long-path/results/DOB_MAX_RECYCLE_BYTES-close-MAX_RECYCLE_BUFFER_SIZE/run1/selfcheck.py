#!/usr/bin/env python3
"""Independent self-check of run 1, DOB_MAX_RECYCLE_BYTES (results §5). For each label folder of the run (default the node's
~/stage4-logs/dob/run1) it re-parses the raw ledger.txt and hold.txt with its own parser (not the harness's ledger.py), takes
from result.json only the raw readings (JMX MemoryUsed/Count, histogram, the ledger byte offsets of each reading), and
recomputes P, V, C = 2(V+P), the branch, the capacities, ΔR, retention, the pool comparison and the cross-label relations
from the case's constants. Also the unit tier's STAGE4 lines (unit/*.out).
usage: selfcheck.py [<run1 folder>]    exit 1 on any failure."""
import json, os, re, sys

D = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/stage4-logs/dob/run1')
TAU = 262144
SIZES = {'B1': 100000, 'B2': 450000, 'B3': 1900000, 'BN': 450000}
ok_n = bad_n = 0
info = []


def chk(name, cond, detail=''):
    global ok_n, bad_n
    ok_n += bool(cond); bad_n += (not cond)
    print(f'{"ok  " if cond else "FAIL"} {name} {detail}'[:300])


def events(path, a=0, b=None):
    import gzip
    if not os.path.exists(path) and os.path.exists(path + '.gz'):
        raw = gzip.open(path + '.gz').read()          # the repository keeps the ledgers compressed; offsets are uncompressed
    else:
        raw = open(path, 'rb').read()
    data = raw[a:None if b is None else b].decode(errors='replace')
    out = []
    for l in data.splitlines():
        m = re.match(r'(new|alloc|grow-free|close|kept|replaced|closed) (.*)', l)
        if m:
            kv = dict(re.findall(r'(\w+)=(\S+)', m[2]))
            kv['k'] = m[1]
            out.append(kv)
    return out


def live(evs, state=None):
    st = dict(state or {})
    for e in evs:
        d = e['dob']
        if e['k'] == 'alloc':
            st[d] = st.get(d, 0) + int(e['size'])
        elif e['k'] in ('grow-free', 'replaced'):
            st[d] = st.get(d, 0) - int(e['cap'])
    return st


res = {}
for lab in sorted(os.listdir(D)):
    if not os.path.isdir(f'{D}/{lab}'):
        continue
    m = re.match(r'^L(262144|default|4194304|2147483647|64)-(B1|B2|B3|BA|BB|BN)(-heap)?$', lab)
    if not m or not os.path.exists(f'{D}/{lab}/result.json'):
        continue
    Ls, b, heap = m[1], m[2], bool(m[3])
    L = 1048576 if Ls == 'default' else int(Ls)
    N = 4 if b == 'BN' else 16
    rj = json.load(open(f'{D}/{lab}/result.json'))
    LG, HD = f'{D}/{lab}/ledger.txt', f'{D}/{lab}/hold.txt'
    held = [dict(re.findall(r'(\w+)=(\S+)', l)) for l in open(HD) if l.startswith('held')]
    # calibration: the first held line is the key -1 write
    t_cal = held[0]['tid']
    allev = events(LG)
    cal = [e for e in allev if e['k'] == 'close' and e['tid'] == t_cal and int(e['limit']) >= 20000]
    S0 = int(cal[0]['limit']); P = S0 - 20001
    chk(f'{lab}: P = S0 - 20001 = {P} in [20, 127], L= on the close line = {cal[0]["L"]}', 20 <= P <= 127 and int(cal[0]['L']) == L)
    V = SIZES[b] if b in SIZES else L // 2 - P + (1 if b == 'BB' else 0)
    C = 2 * (V + P); keep = C <= L
    bo, ao = rj['before']['ledger_off'], rj['after']['ledger_off']
    st0 = live(events(LG, 0, bo)); win = events(LG, bo, ao); st1 = live(win, st0)
    bt = sorted({h['tid'] for h in held[1:]} - set(), key=int)
    batch_held = held[-N:]
    tids = sorted({h['tid'] for h in batch_held}, key=int)
    chk(f'{lab}: the last {N} held lines are on {N} distinct threads', len(tids) == N)
    per = {}
    for t in tids:
        ev = [e for e in win if e['tid'] == t]
        dobs = {e['dob'] for e in ev}
        d = next(iter(dobs)) if len(dobs) == 1 else None
        closes = [(int(e['cap']), int(e['limit'])) for e in ev if e['k'] == 'close']
        br = [e['k'] for e in ev if e['k'] in ('kept', 'replaced')]
        al = [int(e['size']) for e in ev if e['k'] == 'alloc']
        new = any(e['k'] == 'new' for e in ev)
        x = st0.get(d, 0); pk = x
        for e in ev:
            if e['k'] == 'alloc':
                x += int(e['size'])
            elif e['k'] in ('grow-free', 'replaced'):
                x -= int(e['cap'])
            pk = max(pk, x)
        per[t] = dict(d=d, closes=closes, br=br, al=al, new=new, init=st0.get(d, 0), fin=st1.get(d, 0), peak=pk)
    fin = C if keep else 128
    chk(f'{lab}: every batch close shows cap {C} = 2(V+P) and limit {V + P + 1} = S', all(per[t]['closes'] == [(C, V + P + 1)] for t in tids))
    chk(f'{lab}: every branch {"kept" if keep else "replaced"} (C {"<=" if keep else ">"} L = {L})', all(per[t]['br'] == ['kept' if keep else 'replaced'] for t in tids))
    chk(f'{lab}: allocations V+P = {V + P}, then {C} (+128 at creation / replacement)',
        all(per[t]['al'] == ([128] if per[t]['new'] else []) + [V + P, C] + ([] if keep else [128]) for t in tids))
    chk(f'{lab}: each thread ends at {fin}; retained {N} x {fin} = {N * fin}', all(per[t]['fin'] == fin for t in tids))
    chk(f'{lab}: transient peak 3(V+P) = {3 * (V + P)} on every thread', all(per[t]['peak'] == 3 * (V + P) for t in tids))
    R0, R1 = sum(st0.values()), sum(st1.values())
    dR = R1 - R0
    others = {d: st1.get(d, 0) - st0.get(d, 0) for d in set(st0) | set(st1) if d not in {per[t]['d'] for t in tids} and st1.get(d, 0) != st0.get(d, 0)}
    chk(f'{lab}: ΔR = {dR} = Σ(final − initial) over the batch threads; no other instance changed', dR == sum(per[t]['fin'] - per[t]['init'] for t in tids) and not others, str(others)[:80])
    newi = sum(1 for e in win if e['k'] == 'new')
    dMU = rj['after']['MemoryUsed'] - rj['before']['MemoryUsed']; dCt = rj['after']['Count'] - rj['before']['Count']
    if heap:
        chk(f'{lab}: arm H, every allocation direct=false; |ΔMemoryUsed| = {abs(dMU)} <= τ', all(e['direct'] == 'false' for e in win if e['k'] == 'alloc') and abs(dMU) <= TAU)
    else:
        chk(f'{lab}: |ΔMemoryUsed − ΔR| = {abs(dMU - dR)} <= τ', abs(dMU - dR) <= TAU)
        info.append((lab, dCt, newi, dMU - dR))
        chk(f'{lab}: ΔCount = new scratch instances (§9a sub-prediction): {dCt} vs {newi}', dCt == newi)
    if rj.get('persist'):
        chk(f'{lab}: persistence, MemoryUsed 70 s later within τ ({rj["persist"]["MemoryUsed"] - rj["after"]["MemoryUsed"]})', abs(rj['persist']['MemoryUsed'] - rj['after']['MemoryUsed']) <= TAU)
    if Ls == '64':
        k = [e for e in allev if e['k'] == 'kept']
        chk(f'{lab}: L = 64, no kept line anywhere in the lifetime ({sum(1 for e in allev if e["k"] == "replaced")} replaced)', not k)
    res[lab] = dict(L=L, b=b, heap=heap, C=C, keep=keep, retained=sum(per[t]['fin'] for t in tids), peaks={per[t]['peak'] for t in tids}, dMU=dMU,
                    B=rj['after'].get('live_B_bytes'))

# ---------------- cross-label
want = {('B1', '262144'): 1, ('B1', 'default'): 1, ('B1', '4194304'): 1, ('B2', '262144'): 0, ('B2', 'default'): 1, ('B2', '4194304'): 1,
        ('B3', '262144'): 0, ('B3', 'default'): 0, ('B3', '4194304'): 1}
for (b, Ls), k in want.items():
    r = res.get(f'L{Ls}-{b}')
    chk(f'staircase {b} at L={Ls}: {"kept, 16C" if k else "replaced, 2,048 B"}', r and r['keep'] == bool(k) and r['retained'] == (16 * r['C'] if k else 2048), r and r['retained'])
for Ls in ('262144', 'default', '4194304'):
    a, bb = res.get(f'L{Ls}-BA'), res.get(f'L{Ls}-BB')
    chk(f'boundary at L={Ls}: BA C = L kept (16 L), BB C = L + 2 replaced (2,048)', a and bb and a['C'] == a['L'] and a['retained'] == 16 * a['L'] and bb['C'] == bb['L'] + 2 and bb['retained'] == 2048)
for b in ('B1', 'B2', 'B3'):
    pk = [res[f'L{Ls}-{b}']['peaks'] for Ls in ('262144', 'default', '4194304') if f'L{Ls}-{b}' in res]
    chk(f'{b}: in-use peak identical at the three values ({pk})', len(pk) == 3 and all(p == pk[0] and len(p) == 1 for p in pk))
b2, bn = res.get('Ldefault-B2'), res.get('Ldefault-BN')
chk('×N: BN retains a quarter of B2', b2 and bn and 4 * bn['retained'] == b2['retained'])
chk('×N: ΔMU(B2) − 4 ΔMU(BN) within 4τ', b2 and bn and abs(b2['dMU'] - 4 * bn['dMU']) <= 4 * TAU, b2 and bn and b2['dMU'] - 4 * bn['dMU'])
c = res.get('L2147483647-B3')
chk('scenario C, L = 2^31 − 1, B3 kept, 16C retained', c and c['keep'] and c['retained'] == 16 * c['C'])
c64 = res.get('L64-B1')
chk('scenario C, L = 64, B1 replaced, 2,048 B retained', c64 and not c64['keep'] and c64['retained'] == 2048)
for b in ('B2', 'B3'):
    h, d = res.get(f'Ldefault-{b}-heap'), res.get(f'Ldefault-{b}')
    want_d = 16 * h['C'] if (h and b == 'B2') else 0
    diff = (h['B'] - d['B']) if (h and d and h['B'] and d['B']) else None
    chk(f'arm H {b}: live [B above the direct-mode start by {want_d} ± 2 MB (got {diff})', diff is not None and abs(diff - want_d) <= 2_000_000)
for lab, dCt, newi, gap in info:
    print(f'info {lab}: ΔCount {dCt} vs new scratch instances {newi} (extra {dCt - newi}); ΔMU − ΔR = {gap}')

# ---------------- unit tier
U = f'{D}/unit'
tot = mm = 0
for f in sorted(os.listdir(U)):
    if f.endswith('.out'):
        c = [l for l in open(f'{U}/{f}') if l.startswith('STAGE4 check')]
        tot += len(c); mm += sum('MISMATCH' in l for l in c)
chk(f'unit: {tot} harness checks, 0 MISMATCH', tot == 205 and mm == 0, f'{tot}/{mm}')
print(f'TOTAL ok {ok_n} fail {bad_n}')
sys.exit(1 if bad_n else 0)
