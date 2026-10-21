# Stage 3 — predicted positive, pending write-up (formerly `pending.md`)

Lines stage 3 has **read against the three rules and accepted**, but which do
not yet exist as case files in [`cases/`](cases/). They are findings, not a
queue: the judgement is made: what remains is the write-up (all nine
questions of [`../README.md` §5](../README.md#5-required-content-per-if-check-case),
citations checked against the pinned tag).

An entry leaves this file when its case file lands in `cases/` and its row is
added to [`_INDEX.md`](_INDEX.md). Nothing else belongs here — rows still
*awaiting* a read live in
[`../stage2-ai-preprocessing/bands.md`](../stage2-ai-preprocessing/bands.md),
which is stage 3's 3a queue, and rows read but not settled live in
[`undetermined.md`](undetermined.md).

## Write-up queue (updated 2026-10-21)

Two candidates, both accepted 2026-10-21 when the last undecided rows of
[`undetermined.md`](undetermined.md) were settled (feed **3a**; agent guided;
no autonomous file exists for either). Citations checked against the clone at
`cassandra-5.0.9`.

| # | Candidate | Check site | Pattern | What the write-up must carry |
|---|---|---|---|---|
| 14 | `cached_rows_fail_threshold` | [`ReplicaFilteringProtection.java:323`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/ReplicaFilteringProtection.java#L323) `currentRowsCached == cachedRowsFailThreshold + 1`, in `incrementCachedRows()` | (c) | Passes Rule 2 by the 2026-10-21 ruling (README §3.5): rows **held** on the coordinator heap, row size fixed by the schema. The count is raised in `PartitionBuilder.addRow()` (`:477`, count at `:481`) **before** the row is stored, and released per partition in `close()` (`:564`), so the cap is on rows held at once per query, not per query in total. Disallow throws `OverloadedException` (`:331`) and fails the query. Scope: per filtering/index query on the coordinator, node-wide × concurrent such queries. Default 32,000 (`cassandra.yaml:1835`); the warn twin is `:333`. **Target 3:** the error message names `cached_replica_rows_fail_threshold` (`:326`, and the warn message `cached_replica_rows_warn_threshold`, `:338`), keys that do not exist; the yaml keys are `replica_filtering_protection.cached_rows_fail_threshold` / `_warn_threshold`. Null rows are counted too (`:485`). |
| 15 | `native_transport_max_frame_size` | [`Envelope.Decoder.decode():429`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Envelope.java#L429) `totalLength > MAX_TOTAL_LENGTH`, with its allow side `:441` | (a) | `MAX_TOTAL_LENGTH = getNativeTransportMaxFrameSize()` (`:197`, default 16 MiB, `Config.java:285`). Allow: `null` until `totalLength` bytes are in the decoder's cumulation buffer (`:441-442`), then an `Envelope` whose body retains a slice (`:448-449`). Disallow: discard mode, bytes dropped as they arrive, error to the client. **Nothing bounds the cumulation before this check**: on the pre-v5 pipeline (`PipelineConfigurator.java:391`) the in-flight limits are acquired after decode, in `LegacyDispatchHandler.checkLimits()` (`PreV5Handlers.java:149-215`), whose own comment says the check "should have been ideally" in `Envelope.Decoder::decode()`. The same decoder sits in the initial handler (`PipelineConfigurator.java:265`) before negotiation, for every protocol version. So it is a **per-connection** cap on bytes buffered before decode: node-wide = connections × frame size, bounded only by `native_transport_max_concurrent_connections` (default −1, unlimited). The §9 design must vary the connection count, not only the limit. v5 after negotiation frames messages in `FrameDecoder` and is bounded by the filed `native_transport_max_message_size` and receive-queue cases; say which path each arm uses. Cross-link `max_mutation_size` (stage 4 found its 17 MiB write refused here first). |

> **Cleared 2026-10-21.** Until then the filed entries were kept here, struck
> through, as a trail: write-up queue items 1–13 (filed 2026-10-06 to
> 2026-10-15), the four capacity-word-pass candidates (2026-09-22), the eight
> band-A1 candidates (2026-09-28), and an "already covered — cite, do not
> re-file" table. All were filed as cases and closed at stage 4, so they were
> removed per the rule above. The `ResourceLimits$Basic.tryAllocate():213`
> note moved to [`undetermined.md`](undetermined.md) §5 row 3; the
> `CommitLogSegmentManagerCDC.permitSegmentMaybe():200` second check site was
> already in the `cdc_total_space` case file (applied 2026-09-23). Earlier
> references to this file (for example from `undetermined.md` §6 and §7 and
> `predicted-negative.md`) point at that trail; read it at commit `98b8eb3`.
