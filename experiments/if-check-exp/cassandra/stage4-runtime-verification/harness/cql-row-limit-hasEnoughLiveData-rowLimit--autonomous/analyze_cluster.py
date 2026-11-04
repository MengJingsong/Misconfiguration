#!/usr/bin/env python3
"""EXPECTED lines for B3f / B3g (frozen text, as amended 2026-10-27). Usage: analyze_cluster.py <outdir> [reads] [npk]
Reads <outdir>/<arm>/ckpt.jsonl (checkpoints baseline, populated, window, idle). Prints EXPECTED ... GOT ... ok|MISMATCH."""
import sys, os, json
out = sys.argv[1]; READS = int(sys.argv[2]) if len(sys.argv) > 2 else 10000; NPK = int(sys.argv[3]) if len(sys.argv) > 3 else 200
MIB = 2**20
ARMS = {'l1000': (64, '100', 1000), 'l10': (64, '100', 10), 'l100': (64, '100', 100), 'l100k': (64, '100', 100000), 'lnone': (64, '100', None),
        'a100': (64, 'ALL', 100), 'anone': (64, 'ALL', None), 's256': (256, 'ALL', 100), 'off10': (0, '100', 10), 'off1000': (0, '100', 1000), 'offnone': (0, '100', None)}
ck = {}
for a in ARMS:
    f = os.path.join(out, a, 'ckpt.jsonl')
    if os.path.exists(f): ck[a] = {r['name']: r for r in map(json.loads, open(f))}
bad = []; n = 0
def chk(what, ok, exp, got, primary=True):
    global n
    n += 1; print('EXPECTED %s %s GOT %s %s%s' % (what, exp, got, 'ok' if ok else 'MISMATCH', '' if primary else ' (secondary)'))
    if not ok and primary: bad.append(what)
for a, (S, R, L) in ARMS.items():
    if a not in ck: chk(a + ' ran', False, 'checkpoints', 'missing'); continue
    c = ck[a]; pop = c.get('populated'); win = c.get('window'); idle = c.get('idle')
    if not (pop and win and idle): chk(a + ' complete', False, 'populated/window/idle', sorted(c)); continue
    dh = win['hit'] - pop['hit']; do = win['outOfRange'] - pop['outOfRange']; dm = win['miss'] - pop['miss']
    if S == 0:
        chk(a + ' Size', pop['size'] == 0 and win['size'] == 0, 0, win['size']); chk(a + ' counters', (dh, do, dm, pop['hit'], pop['outOfRange'], pop['miss']) == (0,) * 6, '0', (dh, do, dm))
        continue
    rexp = READS * (2000 if L is None or L >= 2000 else L); chk(a + ' rows returned', win['rows_returned'] == rexp, rexp, win['rows_returned'], False)
    if R == '100':
        hit_exp = READS if L in (10, 100) else 0
        chk(a + ' RowCacheHit delta', dh == hit_exp, hit_exp, dh); chk(a + ' RowCacheHitOutOfRange delta', do == READS - hit_exp, READS - hit_exp, do); chk(a + ' RowCacheMiss delta', dm == 0, 0, dm)
        chk(a + ' Entries after populate', pop['entries'] == NPK, NPK, pop['entries']); chk(a + ' Size in [3.2e6, 5.4e6]', 3.2e6 <= pop['size'] <= 5.4e6, '[3.2e6,5.4e6]', pop['size'])
        chk(a + ' Size unchanged populated->window', abs(win['size'] - pop['size']) <= 0.005 * pop['size'], pop['size'], win['size'])
    else:   # R = ALL: the :1931 short-circuit, so no out-of-range; part of the set is not cached, so some reads miss
        chk(a + ' RowCacheHitOutOfRange delta', do == 0, 0, do); chk(a + ' RowCacheHit + RowCacheMiss', dh + dm == READS, READS, dh + dm); chk(a + ' RowCacheHit > 0', dh > 0, '>0', dh)
        if a == 's256':
            chk(a + ' Size in (64 MiB, 256 MiB]', 64 * MIB < win['size'] <= 256 * MIB, '(67108864, 268435456]', win['size']); chk(a + ' Entries > 150', win['entries'] > 150, '>150', win['entries'])
        else:
            chk(a + ' Size <= 64 MiB', win['size'] <= 64 * MIB, '<=67108864', win['size']); chk(a + ' Entries < %d' % NPK, win['entries'] < NPK, '<%d' % NPK, win['entries'])
if all(x in ck and 'window' in ck[x] for x in ('s256', 'a100', 'anone')):
    chk('control: Size(s256) > Size(a100) and Size(anone)', ck['s256']['window']['size'] > max(ck['a100']['window']['size'], ck['anone']['window']['size']), '>', '%d vs %d, %d' % (ck['s256']['window']['size'], ck['a100']['window']['size'], ck['anone']['window']['size']))
sizes = [ck[a]['window']['size'] for a in ('l1000', 'l10', 'l100', 'l100k', 'lnone') if a in ck and 'window' in ck[a]]
if len(sizes) == 5: chk('R=100 Size spread over L within 1%', (max(sizes) - min(sizes)) <= 0.01 * max(sizes), '<=1%', '%d..%d' % (min(sizes), max(sizes)))
# retained RSS (idle - baseline) and the cache-attributable part against the closest cache-off arm
def rss(a): return (ck[a]['idle']['RssAnon_kb'] - ck[a]['baseline']['RssAnon_kb']) * 1024 if a in ck and 'idle' in ck[a] else None
pair = {'l10': 'off10', 'l100': 'off10', 'l1000': 'off1000', 'l100k': 'offnone', 'lnone': 'offnone'}
att = {}
for a, o in pair.items():
    if rss(a) is not None and rss(o) is not None:
        att[a] = rss(a) - rss(o); size = ck[a]['window']['size']
        print('  RSS %s: idle-baseline %.1f MiB, %s %.1f MiB, attributable %.1f MiB, cache Size %.1f MiB' % (a, rss(a) / MIB, o, rss(o) / MIB, att[a] / MIB, size / MIB))
        chk(a + ' attributable RSS <= Size + max(20%, 64 MiB)', att[a] <= size + max(0.2 * size, 64 * MIB), '<=', '%.1f MiB' % (att[a] / MIB), False)
if len(att) == 5:
    chk('R=100 attributable RSS spread over L <= 64 MiB', max(att.values()) - min(att.values()) <= 64 * MIB, '<=64 MiB', '%.1f MiB' % ((max(att.values()) - min(att.values())) / MIB), False)
for a in ARMS:
    if a in ck and 'idle' in ck[a]:
        print('  %s: RssAnon baseline %.0f MiB, window %.0f, idle %.0f; Size %.2f MB, Entries %d' % (a, ck[a]['baseline']['RssAnon_kb'] / 1024, ck[a]['window']['RssAnon_kb'] / 1024, ck[a]['idle']['RssAnon_kb'] / 1024, ck[a]['window']['size'] / 1e6, ck[a]['window']['entries']))
print('primary mismatches: %d of %d checks' % (len(bad), n))
print('CLASS: ' + ('claim holds (B3g row 1)' if not bad else 'see mismatches: ' + '; '.join(bad[:12])))
