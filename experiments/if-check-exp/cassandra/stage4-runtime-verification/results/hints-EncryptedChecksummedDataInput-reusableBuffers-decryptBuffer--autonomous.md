# hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous — stage-4 results  <!-- file: results/hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous`](../../stage3-ai-deep-read/cases/hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous.md)
>
> **Status:** **Closed 2026-10-26 - unit Confirmed, cluster Confirmed - does not cap** (estimate negative, matched); run 1 only (a harness defect in the unit `c1` case, re-run as run1b); no run 2; the session was interrupted once by an API rate limit and resumed from the saved state
>
> **Outcome class:** true negative — stage-3 estimate (negative) vs the stage-4 effect on the constraint (does not cap)
>
> **Agent:** guided / autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD 1ae567d (the case file is still untracked there). Whole-file sha256 after the audit amendments of 2026-10-26: `0ed9ab6f98f22f31e7bd0bf83985c15fb1689a5b1d27d1acbeb5ca5a1963ba8b` (before: `bdc3c822...fd19e09`). **Frozen before any reading:** sha256 of the text of B2f-B2g plus B3f-B3g (from `**B2f.` to `**B2h.` and `**B3f.` to `**B3h.`, amendments included) = `b4c841beb39b7311f00b7d1d4e529410067ac91f2adaedda871b8b88fb843b54`; copy in `results/hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous/run1/frozen-tables.txt`. |
| **Harness** | `harness/hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous/` (written and instrument-checked before run 1: unit shakedowns `shake1`/`shake2`, cluster shakedowns `shake1`/`shake2`; shakedowns are not readings). Not committed (the orchestrator commits). |
| **Tiers and values** | Unit (S1-S6, K2 in {16, 4, 1} MiB for S3, C1) and cluster (F1-F4, K2 default/4/1 MiB for F2, positive control `max_hints_file_size`) on pc12, tree `~/s4-ec` |
| **Audit bottom line** | Ready after amendments - 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1/A2: on-heap thread-local byte[] (and per-reader direct buffer), bytes |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met after amendment | B2b had two max_mutation_size values; R6 adds 4 MiB (three), plus the block-size ladder S1-S4/F1-F3 (the real driver) |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d/B3d: reflection on the retained array, thread-allocated bytes, live heap dump byte[] scan, direct pool gauge; R8 |
| A. Core question | usage driven to the limit and past it | Met | 15 MiB hint (slab/2 limit 16 MiB-12, HintsBuffer.java:152) and the forged 512 MiB header past every limit |
| B. Logic | each step says what it establishes | Met | B2e/B3e |
| B. Logic | prediction stated in numbers or a clear relation | Partly -> Met | S1 band lower bound wrong (R4), exact relation added; S5 retention wrong (R3) |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly -> Met | S5 row added (R3); retained-after-thread-death clarified (R5) |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | negative file: capacity independent of K2, > 256 KiB and > K2; C1 shows the write cap binds |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: compressibility S6, fresh thread, unencrypted file, GC before histograms |
| C. Specific | a human can follow it from the intro and §9a | Met | B1, B2f-g |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly -> Met | producer, keystore, host id, ports and dispatch trigger spelled out in the R2/R8/R9 amendment |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly -> Met | sampling times fixed in R5, ports R9, S6 workload R5 |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | tree ~/s4-ec built (build-test OK, 1 min 7 s); keystore test/conf/cassandra.keystore; harness written in step 1 |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | F1 64 MiB ~ 257 blocks; 15 MiB hint; 512 MiB array under -Xmx2g; 43 GB free on pc12 |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | all cites re-read; reachability chain (descriptor -> cipher -> reader) confirmed, R2 |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Claim 'no encrypted hints written in 5.0.9' holds (HintsService.java:130-148; ENCRYPTION only in HintsDescriptor and HintsEncryptionTest:78) | n/a, confirmed | |
| R2 | Injection reaches :126 via descriptor params + node key_provider + ring-member host id; TDE `enabled` not required | Applied 2026-10-26 (case file, before B3a) | reachability |
| R3 | S5 (both header fields 512 MiB + junk tail) cannot retain: IOException before :126-127; original prediction wrong | Applied (B2f, B2g, B3 F4) | source |
| R4 | S1 lower bound 256 KiB wrong; exact relation capacity = max encrypted length | Applied | arithmetic |
| R5 | Dispatcher core thread times out after 1 min: sample while alive and after; S6 workload defined | Applied | thread lifetime |
| R6 | Knob had two values; add 4 MiB | Applied | protocol A |
| R7 | Fresh FastThreadLocalThread; positive control wording and its limit (write-side cap) | Applied | control |
| R8 | Cluster instruments: Byteman TL capacity/alloc, live heap-dump byte[] scan | Applied | measurement |
| R9 | Ports/addresses as assigned | Applied | node |
| R10 | Header 2nd field is the compressed length, not plaintext; one CBC IV per file, reused by every block | Noted in section D | wording |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-10-25 22:50 to 23:36 MDT (2026-10-26 04:50 to 05:36 UTC) | not done |
| Node | `pc12` (`node1.jason92-320876`), 40 cores, 251 GiB; other agents' nodes ran beside mine on other ports | |
| OS and kernel | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK / Ant | OpenJDK 11.0.32.1 / Ant 1.10.12 | |
| Local source copy | `~/s4-ec` from `cassandra/cassandra-5.0.9/` at repository commit `1ae567d` (`copy-source.sh`; `git describe` = `cassandra-5.0.9`); `ant build-test` 1 min 7 s | |
| Case-file / harness commit | case file sha256 `0ed9ab6f...a1963ba8b` (uncommitted at HEAD `1ae567d`); harness uncommitted (rsync'd to `~/stage4-harness-run/ec/`, md5s in the first lines of each `summary.txt`) | |
| Storage | local disk `/dev/sda3` (ext, 43 GB free before); data, commit log and hints under `~/s4-ec-run/{A,B}` | |
| Full logs | `~/stage4-logs/ec/run1b/unit/` (unit), `~/stage4-logs/ec/run1/cluster/<cell>/` (cluster: `summary.txt`, `cell.json`, `ec.trace`, `produce.out`, `A-system.log`, `B-system.log`, `session.log`); `run1/` unit logs (c1 defect) at `~/stage4-logs/ec/run1/unit/` | |

Ports and addresses used, all as assigned: JMX 7333/7334, Byteman 9333 (A only), native 9355/9356, storage 7033/7034, loopback 127.0.33.2 (A) and 127.0.33.3 (B); each was checked free with `ss -ltn` before every start.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| D1 | shakedown | B3a `transparent_data_encryption_options.enabled: true` | With `enabled: true` the node's commit log is encrypted and 5.0.9 fails at start on both nodes (`AbstractCommitLogSegmentManager.java:125` assert with the default `commitlog_disk_access_mode`; `standard` is refused; `auto` hits the same assert). Not a hints problem. | The nodes run with the `key_provider` block and `enabled: false`. The audit (R2) had already found that the hints reader needs only the key provider (`EncryptionContext.createFromMap` builds an enabled context itself); the run confirms it (the file was decrypted, no 'ignoring encryption' warning). Recorded as a deviation; the claim, predictions and conclusions are unchanged. | 2026-10-26 | not amended in the case file (a deviation of B3a's yaml, see section D note) |
| D2 | run 1 unit | harness `c1` (EcProbe) | `setUp()` ran twice in the C1 JVM (AlreadyExistsException): the write-side cap check passed, then the 600 KiB read aborted. Instrument bug. | `setUp()` made idempotent; the whole unit tier re-run as `run1b` (every case again, predictions untouched). Only `run1b` is used below. | 2026-10-26 | n/a (harness) |
| D3 | shakedown | cluster harness wait for A | After a forged-header read A stops its gossiper and transports, so a `nodetool status` UN wait raced with it; the dispatch-end test also assumed the file is consumed. | A is declared up from its log ('Startup complete'); the forged cell ends on 'Failed to dispatch hints file'. | 2026-10-26 | n/a (harness) |

