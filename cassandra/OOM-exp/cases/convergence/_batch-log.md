# Convergence playbook — batch log

Append one entry per playbook run, per [`../../convergence-playbook.md`](../../convergence-playbook.md).

## Shared-budget group status

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
| Disk → heap (causal-chain) | none picked | **deferred (causal-chain, not picked)** | Flagged during the 2026-11-02 "picking combinations" discussion: disk pressure (commit log/data disk full or slow) stalling flush/compaction could let an on-heap backlog queue grow unbounded — heap OOMs from the backlog, not from a shared pool with disk. This is a distinct convergence mechanism from every other row in this table (causal, not pool-sharing) and is **out of scope for picking combinations today** per `convergence-playbook.md`'s "Picking combinations" step 1 — recorded here so it isn't rediscovered as a gap, not because it's ready to build. |

## 2026-11-02 — run 1

**Node:** `node0.jason92-323989.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB RAM, local disk `/dev/sda3` 63 GB). JDK 11.0.32.1 and Ant 1.10.12 installed fresh; source copied from repository commit `0be49fb6` to `~/cassandra-run1` via `copy-source.sh`, built with `ant build-test`.

**Shared-budget group surveyed:** on-heap JVM heap (`-Xmx`), using the two config-type true-positive cases the task pointed at: `memtable_heap_space` (memtable pool, soft/self-reclaiming cap) and `counter_cache_size` (counter cache, Caffeine weight cap, non-self-reclaiming). Both draw on the same single-node `-Xmx`.

**Combinations attempted:**

1. `memtable_heap_space` (M=550 MiB) + `counter_cache_size` (C=300 MiB), `-Xmx1024M`/`-Xms1024M`, concurrent `cassandra-stress write` + `cassandra-stress counter_write` — case file: [`memtable_heap_space+counter_cache_size.md`](memtable_heap_space+counter_cache_size.md). **Result: OOM reached** (14 genuine `OutOfMemoryError: Java heap space` throws across unrelated thread pools; both control arms safe with 33–39% free margin).

**Combinations considered and skipped (not built or run):**

- A larger 3-way combination (adding `index_summary_capacity`, `row_cache_size`, or `native_transport_max_request_data_in_flight` on top of the two already run) was not attempted this run: the 2-constraint combination above already reached OOM at a comfortable margin (126% of `-Xmx` predicted, 96.6% used + 0 young regions actually observed), so a 3-way combination would not add evidence about whether 2 constraints already suffice — it would need its own fresh sizing and control arms to be a real case, and the playbook asks for rigor over quantity on the first run.
- No other shared-budget group (off-heap/direct memory, disk) was surveyed this run; this run's budget was fixed by the task to on-heap JVM heap only.

**Stopping reason:** time/rigor budget for a first run — one combination was built, sized with a stated arithmetic prediction, run through both control arms and the convergence arm, and filed as a complete case with raw-log evidence for every claim. The shared-budget group (on-heap, these two constraints) is not marked exhausted: a 3-constraint extension on the same heap budget (e.g. adding `row_cache_size` or `index_summary_capacity`) remains open for a future run, as does trying smaller M/C values to find the actual minimum combined sizing that still OOMs (this run deliberately sized with margin to exceed, not to find the tightest boundary).

**Verification environment notes carried to the next run:** `jcmd GC.heap_info` and `jcmd GC.run` both slow down sharply (14 s and 74 s respectively, vs. <1 s normally) once the heap is genuinely under OOM pressure — budget extra wall-clock time for the final reading in a future convergence arm that pushes this hard. `sudo dmesg -T` needs `sudo` (plain `dmesg` fails with "Operation not permitted" on this node's kernel).

## 2026-11-02 — run 2

**Node:** same node (`pc41`/`node0.jason92-323989...`), same build (`~/cassandra-run1` at `cassandra-5.0.9`, unchanged since run 1 — no rebuild needed).

**Shared-budget group surveyed:** same on-heap JVM heap group as run 1, extended to a 3rd constraint — the open follow-up from `HANDOFF.md`. Checked the two candidates it suggested (`row_cache_size`, `index_summary_capacity`) against their stage-4 results for the first time: both are **off-heap** (`Native.malloc`/off-heap index-summary bytes), not on-heap, so neither is a clean addition to this group. Surveyed on-heap true positives instead and picked `key_cache_size` (config-type true positive, same Caffeine-weighted-cache family as `counter_cache_size`).

**Combinations attempted:**

1. `memtable_heap_space` (M=350 MiB) + `counter_cache_size` (C=250 MiB) + `key_cache_size` (K=200 MiB), `-Xmx1024M`/`-Xms1024M`, concurrent `write` + `counter_write` + `read` (the read arm needs a preloaded, flushed dataset — key cache only engages on sstable reads, not memtable reads) — case file: [`memtable_heap_space+counter_cache_size+key_cache_size.md`](memtable_heap_space+counter_cache_size+key_cache_size.md). **Result: OOM reached, JVM killed.** Smaller individual values than run 1's 2-constraint case (chosen so no pairwise subset was already enough to overshoot), each alone safe (46–87% heap free, 0 errors), combined drove the heap to 989/1024 MiB (96.6%) right after a forced full GC with a 72-byte allocation failing, a genuine `OutOfMemoryError`, a 1.35 GB heap dump, and — unlike run 1's case, where the JVM survived — `-XX:OnOutOfMemoryError=kill -9 %p` actually fired and killed the process.

**Combinations considered and skipped (not built or run):**

- A 4th constraint on top of M+C+K was not attempted: the 3-way combination already reached a harder outcome (genuine crash, not just caught `OutOfMemoryError`s) than run 1's 2-way case, so a 4th constraint wouldn't add evidence about whether 3 already suffice.
- The off-heap group (`row_cache_size` + `index_summary_capacity`, both off-heap true positives found while surveying this run) was noted but not run: off-heap convergence needs a different way to make the budget tight (the node's 251 GiB of physical RAM is not a usable ceiling for off-heap the way `-Xmx` is for on-heap; off-heap budgeting here would likely need a cgroup memory limit or similar, not yet set up) — left as a candidate for a future run, possibly closer to `bypass-playbook` territory if `-XX:MaxDirectMemorySize` turns out to be the more relevant constraint.
- Finding the tighter minimum M+C+K boundary (vs. this run's margin-sized values) was not attempted — same "rigor over quantity" reasoning as run 1.

**Stopping reason:** one new combination built, sized with a stated arithmetic prediction, run through three control arms plus the convergence arm, and filed as a complete case. One harness bug was hit and fixed mid-run (the `read` workload's `cassandra-stress` call needed `-col` to match the preload write's or validation failed immediately — see the case file §2.3/Instrument check) — the result reported is the corrected re-run, not the failed first attempt.

**Verification environment notes carried to the next run:** when the JVM genuinely runs out of room (not just gets close), `jcmd GC.run` can take minutes (3m40s here) to return, and a subsequent `jcmd GC.heap_info` can fail outright with `Premature EOF` if the process dies in between — treat a failed final heap sample as a signal to check `logs/gc.log`'s last lines (`ReportJavaOutOfMemory` safepoint) and for an `.hprof` file before assuming the harness itself broke. `set -Eeuo pipefail` scripts should expect this failure mode (a non-zero `jcmd` return) to trip the `ERR` trap and skip the harness's own post-run steps (error-count, oom-grep, dmesg) — recompute them manually from `system.log`/`dmesg` directly when that happens, which is what `converge/error-count.txt`'s comment in this case does.

## 2026-11-02 — run 3

**Node:** same node (`pc41`/`node0.jason92-323989...`), same build (`~/cassandra-run1`, unchanged). First run in this project to use a second node (127.0.0.3) and a dedicated loop-mounted disk budget (`~/oom-disk-run3/disk3.img`, 1536 MiB, mounted at `~/oom-disk-run3/mnt`) rather than the node's real local disk.

**Shared-budget group surveyed:** disk (shared-pool sense), per `HANDOFF.md`'s open follow-up. Surveyed if-check-exp's disk-bound true positives: `commitlog_total_space`, `max_hints_size_per_host`, `max_space_usable_for_compactions_in_percentage`, `cdc_total_space`, `repair_disk_headroom_reject_ratio`. Rejected `cdc_total_space` as a pairing with `commitlog_total_space` specifically (not disk in general) — CDC segments are **hard-linked** to the main commit log segments, so their on-disk bytes overlap rather than add; combining them would not be a genuine sum of two independent consumers. Rejected `max_space_usable_for_compactions_in_percentage` and `repair_disk_headroom_reject_ratio` as a first pair — both are protective *gates* (they refuse further compaction/streaming/repair once headroom is low) rather than *quota consumers* that themselves grow disk usage when pushed to capacity, so "pushing them to capacity" doesn't load the disk the way the heap cases' pools did. Picked `commitlog_total_space` + `max_hints_size_per_host`: both are true-positive byte quotas on genuinely separate directories that default to the same disk unless an operator splits them onto separate mounts, and `max_hints_size_per_host` has a tight, well-characterized overshoot bound from its own if-check-exp stage-4 run.

**Combinations attempted:**

1. `commitlog_total_space` (target 800 MiB) + `max_hints_size_per_host` (target 900 MiB), on a dedicated 1536 MiB loop-mounted disk budget, 2-node ring (127.0.0.2 under test, 127.0.0.3 killed to generate hints) — case file: [`commitlog_total_space+max_hints_size_per_host.md`](commitlog_total_space+max_hints_size_per_host.md). **Result: OOM not reached — blocked before a valid convergence arm could run.** The `commitlog_alone` control arm (meant to confirm commit log is safe alone) instead ran the mount to 100% full from flush/compaction overhead the sizing hadn't budgeted for, tripping a real `FSWriteError`/`disk_failure_policy=stop` event, and separately produced real (non-stale-log) hint growth in an arm meant to produce zero hints — diagnosed as contention-induced false suspicion from two co-located JVMs plus a loaded stress client on one host. The `hints_alone` and `converge` arms were never run as a result. Filed as a **blocked, retryable** case, not exhausted — see the case file §4 for the specific fixes a retry needs (bigger mount or throttled workload; `phi_convict_threshold` tuning or incidental-hint accounting).

**Combinations considered and skipped (not built or run):**

- `commitlog_total_space` + `cdc_total_space`: rejected before building — CDC segments hard-link to the main commit log segments, so they do not add as independent disk consumers (see above).
- `max_space_usable_for_compactions_in_percentage` and `repair_disk_headroom_reject_ratio` as a pairing: rejected before building — both are protective gates, not quota consumers; pushing either "to capacity" causes Cassandra to refuse further work, not to keep growing disk usage, so they don't fit this playbook's convergence shape the way a true quota does.

**Stopping reason:** the one combination attempted surfaced a genuine sizing error and a genuine environmental confound mid-run (both diagnosed with concrete log evidence, documented in the case file's §3.0 and §4), rather than clearing to a clean result. Rather than continuing to resize/re-tune blind within this run, the decision was to stop here, file what was found as a blocked-not-exhausted case, and leave the retry (bigger mount/throttled workload, `phi_convict_threshold` tuning) for a future run.

**Verification environment notes carried to the next run:** (1) Cassandra's JMX/RMI listener binds to `127.0.0.1` regardless of `listen_address` — use `nodetool -h 127.0.0.1 -p <node's own JMX port>`, never the node's own gossip address, matching if-check-exp's own hints harness convention. (2) A pidfile-based "is it stopped" check can report false before the JVM actually finishes exiting (the shutdown hook removes the pidfile early); give `pgrep`-based confirmation a ~60s retry budget, not a short one. (3) Running two Cassandra JVMs plus a loaded stress client on one physical host is not resource-neutral: it caused both a 34-second local-pause warning from the failure detector in an early attempt and, in the final attempt, real hint generation toward a replica that never actually went down — any future multi-instance-on-one-host harness in this project should expect this and either budget for it or raise `phi_convict_threshold`. (4) A disk-budget mount's size must account for flush-and-compaction overhead as its own large consumer, not just the byte targets of the constraints under test — the heap cases' arithmetic (baseline + per-constraint overshoot) does not carry over to disk without this extra term.

