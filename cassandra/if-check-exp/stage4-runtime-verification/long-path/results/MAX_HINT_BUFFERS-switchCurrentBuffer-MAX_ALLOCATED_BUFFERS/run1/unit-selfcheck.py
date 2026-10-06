#!/usr/bin/env python3
"""Self-check of run 1, unit tier (results §5.1). Re-reads the committed evidence files in this folder and
asserts every relation the conclusion in results §4.2 relies on. Usage: python3 unit-selfcheck.py > unit-selfcheck.txt"""
import re

ok = True
def chk(cond, msg):
    global ok
    print(("PASS " if cond else "FAIL ") + msg)
    ok &= bool(cond)

# ---- the seven JVMs: every one ran one test, with no failure and no error (unit-summary.txt, unit-session.log)
summary = open('unit-summary.txt').read().strip().splitlines()
chk(len(summary) == 7 and all('tests=1 failures=0 errors=0' in l and 'ant_exit=0' in l for l in summary),
    "unit-summary.txt: 7 JVMs, each tests=1 failures=0 errors=0, ant exit 0")
log = open('unit-session.log').read()
chk(len(re.findall(r'Tests run: 1, Failures: 0, Errors: 0, Skipped: 0', log)) == 7,
    "unit-session.log: seven 'Tests run: 1, Failures: 0, Errors: 0' lines")
chk('done; any test failed: 0' in log, "unit-session.log: 'done; any test failed: 0'")
chk('FAIL:' not in log and log.count(': OK') == 3,
    "unit-session.log: set-up printed no FAIL and three sha256sum 'OK' lines (harness = committed files)")

# ---- the harness test's own readings (unit-harness-readings.txt)
txt = open('unit-harness-readings.txt').read()
blocks = re.split(r'\n== ', txt)[1:]
chk(len(blocks) == 4, "unit-harness-readings.txt: four JVM blocks")
mem = {}
for b in blocks:
    lab = b.split('\n', 1)[0]
    def fields(key):
        return dict(re.findall(r'(\w+)=(\d+)', re.search(r'unit ' + key + r' (.*)', b).group(1)))
    hdr = re.search(r'unit n=(\d+) bufferSize=(\d+) hintsToWrite=(\d+) entrySize=(\d+)', b)
    n, size, total, entry = map(int, hdr.groups())
    base = fields('directBaseline')
    w, a, r, e = fields('atWait'), fields('after2s'), fields('afterOneRecycle'), fields('atEnd')
    per = size // entry
    mem[lab] = int(w['usedDelta'])
    chk(re.search(r'parkedAt=.*LinkedBlockingQueue\.take.*HintsBufferPool\.switchCurrentBuffer', b),
        f"{lab}: writer parked in take() under switchCurrentBuffer")
    chk(int(w['allocatedBuffers']) == n and int(w['queued']) == n - 1,
        f"{lab}: allocatedBuffers {w['allocatedBuffers']} == n {n}; buffers handed to the callback {w['queued']} == n-1")
    chk(int(w['countDelta']) == n and int(w['usedDelta']) == n * size,
        f"{lab}: Count +{w['countDelta']} == n; MemoryUsed +{w['usedDelta']} == n x bufferSize {n * size}")
    chk(w == a, f"{lab}: all six readings unchanged after 2 s ({w['written']} hints written)")
    chk(int(w['written']) == n * per,
        f"{lab}: hints written at the wait {w['written']} == n x floor(bufferSize/entrySize) = {n} x {per}")
    chk(int(r['written']) - int(a['written']) == per
        and all(r[k] == w[k] for k in ('allocatedBuffers', 'queued', 'countDelta', 'usedDelta')),
        f"{lab}: one recycle let through {int(r['written']) - int(a['written'])} hints (one buffer); allocatedBuffers, queued, Count, MemoryUsed unchanged")
    chk(int(e['written']) == total == int(e['hintsCounted']) and int(e['allocatedBuffers']) == n
        and int(e['countDelta']) == n and int(e['usedDelta']) == n * size,
        f"{lab}: at the end {e['written']} written == {e['hintsCounted']} found in buffers == {total} planned; still {n} buffers, +{e['usedDelta']}")
    chk(total == (n + 3) * size // entry + 1, f"{lab}: planned hints {total} = hints worth n+3 buffers")
    steps = re.findall(r'directChange count=(\d+) used=(\d+)', b)
    cnt = [int(c) - int(base['count']) for c, _ in steps]
    used = [int(u) - int(base['used']) for _, u in steps]
    chk(cnt == list(range(0, n + 1)) and used[-1] == n * size,
        f"{lab}: direct Count rose one per buffer, {cnt}, and stopped at n; final MemoryUsed step {used[-1]}")
    chk('unit PASS' in b, f"{lab}: test printed PASS")
chk(len({re.search(r'directBaseline (.*)', b).group(1) for b in blocks}) == 1,
    "the four JVMs started from the same baseline (same Count and MemoryUsed)")
chk(mem['ceiling-n6-1MiB'] == mem['ceiling-n3-2MiB'] == 6291456,
    "second-knob check: n=6 x 1 MiB and n=3 x 2 MiB both +6291456 bytes")
chk(mem['ceiling-n2-1MiB'] < mem['ceiling-n3-1MiB'] < mem['ceiling-n6-1MiB'],
    "the ceiling moves with n: " + " < ".join(str(mem[k]) for k in ('ceiling-n2-1MiB', 'ceiling-n3-1MiB', 'ceiling-n6-1MiB')))

# ---- clone state and configuration (unit-ant-excerpts.txt)
ex = open('unit-ant-excerpts.txt').read()
chk(ex.count('git.sha=b5f2a54210d541339c2e7c17a794195cac0e67c2-dirty') == 7, "unit-ant-excerpts.txt: seven JVMs, clone HEAD b5f2a54, dirty")
chk(ex.count('Configuration location: file:/users/jason92/cassandra-run1/test/conf/cassandra.yaml') == 2,
    "unit-ant-excerpts.txt: a harness JVM and an upstream JVM loaded test/conf/cassandra.yaml")
print("ALL CHECKS PASS" if ok else "SOME CHECKS FAILED")
raise SystemExit(0 if ok else 1)
