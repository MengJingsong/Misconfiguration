# commitlog_total_space + max_hints_size_per_host — convergence case

> **Playbook:** [`../../convergence-playbook.md`](../../../convergence-playbook.md)
>
> **Run:** 2026-11-02, node `node0.jason92-323989.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB, local disk `/dev/sda3` 63 GB), Ubuntu 22.04.2, kernel `5.15.0-198-generic`, OpenJDK 11.0.32.1, Ant 1.10.12.
>
> **Source:** `systems/cassandra/source` at the pinned tag, reusing the existing build at `~/cassandra-run1` (unchanged since the closed heap-case runs — no rebuild needed).
>
> **Harness:** [`commitlog_total_space+max_hints_size_per_host/run1/oom-run.sh`](commitlog_total_space+max_hints_size_per_host/run1/oom-run.sh). Full logs on the node at `~/oom-disk-run3/{N1-logs,N2-logs,logs/<arm>}/`; this case has no raw-log excerpts committed (see §4 — the run did not reach a state worth excerpting beyond what is quoted inline below).
>
> **Outcome: OOM not reached — blocked before a valid convergence arm could run, by a sizing error and a confound, both diagnosed. Not exhausted; a real retry candidate.** The single control arm that was supposed to establish "commit log alone is safe" instead ran the disk-budget mount to 100% full and tripped a real `FSWriteError`/`disk_failure_policy=stop` event — on its own, before `max_hints_size_per_host` was ever pushed to its target, and with a second confound (unintended hint growth in a "zero hints expected" arm) layered on top. The `hints_alone` and `converge` arms were never run, because the precondition the playbook requires before combining constraints (each one safe alone) was not met.

## 1. Constraints and capacities

Both constraints are config-type, **true positive** at if-check-exp stage 4, and were picked as the first candidates surveyed for the **disk** shared-budget group (`_batch-log.md`'s status table, "open (unexamined)" going into this run).

| | `commitlog_total_space` | `max_hints_size_per_host` |
|---|---|---|
| if-check-exp case file | [`commitlog-total-space-calculateDefaultSpaceInMiB-minSizeInMiB--autonomous.md`](../../../../if-check-exp/cassandra/stage3-ai-deep-read/cases/commitlog-total-space-calculateDefaultSpaceInMiB-minSizeInMiB--autonomous.md) (constraint); verification solution at `commitlog_total_space-maybeFlushToReclaim-unused--autonomous.md` | [`max_hints_size_per_host-shouldHint-maxHintsSize--guided.md`](../../../../if-check-exp/cassandra/stage3-ai-deep-read/cases/max_hints_size_per_host-shouldHint-maxHintsSize--guided.md) |
| if-check-exp stage-4 results | [`commitlog_total_space-maybeFlushToReclaim-unused--autonomous.md`](../../../../if-check-exp/cassandra/stage4-runtime-verification/results/commitlog_total_space-maybeFlushToReclaim-unused--autonomous.md) | [`max_hints_size_per_host-shouldHint-maxHintsSize--guided.md`](../../../../if-check-exp/cassandra/stage4-runtime-verification/results/max_hints_size_per_host-shouldHint-maxHintsSize--guided.md) |
| Outcome class | true positive (soft cap, confirmed overshoot C+4S..C+S bound) | true positive (tight cap, confirmed overshoot bounded to ~one flush period, 0.2–0.97 MiB observed) |
| Capacity check | `AbstractCommitLogSegmentManager.maybeFlushToReclaim()` / `tryAllocate` path, `CommitLogSegmentManagerStandard` | `StorageProxy.shouldHint():2492` — `actualTotalHintsSize > maxHintsSize`, gated by `if (maxHintsSize > 0)` at `:2489` |
| What it caps | On-disk bytes of commit log segments (`commitlog_directory`) | On-disk bytes of hint files for one destination host (`hints_directory`) |
| Default / how set | yaml `commitlog_total_space` (default: `min(8192, 1/4 of commitlog volume)` MiB); restart-only | yaml `max_hints_size_per_host` (default `0B` = **disabled**); restart-only |
| Mechanism needed to generate load | Any sustained write volume (commit log always grows with writes) | **Requires a replica Cassandra currently can't reach** — a single node has no other endpoint to hint for, so this constraint is structurally untestable without a second node (if-check-exp's own stage-4 team reached the same conclusion and built a 3-node loopback cluster for exactly this reason) |
| **Capacity chosen for this case** | **800 MiB** (target; not reached — see §3) | **900 MiB** (target; never exercised — see §3) |

**Shared budget and node total:** a dedicated **1536 MiB loop-mounted ext4 filesystem** (`~/oom-disk-run3/disk3.img`, mounted at `~/oom-disk-run3/mnt`), standing in for "the disk" the same way `-Xmx1024M` stood in for "the heap" in the closed cases — the node's real 63 GB local disk is not the experiment's budget. Only N1's `data/commitlog/hints/saved_caches/cdc_raw` directories live on this mount; N1's own logs (and everything about N2) are on normal local disk, outside the budget being tested.

**Topology (new for this case; not used by either closed heap case):** two Cassandra nodes on one physical host, loopback addresses 127.0.0.2 (**N1**, the node under test) and 127.0.0.3 (**N2**, a plain RF=2 replica on normal local disk that gets killed to make N1 hint for it). `max_hints_size_per_host` cannot be exercised any other way — see the mechanism row above.

## 2. Verification solution

### 2.1 Baseline measurement

Idle N1 disk usage (both nodes up, no load, both target knobs tiny/off): `du -sb` on N1's directory tree gave **67,440,467 B ≈ 64.3 MiB** — almost entirely two pre-allocated 32 MiB commit log segments (Cassandra's commit log pre-allocates segments at `commitlog_segment_size`, default 32 MiB, regardless of content), plus a few hundred KB of system-keyspace data and an empty hints directory. **Baseline b ≈ 64 MiB.**

### 2.2 Sizing (as designed, before running anything)

Known overshoot behavior from if-check-exp stage 4 (not re-derived): commit log is a **soft cap with moderate overshoot** under throttled load (cluster tier: C=1024 MiB peaked at 1184 MiB, factor ≈1.16×); hints is a **tight cap** (overshoot bounded to about one flush period, 0.2–0.97 MiB observed at L=16/64/256 MiB).

- **Commit log alone target:** X = 800 MiB → predicted real usage ≈ 1.16×800 = 928 MiB → alone_used = 64+928 = 992 MiB = 64.6% of 1536 MiB → **35.4% free.** ≥30% margin met (on paper).
- **Hints alone target:** Y = 900 MiB → predicted real usage ≈ 901 MiB → alone_used = 64+901 = 965 MiB = 62.8% of 1536 MiB → **37.2% free.** ≥30% margin met (on paper).
- **Combined, predicted to exceed the budget:** 64 + 928 + 901 = 1893 MiB = **123.2% of 1536 MiB**, a clean ~23% overshoot — the same shape as the closed heap case's 126%.

**This sizing never got validated against the real workload** — see §3. The arithmetic above only accounts for the two target constraints' own byte budgets; it does not account for flush output and compaction rewrite overhead as a *separate*, much larger disk consumer, which is exactly what broke the control arm.

### 2.3 Workload, settings, and procedure

- Settings carried over from the closed heap cases, after the first attempt's failure made clear they were needed here too: `memtable_allocation_type: unslabbed_heap_buffers`, `memtable_cleanup_threshold: 0.99` (per if-check-exp's own commitlog_total_space case file: *"Requires `memtable_cleanup_threshold: 0.99` to actually reach the limit, otherwise the default threshold reclaims early"*). `-Xmx1024M` after an earlier `-Xmx512M` attempt genuinely heap-OOM'd under this write shape (see §3.0).
- **`commitlog_alone` control:** N2 stays up throughout (zero hints expected); `commitlog_total_space=800MiB`; `cassandra-stress write n=1000000 no-warmup cl=ONE -col 'size=FIXED(1024)' -rate threads=256` against N1, RF=2 keyspace.
- **`hints_alone` control (never run):** N2 killed hard right after the ring forms; `max_hints_size_per_host=900MiB`; slower, throttled write (`n=210000`, 5 KiB columns, `threads=4 throttle=200/s`) so commit log stays near baseline (self-reclaiming) while hints accumulate cumulatively (no reclaim while N2 stays down).
- **`converge` arm (never run):** N2 killed hard; both `commitlog_total_space=800MiB` and `max_hints_size_per_host=900MiB`; the same fast write as the control, since hints don't self-reclaim and would plateau near 900 quickly while the fast rate also drives commit log toward 800.
- Each arm brings up a **fully fresh ring** (both N1 and N2 wiped and restarted) rather than reusing nodes across arms — wiping only N1 while N2 persisted was tried and rejected during harness-writing: it corrupts gossip state (N1 restarts with a fresh host ID/system keyspace while N2 still remembers the old incarnation at the same address).

## 3. Runtime results

### 3.0 Setup problems fixed before a result was obtainable (recorded for the next run)

Three issues surfaced and were fixed in sequence while just getting the harness itself to run cleanly, documented here because they're specific and reusable, not because they're the case's actual finding:

1. **JMX bind address.** `nodetool -h <node's own address>` failed to connect — Cassandra's JMX/RMI listener binds to `127.0.0.1` regardless of `listen_address` (matches if-check-exp's own hints harness, which uses `nodetool -p <port>` with no `-h` for exactly this reason). Fixed: all `nodetool` calls use `-h 127.0.0.1` with each node's own JMX port.
2. **Teardown timing.** The harness's own "no CassandraDaemon left" check timed out at 15s even though the processes were confirmed (by hand) to fully exit shortly after — Cassandra's pidfile is removed by its shutdown hook *before* the JVM actually finishes exiting (netty, GC/JFR threads), so a naive pidfile-based check reports "down" prematurely. Fixed: widened to a 60s retry budget, matching the closed heap cases' own `stop_node` convention.
3. **Heap sizing.** A `-Xmx512M` first attempt crashed N1 with a genuine heap `OutOfMemoryError` (`gc.log`: `Pause Full (G1 Evacuation Pause) 480M->480M(512M)`, `Did not expand the heap (heap already fully expanded)`) at commit log ≈160 MiB / total disk ≈234 MiB — nowhere near either target, so this was never a disk-budget result. Fixed: `-Xmx1024M`, which the closed heap cases already ran this exact write shape on safely.

### 3.1 `commitlog_alone` control — the actual blocking result

With both the memtable-cleanup-threshold fix and the heap fix in place, the arm ran without crashing but **did not stay safe**:

- Commit log behaved correctly for the first time — oscillating near its own cap under the `memtable_cleanup_threshold=0.99` setting (335,548,416 → 100,667,392 → 335,548,416 → 134,221,824 B across samples), confirming the soft-cap-with-reclaim mechanism this fix was meant to restore. It never reached the 800 MiB target.
- **Total N1 disk usage climbed past the 1536 MiB mount and the mount hit 100% full:**

  ```
  disk s21: N1-total=1501961220B (1432.4MiB) ... mount=1.4G/1.5G (100% used)
  ERROR [PerDiskMemtableFlushWriter_0:2] ... org.apache.cassandra.io.FSWriteError: java.io.IOException: No space left on device
  ERROR [PerDiskMemtableFlushWriter_0:2] ... DefaultFSErrorHandler.java:72 - Stopping transports as disk_failure_policy is stop
  ERROR [PerDiskMemtableFlushWriter_0:2] ... StorageService.java:684 - Stopping native transport
  ```
  Two `CompactionExecutor` thread exceptions preceded the flush failure. With commit log itself only at ~320 MiB at the time, the other ~1.1 GiB of the 1.43 GiB used is flush output plus compaction rewriting it — overhead that is not part of either target constraint's own byte accounting, and that this case's sizing (§2.2) did not budget for at all.
- **A second, independent confound: real hint growth in an arm where N2 never went down.** `hints` bytes grew from 1,209,958 to 29,095,356 B (≈1.2 → 27.8 MiB) over the run, even though N2's process stayed up the entire time (confirmed: N2's pidfile and log were freshly rotated this run specifically to rule out stale-log carryover, and N2 was never killed in this arm). The only plausible mechanism is **contention-induced false suspicion**: two co-located JVMs plus a 256-thread stress client all competing for CPU on one host apparently let N1's failure detector flag N2 as transiently unreachable, triggering real hint writes despite N2 never actually going down.
- The `hints_alone` and `converge` arms were **not run** — the playbook requires each constraint confirmed safe alone before combining them, and that precondition failed here.