## 2026-11-02/03 — run 4

**Node:** same node (`pc41`/`node0.jason92-323989...`), same build (`~/cassandra-run1`, unchanged). First run in this project to target the off-heap/direct-memory shared budget (previously parked) and the first to use a **cgroup v2 `memory.max`** (via `systemd-run --user --scope`) as the actual budget, rather than `-Xmx`.

**Shared-budget group surveyed:** off-heap/direct memory, per `HANDOFF.md`'s open follow-up. Confirmed `row_cache_size` and `index_summary_capacity` (surveyed in run 2, see `_constraint-groups.md`'s off-heap table) as the two off-heap true positives to pair. **Key design correction made before any run**: the task's suggested budget mechanism, `-XX:MaxDirectMemorySize`, does **not** actually bind either constraint — both allocate via `MemoryUtil.allocate → JNA Native.malloc`, which never touches the JVM's `DirectByteBuffer`/`Bits.reserveMemory` accounting that flag polices (confirmed from both constraints' own if-check-exp case files, which independently note this and use `RssAnon`, not any JVM-reported metric, for exactly this reason). The real budget enforced in this run is a cgroup v2 `memory.max`, independently verified with a smoke test (500 MiB limit against a ~900 MiB idle-baseline node produced a genuine kernel `Memory cgroup out of memory: Killed process ... (java)` within ~25s).

**Combinations attempted:**

1. `row_cache_size` (550 MiB, `SerializingCacheProvider`) + `index_summary_capacity` (100 MiB configured cap; effective pre-resize transient ≈595-650 MiB — see case file §2.2 for why the transient, not the configured cap, is the number that matters for this arithmetic), cgroup budget 2000 MiB, `-Xmx384M` — case file: [`row_cache_size+index_summary_capacity.md`](row_cache_size+index_summary_capacity.md). **Result: OOM NOT reached.** Both control arms stayed safe (R alone: 73.6% of budget, 26.4% free; I alone: 76.8% of budget, 23.2% free). The convergence arm's combined peak (90.1% of budget) came in well under the naive additive prediction (106.1%) and never crossed the budget (`memory.events`' `oom`/`oom_kill` stayed 0 throughout). Diagnosed as a timing effect: each constraint's own enforcement (Caffeine eviction for the row cache, periodic resize for the index summary) kept operating under combined load, so the two measured "worst moments" — each captured in isolation at that constraint's own worst instant — did not actually coincide when run together.

