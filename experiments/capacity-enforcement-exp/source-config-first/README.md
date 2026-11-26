# Lead source: config-first (added 2026-11-25, owner)

> **Paths (multi-system layout).** This is a system-agnostic method doc. Per-system data lives in
> `experiments/capacity-enforcement-exp/<system>/source-config-first/`.

## Why

Stage 1 (CodeQL) starts from code: it finds enforcement places and capacity-set places (README §3.7).
Then stage 2 bands each unit by name, and stage 3 reads the units in band order. A configuration entry
reaches a case only if one of its places was found, banded high enough and read. Phase 2's OOM candidates
come from these case files through stage 5. So an entry whose value limits memory without any place
CodeQL finds never reaches phase 2. One example is a value used as a size or a count several calls away
from any comparison. Another is a limit that ships disabled. Entries whose units were banded D or are
still queued are also missed.

The config-first source starts from the other end: **every configuration entry**. It rules out the
entries phase 1 already covers and traces the rest forward from the declaration, so the gap can be
measured and then closed.

## Steps

| Step | What it does | Agents | Output (per system) |
|---|---|---|---|
| **1. Coverage diff** | Lists every configuration entry (yaml/XML entries, JVM properties) and puts each in a tier (below) by how far phase 1 and phase 2 already reach it | none (a script) | `config-coverage.csv`, counts in `README.md` |
| **2. Banding** | The entries with no case (tiers 3–6, in scope) are banded A–D for memory relevance from the name, the declaration's comment and the shipped default, as stage 2 does; tier 2 entries follow at lower priority | one banding agent per batch | `config-bands.csv` |
| **3. Forward trace** | A stage-3 autonomous agent starts at the entry's declaration, follows the value to every place it restricts memory or disk, and writes **one ordinary stage-3 case file per place**, with the header row `Lead source \| config-first`; a place that already is a case target is skipped | fresh agent per entry | case files in `<system>/stage3-ai-deep-read/cases/` |

Stages 4 and 5 then treat these case files like any other. Phase 2 reads the candidates from stage 5,
and each candidate row already names its case file. **The case's `Lead source` row gives a true-positive rate
per lead source**: CodeQL (no row), config-first or consumer-first.

### Tiers (step 1)

| Tier | Meaning | Next |
|---|---|---|
| `1-case-constraint` | the entry is the constraint of a phase-1 case (stem prefix or §A1) | ruled out |
| `2-case-mentioned` | named in a phase-1 or phase-2 case file, but not as the constraint | banded after tiers 3–6 |
| `3-unit-reads-it` | no case; a stage-1 unit's expression names the entry or a getter that reads it | banded |
| `4-unit-nearby` | no case; a stage-1 unit lies within 30 lines of a read of the entry | banded |
| `5-no-unit` | no case; the entry is read, but no stage-1 unit is near any read | banded (CodeQL's gap) |
| `6-not-read` | not read in the main source tree (deprecated, unused, or read only through reflection or tools) | banded only on a name hint |

`scope = out` marks JVM properties that only serve tests, the JDK, logging or JMX. `name_hint` is a
keyword prefilter (size, capacity, threshold, queue, threads, …): it orders the work but does not rule
anything out.

**Limits of step 1.** It matches text, not data flow. An entry is "read" through its getters
(`DatabaseDescriptor`, `GuardrailsOptions` for Cassandra) and direct field access, so a value passed on
through other variables can make tiers 3–4 miss a unit. Tier 5 is therefore an upper bound on CodeQL's
gap, and the banding and forward trace settle each entry.

## Rules

- **Default constraints only** (phase-2 scope rule, 2026-11-23) applies to the candidates, not here:
  phase 1 records the constraint whatever its default.
- **Method source:** the forward trace reuses the constraint-first method of the paused
  [`entry-restriction-exp`](../../entry-restriction-exp/README.md), but each place is written up as a
  stage-3 case file, so the existing stages 4 and 5 apply unchanged. Its pairs are not imported.
- **Not covered here:** per-table options (CQL `WITH …` parameters) and hard-coded constants. Constants
  are the non-config agent's job (stage 3), and memory with no constraint at all is the consumer-first
  source's job ([`../source-consumer-first/README.md`](../source-consumer-first/README.md)).

## Status

| System | Step 1 | Step 2 | Step 3 |
|---|---|---|---|
| Cassandra | done 2026-11-25 ([counts](../cassandra/source-config-first/README.md)) | not started | not started |
| Hadoop | not started | – | – |