## 4. Conclusion

**OOM not reached — but not because these two constraints don't converge; the run never got to test that.** Two specific, diagnosed problems blocked a valid result, both structural to this run's design rather than something about the constraints themselves:

1. **A sizing error.** The 1536 MiB mount and the `n=1,000,000` write workload (≈976 MiB raw mutation payload) were sized against the two target constraints' own byte budgets (§2.2) without accounting for flush-and-compaction overhead as a separate, larger consumer of the same disk. In this run that overhead alone (≈1.1 GiB) consumed nearly the whole mount before commit log came anywhere near its own 800 MiB target, let alone leaving room for hints to reach 900 MiB on top. This needs **either a bigger mount or a smaller/throttled workload** so that flush+compaction overhead leaves real, measured margin under the commit log's own target before a retry's control arm is trusted.
2. **A contention confound in the control arm itself.** Running two Cassandra JVMs plus a loaded stress client on one physical host produced real (not stale-log) hint growth in an arm specifically designed to produce zero hints, because N1's failure detector appears to flag a live, CPU-starved N2 as transiently down. A retry should either raise `phi_convict_threshold` to tolerate the contention, or otherwise isolate/account for incidental hint activity before treating a control arm's hint reading as clean.

Both problems are about this run's experimental setup, not about whether `commitlog_total_space` and `max_hints_size_per_host` share a real disk budget — they clearly do (both live, by default, as subdirectories of the same disk unless an operator splits them onto separate mounts), and the **mechanism** identified while designing this case (a replica going down drives *both* constraints from a single write stream, with no deliberate dual-knob misconfiguration needed — see Target-3 note below) remains intact and worth testing. This is filed as a **blocked, retryable case**, not a dead end: the batch log's disk-group status reflects "open, one attempt blocked by sizing/confound" rather than exhausted.

**Target-3 note:** the scenario this case was built around — a replica going down under sustained write load, filling both the sender's commit log and its hints for the down replica from one ordinary operational event — remains realistic and needs no deliberate dual-knob misconfiguration. What wasn't realistic, and what broke this run, was purely an artifact of the test environment (two JVMs sharing one host's CPU budget, and a disk-budget mount sized without accounting for flush/compaction overhead) — not a property of the production scenario being modeled.