**Combinations considered and skipped (not built or run):**

- Two earlier sizing attempts within this run's own index-summary calibration (3,600,000 and 3,000,000 partitions at the same 2000 MiB budget, before the final 1,500,000-partition sizing was chosen) **did** genuinely OOM-kill the node — but during what was meant to be a safe "alone" control arm, with no comparison baseline to file a convergence case against, so these are cited in the filed case's §2.2/§3.2 by their `dmesg` timestamps rather than given their own case files. They are the direct evidence behind the final, smaller sizing, not discarded data.
- No other off-heap candidate pair (e.g. the networking-pool family `internode_application_*`/`native_transport_*` constraints, already flagged in `_constraint-groups.md` as likely-the-same-underlying-pool) was surveyed this run — the task specifically pointed at `row_cache_size`+`index_summary_capacity`, and one full combination (control arms + convergence arm, with a genuine design correction mid-flight) was enough to fill this run's time budget.

**Stopping reason:** one combination built, sized (with an explicit, stated arithmetic correction when the naive prediction based on isolated calibration turned out to overestimate the true concurrent peak), run through two control arms and a convergence arm, and filed as a complete case with raw `dmesg`/cgroup-event evidence for every OOM/no-OOM claim. The group is left **open** (not exhausted): the case file's own §4 identifies a concrete, specific retry (longer `index_summary_resize_interval` so the pre-resize transient has more time to grow before being trimmed, or fully-concurrent rather than sequential-then-concurrent preloads) that would more faithfully force both constraints' individual worst moments to coincide — this wasn't attempted this run given the time already spent on sizing corrections, but is a timing/workload-shape question, not a "does this group converge at all" question, so a future run picking it back up does not need to re-survey the group from scratch.

