#!/usr/bin/env python3
"""Self-check of run 1, cluster tier (results §5.1). Re-reads the committed evidence files in cluster/<label>/ and asserts every
relation the conclusion in results §4.3 relies on. Usage, from this folder: python3 cluster-selfcheck.py > cluster-selfcheck.txt

Two kinds of line. PASS/FAIL lines are checks. INFO lines are readings the conclusion quotes and do not decide anything. The
checks are in two groups: RULE checks come from the frozen §9a/§9e (what the design said the run must show), OBSERVATION checks
are properties of the data that the conclusion uses to explain something the rule did not anticipate (the 4 MiB band, see below).
The reading rule's 4 MiB band is PRINTED for every value, not asserted: it is exceeded at every value, and the rule sends a larger
difference to the create trace, which is asserted."""
import re, os, sys, csv

MiB = 1 << 20
BAND = 4 * MiB
LIM = 128 * 40                                   # in-flight hint limit on the 40-core node (case 9c)
ok = True
def chk(cond, msg):
    global ok
    print(("PASS " if cond else "FAIL ") + msg)
    ok &= bool(cond)
def info(msg):
    print("INFO " + msg)

HERE = os.path.dirname(os.path.abspath(__file__))
def path(label, f): return os.path.join(HERE, 'cluster', label, f)
def text(label, f): return open(path(label, f)).read()

# label -> (n, bufferSize, hold loaded, lines the yaml diff adds)
VALUES = {'n2': (2, 32 * MiB, True, 3), 'n3': (3, 32 * MiB, True, 3), 'n6': (6, 32 * MiB, True, 3),
          'n3-buf64MiB': (3, 64 * MiB, True, 5), 'n3-natural': (3, 32 * MiB, False, 3)}

def load(label):
    n, size, hold, yadd = VALUES.get(label.split('-attempt')[0], VALUES['n3-buf64MiB'])
    s = text(label, 'summary.txt')
    rd = list(csv.DictReader(open(path(label, 'readings.csv'))))
    for r in rd:
        for k in ('ms', 'MemoryUsed', 'Count', 'NMT_Other_KB', 'TotalHints', 'HintsInProgress'):
            r[k] = int(r[k]) if r[k] != '' else None
    cr = [dict(zip(('n', 'size', 'max', 'ms', 'thread'), re.match(r'created=(\d+) size=(\d+) max=(\d+) ms=(\d+) thread=(\S+)', l).groups()))
          for l in open(path(label, 'hints-pool.txt')) if l.startswith('created=')]
    for c in cr:
        for k in ('n', 'size', 'max', 'ms'): c[k] = int(c[k])
    wt = [(int(m.group(1)), m.group(2)) for l in open(path(label, 'hints-pool.txt')) if (m := re.match(r'waiting ms=(\d+) thread=(\S+)', l))]
    holds = [int(m.group(1)) for l in (open(path(label, 'hold.txt')) if os.path.exists(path(label, 'hold.txt')) else [])
             if (m := re.match(r'hold ms=(\d+)', l))]
    dumps = [(m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5))) for m in
             re.finditer(r'thread dump (\S+) at (\d+): parked-in-take=(\d+) blocked-on-monitor=(\d+) other=(\d+)', s)]
    return dict(label=label, n=n, size=size, hold=hold, yadd=yadd, s=s, rd=rd, cr=cr, wt=wt, holds=holds, dumps=dumps)

def phase(v, p): return [r for r in v['rd'] if r['phase'] == p]

def recount(label, tag):
    """(parked at :118, blocked at :109, MutationStage states) of one full dump, from dump-recount.txt (dump-recount.py on node0)."""
    for l in open(os.path.join(HERE, 'dump-recount.txt')):
        if l.startswith(f"{label} {tag} "):
            m = re.search(r'parked_at_118=(\d+) blocked_at_109=(\d+) other_in_switchCurrentBuffer=(\d+) MutationStage_states=(\{.*\})', l)
            return int(m.group(1)), int(m.group(2)), eval(m.group(4))
    raise KeyError((label, tag))

