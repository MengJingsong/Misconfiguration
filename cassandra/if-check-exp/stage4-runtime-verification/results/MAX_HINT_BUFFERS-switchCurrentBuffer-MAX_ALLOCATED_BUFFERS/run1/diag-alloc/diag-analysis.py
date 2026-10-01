#!/usr/bin/env python3
"""Supplementary diagnostic (results §4.3): attribute the direct memory that appears between the idle control and scenario A.

Input: diag-alloc.txt (one line per ByteBuffer.allocateDirect call: size, time, thread, flattened stack; 8.5 MB, committed as
diag-alloc.txt.gz, the original is on node0) and readings.csv / hints-pool.txt from the same run, all in this folder.
Usage: python3 diag-analysis.py . > diag-analysis.txt
It reads only; it asserts the accounting identities and prints the table of the window's allocations by site."""
import re, sys, collections, os, gzip

d = sys.argv[1] if len(sys.argv) > 1 else '.'
ok = True
def chk(cond, msg):
    global ok
    print(("PASS " if cond else "FAIL ") + msg)
    ok &= bool(cond)

# ---- readings and the pool's create trace
rd = [l.strip().split(',') for l in open(os.path.join(d, 'readings.csv')).read().strip().splitlines()[1:]]
R = {r[0]: dict(ms=int(r[1]), used=int(r[2]), count=int(r[3])) for r in rd if r[0] in ('control', 'A', 'A-plus3s')}
created = [dict(zip(('n', 'size', 'max', 'ms', 'thread'), re.match(r'created=(\d+) size=(\d+) max=(\d+) ms=(\d+) thread=(\S+)', l).groups()))
           for l in open(os.path.join(d, 'hints-pool.txt')) if l.startswith('created=')]
created = [{k: (int(v) if k != 'thread' else v) for k, v in c.items()} for c in created]

# ---- every allocateDirect call
allocs = []
trace = os.path.join(d, 'diag-alloc.txt')
for l in (open(trace) if os.path.exists(trace) else gzip.open(trace + '.gz', 'rt')):
    m = re.match(r'alloc size=(\d+) ms=(\d+) thread=(.*?) stack=\[(.*)\]\s*$', l)
    if not m:
        continue
    size, ms, thread, stack = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
    frames = [f.strip() for f in stack.split(', ')]
    # frames[0..] run from Thread.getStackTrace through Byteman's own frames to ByteBuffer.allocateDirect, then the callers
    i = next(k for k, f in enumerate(frames) if 'java.nio.ByteBuffer.allocateDirect' in f)
    callers = frames[i + 1:]
    app = next((f for f in callers if f.startswith(('org.apache.cassandra', 'io.netty', 'com.codahale'))), None)
    imm = callers[0] if callers else '?'
    short = lambda f: re.sub(r'\(.*\)', '', f).split('.')[-2] + '.' + re.sub(r'\(.*\)', '', f).split('.')[-1] if f else ''
    allocs.append(dict(size=size, ms=ms, thread=thread, imm=re.sub(r'\(.*\)', '', imm), app=re.sub(r'\(.*\)', '', app) if app else None,
                       via=short(callers[1]) if len(callers) > 1 else '', fam=re.match(r'[A-Za-z]+', thread).group(0) if re.match(r'[A-Za-z]+', thread) else thread))

print(f"allocateDirect calls traced since JVM start: {len(allocs)}; total bytes requested: {sum(a['size'] for a in allocs):,}")
t_ctl, t_A = R['control']['ms'], R['A']['ms']
win = [a for a in allocs if t_ctl < a['ms'] <= t_A]
pre = [a for a in allocs if a['ms'] <= t_ctl]
print(f"control reading at ms={t_ctl}; A reading at ms={t_A} ({(t_A - t_ctl) / 1000:.1f} s later)")
print(f"before the control reading: {len(pre)} calls, {sum(a['size'] for a in pre):,} bytes requested; window (control, A]: {len(win)} calls, {sum(a['size'] for a in win):,} bytes requested")
dU, dC = R['A']['used'] - R['control']['used'], R['A']['count'] - R['control']['count']
print(f"direct pool change over the window: MemoryUsed +{dU:,}, Count +{dC}")

# ---- the pool's own allocations, as seen at the JDK API
pool = [a for a in allocs if a['size'] == created[0]['size']]
chk(len(pool) == len(created) == 3 and all(c['max'] == 3 for c in created),
    f"allocateDirect({created[0]['size']}) was called {len(pool)} times, equal to the {len(created)} created lines (max=3)")