**Verification environment notes carried to the next run:** (1) `-XX:MaxDirectMemorySize` is not a safe default assumption for "the off-heap budget" — check each constraint's own allocation path (JNA/malloc vs. `DirectByteBuffer`) before picking a JVM-flag-based budget; a cgroup `memory.max` is the more general mechanism and was confirmed working here. (2) `memory.current`/`memory.max` alone are a **misleading "percent used" metric** once any sstable/commitlog I/O is involved — the cgroup counts reclaimable page cache toward `memory.current`, so it can sit pegged at `memory.max` for long stretches with zero real memory pressure; use `RssAnon` (from `/proc/<pid>/status`) for the "how full is the hard, non-reclaimable budget" reading, and `memory.events`' `oom`/`oom_kill` fields (not `memory.current`) as the only reliable OOM-or-not signal. (3) `bin/cassandra -f` never writes a pidfile (only the backgrounding branch of the script does) — detect the daemon's PID by `pgrep`, not a pidfile, when the harness must run the JVM in the foreground (needed here so `systemd-run --scope` tracks the right process). (4) A `systemd-run --user --scope` cgroup's path includes an undocumented `app.slice/` component (`.../user@<uid>.service/app.slice/<unit>.scope`). (5) `index_summary_resize_interval`'s first scheduled run fires on a delay from the **manager's own startup**, not from when a workload's data is loaded — a resize-wait must capture a log-line offset before the workload starts, or it can match an earlier, near-empty resize. (6) `cassandra-stress user profile=...` requires a `queries:` section in the yaml even when only `insert` ops are ever run (a hard `AssertionError` otherwise). (7) a too-small key size for a cassandra-stress table meant to stress `index_summary_capacity` can make the achievable raw summary size per partition far too small to reach a meaningful total within a feasible partition count — match if-check-exp's own ~200-byte-key calibration rather than using a small/realistic key.

