# MAX_KEY_SIZE-write-limit--autonomous — stage-4 results  <!-- file: results/MAX_KEY_SIZE-write-limit--autonomous.md -->

> **Case:** [`MAX_KEY_SIZE-write-limit--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/MAX_KEY_SIZE-write-limit--autonomous.md)
>
> **Status:** **verdict filed 2026-11-06** — unit **Confirmed** (does not cap), with one flag: the retained-heap reading `retainedDelta` missed A4's C ± 1 MiB in 1 of 9 rows (an instrument artefact, §4.2 part 6). Cluster **not run: n/a** (A7). Claim tested: the heap held by a `BoundedByteArrayOutputStream` is its capacity and does not follow `limit`; writes up to and past `limit` through `write(int)` allocate nothing. The check fired at write L+1 in every pass (102400 `EOFException`s per row); in-limit writes allocated 0.00 bytes per pass and past-limit writes exactly 1024 × 520 bytes (the exception objects) at every L from 1024 to 16 MiB; the positive control grew with W (×16384). One run 1, no run 2.
>
> **Outcome class:** **true negative** — stage-3 estimate `negative` against the stage-4 effect `does not cap` (unit tier; the cluster tier is n/a, so the class follows the unit tier as for the Cassandra n/a cases) ([definition](../../../../stage4-runtime-verification/README.md#outcome-class))
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Layout.** Hadoop, Jingsong's share: this file is in `hadoop/stage4-runtime-verification/jingsong/results/`; the case file is in
`hadoop/stage3-ai-deep-read/jingsong/cases/`; the harness is in `../harness/MAX_KEY_SIZE-write-limit--autonomous/`; the protocol is
[`../../../../stage4-runtime-verification/README.md`](../../../../stage4-runtime-verification/README.md#the-run-protocol);
the node is described in [`../environment.md`](../environment.md).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, repository HEAD `38acb6bf` plus the uncommitted case file (untracked at audit time). sha256 at filing (`_INDEX.md` §4, queue order 5): `4f3911cd75ba7160d73dac1f4cfd7e354a9e8be853dd9b72891bbea0d8d62224` (checked before the audit). After the audit's amendments A1–A7 (section D1), 2026-11-06 14:04 EST, before any harness run or reading: whole-file sha256 **`585ee2f6837d5c47ec8009f406ffbd9766a6d1b7c87526ce07b697b4991339d8`** (frozen version). Frozen prediction, conclusions and controls: sha256 of the text from `**B2f.` up to `**B2h.` (B2f + B2g with A4, A6) `992fa50ec7f6ca298318e495930fa80c3191a04ddbe487ac6a97491c3d54cd7e`; from `**B2f.` up to `### B3.` (adds B2h with A5) `0ee1fb22779eea19aca0c4984d2344ef141f9d15b5170d4e10e5f81a41c2b826`; the B3 section (n/a, with A7) from `### B3.` up to `**B4.` `8f8e9809619f7c2c0e4ace98d7abd6c690f60040510105f5b9d3ba94b75d9681`. Section D takes the feedback after the run, so the whole-file hash changes then; these text hashes do not. |
| **After the run** | Section D2 added 2026-11-06 after run 1: whole-file sha256 `ce6dbf60b493acf98065d151efaf4e5e1c12d71c2b4140da3ae06ac71dce0126`; the B2f–B2h and B3 text hashes above re-computed and unchanged. |
| **Harness** | `../harness/MAX_KEY_SIZE-write-limit--autonomous/` (written after this freeze, before run 1): `TestBoundedLimitHeap.java` md5 `266556fa`, `unit-run.sh` `783ff5d5`, `selfcheck.py` `26bef5a0`, `README.md`. Uncommitted at run time (the parent session commits). Instrument check: `unit-run.sh --compile-only` BUILD SUCCESS 14:07 (`run1/unit/unit-run.log`); known answer in the run itself (`IFCHK,instr`: a 1 MiB array read as 1048592 bytes, zero reading 0, heap 495 MiB, GC `Copy` = Serial, so A1's options applied). |
| **Tiers and values** | Unit (B2) only: C ∈ {65536, 1048576, 16777216} × L ∈ {1024, C/2, C}, W = L + 1024, 100 measured passes; TFile key path with `prepareAppendKey(-1)` / `(100)` and `writeInt`; control `ByteArrayOutputStream(32)` and `DataOutputBuffer` at the same W. Cluster (B3): **n/a** (compile-time constant; no daemon path reaches line 76; A7). |
| **Audit bottom line** | **Ready after amendments** — 2026-11-06 |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: heap bytes held and allocated by a `BoundedByteArrayOutputStream` (the TFile key buffer); the check's own operand `currentPointer` is named as the usage-side counter. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | A1: `MAX_KEY_SIZE` is a compile-time constant (`TFile.java:155`), so B2b varies the check's per-instance operand `limit` directly via `reset(L)`, L ∈ {1024, C/2, C} (C = 65536 with L = C is the TFile default), and the capacity C separately; the TFile path uses the real constant (`prepareAppendKey(-1)`) and a declared length 100. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d: thread allocated bytes (HotSpot) and retained heap after GC, besides `size()`; header-size gap named (±64 B). Retained heap resolves only ~±1 MiB (named in A3d). |
| A. Core question | usage driven to the limit and past it | Partly → Met | B2c drove past the limit by L writes per pass (impracticable at 16 MiB; see D). **Amended** (A2: 1024 past-limit writes per pass, every pass). |
| A. Core question | positive control (negative estimate) | Partly → Met | B2h named `ByteArrayOutputStream(32)` / `DataOutputBuffer` with "≈ 2·W" only. **Amended** (A5: bounds and a growth ratio); capacity C, which does set the allocation, is a second known-binding comparison with the same instrument (B2g row 3). |
| B. Logic | each step says what it establishes | Met | B2c/B2h: direct loop isolates line 76; TFile path ties it to the production class; control proves the instrument; exception baseline and warm-up rule out the alternatives. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met | B2f had exact failure indices and "< 1 KiB", but "≈ C", "flat" and "grows" were undefined. **Amended** (A4). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met | B2g lacked verdicts for rows 3–4, TFile rows, a missed-bound-but-flat row and an existing-test failure row. **Amended** (A6). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | For this negative file: the disallow branch's firing is observed directly (`EOFException` at write L+1, `size()` = L, exception count), and the control shows heap that follows the bytes written. |
| B. Logic | alternative explanations and their controls | Met | B2h: exception allocation (baseline at the same stack depth, A3a), JIT/class loading (warm-up), other threads (single thread, SerialGC), instrument broken (control, A3c). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, Ground, A3 steps 1–7, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met | B2a paths (`~/hadoop-3.4.2`, `/mydata/s4`) do not exist on the node, and `-DargLine` is ignored by this build (`hadoop-project/pom.xml:187, 2469`). **Amended** (A1). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | Pass structure and "per pass" were ambiguous; CSV lacked the exception cost. **Amended** (A2, A3). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Test class and run script are step-1 work (B2e). JDK 8, Maven 3.6.3, `~/.m2` 3.4.2 artifacts present on `pc41` (`environment.md` §1, §3). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly → Met | As filed, L = 16 MiB × W = 2L × 100 passes = 1.6 × 10⁹ exceptions (hours). After A2: ≈ 2.6 × 10⁹ single-byte writes in all, 9 × 102400 exceptions, ≤ 3 × 16 MiB live arrays under `-Xmx512m`; a few MiB of TFile files on `/mydata`. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `systems/hadoop/source/` (HEAD `38acb6bf`, clean): `BoundedByteArrayOutputStream.java:45-56` (alloc), `:63-71` (`resetBuffer`), `:76-79` (check, throw, store), `:91-95`, `:103-108` (`reset(int)`), `:140-142` (`size`); `TFile.java:155`, `:289-290`, `:418-431` (`KeyRegister`), `:527-536` (`prepareAppendKey`), `:57`, `:1291`; `AggregatedLogFormat.java:150, 492, 505-541`; `FileSystemApplicationHistoryStore.java:738, 756, 788-789`; `IFileOutputStream.java:96-98`. All as cited, except the minor note R2. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 (A1) | Node paths, no install build, surefire options through `maven-surefire-plugin.argLine`, read surefire counts | Applied 2026-11-06 (uncommitted; frozen sha256 above) | filed paths do not exist; `-DargLine` is ignored by this build |
| R2 | A3 step 4 says the Writer's `errorCount` is left raised by a failing key write; in fact `KeyRegister.close` is the only place it is touched (`TFile.java:434-446`) and the Writer simply stays in state `IN_KEY` until `close`. The "fresh Writer per failing case" rule is right either way | Left for stage 3 | not load-bearing for the claim |
| R3 (A2) | `W = L + 1024`, warm-up + 100 passes, an in-limit-only loop | Applied 2026-11-06 | `W = 2L` is not runnable at L = 16 MiB and the exception subtraction would swamp the 1 KiB bound |
| R4 (A3) | Exception cost at the same stack depth; instrument zero and support check; retained-heap definitions; CSV columns | Applied 2026-11-06 | needed for an unambiguous reading |
| R5 (A4, A5, A6) | Numbers for "≈/flat/grows", the control's bounds, a verdict for every row, missing rows | Applied 2026-11-06 | every plausible outcome needs a row before any reading |
| R6 (A7) | Re-check the B3 n/a; do not run the optional `jmap` check (it does not execute line 76) | Applied 2026-11-06 | a tier is never silently dropped |

**Agreement criteria** — only if run 2 is chosen (see 5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-11-06 (instrument check 14:06:57–14:07:19 EST, counted run 14:07:25–14:08:35; diagnostic of §4.2 part 6 at 14:12) | not done |
| Node | `pc41` = `node0.jason92-323989.misconfiguration-pg0.cloudlab.umass.edu` (the local node), 40 cores, 251 GiB; no Java process before the run (`jps`); shared with Yang's node and with Jingsong's concurrent `DF_getAvailable-…` case; this case started no daemon and used no port | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` | — |
| JDK (`java -version`) | OpenJDK `1.8.0_504` (`/usr/lib/jvm/java-8-openjdk-amd64`), surefire JVM `-Xmx512m -XX:+UseSerialGC` (confirmed in `IFCHK,instr`: max heap 518979584, GC `Copy`) | — |
| Build tool | Apache Maven 3.6.3; artifacts from the node's `~/.m2` (3.4.2, built 2026-11-06); `hadoop-common` module compiled in the copy | — |
| Local source copy | `/mydata/jingsong-s4/MAX_KEY_SIZE-write-limit-run1/src`, made by `../copy-source.sh` from `systems/hadoop/source/` at HEAD `38acb6bf` (clean), tag `rel/release-3.4.2`; only `TestBoundedLimitHeap.java` added (`git status` in `run1/unit/unit-run.log`) | — |
| Case-file commit / harness commit | `38acb6bf` + the uncommitted case file at sha256 `585ee2f6…` (A1–A7) / uncommitted, md5 in §1 | — |
| Storage for node data | `/mydata/jingsong-s4/MAX_KEY_SIZE-write-limit-run1/tmp` (local disk; TFile files of a few KiB, deleted at the end); nothing on `/proj` | — |
| Full logs (path, outside the repo) | `/mydata/jingsong-s4/MAX_KEY_SIZE-write-limit-run1/logs/unit/` (`unit-run.log`, `mvn-test-ifchk.log`, `mvn-test-existing.log`, `compile.log`, surefire reports and `-output.txt`, `ifchk.csv`, `selfcheck.txt`); diagnostic in `…/diag/` | — |

## 3. Runbook defects

None. Every step of B2e (as amended by A1–A6 before the run) ran as written.

## 4. Run 1

**Scope:** unit tier, all 9 (C, L) rows, the three TFile cases, the 18 control rows, the two existing test classes. Cluster tier not run (n/a, A7). **Command log:**
`MAX_KEY_SIZE-write-limit--autonomous/run1/unit/unit-run.log` (instrument check and counted run). Raw CSV: `run1/unit/ifchk.csv` (the `IFCHK` lines of the surefire `-output.txt`).

### 4.1 Readings

**Unit tier — direct rows** (`run1/unit/ifchk.csv`; every row: `W = L + 1024`, `sizeAtFail = L`, `exceptions = 102400`, `badPasses = 0`, `bufIdentitySame = true`, `bufLength = C`, `excCost = 520.00`, `allocZero = 0`)

| C | L | failIndex | allocCtor | allocWrites / pass | allocIn / pass | residual / pass | retainedDelta | retainedLoop |
|---|---|---|---|---|---|---|---|---|
| 65536 | 1024 | 1025 | 65616 | 532492.96 | 0.00 | 12.96 | 60808 | 1280 |
| 65536 | 32768 | 32769 | 65584 | 532480.00 | 0.00 | 0.00 | 65584 | 0 |
| 65536 | 65536 | 65537 | 65584 | 532480.00 | 0.00 | 0.00 | 65584 | 496 |
| 1048576 | 1024 | 1025 | 1048624 | 532480.00 | 0.00 | 0.00 | 1048624 | 0 |
| 1048576 | 524288 | 524289 | 1048624 | 532480.00 | 0.00 | 0.00 | **0** (= C − 1 MiB, at the bound) | 0 |
| 1048576 | 1048576 | 1048577 | 1048624 | 532480.00 | 0.00 | 0.00 | 899976 | −37216 |
| 16777216 | 1024 | 1025 | 16777264 | 532480.00 | 0.00 | 0.00 | 16777264 | 0 |
| 16777216 | 8388608 | 8388609 | 16777264 | 532480.00 | 0.00 | 0.00 | 16777264 | 8064 |
| 16777216 | 16777216 | 16777217 | 16777264 | 532480.00 | 0.00 | 0.00 | **−6872** (outside C ± 1 MiB) | 1776 |

**Unit tier — other readings**

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Instrument | supported, enabled; zero 0; 1 MiB array → 1048592 bytes | `run1/unit/ifchk.csv` (`IFCHK,instr`) |
| TFile `writeByte`, `prepareAppendKey(-1)` | fails at call **65537**, `size()` 65536, key buffer 65536 / limit 65536; Writer alloc 131608; loop alloc 520 = one `excCost` → residual 0 | `run1/unit/ifchk.csv` (`IFCHK,tfile`) |
| TFile `writeByte`, `prepareAppendKey(100)` | fails at call **101**, `size()` 100, limit 100; Writer 131608; loop 520, residual 0 | same |
| TFile `writeInt`, `prepareAppendKey(-1)` | fails on int **16385**, `size()` 65536; Writer 131608; loop 520, residual 0 | same |
| Control `ByteArrayOutputStream(32)` | alloc/pass 4176 (W 2048) … 67109168 (W 16778240); ratio 2.04–4.00; ×16070 from smallest to largest W | `run1/unit/ifchk.csv` (`IFCHK,control`) |
| Control `DataOutputBuffer` | 4256 … 67109248; ratio 2.08–4.00; ×15768 | same |
| Surefire `TestBoundedLimitHeap` | 3 run, 0 failures, 0 errors | `run1/unit/org.apache.hadoop.io.TestBoundedLimitHeap.txt` |
| Existing `TestTFileStreams` / `TestBoundedByteArrayOutputStream` | 19 / 2 run, 0 failures, 0 errors | `run1/unit/org.apache.hadoop.io.file.tfile.TestTFileStreams.txt`, `…TestBoundedByteArrayOutputStream.txt` |

**Cluster tier** — not run (n/a, A7).

### 4.2 Conclusion and logic

1. **Validity** — valid. The limit was reached and passed in every pass: first failure at L + 1 in all 100 passes of all 9 rows (`badPasses` 0), 102400 exceptions per row [observed: `run1/unit/ifchk.csv`]. The fixed settings held: Serial GC and a 495 MiB heap in the test JVM, single test thread, instrument supported and enabled with a correct known answer [observed: `IFCHK,instr`]; all surefire counts clean, including the existing tests [observed: the three surefire `.txt` files].
2. **Readings** — the writes are exact: in-limit writes allocated 0.00 bytes per pass in every row, and past-limit writes allocated exactly 1024 × 520 = 532480 bytes per pass (the exceptions) in 8 rows, 12.96 bytes more in the first row (first-row warm-up; still < 1024) [observed]. One unusual reading: `retainedDelta` (heap after GC, after vs. before construction) is −6872 in the row C = 16 MiB, L = 16 MiB and 0 in the row C = 1 MiB, L = 512 KiB, against ≈ C elsewhere [observed]. See part 6.
3. **Matched row** — B2g row 1: "`allocWrites` ≈ 0 for all L, `retainedDelta` ≈ C regardless of L, failure at L+1; control grows ≈ W" with A4/A5 numbers: `allocInPerPass` 0.00 < 1024 and `residualPerPass` ≤ 12.96 < 1024 in every row; failure at L + 1, `sizeAtFail` L, same buffer of length C; `allocCtor` C + 48..80 (A4: ≤ C + 256); `|retainedLoop|` ≤ 37216 ≤ 1 MiB; TFile 65537 / 101 / 16385, residual 0, Writer 131608 ≥ 131072; control within [W, 4W + 1024] in all 18 rows and ×16070 / ×15768 > 1000 [observed: `run1/unit/ifchk.csv`, `run1/unit/selfcheck.txt`]. `retainedDelta` within C ± 1 MiB in 8 of 9 rows; it misses in one row (part 6), so the row is matched **with a flag**, as the Cassandra cases did with a missed tolerance.
4. **Excluded rows** — *Refuted, allocation or retained heap grows with L or W* (row 2, A4 "grows"): at C = 16 MiB `allocInPerPass` and `residualPerPass` are 0.00 at both L = 1024 and L = 16 MiB (difference 0 against the 167 762 threshold); no row has `allocIn` ≥ 1 % of L; `retainedLoop` ≤ 8064 B; identity never changes [observed]. *Failure at another index / no `EOFException`* (row 4): every first failure at L + 1 [observed]. *Control does not grow / instrument −1* (row 5): control ×16070, instrument supported [observed]. *Limit never reached* (row 6): 102400 exceptions per row [observed]. A6 rows: *missed bound but flat* — no allocation bound missed [observed]; *TFile failure elsewhere*, *TFile key loop ≥ 64 KiB*, *Writer < 131072* — 65537/101/16385, residual 0, 131608 [observed]; *existing tests fail* — 0 failures [observed].
5. **Observed vs. inferred** — The claim rests on observed allocation counts. Inferred: (a) that the 520 bytes per throw are the `EOFException` objects and not buffer growth [inferred: `excCost` measured at the same stack depth equals the per-throw cost to the byte, and `allocIn` with no throws is 0.00]; (b) that the one off `retainedDelta` is an artefact of the measurement, not of the stream (part 6) [inferred from a diagnostic and from `allocCtor`/`bufLength`, see part 6].
6. **Deviations and gaps** — (i) **`retainedDelta` flag.** In the row C = 16 MiB, L = 16 MiB, `retainedDelta` = −6872 instead of C ± 1 MiB. `retainedDelta` is measured right after construction, before any `reset(L)` or write, so L cannot affect it; the same row shows `allocCtor` = 16777264 and a reachable buffer of length 16777216, and `retainedLoop` after the 100 passes is +1776. A diagnostic run after the readings (`run1/unit/RetDiag.java`, `run1/unit/retdiag.txt`; the same `used()` routine, the same JVM options, constructions only, no writes) reproduces the pattern deterministically: in a loop that constructs streams and sets the reference to `null`, the previous iteration's stream is still counted in the "before" reading in some iterations (three constructions each at C = 64 KiB, 1 MiB, 16 MiB: deltas −2791944 (JVM start-up garbage) / 65584 / −264, 1048624 / 0 / 1048624, 15728640 / 16777264 / 0, identical in two JVMs), so `retainedDelta` reads C − C_previous. The miss is a fault of the retained-heap instrument across rows (the previous row's stream still reachable at the "before" GC), not a reading of this stream; A3d had already named retained heap as the weak instrument. The frozen numbers are not changed; the flag stands. (ii) The cluster tier is n/a (A7); the optional `jmap` check was not run because no daemon path executes line 76. (iii) Allocation by JDK code inside `getThreadAllocatedBytes` is included in every reading; its zero reading is 0.
7. **Core question** — Usage did not follow the constraint. The check fired exactly as traced (cursor stopped at L, `EOFException` at write L + 1, in the direct stream and in the TFile key buffer at the real `MAX_KEY_SIZE` 65536) — parts 1, 3. Heap was set by the capacity at construction (`allocCtor` = C + 48) and writing up to the limit allocated nothing (0.00 bytes per pass) at every limit from 1 KiB to 16 MiB; going past it cost only the exception objects (520 bytes each), the same at every L — part 3. The same instrument saw heap follow the bytes written in the control (×16070) — part 3. So the check bounds a cursor in a fixed buffer; it does not cap memory.

**Conclusion (one line):** Unit: B2g row 1 — confirmed (flag: `retainedDelta` missed C ± 1 MiB in 1 of 9 rows, instrument artefact, part 6). Cluster: not run (n/a).

## 5. Self-check of run 1 — AI

`../harness/MAX_KEY_SIZE-write-limit--autonomous/selfcheck.py` re-parses the raw surefire `-output.txt` and the surefire reports (not the run script's `ifchk.csv`); output `run1/unit/selfcheck.txt`: 125 PASS, **1 FAIL** (`C=16777216 L=16777216 retainedDelta in C +- 1 MiB: -6872`).

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.txt`: failIndex/sizeAtFail/badPasses, 102400 exceptions per row, surefire 3/0/0, 19/0/0, 2/0/0; `IFCHK,instr` heap 518979584, GC `Copy` |
| 2. Readings | yes | `ifchk.csv`: allocIn 0.00 ×9, residual 12.96 then 0.00 ×8; `retainedDelta` −6872 and 0 as stated |
| 3. Matched row | yes, with the flag | every A4/A5 check passes in `selfcheck.txt` except one `retainedDelta`; the flag is recorded, not hidden. The matched row's own content ("retainedDelta ≈ C regardless of L") holds in the sense that matters: the one miss is in a reading taken before any L was applied |
| 4. Excluded rows | yes | `selfcheck.txt` "grows test … not met" (0.00 − 0.00 vs 167762) ×2; no `allocIn ≥ 1 % of L`; `retainedLoop` all within ±1 MiB; control rows all PASS |
| 5. Observed vs. inferred | yes | (a) `excCost` 520.00 in every row and `allocWritesPerPass` 532480.00 = 1024 × 520 exactly; (b) `retdiag.txt` shows the same alternating deltas with no write at all |
| 6. Deviations and gaps | yes | the artefact cannot bear on the claim: the claim's refuted-if concerns allocation and retention across writes, which `allocIn`, residual and `retainedLoop` measure, all within bounds |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B2h logic: direct loop at three L per C → no allocation change; TFile at the real constant → same; control → instrument sees growth. Matches B1's refuted-if (not met) |

### 5.2 Run 2?

**No** — decided 2026-11-06. The readings are exact (0.00 bytes per pass; exception cost equal to the byte), the result confirms the stage-3 estimate rather than refuting it or confirming a bypass, the positive control moved, and the one inferred statement (the `retainedDelta` artefact) is settled by a diagnostic from run 1's own routine. A run 2 would repeat the same deterministic counts.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason. In particular, the `retainedDelta` flag (§4.2 part 6) was judged an instrument artefact and the tier Confirmed; a stricter reading of A6 ("every A4 reading holds") would make it **Not confirmed**, which would leave the case **undetermined**.

**Stage-3 estimate:** negative. **Outcome class:** **true negative** — estimate `negative`, effect `does not cap` (unit tier; cluster n/a).

**Claim tested:** (B1) the heap held by a `BoundedByteArrayOutputStream`, including the two key buffers of a `TFile.Writer`, equals its capacity at construction and does **not** follow `limit`; writes up to and past `limit` through `write(int)` allocate no extra heap — the check only stops the cursor at `limit` and throws `EOFException`.
"Confirmed" below always means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (allocIn 0.00 B/pass and exception-only past-limit cost at L = 1 KiB … 16 MiB; failure at L + 1; TFile at 65537 / 101 / int 16385; control ×16070). Flag: `retainedDelta` −6872 vs C ± 1 MiB in 1 of 9 rows (instrument artefact, §4.2 part 6) | does not cap | run 1 + self-check | 2026-11-06 |
| Cluster | not run: `n/a` — compile-time constant with no configuration key, and no daemon path executes line 76 (keys written with `writeUTF` → line 91; A7) | not run | B3 + A7 | 2026-11-06 |

**Positive control:** the same single-byte workload (W = L + 1024) into `ByteArrayOutputStream(32)` and `DataOutputBuffer`: allocation 4176 → 67109168 and 4256 → 67109248 bytes per pass from W = 2048 to W = 16778240 (2.0–4.0 × W), measured by the same thread-allocation instrument that read 0.00 for the bounded stream; and `allocCtor` followed the capacity C (65584 / 1048624 / 16777264).

**Feedback filed:** the case file's section D2 "Stage-4 result" (2026-11-06, uncommitted); amendments A1–A7 (audit, before any reading) in the sections they change and in D1. `_INDEX.md`, `queue.csv`, `case-notes.md` and HANDOFF were not edited (left to the parent session).

**Left on the node:** `/mydata/jingsong-s4/MAX_KEY_SIZE-write-limit-run1/` (356 MB: `src/` copy with the test class and its `target/`, `logs/unit/`, `diag/`, empty `tmp/`); no daemon, no container, no test JVM, no port (`jps` showed only `Jps` after the run). Undo: `rm -rf /mydata/jingsong-s4/MAX_KEY_SIZE-write-limit-run1/`.