# HintsBuffer.create(int) is the pool's only allocation site: `ByteBuffer.allocateDirect(slabSize)` at HintsBuffer.java:77,
# reached from HintsBufferPool.createBuffer() (HintsBufferPool.java:133). An earlier draft of this check named HintsBuffer.allocate,
# a method that does not allocate; the trace showed `create`, and the source at the pinned tag agrees.
chk(all(a['imm'].endswith('HintsBuffer.create') for a in pool),
    "every one of them was called from HintsBuffer.create: " + ', '.join(sorted({a['imm'] for a in pool})))
pool_win = [a for a in pool if t_ctl < a['ms'] <= t_A]
chk(len(pool_win) == 2, f"two of the three fall in the window (created=2 and created=3); the first was made at idle, before the control reading")
for a, c in zip(pool, created):
    chk(abs(a['ms'] - c['ms']) <= 50 and a['thread'] == c['thread'], f"allocation at ms={a['ms']} thread={a['thread']} matches created={c['n']} line (ms={c['ms']}, thread={c['thread']})")

# ---- everything else in the window, by allocation site
other = [a for a in win if a not in pool_win]
print(f"\nnot the pool, in the window: {len(other)} calls, {sum(a['size'] for a in other):,} bytes requested")
by = collections.OrderedDict()
for a in sorted(other, key=lambda a: -a['size']):
    key = (a['app'] or a['imm'], a['imm'])
    by.setdefault(key, []).append(a)
rows = sorted(by.items(), key=lambda kv: -sum(a['size'] for a in kv[1]))
print(f"{'calls':>5} {'bytes':>12}  {'sizes (count x size)':<34} allocating site (first cassandra/netty frame; immediate caller in brackets)")
for (site, imm), lst in rows[:14]:
    sizes = collections.Counter(a['size'] for a in lst)
    sz = ', '.join(f"{c}x{s}" for s, c in sizes.most_common(3)) + (' …' if len(sizes) > 3 else '')
    print(f"{len(lst):>5} {sum(a['size'] for a in lst):>12,}  {sz:<34} {site}  [{imm.split('.')[-2]}.{imm.split('.')[-1]}]")
    fams = collections.Counter(a['fam'] for a in lst).most_common(3); vias = collections.Counter(a['via'] for a in lst).most_common(3)
    print(f"{'':>19}  threads: {', '.join(f'{k} x{c}' for k, c in fams)}; called by: {', '.join(f'{k} x{c}' for k, c in vias)}")
big = [a for a in other if a['size'] >= 1 << 20]
print("\nallocations of 1 MiB or more in the window that are not the pool's:")
for a in big:
    print(f"  size={a['size']:,} ms={a['ms']} thread={a['thread']} site={a['app'] or a['imm']} immediate caller={a['imm']}")

# ---- the accounting: what the window added, less what the JVM freed, equals what the bean shows
req_other = sum(a['size'] for a in other)
explained = req_other + sum(a['size'] for a in pool_win)
print(f"\naccounting: bytes requested in the window {explained:,} (pool {sum(a['size'] for a in pool_win):,} + other {req_other:,}); bean change +{dU:,}")
print(f"  requested minus bean change = {explained - dU:,} bytes (buffers the JVM freed within the window, or temporary NIO buffers replaced by larger ones)")
mb = [a for a in big if a['size'] == 8392704]
chk(len(mb) == 1 and (mb[0]['app'] or '').startswith('org.apache.cassandra.utils.memory.BufferPool'),
    "exactly one 8,392,704-byte (8 MiB + 4 KiB alignment) call in the window, from org.apache.cassandra.utils.memory.BufferPool: "
    + (mb[0]['app'] if mb else 'none'))
residual = dU - sum(a['size'] for a in pool_win) - (mb[0]['size'] if mb else 0)
print(f"the bean's change less the pool's two buffers and that one chunk: {residual:,} bytes over {dC - 2 - len(mb)} more buffers "
      f"({residual / max(1, dC - 2 - len(mb)):.0f} bytes each on average)")
small = [a for a in other if a['size'] < 1 << 20]
print("small allocations in the window by immediate caller (count, total bytes requested):")
byc = collections.Counter(); byb = collections.Counter()
for a in small:
    byc[a['imm']] += 1; byb[a['imm']] += a['size']
for k, _ in byb.most_common(6):
    print(f"  {byc[k]:>4} calls {byb[k]:>10,} bytes  {k}")
print("\n" + ("ALL CHECKS PASS" if ok else "SOME CHECKS FAILED"))
sys.exit(0 if ok else 1)
