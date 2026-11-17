# Experiments — how they relate

*Written 2026-11-16.* What each experiment is for, which depends on which, and how results flow
back. The method of each experiment is in its own README.

## Vocabulary

| Term | Means | Where defined |
|---|---|---|
| **Target 1 / 2 / 3** | the goals of this repository: identify resource constraints; show how each restricts usage; investigate how usage gets past them to exhaustion | root [`README.md`](../README.md) |
| **Phase 1 / 2** | the experiments in dependency order: phase 2 depends on phase 1's results | this file |
| **Stage 1–4** | steps inside `capacity-enforcement-exp` (CodeQL, AI preprocessing, AI deep read, runtime verification) | [`capacity-enforcement-exp/README.md`](capacity-enforcement-exp/README.md) |

Write "phase 1" in full, never "P1": in OOM-exp, P1–P3 are queue priorities and P1–P6 are patterns.

## The phases

| Phase | Experiment | Targets | Question |
|---|---|---|---|
| **1** | [`capacity-enforcement-exp/`](capacity-enforcement-exp/README.md) (named `if-check-exp` until 2026-11-11) | 1 + 2 | Which factors affect how much memory or disk the system uses, and does usage follow each one? |
| 1 (supplement, paused) | [`entry-restriction-exp/`](entry-restriction-exp/README.md) | 1 + 2 | The same, worked forward from where a constraint is declared |
| **2** | [`OOM-exp/`](OOM-exp/README.md) | 3 | Starting from phase 1's constraints at their **default values**, is there a reachable way to run out of memory? |

**Phase 1** looks for every factor that affects resource usage. A factor is **config** (a yaml entry
or a JVM system property; these are documented, and phase 1's config results should ideally cover
every capacity-related entry) or **non-config**: a local variable or constant. Non-config factors are
the **hidden factors**, because nothing documents them.

**Phase 2** tests whether those factors work as expected. If a reachable workload drives a node out of
memory while the constraints sit at their defaults and the memory budget is one a deployment would
run, the protection is imperfect. Only such cases are **verified** (OOM-exp
[verification protocol](OOM-exp/verification-protocol.md), V6–V7).

**Phases are per system.** Cassandra is in phase 2; Hadoop is still in phase 1, and its phase 2
starts from Hadoop's phase-1 results.

## How phase 2 uses phase 1

- Phase 1's case files, estimates and stage-4 results are OOM-exp's inventory of constraints and of
  the places that enforce them.
- **JIRA OOM history** gives clues for selecting among phase 1's constraints: which ones have failed
  before, and how.
- **Data-flow tracing** (OOM-exp) starts from where bytes are held, not from a constraint. It stays a
  **phase-2-only source for now** (owner's decision, 2026-11-17): the one lead source that does not go
  through phase 1, and the one that can find memory no constraint touches.

## How phase 2 feeds back into phase 1

The two phases should be strongly connected: a verified OOM case should, where possible, trace back
to a clue in phase 1, such as a counter that charges less than the memory really held (internode
queues, B6) or a limit whose only stop is the JVM's own `OutOfDirectMemoryError` (concurrent reads,
C2). Phase 1 is therefore never closed.

1. **Back-link.** Every case that becomes `verified-OOM` or `verified-gap` gets one row in
   [`phase-links/<system>.md`](phase-links/) by the [back-link playbook](backlink-playbook.md): was
   the clue in phase 1 as filed (`flagged`, `recorded-untested`, `missed`, `no-case`,
   `out-of-scope`), and which question would have surfaced it.
2. **Guided playbook.** A question that would have surfaced a missed clue joins the guided
   playbook's [enforcement-property questions](capacity-enforcement-exp/stage3-ai-deep-read/playbook-guided.md#32-enforcement-properties-added-2026-11-16)
   (E1–E4 so far), dated and with the case named. The **autonomous playbook is never changed** this
   way: it is the control that gets the target only.
3. **Rechecks.** Phase-1 case files filed before a question existed are rechecked
   ([guided playbook §5](capacity-enforcement-exp/stage3-ai-deep-read/playbook-guided.md#5-rechecking-a-filed-case-added-2026-11-16)):
   in `back-link` mode for the files a link row names, in `blind` mode (without reading OOM-exp) for
   a batch the owner approves.
4. **Flags back to phase 2.** Each recheck answer that says real memory can exceed what a constraint
   governs is a flag in `capacity-enforcement-exp/<system>/stage3-ai-deep-read/recheck-flags.md`,
   which OOM-exp reads as leads. **Only blind flags that OOM-exp later verifies show that phase 1
   predicts phase 2**; back-link rows only explain results after the fact.

Not every verified case needs a phase-1 clue. Memory that no constraint or capacity touches is
outside phase 1's definition; its link row says `out-of-scope` rather than stretching phase 1.

## Files at this level

| File | Holds |
|---|---|
| [`backlink-playbook.md`](backlink-playbook.md) | The procedure run for each newly verified OOM-exp case |
| [`phase-links/`](phase-links/) | One link table per system |
