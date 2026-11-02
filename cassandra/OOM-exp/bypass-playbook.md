# Bypass playbook (Direction 2)

**This is the agent's whole instruction for a bypass run.** Give an agent
this file, read access to [`if-check-exp`](../if-check-exp/README.md) (its
case files and stage-4 results are the input; this experiment does not
re-derive them), and a copy of the Cassandra source at tag `cassandra-5.0.9`
built on a node you own. The agent does the whole job itself: **it picks
which constraint/check to attack and what bypass mechanism to try, designs
the test, runs it, and files the result** — there is no separate
design-then-execute split here (unlike if-check-exp stage 3/4). Run it as a
Claude Code session on the node, or on a node it can reach, so it can build,
start Cassandra, drive load and read logs/heap output directly.

## Produces: multiple bypass cases, one agent run

**One playbook run produces a batch of bypass cases, not one.** Each case is
one specific constraint paired with one specific bypass mechanism tried
against it, with its own design and its own execution result. Work through
candidates until either:

- a stopping budget is reached (number of candidates tried, or wall-clock
  time given), or
- the agent judges the remaining plausible candidates are exhausted for the
  if-check-exp cases available (see "Picking candidates" below).

State at the top of the batch log how many candidates were attempted and how
many are filed as cases. A candidate considered but rejected before building
(the mechanism clearly doesn't apply, or it's a true negative with nothing to
bypass) does not need a full case file — note it in the batch log instead;
only candidates that were actually designed and run get a case file.

## The goal, per case

Starting from one if-check-exp case (a capacity check and the constraint that
sets it), find a way for usage to grow **past** that capacity while the check
is still present and still runs. The check does not fire, or fires too late,
or fires but does not actually stop the growth — ideally pushed far enough,
or combined with enough baseline load, to threaten OOM.

## Picking candidates (the agent's job)

The agent chooses which constraint/mechanism pairs to try. There is no fixed
list to work down — survey if-check-exp's cases itself. Prefer, in this
order:

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
usage never follows that constraint) — there is no cap there to bypass; note
it as skipped in the batch log if it was considered.

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

## Designing and running a case (the agent's job)

For each chosen constraint/mechanism pair:

1. **State the check and the claim before trying anything**: what the check
   is supposed to prevent, and the specific mechanism expected to defeat it.
2. **Design the control arm**: drive usage through the *normal* path to the
   capacity, confirmed blocked (reuse the if-check-exp cluster-tier result if
   it exists).
3. **Design the bypass arm**: the exact path, knobs, and workload that drives
   the same resource past the capacity through the identified mechanism, and
   the instruments to measure the real resource (heap, off-heap, or disk
   bytes) — not just the check's own counter, which may itself be part of
   the gap.
4. **Run both arms**, scripted and logged. Push the bypass arm as far as is
   safe on the test node: either to actual OOM, or to a clearly documented
   stopping point (e.g. node memory exhausted to a dangerous margin, logged
   and the process stopped before a hard crash) — state which, and why.
5. **Rule out the mundane explanation**: confirm the bypass arm isn't simply
   using a different, still-enforced capacity (check that no other guardrail
   caught it) and that the result reproduces at least once.
6. Run on a node you own, with nothing outside that node touched. Never fill
   shared storage. Stop every process the run starts and check none is left
   before moving to the next candidate.

## Output

Write one file per attempted candidate to
`cases/bypass/<constraint>-<function>.md` in this folder. Use this
template — four sections, in this order:

### 1. Constraint and capacity

The if-check-exp case this bypass targets: its case-file link and outcome
class, the capacity check (`file:line`), the constraint and what it caps.
Name the bypass mechanism being tried — escape hatch / accounting gap /
computation flaw / partial enforcement — with `file:line` citations in the
pinned tree for the mechanism itself (not just the check).

### 2. Verification solution

How to make usage exceed the capacity while the check is still present. The
design, written before running anything:

- **The claim.** What usage should do under the normal path (capped) vs. the
  bypass path (not capped, or capped too late).
- **Control-arm procedure.** Exact knobs, workload, and instruments to drive
  the normal path to capacity and confirm it is blocked.
- **Bypass-arm procedure.** Exact knobs, workload, and instruments to drive
  the same resource through the identified mechanism, past the capacity.
- **Stop condition.** What "far enough" means for this candidate (actual OOM
  vs. a documented safe stopping point) and why.

### 3. Runtime results

What happened after the solution was executed:

- Control-arm readings: confirmed capped, at what measured usage.
- Bypass-arm readings: how far past capacity usage went, in bytes and as a
  multiple of the capacity, and whether it reached OOM (actual
  `OutOfMemoryError`, kernel OOM-kill via `dmesg`, or neither). Cite the raw
  log/excerpt for every number and every claimed event.
- The mundane-explanation check from step 5 above, and its result.

### 4. Conclusion

- **If the bypass is confirmed** (usage exceeded the capacity through the
  identified mechanism): state the conclusion as a capability gap — *this
  check does not actually bound usage on [path/condition], because
  [mechanism]*, and whether it looks like a genuine upstream defect worth a
  JIRA check/report (separate from whatever is already listed in
  `HANDOFF.md`'s "Upstream bug candidates"). Say how far past capacity usage
  went and whether it reached OOM on its own or would need combining with
  other load.
- **If the bypass did not hold** (usage stayed capped, or the mechanism
  didn't do what was expected): state why, specifically — the agent's
  diagnosis, not just "it didn't happen." Common reasons to check and name
  whichever applies: the mechanism doesn't actually skip the check (misread
  code path), a different guardrail caught the attempt, the workload didn't
  exercise the mechanism as designed, or the accounting gap exists but is too
  small to matter at reachable scale. State whether a modified version of
  the same candidate is worth a retry, or whether this candidate should be
  marked exhausted.

Keep a **batch log** at `cases/bypass/_batch-log.md` (append one entry per
playbook run): the date, the if-check-exp cases surveyed, every
constraint/mechanism pair attempted with a link to its case file, every
candidate considered and skipped with why, and the stopping reason (budget
exhausted vs. time/count limit).

Commit case files, the batch log, and raw-log excerpts the same way
if-check-exp stage 4 does (small excerpts in the repo, full logs kept on the
node, path recorded). The agent does not commit or push unless asked.