## 2026-11-03 — run 5

**Node:** same node and build as runs 1-4 (`~/cassandra-run1`, unchanged). **Scope:** one combination, the off-heap retry named in run 4's §4. The 57 `if-check-exp` set-B cases (merged 2026-11-03) were checked for new standing-pool candidates; none added an off-heap one (they are new decision points on constraints already surveyed, and `paxos_cache_size` is on-heap, a group already exhausted). Disk stayed skipped.

**Correction (found in run 6):** the converge arm's burst wrote 0 partitions (the stress client's CREATE TABLE timed out), so this run's converge arm is void. See run 6.

**Combinations attempted:** 1. `row_cache_size` (550 MiB) + `index_summary_capacity` (100 MiB), cgroup 2000 MiB, `index_summary_resize_interval=30m`, burst and read pass concurrent. Case file: [`row_cache_size+index_summary_capacity--run5.md`](row_cache_size+index_summary_capacity--run5.md). **Result: OOM not reached; converge arm incomplete** (burst client timeouts, peak 1501 MiB vs 1608 / 1550 alone).

**Stopping reason:** one combination built and run through two control arms and a convergence arm. Group left **open** with two untried retries (larger client timeout / fewer threads; fill the row cache first, then burst).

**Notes for the next run:** (1) with the cgroup pinned at `memory.max`, reclaim throttling slows writes, so a concurrent burst can stall rather than grow memory; record partitions actually written, since the stress client prints no totals on timeout. (2) `oom-run.sh baseline` printed "process gone" for its idle sample (PID picked up before the daemon settled); arms are unaffected. (3) Do not call `nodetool stopdaemon` while the driver is running; check `pgrep -fa oom-run.sh` first.

