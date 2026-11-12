# OOM-exp — Cassandra run log

One chronological log of every playbook run (convergence/custom, default-value
convergence, and bypass), merged from the former per-direction batch logs
(`custom-convergence/_batch-log.md`, `default-convergence/_batch-log.md`,
`bypass/_batch-log.md`). Append one entry per playbook run, per the relevant
playbook: [`../../custom-convergence-playbook.md`](../../custom-convergence-playbook.md),
[`../../default-convergence-playbook.md`](../../default-convergence-playbook.md),
[`../../bypass-playbook.md`](../../bypass-playbook.md). Regime (custom | default)
is a label on each run, not a folder; cases now live under status-first folders
(`convergence/`, `candidates/`, `bypass/`, `negatives/`) — see [`_INDEX.md`](_INDEX.md).

## Runs at a glance

| Date | Playbook / regime | Run | Case | Result |
|---|---|---|---|---|
| 2026-11-02 | convergence / custom | run 1 | [memtable_heap_space+counter_cache_size](candidates/memtable_heap_space+counter_cache_size/memtable_heap_space+counter_cache_size.md) | OOMed |
| 2026-11-02 | convergence / custom | run 2 | [+key_cache_size](candidates/memtable_heap_space+counter_cache_size+key_cache_size/memtable_heap_space+counter_cache_size+key_cache_size.md) | OOMed, JVM killed |
| 2026-11-02 | convergence / custom | run 3 | [commitlog_total_space+max_hints_size_per_host](candidates/commitlog_total_space+max_hints_size_per_host.md) | blocked / parked |
| 2026-11-02/03 | convergence / custom | run 4 | [row_cache_size+index_summary_capacity](candidates/row_cache_size+index_summary_capacity.md) | not reached (superseded by run 6) |
| 2026-11-03 | convergence / custom | run 5 | [row_cache_size+index_summary_capacity--run5](candidates/row_cache_size+index_summary_capacity--run5.md) | void |
| 2026-11-03 | convergence / custom | run 6 | [row_cache_size+index_summary_capacity--run6](candidates/row_cache_size+index_summary_capacity--run6.md) | OOMed (schedule B) |
| 2026-11-03 | convergence / custom | run 7 | [memtable_offheap_space+file_cache_size](candidates/memtable_offheap_space+file_cache_size/memtable_offheap_space+file_cache_size.md) | OOMed |
| 2026-11-03 | convergence / custom | run 8 | [DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS (custom)](candidates/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom.md) | OOMed, JVM killed |
| 2026-11-04 | default | run 1 | [DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS (default)](candidates/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--default.md) | OOMed, strict default |
| 2026-11-09 | default | run 2 (C1) | [internode...--run1-defaultQ](candidates/internode_application_receive_queue_capacity-multiplicity/internode_application_receive_queue_capacity--multiplicity--run1-defaultQ.md) | sensitivity-limited / unresolved |
| 2026-11-09 | convergence / custom | C1 reopen (custom Q) | [internode...--run2-customQ](candidates/internode_application_receive_queue_capacity-multiplicity/internode_application_receive_queue_capacity--multiplicity--run2-customQ.md) | Q-attribution unresolved / negative |
| 2026-11-10 | convergence / custom | C1 run 3 (fast co-replica) | [internode...--run3-fastcoreplica](candidates/internode_application_receive_queue_capacity-multiplicity/internode_application_receive_queue_capacity--multiplicity--run3-fastcoreplica.md) | G1–G3 pass (ceiling at N=8, senders alive); stopped early by a sampler bug; Stage C/D outstanding |
| 2026-11-10 | bypass | B6 run 1 (accounting mismatch) | [internode_application_queue...--run1](bypass/internode_application_queue_capacity-accounting-mismatch/history.md#run-1) | bypass confirmed (2 domains); heap OOM 3/3 + 3/3 at 2 GiB with 60 s deadlines; default-timeout arm not established |
| 2026-11-10/11 | bypass | B6 run 2 (replica disk stall, default timeouts) | [internode_application_queue...--run2-diskstall](bypass/internode_application_queue_capacity-accounting-mismatch/history.md#run-2) | GC service loss 5/5 stall arms (≈ 99% heap, ≈ 97% in Full GC); heap OOM 2/8 stall/hang arms; blob 0 Full GCs; 8 MiB reserve removes it |
| 2026-11-11 | bypass | B6 run 3 (intervention ×3, same-day positives) | [internode_application_queue...--run3-intervention](bypass/internode_application_queue_capacity-accounting-mismatch/history.md#run-3) | reserve 8 MiB removes it 3/3 per condition; positives reproduced except run-1 replica side; run 2 and run-1 coordinator meet V1–V5 |
| 2026-11-11 | convergence / custom | R1 recheck of run 7 (pc96) | [memtable_offheap_space+file_cache_size](candidates/memtable_offheap_space+file_cache_size/memtable_offheap_space+file_cache_size.md) | kernel memcg kill 3/3; alone 0/6; `file_cache_size` 300 MiB removes it 3/3 → V1–V5 met; reproduced-OOM · diagnostic |
| 2026-11-11 | convergence / custom | R2 recheck of run 8 (apt140) | [DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS (custom)](candidates/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom.md) | direct OOM 3/3; alone 0/6; L = 1 MiB removes it 3/3 → V1–V5 met; reproduced-OOM · diagnostic |
| 2026-11-11 | convergence / custom | R3 recheck of run 1 (apt149) | [memtable_heap_space+counter_cache_size](candidates/memtable_heap_space+counter_cache_size/memtable_heap_space+counter_cache_size.md) | heap OOM + kill 3/3; alone 0/6; counter cache 50 MiB removes it 3/3 → V1–V5 met; reproduced-OOM · diagnostic (mixed) |
| 2026-11-11 | convergence / custom | R4 recheck of run 2 (apt179) | [+key_cache_size](candidates/memtable_heap_space+counter_cache_size+key_cache_size/memtable_heap_space+counter_cache_size+key_cache_size.md) | heap OOM + kill 3/3; alone 0/9; counter cache to auto removes it 3/3 → V1–V5 met; reproduced-OOM · diagnostic (mixed) |

---

# Part A — Convergence (custom-regime) runs

Originally `custom-convergence/_batch-log.md`. Per [`../../custom-convergence-playbook.md`](../../custom-convergence-playbook.md).

## Current campaign status — 2026-11-06

This dated table governs new candidate selection. Historical domain-wide statuses
below describe only the earlier standing-pool combinations/arithmetic; they do
not exclude replicated local limits or transient overlap. No new runtime results
are asserted. See [campaign plan](../campaign-plan.md).

| Mechanism / allocation domain / regime | Status | Next action |
|---|---|---|
| C1 / internode private allowances / custom capacities, budget separately labeled | **in progress** (updated 2026-11-10): reopen 2 Q-attribution negative (closed-loop equilibrium); run 3 reached the ceiling at N=8 with live senders, Q/N sweeps not yet run | Continue run 3: coordinator `write_request_timeout` > A_max/D, then S1 (N=8, Q=4/16/64) measuring total and physical memory; Stage D only if total grows with Q |
| C2 / per-query live memory / custom capacities, budget separately labeled | open | Verify threshold applicability and actual concurrent working sets; unlimited defaults are a separate unprotected arm |
| C3 / per-worker DOB allocations / custom capacities, budget separately labeled | open | Audit worker multiplicity and active versus retained buffers |
| Existing standing-pool combinations / original regimes | historical scope only; **recheck queued (R1–R4 P1, R5–R6 P2, 2026-11-11)** | Preserve results; reruns of the six pre-protocol OOMs for V1–V5 per [campaign plan R1–R6](../campaign-plan.md#prioritized-queue) are allowed; other new runs need a distinct mechanism or boundary question |
| Disk exhaustion / all regimes | skipped by request | No new disk runs or retries until explicitly reopened |
| Disk-to-memory causal chain / all regimes | deferred | Outside this batch; not implicitly reopened |

## Historical shared-budget group status

Checked and updated **before** picking a combination for a new run — one row
per shared-budget group surveyed so far (not per combination; see the run
entries below for that). Status is one of: **open** (more combinations in
this group are plausible and worth trying), **exhausted** (no further
combination in this group is expected to add evidence — state why),
**parked** (blocked on something outside this group, e.g. missing
infrastructure — state what), **skipped** (deliberately not being pursued
right now by request, even though it isn't exhausted or technically
blocked — state since when and why, and do not pick a new combination from
this group until it is explicitly un-skipped), or **deferred (causal-chain,
not picked)** (not a shared-pool group at all — see the note below the
table — out of scope for picking combinations until that scope is
revisited).

**Rule: disk is skipped for now (set 2026-11-02, by request).** Do not pick
a new disk-group combination, and do not retry the blocked
`commitlog_total_space+max_hints_size_per_host` case, until this is
explicitly un-skipped. Survey and pick from another open shared-budget group
instead.

| Shared budget | Constraints tried | Status | Why |
|---|---|---|---|
| On-heap JVM heap (`-Xmx`) | `memtable_heap_space`, `counter_cache_size`, `key_cache_size` | **exhausted** | 2-way (run 1) OOMed with caught exceptions; 3-way (run 2) OOMed harder (JVM killed). Escalating outcome across two sizes already shown; a 4th on-heap constraint wouldn't add new evidence per the playbook's own reasoning in both run entries. Reopen only if a future need arises to find the *minimum* boundary (tighter sizing), which is a different question from "does this group converge." |
| Off-heap/direct memory (`row_cache_size`, `index_summary_capacity`, `memtable_offheap_space`, `file_cache_size`, `DOB_MAX_RECYCLE_BYTES`, `MAX_HINT_BUFFERS`) | `row_cache_size` + `index_summary_capacity` (runs 4-6); `memtable_offheap_space` + `file_cache_size` (run 7); `DOB_MAX_RECYCLE_BYTES` + `MAX_HINT_BUFFERS` (run 8) | **exhausted** (2026-11-03, run 8) | Three disjoint pairs, all **OOMed**: run 6 (schedule B, kernel cgroup OOM-kill at 1973 of 2000 MiB; runs 4-5 not reached / void), run 7 (kernel cgroup kill at 3465 of 3500 MiB), run 8 (`OutOfMemoryError: Direct buffer memory` at a 560 MiB `-XX:MaxDirectMemorySize`, then Cassandra's forced heap OOM and `kill -9`; the first case whose budget is the JVM flag itself, since both pools are `ByteBuffer.allocateDirect`). No independent standing pool is left untried: the hints-slab case (`hints-HintsBuffer-put-slabCapacity`) is the same pool as `MAX_HINT_BUFFERS`; `trie_2gb_hard_limit`/`row_overhead_size` follow `memtable_offheap_space`; `nopcache_capacity` duplicates the row cache; the networking `BufferPool` family (`networking_cache_size`, `internode_application_*`, `native_transport_*`) fills only while messages are in flight and is likely one pool (run 7). Reopen only for a different question: cross-pairs of already-used pools (e.g. `DOB_MAX_RECYCLE_BYTES` + `file_cache_size`, both `allocateDirect`), a 3-way case, or the minimum-boundary search. |
| Disk (shared-pool sense) | `commitlog_total_space`, `max_hints_size_per_host` | **skipped** (2026-11-02, by request) | Run 3 attempted `commitlog_total_space+max_hints_size_per_host` on a dedicated 1536 MiB loop-mounted disk budget; blocked by a mount-sizing error (flush/compaction overhead exhausted the mount before commit log reached its own target) and a contention-induced false-suspicion confound (real hints in a "should be zero" control). Both are diagnosed and fixable — this is **not** exhausted, just deliberately paused. Retry (bigger mount/throttled workload, `phi_convict_threshold` tuning) remains the natural next step for this group once un-skipped, not abandoned. |
| Disk → heap (causal-chain) | none picked | **deferred (causal-chain, not picked)** | Flagged during the 2026-11-02 "picking combinations" discussion: disk pressure (commit log/data disk full or slow) stalling flush/compaction could let an on-heap backlog queue grow unbounded — heap OOMs from the backlog, not from a shared pool with disk. This is a distinct convergence mechanism from every other row in this table (causal, not pool-sharing) and is **out of scope for picking combinations today** per `custom-convergence-playbook.md`'s "Picking combinations" step 1 — recorded here so it isn't rediscovered as a gap, not because it's ready to build. |

## 2026-11-02 — run 1 (convergence / custom)

**Node:** `node0.jason92-323989.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB RAM, local disk `/dev/sda3` 63 GB). JDK 11.0.32.1 and Ant 1.10.12 installed fresh; source copied from repository commit `0be49fb6` to `~/cassandra-run1` via `copy-source.sh`, built with `ant build-test`.

**Shared-budget group surveyed:** on-heap JVM heap (`-Xmx`), using the two config-type true-positive cases the task pointed at: `memtable_heap_space` (memtable pool, soft/self-reclaiming cap) and `counter_cache_size` (counter cache, Caffeine weight cap, non-self-reclaiming). Both draw on the same single-node `-Xmx`.

**Combinations attempted:**

1. `memtable_heap_space` (M=550 MiB) + `counter_cache_size` (C=300 MiB), `-Xmx1024M`/`-Xms1024M`, concurrent `cassandra-stress write` + `cassandra-stress counter_write` — case file: [`memtable_heap_space+counter_cache_size.md`](candidates/memtable_heap_space+counter_cache_size/memtable_heap_space+counter_cache_size.md). **Result: OOM reached** (14 genuine `OutOfMemoryError: Java heap space` throws across unrelated thread pools; both control arms safe with 33–39% free margin).

**Combinations considered and skipped (not built or run):**

- A larger 3-way combination (adding `index_summary_capacity`, `row_cache_size`, or `native_transport_max_request_data_in_flight` on top of the two already run) was not attempted this run: the 2-constraint combination above already reached OOM at a comfortable margin (126% of `-Xmx` predicted, 96.6% used + 0 young regions actually observed), so a 3-way combination would not add evidence about whether 2 constraints already suffice — it would need its own fresh sizing and control arms to be a real case, and the playbook asks for rigor over quantity on the first run.
- No other shared-budget group (off-heap/direct memory, disk) was surveyed this run; this run's budget was fixed by the task to on-heap JVM heap only.

**Stopping reason:** time/rigor budget for a first run — one combination was built, sized with a stated arithmetic prediction, run through both control arms and the convergence arm, and filed as a complete case with raw-log evidence for every claim. The shared-budget group (on-heap, these two constraints) is not marked exhausted: a 3-constraint extension on the same heap budget (e.g. adding `row_cache_size` or `index_summary_capacity`) remains open for a future run, as does trying smaller M/C values to find the actual minimum combined sizing that still OOMs (this run deliberately sized with margin to exceed, not to find the tightest boundary).

**Verification environment notes carried to the next run:** `jcmd GC.heap_info` and `jcmd GC.run` both slow down sharply (14 s and 74 s respectively, vs. <1 s normally) once the heap is genuinely under OOM pressure — budget extra wall-clock time for the final reading in a future convergence arm that pushes this hard. `sudo dmesg -T` needs `sudo` (plain `dmesg` fails with "Operation not permitted" on this node's kernel).

## 2026-11-02 — run 2 (convergence / custom)

**Node:** same node (`pc41`/`node0.jason92-323989...`), same build (`~/cassandra-run1` at `cassandra-5.0.9`, unchanged since run 1 — no rebuild needed).

**Shared-budget group surveyed:** same on-heap JVM heap group as run 1, extended to a 3rd constraint — the open follow-up from `HANDOFF.md`. Checked the two candidates it suggested (`row_cache_size`, `index_summary_capacity`) against their stage-4 results for the first time: both are **off-heap** (`Native.malloc`/off-heap index-summary bytes), not on-heap, so neither is a clean addition to this group. Surveyed on-heap true positives instead and picked `key_cache_size` (config-type true positive, same Caffeine-weighted-cache family as `counter_cache_size`).

**Combinations attempted:**

1. `memtable_heap_space` (M=350 MiB) + `counter_cache_size` (C=250 MiB) + `key_cache_size` (K=200 MiB), `-Xmx1024M`/`-Xms1024M`, concurrent `write` + `counter_write` + `read` (the read arm needs a preloaded, flushed dataset — key cache only engages on sstable reads, not memtable reads) — case file: [`memtable_heap_space+counter_cache_size+key_cache_size.md`](candidates/memtable_heap_space+counter_cache_size+key_cache_size/memtable_heap_space+counter_cache_size+key_cache_size.md). **Result: OOM reached, JVM killed.** Smaller individual values than run 1's 2-constraint case (chosen so no pairwise subset was already enough to overshoot), each alone safe (46–87% heap free, 0 errors), combined drove the heap to 989/1024 MiB (96.6%) right after a forced full GC with a 72-byte allocation failing, a genuine `OutOfMemoryError`, a 1.35 GB heap dump, and — unlike run 1's case, where the JVM survived — `-XX:OnOutOfMemoryError=kill -9 %p` actually fired and killed the process.

**Combinations considered and skipped (not built or run):**

- A 4th constraint on top of M+C+K was not attempted: the 3-way combination already reached a harder outcome (genuine crash, not just caught `OutOfMemoryError`s) than run 1's 2-way case, so a 4th constraint wouldn't add evidence about whether 3 already suffice.
- The off-heap group (`row_cache_size` + `index_summary_capacity`, both off-heap true positives found while surveying this run) was noted but not run: off-heap convergence needs a different way to make the budget tight (the node's 251 GiB of physical RAM is not a usable ceiling for off-heap the way `-Xmx` is for on-heap; off-heap budgeting here would likely need a cgroup memory limit or similar, not yet set up) — left as a candidate for a future run, possibly closer to `bypass-playbook` territory if `-XX:MaxDirectMemorySize` turns out to be the more relevant constraint.
- Finding the tighter minimum M+C+K boundary (vs. this run's margin-sized values) was not attempted — same "rigor over quantity" reasoning as run 1.

**Stopping reason:** one new combination built, sized with a stated arithmetic prediction, run through three control arms plus the convergence arm, and filed as a complete case. One harness bug was hit and fixed mid-run (the `read` workload's `cassandra-stress` call needed `-col` to match the preload write's or validation failed immediately — see the case file §2.3/Instrument check) — the result reported is the corrected re-run, not the failed first attempt.

**Verification environment notes carried to the next run:** when the JVM genuinely runs out of room (not just gets close), `jcmd GC.run` can take minutes (3m40s here) to return, and a subsequent `jcmd GC.heap_info` can fail outright with `Premature EOF` if the process dies in between — treat a failed final heap sample as a signal to check `logs/gc.log`'s last lines (`ReportJavaOutOfMemory` safepoint) and for an `.hprof` file before assuming the harness itself broke. `set -Eeuo pipefail` scripts should expect this failure mode (a non-zero `jcmd` return) to trip the `ERR` trap and skip the harness's own post-run steps (error-count, oom-grep, dmesg) — recompute them manually from `system.log`/`dmesg` directly when that happens, which is what `converge/error-count.txt`'s comment in this case does.

## 2026-11-02 — run 3 (convergence / custom)

**Node:** same node (`pc41`/`node0.jason92-323989...`), same build (`~/cassandra-run1`, unchanged). First run in this project to use a second node (127.0.0.3) and a dedicated loop-mounted disk budget (`~/oom-disk-run3/disk3.img`, 1536 MiB, mounted at `~/oom-disk-run3/mnt`) rather than the node's real local disk.

**Shared-budget group surveyed:** disk (shared-pool sense), per `HANDOFF.md`'s open follow-up. Surveyed if-check-exp's disk-bound true positives: `commitlog_total_space`, `max_hints_size_per_host`, `max_space_usable_for_compactions_in_percentage`, `cdc_total_space`, `repair_disk_headroom_reject_ratio`. Rejected `cdc_total_space` as a pairing with `commitlog_total_space` specifically (not disk in general) — CDC segments are **hard-linked** to the main commit log segments, so their on-disk bytes overlap rather than add; combining them would not be a genuine sum of two independent consumers. Rejected `max_space_usable_for_compactions_in_percentage` and `repair_disk_headroom_reject_ratio` as a first pair — both are protective *gates* (they refuse further compaction/streaming/repair once headroom is low) rather than *quota consumers* that themselves grow disk usage when pushed to capacity, so "pushing them to capacity" doesn't load the disk the way the heap cases' pools did. Picked `commitlog_total_space` + `max_hints_size_per_host`: both are true-positive byte quotas on genuinely separate directories that default to the same disk unless an operator splits them onto separate mounts, and `max_hints_size_per_host` has a tight, well-characterized overshoot bound from its own if-check-exp stage-4 run.

**Combinations attempted:**

1. `commitlog_total_space` (target 800 MiB) + `max_hints_size_per_host` (target 900 MiB), on a dedicated 1536 MiB loop-mounted disk budget, 2-node ring (127.0.0.2 under test, 127.0.0.3 killed to generate hints) — case file: [`commitlog_total_space+max_hints_size_per_host.md`](candidates/commitlog_total_space+max_hints_size_per_host.md). **Result: OOM not reached — blocked before a valid convergence arm could run.** The `commitlog_alone` control arm (meant to confirm commit log is safe alone) instead ran the mount to 100% full from flush/compaction overhead the sizing hadn't budgeted for, tripping a real `FSWriteError`/`disk_failure_policy=stop` event, and separately produced real (non-stale-log) hint growth in an arm meant to produce zero hints — diagnosed as contention-induced false suspicion from two co-located JVMs plus a loaded stress client on one host. The `hints_alone` and `converge` arms were never run as a result. Filed as a **blocked, retryable** case, not exhausted — see the case file §4 for the specific fixes a retry needs (bigger mount or throttled workload; `phi_convict_threshold` tuning or incidental-hint accounting).

**Combinations considered and skipped (not built or run):**

- `commitlog_total_space` + `cdc_total_space`: rejected before building — CDC segments hard-link to the main commit log segments, so they do not add as independent disk consumers (see above).
- `max_space_usable_for_compactions_in_percentage` and `repair_disk_headroom_reject_ratio` as a pairing: rejected before building — both are protective gates, not quota consumers; pushing either "to capacity" causes Cassandra to refuse further work, not to keep growing disk usage, so they don't fit this playbook's convergence shape the way a true quota does.

**Stopping reason:** the one combination attempted surfaced a genuine sizing error and a genuine environmental confound mid-run (both diagnosed with concrete log evidence, documented in the case file's §3.0 and §4), rather than clearing to a clean result. Rather than continuing to resize/re-tune blind within this run, the decision was to stop here, file what was found as a blocked-not-exhausted case, and leave the retry (bigger mount/throttled workload, `phi_convict_threshold` tuning) for a future run.

**Verification environment notes carried to the next run:** (1) Cassandra's JMX/RMI listener binds to `127.0.0.1` regardless of `listen_address` — use `nodetool -h 127.0.0.1 -p <node's own JMX port>`, never the node's own gossip address, matching if-check-exp's own hints harness convention. (2) A pidfile-based "is it stopped" check can report false before the JVM actually finishes exiting (the shutdown hook removes the pidfile early); give `pgrep`-based confirmation a ~60s retry budget, not a short one. (3) Running two Cassandra JVMs plus a loaded stress client on one physical host is not resource-neutral: it caused both a 34-second local-pause warning from the failure detector in an early attempt and, in the final attempt, real hint generation toward a replica that never actually went down — any future multi-instance-on-one-host harness in this project should expect this and either budget for it or raise `phi_convict_threshold`. (4) A disk-budget mount's size must account for flush-and-compaction overhead as its own large consumer, not just the byte targets of the constraints under test — the heap cases' arithmetic (baseline + per-constraint overshoot) does not carry over to disk without this extra term.

## 2026-11-02/03 — run 4 (convergence / custom)

**Node:** same node (`pc41`/`node0.jason92-323989...`), same build (`~/cassandra-run1`, unchanged). First run in this project to target the off-heap/direct-memory shared budget (previously parked) and the first to use a **cgroup v2 `memory.max`** (via `systemd-run --user --scope`) as the actual budget, rather than `-Xmx`.

**Shared-budget group surveyed:** off-heap/direct memory, per `HANDOFF.md`'s open follow-up. Confirmed `row_cache_size` and `index_summary_capacity` (surveyed in run 2, see `_constraint-groups.md`'s off-heap table) as the two off-heap true positives to pair. **Key design correction made before any run**: the task's suggested budget mechanism, `-XX:MaxDirectMemorySize`, does **not** actually bind either constraint — both allocate via `MemoryUtil.allocate → JNA Native.malloc`, which never touches the JVM's `DirectByteBuffer`/`Bits.reserveMemory` accounting that flag polices (confirmed from both constraints' own if-check-exp case files, which independently note this and use `RssAnon`, not any JVM-reported metric, for exactly this reason). The real budget enforced in this run is a cgroup v2 `memory.max`, independently verified with a smoke test (500 MiB limit against a ~900 MiB idle-baseline node produced a genuine kernel `Memory cgroup out of memory: Killed process ... (java)` within ~25s).

**Combinations attempted:**

1. `row_cache_size` (550 MiB, `SerializingCacheProvider`) + `index_summary_capacity` (100 MiB configured cap; effective pre-resize transient ≈595-650 MiB — see case file §2.2 for why the transient, not the configured cap, is the number that matters for this arithmetic), cgroup budget 2000 MiB, `-Xmx384M` — case file: [`row_cache_size+index_summary_capacity.md`](candidates/row_cache_size+index_summary_capacity.md). **Result: OOM NOT reached.** Both control arms stayed safe (R alone: 73.6% of budget, 26.4% free; I alone: 76.8% of budget, 23.2% free). The convergence arm's combined peak (90.1% of budget) came in well under the naive additive prediction (106.1%) and never crossed the budget (`memory.events`' `oom`/`oom_kill` stayed 0 throughout). Diagnosed as a timing effect: each constraint's own enforcement (Caffeine eviction for the row cache, periodic resize for the index summary) kept operating under combined load, so the two measured "worst moments" — each captured in isolation at that constraint's own worst instant — did not actually coincide when run together.

**Combinations considered and skipped (not built or run):**

- Two earlier sizing attempts within this run's own index-summary calibration (3,600,000 and 3,000,000 partitions at the same 2000 MiB budget, before the final 1,500,000-partition sizing was chosen) **did** genuinely OOM-kill the node — but during what was meant to be a safe "alone" control arm, with no comparison baseline to file a convergence case against, so these are cited in the filed case's §2.2/§3.2 by their `dmesg` timestamps rather than given their own case files. They are the direct evidence behind the final, smaller sizing, not discarded data.
- No other off-heap candidate pair (e.g. the networking-pool family `internode_application_*`/`native_transport_*` constraints, already flagged in `_constraint-groups.md` as likely-the-same-underlying-pool) was surveyed this run — the task specifically pointed at `row_cache_size`+`index_summary_capacity`, and one full combination (control arms + convergence arm, with a genuine design correction mid-flight) was enough to fill this run's time budget.

**Stopping reason:** one combination built, sized (with an explicit, stated arithmetic correction when the naive prediction based on isolated calibration turned out to overestimate the true concurrent peak), run through two control arms and a convergence arm, and filed as a complete case with raw `dmesg`/cgroup-event evidence for every OOM/no-OOM claim. The group is left **open** (not exhausted): the case file's own §4 identifies a concrete, specific retry (longer `index_summary_resize_interval` so the pre-resize transient has more time to grow before being trimmed, or fully-concurrent rather than sequential-then-concurrent preloads) that would more faithfully force both constraints' individual worst moments to coincide — this wasn't attempted this run given the time already spent on sizing corrections, but is a timing/workload-shape question, not a "does this group converge at all" question, so a future run picking it back up does not need to re-survey the group from scratch.

**Verification environment notes carried to the next run:** (1) `-XX:MaxDirectMemorySize` is not a safe default assumption for "the off-heap budget" — check each constraint's own allocation path (JNA/malloc vs. `DirectByteBuffer`) before picking a JVM-flag-based budget; a cgroup `memory.max` is the more general mechanism and was confirmed working here. (2) `memory.current`/`memory.max` alone are a **misleading "percent used" metric** once any sstable/commitlog I/O is involved — the cgroup counts reclaimable page cache toward `memory.current`, so it can sit pegged at `memory.max` for long stretches with zero real memory pressure; use `RssAnon` (from `/proc/<pid>/status`) for the "how full is the hard, non-reclaimable budget" reading, and `memory.events`' `oom`/`oom_kill` fields (not `memory.current`) as the only reliable OOM-or-not signal. (3) `bin/cassandra -f` never writes a pidfile (only the backgrounding branch of the script does) — detect the daemon's PID by `pgrep`, not a pidfile, when the harness must run the JVM in the foreground (needed here so `systemd-run --scope` tracks the right process). (4) A `systemd-run --user --scope` cgroup's path includes an undocumented `app.slice/` component (`.../user@<uid>.service/app.slice/<unit>.scope`). (5) `index_summary_resize_interval`'s first scheduled run fires on a delay from the **manager's own startup**, not from when a workload's data is loaded — a resize-wait must capture a log-line offset before the workload starts, or it can match an earlier, near-empty resize. (6) `cassandra-stress user profile=...` requires a `queries:` section in the yaml even when only `insert` ops are ever run (a hard `AssertionError` otherwise). (7) a too-small key size for a cassandra-stress table meant to stress `index_summary_capacity` can make the achievable raw summary size per partition far too small to reach a meaningful total within a feasible partition count — match if-check-exp's own ~200-byte-key calibration rather than using a small/realistic key.

## 2026-11-03 — run 5 (convergence / custom)

**Node:** same node and build as runs 1-4 (`~/cassandra-run1`, unchanged). **Scope:** one combination, the off-heap retry named in run 4's §4. The 57 `if-check-exp` set-B cases (merged 2026-11-03) were checked for new standing-pool candidates; none added an off-heap one (they are new decision points on constraints already surveyed, and `paxos_cache_size` is on-heap, a group already exhausted). Disk stayed skipped.

**Correction (found in run 6):** the converge arm's burst wrote 0 partitions (the stress client's CREATE TABLE timed out), so this run's converge arm is void. See run 6.

**Combinations attempted:** 1. `row_cache_size` (550 MiB) + `index_summary_capacity` (100 MiB), cgroup 2000 MiB, `index_summary_resize_interval=30m`, burst and read pass concurrent. Case file: [`row_cache_size+index_summary_capacity--run5.md`](candidates/row_cache_size+index_summary_capacity--run5.md). **Result: OOM not reached; converge arm incomplete** (burst client timeouts, peak 1501 MiB vs 1608 / 1550 alone).

**Stopping reason:** one combination built and run through two control arms and a convergence arm. Group left **open** with two untried retries (larger client timeout / fewer threads; fill the row cache first, then burst).

**Notes for the next run:** (1) with the cgroup pinned at `memory.max`, reclaim throttling slows writes, so a concurrent burst can stall rather than grow memory; record partitions actually written, since the stress client prints no totals on timeout. (2) `oom-run.sh baseline` printed "process gone" for its idle sample (PID picked up before the daemon settled); arms are unaffected. (3) Do not call `nodetool stopdaemon` while the driver is running; check `pgrep -fa oom-run.sh` first.

## 2026-11-03 — run 6 (convergence / custom)

**Node:** same node and build. **Scope:** the two retries named in run 5, on the same pair. Case file: [`row_cache_size+index_summary_capacity--run6.md`](candidates/row_cache_size+index_summary_capacity--run6.md).

**Combinations attempted (one pair, two workload schedules):**

1. **Schedule A**, concurrent burst (16 threads, 50 retries/op) and row read pass, `isc.t` pre-created: **not reached**, peak 1866 MiB (93%); both pools fully loaded at the end (row cache 550 MiB, index summaries 303 MiB). The burst finished in 1 m 42 s, long before the 26-minute row-cache fill, so the compaction transient did not coincide with a full cache.
2. **Schedule B**, row cache filled to its cap first, then the 64-thread burst: **OOMed**, kernel cgroup OOM-kill (`CompactionExecutor` allocation, anon-rss 1973 MiB) about 13 s after the burst finished, during `isc.t` flush/compaction. Alone: 78% / 80%.

**Harness defect found:** a `cassandra-stress user` client creating its own table under concurrent load can time out on `CREATE TABLE` and write nothing, and `-errors retries` does not cover schema creation. This voided `A_converge_slow` and, retroactively, run 5's converge arm. Fixed by creating the table with `cqlsh --request-timeout=120` on the idle node; check each burst's `tablestats` (partition count, "Index summary off heap memory used") instead of trusting the client.

3. **Schedule B with a 1-minute resize** (arm C, a follow-up check): **no off-heap kill**, peak 1859 MiB (93%), resize ran every minute through the burst. The JVM still died, of a Java heap `OutOfMemoryError` (old gen 349/384 MiB, full GCs freeing nothing), not attributed and not counted as a convergence OOM; heap dump kept on the node, unanalyzed. See the run 6 case file's addendum.

**Run 4 superseded:** run 4 used the reverse order (burst first, then cache fill) with a 1-minute resize; not worth re-running unchanged. Marked superseded in `_INDEX.md` and its case file.

**Stopping reason:** both named retries run, plus the 1-minute-resize check; the pair closed as OOMed. The group stays open only for untried candidates.

## 2026-11-03 — run 7 (convergence / custom)

**Node:** same node and build. **Shared budget:** off-heap/direct memory, cgroup v2 `memory.max`. On-heap exhausted, disk skipped; the first off-heap pair closed in run 6.

**Combinations attempted:** 1. `memtable_offheap_space` (1200 MiB, `offheap_objects`, cleanup threshold 0.99) + `file_cache_size` (1200 MiB, chunk cache enabled), 3500 MiB budget, `-Xmx768M`. Case file: [`memtable_offheap_space+file_cache_size.md`](candidates/memtable_offheap_space+file_cache_size/memtable_offheap_space+file_cache_size.md). **OOMed:** alone 77.6% / 77.7%; converge (cache filled, then write burst) kernel-killed 16 s into the burst, anon-rss 3465 MiB.

**Considered and not picked:** the networking `BufferPool` family (`networking_cache_size`, `internode_application_*`, `native_transport_*` queue capacities). It fills only while messages are in flight, so it has no sustained window at capacity; `_constraint-groups.md` also flags those as likely one shared pool.

**Calibration note:** at 600 MiB per pool (8000 MiB budget) about 250 MiB of load-driven growth appears in each alone arm but once in the combined arm, and the ~1300 MiB idle (768 MiB pre-touched heap) left no workable budget; doubling both pools fixed the ratio. Calibration arms are kept in the case folder.

**Stopping reason:** one new pair sized, run through two matched control arms and a convergence arm, OOMed on the first try. Remaining off-heap candidates are few (`DOB_MAX_RECYCLE_BYTES`, `MAX_HINT_BUFFERS` / hints buffers, trie-memtable limits that follow `memtable_offheap_space`); a next run should check whether any is an independent standing pool before picking.

## 2026-11-03 — run 8 (convergence / custom)

**Node:** same node and build (`pc41`, `~/cassandra-run1`). **Shared budget:** off-heap/direct memory, this time the JVM's own `-XX:MaxDirectMemorySize` (both pools are `java.nio.DirectByteBuffer`s through `Bits.reserveMemory`; checked from source and confirmed by the OOM). On-heap exhausted, disk skipped. Second loopback node used again (hints need a down replica), but killed before any reading, so run 3's two-JVM contention cannot arise.

**Candidates checked:** the three named by run 7. `DOB_MAX_RECYCLE_BYTES`: standing (each thread keeps a scratch buffer of up to L between uses; `allocateDirect`). `MAX_HINT_BUFFERS`: standing (slabs recycled, never freed; `allocateDirect`); the stage-4 natural-load control already reached its cap without a Byteman hold, and calibration here reached 9 slabs at n = 12. The hints-slab case is the same pool as `MAX_HINT_BUFFERS`; the trie limits follow `memtable_offheap_space` (not independent).

**Combinations attempted:** 1. `DOB_MAX_RECYCLE_BYTES` (L = 8 MiB, 4 MB writes on 8 client threads) + `MAX_HINT_BUFFERS` (n = 8, 32 MiB slabs, 1 KiB writes to a down replica), 560 MiB `MaxDirectMemorySize`, `-Xmx3072M`. Case file: [`DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS.md`](candidates/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--custom.md). **OOMed:** alone 50.4% / 69.5%; converge (hints pool at its cap, then the DOB burst) hit `OutOfMemoryError: Direct buffer memory` in scratch-buffer growth about 7 s into the burst; Cassandra forced a heap OOM (heap 570 of 3072 MiB) and `OnOutOfMemoryError` killed the JVM. **Attribution control:** the same converge arm with only `dob_max_recycle_bytes` at its 1 MiB default stayed at 51%, no OOM.

**Harness defect found:** `cassandra-stress write` always sends `CREATE KEYSPACE` first; under the other workload's load it timed out and the client wrote nothing. This voided two converge attempts (one per order). Fixed with `cassandra-stress user` profiles that have no schema definitions; both controls re-run with them. Any future concurrent-workload harness should use such profiles, not just pre-create the table (run 6's fix covered `CREATE TABLE`, not this).

**Calibration note:** 14 MiB blobs with L = 32 MiB kept 1206 MiB (about 43 threads), far more than the hints pool; 4 MB blobs with L = 8 MiB kept about 337 MiB (about 44 threads). *T*, the number of threads that keep a buffer, is set by how many shared-pool workers the burst touches, not by the client's 8 threads; budget for about 44.

**Stopping reason:** one new pair sized, run through two matched controls, a convergence arm and an attribution control; OOMed. The off-heap group is marked **exhausted**: no independent untried standing pool is left (see the status table).

**Notes for the next run:** (1) `MaxDirectMemorySize` appears twice on the command line (`cassandra-env.sh` computes one first); the last one wins. (2) The JDK 11 direct-OOM message carries no byte counts; read the limit from the arm's flags and the trajectory from the `BufferPool` MXBean. (3) Client totals after a node death are not writes (cassandra-stress counts `NoHostAvailable` failures as done); use server-side `tablestats`. (4) The node keeps the heap dump (687 MB) in `~/oom-direct-run8/logs/converge/`.

## 2026-11-09 — C1 reopen (convergence / custom Q, single-replica topology)

**Nodes:** CloudLab LAN 10.10.1.0/24 — victim `apt140`/10.10.1.1 (dc=v, `~/cassandra-b1`); 8 coordinator
instances dc=c on `apt179/138/190/149` (`~/cassandra-c1`, 1 GiB heap, LAN IP aliases .32–.81, 2/host).
**Design:** [`C1-design-v2.md`](candidates/internode_application_receive_queue_capacity-multiplicity/design/C1-design-v2.md). Case file:
[`internode_application_receive_queue_capacity--multiplicity--run2-customQ.md`](candidates/internode_application_receive_queue_capacity-multiplicity/internode_application_receive_queue_capacity--multiplicity--run2-customQ.md).
Reopens the run-2 **default**-Q negative to test whether a **raised (custom)** exclusive allowance N·Q can
drive the victim to OOM, under v2's three fixes (raise Q; victim owns the only replica so RF=1 keeps
senders light; concentrate load so backpressure is natural).

**Both v2 topology fixes succeeded.** G1: keyspace `NTS {v:1}` → `getendpoints` = victim-only (10/10 keys).
G2: at N=8 the 1 GiB coordinators stayed ~336–384 MiB heap, **no sender OOM** (run 2's 512 MiB/2 GiB
coordinators both OOMed under RF-fanout). G3: noise band **±~10 MiB** vs run 2's ±350 (load concentrated).
Natural backpressure now reaches ~1.5–1.7 MiB/conn (run 2: 0.4); with the declared Byteman 100 ms delay the
exclusive allowance fills to **exactly Q** per connection.

**Mechanism confirmed to the MiB; ladders show total occupancy is Q-invariant.** S1 (N=8): using ~266 MiB
at **every** Q, with exclusive = N·Q (32 / 128 / 267 MiB at Q = 4 / 16 / 64) and reserve taking the
remainder (234 / 138 / 0). S2 (Q=64): using scales with N (34 / 136 / 267 MiB at N = 1 / 4 / 8),
per-connection equilibrium ~34 MiB. Reduced-Q (Q=1): exclusive 8 MiB (= N·Q), reserve 258, total 266.
`throttled_count` ≡ 0 in every arm — the admission ceiling (A_max) is never reached; occupancy ~266 MiB
sits below G=512. Occupancy is also **invariant to client threads** (identical at 800 and 1500).

**Why no Q-attribution:** in the single-replica/CL=ONE topology the client blocks on the slow victim, so
the receive queue reaches a **closed-loop occupancy equilibrium** that raising Q merely **re-buckets**
(reserve→exclusive) without growing. A **load-driven direct-buffer OOM is reachable** — at
`-XX:MaxDirectMemorySize=384 MiB`, `OutOfMemoryError: Direct buffer memory` on the inbound `BufferPool.allocate`
path, victim JVM killed ~20–27 s into load, **3/3 clean-start repeats** — but it fires at the **same budget
for Q=4 and Q=64** (total footprint is Q-invariant), so it is an *aggregate receive-queue-footprint* sizing
hazard, **not** an exclusive-allowance multiplicity gap. Reduced-Q neither lowers the footprint nor moves
the threshold. Surviving control (budget 3072) reproduced ≥3 clean starts.

**Decision rule (verification-protocol):** a supported Q-multiplicity result needs physical memory tracking
N·Q **and** the reduced-Q control removing the OOM — both fail. **Q-attribution: UNRESOLVED / negative**;
the new obstacle (closed-loop occupancy equilibrium) is the dual of run 2's sender-OOM obstacle — decoupling
the client to reach the ceiling re-creates the coordinator retention run 2 hit.

**Stopping reason:** both ladders, the failing OOM point with 3 clean-start repeats and its surviving
control, the reduced-Q control, and the Q-independence control all ran within the ~3 h budget; no OOM was
manufactured (the direct-buffer OOM is real but Q-independent). **Raw logs** on the nodes under
`/mydata/c1r/victim/logs{,.prev}` and `/mydata/c1r/arms/<arm>/`; small excerpts in the case `logs/`.
**Cleanup verified:** no Cassandra JVMs, stress, IP aliases, port-7000 firewall rules, or systemd user
units on any node; linger disabled.

## 2026-11-10 — C1 run 3 (convergence / custom topology, fast co-replica)

**Nodes:** victim `apt140`/10.10.1.1 (dc=v, `~/cassandra-b1`, 1 GiB heap, 3072 MiB direct, cgroup 7168 MiB,
swap off); fast co-replica `apt179`/10.10.1.2 (dc=f, 4 GiB heap); 8 coordinators dc=c on `apt138/190/149`
(aliases .31–.33/.41–.43/.51–.52, 1 GiB). **Design:**
[`C1-run3-plan-review.md`](candidates/internode_application_receive_queue_capacity-multiplicity/design/C1-run3-plan-review.md)
(amends [`C1-design-v3.md`](candidates/internode_application_receive_queue_capacity-multiplicity/design/C1-design-v3.md)).
Case file:
[`internode_application_receive_queue_capacity--multiplicity--run3-fastcoreplica.md`](candidates/internode_application_receive_queue_capacity-multiplicity/internode_application_receive_queue_capacity--multiplicity--run3-fastcoreplica.md).

**Premise:** keyspace `NTS {v:1,f:1}`, CL=ONE, so the fast replica acks the client and the victim is flooded
open-loop (`cassandra-stress -rate fixed=`), with hints off on all instances.

**Results (calibration only):** G1 replicas = {victim, fast} for all sampled keys. Drain rate D ≈ 20/s
(1 MiB). G2 client at the offered 40 op/s, 22 ms, 0 errors. **G3 pass:** `fixed=150/s` N=4 peak 524 MiB
(16 excl + 508 rsv, A_max 528); `fixed=300/s` N=8 peak **543 MiB = 8×4.0 excl + 511 rsv (A_max 544)**,
throttling active; victim and all coordinators alive (no `java.lang.OutOfMemoryError`). `threads=1200`
reached the same ceiling but the client got `WriteTimeoutException`.

**Stopping reason / error:** the run was stopped after the calibration arms because the live sampler
summed cqlsh `|` separator fields and read 0 for every queue counter; it was first filed as "G3 fail". The
raw `arms/<arm>/queue.log` files, re-parsed the same day, show the ceiling was reached; the case file was
corrected. **Not run:** S1/S2 sweeps, reduced-Q, Stage D. **Open defect:** coordinators kept the default
2 s `write_request_timeout` (the sender sets `expiresAt`), so expiry was high and the Q=64 arms cannot reach
their ceiling until it is raised.

**Raw logs** on the nodes under `/mydata/c1r3/victim/logs{,.prev}`, `/mydata/c1r3/arms/<arm>/`,
`/mydata/c1r3/inst-*/logs`. **Cleanup verified:** no Cassandra JVMs, IP aliases or c1r3 systemd user
units on any node; linger (enabled for this run) disabled again.

---

# Part B — Default-value convergence runs

Originally `default-convergence/_batch-log.md`. Per [`../../default-convergence-playbook.md`](../../default-convergence-playbook.md).
Same format as the convergence/custom run entries in Part A above, plus the default-arithmetic verdict for each group surveyed.

## Current campaign status — 2026-11-06

This dated table governs new candidate selection. Historical domain-wide statuses
below describe only the earlier standing-pool combinations/arithmetic; they do
not exclude replicated local limits or transient overlap. No new runtime results
are asserted. See [campaign plan](../campaign-plan.md).

| Mechanism / allocation domain / regime | Status | Next action |
|---|---|---|
| C1 / internode private allowances / default capacities, budget separately labeled | **sensitivity-limited / unresolved** (run 2, 2026-11-09) | Mechanism confirmed exactly (N=4: per-conn exclusive=Q, Σreserve=G saturated, admitted=A_max); but N·Q (≤112 MiB) is dominated by the invariant G=512 reserve + occupancy noise, and senders OOM before high N. Reopen only with senders that survive RF-fanout to a slow victim (large heaps / dedicated load hosts) to test N=4 vs N=32 |
| C2 / per-query live memory / default capacities, budget separately labeled | open | Verify threshold applicability and actual concurrent working sets; unlimited defaults are a separate unprotected arm |
| C3 / per-worker DOB allocations / default capacities, budget separately labeled | open | Audit worker multiplicity and active versus retained buffers |
| Existing standing-pool combinations / original regimes | historical scope only; **recheck queued (R1–R4 P1, R5–R6 P2, 2026-11-11)** | Preserve results; reruns of the six pre-protocol OOMs for V1–V5 per [campaign plan R1–R6](../campaign-plan.md#prioritized-queue) are allowed; other new runs need a distinct mechanism or boundary question |
| Disk exhaustion / all regimes | skipped by request | No new disk runs or retries until explicitly reopened |
| Disk-to-memory causal chain / all regimes | deferred | Outside this batch; not implicitly reopened |

## Historical shared-budget group status

Independent of the original convergence playbook's table: a group exhausted there (raised values) is a separate question at defaults. Statuses as in the original (**open**, **exhausted**, **parked**, **skipped**, **deferred (causal-chain, not picked)**), plus **cannot converge at defaults** (the default arithmetic shows no budget where each is safe alone and the sum exceeds it; state the arithmetic).

**Rule: disk is skipped (carried over from the original playbook's 2026-11-02 request).** Do not pick a disk-group combination until it is lifted here.

| Shared budget | Constraints tried | Status | Why |
|---|---|---|---|
| On-heap JVM heap | none built (arithmetic only, run 1) | **cannot converge at defaults** | Every capped heap pool is a heap fraction or a small floor. At capacity, with if-check-exp's overhead factors: memtable 1.1 × H/4, key cache 2.0 × 5% H, counter cache 2.1 × 2.5% H, paxos cache ~2 × 1% H, prepared statements 10 MiB, baseline ≈ 57 MiB. Sum = 67 + 0.45H MiB, which exceeds H only below H ≈ 121 MiB. But the memtable alone needs H ≥ 134 MiB to stay ≥ 30% free. No window at any heap; above ~2 GiB the key/counter caps make it worse. The memtable also flushes at the default cleanup threshold (1/3 of its limit), so it rarely reaches H/4. Smallest non-default change: convergence run 1 (raise `memtable_heap_space` + `counter_cache_size`, cleanup 0.99). See run 1 below. |
| Off-heap/direct memory (`MaxDirectMemorySize`, `allocateDirect` pools) | `DOB_MAX_RECYCLE_BYTES` + `MAX_HINT_BUFFERS` (run 1) | **open** | Run 1 **OOMed, strict default**, at a 192 MiB direct limit. Both defaults are absolute (96 MiB hints pool, 1 MiB × shared-pool workers), so a window exists only at small direct budgets (about 173-200 MiB here), far below the automatic limit. Left open for the other default `allocateDirect` consumers seen in run 1: the networking `BufferPool` (`networking_cache_size` = min(128 MiB, heap/16), in-flight only) and compaction read-ahead buffers (256 KiB × compaction threads, not yet in `_constraint-groups.md`). |
| Off-heap JNA/malloc (cgroup budget) | none built (arithmetic only, run 1) | **cannot converge at defaults** | Only one pool exists at defaults: `index_summary_capacity` (5% heap). `memtable_allocation_type: heap_buffers` (shipped yaml line 825) keeps memtables on heap, so `memtable_offheap_space` holds nothing. `row_cache_size: 0MiB` (line 564) and `file_cache_enabled: false` (line 742) are off. A cgroup budget that mixes heap + direct + JNA is a cross-group question, not this group. |
| Disk | none | **skipped** (carried over, 2026-11-02 request) | See the original batch log (Part A). |

## 2026-11-04 — run 1 (default)

**Node:** `pc41` (`node0.jason92-323989...`, 40 cores, 251 GiB), same build as convergence runs 1-8 (`~/cassandra-run1`, cassandra-5.0.9). Shipped yaml read from the pristine `systems/cassandra/source/conf/cassandra.yaml`; note that `~/cassandra-run1/conf/cassandra.yaml` still carries run 7's edits. Harnesses use `git archive HEAD conf`, so they are unaffected.

**Counts:** 1 combination built and filed as a case (two workload designs); 2 groups judged by arithmetic only (on-heap, off-heap JNA); disk skipped.

**Default arithmetic per group:** see the status table. In summary:
- heap fractions never sum past the heap;
- the JNA group has one live pool at defaults;
- the direct group has two absolute defaults (hints pool 96 MiB; DOB 1 MiB × *T*), so a window exists at a small direct budget.

**Combinations attempted:**

1. `DOB_MAX_RECYCLE_BYTES` + `MAX_HINT_BUFFERS`, both unset, 500,000-byte values (so the doubled scratch buffer stays at or under 1 MiB) and a down replica. Case file: [`DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS.md`](candidates/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--default.md).
   - **Design A** (185 MiB, 64 hints threads): controls 66% / 67%; converge OOMed 2 of 2. **But the no-hints attribution control also died.** The extra writers raised the DOB pool to 99.5% by themselves, and compaction read-ahead buffers ended it. Not filed as the result.
   - **Design B** (192 MiB, 8 hints threads, DOB control run at matched concurrency): alone 63% / 69.3%. Converge: `OutOfMemoryError: Direct buffer memory` 7 s into the burst, forced heap OOM, JVM killed. **OOMed, strict default.**

**Considered and not picked:**
- Every on-heap and JNA combination: no window at defaults (table).
- `max_hints_size_per_host` (default 0 = unlimited): not a cap at its default; disk group anyway. A candidate for an "unbounded at default" note.
- `networking_cache_size` (default min(128 MiB, heap/16)): in-flight only, as in the original batch log.

**Stopping reason:** the one viable group at defaults produced a filed OOM, with a clean attribution control after one redesign. The other memory groups were closed by arithmetic.

**Notes for the next run:**
1. At defaults the DOB pool is about 1 MiB × the shared-pool workers that ever serialize a mutation of up to ~0.5 MB. Any concurrent traffic raises that count, so a DOB control must run at the convergence arm's total concurrency (`B_D_matched`), not alone.
2. 8 client threads of 1 KiB hinted writes fill the default 3-slab hints pool within 10 s.
3. `ThreadLocalReadAheadBuffer` (compaction, direct, 256 KiB each) is a third default direct consumer that can end an arm sitting near the limit.
4. `start_node` clears `N1-logs`, deleting the previous arm's heap dump. Copy the dump out first if it is needed.

## 2026-11-09 — run 2 (default; C1, internode receive queues)

**Nodes:** CloudLab APT, one experiment, LAN 10.10.1.0/24, user jason92. Victim `apt140` (10.10.1.1,
16 threads, 15 GiB, cgroup v2, swap 8G). Peer hosts `apt179/138/190/149` (10.10.1.2–.5), each 16 threads/
15 GiB. cassandra-5.0.9 built locally (`~/cassandra-b1` victim, `~/cassandra-c1` peers). Run data on
`/mydata` only. Internode port 7000 restricted to 10.10.1.0/24 during the run (removed after).

**Mechanism / allocation domain / regime:** C1, internode inbound receive queues (exclusive Q=4 MiB,
endpoint E=128 MiB, global G=512 MiB — **defaults**), tightened diagnostic direct-memory budget. First
convergence case in this project driven by **multiplicity of active peers** rather than two stacked pools,
and the first multi-instance ring (up to 33 Cassandra instances via LAN IP aliases).

**Attempted:** one case — [`internode_application_receive_queue_capacity--multiplicity--run1-defaultQ.md`](candidates/internode_application_receive_queue_capacity-multiplicity/internode_application_receive_queue_capacity--multiplicity--run1-defaultQ.md).
Arms: G1 reachability; D_cal_n4 (reference, Byteman 100 ms apply-delay, Q=4, 2048 MiB budget); D_cal_n8;
RQ_n4_q1 (reduced-Q causal control, Q=1 MiB); D_oom_n4_b450 (450 MiB budget). **Result: mechanism confirmed
exactly, multiplicity-OOM sensitivity-limited / UNRESOLVED.** At N=4 the admitted bytes = 527.8 MiB =
A_max(4)=N·Q+G=528, per-connection = 4.0 MiB exclusive (=Q) + 127.9 MiB (=E), Σreserve = 511.8 MiB (G
saturated); reduced-Q drops per-conn exclusive to exactly 1.00 MiB. But the escaping term N·Q (16→128 MiB
over N=4→32) is dominated by the invariant reserve G=512 MiB and by ±~350 MiB occupancy noise, and the peer
coordinators OOM (heap, retaining 128 KiB mutations for the slow victim) before a high-N arm can be
sustained — so N=16/32 could not be reached and the RF=33 ring was reduced to RF=9.

**Key empirical blockers (all anticipated by the design's decision rules):**
1. **No natural backpressure** — at reachable load the victim's MutationStage drains and queues stay ~0;
   the designed **Byteman apply-delay** (frozen, saved) was required to fill them, so queue-fill results are
   conditional on injected delay; reproduction without it is negative.
2. **Sender bottleneck** — 512 MiB (and even 2 GiB) peer coordinators OOM under RF fanout to a slow victim.
3. **Reserve dominates** — receive-queue memory is ~all the shared G=512 MiB reserve, invariant across N; a
   direct-buffer OOM is reachable only at a budget (450 MiB) so tight that baseline + reserve exceed it
   before load — reserve/baseline-driven, not multiplicity.

**Infrastructure notes for the next run (multi-instance Cassandra rings):**
1. `num_tokens: 1` without `initial_token` causes **random-token collisions** across many simultaneous
   fresh nodes — nodes get dropped from the ring. Assign explicit evenly-spaced `initial_token` per instance.
2. A `systemd-run --user` transient **service** (not `--scope`) survives the launching ssh session, but
   needs `loginctl enable-linger` or the user manager tears it down when the session closes.
3. Do **not** wipe a node's `data/` to "freshen" it between restarts — it erases `system.local` and the
   rejoin hits an endpoint collision; keep the data to rejoin, or use `replace_address_first_boot` +
   `allow_unsafe_replace=true`.
4. Peers need distinct JMX ports: `cassandra-env.sh` hardcodes `JMX_PORT="7199"`; sed it per instance. JMX
   binds to 127.0.0.1 — use `nodetool -h 127.0.0.1 -p <port>`.
5. `cassandra-stress -node whitelist <csv>` restricts coordinators to exactly those peers (WhiteListPolicy).
6. Byteman on a Cassandra class (`MutationVerbHandler.doVerb`) needs no `boot:`; confirm the rule actually
   fires (`bmsubmit -l`) — a loaded rule that isn't delaying usually means the arm hit a *dead* coordinator,
   not a Byteman failure.
7. Raising `write_request_timeout` (here 30 s) lifts the message-expiry ceiling so the receive queue can
   hold more than `arrival × 2 s` before expiry releases permits.

**Stopping reason:** the mechanism was confirmed to the model and the sensitivity limit was reached and
quantified (noise ≫ multiplicity signal; senders fail before high N). No OOM was manufactured. Reopen only
with senders that survive RF-fanout to a slow victim (much larger heaps or dedicated load hosts) to test the
N=4 vs N=32 window directly. Cleanup verified: no Cassandra JVMs, IP aliases, or port-7000 rules left on any
node; lingering disabled.

---

# Part C — Bypass runs

Originally `bypass/_batch-log.md`.

## Current campaign status — 2026-11-06

Planning entries as of 2026-11-06; updated 2026-11-11 with B6 (the first bypass
runs, entries below). Use the
[campaign plan](../campaign-plan.md) and [protocol](../../verification-protocol.md).
Append dated execution records with attempted/skipped cases, configuration/budget
regime, evidence, status/range and stopping reason.

| Mechanism / allocation domain | Priority | Status / next action |
|---|---|---|
| B1 / native-v5 request allocation lifecycle | P1 | open; audit recorded retention and construct repeated-cycle controls |
| B2 / memtable and pre-V5 exceptional admission | P2 | open; separate paths, quantify outstanding-work bounds |
| B3 / buffer-pool fallback | P2 | open; distinguish pool contract from total allocation |
| B4 / cache explicit-clear release | P2 | open; trace ownership before repeated-cycle test |
| B5 / periodic enforcement or replacement ordering | P3 | open; verify format/path and temporal bounds |
| B6 / internode send+receive queues vs heap `Mutation`s (`source: flow:coordinator-write`) | P1 | **verified 2026-11-11** (runs 1–3; [case](bypass/internode_application_queue_capacity-accounting-mismatch/internode_application_queue_capacity--accounting-mismatch.md)): A — 8 GiB replica, storage stall, default settings: `verified-gap · service-loss · deployment`; B — 2 GiB coordinator, slow replica, 60 s timeouts: `reproduced-OOM · diagnostic` (was `verified-OOM`; V7 unmet, reclassified 2026-11-11); C — 2 GiB replica: candidate. Next: JIRA check (CASSANDRA-15066), stall-length sweep, ≥ 2 slow replicas at 8 GiB |

## 2026-11-10 — B6 run 1 (bypass · accounting mismatch, default capacities)

*(Entry written from the case file and raw arm logs after the run; the run's own session did not append one.)*

**Lead source:** `flow:coordinator-write` (traced from C1's write path). **Node:** `pc96`
(`node0.jason92-325405`), three instances on loopback: slow replica V 127.0.0.11 (Byteman 100 ms at
`MutationVerbHandler.doVerb`, `concurrent_writes: 2`), fast replica F .12 (8 GiB, acks CL=ONE),
coordinator S .13 (client talks only to S). Keyspace `NTS {v:1,f:1}`, hints off, caches 0.
Default internode queue capacities (4/128/512 MiB); measured instance at a tightened 2 GiB heap.
Supporting deviations: `write_request_timeout` and `native_transport_timeout` 60 s (defaults in D arms).
Design: [`B6-design.md`](bypass/internode_application_queue_capacity-accounting-mismatch/design/B6-design.md); case: [`...--run1`](bypass/internode_application_queue_capacity-accounting-mismatch/history.md#run-1).

**Arms (harness `bypass/internode_application_queue_capacity-accounting-mismatch/harness/`, batches 1–3):**

| Arm group | n | Outcome |
|---|---|---|
| A1–A3 calibration (S, V at 8 GiB; A1 V at 2 GiB) | — | R = heap/on-wire: map 19.7× (S) / 16.7× (V), blob 2.2×; K = 132 MiB while U = 5.6 GiB (S) / 2.2 GiB (V). A1: unplanned V heap OOM → receive domain added |
| `B_S2g_map_r1–3` | 3 | **3/3 S heap OOM**, S→V `pending_bytes` 0 (retention after flush via `hintOnFailure`) |
| `B_S2g_blob_r1–3` | 3 | 0/3, queues full (132 MiB) and dropping |
| `B_V2g_map_r1–3` | 3 | **3/3 V heap OOM**, V←S `using_bytes` ≤ 122 MiB |
| `B_V2g_blob_r1–3` | 3 | 0/3 |
| `C_{S,V}2g_map_rsv8m` (endpoint reserves 8 MiB) | 1 each | both alive, 0 client errors |
| `D_{S,V}2g_map_deftimeout_c4/c16` (default deadlines) | 1 each | all alive; queues ≤ 56 MiB; client ≤ 2.3k inserts/s (≈ 6k/s needed) |

**Status:** candidate — bypass (accounting mismatch) confirmed on two domains; OOM reproduced with
supporting deviations; default-timeout reproduction **not established** (blocked by load-generator rate,
not shown safe). Interpretation: documented on-wire accounting unit (sizing gap) plus uncovered
after-flush coordinator retention. **Stopping reason:** planned endpoint reached for batches 1–3.
**Raw logs:** `/mydata/b6/runs/<arm>/` on `pc96` (heap dumps 2.9 GB for A1 and `B_S2g_map_r1`); excerpts in
the case `logs/`. **Cleanup:** all instances stopped after each batch; no Java process left on `pc96`.

## 2026-11-10/11 — B6 run 2 (bypass · accounting mismatch, replica disk stall, default timeouts)

*(Entry written from the case file and `logs-run2/arm-outcomes.txt`; the run's own session did not append one.)*

**Node:** `pc96` (`node0.jason92-325405`), six instances on loopback: replica V 127.0.0.11 with data,
commit log and hints on `/mydata/b6/slow` (ext4 on a dm-delay device over a loop file), fast replica F
(8 GiB), coordinators S1–S4 (8 GiB). `NTS {v:1,f:1}`, CL=ONE, hints off, caches 0, **all timeouts
default, default `concurrent_writes`, no Byteman**. Client: Java driver (`harness-run2/B6Load.java`),
256 in flight per coordinator. Replica heap 8 GiB (deployment-like) and 6 GiB. Design:
[`B6-run2-design.md`](bypass/internode_application_queue_capacity-accounting-mismatch/design/B6-run2-design.md); case:
[`...--run2-diskstall`](bypass/internode_application_queue_capacity-accounting-mismatch/history.md#run-2).

| Arm group | n | Outcome |
|---|---|---|
| map, 30 s stall, V 8 GiB | 2 | 98.7–99.3% live after Full GC; 59–64 Full GCs, ≈ 105 s pause; alive |
| map, 30 s stall, V 6 GiB | 3 | 99.1–99.5% live; 39–81 Full GCs; **r2 heap OOM** (killed) |
| blob, 30 s stall, V 8/6 GiB | 3 + 1 | 0 Full GCs (≈ 4× the on-wire traffic) |
| map, no stall, V 8 GiB | 1 | ≤ 26.9% live |
| map, 30 s stall, receive endpoint reserve 8 MiB | 1 | ≤ 21.6% live, 1 Full GC, 0 client errors |
| 600 s hang: map V 8 GiB ×2, map V 6 GiB ×1, blob V 8 GiB ×1 | 4 | map: JVM froze (≈ 136–138 s local pause) in 2/3, **8 GiB r2 heap OOM** in 1/3; blob alive |

**Status:** candidate — receive-side accounting mismatch reproduced without run 1's deviations;
outcome mostly **GC-driven service loss** (not OOM per protocol), **2 heap OOMs** in 8 map stall/hang
arms. Interpretation: documented on-wire unit → sizing gap. **Stopping reason:** planned arms complete.
**Raw logs:** `/mydata/b6/runs2/<arm>/` on `pc96`; excerpts in the case `logs-run2/`. **Cleanup:** all
instances stopped and dm-delay reset to 0 after each batch; the dm-delay device and loop file are kept on
`pc96` for reuse.

## 2026-11-11 — B6 run 3 (bypass · accounting mismatch; V1/V4 of the promotion rule)

**Node:** `pc96`, same build, harnesses and devices as runs 1–2, called unchanged by
`harness-run3/batch.sh`. Design (written before readings):
[`B6-run3-design.md`](bypass/internode_application_queue_capacity-accounting-mismatch/design/B6-run3-design.md); case:
[`...--run3-intervention`](bypass/internode_application_queue_capacity-accounting-mismatch/history.md#run-3).
Purpose: three fresh endpoint-reserve interventions per condition, a same-day positive per condition,
and a third clean-start repeat of run 2's failing condition. Batch 11:46–12:52.

| Arm group | n | Outcome |
|---|---|---|
| run-2 condition, map, 30 s stall, V 8 GiB (positive) | 1 | 99.3% live, 98% of 126 s in Full GC (service loss MET); alive |
| run-2 condition + receive endpoint reserve 8 MiB | 3 | 1 Full GC each, 22.1–30.9% live, 0 client errors; coordinators ≤ 8.2% (one arm) |
| run-1 condition, S 2 GiB (positive) | 1 | **heap OOM**, dump 2.85 GB, S send queue empty |
| run-1 condition, S 2 GiB + send/receive endpoint reserves 8 MiB | 3 | survived; 20–26 Full GCs, 69.2–75.0% live; S dropped ≈ 51–58k writes to V (overload) |
| run-1 condition, V 2 GiB (positive) | 1 | **no OOM**: 98.2% live, 131 Full GCs, 57% of 83 s in Full GC, alive at end of load |
| run-1 condition, V 2 GiB + reserves 8 MiB | 3 | survived; 0 Full GCs, ≤ 25% heap after any GC |

**Status (as run):** candidate pending filing. Under the protocol's promotion rule, run 2 meets V1–V5
(`verified-gap · service-loss`, conditions label pending: hints off) and run 1's coordinator side
meets V1–V5 (`verified-OOM · diagnostic`); run 1's replica side stays candidate (its same-day positive
did not reproduce). **Stopping reason:** planned 12 arms complete. **Raw logs:**
`/mydata/b6/runs2/R3B_*`, `/mydata/b6/runs/R3A_*` on `pc96`; excerpt in the case `logs-run3/`.
**Cleanup:** `pgrep java` empty, dm-delay reset to 0; device and loop file kept for reuse.

**Filed 2026-11-11 (after the run):** run 2's condition labelled `deployment` (hints off is an
accepted, documented setting); B6 consolidated into one final case file in `bypass/`
([case](bypass/internode_application_queue_capacity-accounting-mismatch/internode_application_queue_capacity--accounting-mismatch.md)) with runs 1–3 kept verbatim in its `history.md`; the
folder moved from `candidates/internode_application_send_queue_capacity-accounting-mismatch/`.

## 2026-11-11 — reclassification: pre-protocol convergence OOMs → candidates

No runs. By the researcher's decision, the six convergence OOMs filed before the
2026-11-06 protocol were moved from `convergence/` to `candidates/` with status
`candidate (pre-protocol)`: convergence runs 1, 2, 6, 7, 8 and default run 1. Runs 4
and 5 (superseded by run 6) moved with them. Each has one failing run of its filed
condition, one run per control and at most one intervention run, so V1, V2 and V4
of the promotion rule are unmet; V3 is met by direct usage readings; V5 has the
first error or kill record but no holder histogram at failure. The recorded OOMs
are unchanged. `convergence/` is now empty. Recheck order suggested: run 7 and
run 8 (hard standing caps; run 8 has the `converge_Ldefault` intervention), then
runs 1–2, then run 6 and default run 1 (timing- or window-sensitive; may reach
only a stated rate below 3/3).

## 2026-11-11 — R1–R4 recheck of pre-protocol convergence OOMs (four nodes in parallel)

**Setup.** One case per node, one agent per case, run in parallel: R1 on `pc96` (32 cores,
125 GiB), R2 on `apt140`, R3 on `apt149`, R4 on `apt179` (APT r320, 16 threads, 15.5 GiB). Same
Cassandra 5.0.9 source tree (`b796bcfd…`) on every node, each in its own copy under
`/mydata/oom-recheck/<Rn>/`. Same settings, budgets, workloads and harnesses as the filed runs
(path changes, pinned overrides and added readings only; diffs in each case's
`recheck-2026-11-11/`). Node change from `pc41` (40 cores) disclosed in each case. Each arm ×3
from clean starts; dated designs written before readings. Full logs and dumps stay on the nodes.

- **R1 · memtable_offheap_space + file_cache_size (run 7), pc96, 14 executions, ≈ 3 h 20 min.**
  Converge: kernel memcg OOM-kill 3/3, 7–11 s into the burst (anon-rss 3467–3468 of 3500 MiB);
  an uninstrumented converge was also killed. M_alone / F_alone 0/6 at 76.0–77.6% (margin ≈ 22%,
  below the 30% target, disclosed). Intervention `file_cache_size` 300 MiB: 0/3 at the same burst
  rate (≈ 16.5–17k op/s). At each kill the chunk cache was exactly 1200 MiB (JDK direct) and the
  memtable counter 283–738 MiB (physical ≤ 793 MiB, a bound: NativeAllocator uses JNA malloc,
  not NMT-tracked). Every domain ≤ its cap → convergence. Not run: deployment-budget and
  default-cleanup-threshold arms.
- **R2 · DOB_MAX_RECYCLE_BYTES + MAX_HINT_BUFFERS, custom (run 8), apt140, 13 executions, ≈ 2 h.**
  `HINT_LEAD` amended 20 → 50 s before any converge reading (hints pool needs 47–84 s to fill
  here). Converge: direct-buffer OOM 3/3, ≈ 10 s into the 4 MB burst, hints pool at 8 slabs.
  H_alone 3/3 at 49.6%; D_alone 3/3 at 70.0–71.4% (70% margin missed by ≤ 1.4 points,
  disclosed). Intervention L = 1 MiB: 0/3, thin margin (transient peaks 93–94%). Dumps (python
  HPROF reader), identical in all three: 559.5 MiB charged = 282 MiB DOB scratch (36 kept
  7.63 MiB buffers on MutationStage and native-transport threads) + 256 MiB hint slabs + ≈ 21 MiB other.
- **R3 · memtable_heap_space + counter_cache_size (run 1), apt149, 14 executions, ≈ 3 h.**
  Converge: Java heap OOM 3/3 at ≈ 5 min, ≈ 6.5 min of back-to-back Full GC, then heap dump and
  kill by the shipped `OnOutOfMemoryError` (run 1's JVM survived; likely stopped by its harness
  before the kill fired, unverified). M_alone / C_alone 0/6 (≤ 65%). Intervention
  `counter_cache_size` 50 MiB: 0/3 at matched throughput. Dumps: memtable 535 MiB (counter 532,
  cap 550); counter cache 327–337 MiB (counter 185–190, cap 300) → the cache weigher omits
  per-entry container overhead; the caps alone (907 MiB with baseline) fit the heap → **mixed**.
- **R4 · memtable_heap_space + counter_cache_size + key_cache_size (run 2), apt179, 20 executions,
  ≈ 4.5 h.** Converge: Java heap OOM + JVM kill 3/3 at 6.5–15.5 min. M/C/K alone 0/9 (15–57%).
  Intervention counter cache to auto (25 MiB): 0/3, all 7.6M operations complete (live ≤ 748 MiB,
  still 24–37% GC time). The row's suggestion, key cache to auto (51 MiB): 3/3 OOM (counter cache
  refills the heap), so it is not an intervention. Dumps: memtable 334 MiB ≤ C; counter cache
  U 292 / K 168 / C 250; key cache U 222 / K 109 / C 200 → **mixed**. Open lead: an
  8,589,934,600 B failed allocation logged in two arms on a byte-array read thread.

**Filing.** All four meet V1–V5 and moved from `candidates/` to `convergence/<case>/` as
`verified-OOM · diagnostic` (one final case file + `history.md` with the run-1/2/7/8 case files
verbatim + `recheck-2026-11-11/`). R3 and R4 carry the **mixed** tag. New bypass lead from R3/R4:
B7 (cache weigher omits container overhead) in the campaign plan. **Cleanup:** no Cassandra,
stress or harness processes left on any of the four nodes; data under `/mydata/oom-recheck/`.

## 2026-11-11 — protocol amendment V6–V7 (defaults and acceptable budget): reclassification

No runs. By the researcher's decision the promotion rule gained V6 (every constraint the
endpoint depends on at its shipped default) and V7 (a heap/memory budget argued acceptable case
by case and reviewed before readings), and a new status `reproduced-OOM` / `reproduced-gap` for
cases meeting V1–V5 only ([protocol](../../verification-protocol.md#defaults-and-acceptable-budget-amended-2026-11-11)).
Effect, evidence unchanged:

- R1–R4 (runs 7, 8, 1, 2) moved from `convergence/` back to `candidates/` as
  `reproduced-OOM · diagnostic` (R3, R4 still mixed): each uses raised capacities (1.4–12× the
  defaults) and a deliberately tightened heap, direct or cgroup budget. Their case files carry a
  dated status note naming the unmet V6/V7 values.
- B6 condition B (2 GiB coordinator, 60 s timeouts): `verified-OOM · diagnostic` →
  `reproduced-OOM · diagnostic` (default capacities, V6 met; tightened 2 GiB heap, V7 unmet).
- B6 condition A (default capacities, 8 GiB replica, external storage stall) keeps
  `verified-gap · service-loss · deployment`; its 8 GiB heap was reviewed and accepted by the researcher the same day (V7 met).
- `convergence/` is empty again. Next step for R1–R4: test the same mechanisms with default
  constraints at an acceptable budget (a clean no-failure result there is a `negative`).