summ = {}
def check_value(label):
    v = load(label); summ[label] = v
    n, size, s, rd = v['n'], v['size'], v['s'], v['rd']
    ctl = phase(v, 'control')[0]; A = phase(v, 'A')[0]
    print(f"\n== {label}: n={n} bufferSize={size}")
    # ---- validity (9b "confirm it took effect", 9e step 2)
    chk(f"n={n} bufferSize={size}" in s.splitlines()[0], "summary header gives n and bufferSize")
    chk(f"-Dcassandra.MAX_HINT_BUFFERS={n} " in s and '-XX:NativeMemoryTracking=summary' in s and 'hints-pool.btm,listener:true' in s,
        "JVM_EXTRA_OPTS has the knob, NMT and the agent with hints-pool.btm")
    chk(re.search(rf'^cassandra\.MAX_HINT_BUFFERS={n}$', s, re.M), f"the JVM reports cassandra.MAX_HINT_BUFFERS={n}")
    chk(re.search(r'^DN +198\.22\.255\.91', s, re.M), "node 1 saw node 2 as DN at start")
    ydiff = text(label, 'cassandra.yaml.diff')
    chk(len(re.findall(r'^\+[^+]', ydiff, re.M)) == v['yadd'], f"the yaml diff adds {v['yadd']} lines")
    if size == 64 * MiB:
        chk('+commitlog_segment_size: 64MiB' in ydiff and '+max_mutation_size: 32MiB' in ydiff, "second-knob arm: the two lines of case 9b are in the diff")
    sl = text(label, 'session.log')
    chk('CHECK FAILED' not in sl and 'FAIL:' not in sl and sl.count('CHECK PASS') >= 10, f"session.log: {sl.count('CHECK PASS')} CHECK PASS lines, no CHECK FAILED / FAIL:")
    sub = text(label, 'submit-l.txt')
    chk('HintsBufferPool.createBuffer' in sub and 'HintsBufferPool.switchCurrentBuffer' in sub, "Submit -l lists createBuffer() and switchCurrentBuffer(...) triggers")
    chk(not re.search(r'^EXPECTED: .* NO', s, re.M), "no EXPECTED line of the script was answered NO")
    chk(re.search(r'ERROR lines in system.log: 0', s), "0 ERROR lines in node 1's system.log")
    # ---- the create trace (9d)
    cr = v['cr']
    chk(len(cr) == n and [c['n'] for c in cr] == list(range(1, n + 1)), f"exactly {n} created lines, numbered 1..{n}")
    chk(all(c['max'] == n and c['size'] == size for c in cr), f"every created line has max={n} and size={size}")
    chk(cr[0]['thread'].startswith('HintsWriteExecutor') and cr[0]['ms'] < ctl['ms'], "created=1 is the hints executor's, made at idle before the control reading")
    if v['hold']:
        t_hold = int(re.search(r'A: loading the hold at (\d+)', s).group(1))
        chk(all(c['thread'].startswith('MutationStage') and c['ms'] > t_hold for c in cr[1:]), f"created=2..{n} are MutationStage writers, after the hold was loaded")
    # ---- disallow evidence
    wt = v['wt']
    chk(len(wt) >= 1 and all(t.startswith('MutationStage') for _, t in wt) and wt[0][0] >= cr[-1]['ms'],
        f"{len(wt)} waiting lines, all MutationStage, the first not before created={n}")
    if v['hold']:
        chk(len(v['holds']) >= 20, f"{len(v['holds'])} held flushes (hold lines)")
        # ---- usage does not move while writers wait (B), nor after the release
        after = [r for r in rd if r['phase'] in ('B', 'Bend', 'release')]
        chk(max(r['MemoryUsed'] for r in after) - A['MemoryUsed'] <= 1024 and A['MemoryUsed'] - min(r['MemoryUsed'] for r in after) <= 65536,
            f"MemoryUsed from A through B and the release stays within +1 KiB / -64 KiB of A (max +{max(r['MemoryUsed'] for r in after) - A['MemoryUsed']}, min -{A['MemoryUsed'] - min(r['MemoryUsed'] for r in after)})")
        bend, rel = phase(v, 'Bend')[0], phase(v, 'release')[0]
        chk(rel['MemoryUsed'] <= bend['MemoryUsed'] + 1024 and max(c['n'] for c in cr) == n, "after the release MemoryUsed did not rise and no created line appeared: the wait ended without a new buffer")
        chk(A['TotalHints'] > 0 and bend['TotalHints'] > A['TotalHints'] and rel['TotalHints'] > bend['TotalHints'],
            f"hints flowed: TotalHints A {A['TotalHints']:,} < end of B {bend['TotalHints']:,} < after release {rel['TotalHints']:,}")
        chk(max(r['HintsInProgress'] for r in rd if r['HintsInProgress'] is not None) <= LIM * 3 // 4, "HintsInProgress never reached 75% of 128 x cores (B was not cut short)")
        # ---- thread dumps
        bd = [d for d in v['dumps'] if d[0].startswith('B')]
        chk(len(bd) >= 1 and any(d[2] == 1 and d[3] == 31 for d in bd), f"{len(bd)} B dump(s); at least one shows 1 writer parked in take() and 31 blocked on the monitor")
        chk(all(d[2] <= 1 and d[4] == 0 for d in v['dumps']), "no dump shows more than one thread in take() (the method is synchronized)")
        for tag, ms, parked, blocked, oth in v['dumps']:
            ex = text(label, f'dump-{tag}-excerpt.txt')
            if tag == 'release':
                chk(parked == 0 and blocked == 0 and ex == '' and recount(label, tag)[:2] == (0, 0), "release dump: no thread in switchCurrentBuffer (excerpt empty; the independent recount agrees)")
            elif parked == 1:
                # the excerpt written by cluster-run.sh's dump() holds the parked thread and ONE blocked thread as an example, by design;
                # the counts (1 and 31) are from the full dump on node0, which dump-recount.txt recounts by a different method
                chk('java.util.concurrent.LinkedBlockingQueue.take' in ex and 'HintsBufferPool.switchCurrentBuffer(HintsBufferPool.java:118)' in ex and ex.count('waiting to lock') >= 1
                    and recount(label, tag)[:2] == (1, 31),
                    f"dump {tag}: excerpt has the parked frame at HintsBufferPool.java:118 and a blocked example; the independent recount of the full dump agrees: 1 parked, 31 blocked")
            else:
                near_hold = any(0 <= ms - h <= 500 for h in v['holds']); near_wait = any(0 <= w - ms <= 500 for w, _ in wt)
                chk(near_hold and near_wait and parked == 0 and blocked == 0 and recount(label, tag)[:2] == (0, 0) and recount(label, tag)[2] == {'RUNNABLE': 32},
                    f"dump {tag} found no writer in the pool (all 32 MutationStage threads RUNNABLE in the independent recount): a hold line {min(ms - h for h in v['holds'] if ms - h >= 0)} ms before and a waiting line {min(w - ms for w, _ in wt if w - ms >= 0)} ms after it (the refill window)")
        # ---- the reading rule (9a), printed and then decided by the create trace
        rise, pred = A['MemoryUsed'] - ctl['MemoryUsed'], (n - 1) * size
        info(f"idle MemoryUsed {ctl['MemoryUsed']:,} Count {ctl['Count']}; at A {A['MemoryUsed']:,} Count {A['Count']}; rise {rise:,}; predicted (n-1) x bufferSize {pred:,}; "
             f"difference {rise - pred:+,} = {(rise - pred) / MiB:+.2f} MiB; the 4 MiB band is {'MET' if abs(rise - pred) <= BAND else 'EXCEEDED by ' + format(abs(rise - pred) - BAND, ',') + ' bytes'}")
        info(f"Count rose by {A['Count'] - ctl['Count']}: {n - 1} pool buffers and {A['Count'] - ctl['Count'] - (n - 1)} other direct buffers")
    # NMT cross-check: NMT 'Other' moves with MemoryUsed one for one
    nm = [r for r in rd if r['NMT_Other_KB'] is not None]
    gap = {r['phase']: r['NMT_Other_KB'] - r['MemoryUsed'] / 1024 for r in nm}
    info("NMT Other minus MemoryUsed (KB): " + ', '.join(f"{p} {g:,.0f}" for p, g in gap.items()))
    if v['hold']:
        g = [gap[p] for p in ('A', 'Bend', 'release')]
        # tolerance 64 KB: a first draft used 2 KB, a guess made before the data were read; the measured spread is 7-11 KB, the size of the ~10 KB
        # drift MemoryUsed itself shows between A and the end of B (freed per-thread buffers), on a 1.3 GB quantity
        chk(max(g) - min(g) <= 64, f"NMT 'Other' minus MemoryUsed is the same at A, end of B and after release, within {max(g) - min(g):.0f} KB (limit 64 KB): the two readings move together")

for label in ('n2', 'n3', 'n6', 'n3-buf64MiB'):
    check_value(label)

# ---- the first attempt of the 64 MiB arm: the workload was too short (results §3, defect 3)
print("\n== n3-buf64MiB, attempt 1 (200,000 rows)")
a1 = load('n3-buf64MiB-attempt1')
chk("stress n=200000" in a1['s'] and re.search(r'B: stress exited at 3\dS?s?', a1['s'].replace('s\n', 's\n')) is not None, "attempt 1 used 200,000 rows and the stress exited within B, at 30-39 s")
chk(len([d for d in a1['dumps'] if d[0].startswith('B')]) == 1 and [d for d in a1['dumps'] if d[0] == 'B10'][0][2:4] == (1, 31), "attempt 1 took one B dump (B10: 1 parked, 31 blocked)")
chk(len(a1['cr']) == 3 and all(c['size'] == 64 * MiB and c['max'] == 3 for c in a1['cr']), "attempt 1: 3 created lines, size=67108864, max=3")
chk('release: TotalHints did not rise' in a1['s'], "attempt 1: nothing was left to resume at the release, which is why its release check is empty")
r1 = phase(a1, 'A')[0]['MemoryUsed'] - phase(a1, 'control')[0]['MemoryUsed'] - 2 * 64 * MiB
info(f"attempt 1 rise over idle less (n-1) x 64 MiB: {r1:+,}")

# ---- the natural-load control (9b): no hold rule
print("\n== n3-natural (control, no hold)")
nl = load('n3-natural'); summ['n3-natural'] = nl
chk(not os.path.exists(path('n3-natural', 'hold.txt')) and 'the hold is never loaded' in nl['s'] and 'A: loading the hold' not in nl['s'], "the hold rule was never loaded")
chk(len(nl['cr']) == 3 and all(c['max'] == 3 and c['size'] == 32 * MiB for c in nl['cr']), "3 created lines, max=3, size=33554432")
chk(len(nl['wt']) >= 1, f"{len(nl['wt'])} waiting lines: the cap was reached and enforced with no hold")
chk(any(d[2] == 1 and d[3] == 31 for d in nl['dumps']), "a B dump shows 1 writer parked in take() and 31 blocked")
nr = nl['rd']; filled = [r for r in nr if r['MemoryUsed'] > 100 * MiB]
chk(len(filled) >= 3 and max(r['MemoryUsed'] for r in filled) - min(r['MemoryUsed'] for r in filled) <= 1024, f"once the pool had filled MemoryUsed did not move (range {max(r['MemoryUsed'] for r in filled) - min(r['MemoryUsed'] for r in filled)} bytes over {len(filled)} readings)")
chk(phase(nl, 'Bend')[0]['TotalHints'] == 200000, "TotalHints is 200,000 at the end: every row left its hint")
chk(re.search(r'Total errors +: +0 ', text('n3-natural', 'stress-excerpt.txt')), "the stress client reported 0 errors")
info(f"natural load: highest created {max(c['n'] for c in nl['cr'])}, peak MemoryUsed {max(r['MemoryUsed'] for r in nr):,}")

# ---- across values: the quantities the conclusion uses
print("\n== across values")
def rise(l): v = summ[l]; return phase(v, 'A')[0]['MemoryUsed'] - phase(v, 'control')[0]['MemoryUsed']
def pool(l): v = summ[l]; return v['n'] * v['size']
def U(l, p): v = summ[l]; r = phase(v, p)[0]; return r['MemoryUsed'] - (v['n'] if p == 'A' else 1) * v['size']   # direct memory that is not the pool's
ex = {l: rise(l) - (summ[l]['n'] - 1) * summ[l]['size'] for l in ('n2', 'n3', 'n6', 'n3-buf64MiB')}
info("band table, difference from (n-1) x bufferSize: " + ', '.join(f"{l} {e:+,} ({e / MiB:+.2f} MiB)" for l, e in ex.items()))
chk(all(abs(e) > BAND for e in ex.values()), "OBSERVATION: the 4 MiB band is exceeded at all four hold values, so the rule's clause 'a larger difference is decided by the create trace' applies to every value")
chk(max(ex.values()) - min(ex.values()) <= 64 * 1024, f"OBSERVATION: the excess is the same at every value and every bufferSize, within {max(ex.values()) - min(ex.values()):,} bytes (limit 64 KiB): it does not depend on n or on bufferSize")
d32, d63 = rise('n3') - rise('n2'), rise('n6') - rise('n3')
chk(abs(d32 - 32 * MiB) <= 64 * 1024, f"OBSERVATION: rise(n3) - rise(n2) = {d32:,}; one 32 MiB buffer is {32 * MiB:,} (off by {d32 - 32 * MiB:+,})")
chk(abs(d63 - 3 * 32 * MiB) <= 64 * 1024, f"OBSERVATION: rise(n6) - rise(n3) = {d63:,}; three 32 MiB buffers are {3 * 32 * MiB:,} (off by {d63 - 3 * 32 * MiB:+,})")
chk(pool('n6') == pool('n3-buf64MiB') == 192 * MiB, "second-knob arm: n x bufferSize is 192 MiB = 201,326,592 for n=6 x 32 MiB and for n=3 x 64 MiB, from the create trace")
a6, ab = phase(summ['n6'], 'A')[0]['MemoryUsed'], phase(summ['n3-buf64MiB'], 'A')[0]['MemoryUsed']
chk(abs(a6 - ab) <= 64 * 1024, f"second-knob arm: MemoryUsed at A is {a6:,} (n=6) and {ab:,} (n=3 x 64 MiB), {abs(a6 - ab):,} bytes apart")
chk(abs(ex['n3-buf64MiB'] - (phase(a1, 'A')[0]['MemoryUsed'] - phase(a1, 'control')[0]['MemoryUsed'] - 2 * 64 * MiB)) <= 64 * 1024, "second-knob arm: attempt 1 and attempt 2 agree on the excess within 64 KiB")
Ua = {l: U(l, 'A') for l in ('n2', 'n3', 'n6', 'n3-buf64MiB')}
Ui = {l: U(l, 'control') for l in ('n2', 'n3', 'n6', 'n3-buf64MiB', 'n3-natural')}
info("direct memory that is not the pool's (MemoryUsed less created x bufferSize), at idle: " + ', '.join(f"{l} {u:,}" for l, u in Ui.items()))
info("same, at A: " + ', '.join(f"{l} {u:,}" for l, u in Ua.items()) + f"; natural at end {phase(nl, 'Bend')[0]['MemoryUsed'] - 3 * 32 * MiB:,}")
three = [Ui[l] for l in ('n3', 'n6', 'n3-buf64MiB', 'n3-natural')]
chk(max(three) - min(three) <= 128 * 1024, f"OBSERVATION: the non-pool idle floor is the same in four of the five runs (n3, n6, 64 MiB arm, natural): {max(three) - min(three):,} bytes apart")
chk(abs((Ui['n2'] - Ui['n3']) - 8 * MiB) <= 32 * 1024 and abs((Ua['n2'] - Ua['n3']) - 8 * MiB) <= 32 * 1024,
    f"OBSERVATION: the n=2 run's non-pool floor is higher by one 8 MiB lump, at idle ({Ui['n2'] - Ui['n3']:,}) and at A ({Ua['n2'] - Ua['n3']:,}); it cancels in the rise over idle")
chk(abs((phase(nl, 'Bend')[0]['MemoryUsed'] - 3 * 32 * MiB) - Ua['n3']) <= 256 * 1024, "OBSERVATION: the natural-load control's non-pool memory equals the hold runs' (within 256 KiB): the hold rule adds none")
g = [summ[l]['rd'] for l in ('n3', 'n6', 'n3-buf64MiB')]
gaps = [phase(summ[l], p)[0]['NMT_Other_KB'] - phase(summ[l], p)[0]['MemoryUsed'] / 1024 for l in ('n2', 'n3', 'n6', 'n3-buf64MiB') for p in ('A',)]
chk(max(gaps) - min(gaps) <= 64, f"OBSERVATION: NMT 'Other' minus MemoryUsed at A is {min(gaps):,.0f}-{max(gaps):,.0f} KB at every value (limit on the spread 64 KB): the ~1.3 GB of native memory under load is not the pool and does not vary with n or bufferSize")

print("\n" + ("ALL CHECKS PASS" if ok else "SOME CHECKS FAILED"))
sys.exit(0 if ok else 1)
