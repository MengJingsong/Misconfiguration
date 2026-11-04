# internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous — stage-4 results  <!-- file: results/internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous.md -->

> **Case:** [`internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous`](../../stage3-ai-deep-read/cases/internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous.md)
>
> **Status:** **Closed 2026-10-22 — unit Confirmed (B2g row 1); cluster Confirmed (B3g row 1).** Effect: caps (accounted bytes follow Q + G exactly; the memory the held messages occupy follows it too, but in the off-heap networking pool, not on the heap). No run 2. Audited 2026-10-22 (estimate positive).
> 
> **Outcome class:** true positive — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

**Relative links in this template** are written for where a *copy* of it lives — inside `results/`.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments R1–R10: `d2bc53b012d19d22143e1c492fb41f24be33b87c597908243b4e11de549f6ea4` (2026-10-22 07:35 MDT, before any harness or run). After run 1 attempt 1 (see §3, defect 1) the dated amendment R4a was added — a workload fix on the sender node, no row or prediction touched — giving the **frozen version for the run reported here**: `3a7804acd1f3b1830dc117f287b65208d377e1afb34ff1b4997cbedc9baecfb3` (section D still "none yet" at that hash; the new line for `_INDEX.md` §4 is this one, and section D is filled afterwards). The file is untracked in the repository (HEAD `00922e0`). |
| **Harness** | `harness/internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous/` — written 2026-10-22 after the audit, in the repository before run 1; files and checks in its `README.md`. md5 of every file, repo = node copy `pc06:~/stage4-harness-run/rsv/`: `results/<stem>/run1/harness-md5-node.txt` (the node's list adds only `run1-chain.sh`, now in the repo). Instrument checks: unit shakedown 1 (149 checks, 0 mismatches; same test, same md5, as run 1), cluster shakedown (`g4`, 40 s, `shake1`; logs `run1/shakedown/`, not a reading). Not committed. |
| **Environment deviation** | Both nodes (A target 127.0.0.2, JMX 7102; B sender 127.0.0.3, JMX 7103) run on one host, `pc06`, on loopback; node data on a 40 GiB tmpfs `/mnt/stage4-rsv` (local RAM), wiped after each label and unmounted at the end (audit R6/R10). Every B→A message crosses a real internode TCP connection. |
| **Harness choices fixed before any reading** | `hinted_handoff_enabled: false`, `auto_snapshot: false` on both; `memtable_allocation_type: offheap_buffers` on A (so the histogram reads the queued messages, not the memtable); A heap 1 GiB (as B3a), B 2 GiB; reading rules of audit R8 coded in `cluster-run.py` before run (docstring). |
| **Tiers and values** | Unit (B2): Q = 1 KiB · 64 KiB × G = 128 KiB · 512 KiB · 2 MiB (E 256 KiB, S 16 KiB), hook H1/H2, 10^6-message concurrent run, two mutants. Cluster (B3): G = E = 4 · 32 · 512 MiB at Q = 1 MiB, control Q = 16 MiB at G = 4 MiB, no-stress baseline; 256 KiB writes, `cl=ALL`, 192 threads, 120 s. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-22 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A1/A2: serialized bytes of inbound internode messages (a proxy for the heap/pooled buffers they occupy); the proxy gap is named in A3 and measured in B3d. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b G = 128 KiB · 512 KiB · 2 MiB (and Q 1 KiB · 64 KiB); B3b G = 4 · 32 · 512 MiB (512 MiB is the default). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B3d: class histogram after `GC.run`, networking BufferPool, direct memory, NMT; the global `using` is not exposed (named) — the Byteman trace supplies it (R7). Unit tier: counter only, as filed. |
| A. Core question | usage driven to the limit and past it | Partly | B3c's "64 threads × 256 KiB = 16 MiB offered" is wrong at CL=ONE (the client does not wait for the forwarded replica), and 32 MiB is called "borderline" with 16 MiB offered. **Amended** (R4: `cl=ALL`, 192 threads, so 48 MiB offered). |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps each say what is read. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f gives the exact sequential counts (checked by hand; R1 lists them) and the post-conditions; B3f gives ≤ G, throttling at 4 MiB / ~0 at 512 MiB, growth with G, inflation 1–3 (reading rules fixed by R8). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | No row for a wrong sequential count, for the `:447` branch giving a wrong result, for an insensitive test, for no throttling at 32 MiB, for inflation outside 1–3, or for a failed positive control. **Rows added** (R3, R9). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Row 1 needs using ≤ limit, the branch hit and a drain to 0 (unit); capped use, throttling at the small G and memory tracking G (cluster). |
| B. Logic | alternative explanations and their controls | Partly | B2h/B3h name controls, but B2 had no sensitivity control for the `:447` correction (a test that cannot fail proves nothing) and B3's slow consumer was not specified. **Amended** (R2 mutants M1/M2; R5 the Byteman hold). |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | A3 walks the code path with line numbers (checked against the clone: `:396/:411/:428/:431/:438/:447`). |
| C. Specific | an AI can run the runbook without re-deriving the code path | Partly | The deterministic hook, the load, the timeouts and the reading rules were left open. **Amended** (R1, R4, R5, R6, R8). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | See above; `write_request_timeout` (2 s default) would expire the held messages before capacity is acquired (`InboundMessageHandler.java:130-138`). **Amended** (R5). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | The closed sibling harness `…releaseCapacity-queueCapacity--autonomous` has the unit `Setup`, mutant runner, hold rule, trace, yaml maker, samplers, `Jmx.java`; Byteman and `cassandra-stress` are in the build. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | Offered load corrected (R4); 120 s × ~90 writes/s × 256 KiB ≈ 2.9 GB per node per label on a tmpfs. **Run 1 attempt 1 then showed the sender capped the load at 128 messages: defect 1, R4a.** |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `AbstractMessageHandler.java:396, 411, 413, 419, 426, 428, 431-435, 438-439, 447-455, 461-474`, `ResourceLimits.java:96-143`, `MessagingService.java:309-310`, `DatabaseDescriptor.java:974-996` (internode_max_message_size derives to the endpoint reserve when unset). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Exact B2 values (sequential counts, refusal outcome) and the deterministic `:447` hook H1/H2 with the branch counter | Applied 2026-10-22 (amendment block) | B2c left the hook open; hand-computed values make the check exact |
| R2 | Mutants M1/M2 in a separate clone must fail the test; a Q ≥ offered control | Applied 2026-10-22 | a test that cannot fail proves nothing about the correction |
| R3 | Add B2g rows 1b, 5b, 6, 7 | Applied 2026-10-22 | no row covered those outcomes |
| R4 | `cl=ALL`, 192 threads, `no-warmup`, `duration=120s` | Applied 2026-10-22 | CL=ONE does not bound the offered in-flight |
| R4a | `native_transport_max_threads: 256` on the sender | Applied 2026-10-22 08:10 (runbook defect 1) | the default 128 capped the load at 128 messages |
| R5 | Byteman 20 ms hold on A with `concurrent_writes: 2`; 60 s timeouts; hints off | Applied 2026-10-22 | the slow consumer and the expiry were unspecified |
| R6 | Five labels (`g4`, `g32`, `g512`, `ctlq16`, `base`), two loopback JVMs, tmpfs | Applied 2026-10-22 | B3e's step list made concrete |
| R7 | Global `using` read from the Byteman trace (and the vtable, since E = G) | Applied 2026-10-22 | B3d says it is not observable |
| R8 | Reading rules for M, acc, r, "load-limited", the control's threshold | Applied 2026-10-22 | B3f's "about 1 to 3" and "flat or load-limited" needed operational definitions before any reading |
| R9 | Add B3g rows 6, 7, 8 | Applied 2026-10-22 | no row covered those outcomes |
| R10 | tmpfs and one host (environment) | Applied 2026-10-22 | recorded deviation |

**Agreement criteria** — no run 2 (§5.2): not filled.

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-10-22 (MDT): unit 07:51–07:54; cluster attempt 1 07:57–08:16 (discarded, defect 1); cluster run 1 08:16–08:35; self-check afterwards | not done |
| Node | `pc06` = `node2.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB), nodes A and B on loopback on this host | — |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | — |
| JDK | OpenJDK 11.0.32.1; G1; A `-Xms1G -Xmx1G` (NMT summary), B 2G | — |
| Ant | 1.10.12 | — |
| Local clone commit | `~/cassandra-rsv` at `cassandra-5.0.9` (`b5f2a54`), `ant build-test` BUILD SUCCESSFUL (1 min 14 s); mutants in `~/cassandra-rsv-mut` (same commit), removed | — |
| Case-file commit / harness commit | case file untracked (HEAD `00922e0`), sha256 `3a7804ac…` (§1); harness untracked, md5 in `run1/harness-md5-node.txt` | — |
| Storage for node data | 40 GiB tmpfs `/mnt/stage4-rsv`, wiped after each label, unmounted at the end | — |
| Full logs | `pc06:~/stage4-logs/rsv/{run1,run1a-cluster,shake1}/` (68 MB per cluster run: traces, samples, node logs); excerpts in `results/<stem>/run1/` | — |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | cluster attempt 1 (`run1a`, 07:57–08:16) | B3c (R4) | With 192 stress threads at `cl=ALL` the target never held more than 128 messages: accounted peak 33,562,368 B = 128 × 262,206 B at both 32 MiB and 512 MiB, MutationStage pending 126 + 2 active, `ThrottledCount` 0 at 32 MiB (ceiling 34,603,008 B). A `cl=ALL` write holds one of the sender's `Native-Transport-Requests` threads and `native_transport_max_threads` defaults to 128. | `native_transport_max_threads: 256` on the sender only (R4a); B3f/B3g unchanged; the cluster tier restarted from its beginning (all five labels). Attempt-1 excerpts: `run1a/`. | 2026-10-22 08:10; the unit tier was not affected. | untracked file |
| 2 | both | B3d | "Global `using` not directly observable" — only the endpoint figure is in the virtual table. | Not a failure: with one sender and E = G the two are equal (confirmed, §4.1: vtable reserve = trace ep = trace gl), and the trace gives both. | R7 | — |

## 4. Run 1

**Scope:** unit tier complete; cluster tier G = 4 · 32 · 512 MiB (Q 1 MiB), control Q 16 MiB, baseline. **Command log:** `<stem>/run1/` (`unit/summary.txt`, `chain.txt`, `cluster/<label>/summary.txt` with the `EXPECTED:` lines, `readings.json`).

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, `harness.out`: 149 checks, 0 mismatches)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Upstream `ResourceLimitsTest` | 5 run, 0 failures | `unit/summary.txt` |
| `sequential`, 6 cells | successes 8 · 16 · 16 (Q 1 KiB) and 12 · 20 · 20 (Q 64 KiB) at G = 128 KiB · 512 KiB · 2 MiB, all = floor((Q + min(E,G))/S); the next call `INSUFFICIENT_GLOBAL` at 128 KiB, `INSUFFICIENT_ENDPOINT` otherwise; reserve at exhaustion 130,048 · 261,120 · 261,120 · 131,072 · 262,144 · 262,144 B; `E.using == G.using` and ≤ limits after every call; drain (0,0,0); outer form refused with `throttledCount` +1 and state unchanged; branch entries 0 | `unit/harness.out` (`seq.*`) |
| `control` (Q 1 MiB ≥ 640 KiB offered) | reserves never touched (0), drain (0,0,0) | `harness.out` (`control.*`) |
| `hook` H1 | acquire 600 with the queue released to 0 inside `tryAllocate`: after (q,E,G) = (600,0,0); branch entered once, released 600 to each reserve; drain (0,0,0) | `harness.out` (`H1.*`) |
| `hook` H2 | partial case: after (1224,200,200) = q − Q; branch released 400; drain (0,0,0) | `harness.out` (`H2.*`) |
| `hook` H1b, endpoint-refusal rollback | H1b (5-arg form) (600,0,0), `throttledCount` 0; refusal at `:431` rolls the global permits back: (1624,600,600) unchanged | `harness.out` (`H1b.*`, `ER.*`) |
| `single` (100,000 steps) | invariant E = G = max(0, q − Q) ≤ 2048 at every step; branch entries 0; drain (0,0,0) | `harness.out` (`single.*`) |
| `concurrent` (10^6 acquires, 4 releasers, sampler) | no exception, 1,000,000 released, final (0,0,0), using ≤ 2048 at every acquirer sample and in the sampler; **branch entered 8,218 times** (refusals 607,951) | `harness.out` (`concurrent.*`, note) |
| `defaults`; 32 MiB config | 4 MiB / 128 MiB / 512 MiB; 32 MiB reserve (and derived max message size) read back as 33,554,432 | `harness.out` (`defaults.*`, `config.32MiB`) |
| Mutant M1 (`globalReserve.release(excess)` removed) | test fails (`hook`, `concurrent`: global left at 600 / 2048) | `unit/mutant-M1.out`, `mutant-M1.diff` |
| Mutant M2 (`excess = allocatedExcess`) | test fails (H2 ends at (1224,0,0); `UnrecoverableIllegalStateException` in the drain) | `unit/mutant-M2.out`, `mutant-M2.diff` |

**Cluster tier** — A's inbound from B, loaded window = stress launch to drain, 131 s, 0 stress errors in every run, drained ≤ 1.3 s after the stress (`cluster/<label>/summary.txt`, `readings.json`):

| Capacity value | Run | Observable | Reading | Evidence |
|---|---|---|---|---|
| G = E = 4 MiB, Q 1 MiB (C = 5,242,880) | `g4` | accounted peak `acc` / max reserve `using` (trace) / vtable `using_reserve_bytes` max | 4,981,914 / 3,933,338 / 3,933,338 (= acc − Q) | `g4/summary.txt` |
| | | refusals / `ThrottledCount` delta / received | 10,226 `INSUFFICIENT_GLOBAL` / 10,226 / 11,337 | same |
| | | H (Mutation + `[B` above idle) / P (networking pool) / M | 4,215,616 / 6,989,824 / 11,205,440 B; live `Mutation` above idle 2 | same |
| G = E = 32 MiB, Q 1 MiB (C = 34,603,008) | `g32` | `acc` / max reserve `using` / vtable max | 34,348,986 / 33,300,410 / 33,300,410 | `g32/summary.txt` |
| | | refusals / `ThrottledCount` / received | 9,674 `INSUFFICIENT_GLOBAL` / 9,674 / 11,329 | same |
| | | H / P / M | 4,221,224 / 51,988,015 / 56,209,239 B; live `Mutation` 2 | same |
| G = E = 512 MiB (default), Q 1 MiB | `g512` | `acc` / max reserve `using` | 50,343,552 (= 192 × 262,206) / 49,294,976; ceiling 537,919,488 never approached | `g512/summary.txt` |
| | | refusals / `ThrottledCount` / received | 0 / 0 / 11,379 | same |
| | | H / P / M | 4,218,816 / 70,856,183 / 75,074,999 B; live `Mutation` 2 | same |
| G = E = 4 MiB, **Q 16 MiB** (control, C = 20,971,520) | `ctlq16` | `acc` / max reserve / `ThrottledCount` | 20,714,274 / 3,937,058 / 10,233 | `ctlq16/summary.txt` |
| | | H / P / M | 4,213,704 / 31,109,120 / 35,322,824 B | same |
| no stress (baseline) | `base` | H range + P range (noise) | 14,552 B; H offset above idle 2.7 MB (constant); `using` 0 throughout | `base/summary.txt`, `analysis.txt` |
| After every drain | all | vtable `using_bytes` / `using_reserve_bytes`; last trace line `ep`/`gl` using; live `Mutation` above idle | 0 / 0; 0 / 0; 0 | `summary.txt` `EXPECTED: …idle…` |
| Cross-run (R8) | `analyze` | M(g32) − M(g4); noise | 45,003,799 B (≥ 10 MiB, ≥ 2 × 14,552) | `analyze-summary.txt` |
| | | r = ΔM / Δacc | 45,003,799 / 29,367,072 = 1.532 | same |
| | | M(g512) vs 3 × acc(g512) | 75,074,999 ≤ 151,030,656 | same |
| | | control: M(ctlq16) − M(g4) | 24,117,384 B ≥ 15 MiB; acc 20.7 MB > 5.0 MB | same |

All 33 `EXPECTED:` lines of the five labels and the 4 of `analyze` are "yes" (none "NO").

### 4.2 Conclusion and logic

1. **Validity** — [observed: `cluster/*/summary.txt`] read-back at every start (queue capacity, endpoint and global reserve equal the label's values from the first `acq` line); the hold fired in `g4/g32/g512/ctlq16` (10,932–10,988 hold lines, 2 MutationStage workers asleep in `doVerb` at the first load sample); the limit was reached at 4 MiB, 32 MiB and in the control (`acc` within one message of C, `ThrottledCount` ≈ 10^4) and not at 512 MiB (offered 192 × 262,206 B = 50.3 MB < 538 MB); no OOM, no `UnrecoverableIllegalStateException`, 0 stress errors. Unit: all 149 checks and both mutants as designed. The run is valid.
2. **Readings** — unusual: (a) the heap histogram is flat (H ≈ 4.2 MB at every G, with 2 live `Mutation` instances) and sits 2.7–4.2 MB above the "idle" histogram even with no load (`base`), so H does not move with G; the memory that moves is the networking pool (P 7.0 → 52.0 → 70.9 MB), i.e. M is P in effect [observed: `readings.json`]. (b) Attempt 1's g32/g512 readings are void (defect 1).
3. **Matched row** — unit **B2g row 1** "using <= limit always, drains to 0, branch at `:447` hit": using ≤ limit at every sample (sequential, `single`, `concurrent`, sampler thread) [observed: `harness.out`]; drains to (0,0,0) after every scenario [observed]; the branch entered 1× in each of H1/H2 with the exact releases (600; 400) and 8,218× in the natural race [observed]. Cluster **B3g row 1** "reserve use capped at G, throttling at small G, memory tracks G": reserve `using` peaks 3,933,338 ≤ 4 MiB and 33,300,410 ≤ 32 MiB (and 49.3 MB ≪ 512 MiB) [observed: trace and vtable agree]; `ThrottledCount` 10,226 at 4 MiB, 9,674 at 32 MiB, 0 at 512 MiB [observed]; M 11.2 → 56.2 → 75.1 MB (+45.0 MB for the 28 MiB permit step, r = 1.53 in B3f's 1–3; at 512 MiB load-limited at 1.49 × acc) [observed]; reserve and `using` return to 0 at idle [observed].
4. **Excluded rows** — B2g "using > limit": none above (max 2048/2048 at the limit, never over). "using > 0 after drain": drains all (0,0,0). "using < 0 / over-release": no `UnrecoverableIllegalStateException` in the natural run (it appears only in mutant M2). "branch never hit": hit 8,218×; rows 1b, 6, 7 (added): counts, H1/H2 values and mutants all as expected. B3g row 2 (`USING` > G): excluded by the maxima above. Row 3 (counter capped but memory identical across G): M differs by 45 MB between 4 and 32 MiB [observed]. Row 4 (no throttling at 4 MiB): 10,226. Row 5 (nonzero at idle): 0. Added rows 6 (r outside [1,3]): 1.53; 7 (no throttling at 32): 9,674; 8 (control fails): +24.1 MB.
5. **Observed vs inferred** — inferred: (i) that the networking pool's growth *is* the inbound messages' memory — attributed from its tracking `acc` (P/acc = 1.40 · 1.51 · 1.41 · 1.50 for g4 · g32 · g512 · ctlq16) and from only 2 live `Mutation` instances, not from an allocation trace; (ii) that attempt 1's cap at 128 messages was the sender's NTR thread count (the fix gave exactly 192 messages at 512 MiB); (iii) that the `:447` branch also fires on a node: the unit tier proves the branch's effect, the node trace does not show it (no per-branch counter on the cluster).
6. **Deviations and gaps** — one host, loopback and tmpfs; the heap is not where the held messages sit (see 2a), so "heap" in B1 is read as pool + heap; the `:447` branch was not observed on a node (inferred only); one run per value (noise from `base`, not repeats); defect 1 restart (§3).
7. **Core question** — Usage followed the constraint: the accounted bytes of inbound messages stopped at Q + G (4,981,914 of 5,242,880; 34,348,986 of 34,603,008) and the pooled memory they occupy rose with G (11.2 → 56.2 MB) and stopped rising where the load did not reach the limit (75.1 MB at 512 MiB), so the reserve caps the memory of held inbound internode messages (parts 3, 4); the `:447` correction returns exactly `allocatedExcess − actualExcess` and the reserves return to 0 (unit H1/H2, 8,218 natural entries, M1/M2 killed; cluster idle 0/0).

**Conclusion (one line):** unit **B2g row 1** and cluster **B3g row 1** — confirmed (caps).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.py` re-parses the raw `rsv.trace`, `jmx-A.csv`, `vt-in.csv`, histograms and logs with its own regexes: 34 checks PASS, 0 FAIL (`run1/selfcheck.out`). Re-read by hand: `unit/harness.out`, `unit/summary.txt`, `unit/mutant-M{1,2}.out`, the five `summary.txt`.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | read-backs, hold lines and thread dumps in each `summary.txt`; stress 0 errors and no OOM in `selfcheck.out`; acc ≤ C at every label. |
| 2. Readings | yes | `selfcheck.out` reproduces acc (4,981,914 · 34,348,986 · 50,343,552 · 20,714,274), max `using` (3,933,338 · 33,300,410 · 49,294,976 · 3,937,058 = acc − Q), `ThrottledCount` 10,226 · 9,674 · 0 · 10,233, pool maxima, heap samples; H + P sums recomputed equal `readings.json`'s M. The H offset (3.7–4.2 MB above idle, 2.7 MB in `base`) is a constant, noted. |
| 3. Matched row | yes | unit: row 1 from `harness.out` (`seq.*`, `H1.*`, `H2.*`, `concurrent.*`); cluster: row 1's four parts each cite a reading above. |
| 4. Excluded rows | yes | each excluded row has its reading (4.2 part 4); the added rows too. |
| 5. Observed vs inferred | yes | the three inferred statements are the ones the Confirmed depends on least: the cap itself is observed in the trace and vtable; only the "pool = inbound memory" attribution and the node-side `:447` firing are inferred. |
| 6. Deviations and gaps | yes | listed; they limit "memory" to a pool+heap reading and leave the node-side branch evidence to the unit tier. |
| 7. Core question | yes | steps 3→4→7 follow B3 B1's logic: reserve ≤ G, throttling, memory tracks G, drain to 0. |

### 5.2 Run 2?

**No** (decided 2026-10-22): the cap itself is read directly (trace, vtable, `ThrottledCount`) and independently re-parsed; the two inferred statements do not carry the verdict; the instruction for this batch is run 1 only.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Comparison — only if run 2 was done

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested:** B1 — total reserve permits in use never exceed `internode_application_receive_queue_reserve_global_capacity`, node memory attributable to inbound internode messages stops growing with offered load once the limit is hit, and the `:447` release path returns exactly `allocatedExcess − actualExcess` so `using` returns to 0 when traffic stops. "Confirmed" means this held.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed — B2g row 1** | caps | run 1 + self-check | 2026-10-22 |
| Cluster | **Confirmed — B3g row 1** | caps (accounted bytes exactly Q + G; the held messages' memory follows it in the off-heap networking pool, ×1.4–1.5, while the heap stays flat) | run 1 + self-check | 2026-10-22 |

**Positive control:** raising the per-connection queue Q from 1 to 16 MiB at G = 4 MiB raised the ceiling from 5.0 to 20.7 MB (accounted) and the measured memory M from 11.2 to 35.3 MB (+24.1 MB ≥ 15 MiB), with `ThrottledCount` still ≈ 10^4 — the instruments can show an effect.

**Feedback filed:** the case file's section D (this date); the amendments are R1–R10 and R4a in the case file (block after B4).
