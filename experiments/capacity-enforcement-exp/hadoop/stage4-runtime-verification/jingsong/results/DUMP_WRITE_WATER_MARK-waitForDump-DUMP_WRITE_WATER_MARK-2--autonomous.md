# DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-2--autonomous — stage-4 results  <!-- file: results/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-2--autonomous.md -->

> **Case:** [`DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-2--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-2--autonomous.md) (queue order 15; check `OpenFileCtx.java:284`)
>
> **Status:** verdict filed (run 1 + self-check; no run 2) — 2026-11-25
>
> **Outcome class:** **true positive** — estimate `positive`, effect `caps` in both tiers (a dump-failure bypass is recorded from the unit probe).
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); the feedback section is D.

Drafted outside the repository (`~/writeup-hadoop/out/o15/`); paths below marked `run1/…` are relative to that folder.
Harness: `~/writeup-hadoop/out/o15/harness/`. Amended case file: `~/writeup-hadoop/out/o15/case-amended.md`.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository file at commit `bef6bc8a` (sha256 `16dec81e…6cf9e`, as in `_INDEX.md` §4). After the audit's three dated amendments (2026-11-25): sha256 **`3b8bfc582ed4982800f2973b95be0f8ecdd81af31cb33f4eee56ed6e2f976e5a`** (`run1/frozen-sha256.txt`), recorded before any reading. Section D feedback was added after the run and is not part of the frozen version. |
| **Harness** | `harness/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-2--autonomous/`: `TestDumpWaterMark.java`, `unit-run.sh`, `check-unit.py`, `cluster-run.sh`, `oow.py`, `analyze.py` (staged at `~/writeup-hadoop/out/o15/harness/`, not committed: no commit asked for) |
| **Tiers and values** | Unit: M = 256 KiB, 1 MiB (default), 4 MiB; control dump disabled; sequential sub-test; bypass probe. Cluster: M = 1 MiB (stock jar), 8 MiB, 64 MiB, `Long.MAX_VALUE` (positive control); sequential control on stock jar |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Met | A2/B1: heap bytes of out-of-order WRITE payloads per open file (`nonSequentialWriteInMemory`, payload bytes) |
| A | knob varied, ≥ 3 values incl. default | Met | B2b: 256 KiB / 1 MiB / 4 MiB by reflection; B3b: 1 / 8 / 64 MiB by rebuilt jar, plus no-cap control. Not configurable (A1), so reflection/jar patch is the stated approach |
| A | real resource measured, not only the counter | Met | B2d: referenced `WriteCtx.data` bytes and dump-file length; B3d: `[B` histogram after forced GC, dump-file size, RSS |
| A | usage driven to the limit and past it | Met | B2c 15.9 MiB (4–64× the mark); B3c 256 MiB (4–256× the mark) |
| B | each step says what it establishes | Met | B2g/B3g rows and B2h/B3h controls |
| B | prediction in numbers | Met | B2f/B3f exact byte values per arm |
| B | every plausible outcome has a row | Met | over-limit, linear growth, same ceiling, control flat, proxy-only, bypass rows all present |
| B | confirmation needs ceiling-follows-knob and disallow evidence | Met | sawtooth period follows M; dump file in steps of M is the disallow (spill) evidence |
| B | alternative explanations and controls | Met | no-dump / `Long.MAX_VALUE` positive control, sequential control, `counted + dump == k·r` |
| C | a human can follow it | Met | B1 + B2f/B3f |
| C | an AI can run it without re-deriving the path | Partly | B2a/B3a assume `~/hadoop-3.4.2`, `start-dfs.sh`, and a privileged secure starter that the nodes do not have (amendments) |
| C | values, commands, observables exact | Met | |
| D | harness and environment prerequisites | Partly | harness listed as work; environment differences fixed by amendment |
| D | workload arithmetic reaches the limit | Met | 256 MiB in a 1 GiB gateway heap; ~0.5 GiB disk per arm |
| D | load-bearing citations spot-checked | Met | `OpenFileCtx.java:73,179,251,278,284,294,349-361,383`; `WriteCtx.dumpData`; `RpcProgramNfs3` dump-dir clear; `WriteManager:182-185`; `Nfs3Utils.writeChannel` null channel; `checkCommitInternal` (large-file upload path answers COMMIT with a hole as success, so a `sync` mount does not stall) |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: use `copy-source.sh`, skip `-am install`, run `mvn -o` | Applied, amendment 2026-11-25 (B2a) | environment.md; no change to B2f |
| 2 | B2c/B2e: run each call on a worker thread with a 10 s wait so a block is recorded, then free the writer; second writer after the block (extra) | Applied, amendment 2026-11-25 (B2c) | needed to observe step 5 cleanly; instrument only |
| 3 | B3a/B3e: copy the built dist, build jars offline in the copy, `hdfs --daemon` instead of `start-dfs.sh`, gateway as `$USER` (no jsvc), `soft` mount, request size/order from `OpenFileCtx` DEBUG lines | Applied, amendment 2026-11-25 (after B3e) | runbook would not run as written on these nodes; B3f/B3g unchanged |
| 4 | Stage 3: per-step dump growth at 1 s sampling cannot resolve 1 MiB steps; name the dumper's "Before dump == M / After dump == 0" debug lines as the step evidence | Left for stage 3 | used here as evidence; wording only |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25, 03:50–04:13 MST (node clock) |
| Node | `pc72` (`node2.jason92-326665`, CloudLab UMass, 40 cores, 125 GiB RAM) |
| OS / kernel | Ubuntu 22.04.2 LTS / `5.15.0-203-generic` |
| JDK | OpenJDK `1.8.0_514` (`/usr/lib/jvm/java-8-openjdk-amd64`); Maven 3.6.3 |
| Local source copy | `copy-source.sh` from `systems/hadoop/source/` at repository commit `cd9e1cde` → `/mydata/jingsong-s4/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-2-run1/src` (`rel/release-3.4.2`) |
| Distribution | copy of `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` (node build of 2026-11-24) |
| Case-file commit / harness | `bef6bc8a` + amendments (sha256 above) / not committed |
| Storage | `/mydata` local LVM (753 GB); dump dir, NN/DN data under the run folder |
| Portmapper | system `rpcbind`; the gateway (as `jason92`) registered `mountd` and `nfs` with it, so the fallback was not used (`run1/driver-m1.out`) |
| Full logs | node: `…-2-run1/logs/` (bulk deleted, small logs kept); local copies: `~/writeup-hadoop/out/o15/run1/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Commit |
|---|---|---|---|---|---|---|
| 1 | audit | B2a | `~/hadoop-3.4.2` does not exist; `-am install` unnecessary | `copy-source.sh`, `mvn -o` | amendment 2026-11-25, before run 1 | not committed |
| 2 | audit | B3a/B3e | `start-dfs.sh` needs ssh to localhost (unavailable); no jsvc for the secure starter | `hdfs --daemon start …`; gateway as `$USER` | amendment 2026-11-25, before run 1 | not committed |

No step failed during run 1.

## 4. Run 1

**Scope:** both tiers, all values. **Command logs:** `run1/unit/unit-run.log`, `run1/cluster-run.log`, `run1/driver-m1.out`, `run1/driver-rest.out`.

### 4.1 Readings

**Unit tier** (`mvn -o test -Dtest=TestDumpWaterMark`: Tests run 6, Failures 0, Errors 0 — `run1/unit/org.apache.hadoop.hdfs.nfs.nfs3.TestDumpWaterMark.txt`)

| Test or assertion | Result | Evidence |
|---|---|---|
| M = 256 KiB: counted after write k = (k mod 4)·r for all 255 rows; dump steps {262,144}; final dump 16,515,072; log peak 262,144 | as predicted (0 mismatches) | `run1/unit/readings.csv`, `run1/unit/check-unit.txt` |
| M = 1 MiB: (k mod 16)·r; steps {1,048,576}; final dump 15,728,640; log peak 1,048,576 | as predicted (0 mismatches) | same |
| M = 4 MiB: (k mod 64)·r; steps {4,194,304}; final dump 12,582,912; log peak 4,194,304 | as predicted (0 mismatches) | same |
| max counted after any returned call | 196,608 / 983,040 / 4,128,768 (all < M) | `SUMMARY` rows |
| counted == referenced payload bytes, counted + dump == k·r | 0 violations in every arm | `SUMMARY` (`heldViolations=0`, `sumViolations=0`) |
| control (dump disabled): counted = k·r up to 16,711,680, no dump file | as predicted | `SUMMARY,control` |
| sequential sub-test: counted 0, state `NO_DUMP` | as predicted | `SEQ` row |
| cleanup deletes the dump file | yes in all three capped arms | `CLEANUP` rows |
| bypass probe (dump dir missing, M = 1 MiB): write 16 does not return in 10 s; "Got failure when creating dump stream" logged; `enabledDump=false` | as predicted (block observed) | `BLOCKED,probeMissingDir,…,16`, `SUMMARY,probeMissingDir` |
| extra: a second writer then adds 16 more out-of-order writes, all return; counter 2,097,152 (2× mark) while the first writer stays blocked | observed | `PROBE2` row |

**Cluster tier** (one 256 MiB file per arm, 4095 out-of-order 64 KiB writes, 120 s hold; `run1/cluster/analyze.txt`)

| Value | Arm | Observable | Reading | Prediction | Evidence |
|---|---|---|---|---|---|
| 1 MiB | A (stock) | dump file at hold | 267,386,880 (mod M = 0) | 267,386,880 | `arm-m1/dump-hold.txt` |
| 1 MiB | A | counter at hold (log) / max | 983,040 / 1,048,576 | 983,040 / 1,048,576 | `arm-m1/counter-at-hold.txt`, `analyze.txt` |
| 1 MiB | A | `[B` delta at hold | +447,264 B | < ~5 MiB | `arm-m1/histo-summary.txt` |
| 1 MiB | A | dump rounds; "Before dump" / "After dump" values | 255; all 1,048,576 / all 0; true-branch log line at `:285` 255× | steps of M | `arm-m1/nfs3-dump-excerpt.log`, `branch-284-counts.txt` |
| 8 MiB | B | dump at hold / counter at hold / max | 260,046,848 / 8,323,072 / 8,388,608 | same | `arm-m8/*` |
| 8 MiB | B | `[B` delta | +7,809,816 B | ≈ +8 MiB (8,323,072) | `arm-m8/histo-summary.txt` |
| 8 MiB | B | dump rounds | 31; Before = 8,388,608, After = 0 | | `analyze.txt` |
| 64 MiB | C | dump at hold / counter at hold / max | 201,326,592 / 67,043,328 / 67,108,864 | same | `arm-m64/*` |
| 64 MiB | C | `[B` delta | +66,359,272 B | ≈ +64 MiB (67,043,328) | `arm-m64/histo-summary.txt` |
| 64 MiB | C | dump rounds | 3; Before = 67,108,864, After = 0 | | `analyze.txt` |
| `Long.MAX_VALUE` | control | dump file / counter at hold | no file / 268,369,920 | no file / 268,369,920 | `arm-inf/*` |
| `Long.MAX_VALUE` | control | `[B` delta | +267,740,928 B | ≈ +256 MiB | `arm-inf/histo-summary.txt` |
| 1 MiB | sequential | counter updates / dump / `[B` delta | 0 / no file / −720,400 B | ~0 / no file / ~0 | `arm-seq/*` |
| all out-of-order arms | | `WriteCtx` instances at hold | 4095 | ≈ 4095 | `histo-summary.txt` |
| all | | WRITE size and order | 4095 increments of 65,536; offsets 65,536…268,369,920 consecutive, then 0 (hole); seq: 0…268,369,920 | as designed | `offset-order-check.txt`, `analyze.txt` |
| all | | client stable how | `FILE_SYNC` changed to `UNSTABLE` 4095× in each out-of-order arm, 0 in seq | (sync mount) | `nfs3-dump-excerpt.log` |
| all | | md5 after the hole is written | match in all five arms | match | `arm-*/md5.txt` |
| all | | OutOfMemoryError | 0 | | `analyze.txt` |
| all | | jar constant (`javap`) | 1048576 / 8388608 / 67108864 / 9223372036854775807 | | `arm-*/jar-const.txt` |

### 4.2 Conclusion and logic

1. **Validity.** The limit was reached many times in every capped arm: 63/15/3 unit spills and 255/31/3 cluster spills [observed: `readings.csv`, `analyze.txt`]. Hold-fixed settings: request size 65,536 and ascending order [observed: `offset-order-check.txt`], `nfs.wtmax`, `nfs.file.dump=true`, `nfs.stream.timeout=600000`, dump dir on local disk [observed: `run1/cluster-run.log` (hdfs-site)]; the jar in each arm carried the intended constant [observed: `jar-const.txt`]; a gateway restart cleared the dump dir between arms (empty `ls` before each mount) [observed: `driver-rest.out`]. Valid.
2. **Readings.** No outlier. `[B` deltas sit 0.5–0.7 MB below the payload bytes in the 8/64 MiB/no-cap arms, within baseline jitter (baselines vary by ±0.2 MB; the seq arm shows −0.7 MB) [observed: `histo-summary.txt`]. `hdfs dfs -stat %b` showed 134,217,728 B for the out-of-order files while the gateway still held them open (last block under construction); the md5 of the full 268,435,456 B content matched [observed: `md5.txt`]; not a B1 matter.
3. **Matched rows.** Unit B2g row 1, "Sawtooth with period q, counted after each call < M, dump grows in steps of M, for all three M → Claim confirmed at the mechanism level; the ceiling follows the knob": every row equals (k mod q)·r, max after-call counter < M, dump step set = {M} [observed: `check-unit.txt`, `SUMMARY`]. Cluster B3g row 1, "`[B` delta and 268,369,920 − dumpsize follow the table and scale with M; dump grows in steps of M → Claim confirmed": in-memory 983,040 / 8,323,072 / 67,043,328 exactly as B3f, `[B` deltas +0.45 / +7.8 / +66.4 MB, every dump round from M to 0 [observed: `analyze.txt`]; and B3g row 3, positive control moved: `Long.MAX_VALUE` kept 268,369,920 B counted and +267.7 MB `[B`, no dump file [observed: `arm-inf/*`].
4. **Excluded rows.** Unit: counter ≥ M after a call — never (max 0.94·M) ; dump not a multiple of M — final dump mod M = 0 in all arms; linear growth in a capped arm — no, sawtooth; same ceiling for 256 KiB and 4 MiB — no (196,608 vs 4,128,768); control flat — no (linear to 16,711,680); counted ≠ payload bytes — 0 violations; bypass probe returns — no (blocked) [observed: `readings.csv`]. Cluster: in-memory ≥ M at hold or +256 MiB in a capped arm — no; no-cap arm with a dump file or small delta — no; request sizes/order off — no; md5 mismatch — no [observed: `analyze.txt`, `md5.txt`].
5. **Observed vs. inferred.** The conclusion rests on observed readings. Inferred: (a) that the blocking of the RPC thread happens at the `:294-299` wait — supported by the `:285` "Asking dumper to dump" line (inside the true branch of `:284`) appearing once per spill [observed: `branch-284-counts.txt`] and by the unit block at k = 16 with the dumper dead; (b) that the `[B` delta is the payload — supported by `WriteCtx` count 4095 and the agreement with 268,369,920 − dump in three arms.
6. **Deviations and gaps.** Amendments 1–3 (environment only). Per-step dump growth was not sampled finer than 1 s; the step size is taken from the dumper's before/after lines and the final size mod M. RSS was sampled but is not a B3f observable (rose to 838,808 kB in the no-cap arm vs 679,020 kB at 1 MiB, consistent with the heap difference). The unit log capture was parsed for the peak only (no per-line copy kept).
7. **Core question.** Yes. The counted and the real (referenced/`[B`) heap of out-of-order payloads per open file rise to the mark and drop to 0 at each spill, the ceiling moves with the mark (256 KiB → 4 MiB in the unit tier; 1 → 8 → 64 MiB in the gateway, scaling with M), and with no cap the full 256 MiB stays in heap (parts 3, 4). The excess goes to the uncapped local dump file, exactly in multiples of M (part 3).

**Conclusion:** unit B2g row 1 — **confirmed**; cluster B3g rows 1 and 3 — **confirmed**.

## 5. Self-check of run 1 — AI

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | re-read `analyze.txt`, `jar-const.txt` ×5, `offset-order-check.txt`, hdfs-site block in `cluster-run.log` |
| 2. Readings | yes | re-read `histo-summary.txt` ×5, `md5.txt` ×5 |
| 3. Matched row | yes | re-ran `check-unit.py` on `readings.csv` (0 mismatches, step sets = {M}); `dump-hold.txt` sizes equal B3f to the byte |
| 4. Excluded rows | yes | each row checked against `SUMMARY`/`analyze.txt` values |
| 5. Observed vs. inferred | yes | `branch-284-counts.txt`: 255/31/3/0/0 true-branch lines = spill counts |
| 6. Deviations and gaps | yes | amendments in `case-amended.md` dated before the first reading (`frozen-sha256.txt` written 05:54:32 EST = 03:54:32 MST; unit run started 03:54:36 MST) |
| 7. Core question | yes | the chain hypothesis → dose (M) → ceiling + spill → positive control follows B1 |

### 5.2 Run 2?

**No** — 2026-11-25. Every load-bearing statement is observed, readings match predictions exactly, and the result confirms rather than refutes or adds a bypass row.

## 6. Run 2 — not done

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** **true positive** (positive, caps).

**Claim tested (B1):** out-of-order WRITE payloads that one open file holds in the NFS gateway heap are capped by `DUMP_WRITE_WATER_MARK`; after each request the counted bytes are below the mark (≤ mark + one request during it); the rest is in `<nfs.dump.dir>/<fileId>`; the in-memory amount follows the mark, and without the cap everything stays in heap.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (sawtooth, ceiling follows the knob); bypass probe blocked as predicted | caps (bypass recorded: after a dump failure the writer hangs and later writes to that file are not capped) | run 1 + self-check | 2026-11-25 |
| Cluster | **Confirmed** — B3g row 1, positive control (row 3) moved | caps | run 1 + self-check | 2026-11-25 |

**Feedback filed:** section D of the amended case file (`~/writeup-hadoop/out/o15/case-amended.md`); not written to the repository (task rule).
