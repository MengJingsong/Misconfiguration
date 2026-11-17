# Blind recheck — the whole instruction

*Added 2026-11-16.* The instruction for a **blind** recheck of a filed phase-1 case
([`playbook-guided.md`](playbook-guided.md) §5, `blind` mode). It holds the enforcement-property
questions of the guided playbook's §3.2 **without** their examples, which name results of the later
OOM experiment. **A blind agent is given this file and does not open `playbook-guided.md`.** When
§3.2's questions change, change them here too.

## Do not open

Anything under `experiments/OOM-exp/` or `experiments/phase-links/`; `experiments/README.md`;
`experiments/backlink-playbook.md`; `playbook-guided.md`; any `HANDOFF*.md`; `oom-lead-list.md`;
`budget-ledger.md`; and git history or commit messages. In other case files, skip any section headed
`## Recheck`. Everything else in phase 1 (case files, stage-4 results, `_INDEX.md`) and the pinned
source may be read.

## The questions

Patterns are added over time (E5, …). In a **sweep** over files already rechecked, answer only the
patterns you are told to, under `## Recheck — <patterns> (guided, YYYY-MM-DD, blind)`, and end every
recheck heading with the patterns answered.

A constraint can cap the quantity its check counts and still leave real memory unbounded. Answer each
question from the pinned source (`systems/cassandra/source/`, tag `cassandra-5.0.9`) with `file:line`,
or write `unknown: <what would settle it>`. Answer for the shipped **default** settings and a reachable
workload.

| # | Pattern to look for | Question |
|---|---|---|
| **E1** | **Mismatch between the counter and real usage** (charges less than is held, or released before the memory is freed) | **What is counted, and for how long?** The unit the counter charges (on-wire bytes, entries, a weigher's estimate) against the bytes the object really holds once admitted (after deserialization, with per-entry overhead, with copies). And when the counter is released against when the memory is freed. |
| **E2** | **A direct error after usage exceeds capacity** (the refused allocation goes elsewhere, or only the JVM's own error stops it) | **What happens at the limit?** A graceful outcome (reject, block, evict, back-pressure, shrink) or a failing one: the disallow path still allocates elsewhere (overflow, fallback), or nothing stops the allocation before the JVM's own limit, so the "enforcement" is an `OutOfMemoryError` / `OutOfDirectMemoryError`. |
| **E3** | **A per-owner limit times an unbounded number of owners** | **Per what, and how many?** The owner a limit applies to (node, table, connection, peer link, thread, writer, validation), how many owners exist at default settings and under a reachable load, and whether any limit caps their total. |
| **E4** | **Defaults that over-commit a shared budget** | **Which budget, shared with what?** The memory domain (heap, direct, other native, page cache, container), the other constraints that draw on the same domain, and whether their defaults, resolved at a deployment heap, add up to more than that domain's default budget. |

## Procedure

1. Read the case file (guided or autonomous) and its stage-4 result
   (`../cassandra/stage4-runtime-verification/results/<same stem>.md`, if any), then every
   `file:line` it cites for the constraint, the counter and the disallow path.
2. Answer E1–E4. Open every new citation and check it.
3. **Append, don't rewrite.** At the end of the case file add:

   ```
   ## Recheck — enforcement properties (guided, YYYY-MM-DD, blind, E1–E4)

   | Field | Content |
   |-------|---------|
   | **E1 Counted quantity** | … |
   | **E2 At the limit** | … |
   | **E3 Owner and multiplier** | … |
   | **E4 Budget domain** | … |
   | **OOM lead** | one line, or `none` |

   **Real-memory estimate:** `same as Estimate`, or positive / negative / undetermined, with the question that decides it
   **Stage-4 claim to add:** `none`, or the claim
   ```

   Leave every earlier section, the Estimate and the stage-4 feedback as filed. Keep the section
   under about 60 lines.
4. **Record leads conservatively.** Write an OOM lead only when an answer shows a concrete way real memory,
   at defaults, can exceed what the constraint governs: name the mechanism and a rough magnitude. A
   theoretical overshoot by one item is not a lead. The session that started you copies each lead
   into the system's OOM lead list (you do not open it).
5. Do not run Cassandra and do not start stage 4.