## 4. Run 1

**Scope:** unit tier: S1 x3, S2 x3, S3 x3, S4 x3, S6 x3 (fresh JVM each), S3 at `max_mutation_size` 4 MiB and 1 MiB, S5, no-shrink, C1; cluster tier: F1, F2 (default, 4 MiB, 1 MiB), F3 (default, 1 MiB), F3 plain (unencrypted control), F4 forged, positive controls (`max_hints_file_size` default and 4 MiB). **Command logs:** `hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous/run1/unit-run1b/{summary.txt,test.out}`, `hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous/run1/cluster-run1/<cell>/`, and `hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous/run1/selfcheck-output.txt` (a copy of the case-file text before the amendments and the frozen-table text are beside them).

### 4.1 Readings

**Unit tier** (`unit-run1b/summary.txt`, `test.out`; 105 harness checks, 0 mismatches; capacity = the `reusableBuffers` thread-local read by reflection on the reading thread after the file):

| Test or assertion | Result | Evidence |
|---|---|---|
| S1: 2,000 x 1 KiB random hints, 9 blocks | retained 250,928 / 250,912 / 250,896 B (245.0 KiB) in the three repeats = the largest raw encrypted block exactly; reader buffer 261,360 B (direct); block plaintext about 261 KB, compressed to about 251 KB because the hint framing (table id, column name, timestamps) compresses | `test.out` s1_1..3 |
| S2: one 1 MiB hint | 1,052,768 B (= 1 MiB + 4,192); same x3 | s2_1..3 |
| S3: one 8 MiB hint | 8,421,584 B (= 8 MiB + 32,976); same x3 and the same at `max_mutation_size` 16 MiB, 4 MiB and 1 MiB (the three JVMs printed 16777216, 4194304, 1048576) | s3_1..3, s3_mm4096, s3_mm1024 |
| S4: one 15 MiB hint | 15,790,400 B (= 15 MiB + 61,760); same x3 | s4_1..3 |
| S6: 4 x 250 KB zero hints | retained 1,088 B; reader buffer 256,066 B | s6_1..3 |
| S5: header [512 MiB][512 MiB] + 5 junk bytes | read failed (`FSReadError`: `IOException: failed to decrypt commit log block`), thread allocated 537,693,416 B, retained capacity after = 0 | s5 |
| No shrink: big file then a smaller one, same thread | capacity after the big file = after the small file (250,864) | noshrink |
| C1 | `HintsBuffer.allocate(600 KiB)` in a 1 MiB slab throws 'Hint of 614400 bytes is too large - the maximum size is 524288'; a 600 KiB block is read and retained (616,896 B) | c1 |

