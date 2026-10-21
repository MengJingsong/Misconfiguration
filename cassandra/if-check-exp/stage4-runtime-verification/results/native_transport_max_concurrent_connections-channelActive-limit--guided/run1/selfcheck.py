#!/usr/bin/env python3
"""Independent self-check of run 1, native_transport_max_concurrent_connections-channelActive-limit--guided (results §5).
Written 2026-10-20 after run 1's conclusion was drafted. It re-derives every figure the conclusion uses from the raw
files alone (client outputs, the Byteman trace cut by phases.csv, the class histograms, /proc status snapshots,
system.log, the control's poll file), without cluster-run.py's parsing or arms.csv, then compares a few of them with
the run script's own summary lines.

usage: selfcheck.py [~/stage4-logs/ncc/run1]        prints the checks; "ok" / "FAIL" per check, a count at the end
"""
import os, re, statistics, sys

R = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/stage4-logs/ncc/run1')
results = []


def chk(name, cond, detail=''):
    results.append(bool(cond))
    print(f'{"ok  " if cond else "FAIL"} {name}: {detail}')


def histo(path):
    total, counts, byts = None, {}, {}
    for l in open(path):
        m = re.match(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
        if m:
            counts[m.group(3)] = counts.get(m.group(3), 0) + int(m.group(1))
            byts[m.group(3)] = byts.get(m.group(3), 0) + int(m.group(2))
        m = re.match(r'^Total\s+(\d+)\s+(\d+)', l)
        if m:
            total = int(m.group(2))
    return total, counts, byts


def rss(path):
    return int(re.search(r'^RssAnon:\s+(\d+) kB', open(path).read(), re.M).group(1)) * 1024


def phases(d):
    out = []
    for l in open(d + '/phases.csv').read().splitlines()[1:]:
        ms, label, arm, ph = l.split(',')
        out.append((int(ms), arm, ph))
    return out


def trace(d):
    rows = []
    for l in open(d + '/ncc.trace'):
        m = re.search(r' ms=(\d+)\s*$', l)
        if m:
            rows.append((int(m.group(1)), l.strip()))
    return rows


# ---------------- idle lifetime
D = R + '/cluster/idle'
ph = phases(D)
tr = trace(D)
starts = {(arm, p): ms for ms, arm, p in ph}
order = []
for ms, arm, p in ph:
    if arm not in order:
        order.append(arm)
limit_of = {'warm': -1, 'm1a': -1, 'm1b': -1, 'm1c': -1, 'L2000': 2000, 'L1000': 1000, 'L500': 500}
held = {}
print('== idle lifetime: per arm (client HELD line, trace between this burst and the next arm, histograms, status)')
for i, arm in enumerate(order):
    L = limit_of[arm]
    want = 4000 if L < 0 else min(4000, L)
    t0 = starts[(arm, 'burst')]
    t1 = starts[(order[i + 1], 'base')] if i + 1 < len(order) else 10 ** 15
    seg = [l for ms, l in tr if t0 <= ms < t1]
    acc = sum(1 for l in seg if l.startswith('acc '))
    rej = sum(1 for l in seg if l.startswith('rej '))
    ina = [l for l in seg if l.startswith('ina ')]
    rej_n = sorted(int(re.search(r'n=(\d+)', l).group(1)) for l in seg if l.startswith('rej '))
    acc_n = sorted(int(re.search(r'n=(\d+)', l).group(1)) for l in seg if l.startswith('acc '))
    ctext = open(f'{D}/client-{arm}.txt').read()
    m = re.search(r'^HELD open=(\d+) closed_by_server=(\d+) errors=(\d+)', ctext, re.M)
    co, cc, ce = (int(x) for x in m.groups())
    tb, cb, bb = histo(f'{D}/histo-{arm}-base.txt')
    th, ch, bh = histo(f'{D}/histo-{arm}-held.txt')
    ep = ch.get('io.netty.channel.epoll.EpollSocketChannel', 0)
    nio = ch.get('io.netty.channel.socket.nio.NioSocketChannel', 0)
    held[arm] = dict(total=th, epoll=ep, rss=rss(f'{D}/status-{arm}-held.txt'), base_total=tb, bh=bh, bb=bb, ch=ch, cb=cb)
    print(f'   {arm}: L={L} client open={co} closed={cc} errors={ce}; acc={acc} rej={rej} ina={len(ina)}; '
          f'Epoll live {cb.get("io.netty.channel.epoll.EpollSocketChannel", 0)} -> {ep}; Nio {nio}; total {tb} -> {th}; RssAnon {held[arm]["rss"]}')
    if arm == 'warm':
        continue
    chk(f'{arm} open = min(4000, L) = {want} (client)', co == want and ce == 0, f'{co} open, {ce} errors')
    chk(f'{arm} closed by server = {4000 - want}', cc == 4000 - want, cc)
    chk(f'{arm} live EpollSocketChannel at 30 s = {want}', ep == want, ep)
    chk(f'{arm} no NioSocketChannel', nio == 0, nio)
    if L > 0:
        chk(f'{arm} acc lines {want}, numbered 1..{want}', acc == want and acc_n == list(range(1, want + 1)), f'{acc}, n {acc_n[:1]}..{acc_n[-1:]}')
        chk(f'{arm} rej lines {4000 - want}, every n > L', rej == 4000 - want and all(n > L for n in rej_n), f'{rej}, n min {rej_n[:1]}')
        last = int(re.search(r'n=(-?\d+)', ina[-1]).group(1)) if ina else None
        chk(f'{arm} ina lines 4000, counter ends 0', len(ina) == 4000 and last == 0, f'{len(ina)}, last {last}')
    else:
        chk(f'{arm} no handler lines at -1', acc == rej == len(ina) == 0, (acc, rej, len(ina)))

print('== system.log: "Exceeded maximum native connection limit of <L>" lines by limit')
ex = {}
for l in open(D + '/system.log', errors='replace'):
    m = re.search(r'Exceeded maximum native connection limit of (\d+) by using (\d+) connections', l)
    if m:
        ex.setdefault(int(m.group(1)), []).append(int(m.group(2)))
print('  ', ex)
for L in (2000, 1000, 500):
    chk(f'log line for limit {L}', L in ex and all(u > L for u in ex[L]), ex.get(L))

print('== R1 (band = range over the three -1 arms; held readings)')
for key, name in (('epoll', 'live EpollSocketChannel'), ('total', 'live heap, histogram Total'), ('rss', 'RssAnon')):
    m1 = [held[a][key] for a in ('m1a', 'm1b', 'm1c')]
    band = max(m1) - min(m1)
    r = {L: held[f'L{L}'][key] for L in (500, 1000, 2000)}
    spread = max(r.values()) - min(r.values())
    s1, s2 = (r[1000] - r[500]) / 500, (r[2000] - r[1000]) / 1000
    follows = r[2000] - r[500] > 2 * band and s1 > 0 and s2 > 0 and max(s1, s2) / min(s1, s2) <= 1.5
    flat = spread <= band
    print(f'   {name}: -1 {m1} band {band}; 500 {r[500]} 1000 {r[1000]} 2000 {r[2000]}; spread {spread}; '
          f'slope {(r[2000] - r[500]) / 1500:.1f}/conn (segments {s1:.1f}, {s2:.1f}); -> '
          f'{"follows" if follows else ("flat" if flat else "neither")}')
    if key == 'total':
        slope = (r[2000] - r[500]) / 1500
        pred4000 = r[500] + slope * 3500
        mean_m1 = statistics.mean(m1)
        print(f'      line through 500 and 2000 extended to 4000: {pred4000:.0f}; -1 mean {mean_m1:.0f}; '
              f'difference {mean_m1 - pred4000:.0f} ({(mean_m1 - pred4000) / (slope * 3500) * 100:.1f} % of the 500->4000 rise)')
        chk('live heap follows the limit by R1', follows, f'{r[2000] - r[500]} > 2 x {band}')
    if key == 'epoll':
        chk('live channels follow the limit by R1', follows, f'{r[2000] - r[500]} > 2 x {band}')
    if key == 'rss':
        print(f'      RssAnon: {"flat" if flat else "not flat"} (spread {spread} vs band {band}); AlwaysPreTouch makes the heap resident from start')

print('== per-connection heap composition (held - base, mean of the three -1 arms, per connection; top 12 classes)')
deltas = {}
for a in ('m1a', 'm1b', 'm1c'):
    for c in set(held[a]['bh']) | set(held[a]['bb']):
        deltas.setdefault(c, []).append(held[a]['bh'].get(c, 0) - held[a]['bb'].get(c, 0))
per = sorted(((statistics.mean(v) / 4000, c) for c, v in deltas.items() if len(v) == 3), reverse=True)
tot = sum(x for x, _ in per)
for x, c in per[:12]:
    print(f'   {x:8.1f} B  {c}')
print(f'   sum over all classes {tot:.1f} B per connection')

# ---------------- control lifetimes
print('== control lifetimes')
ctl = {}
for label in ('C0-1g', 'C0-16m', 'C-1g', 'C-16m'):
    d = f'{R}/cluster/{label}'
    ph = {(arm, p): ms for ms, arm, p in phases(d)}
    tr = trace(d)
    t_send, t_rel = ph[('C', 'send')], ph[('C', 'release')]
    before = [l for ms, l in tr if t_send <= ms < t_rel]
    hin = sum(1 for l in before if l.startswith('hin '))
    caps = sorted({re.search(r' cap=(\d+)', l).group(1) for ms, l in tr if l.startswith('new ')})
    bigacq = [l for ms, l in tr if l.startswith('acq ') and int(re.search(r' b=(\d+)', l).group(1)) > (1 << 20)]
    b = int(re.search(r' b=(\d+)', bigacq[0]).group(1))
    insuff = sum(1 for l in bigacq if 'INSUFFICIENT' in l)
    gl = max(int(re.search(r' gl=(\d+)/', l).group(1)) for l in bigacq)
    rs = []
    for l in open(d + '/poll-C.csv'):
        p = l.strip().split(',')
        if len(p) == 5 and 'ERR' not in p:
            rs.append(int(p[1]))
    tb, cb, _ = histo(d + '/histo-C-base.txt')
    th, chh, _ = histo(d + '/histo-C-held.txt')
    qm = chh.get('org.apache.cassandra.transport.messages.QueryMessage', 0)
    tot = re.search(r'^TOTAL ok=(\d+) err=(\d+) missing=(\d+)', open(d + '/client-C.txt').read(), re.M)
    ctl[label] = dict(hin=hin, held_bytes=hin * b, rsmax=max(rs), dheap=th - tb, qm=qm)
    print(f'   {label}: cap {caps}; b {b}; held at the sample {hin} (= {hin * b} B); large acquires {len(bigacq)} '
          f'(INSUFFICIENT {insuff}); reserve max {gl} (poll max {max(rs)}); live heap held - base {th - tb}; '
          f'QueryMessage live {qm}; client {tot.groups()}')
    chk(f'{label} every connection answered', tot.groups() == ('64', '0', '0'), tot.groups())
chk('as filed (C0): the 16 MiB arm holds as many requests as the 1 GiB arm',
    ctl['C0-16m']['hin'] == ctl['C0-1g']['hin'] == 64, (ctl['C0-1g']['hin'], ctl['C0-16m']['hin']))
chk('control (C): 1 GiB arm holds 64 requests, 16 MiB arm at most 15', ctl['C-1g']['hin'] == 64 and ctl['C-16m']['hin'] <= 15,
    (ctl['C-1g']['hin'], ctl['C-16m']['hin']))
chk('control (C): reserve max <= 16 MiB in the 16 MiB arm', ctl['C-16m']['rsmax'] <= 16 << 20, ctl['C-16m']['rsmax'])
chk('control (C): held heap lower in the 16 MiB arm by > 32 MiB', ctl['C-1g']['dheap'] - ctl['C-16m']['dheap'] > 32 << 20,
    (ctl['C-1g']['dheap'], ctl['C-16m']['dheap']))

print('== agreement with the run script (summary.txt ARM lines)')
s = open(D + '/summary.txt').read()
for arm in ('m1a', 'L2000', 'm1b', 'L1000', 'm1c', 'L500'):
    m = re.search(rf'^ARM \[idle\] {arm}: .*?EpollSocketChannel (\d+) -> (\d+); histo total (\d+) -> (\d+); RssAnon (\d+) -> (\d+)', s, re.M)
    chk(f'summary {arm} matches the raw files', m and int(m.group(2)) == held[arm]['epoll'] and int(m.group(4)) == held[arm]['total']
        and int(m.group(6)) == held[arm]['rss'], m.groups() if m else None)
print(f'== {sum(results)} ok, {len(results) - sum(results)} fail')