## 2026-11-03 — run 6

**Node:** same node and build. **Scope:** the two retries named in run 5, on the same pair. Case file: [`row_cache_size+index_summary_capacity--run6.md`](row_cache_size+index_summary_capacity--run6.md).

**Combinations attempted (one pair, two workload schedules):**

1. **Schedule A**, concurrent burst (16 threads, 50 retries/op) and row read pass, `isc.t` pre-created: **not reached**, peak 1866 MiB (93%); both pools fully loaded at the end (row cache 550 MiB, index summaries 303 MiB). The burst finished in 1 m 42 s, long before the 26-minute row-cache fill, so the compaction transient did not coincide with a full cache.
2. **Schedule B**, row cache filled to its cap first, then the 64-thread burst: **OOMed**, kernel cgroup OOM-kill (`CompactionExecutor` allocation, anon-rss 1973 MiB) about 13 s after the burst finished, during `isc.t` flush/compaction. Alone: 78% / 80%.

**Harness defect found:** a `cassandra-stress user` client creating its own table under concurrent load can time out on `CREATE TABLE` and write nothing, and `-errors retries` does not cover schema creation. This voided `A_converge_slow` and, retroactively, run 5's converge arm. Fixed by creating the table with `cqlsh --request-timeout=120` on the idle node; check each burst's `tablestats` (partition count, "Index summary off heap memory used") instead of trusting the client.

3. **Schedule B with a 1-minute resize** (arm C, a follow-up check): **no off-heap kill**, peak 1859 MiB (93%), resize ran every minute through the burst. The JVM still died, of a Java heap `OutOfMemoryError` (old gen 349/384 MiB, full GCs freeing nothing), not attributed and not counted as a convergence OOM; heap dump kept on the node, unanalyzed. See the run 6 case file's addendum.

**Run 4 superseded:** run 4 used the reverse order (burst first, then cache fill) with a 1-minute resize; not worth re-running unchanged. Marked superseded in `_INDEX.md` and its case file.

**Stopping reason:** both named retries run, plus the 1-minute-resize check; the pair closed as OOMed. The group stays open only for untried candidates.

## 2026-11-03 — run 7

**Node:** same node and build. **Shared budget:** off-heap/direct memory, cgroup v2 `memory.max`. On-heap exhausted, disk skipped; the first off-heap pair closed in run 6.

**Combinations attempted:** 1. `memtable_offheap_space` (1200 MiB, `offheap_objects`, cleanup threshold 0.99) + `file_cache_size` (1200 MiB, chunk cache enabled), 3500 MiB budget, `-Xmx768M`. Case file: [`memtable_offheap_space+file_cache_size.md`](memtable_offheap_space+file_cache_size.md). **OOMed:** alone 77.6% / 77.7%; converge (cache filled, then write burst) kernel-killed 16 s into the burst, anon-rss 3465 MiB.

**Considered and not picked:** the networking `BufferPool` family (`networking_cache_size`, `internode_application_*`, `native_transport_*` queue capacities). It fills only while messages are in flight, so it has no sustained window at capacity; `_constraint-groups.md` also flags those as likely one shared pool.