**Cluster tier** (two nodes, A reads the injected file; `cluster-run1/<cell>/`; `ec.trace` is A's Byteman trace, `SNAPSHOT` lines in `summary.txt` are live heap dumps parsed for `byte[]`):

| Cell (max_mutation_size on A) | Injected file | Retained capacity at the last block (trace) = largest raw encrypted block | Live heap dump: a `byte[]` of exactly that length | Direct pool above baseline 66.9 MB (+10 s / +30 s / +150 s) | Thread / dispatch |
|---|---|---|---|---|---|
| F1 (default) | 65,536 x 1 KiB, 274 blocks | 250,848 B | yes at +10 s and +30 s, gone at +150 s | +0.27 / +0.27 / 0 MB | 1 `HintsDispatcher` thread at +10 s and +30 s, 0 at +150 s; dispatch ended 23 s after A's start |
| F2 (default / 4 MiB / 1 MiB) | one 8 MiB hint + 200 x 1 KiB | 8,421,584 B in all three | yes (+10 s, +30 s), gone (+150 s), all three | +8.4 / +8.4 / 0 MB | same; 201 rows on B |
| F3 (default / 1 MiB) | one 15 MiB hint + 200 x 1 KiB | 15,790,400 B in both | yes, gone | +15.8 / +15.8 / 0 MB | same; 201 rows on B |
| F3 plain (unencrypted file, same hints) | the encrypted reader never ran (0 trace lines) | none | no `byte[]` >= 2 MiB | +0.0 | file consumed, 201 rows on B |
| F4 forged (default) | header [512 MiB][512 MiB] + 5 junk bytes | `readBuffer` left by an exception, thread-local 0 before and after, 537,110,600 B allocated by the reader thread in the call | no `byte[]` >= 64 MiB | +536.9 / +536.9 / 0 MB | `Failed to dispatch hints file ...: file is corrupted` (FSReadError); A then logs 'Stopping gossiper' and 'Stop listening for CQL clients'; file left in place; 0 rows on B |
| Positive control, `max_hints_file_size` default | 200 x 1 MiB hinted writes at CL ONE through A with B down | 2 hint files (134,226,730 B and 75,502,554 B), total 209.7 MB | | | `pos_default/summary.txt` |
| Positive control, `max_hints_file_size` 4 MiB | same workload | 50 hint files, each 4,194,626 B (4 MiB + 322 B), total 209.7 MB | | | `pos_4mib/summary.txt` |

The numbers above are those in `cluster-run1/*/summary.txt` and `cell.json`; the independent re-parse is `run1/selfcheck-output.txt`.

### 4.2 Conclusion and logic

1. **Validity** - [observed: `cluster-run1/*/summary.txt` and `A-system.log`: 'Finished hinted handoff of file' in the five encrypted and the plain cell, 0 'ignoring encryption' warnings, so the injected file was decoded as encrypted] the injection reached `readBuffer()` (trace `in`/`out` lines on thread `HintsDispatcher:1`). [observed: `produce.out`] the produced blocks are the intended shapes (274 blocks of about 250 KB; 8 MiB and 15 MiB single blocks). The limit was reached: blocks 32 to 60 times the 256 KiB constant and larger than every tested `max_mutation_size` (1 MiB, 4 MiB; 8 MiB and 15 MiB hints with the knob at 1 MiB). Held-fixed settings: `max_hints_delivery_threads: 1` [observed: one reader thread in every trace]; `max_mutation_size` as labelled [observed: yaml tail in each `summary.txt`; unit JVMs printed it]. Deviation D1 (TDE `enabled: false`) does not touch the reader.
2. **Readings** - S1 and F1 missed the frozen (amended) numeric band: 245 KiB, not [254 KiB, 257.1 KiB], because the hint framing compresses (the amendment assumed an incompressible block). The exact relation (retained = largest raw encrypted block) holds in every case. The direct pool excess in the cluster cells is the size of the encrypted block (8.4 MB, 15.8 MB, 536.9 MB), is held at +10 s and +30 s and gone at +150 s (thread gone): [inferred: equal to the block length, absent when the dispatcher thread is gone, and the hints path reads into an on-heap buffer, so it is the JDK's per-thread cached temporary direct buffer for `FileChannel.read` of a heap buffer, not the reader's own buffer].
3. **Matched row** - unit B2g row 1: 'Capacity ~ block size (S1 ~256 KiB; S2-S4 ~ hint size; S5 >= 512 MiB), unchanged by K2 -> Claim confirmed'. [observed] S2-S4 capacity = hint size + framing (1.0 MiB, 8.0 MiB, 15.0 MiB classes), S1 = the 256 KiB-class block (245 KiB, the stated number band missed), unchanged by K2 at three values; S5 as amended: allocation observed, no retention. Row 2 (S3/S4 above 256 KiB and above 1 MiB with K2 = 1 MiB) [observed] 8.0 MiB and 15.0 MiB retained with the knob at 1 MiB. Cluster B3g row 1: [observed] F1 250,848 (about 256 KiB class), F2 8,421,584, F3 15,790,400, unchanged by K2 (F2 at three values, F3 at two); row 2 F2/F3 retained > 1 MiB; the positive-control row: [observed] `max_hints_file_size` 4 MiB gives 50 files of 4 MiB against 2 files by default.
4. **Excluded rows** - 'rises with K2' (Refuted): [observed] F2 and S3 identical at 16/4/1 MiB. 'Stays <= ~258 KiB for S2-S5' (Refuted): [observed] 1.0, 8.0, 15.0 MiB retained. 'Shrinks after a smaller second read': [observed] no-shrink case. 'Dispatch never ran / controls did not engage': [observed] dispatch ended in 22 to 23 s in every cell and both controls rotated or did not as designed. The amended S5 row: [observed] allocation >= 512 MiB, error, no retention.
5. **Observed vs. inferred** - inferred: (a) the direct-pool excess is the JDK temporary buffer (item 2; not used by the verdict); (b) a retained buffer is freed with its thread because the array disappears from the live dump when the thread is gone at +150 s [observed: both facts; the causal link is inferred]. The verdict rests on observed readings.
6. **Deviations and gaps** - D1 (TDE `enabled: false`); the 5-minute idle replaced by +10/+30/+150 s samples (audit R5); no 'unencrypted file of the same payload' beyond F3; the K2 ladder for F3 has two values (default, 1 MiB); rows on B for F1 read 55,000 of 65,536 at the count (the count ran immediately at dispatch end; not rechecked, not used); the S1/F1 numeric band missed; no run 2.
7. **Core question** - Retained decrypt-buffer memory follows the largest block header in the file (exactly, to the byte), not the 256 KiB write constant and not `max_mutation_size`: 8 MiB and 15 MiB blocks stay retained on the dispatcher thread with the knob at 1 MiB, and nothing validates a block header before it is allocated (a forged 512 MiB header allocates 537 MB on the heap and about 537 MB of cached direct memory on the reading thread, then the file is rejected as corrupt, the retained buffer is not set, and A stops its gossiper and transports). The only bounds are on the writing side (`HintsBuffer.allocate`, `max_hints_file_size` binding in the positive control). Steps: validity (1) -> readings (4.1) -> matched rows (3) -> exclusions (4).

**Conclusion (one line):** B2g/B3g row 1 (capacity follows the block on disk, unchanged by `max_mutation_size`) - **Confirmed - does not cap**, for both tiers; the S1/F1 numeric band and the original S5 retention claim were wrong and are recorded as such.

## 5. Self-check of run 1 - AI

### 5.1 Check of run 1's conclusion

`harness/hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous/selfcheck.py` re-parses the raw `test.out`, `produce.out`, `ec.trace`, the `SNAPSHOT` lines, `pos.json` and `A-system.log` with its own code (output: `run1/selfcheck-output.txt`): 88 of 96 PASS (the one 'cell.json missing' line is the `all` driver directory; 7 of the 8 FAILs are the S1/F1 numeric bands: amended and original, three repeats, and F1). I also re-opened the raw files by hand for the points below.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `A-system.log` of each cell: 'Finished hinted handoff', 0 'ignoring encryption'; `ec.trace` has `in`/`out` on `HintsDispatcher:1`; the yaml tails show `max_hints_delivery_threads: 1`, mm values |
| 2. Readings | yes, with the S1/F1 miss recorded | `test.out` s1_*: blocks 250.4 to 250.9 KB encrypted with reader buffer 261,360 B (so plaintext 261 KB, compressed): the miss is in the amendment's arithmetic, not in the code path |
| 3. Matched row | yes | selfcheck: exact relation PASS in all 14 unit repeat cases and all 6 encrypted cluster cells; K2 identical |
| 4. Excluded rows | yes | no-shrink PASS; S2-S4 and F2/F3 above 1 MiB; dispatch ended in every cell |
| 5. Observed vs. inferred | yes | the two inferred items do not carry the verdict |
| 6. Deviations and gaps | yes | D1 confirmed by the successful decode; F1 row count not used |
| 7. Core question | yes | steps follow the audited logic; the forged-header consequences (gossiper stop) are an extra finding from `A-system.log` |

### 5.2 Run 2?

**No** (2026-10-26). The conclusion rests on exact observed relations (trace capacity = raw block length, live heap array of exactly that length, three-valued K2) that two independent instruments agree on, and the run does not refute the case or confirm a bypass.

## 6. Run 2 - fresh AI session (optional)

Not done.

## 7. Comparison - only if run 2 was done

Not applicable.

## 8. Verdict - AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** (B1) the on-heap `reusableBuffers` array retained after reading encrypted hints has capacity equal to the largest block header seen by that thread; it is independent of `max_mutation_size` and of the 256 KiB `WRITE_BUFFER_SIZE`; it does not shrink after the read, and a forged header larger than every configured limit is allocated without any check. "Confirmed" below means this claim held (with the amendments of 2026-10-26 and the two misses listed in 4.2 item 6).

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed - capacity ~ block size, unchanged by K2 (S5: the allocation is unchecked; the retained buffer is not set on a failed read) | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | Confirmed - retained `byte[]` = the largest block (250,848 B; 8,421,584 B; 15,790,400 B), unchanged by K2; forged header allocated unchecked | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control:** the write-side cap binds and the reader has none: C1 (a 600 KiB hint into a 1 MiB slab is rejected, while a 600 KiB block on disk is read and retained) and `max_hints_file_size` (4 MiB gives 50 files of 4,194,626 B against 2 files of up to 134 MB by default, same 200 MiB workload); instrument sensitivity: the retained capacity moves S1 < S2 < S3 < S4 and F1 < F2 < F3. Limit: the binding caps are on the write path; no cap exists on the read path to bind.

**Findings beyond the predictions:** (1) a forged 512 MiB header costs about 537 MB heap (garbage) plus about 537 MB of direct memory cached on the reading thread until it dies, and the FSReadError stops A's gossiper and client transports (`disk_failure_policy` stop) - the sibling `CompressedChecksummedDataInput` cases found the same unvalidated header allocation; (2) the retained buffer lives only as long as the dispatcher pool thread (1-minute keep-alive), so a quiet node returns to baseline about a minute after dispatch; (3) TDE `enabled: true` cannot start in this build (D1).

**Feedback filed:** the case file's section D updated with this verdict (sha256 reported in the final reply), `_INDEX.md` and `writeup-set-A.csv` left to the orchestrator.

**Leftovers (pc12, checked 2026-10-26 after the last cell):** no process of mine running; none of my ports (7033/7034, 7333/7334, 9333/9334, 9355/9356) listening. Files only: `~/s4-ec` (build tree), `~/s4-ec-run` (node dirs of the last cell, tools), `~/stage4-harness-run/ec`, `~/stage4-logs/ec/` (run1, run1b, shake1, shake2, build-test.log). Case-file sha256: after the audit amendments (frozen) `0ed9ab6f98f22f31e7bd0bf83985c15fb1689a5b1d27d1acbeb5ca5a1963ba8b`; after the section D feedback `357f02522bb4772e4c5eebbdd3652160da13fccf27fe2f26e568d119793cf6cb`.
