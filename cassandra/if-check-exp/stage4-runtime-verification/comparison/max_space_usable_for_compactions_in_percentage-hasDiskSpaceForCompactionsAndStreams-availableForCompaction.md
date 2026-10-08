# max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction — the two paths side by side

> **Long path:** [`long-path/results/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md`](../long-path/results/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md)
>
> **Short path:** [`short-path/results/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md`](../short-path/results/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md)

Written 2026-10-08 by a separate AI session after both paths' runs were filed and committed (long: 2026-10-07; short:
`run-executor.py collect`, 2026-10-08, commit `3d6afa9`). The rules are in the README's
[Two paths, two tiers each](../README.md#two-paths-two-tiers-each). It edits neither solution nor any results file, and **rates
nothing**: it reports.

## 1. Verdicts

| Path | Tier | Verdict (row of that path's own table) | Results file | Date |
|---|---|---|---|---|
| Long | Unit | **Confirmed**: the check's arithmetic is exact at `pct` 0.95 · 0.5 · 0.1 · 0.01; the ladder gives 1 · 3 · 6 · 8 passes (n = 0 · 2 · 5 · abort) at `B / total` 1.5 · 0.8 · 0.4 · 0.1; upstream `DirectoriesTest`, `CompactionsBytemanTest`, `PartialCompactionsTest` pass | long §8 | 2026-10-07 |
| Long | Cluster | **Confirmed** (first row of §9a's Conclusions): n = 0 · 0 · 2 · 5 · abort at 0.95 · 1.5 · 0.8 · 0.4 · 0.1, in-flight n = 5 against 0; **H1 as predicted** (the hatch does not cover `nodetool compact`); **H2 bypass as recorded** (a background compaction wrote 10 × the budget with the check off) | long §8 | 2026-10-07 |
| Short | Unit | **Confirmed**: B2g row 1 (budget = `round(usable × pct)` at 1.0 · 0.95 · 0.5 · 0.0) and row 3 (gate admits budget − 1, rejects budget + 1 for every pct > 0); B2h control linear | short §8 | 2026-10-08 |
| Short | Cluster | **Not confirmed: no B3g row fits the knob comparison.** B3f's pct = 1.0 row refuted (11 `Reducing scope` WARNs, 3 of 14 SSTables compacted); B3f's pct = 0.5 row holds; B3g row 4 (flushes grow the data dir past the pct budget) confirmed | short §8 | 2026-10-08 |

All four tiers were run; none was declared `n/a`. Neither path did a run 2.

## 2. Do the conclusions agree?

**Partly.** The unit tiers agree. The cluster verdicts differ, but the two paths' cluster readings agree on the mechanism.

- **Unit tier: agree.**
  - Both find the budget equals `round((usable − min_free) × pct)` exactly, and the gate splits at that figure.
  - Long also drives a real `CompactionTask` through the reduce-scope ladder (`CompactionLadderTest`).
- **Cluster tier: the verdicts differ, and the difference is in the design's prediction, not in what the node did.**
  - **Both paths read the same budget formula from the node's own debug line, to the byte:** `pct × (free − min_free)`, with free space
    taken at check time.
    - Long: `available = round((U − 50 MiB) × pct)` in every arm, from the `df` read before the trigger.
    - Short: 411,447,296 = (421,933,056 − 10 MiB) × 1.0 and 205,625,344 = (421,736,448 − 10 MiB) × 0.5.
  - **Both paths saw the compaction reduced one input at a time until it fit.**
    - Long: the largest input dropped at each pass; 2 dropped at 0.8, 5 at 0.4, and an abort at 0.1.
    - Short: 11 dropped at 1.0 and 13 at 0.5.
  - **Both saw the written output stay within the budget.**
  - **Where the designs differ:** the short solution's cluster prediction (B3c/B3f) took the budget as `pct × capacity` of the 2 GiB
    filesystem. With ~1.6 GiB loaded first, free space was ~0.42 GB, so even pct = 1.0 could not admit the ~1.6 GB compaction.
    - The short executor flagged this at the audit, from the source alone (finding D2), before any reading. It ran the design as written
      because a short solution is never amended.
    - The long design took `pct` and the dataset from measured free space (`B / total` set per label, with the node stopped). Its
      prediction is therefore the formula the node used.
  - The short path's own conclusion is the same as the long path's: "the knob caps compaction-driven disk growth at pct × (free −
    min_free) measured at check time, not at pct × capacity". It therefore files **Not confirmed** against its own table. Neither path is
    overruled by the other.

## 3. What only one path's design produced

**Long path only**
- **The abort.** At `B / total` 0.1, eight passes, seven `Reducing scope` WARNs, an abort and `CompactionsAborted` +1, with inputs left
  untouched. This comes from a `pct` low enough that even the smallest single input exceeds the budget; short's lowest cluster value was
  0.5.
- **The escape hatch, both sides.**
  - H1: `compactionDiskSpaceCheck(false)` by JMX, then `nodetool compact`, is still refused, because `MAJOR_COMPACTION` is not
    `COMPACTION`.
  - H2: `nodetool enableautocompaction` with the check off writes 529.5 MB against a 53 MB budget (bypass).
  - Produced by the audit's source finding and the H1/H2 arms. Short's design has no hatch arm.
- **The in-flight term.**
  - The design ran `ks1.t2` once alone (I1) and once beside a throttled `ks1.slow` (I2). Alone it was admitted whole; beside `slow` it
    was shed to n = 5.
  - `requested − total` equals the slow task's remaining write from `system_views.sstable_tasks` to 0.02 %.
  - Produced by the I1/I2 arms, the 4 MiB/s throttle and the `sstable_tasks` sampler.
- **The default 0.95 at the cluster tier** (`d95`), and a ladder simulated from the Data.db lengths that matches every `requested` to the
  byte in 7 arms.
- **An independent self-check** (`run1/selfcheck.py`, 134 checks) that re-parses the raw `debug.log` and `system.log`.
- **Idle controls:** 30 s per label with no pass line, and `df`/`du` unchanged.

**Short path only**
- **Flush-driven growth ignores the knob** (B3g row 4). With autocompaction off, memtable flushes alone grew the data dir to 1.72 GB,
  past the budget the node itself logged before the load (1.07 GB at pct = 0.5). Produced by a load sized to ~1.5 GiB on a 2 GiB
  filesystem, with the budget read before and after it.
- **The budget read at two moments in one run:** before the load (2,136,104,960 / 1,068,052,480 B, exactly ½) and at compaction. This
  shows the same knob giving a budget that shrinks as the disk fills.
- **A non-default `min_free_space_per_drive` (10 MiB) at the cluster tier.** Long used the default 50 MiB there and varied the second
  knob only at the unit tier.
- **`pct = 0.0` at the unit tier** (budget 0; the gate admits 0 and rejects 1).
- **A RAM-backed data filesystem** (a 2 GiB tmpfs in a user namespace, without root). The `getUsableSpace()` reading matched `df` in a
  known-answer check.

## 4. Runbook defects

**Long path:** 1 defect, at the instrument check (not run 1).
- In `CompactionLadderTest`, `CompactionManager.instance.disableAutoCompaction()` missed the re-created table, so STCS merged inputs and
  18 checks gave `MISMATCH`. Fixed in the harness with `cfs.disableAutoCompaction()`.

Run 1 had no defect. Deviations recorded:
- A shakedown folder was moved aside by hand.
- Raw JMX counter values were not kept, only deltas.
- 3 labels were not shaken down.

The audit made 9 recommendations: 8 were applied as dated amendments to §9 before the freeze, and 1 was left for stage 3.

**Short path:** 7 defects, fixed in the harness; the solution is never amended.
- R1: no root for `mount -o loop`; replaced with a tmpfs in a user namespace.
- R2: placeholder paths; one local clone used for both tiers.
- R3: a namespace mount cannot outlive one script; one fresh filesystem and node per value.
- R4: the table, `nodetool` syntax and row count were not exact; the stress writes `ks.standard1`, loaded in 14 chunks of 500,000 rows.
- R5: `du -sh` / `df -h` are rounded; replaced with bytes, sampled every 2 s.
- H1: `-Dtest.methods` on the `@Parameterized` `DirectoriesTest` matched nothing; the unit tier was restarted with the whole class.
- H2: a `ps | grep` pre-check matched its own ssh command line; restarted with a match on `java` processes.

The audit made 4 recommendations for stage 3; the main one is to compute the budget from free space at check time.

**Blindness audit (short path, `collect-report.txt`): `BLINDNESS: FAIL`, 2 EXECUTED hits, 0 REFUSED.**
- Both hits are Bash reads under `~/.claude/projects/<workspace>/…`, classed "Claude Code state". HANDOFF says they are the executor's
  own spilled tool output (its own run log).
- Jingsong judged them harmless and the result was copied with `--force`. `check-blindness.py` has exempted that folder since `d42baba`.
- **The committed `collect-report.txt` is still the original FAIL report,** not a PASS re-run as HANDOFF states.
- Every D check (D1–D5) passed.

## 5. Cost

| Path | Tier | Runs | JVMs / nodes | Wall-clock |
|---|---|---|---|---|
| Long | Unit | 2 instrument runs, then run 1 on `pc66`: 3 upstream classes + `CompactionBudgetTest` + `CompactionLadderTest` | build/test JVMs only | test time ≈ 27 s in total (from the JUnit summaries); build time not recorded |
| Long | Cluster | shakedowns of 3 labels (`f08`, `f01`, `inflight`), then run 1: 6 labels (`d95`, `f15`, `f08`, `f04`, `f01`, `inflight`) | 1 node (`pc66`), 2 node starts per label (12), a fresh 4 GiB loop ext4 per label | run 1: 19:53:15 → 20:18:10 MDT, 2026-10-07 (≈ 25 min); shakedowns 3–5 min per label |
| Short | Unit | 1 failed attempt (H1), then run 1 on `pc57`: `DirectoriesTest` + `MaxCompactionSpaceOperandTest` | build/test JVMs only | 16:57 → 16:58 UTC, 2026-10-08, after a JDK/Ant install and build |
| Short | Cluster | 1 aborted pre-check (H2), then 2 values (1.0, 0.5) | 1 node (`pc57`; `pc50` listed but untouched), 1 node start per value, a fresh 2 GiB tmpfs per value | 17:12 → 17:18 and 17:22 → 17:28 UTC (≈ 6 min each); the whole executor session 12:51 → collect 13:42 EDT (≈ 50 min, setup included) |

Short executor: claude-opus-5-5, Claude Code 2.1.291, 53 tool calls.
