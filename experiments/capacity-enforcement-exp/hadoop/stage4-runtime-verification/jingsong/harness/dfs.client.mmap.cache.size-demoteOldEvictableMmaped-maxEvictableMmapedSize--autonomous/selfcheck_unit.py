# Checks every IFCHK line of the unit tier against B2f/B2h + A4 (exact match). Usage: python3 -I selfcheck_unit.py ifchk.txt
import re, sys
N = 12; MiB = 1 << 20
def M(s): return min(N, max(s - 1, 0))
rows = {}
for l in open(sys.argv[1]):
    if not l.startswith('IFCHK,rep='): continue
    h = dict(kv.split('=', 1) for kv in l.split(',')[1:7])
    mm = re.search(r'step=(\S+)', l)
    if not mm: continue
    step = mm.group(1)
    v = {k: int(x) for k, x in re.findall(r'\b(evictableMmapped|outstanding|evictable|replicas|blkMaps|blkMappedBytes|blkMapsJvm|demoteNeed|demoteOld|purge)=(\d+)', l)}
    rows.setdefault((h['rep'], h['tag']), {})[step] = v
ok = bad = 0
def chk(name, got, exp):
    global ok, bad
    if got == exp: ok += 1
    else: bad += 1; print('MISMATCH', name, 'got', got, 'expected', exp)
for (rep, tag), st in sorted(rows.items()):
    s = int(re.sub(r'\D', '', tag) or 256) if tag.startswith('S') else 256
    if tag.startswith('S'):
        m = M(s)
        for i in range(N):
            v = st[str(i)]
            chk(f'{rep}/{tag}/step{i}/evictableMmapped', v['evictableMmapped'], min(i, m))
            chk(f'{rep}/{tag}/step{i}/outstanding', v['outstanding'], min(i, m) + 1)
            chk(f'{rep}/{tag}/step{i}/blkMaps', v['blkMaps'], min(i, m) + 1)
            chk(f'{rep}/{tag}/step{i}/blkMappedBytes', v['blkMappedBytes'], (min(i, m) + 1) * MiB)
        for k in ('after-close', 'end'):
            v = st[k]
            for f in ('evictableMmapped', 'outstanding', 'blkMaps'): chk(f'{rep}/{tag}/{k}/{f}', v[f], m)
            chk(f'{rep}/{tag}/{k}/blkMappedBytes', v['blkMappedBytes'], m * MiB)
            chk(f'{rep}/{tag}/{k}/evictable', v['evictable'], N - m)
            chk(f'{rep}/{tag}/{k}/replicas', v['replicas'], N)
            chk(f'{rep}/{tag}/{k}/demoteNeed', v['demoteNeed'], N - m)
            chk(f'{rep}/{tag}/{k}/demoteOld', v['demoteOld'], 0)
            chk(f'{rep}/{tag}/{k}/purge', v['purge'], 0)
    elif tag == 'posctl':
        v = st['after-close']
        for f, e in (('evictableMmapped', 4), ('blkMaps', 4), ('blkMappedBytes', 4 * MiB), ('demoteNeed', 0), ('purge', 8)):
            chk(f'{rep}/{tag}/after-close/{f}', v[f], e)
    elif tag == 'timectl':
        v = st['end']
        for f, e in (('evictableMmapped', 0), ('blkMaps', 0), ('demoteNeed', 0)):
            chk(f'{rep}/{tag}/end/{f}', v[f], e)
        chk(f'{rep}/{tag}/end/demoteOld>=1', v['demoteOld'] >= 1, True)
    elif tag == 'baseline':
        for k, v in st.items():
            if k in ('before', 'cleanup'): continue
            chk(f'{rep}/{tag}/{k}/blkMaps', v['blkMaps'], 0)
            for f in ('demoteNeed', 'demoteOld', 'purge'): chk(f'{rep}/{tag}/{k}/{f}', v[f], 0)
# repeat identity: every reading of rep 1 equals rep 2
for (rep, tag), st in rows.items():
    if rep != '1': continue
    st2 = rows.get(('2', tag))
    for k, v in st.items():
        if k == 'cleanup': continue
        chk(f'rep1==rep2/{tag}/{k}', v, st2.get(k))
print(f'phases={len(rows)} checks ok={ok} mismatches={bad}')
