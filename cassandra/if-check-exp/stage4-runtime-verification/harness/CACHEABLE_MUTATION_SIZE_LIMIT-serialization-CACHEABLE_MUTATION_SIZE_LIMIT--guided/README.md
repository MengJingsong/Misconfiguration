# Harness — CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT

Stage-4 harness for the case's §9 as amended by the step-0 audit of 2026-10-14 (frozen §9 hash in the results file §1). Written
2026-10-14 by the long-path AI session that audited the case, after the freeze and before any reading. Run from a copy on the node,
`~/stage4-harness-run/cms/`; compare `md5sum` with this folder before run 1. Logs go to `~/stage4-logs/cms/<run>/`
(`STAGE4_LOGROOT` overrides it for shakedowns).

| File | Tier | What it does |
|---|---|---|
| `CacheableMutationSizeTest.java` | unit | 9e unit step 2 in one JVM per value (`-Dcassandra.cacheable_mutation_size_limit_bytes=<L> -Dstage4.expect_limit=<L>`): setup (version, slot ordinal, `isThreadAllocatedMemorySupported()`), read-back of the private field and `getLong()`, calibration of *p\** (amended start *L* − 1 − *k*₁ − *s*, ≤ 64 steps), the serialize site (slot class and copy length, *Δ* per size, scratch capacity), the receive site (wire bytes *W* deserialized; slot null or a copy equal to *W*; slot after a `serializedSize` call), the tee alone, and the idle control. Package `org.apache.cassandra.db` (reads `Mutation.cachedSerializations`, `Mutation.CACHEABLE_MUTATION_SIZE_LIMIT`, `CachedSerialization.serialized` and `DataOutputBuffer.capacity()` by reflection). Prints `STAGE4 check <name> <expected> <actual> ok\|MISMATCH` for each prediction and `STAGE4 record …` for the scratch capacity (recorded, not concluded); fails at the end on any mismatch. |
| `unit-run.sh [upstream\|harness\|all] [values…]` | unit | The upstream `TeeDataInputPlusTest`, then the harness test at 100000, 1000000, 4000000, 1, 0 (one `ant testsome` each); one summary line per JVM. Output `<logroot>/unit/<L>.out`. |
| `cache-trace.btm` | cluster | Byteman observation rules, keyspaces `ks0` and `ks1`: `serialize T=… cached=<class> ks=… pk=… v=…` at `Mutation$MutationSerializer.serialization()` line 463 (the store into the slot), and `deserialize cached=<!limitReached> teeLen=… ks=… pk=… v=…` at `deserialize(DataInputPlus, int, Flag)` line 518. To `stage4.byteman.out`. |
| `hold.btm` | cluster | The trigger: at the entry of `Keyspace.applyInternal()` for keyspace `ks1`, a `held ks=ks1 pk=…` line to `stage4.hold.out` and `delay(stage4.hold.ms)`. |
| `make-node-yaml.sh <label>` | cluster | Rebuilds `conf/cassandra.yaml` from the tag with the 9b hold-fixed settings: batch commit-log sync (period removed), `write_request_timeout: 120000ms`, `native_transport_timeout: 180000ms` (amended). The knob is a JVM property, so the yaml is the same at every value. |
| `send-mutation.py` | cluster | Bundled driver, protocol 4, 180 s timeout, CL ONE, `FallthroughRetryPolicy`: `probe`, `insert [--ks ks0\|ks1] <pk> <bytes>`, `many [--ks …] <first-pk> <n> <bytes>` (*n* inserts at once with `execute_async`), `readback`. Table `ks1.t` or `ks0.ctl`. One `OK`/`ERR <class>` line with JSON. |
| `histo.sh <pid> <out>` | cluster | `jcmd <pid> GC.class_histogram` (live objects: a full collection first) to `<out>`, then one line with the `[B` row and the live instances and bytes of `Mutation$CachedSerialization`, `Mutation$SizeOnlyCacheableSerialization` and `Mutation`. |
| `cluster-run.py` | cluster | Modes `instrument` (9e "Instrument check" (i)–(vi) at 1,000,000), `value <L>` (Phase 1: start, property read-back with `jcmd VM.system_properties`, schema `ks1.t` + `ks0.ctl`, idle pair, the control write, 8 × 90,000 + 8 × 500,000 + 8 × 2,000,000 held, histograms 5 s and 15 s after the 24th `held` line, release; `kill -9`; Phase 2: restart without a wipe, replay held, histograms, release after `UN`), `compare` (the `[B` excesses over *L* = 1, *S*_B, dose-response, from every value's `histo.csv`), `down`. `EXPECTED:` lines in `summary.txt`; `histo.csv`, `writers-p1.txt`, `hold-p<n>.txt`, `trace-p<n>.txt`, raw `histo-p<n>-<label>.txt`, `system.p1.log`/`system.end.log`, `session.log`. Stops at a failed instrument, control or set-up check; node stopped and yaml restored on any exit. |

**Readings rules encoded in `cluster-run.py`** (from §9a; recorded here so the self-check can re-derive them):

- A Phase 1 count "held − idle = predicted" holds when the predicted value lies between the two differences against the idle pair (the
  idle spread is the tolerance; 9a "the spread between two histograms of the same quiet node … is their tolerance").
- Phase 2 counts are held − the after-replay histogram (9a), with the Phase 1 idle spread as the tolerance; Phase 2's release is read
  against Phase 1's idle pair (amended 9a "Release").
- `[B` excesses (`compare`): value *L* − reference *L* = 1 in the same phase and the same histogram slot (held-1 with held-1, held-2
  with held-2); predicted 8 × Σ over cached sizes of the array's size (*T* + 16, rounded up to 8); tolerance max(10 %, 3 *S*_B); read
  only where the prediction exceeds 3 *S*_B, else recorded.
- Unit idle control: "unchanged" is read against the meter's own cost (two back-to-back `getThreadAllocatedBytes` reads; on JDK 11
  each read allocates its own small arrays).
