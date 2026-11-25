# Checks the cluster-tier probe logs against B3f/B3h + A7. Usage: python3 -I selfcheck_cluster.py <dir with <tag>.log/.ext>
import re, sys, os
D = sys.argv[1]; N = 16; B = 64 << 20; MiB = 1 << 20
def M(s): return min(N, max(s - 1, 0))
ok = bad = 0
def chk(name, got, exp):
    global ok, bad
    if got == exp: ok += 1
    else: bad += 1; print('MISMATCH', name, 'got', got, 'expected', exp)
def parse(tag):
    L = open(os.path.join(D, tag + '.log')).read().split('\n')
    snap = {}; steps = {}; need = old = purge = 0; after = False; old_total = 0; purge_total = 0
    for l in L:
        m = re.match(r'^(before|after-close|end) blkMaps=(\d+) blkMappedBytes=(\d+) VmSize: (\d+) kB RssFile: (\d+) kB', l)
        if m: snap[m.group(1)] = tuple(int(x) for x in m.groups()[1:]); after |= m.group(1) == 'after-close'; continue
        m = re.match(r'^step (\d+) sum=\S+ blkMaps=(\d+) blkMappedBytes=(\d+)', l)
        if m: steps[int(m.group(1))] = (int(m.group(2)), int(m.group(3))); continue
        if 'demoteOldEvictable: demoting' in l:
            if 'because we need more space' in l and not after: need += 1
            if "because it's too old" in l:
                old_total += 1
                if not after: old += 1
        if 'trimEvictionMaps is purging' in l:
            purge_total += 1
            if not after: purge += 1
    ext = open(os.path.join(D, tag + '.ext')).read()
    extn = int(re.search(r'blk_ data maps: (\d+)', ext).group(1))
    return snap, steps, dict(need=need, old=old, purge=purge, old_total=old_total, purge_total=purge_total), extn
res = {}
for tag in ['S0', 'S1', 'S2', 'S5', 'S9', 'S17', 'S256', 'posctl', 'unmapctl', 'S2-rep2', 'S9-rep2', 'S256-rep2', 'S5-jdk11', 'S256-jdk11', 'unmapctl-jdk11']:
    res[tag] = parse(tag)
base_rss = res['S0'][0]['end'][3]
print(f'S=0 end RssFile = {base_rss} kB (reference for deltas)')
print('tag | after-close blkMaps | blkMappedBytes | end blkMaps | ext blkMaps | RssFile end kB | delta MiB | predicted MiB | tol MiB | VmSize delta MiB | demoteNeed | demoteOld(before/total) | purge')
for tag, (snap, steps, c, extn) in res.items():
    s = int(re.match(r'S(\d+)', tag).group(1)) if tag.startswith('S') else 256
    m = M(s)
    jdk11 = tag.endswith('jdk11')
    ref_rss = res['S0'][0]['end'][3] if not jdk11 else snap['before'][3]
    ref_vm = res['S0'][0]['end'][2] if not jdk11 else snap['before'][2]
    d = (snap['end'][3] - ref_rss) / 1024.0; dv = (snap['end'][2] - ref_vm) / 1024.0
    if tag.startswith('S'):
        for i in range(N):
            chk(f'{tag}/step{i}/blkMaps', steps[i][0], min(i + 1, max(s, 1)) if s >= 1 else 1)
            chk(f'{tag}/step{i}/blkMappedBytes', steps[i][1], steps[i][0] * B)
        for k in ('after-close', 'end'):
            chk(f'{tag}/{k}/blkMaps', snap[k][0], m); chk(f'{tag}/{k}/blkMappedBytes', snap[k][1], m * B)
        chk(f'{tag}/ext', extn, m)
        chk(f'{tag}/demoteNeed', c['need'], N - m); chk(f'{tag}/demoteOld', c['old_total'], 0); chk(f'{tag}/purge', c['purge_total'], 0)
        pred = m * 64; tol = 16 + 0.05 * pred
        chk(f'{tag}/RssFile delta within tol', abs(d - pred) <= tol, True)
    elif tag == 'posctl':
        pred = 4 * 64; tol = 16 + 0.05 * pred
        chk(f'{tag}/after-close/blkMaps', snap['after-close'][0], 4); chk(f'{tag}/end/blkMaps', snap['end'][0], 4)
        chk(f'{tag}/blkMappedBytes', snap['after-close'][1], 4 * B); chk(f'{tag}/ext', extn, 4)
        chk(f'{tag}/purge', c['purge'], 12); chk(f'{tag}/demoteNeed', c['need'], 0)
        chk(f'{tag}/RssFile delta within tol', abs(d - pred) <= tol, True)
    else:  # unmap control
        pred = 0; tol = 16
        chk(f'{tag}/after-close/blkMaps', snap['after-close'][0], 16); chk(f'{tag}/end/blkMaps', snap['end'][0], 0)
        chk(f'{tag}/ext', extn, 0); chk(f'{tag}/demoteNeed', c['need'], 0); chk(f'{tag}/demoteOld>=1', c['old_total'] >= 1, True)
        chk(f'{tag}/RssFile delta within tol', abs(d - pred) <= tol, True)
    print(f"{tag} | {snap['after-close'][0]} | {snap['after-close'][1]} | {snap['end'][0]} | {extn} | {snap['end'][3]} | {d:.1f} | {pred} | {tol:.1f} | {dv:.1f} | {c['need']} | {c['old']}/{c['old_total']} | {c['purge']}")
for t in ('S2', 'S9', 'S256'):
    a, b = res[t], res[t + '-rep2']
    chk(f'{t} rep2 blkMaps', (a[0]['after-close'][:2], a[0]['end'][:2], a[1]), (b[0]['after-close'][:2], b[0]['end'][:2], b[1]))
    chk(f'{t} rep2 counts', a[2], b[2])
for t in ('S5', 'S256', 'unmapctl'):
    a, b = res[t], res[t + '-jdk11']
    chk(f'{t} jdk11 blkMaps', (a[0]['after-close'][:2], a[0]['end'][:2], a[1]), (b[0]['after-close'][:2], b[0]['end'][:2], b[1]))
print(f'checks ok={ok} mismatches={bad}')
