# Bypass playbook (Direction 2)

Produces one **bypass case**: for a single constraint/capacity from
if-check-exp, a way to make the real resource usage exceed the capacity the
check was meant to enforce — ideally far enough, or combined with enough
baseline load, to threaten OOM.

Run this by hand or give it to an agent, in a Claude Code session with a copy
of the Cassandra source at tag `cassandra-5.0.9` and read access to
[`if-check-exp`](../if-check-exp/README.md) (its case files and the stage-4
results are the input).

## The goal

Starting from one if-check-exp case (a capacity check and the constraint that
sets it), find a way for usage to grow **past** that capacity while the check
is still present and still runs. The check does not fire, or fires too late,
or fires but does not actually stop the growth.

## Where to start

Prefer, in this order:

1. **Confirmed bypasses already on record.** if-check-exp's stage-4 results
   mark some cases "caps only on some paths (bypass)", and `HANDOFF.md`'s
   "Upstream bug candidates" list and each case's §8/Target-3 note name
   several already-spotted gaps (e.g. buffers never returned to a pool, a
   counter that cannot free native memory on an explicit-removal path, an
   `int` overflow in a space calculation, a cache-save flag whose `0` means
   the opposite of what it says). Pick one and push it to see how far past
   the capacity it goes.
2. **True-positive cases** (the check does cap usage, confirmed at stage 4) —
   look for a path the stage-4 run did not drive through: a different code
   caller of the same check, a config combination that changes which branch
   fires, a protocol feature that skips validation.
3. **Weak or undetermined cases** where the cluster tier never settled — the
   gap stage 4 could not close may itself be the bypass.

Do not start from a confirmed true negative (the case file already shows
usage never follows that constraint) — there is no cap there to bypass.

## Kinds of bypass to look for

- **Escape hatch.** A config flag, option, or alternate code path that is
  documented or intended, but which skips or loosens the check for some
  callers (e.g. an internal/system keyspace exempted from a guardrail, a
  superuser bypass, `ALLOW FILTERING`-style opt-outs, an admin tool that
  writes around the normal write path).
- **Accounting gap.** The check tracks one quantity (a counter, an estimate,
  a "logical" size) while the correlated real resource (heap, native memory,
  disk) grows by a different, uncounted amount — e.g. the check counts
  evictions but not all removal causes, or tracks serialized size but the
  in-memory structure is larger.
- **Computation flaw.** The bound itself is computed wrong: integer overflow
  or wraparound at a large input, a unit mismatch (bytes vs. MiB), a
  check-after-allocate ordering (the allocation happens, then the check
  rejects it, but the memory was already taken), or a race between the check
  and a concurrent increment of the same counter.
- **Partial enforcement.** The check caps one path to a resource but another
  path reaches the same resource uncapped (a second writer, a retry queue, a
  background task) — see if-check-exp's "second check site" notes for
  constraints with more than one caller.

## Verifying a bypass

1. **State the check and the claim before trying anything**: what the check
   is supposed to prevent, and the specific mechanism you expect to defeat it.
2. **Control arm**: drive usage through the *normal* path to the capacity,
   confirmed blocked (reuse the if-check-exp cluster-tier result if it exists).
3. **Bypass arm**: drive the same resource through the path you identified,
   past the capacity, and measure the real resource (heap, off-heap, or
   disk bytes) — not just the check's own counter, which may itself be part
   of the gap.
4. **Push it as far as is safe** on the test node: either to actual OOM, or to
   a clearly documented stopping point (e.g. node memory exhausted to a
   dangerous margin, logged and the process stopped before a hard crash) —
   state which, and why you stopped there.
5. **Rule out the mundane explanation**: confirm the bypass arm isn't simply
   using a different, still-enforced capacity (check that no other guardrail
   caught it) and that the result reproduces at least once.

## Output

Write one file per case to `cases/<constraint>-<function>--bypass.md` in this
folder, covering:

- **A.** The if-check-exp case this bypass targets (link, outcome class, the
  capacity and constraint).
- **B.** The bypass mechanism — escape hatch / accounting gap / computation
  flaw / partial enforcement — with `file:line` citations in the pinned tree.
- **C.** The claim: what usage should do under the normal path vs. the bypass
  path.
- **D.** Control-arm and bypass-arm procedures (knobs, workload, instruments,
  stop conditions), reusing if-check-exp's cluster-tier harness where it exists.
- **E.** Results: control-arm reading (capped), bypass-arm reading (how far
  past capacity, in bytes and as a multiple of the capacity), and whether it
  reached OOM.
- **F.** Whether this looks like a genuine upstream defect worth a JIRA
  check/report, separate from whatever is already listed in `HANDOFF.md`'s
  "Upstream bug candidates".

Commit case files and raw-log excerpts the same way if-check-exp stage 4 does
(small excerpts in the repo, full logs kept on the node, path recorded).
