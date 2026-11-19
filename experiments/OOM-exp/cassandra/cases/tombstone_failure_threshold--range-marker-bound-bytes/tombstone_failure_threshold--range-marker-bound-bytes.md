# B16 — tombstone_failure_threshold (count) and the replica response buffer: range-marker bound bytes uncounted  <!-- file: cassandra/cases/tombstone_failure_threshold--range-marker-bound-bytes/tombstone_failure_threshold--range-marker-bound-bytes.md -->

| Field | Value |
|---|---|
| Case ID | `B16` (B = bypass; README "ID prefixes") |
| From | cluster `OC-282` (primary), `OC-158`, `OC-161`, `OC-162`, `OC-295`, `OC-48` of the phase 1 OOM candidate list (all `picked: B16`) |
| Phase-1 case files | [`tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous.md) (OC-282, OC-295); [`tombstone_failure_threshold-countTombstone-tombstones--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/tombstone_failure_threshold-countTombstone-tombstones--autonomous.md) (OC-158, OC-161, OC-162, OC-48) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9); build to be copied from `ms0617:/mydata/s4/cassandra-base` (jar sha256 `e55f4f29…3b5a942`, conf files identical to the pinned source, checked 2026-11-18 13:50 EST) |
| Stage 1 (design) | phase-2 OOM agent, stage 1 session, wave 4, 2026-11-18 13:40–14:20 EST; nothing run (read-only node checks only) |
| Stage 2 (verify) | phase-2 OOM agent, stage 2 session (fresh session), wave 4, 2026-11-18 13:57–15:35 EST, ms0611 (aarch64); 23 lifetimes plus LOAD |
| Verdict | **`true positive`** — `verified-OOM · deployment`, bypass, attributed (§4) |

## Summary

- **Conclusion:** true positive, `verified-OOM · deployment`. At shipped defaults one `SELECT` of a partition of
  99,998 range-tombstone markers with 12,000-byte bounds (0 live rows, under the 100,000 threshold) kills a 2 GiB-heap
  node with `OutOfMemoryError: Java heap space` on the first read, 3/3; the same markers with 1,000-byte bounds survive
  0/3. The endpoint holds at every heap `cassandra-env.sh` resolves, up to 31,744 MiB (ms0611's own default) with 6
  concurrent reads, 3/3. Single node, RF 1, aarch64.
- **Root cause:** `tombstone_failure_threshold`, the only read guard on by default, counts markers, not bytes, and
  each marker carries its clustering bound, so the replica's on-heap response `DataOutputBuffer`
  (`LocalDataResponse.build`) grows to ≈ 1.6 GiB for one read. The byte guard that could stop it ships off, and when
  switched on it is blind to these bytes: a marker's `unsharedHeapSize()` leaves out its bound (`LocalReadSize`
  4.87 MB for a 1.1–1.6 GiB response; counting the bound makes it abort every such read, 0/3 OOM). Read timeouts free
  the client but not the marker scan, so at large heaps more scans run than the client has reads in flight.
- **Hypothesis (stage 1):** at shipped defaults the only read guard that is on, `tombstone_failure_threshold`
  (100,000, documented in `cassandra.yaml` as the guard against tombstones exhausting the heap), counts markers, not
  bytes; each range-tombstone marker carries its clustering bound (up to 65,535 B), and the replica serializes every
  scanned marker into one on-heap `DataOutputBuffer` for its response. A partition of 49,999 range deletions with
  12,000-byte bounds (99,998 markers, just under the threshold, 0 live rows) makes **one** `SELECT` build a ≈ 1.15 GiB
  response that needs a ≈ 1.6 GiB growth step, so a 2 GiB heap dies on a single read; nothing sums concurrent reads at
  larger heaps. Two stage-1 source findings make it a bypass rather than a sizing issue: the byte tracker that is off
  by default (`local_read_size_fail_threshold`) would not see these bytes even when switched on, because a marker's
  `unsharedHeapSize()` leaves out its bound; and the read timeout cannot stop a marker-only scan, because the
  cancellation check runs per row and per partition, never per marker.

## 1. Candidate

**Cluster rows (quoted from `phase1-oom-candidates.md`; the full text of the wave rows is quoted from `runs/wave1.md`
and `runs/wave2.md`).**