**Calibration note:** at 600 MiB per pool (8000 MiB budget) about 250 MiB of load-driven growth appears in each alone arm but once in the combined arm, and the ~1300 MiB idle (768 MiB pre-touched heap) left no workable budget; doubling both pools fixed the ratio. Calibration arms are kept in the case folder.

**Stopping reason:** one new pair sized, run through two matched control arms and a convergence arm, OOMed on the first try. Remaining off-heap candidates are few (`DOB_MAX_RECYCLE_BYTES`, `MAX_HINT_BUFFERS` / hints buffers, trie-memtable limits that follow `memtable_offheap_space`); a next run should check whether any is an independent standing pool before picking.

## 2026-11-03 — run 8

**Node:** same node and build (`pc41`, `~/cassandra-run1`). **Shared budget:** off-heap/direct memory, this time the JVM's own `-XX:MaxDirectMemorySize` (both pools are `java.nio.DirectByteBuffer`s through `Bits.reserveMemory`; checked from source and confirmed by the OOM). On-heap exhausted, disk skipped. Second loopback node used again (hints need a down replica), but killed before any reading, so run 3's two-JVM contention cannot arise.

**Candidates checked:** the three named by run 7. `DOB_MAX_RECYCLE_BYTES`: standing (each thread keeps a scratch buffer of up to L between uses; `allocateDirect`). `MAX_HINT_BUFFERS`: standing (slabs recycled, never freed; `allocateDirect`); the stage-4 natural-load control already reached its cap without a Byteman hold, and calibration here reached 9 slabs at n = 12. The hints-slab case is the same pool as `MAX_HINT_BUFFERS`; the trie limits follow `memtable_offheap_space` (not independent).

**Combinations attempted:** 1. `DOB_MAX_RECYCLE_BYTES` (L = 8 MiB, 4 MB writes on 8 client threads) + `MAX_HINT_BUFFERS` (n = 8, 32 MiB slabs, 1 KiB writes to a down replica), 560 MiB `MaxDirectMemorySize`, `-Xmx3072M`. Case file: [`DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS.md`](DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS.md). **OOMed:** alone 50.4% / 69.5%; converge (hints pool at its cap, then the DOB burst) hit `OutOfMemoryError: Direct buffer memory` in scratch-buffer growth about 7 s into the burst; Cassandra forced a heap OOM (heap 570 of 3072 MiB) and `OnOutOfMemoryError` killed the JVM. **Attribution control:** the same converge arm with only `dob_max_recycle_bytes` at its 1 MiB default stayed at 51%, no OOM.

**Harness defect found:** `cassandra-stress write` always sends `CREATE KEYSPACE` first; under the other workload's load it timed out and the client wrote nothing. This voided two converge attempts (one per order). Fixed with `cassandra-stress user` profiles that have no schema definitions; both controls re-run with them. Any future concurrent-workload harness should use such profiles, not just pre-create the table (run 6's fix covered `CREATE TABLE`, not this).

**Calibration note:** 14 MiB blobs with L = 32 MiB kept 1206 MiB (about 43 threads), far more than the hints pool; 4 MB blobs with L = 8 MiB kept about 337 MiB (about 44 threads). *T*, the number of threads that keep a buffer, is set by how many shared-pool workers the burst touches, not by the client's 8 threads; budget for about 44.

**Stopping reason:** one new pair sized, run through two matched controls, a convergence arm and an attribution control; OOMed. The off-heap group is marked **exhausted**: no independent untried standing pool is left (see the status table).

**Notes for the next run:** (1) `MaxDirectMemorySize` appears twice on the command line (`cassandra-env.sh` computes one first); the last one wins. (2) The JDK 11 direct-OOM message carries no byte counts; read the limit from the arm's flags and the trajectory from the `BufferPool` MXBean. (3) Client totals after a node death are not writes (cassandra-stress counts `NoHostAvailable` failures as done); use server-side `tablestats`. (4) The node keeps the heap dump (687 MB) in `~/oom-direct-run8/logs/converge/`.