> | OC-282 | 2026-11-18 | `tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous` | autonomous | The threshold counts tombstones, not bytes. Each counted tombstone (a row deletion or a range-tombstone bound) can carry a clustering of up to 65535 B. [details](runs/wave2.md#oc-282) | — | picked: B16 |
>
> Details (`runs/wave2.md#oc-282`): "The threshold counts tombstones, not bytes. Each counted tombstone (a row deletion or a range-tombstone bound) can carry a clustering of up to 65535 B. Up to 100,000 of them are serialized into the replica's heap DataOutputBuffer for the read response before the abort fires. At defaults no byte limit applies: read_thresholds_enabled is false and the local/coordinator read-size thresholds are null. Paging counts only live rows, not tombstones. Stage 4 measured 145 MiB per read with 1000-character clusterings. With about 64 KiB clusterings the buffer reaches the 2 GiB array limit, about 3.3 GB at the peak with the 1.5x growth copy, in a single read. Even at 1 KB keys, concurrent_reads 32 gives about 4.6 GB. **Where:** db/ReadCommand.java:588-601 (count-only check), :461; db/ReadResponse.java:197-201 (whole response in DataOutputBuffer); config/Config.java:526-535; io/util/DataOutputBuffer.java:158-171; config/Config.java:179"

> | OC-158 | 2026-11-17 | `tombstone_failure_threshold-countTombstone-tombstones--autonomous` | autonomous | Holder: the replica's on-heap response DataOutputBuffer (and the coordinator's copies of the RF responses), one per concurrent data read. [details](runs/wave1.md#oc-158) | — | picked: B16 |
>
> Details (`runs/wave1.md#oc-158`): "Holder: the replica's on-heap response DataOutputBuffer (and the coordinator's copies of the RF responses), one per concurrent data read. Why nothing stops it: the threshold counts tombstones, not bytes, so tombstone size (clustering size) is unbounded. It applies per read command, not per node. The byte-based local_read_size_fail_threshold is off by default (read_thresholds_enabled=false). Each growth step copies the buffer (old and new live together, x2 below 64 MiB, then x1.5). Rough size at defaults: T=100,000 x 1 KB tombstones is about 100 MB, peaking at 144-216 MiB per read (stage 4). With concurrent_reads=32 that is about 4.6-7 GB live, while stage 4 saw 4-6 GB of old generation filled with humongous buffers by 8 readers. With 64 KiB clusterings a single read can reach the about 2 GB array cap, about 3 GB with the copy. **Where:** src/java/org/apache/cassandra/db/ReadCommand.java:591; src/java/org/apache/cassandra/db/ReadResponse.java:199-201; src/java/org/apache/cassandra/io/util/DataOutputBuffer.java:158-181; src/java/org/apache/cassandra/config/Config.java:179,526,535"

> | OC-161 | 2026-11-17 | `tombstone_failure_threshold-countTombstone-tombstones--autonomous` | guided | Holder: the replica's on-heap response buffer (DataOutputBuffer in LocalDataResponse.build), one per executing read command. [details](runs/wave1.md#oc-161) | CP-2, CP-7, CP-12, CP-8 | picked: B16 |
>
> Details (`runs/wave1.md#oc-161`): "Holder: the replica's on-heap response buffer (DataOutputBuffer in LocalDataResponse.build), one per executing read command. Why nothing stops it: tombstone_failure_threshold counts tombstones, not bytes. One tombstone's size is bounded only by its clustering values (up to 64 KiB per component). The count is per command and per replica, and nothing sums it across the 32 concurrent ReadStage threads (concurrent_reads). The only byte guard, local_read_size_fail_threshold, is off by default (read_thresholds_enabled=false). The buffer grows by 2x up to 64 MiB and by 1.5x beyond, with a full copy each time, so old and new arrays are live together. Rough size at defaults: T = 100,000 x about 1 KB tombstones is about 144 MiB per read (measured in stage 4), so 32 concurrent reads hold about 4.5 GiB, up to about 7.5 GiB during growth copies, against an 8 GiB heap that also holds memtables (heap/4). Stage 4 saw the old generation reach about 6 GB with only 8 concurrent readers. **Where:** src/java/org/apache/cassandra/db/ReadCommand.java:590-602 (countTombstone, item count); src/java/org/apache/cassandra/db/ReadResponse.java:197-201 (new DataOutputBuffer per response); src/java/org/apache/cassandra/io/util/DataOutputBuffer.java:158-182 (growth copy); src/java/org/apache/cassandra/config/Config.java:179 (concurrent_reads = 32), :526 (read_thresholds_enabled = false)"

> | OC-162 | 2026-11-17 | `tombstone_failure_threshold-countTombstone-tombstones--autonomous` | guided | Holder: the coordinator, which keeps each replica's serialized data response (RemoteDataResponse ByteBuffer) until all expected responses arrive and are merged. [details](runs/wave1.md#oc-162) | CP-7, CP-2, CP-12 | picked: B16 |
>
> Details (`runs/wave1.md#oc-162`): "Holder: the coordinator, which keeps each replica's serialized data response (RemoteDataResponse ByteBuffer) until all expected responses arrive and are merged. Why nothing stops it: the tombstone cap acts on each replica separately. The coordinator's in-flight request limit counts request bytes, not responses. Concurrent reads per coordinator are bounded only by native_transport_max_threads (128), not by any byte limit. A digest mismatch at QUORUM fetches full data from every contacted replica. A remote response can be up to internode_max_message_size (128 MiB by default) and a local one is unbounded. Rough size at defaults: 128 concurrent tombstone-heavy reads x 1-2 responses x up to 128 MiB is many GiB, far above an 8 GiB heap. Even 16 such reads with about 144 MiB responses is about 2.3 GiB. This is plausible from the source only; stage 4 did not measure the coordinator. **Where:** src/java/org/apache/cassandra/db/ReadResponse.java:213-221 (RemoteDataResponse holds the ByteBuffer); src/java/org/apache/cassandra/config/Config.java:283 (native_transport_max_threads = 128); src/java/org/apache/cassandra/config/DatabaseDescriptor.java:990-995 (default internode_max_message_size = 128 MiB)"

> | OC-295 | 2026-11-18 | `tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous` | guided | Holder: the replica's per-read heap DataOutputBuffer response (ReadResponse.LocalDataResponse.build) plus the scan's allocation. [details](runs/wave2.md#oc-295) | CP-2, CP-1, CP-7, CP-8, CP-12 | picked: B16 |
>
> Details (`runs/wave2.md#oc-295`): "Holder: the replica's per-read heap DataOutputBuffer response (ReadResponse.LocalDataResponse.build) plus the scan's allocation. Why nothing stops it: tombstone_failure_threshold counts tombstones (100,000), not bytes, and each range-tombstone marker carries clustering bounds of up to 65535 B. The byte guard on the same reads (local_read_size_*) ships off (read_thresholds_enabled=false, Config.java:526-530). The budget is per read command, with up to concurrent_reads=32 at once and no node-wide total. Rough size: stage 4 measured a 145 MiB buffer for 100,000 markers with 1 KB clusterings at the default threshold, and about 600 B of scan allocation per counted tombstone. With multi-KB to 64 KiB clusterings one read reaches GBs. 32 concurrent reads at 145 MiB are already about 4.6 GiB, beyond an 8 GiB heap's free share. Stage 4 saw eight clients hold about 1.3 GB of a 2 GiB heap. **Where:** src/java/org/apache/cassandra/db/ReadCommand.java:529-537, :582-601; src/java/org/apache/cassandra/db/ReadResponse.java:197-203; src/java/org/apache/cassandra/config/Config.java:179, :526-530, :535"

> | OC-48 | 2026-11-17 | `tombstone_failure_threshold-countTombstone-tombstones--autonomous` | legacy | [lead list ×2 (blind, E3/E1): `tombstone_failure_threshold-countTombstone-tombstones`, `tombstone-failure-threshold-withMetricsRecording-failureThreshold`; N17 cluster; queued as U4] The tombstone failure threshold (100,000, documented as heap protection) counts tombstones per read, not bytes: 100k range markers with 1 KB clusterings make a ≈ 145 MiB response buffer per read (stage 4), × 32 concurrent reads ≈ 4.6 GiB live on one replica, with `local_read_size_*` off. | CP-2 | picked: B16 |

**Triage (runs/triage-2026-11-18.md, rank 4 of the top 20):** "tombstone_failure_threshold counts tombstones, not
bytes, and paging counts only live rows. A single read of a partition holding about 10k range tombstones with bounds
near 64 KiB serializes about 1.3 GB into one replica heap DataOutputBuffer, about 2 GB at the growth copy, well under
the 100k abort. Stage 4 already measured 145 MiB per read with 1 KB clusterings, so one or two reads at a 2 GiB heap is
a short test." Overlaps: "Same holder as U4 (replica response buffer), but tombstones bypass the page row limit that
U4 relies on. Duplicates the legacy OC-48 (open, 1 KB keys) and OC-158, OC-161, OC-162 and OC-295." Notes §1:
"Tombstone-count reads: OC-158, 161, 162, 282, 295, plus the legacy OC-48"; §5 lists OC-282 among the likely fastest
first wins.

**The cluster's shared mechanism, and what this design covers.** All six rows name one holder (the serialized data
response of one read command, on the heap) and one gap: the guard that is on at defaults counts tombstones, the guard
that counts bytes is off, and nothing sums concurrent reads. The design tests that mechanism on one node with
range-tombstone markers:

| Row | Covered by | Not covered |
|---|---|---|
| OC-282 (primary) | the test arm: one read of 99,998 markers with 12,000 B bounds (≈ 1.15 GiB response) at 2 GiB; the budget search adds concurrency | row-deletion tombstones (they differ: a row is checked by the read-timeout cancellation and its clustering is counted by the local read-size tracker, see the mechanism); bounds near 64 KiB and the 2 GiB array cap (12 KB bounds keep the write-side BIG row-index buffer, OC-277's mechanism, out of the run) |
| OC-158 | the replica buffer, one per concurrent read (budget search; CAL-M sweep) | the coordinator's copies of RF remote responses (single node, RF 1) |
| OC-161 | the replica buffer per executing read command, growth copies, no sum across concurrent reads | — |
| OC-162 | — (its holder is the coordinator's `RemoteDataResponse` of other replicas; on one node the coordinator holds only the local response, the same buffer as above) | the whole row: needs ≥ 2 replicas and a digest mismatch at QUORUM; left `picked: B16` for the owner to decide (not run) |
| OC-295 | range markers, read thresholds off, per-read buffer plus scan allocation (GC log), concurrency | the "≈ 600 B scan allocation per tombstone" is recorded only as GC activity, not attributed |
| OC-48 | its exact shape (99,998 markers with 1,000 B bounds) is the matched control `M` table; its concurrency claim is the `CAL-M-2G` sweep (one run, lower priority) | 32 concurrent reads at an 8 GiB heap (not planned) |

**Phase-1 constraint and check.** `tombstone_failure_threshold` (`Config.java:535`, default 100,000;
`cassandra.yaml:1814-1815`), enforced per read command in `ReadCommand.withMetricsRecording` (`ReadCommand.java:525`):
`applyToMarker` calls `countTombstone(marker.clustering())` once per marker (`:582-585`), and
`countTombstone` throws `TombstoneOverwhelmingException` when `++tombstones > failureThreshold` (`:588-601`). Unit:
markers / dead cells / row deletions, not bytes. The yaml documents it as heap protection: "we need to keep the
tombstones seen in memory so we can return them to the coordinator … this can cause performance problems and even
exaust the server heap" (`cassandra.yaml:1805-1809`). Both phase-1 case files estimate `positive` per read ("bounded
by about (T+1) × the serialized size of one tombstone … The cap counts tombstones, not bytes … per read command, not
the whole node").

**Phase-1 stage 4.**
- [`tombstone_failure_threshold-countTombstone-tombstones--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/tombstone_failure_threshold-countTombstone-tombstones--autonomous.md)
  (pc13, 2026-10-21; one node, 8 GiB heap, 200,000 tombstones of ≈ 1 KB): unit **Confirmed** (aborts at exactly T+1;
  per-read buffer 1.0 / 32 / 144 MiB at T = 1k / 20k / 100k, 216 MiB uncapped); cluster **Not confirmed (partial)**: 8
  concurrent readers filled 4–6 GB of old generation with humongous garbage at T ≥ 20k, no OOM; "the heap held by the
  reads at any instant was not measured".
- [`tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous.md)
  (pc07, 2026-10-26; 2 GiB heap): unit **Confirmed** (caps per read); cluster **Not confirmed (partial)**: row
  tombstones with `int` clusterings serialize to 11.7 B each, so the default threshold bounds that response at
  ≈ 1.4 MB; the **size variant** (120,000 range markers with 1000-character clusterings) gave a **144.7 MiB** buffer at
  T = 100,000 (1,517 B per marker, 72–129 × the row tombstone); "the cap bounds the count, not the bytes"; 8 clients at
  T = 100,000 drove a 2 GiB heap to ≈ 1.3 GB, no OOM. Finding 4: "Reads of a tombstone-only partition do not fill a
  page, so cqlsh's 100-row paging does not limit the scan."
- Neither run tested an OOM, a held-heap reading under concurrency, or bounds above 1 KB.

**Stage-1 source findings (pinned source, checked 2026-11-18; they shape the design and the arms E-RT and I2).**
1. *The byte tracker would miss marker bounds even when enabled.* `withQuerySizeTracking` (`ReadCommand.java:663-739`;
   active only when `read_thresholds_enabled: true` and a `local_read_size_*` threshold is set, `:656-661`) adds
   `marker.unsharedHeapSize()` per marker (`:699-702`), and `RangeTombstoneBoundMarker.unsharedHeapSize()` is
   `EMPTY_SIZE + deletion.unsharedHeapSize()` (`db/rows/RangeTombstoneBoundMarker.java:164-167`; boundary marker the
   same with two deletion times, `RangeTombstoneBoundaryMarker.java:197-200`): **the bound's clustering values are not
   counted**. A row is counted with its clustering (`BTreeRow.java:532-541`). So for markers the tracker's K is about
   48 B per marker regardless of bound size (estimate; to be measured in `IC`).
2. *The read timeout cannot cancel a marker-only scan.* `QueryCancellationChecker` (`ReadCommand.java:743-795`) checks
   `isAborted()` only in `applyToPartition` and `applyToRow` (`:771-775`); it has no `applyToMarker`. On a partition
   of markers it checks once, at the partition start. `LocalReadRunnable` then completes the command
   (`StorageProxy.java:2228`, `MonitorableImpl.complete()` does not re-check the deadline) and the coordinator,
   already signalled, returns the result (`ReadCallback.java:130`). A row-deletion scan, by contrast, is cancelled at
   `read_request_timeout` (5 s). On a slow (ARM) node this means the buffer reaches its full size however long the
   scan takes.
3. *Paging does not bound it.* The row counter counts live rows only; a partition of markers never fills a page
   (stage-4 finding 4; `DataLimits` counter), so the driver's default 5,000-row page reads the whole partition in one
   command.
4. *Single node path.* The local read runs inline on the request thread when a READ permit is free
   (`AbstractReadExecutor.java:165` → `SEPExecutor.java:218`), serializes the whole partition into
   `new DataOutputBuffer()` (`ReadResponse.java:197-201`; heap `ByteBuffer.allocate`, growth ×2 up to 64 MiB, ×1.5
   above, old and new arrays live during the copy, `DataOutputBuffer.java:158-182`; capacity saturates at
   `Integer.MAX_VALUE − 8`, `:114-127`), and the coordinator deserializes it and drops every marker (0 rows to the client).

**JIRA prior art (read only; nothing posted).** Survey
[`jira-oom-survey.csv`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv):
CASSANDRA-6117 (*Avoid death-by-tombstone by default*, the origin of the threshold; 5143 *Safety valve on number of
tombstones skipped on read path to prevent a full heap*, Duplicate of it) — the threshold was introduced as a heap
safety valve and is a count by design; 12707 (*JVM out of memory when querying an extra-large partition with lots of
tombstones*, Open, 2.x `gatherTombstones`; comment: 3.0+ not affected); 9205 (*replicas keep scanning tombstones and
OOM after the client has timed out*, Duplicate of 2848; the survey notes later read monitoring "narrows this path" —
finding 2 says it does not for markers); 8559 (OOM building a tombstone warning message, Fixed 2.0.15/2.1.5; the
5.0.9 message is capped at 512 query characters, `ReadCommand.java:629`); 18424 (*graceful paging across tombstones*,
Open, 7.x); 21492 (*RangeTombstoneList.copy() O(N²) on memtable merges*, Triage Needed, write side); 16850 / 16896
(read thresholds, Fixed 4.1, off by default; U4's survey); 11745 (byte paging, 6.0-alpha3, live rows, opt-in).
JIRA REST searched 2026-11-18 13:45–13:52 EST: `text ~ "unsharedHeapSize" AND text ~ "RangeTombstone"` (0 hits);
`text ~ "local_read_size" AND text ~ "tombstone"` (112, none on marker accounting); `text ~ "tombstone_failure_threshold"
AND (text ~ OOM OR text ~ OutOfMemoryError) AND (text ~ "large clustering" OR text ~ "clustering key" OR text ~ "bytes")`
(8, none on this shape); `summary ~ tombstone AND (summary ~ size OR bytes OR memory OR heap)` (5: 5143, 16310, 12367,
8603, 12707); `text ~ "QueryCancellationChecker"` (5: 20135, 21710, 21468, 18282, 21360; none on markers);
`text ~ "range tombstone" AND text ~ timeout AND (cancel OR abort) AND created >= 2019-01-01` (6, none relevant);
`text ~ "tombstone_failure_threshold" AND text ~ "range tombstone" AND created >= 2020-01-01` (16, none on bytes).
**Verdict: `new`** for the byte size of counted markers reaching OOM at defaults, for the marker bound left out of
`local_read_size` accounting, and for marker scans escaping the timeout cancellation; **by design** that the
threshold is a count (6117). Not known-fixed, so not a positive control.

**Overlap with filed and in-flight cases.** U4 (verified-OOM, same replica `DataOutputBuffer` holder) needed wide
**live** rows and relied on the driver's 5,000-row page; here the page never fills and the client gets 0 rows, so the
coordinator `ResultSet` holder of U4 is absent and the only holder is the replica buffer. C2 (Netty direct, slow
readers) does not apply (0-row responses). OC-277 (`big-row-index-buffer--64KiB-clustering-wide-partition`, another
wave-4 folder) is the write-side BIG row-index buffer for huge clusterings; this design keeps it out of the measured
lifetimes (load at an 8 GiB heap; reads do not build the index). OC-206/21492 (`range-tombstone-list--…`, another wave-4
folder) is the memtable copy cost on write; it affects only the load phase here.

## 2. Design solution (stage 1; frozen)

**Mechanism.** Direction: **bypass** — a count control whose per-item footprint is unbounded (protocol: U > C, K ≤ C,
"accounting omission/mismatch"; count-based controls are eligible when the item footprint is measured), with the byte
control that could cover it **off** at defaults (unprotected configuration) and, per source finding 1, blind to marker
bounds when on. Technique notes: [`bypass-playbook.md`](../../../bypass-playbook.md) (protected vs suspect payload,
counter vs real bytes) and [`default-convergence-playbook.md`](../../../default-convergence-playbook.md) (multiplicity
sweep at default capacities, for the budget search). A `SELECT * FROM b16.t WHERE pk = 0` on a partition holding
99,998 range-tombstone markers and no live rows passes the row counter (never fills a page) and the tombstone
threshold (99,998 ≤ 100,000, `ReadCommand.java:588-601`); the request thread serializes every marker, bound included
(≈ s + 13 B each, estimate), into one heap `DataOutputBuffer` (`ReadResponse.java:197-201`). With s = 12,000 B the
response is ≈ 1.20 GB; its last growth step holds the old and new arrays together. The read-timeout cancellation does
not fire on markers (finding 2) and no byte guard runs (read thresholds off; finding 1 if on). Nothing sums concurrent
reads (READ permits 32, request threads 128).

**Protection map** (fixed before any run).

| Domain | Holder (allocation → release) | Counter K | Limit at default | At the limit |
|---|---|---|---|---|
| Tombstone threshold (claimed control) | replica response `DataOutputBuffer` (`ReadResponse.java:199`) → released when the coordinator has iterated the response and the request completes | markers counted per read command (`tombstones`, `ReadCommand.java:589`); JMX `TombstoneScannedHistogram` | 100,000 per command (`Config.java:535`) | `TombstoneOverwhelmingException`, read fails (`READ_TOO_MANY_TOMBSTONES`); no byte bound |
| Local read-size tracker | same holder | Σ `unsharedHeapSize()` per row/marker (`ReadCommand.java:692-702`); markers exclude the bound (finding 1); JMX `LocalReadSize` | **off** (`read_thresholds_enabled: false`, `Config.java:526`; thresholds null, `:529-530`) | nothing at defaults (unprotected configuration); when on: `LocalReadSizeTooLargeException` at the threshold of *counted* bytes |
| Read timeout | the scan itself | elapsed time | `read_request_timeout` 5 s (`Config.java:145`) | `QueryCancelledException` per row/partition; **not checked per marker** (finding 2) |
| Row limit / page | — | live rows | driver page 5,000 | never reached (0 live rows) |
| Concurrency | one buffer per in-flight read | READ permits; request threads | `concurrent_reads` 32 (`Config.java:179`); `native_transport_max_threads` 128 (`:283`) | queueing; no byte sum |
| Native in-flight request bytes | the small SELECT | request bytes | heap/10, per IP heap/40 | does not cover responses |
| Scan garbage (ledger, not claimed) | per-marker bound copies from the sstable, `IndexInfo` reads (BIG, 2 bounds per 64 KiB block), coordinator deserialization copies | — | none | transient; GC |
| Baseline | memtables (read-only lifetimes: empty), key cache (min(5 % H, 100 MiB)), chunk cache (direct) | own counters | defaults | evict / flush |

**Configuration and budget audit.**
- **Node:** `ms0611` (Utah m400, **aarch64**, 8 cores, 62 GiB = 64,249 MiB per `free -m`, 8 GiB swap, cgroup v2 with
  user `memory` delegation, `/mydata` 35 GiB free; JDK 11.0.33 `java-11-openjdk-arm64` with `jcmd`, `jfr`, `jar`,
  `javac`; Ant 1.10.12; no Java process, load 0.00 — checked read-only 2026-11-18 13:42 EST). The node clock is MST
  (EST − 2 h). `/mydata/s2r2/` and `/mydata/u1r2/` belong to other cases: **do not touch**. Record `aarch64`; no
  matched arm runs on another node.
- **Build:** no Cassandra on ms0611 now. Copy ms0617's build through the local node (ms0611 cannot ssh to ms0617):
  `ssh ms0617 'tar -C /mydata/s4 -cf - cassandra-base' | ssh ms0611 'tar -C /mydata/s4 -xf -'`, then check
  `sha256sum /mydata/s4/cassandra-base/build/apache-cassandra-5.0.9-SNAPSHOT.jar` =
  `e55f4f2974cb6120712a5cdfbbed9ee1ba25d97b887cbe71b64fd194f3b5a942`. Fallback if the copy fails: copy the pinned
  source (`copy-source.sh` or rsync of `systems/cassandra/source/`) to `/mydata/s4/cassandra-base` and `ant jar`
  (JDK 11, never in a tree a node runs from). Work root `ROOT=/mydata/s4/b16`; `cp -a /mydata/s4/cassandra-base
  $ROOT/tree`; pristine conf `$ROOT/conf-pristine`.
- **Every capacity constraint at its shipped default (V6)** in arms `A`: `tombstone_failure_threshold` 100,000,
  `tombstone_warn_threshold` 1,000, `read_thresholds_enabled` false (local/coordinator/row-index thresholds null),
  `concurrent_reads` 32, `native_transport_max_threads` 128, `read_request_timeout` 5 s, `native_transport_timeout`
  12 s, memtable/caches default, `column_index_size` unset (64 KiB for BIG), `column_index_cache_size` 2 KiB, sstable
  format `big`, `num_tokens` 16, guardrails default. Constraints differ only in arms `I`, `R` (E-RT, IC) and `I2`.
- **`cassandra.yaml` diff (environment only):** `data_file_directories`, `commitlog_directory`, `hints_directory`,
  `saved_caches_directory`, `cdc_raw_directory` under `$ROOT/node/` (U4's `sed` list). Addresses stay `localhost`.
- **Budgets (V7; standing rule: heap/direct ≥ 512 MiB meet V7, 2 GiB ideal; search upward):**
  - `cassandra-env.sh` on ms0611 with G1 (`USING_CMS` ≠ 0 → `heap_limit` 31,744): ½ RAM = 32,124 MiB > 31,744 →
    **auto heap 31,744 MiB, direct 15,872 MiB** (`cassandra-env.sh:53-67`). With a hand-set heap and
    `MAX_DIRECT_MEMORY_SIZE` unset the direct limit stays **15,872M**; this design leaves direct on "auto" in every arm
    (the claimed holder is heap; 0-row responses use almost no direct memory) and records `-Xmx` and
    `-XX:MaxDirectMemorySize` from `ps`.
  - **Primary: heap 2 GiB** (`MAX_HEAP_SIZE=2G`) — what `cassandra-env.sh` resolves on a 4 GiB node and the ideal
    budget; G1 with the shipped `jvm11-server.options` (16 MiB regions, `G1NewSizePercent=50`, `MaxGCPauseMillis=300`),
    `AlwaysPreTouch`, `HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError=kill -9 %p` (shipped).
  - **Upward search** (node classes `cassandra-env.sh` resolves): 4G (8 GiB node), 8G (16 GiB node), 16384M (32 GiB
    node), 31744M (ms0611 itself, the largest default heap).
  - **No container budget.** Each process runs in `systemd-run --user --scope -p MemoryMax=<heap + 15872M + 8G>
    -p MemorySwapMax=0` for isolation only (31744M: MemoryMax 56 GiB). A scope `oom_kill` makes a lifetime
    **invalid**; record `memory.events` at the end of each lifetime.
  - **Heap dumps** (disk is 35 GiB): on for 2G and 4G lifetimes (dump in the run directory; after the lifetime run
    `hprofhist.py` and `hprofstacks.py`, keep the summaries, then delete the hprof and keep its `ls -l` line); **off**
    for 8G and above (append `-XX:-HeapDumpOnOutOfMemoryError` to `JVM_EXTRA_OPTS` and check on the `ps` line that it
    comes after the shipped `+HeapDumpOnOutOfMemoryError`). Before each lifetime require `/mydata` free ≥ heap + 6 GiB
    (dump on) or ≥ 6 GiB (dump off).

**Ceiling arithmetic.**
- *Per marker* (intra-node serialization: flags, kind, component count, vint length + value, deletion time deltas):
  ≈ s + 13 B (estimate; IC measures it). Table `t`: s = 12,000 B, 99,998 markers → R_t ≈ 1.201 GB = **1,146 MiB**.
  Table `m`: s = 1,000 B → R_m ≈ 101 MB = 97 MiB (stage 4: 144.7 MiB capacity for 1000-character markers).
- *Buffer growth* (`DataOutputBuffer.java:158-171`: new = max(2 × cap or 1.5 × cap above 64 MiB, cap + bytes
  pending)); the first 12,000-byte value breaks the power-of-two chain, so for `t` the capacities run ≈ … 48 →
  96 → 144 → 215 → 323 → 485 → 727 → 1,091 → **1,636 MiB** (estimate). R_t > 1,091 MiB, so the last step needs a
  1,636 MiB array while the 1,091 MiB array is live: **≈ 2,727 MiB transient (2.27 × R), ≥ 1.67 × R in any chain.**
  In 16 MiB G1 regions: 69 + 103 = 172 regions; a 2 GiB heap has 128. For `m`: final ≈ 118–145 MiB, transient
  ≈ 200–240 MiB.
- *Per in-flight `t` read:* held after growth ≈ 1.6 GiB, peak ≈ 2.7 GiB; baseline at 2 GiB (read-only) ≈ 0.15–0.3 GiB;
  scan garbage ≈ 1.6 GB per read (bound copies + `IndexInfo`), collectable.
- *Σ contract capacities:* unbounded in bytes (99,998 markers × up to 65,535 B per bound ≈ 6.5 GB per command, capped
  by the array limit at ≈ 2 GiB, × 32 permits). Implicit ceiling ≈ 32 × 2.7 GiB ≈ 86 GiB.
- *Predicted smallest failing concurrency c_fail* (G1 humongous regions are not compacted in JDK 11; young minimum 50 %
  can lower it): **2G → 1** (certain by region count); 4G → 2 (band 1–2); 8G → 3 (2–4); 16384M → 5 (4–8);
  31744M → 9 (7–16). `m` at 2G (OC-48 shape): c_fail ≈ 8 (6–12).
- *Write side (load lifetime only):* BIG row index with 12,012-byte markers closes a 64 KiB block every 6 markers and
  stores its first and last bound, so the flush/compaction index buffer is ≈ ⅓ of the partition ≈ 400 MB
  (`BigFormatPartitionWriter.java:52-58`, `:161-181`), plus the memtable's on-heap range-tombstone list (bounds cloned
  on heap, `BTreePartitionUpdater.java:120`). At the load heap of 8 GiB this fits; it is why s is 12 KB, not 64 KiB.

**Workload and environment.**
- Victim = one Cassandra 5.0.9 node on ms0611; client = one Java-driver JVM on the same node (loopback). One lifetime
  at a time; nothing else runs on ms0611.
- Schema: `CREATE KEYSPACE b16 WITH replication = {'class':'SimpleStrategy','replication_factor':1}`;
  `CREATE TABLE b16.t (pk int, ck text, v int, PRIMARY KEY (pk, ck))` and `CREATE TABLE b16.m (…same…)`, **default
  table options** (LZ4 16 KiB chunks, STCS, `gc_grace_seconds` 864000 so no marker is purgeable, caching keys ALL).
- Data (load lifetime `LOAD`, heap 8G, not a reading): for i in 0 … 49,998, one range deletion
  `DELETE FROM b16.<tbl> WHERE pk = 0 AND ck >= ? AND ck <= ?` with start = `String.format("%06d", i) + "a" + "x"×(s−7)`
  and end = the same with `"b"`: disjoint, non-adjacent ranges → **2 markers per range, 99,998 markers per partition,
  0 live rows**. `t`: s = 12,000 (bounds 12,000 ASCII bytes); `m`: s = 1,000. Sent as UNLOGGED single-partition
  batches of 20 deletions (`t` ≈ 480 KB, below `batch_size_fail_threshold` 640 KiB; single-partition batches skip the
  check anyway, `BatchStatement.java:334-335`), 4 batches in flight, CL ONE, prepared. Raw bytes: `t` ≈ 1.2 GB,
  `m` ≈ 0.1 GB. Then `nodetool flush b16`, `nodetool compact b16` (wait), check one `sstable` per table
  (`nodetool tablestats b16`), `nodetool drain`, stop; `cp -a $ROOT/node $ROOT/template`,
  `rm -rf $ROOT/template/saved_caches/*`. Expected on disk: `t` Data.db small (the filler compresses), Index.db
  ≈ 0.4 GB; template ≈ 0.5 GB. **Every measured lifetime starts from a fresh `cp -a` of the template.** If the load
  cannot finish (e.g. a write-side OOM at 8G, OC-277's domain), record it, then load `t` at s = 8,000
  (R ≈ 0.77 GiB; 2G prediction then c_fail 1–2) as a dated amendment, before any reading.
- Read client: closed loop, c reads in flight over 8 connections, protocol v4, CL ONE, prepared
  `SELECT * FROM b16.<tbl> WHERE pk = 0`, fetch size 5,000 (driver default, set explicitly), client read timeout
  120 s, `FallthroughRetryPolicy`. Each lifetime: warm-up `w` = 1 client on `m` for 15 s, then the arm's steps
  (`c:secs` on its table). Per-second CSV: t, step c, in flight, ok, errors by type (read timeout, READ_TOO_MANY_TOMBSTONES,
  READ_SIZE, other), p50/p99 ms, rows of the last read (must be 0).
- **Arms and conditions** (labels; steps `c:secs`; each sweep stops at the first OOM; table `t` unless named):

| Prio | Label | Arm | Heap | Table / steps | Reps |
|---|---|---|---|---|---|
| 1 | `LOAD` (not a reading) | LOAD | 8G | load `t`, `m`; flush, compact, drain | 1 |
| 2 | `IC` instrument check | **R** | 8G | one read of `m`, then one read of `t` (c = 1), JFR on | 1 |
| 3 | `CAL-2G` | A | 2G | `1:90,2:60,3:60` | 1 |
| 4 | `T-2G-1..3` test | A | 2G | `<c_T>:120` | 3 |
| 5 | `M-2G-1..3` matched control | A | 2G | **`m`**, `<c_T>:120` | 3 |
| 6 | `I-2G-1..3` intervention | **I** | 2G | `<c_T>:120` | 3 |
| 7 | `E-RT-2G-1` bypass of the byte tracker | **R** | 2G | `<c_T>:120` | 1 |
| 8 | `CAL-4G`, `CAL-8G`, `CAL-16G`, `CAL-31744M` budget search | A | 4G / 8G / 16384M / 31744M | `1:90,2:60,3:60,4:60` / `2:60,3:60,4:60,6:60,8:60` / `3:90,4:90,6:90,8:90,12:90` / `6:90,8:90,12:90,16:90,24:90,32:90` | 1 each |
| 9 | `E-RT-2G-2..3` | R | 2G | `<c_T>:120` | 2 |
| 10 | `I2-2G-1..3` attribution intervention | **I2** (patched build) | 2G | `<c_T>:120` | 3 |
| 11 | `CAL-M-2G` (OC-48 shape) | A | 2G | **`m`**, `2:60,4:60,6:60,8:60,12:60,16:60,24:60,32:60` | 1 |
| 12 | `REP-<Hmax>-1..2` | A | largest failing heap | its failing c for 120 s | 2 |

  - Arm **A** = shipped defaults. **c_T** = the smallest c at which `CAL-2G` reached an OOM (predicted 1).
  - Arm **I** (intervention, count bound tightened) = A + `tombstone_failure_threshold: 10000`: a `t` read aborts at
    10,001 markers, ≈ 120 MB serialized (capacity ≤ 144 MiB).
  - Arm **R** = A + `read_thresholds_enabled: true` + `local_read_size_fail_threshold: 64MiB` (the byte control that
    is off by default, switched on; U4's intervention value).
  - Arm **I2** (diagnostic build, attribution) = arm R on a copy of the tree whose jar has two methods patched so a
    marker counts its bound: `RangeTombstoneBoundMarker.unsharedHeapSize()` → `EMPTY_SIZE + bound.dataSize() +
    deletion.unsharedHeapSize()`; `RangeTombstoneBoundaryMarker.unsharedHeapSize()` → `EMPTY_SIZE + bound.dataSize()
    + startDeletion.unsharedHeapSize() + endDeletion.unsharedHeapSize()`. Build: `cp -a $ROOT/tree $ROOT/tree-i2`;
    copy the two pinned source files, edit, `javac -d $ROOT/i2cls -cp "$ROOT/tree/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$ROOT/tree/lib/*:$ROOT/tree/build/lib/jars/*" <2 files>`;
    `jar uf $ROOT/tree-i2/build/apache-cassandra-5.0.9-SNAPSHOT.jar -C $ROOT/i2cls org`; save the exact diff as
    `harness/i2.diff` and both jar sha256s. Same template data.
  - If `CAL-2G` does not OOM at c = 3, extend it once with `4:60,6:60,8:60` before deciding; then c_T is its failing c.

**Harness** (under `harness/` in this folder; adapt U4's verified harness
[`../cql-row-limit--wide-row-default-pages/harness/`](../cql-row-limit--wide-row-default-pages/harness/)):
1. `setup.sh`: the build copy and checksum above; `mkdir -p $ROOT`; tree and pristine conf; compile the client and
   sampler into `$ROOT/cls` (classpath: `$ROOT/tree/build/lib/jars/{cassandra-driver-core-3.12.1-shaded,guava-32.0.1-jre,metrics-core-4.2.28}.jar`
   plus `$ROOT/tree/lib/*`, as U4's `load.sh`; client JVM `-Xmx2g`, own scope `b16-client-<label>`, `MemoryMax=6G`,
   `MemorySwapMax=0`).
2. `victim-ctl.sh` from U4's: `ROOT=/mydata/s4/b16`, `BUILD` = `$ROOT/tree` (arm I2: `$ROOT/tree-i2`); arms
   `LOAD`, `A`, `I`, `R`, `I2` (yaml appends above, `yaml.diff` saved); direct always auto (`MAX_DIRECT_MEMORY_SIZE`
   unset; scope MemoryMax uses 15872M); `JVM_EXTRA_OPTS` as U4 (`-XX:NativeMemoryTracking=summary`, GC log with
   `gc=info,safepoint=info`) plus `-XX:-HeapDumpOnOutOfMemoryError` for heaps ≥ 8G; `CASSANDRA_HEAPDUMP_DIR` = run dir.
3. `B16Load.java` (from `U4Load.java`): `schema`; `load <tbl> <ranges> <boundBytes> <batch> <inflight>`;
   `one <tbl>` (prints rows, latency, error class and message); `run <conns> <warmTbl> <warmSecs> <tbl> <steps>`
   with the CSV above.
4. `C2Sampler.java` unchanged (JMX 1 s: heap used, G1 old-gen post-GC, NTR and ReadStage active/pending, `java.nio`
   direct). Table metrics at the end of each surviving lifetime and after each IC read with
   `nodetool sjk mx -b "org.apache.cassandra.metrics:type=Table,keyspace=b16,scope=<tbl>,name=<N>" -mg -f <attr>` for
   `TombstoneScannedHistogram` (Max, Count), `TombstoneFailures` (Count), `LocalReadSize` (Max, Count),
   `LocalReadSizeAborts` (Count) (or a small JMX client if `sjk` is missing).
5. `run-arm.sh <label> <arm> <heap> <tbl> <steps>` from U4's: refuse if a `CassandraDaemon` runs; disk-space gate;
   clone; start; ready (120 s; one retry); sampler; client; readings every 10 s (NMT summary, `RssAnon`, scope
   `memory.current`); on client end or victim death: outcome (`OutOfMemoryError` line from `stdout.log`/`system.log`,
   hprof present, scope `memory.events`), count of `Read 0 live rows and 99998 tombstone cells` warnings and
   `Scanned over` / `local_read_size_fail_threshold` lines in `system.log`; stop a survivor (`nodetool drain`, SIGTERM
   by PID); then hprof analysis and deletion (2G/4G); copy small files to `logs/<label>/`; full logs on
   `ms0611:$ROOT/runs/<label>/`. Launch each lifetime as a background job and poll with bounded waits.
6. `gcwin.py`, `steps.py` from U4; `hprofhist.py` from U4 with the B16 buckets: `byte[]` ≥ 64 MiB (response
   buffers: count and lengths), `byte[]` of 12,000 ± 32 B and of 1,000 ± 32 B (bound copies), `byte[]` ≥ 8 MiB
   (humongous); `hprofstacks.py <hprof> expandToFit` and `… LocalDataResponse`.
7. IC JFR: `jcmd <pid> JFR.start name=ic settings=profile filename=$R/ic.jfr` before the two reads,
   `JFR.stop name=ic` after; `jfr print --json --events jdk.ObjectAllocationOutsideTLAB --stack-depth 16 ic.jfr` and
   take, per read window, the largest `allocationSize` whose stack contains `DataOutputBuffer.expandToFit`
   (the method of stage 4's
   [`JfrBuf.java`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/harness/tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous/JfrBuf.java)).
   Delete the `.jfr` after extracting.

**Instruments (U independent of K).**
- K (counters): markers counted per read (`TombstoneScannedHistogram` Max; `system.log` warning "Read 0 live rows and
  N tombstone cells"); `TombstoneFailures`; in arms R/I2, `LocalReadSize` Max and `LocalReadSizeAborts`.
- U (real memory): (a) at an OOM (2G/4G), the hprof: count and lengths of `byte[]` ≥ 64 MiB, the 12,000-B bound
  copies, the stack of the thread in `DataOutputBuffer.expandToFit` ← `ReadResponse$LocalDataResponse.build`
  ← `StorageProxy$LocalReadRunnable`; (b) in `IC`, JFR's largest response-buffer allocation per read (U for one read
  without OOM) and the read latency; (c) G1 old-gen post-GC usage and heap used (1 s JMX) and NTR/ReadStage active
  (the load reached c); (d) GC log → STW fraction per 60 s (`gcwin.py`); (e) NMT and `RssAnon` every 10 s (ledger:
  direct stays small); (f) client: 0 rows per read, error classes, reads completed.
- Sampling: 1 s JMX, 10 s readings; one `jcmd GC.class_histogram` only in surviving `M`/`I`/`I2` lifetimes at load
  second 100 (intrusive, so not in failing arms).

**Predicted response** (before readings).
- `LOAD`: completes; `t` and `m` one sstable each; IC read-back of 99,998 markers per table.
- `IC` (8G, arm R): `m` read OK, 0 rows, Tombstone Max 99,998, **LocalReadSize Max ≈ 4.8 MB (band 3–10 MB)**, JFR max
  buffer ≈ 118–145 MiB; `t` read OK (no rejection), 0 rows, Tombstone Max 99,998, **LocalReadSize Max ≈ the same
  4.8 MB** (bound bytes uncounted, < 64 MiB), **JFR max buffer ≈ 1.6 GiB (band 1.1–1.7 GiB)**, latency ≥ 5 s possible
  and still OK (finding 2; not decisive). Implied bytes per marker ≈ 12,013 (t) and ≈ 1,013 (m).
- `CAL-2G`: Java heap OOM at **c = 1** during the first `t` read (≤ 90 s).
- `T-2G` ×3: `java.lang.OutOfMemoryError: Java heap space` 3/3 at c_T; hprof with one response `byte[]` of
  ≈ 1,091 MiB (or the 727 MiB step) and the OOM thread in `DataOutputBuffer.expandToFit` under
  `LocalDataResponse.build`; then the shipped `kill -9`.
- `M-2G` ×3 (same 99,998 markers, bounds 12 × smaller): survive 0/3 OOM; reads OK, 0 rows; old post-GC < 1 GiB.
- `I-2G` ×3: survive 0/3; every `t` read fails `READ_TOO_MANY_TOMBSTONES` ("Scanned over 10001 tombstones");
  0 successful reads (recorded: the count bound protects by rejecting).
- `E-RT-2G`: **OOM** like `T` (the 64 MiB byte bound never fires; `LocalReadSizeAborts` 0 before death).
- `I2-2G` ×3: survive 0/3; every `t` read fails with the local read-size abort ("attempted to read N bytes but max
  allowed is 64MiB") after ≈ 5,500 markers; `m` warm-up reads also abort once their counted bytes pass 64 MiB
  (≈ 66,000 markers; recorded).
- Budget search: c_fail 4G → 2, 8G → 3, 16384M → 5, 31744M → 9 (bands above); **largest failing heap predicted
  31,744 MiB** (ms0611's own default).
- `CAL-M-2G`: OOM at c ≈ 8 (6–12).
- Direct (`java.nio`, NMT Other) stays < 0.5 GiB; no scope `oom_kill`.

**Stopping budget and time plan** (deadline **18:07 EST 2026-11-18**: everything stopped and §3–§4 written; ms0611
shows MST). Durations from the stage-2 start S (expected 14:30–15:00 EST), ARM estimates: setup + harness → S+30 min;
`LOAD` → S+50; `IC` → S+58; `CAL-2G` → S+63; `T` ×3 → S+78; `M` ×3 → S+93; `I` ×3 → S+108; `E-RT-1` → S+113; budget
search (≈ 5 + 6 + 9 + 11 min) → S+144; `E-RT-2..3` → S+154; `I2` build + ×3 → S+174; `CAL-M-2G` → S+184; `REP`
only if time remains. **Hard limits:** no lifetime starts after **17:30 EST** unless it ends by 17:45; all processes
stopped by **17:50 EST**; §3–§4 written by 18:07. **Cuts by start time:** S after 15:00 → skip `REP` and `CAL-M-2G`;
after 15:20 → also skip `I2` and `E-RT-2..3`, and run the budget search only at 4G and 31744M; after 16:00 → only
`LOAD`, `IC`, `CAL-2G`, `T`, `M`, `I`, `E-RT-1`; never cut priorities 1–6. Per lifetime: steps as listed; a node not
ready in 120 s is invalid (retry once); a lifetime's victim is stopped no later than 2 min after its last step. No
escalation after an OOM beyond the planned list.

**Controls and intervention.**
- **Matched control `M-2G` ×3:** same build, heap, template, client, c_T and **count** (99,998 markers, 0 live rows,
  same ranges); only the bound size differs (1,000 vs 12,000 B). Same K, different U: shows the counter does not
  track the memory. `CAL-2G`'s step below c_T is reported as the multiplicity boundary when c_T > 1.
- **Intervention `I-2G` ×3:** the T workload with the count bound tightened 10 × (100,000 → 10,000); removing the OOM
  ties it to the number of markers admitted per read times their size (it also stops every read; recorded).
- **Bypass evidence `E-RT` and attribution `I2`:** E-RT switches on the byte control that ships off; an OOM there
  with `LocalReadSize` ≤ 64 MiB (IC) shows U > C, K ≤ C for that control (accounting omission). I2 restores the
  bound bytes to the marker's size and should remove the OOM.

**Verdict rules (stated before readings).**
- **true positive:** `T-2G` heap OOM in ≥ 3 runs (if 2/3, add up to 2 more), `M-2G` 0/3, `I-2G` 0/3, and the dump
  shows the replica response buffer (`byte[]` ≥ 64 MiB on the `LocalDataResponse.build` path) → `verified-OOM ·
  deployment`, direction **bypass** (count control, unbounded bytes per marker; byte control off at defaults). Add
  "byte tracker omits marker bounds" to the classification only if `E-RT` OOMs with IC's `LocalReadSize` ≤ 64 MiB, and
  "attributed" only if `I2` is 0/3. Largest failing budget from the search, with n/N.
- **retry:** OOM only in another holder (e.g. the dump shows `IndexInfo` or scan garbage, not the response buffer, or
  the load phase fails on the row-index buffer) — the design needs a shape change; service loss (≥ 90 % STW over
  ≥ 60 s) without OOM (`verified-gap`); OOM < 3 runs after 5; `M` also OOMs at c_T (holder not attributed to bound
  bytes); time ran out before V1/V2/V4.
- **false positive:** `CAL-2G` (with its extension) reaches c = 8 with NTR active ≥ c, every `t` read returns 0 rows
  with 99,998 markers counted, IC's JFR buffer is ≥ 1 GiB, and old post-GC stays < 90 % of the heap with no OOM, with no
  named factor left untried (then extend once to `12:60,16:60,24:60,32:60`).
- **invalid lifetime:** client JVM OOM or error on every read for a non-memory reason, scope `oom_kill`, a read that
  does not count 99,998 markers or returns rows, a template that does not match `LOAD`'s read-back; fix and rerun,
  recorded as a deviation.
- **Cleanup:** stop every process started; keep `$ROOT/runs/` (logs, summaries; hprofs and `.jfr` already deleted
  after extraction) and `$ROOT/template` and `/mydata/s4/cassandra-base`; report what is left on ms0611. Touch nothing
  outside `/mydata/s4/b16` and `/mydata/s4/cassandra-base`.

`sha256 of §1–§2 at freeze: 62efdef377f4cdfbd168423daf3a6a12782253b9755b4e1c9a7ca70907f29472` · computed over the lines from `## 1. Candidate` through the line before this one (`sed -n '/^## 1\. Candidate/,/^`sha256 of §1–§2 at freeze/p' <file> | sed '$d' | sha256sum`) · amendments after the freeze: dated, with reason, below this line.

## 3. Runs (stage 2)

**Stage 2:** phase-2 OOM agent, stage 2 session (fresh session), wave 4, 2026-11-18 13:57–15:35 EST.
Freeze hash checked at 13:57 EST: `sed … | sha256sum` = `62efdef3…7f29472`, equal to §2's line. Nothing in §1–§2 changed.

**Environment (as run).** `ms0611` (`node3.jason92-326377…utah.cloudlab.us`), **aarch64**, 8 cores, 64,249 MiB RAM, 8 GiB swap,
cgroup v2, `/mydata` 35 GiB free at start (31 GiB at the end of the arm list), JDK 11.0.33 (`java-11-openjdk-arm64`), Ant
1.10.12, Python 3.10.12; no Java process at start (`pgrep -af CassandraDaemon` empty, load 0.04). Node clock MST.
- **Build:** `ssh ms0617 'tar -C /mydata/s4 -cf - cassandra-base' | ssh ms0611 'tar -C /mydata/s4 -xf -'` (469 MB); jar sha256
  on ms0611 `e55f4f2974cb6120712a5cdfbbed9ee1ba25d97b887cbe71b64fd194f3b5a942` (= §2). Work root
  **`/mydata/s4/b16-w4`** (see deviation 1): `tree/` = `cp -a` of the base, `conf-pristine/`, `cls/`, `template/`, `runs/`.
- **I2 build:** `tree-i2/` = copy of `tree/`, the two classes of [`harness/i2.diff`](harness/i2.diff) compiled with `javac`
  against the unmodified jar and written with `jar uf`; jar sha256 `c78daa7eb0448d3675d641350b69450d08df908be8e5c4226566b7276bfecf1f`
  (unmodified `e55f4f29…3b5a942`). Script [`harness/i2-build.sh`](harness/i2-build.sh).
- **JVM line (every lifetime, from `ps`):** `-XX:+HeapDumpOnOutOfMemoryError -XX:+AlwaysPreTouch -XX:+UseG1GC
  -XX:G1HeapRegionSize=16m -XX:G1NewSizePercent=50 -XX:MaxGCPauseMillis=300 -Xms<H> -Xmx<H> -XX:MaxDirectMemorySize=15872M
  … -XX:NativeMemoryTracking=summary [-XX:-HeapDumpOnOutOfMemoryError for H ≥ 8G] -XX:OnOutOfMemoryError=kill -9 %p`;
  resolved (`jinfo`): `MaxDirectMemorySize=16642998272` (15,872 MiB, auto) in every lifetime, `MaxHeapSize` = H.
- **Scopes:** victim `systemd-run --user --scope -p MemoryMax=<H+15872M+8G> -p MemorySwapMax=0`; client `MemoryMax=6G`,
  `-Xmx2g`. `memory.events` `oom_kill 0` in every lifetime with a reading.
- **yaml:** arm A/LOAD only the five directories ([`logs/CAL-2G/yaml.diff`](logs/CAL-2G/yaml.diff)); arm I +
  `tombstone_failure_threshold: 10000`; arms R/I2 + `read_thresholds_enabled: true`, `local_read_size_fail_threshold: 64MiB`
  ([`logs/E-RT-2G-1/yaml.diff`](logs/E-RT-2G-1/yaml.diff)); `system.log` "Node configuration" shows `read_thresholds_enabled=true`, `local_read_size_fail_threshold=64MiB` in arm R; arm I's value shows in its "Scanned over 10001 tombstones" aborts.
- **Harness:** [`harness/`](harness/) — `setup.sh`, `victim-ctl.sh`, `run-arm.sh`, `load-data.sh`, `batch.sh` (arm list in
  priority order with the 17:45 EST guard), `load.sh`, `B16Load.java`, `C2Sampler.java` (unchanged), `gcwin.py`, `steps.py`
  (unchanged), `hprofhist.py` (B16 buckets), `hprofstacks.py` (40 frames, deviation 3), `jfrmax.py`, `i2-build.sh`,
  `i2.diff`. Full logs on **`ms0611:/mydata/s4/b16-w4/runs/<label>/`** (system.log, gc.log, samples, readings, client.csv,
  hprof summaries; hprofs deleted after analysis, `ls -l` kept in `logs/<label>/hprof.ls`); excerpts in [`logs/`](logs/).

**LOAD (8G, arm LOAD, 14:02–14:05 EST; not a reading).** `t`: 49,999 ranges × 12,000-B bounds in 14 s, 0 errors; `m`:
49,999 × 1,000 B in 5 s, 0 errors; flush, `compact` 24 s; one sstable per table (`t` Data.db 8.5 MB, Index.db 400.4 MB,
"Compacted partition maximum bytes" 1,386,179,893; `m` Data.db 1.2 MB, Index.db 3.1 MB, 107,964,792). Read-back: `m` and
`t` 0 rows, "Read 0 live rows and **99998** tombstone cells" for each (`t` 3.9 s, `m` 1.5 s at 8G). Template 396 MB.
No write-side failure, so the s = 8,000 fallback was not needed. [`logs/LOAD/`](logs/LOAD/).

**IC (8G, arm R = byte tracker on at 64 MiB, 14:05–14:08 EST).** [`logs/IC/`](logs/IC/)
- `m` read: OK, 0 rows, 1,742 ms, warning 99,998 tombstones; **`LocalReadSize` Max 4,866,323 B** (Count 1, aborts 0); JFR
  `expandToFit` allocations 8.0 → 16.1 → 32.2 → 64.3 → 96.5 → **144.7 MiB** (151,732,240 B).
- `t` read: OK (no abort), 0 rows, 4,189 ms, warning 99,998 tombstones; **`LocalReadSize` Max 4,866,323 B** — the same
  counted bytes as `m` with bounds 12 × larger; JFR `expandToFit` allocations … 211.4 → 317.2 → 475.8 → 713.6 → 1,070.5 →
  **1,605.7 MiB** (1,683,675,088 B). So the response R_t lies in (1,070.5, 1,605.7] MiB (predicted ≈ 1,146 MiB, last
  capacity predicted 1,636 MiB), and the byte tracker's K for that read is 4.87 MB: **U/K ≥ 230** (≥ 1,070.5 MiB / 4.64 MiB).
  Old gen after the read 5,270 MiB used (garbage at 8G).

**Runs** (H = heap; c = reads in flight on the step; every lifetime starts with a fresh template, warm-up 1 read on `m` for
15 s, 0 rows on every successful read; "+s" = seconds from client start to victim death).

| Run | Arm | Budget | Load reached | Endpoint | Key reading (U vs K) |
|---|---|---|---|---|---|
| `CAL-2G` | test (A) | 2G | c = 1 (first `t` read) | **Java heap OOM** at c = 1, +31 s | dump: one `byte[]` **713.6 MiB** (the response buffer; 776 MiB shallow heap); K: 99,998 markers ≤ 100,000 → **c_T = 1** |
| `T-2G-1` | test (A) | 2G | c = 1 | **Java heap OOM**, +33 s | one `byte[]` **1,070.5 MiB**; 1 `DataOutputBuffer`, 1 `LocalDataResponse`; OOM thread in `DataOutputBuffer.expandToFit` ← `ClusteringBoundOrBoundary$Serializer.serialize` |
| `T-2G-2` | test (A) | 2G | c = 1 | **Java heap OOM**, +31 s | one `byte[]` **713.6 MiB**; same stack |
| `T-2G-3` | test (A) | 2G | c = 1 | **Java heap OOM**, +33 s | one `byte[]` **713.6 MiB**; same stack |
| `M-2G-1` | matched control (A, `m`) | 2G | c = 1, 121 s, 209 reads | none (survived) | 99,998 markers per read (209 warnings); old post-GC max 188 MiB; STW max60 1 % |
| `M-2G-2` | matched control | 2G | c = 1, 216 reads | none | old post-GC max 172 MiB; STW max60 1 % |
| `M-2G-3` | matched control | 2G | c = 1, 211 reads | none | old post-GC max 812 MiB; STW max60 4 % |
| `I-2G-1` | intervention (I) | 2G | c = 1, 689 reads | none | **0 reads OK**; 689 errors = 689 "Scanned over 10001 tombstones" (`t` 451, `m` warm-up 238); old post-GC max 227 MiB (c = 1 step) |
| `I-2G-2` | intervention | 2G | c = 1, 688 reads | none | 0 OK; 688 = 688 "Scanned over 10001"; old post-GC max 964 MiB |
| `I-2G-3` | intervention | 2G | c = 1, 614 reads | none | 0 OK; 614 = 614 "Scanned over 10001"; old post-GC max 397 MiB |
| `E-RT-2G-1` | bypass of the byte tracker (R) | 2G | c = 1 | **Java heap OOM**, +32 s | 0 `local_read_size` aborts logged; `byte[]` **713.6 MiB**; full stack (below) |
| `E-RT-2G-2` | R | 2G | c = 1 | **Java heap OOM**, +33 s | 0 aborts; `byte[]` **1,070.5 MiB** |
| `E-RT-2G-3` | R | 2G | c = 1 | **Java heap OOM**, +31 s | 0 aborts; `byte[]` **713.6 MiB** |
| `I2-2G-1` | attribution (I2, patched) | 2G | c = 1, 709 reads | none | 0 OK; every read aborted by the byte tracker: `t` 661 reads at **5,570 markers**, `LocalReadSize` Max 74,975,550 B, `LocalReadSizeAborts` 661; `m` warm-up 48 aborts |
| `I2-2G-2` | I2 | 2G | c = 1, 816 reads | none | 0 OK; `t` 768 aborts at 5,570 markers; `m` 48 |
| `I2-2G-3` | I2 | 2G | c = 1, 866 reads | none | 0 OK; `t` 816 aborts at 5,570 markers; `m` 50 |
| `CAL-4G` | budget search (A) | 4G | c = 1 | **Java heap OOM** at c = 1, +54 s | `byte[]` **1,070.5 MiB** (dump 1,206 MB) |
| `CAL-8G` | budget search (A) | 8G | c = 2: 60 s, 27 reads OK; c = 3 | **Java heap OOM** at c = 3, +135 s | c = 2 old post-GC max 3,820 MiB; c = 3 old post-GC 4,540 MiB, 6 client read timeouts; dumps off |
| `CAL-16G` | budget search (A) | 16384M | c = 3: 90 s, ≈ 50 reads; c = 4 | **Java heap OOM** at c = 4, +173 s | c = 3 old post-GC max 6,508 MiB; c = 4: 42 client read timeouts, ReadStage active max **12** |
| `CAL-31744M` | budget search (A) | 31744M | c = 6 (first step): 26 reads OK, 76 timeouts | **Java heap OOM** at c = 6, +106 s | old post-GC max 26,014 MiB; ReadStage active max **32** (= `concurrent_reads`) |
| `CAL-M-2G` | OC-48 shape (A, `m`) | 2G | c = 2/4/6: 60 s each (2.7/4.6/4.8 reads/s); c = 8 | **Java heap OOM** at c = 8, +246 s | dump: **11** `byte[]` of 64–145 MiB = 1,141.5 MiB, 7 `LocalDataResponse`, 5 threads in `LocalDataResponse.build`; full-GC share 15 % at c = 8 |
| `REP-31744M-1` | repetition at the largest failing heap (A) | 31744M | c = 6: 28 reads OK, 72 client timeouts | **Java heap OOM** at c = 6, +106 s | old post-GC max 20,734 MiB; ReadStage active max **32** |
| `REP-31744M-2` | repetition (A) | 31744M | c = 6: 28 reads OK, 70 client timeouts | **Java heap OOM** at c = 6, +105 s | old post-GC max 21,165 MiB; ReadStage active max **32** |

Outcome types: every endpoint above is `java.lang.OutOfMemoryError: Java heap space` from the victim's `stdout.log`
followed by the shipped `kill -9`; `HeapDumper`/`ReportJavaOutOfMemory` safepoints in gc.log; no scope `oom_kill`; no
service loss (STW max60 ≤ 18 % in every lifetime). Per-step summaries in `logs/<label>/steps.txt`, GC windows in
`logs/<label>/gcwin.txt`, dump summaries in `logs/<label>/hprofhist.txt`, stacks in `logs/<label>/hprofstacks.txt`.

**OOM stack (V5; `E-RT-2G-1`, identical in `E-RT-2G-2/3`, `CAL-4G`; the first 14 frames identical in `CAL-2G`, `T-2G-1..3`):**
`OutOfMemoryError` ← `ByteBuffer.allocate` ← `BufferedDataOutputStreamPlus.allocate:77` ← `DataOutputBuffer.expandToFit:178`
← `doFlush:138` ← … `ClusteringPrefix$Serializer.serializeValuesWithoutSize:473` ←
`ClusteringBoundOrBoundary$Serializer.serialize:107` ← `UnfilteredSerializer.serialize:287` (the marker) ←
`UnfilteredRowIteratorSerializer.serialize` ← `UnfilteredPartitionIterators$Serializer.serialize:339` ←
**`ReadResponse$LocalDataResponse.build(ReadResponse.java:201)`** ← `ReadCommand.createResponse:374` ←
**`StorageProxy$LocalReadRunnable.runMayThrow:2211`** ← `SEPWorker.run`. The OOM is thrown while the replica writes a
marker's bound into its response buffer.

**Predictions vs readings.** `IC`, `CAL-2G` (c = 1), `T` 3/3, `M` 0/3, `I` 0/3, `E-RT` OOM, `I2` 0/3 (abort ≈ 5,500
predicted, 5,570 read; `m` warm-up aborts predicted, seen) and `CAL-M-2G` (c ≈ 8 predicted, 8 read) as predicted.
c_fail: 4G **1** (predicted 2, band 1–2), 8G **3** (3), 16384M **4** (5, band 4–8), 31744M **≤ 6** (9, band 7–16; 6
was the sweep's first step). The large heaps fail below the prediction because timed-out reads keep scanning: at
16384M and 31744M the coordinator answers the client with a read timeout after 5 s (42 and 76 timeouts), the client
sends its next read, and the replica's marker scan, which the timeout cannot cancel (source finding 2), keeps building
its buffer — ReadStage active reached 12 with 4 client reads and 32 with 6. The dump at 2G holds the 713.6 MiB step
(2/3 of dumps) or the 1,070.5 MiB step: the failing request is the next growth (1,070.5 or 1,605.7 MiB) while the old
array is live, as the ceiling arithmetic predicted.

**Deviations from the design** (none changes a constraint, a budget or the workload):
1. *Work root* `/mydata/s4/b16-w4`, not `/mydata/s4/b16` (the session's node instruction: a fresh `-w4` directory). Environment only.
2. *Client error classes.* With protocol v4 the driver's `ReadFailureException` carries an empty failure-reason map, so the
   CSV's `eTomb`/`eSize` columns stayed 0 and every rejection landed in `eOther`. The class of each error is taken from
   `system.log` instead: the count of "Scanned over 10001 tombstones" (arm I) and of local-read-size abort lines (arm I2)
   equals the client's error count in every lifetime (`logs/<label>/threshold-excerpt.txt`).
3. *Stack depth of `hprofstacks.py`.* U4's copy prints 14 frames; raised to 40 at 14:17 EST (after the `CAL-2G` and `T`
   dumps had been analysed and deleted). Those four dumps show the stack down to `ClusteringBoundOrBoundary$Serializer.serialize`
   and one `LocalDataResponse` instance; every later dump (`E-RT` ×3, `CAL-4G`, `CAL-M-2G`) shows the full path above.
4. *JFR stack depth 16* (as designed) does not reach `LocalDataResponse`; IC's buffer sizes are the `expandToFit`
   allocations of the read window (one read per window, nothing else serializing).
5. *Thread.* The local read ran on a ReadStage worker (`SEPWorker` → `LocalReadRunnable`), not inline on the request thread
   as source finding 4 expected; the holder is the same.
6. *K in failing lifetimes.* Table metrics cannot be read after the victim dies; K for a `t` read is IC's (99,998 markers,
   `LocalReadSize` 4,866,323 B) and the warning lines of surviving reads. `TombstoneScannedHistogram` Max shows the
   histogram bucket 105,778 for 99,998 (5,722 for 5,570; 11,864 for 10,001).
7. *After a victim death* the client loops on `NoHostAvailableException` until it is stopped, so the dying step's error
   count in `steps.txt` (millions) is not reads; reads and timeouts above are counted up to the last valid JMX sample.
8. *hprof analysis* ran in the background (nice 19, one at a time) during the next lifetime, as in U4's batch.

**Left on ms0611:** `/mydata/s4/b16-w4/` (≈ 2.3 GB: `tree/`, `tree-i2/`, `template/`, `conf-pristine/`, `cls/`,
`i2cls/`, `i2src/`, `harness/`, `repo-logs/`, `runs/` with full logs; no hprof, no `.jfr`) and `/mydata/s4/cassandra-base/`
(the build copied from ms0617). No process left (`pgrep -af 'CassandraDaemon|B16Load|C2Sampler'` empty at 15:22 EST).
`/mydata/s2r2/` and `/mydata/u1r2/` untouched.

## 4. Conclusion (stage 2)

- **Verdict:** **`true positive`** ([`oom-agent-playbook.md`](../../../oom-agent-playbook.md)).
- **Protocol status (detail):** **`verified-OOM · deployment`**, direction **bypass** (count control with unbounded bytes per
  counted marker; the byte control that ships off omits marker bounds when switched on: U > C, K ≤ C, accounting
  omission), **attributed** (`I2` 0/3). Interpretation: the threshold being a count is by design (CASSANDRA-6117); the byte
  guard being off is a configuration gap (unprotected configuration); the marker's `unsharedHeapSize()` leaving out its
  bound and the marker scan escaping the read-timeout cancellation are suspected implementation defects.

| | Requirement | Evidence |
|---|---|---|
| V1 Repetition | ≥ 3 runs reach the endpoint | `T-2G-1..3` 3/3 Java heap OOM at c = 1 (and `CAL-2G` 1/1, same condition: 4/4) |
| V2 Matched control | nearest surviving control ≥ 3 runs | `M-2G-1..3` 0/3 (same 99,998 markers, 0 rows, same c, same heap; bounds 1,000 B): 209–216 reads each, old post-GC ≤ 812 MiB |
| V3 Measurement | U independent of K | U: hprof `byte[]` 713.6 / 1,070.5 MiB on the OOM path, JFR 1,605.7 MiB for one read; K: 99,998 markers ≤ 100,000 (count control), `LocalReadSize` 4,866,323 B ≤ 64 MiB (byte control, arm R) |
| V4 Intervention | ≥ 3 runs without the endpoint | `I-2G-1..3` 0/3 (count bound 10,000: every read rejected, 0 successful reads); `I2-2G-1..3` 0/3 (bound counted: every `t` read aborted at 5,570 markers, 0 successful reads). Both protect by refusing the read; recorded |
| V5 Initiating failure | first error + stack + dump | `java.lang.OutOfMemoryError: Java heap space` in `DataOutputBuffer.expandToFit` ← `LocalDataResponse.build:201` ← `LocalReadRunnable`; dump: one response `byte[]` holds 92–95 % of the shallow heap |
| V6 Default constraints | all at shipped defaults | arm A: only directory settings changed (`yaml.diff`); `tombstone_failure_threshold` 100,000, `read_thresholds_enabled` false, `concurrent_reads` 32, `read_request_timeout` 5 s, BIG format, defaults resolved at each heap |
| V7 Acceptable budget | ≥ 512 MiB heap; search upward | 2 GiB heap (ideal), direct 15,872 MiB (auto); OOM also at 4G (c = 1), 8G (c = 3), 16384M (c = 4) and **31,744 MiB** — ms0611's own auto heap, the largest `cassandra-env.sh` resolves — at c = 6 (**3/3**: `CAL-31744M`, `REP-31744M-1..2`) |

| Condition | n/N | Status |
|---|---|---|
| defaults, 2 GiB heap, `t` (12,000-B bounds), c = 1 | 4/4 OOM (`CAL-2G`, `T` ×3) | `verified-OOM · deployment` |
| defaults, 31,744 MiB heap (node auto), `t`, c = 6 | 3/3 OOM (`CAL-31744M`, `REP` ×2) | `verified-OOM · deployment` (no matched control or intervention at this heap; V2/V4 come from 2 GiB) |
| defaults, 4G / 8G / 16384M, `t`, sweep | 1/1 each (c = 1 / 3 / 4) | budget-search readings |
| byte guard on (64 MiB), 2 GiB, `t`, c = 1 | 3/3 OOM (`E-RT`) | bypass of the byte tracker (U > C, K ≤ C) |
| defaults, 2 GiB, `m` (1,000-B bounds), c = 1 | 0/3 | matched control |
| defaults, 2 GiB, `m`, sweep | OOM at c = 8, 1/1 (`CAL-M-2G`) | OC-48 shape, single sweep (lead, not verified) |
| count bound 10,000 / bound counted (I2), 2 GiB, `t`, c = 1 | 0/3 / 0/3 | interventions |

- **Reason:** at shipped defaults, one `SELECT` of a partition holding 99,998 range-tombstone markers with 12,000-byte
  bounds and no live rows passes every guard that is on — the tombstone threshold counts 99,998 ≤ 100,000, the page never
  fills — and the replica serializes the whole partition into one heap `DataOutputBuffer` whose capacity reaches 1,605.7
  MiB (JFR, 8G); on a 2 GiB heap the growth from 713.6 or 1,070.5 MiB to the next step throws `OutOfMemoryError: Java heap
  space` in `LocalDataResponse.build` on the first read, 3/3 (`T`) plus `CAL-2G`, while the same 99,998 markers with
  1,000-byte bounds (`M`, 145 MiB responses) survive 0/3 OOM over 636 reads, and tightening the count bound to 10,000 (`I`)
  removes the OOM 0/3. The byte control that ships off does not help when switched on: its counter charged the `t` read
  4,866,323 B — the same as the `m` read — so the 64 MiB limit never fired and `E-RT` OOMed 3/3; counting the bound
  (`I2`) makes the same limit abort every `t` read at 5,570 markers (74,975,550 B) and removes the OOM 0/3. The budget
  search shows the endpoint at every heap `cassandra-env.sh` resolves, up to 31,744 MiB at 6 concurrent reads, helped by
  read timeouts that free the client but not the replica scan (ReadStage active 32). OC-48's 1 KB-bound shape also
  reaches OOM at 2 GiB with 8 concurrent reads (`CAL-M-2G`, 1/1, 11 response buffers of 64–145 MiB).
- **Limits of attribution:** one node, RF 1, loopback client; OC-162 (coordinator copies of remote responses) not tested;
  `CAL-*` and `CAL-M-2G` are single sweeps (n = 1 per step) apart from the 31,744 MiB condition (3/3); the T dumps' stacks are truncated at 14
  frames (deviation 3); s = 12,000 B, not 64 KiB.
- **For retry:** — (not a retry).
