# max_hints_size_per_host — verification solution  <!-- file: cases/max_hints_size_per_host-shouldHint-maxHintsSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`StorageProxy.java:2489`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2489) (`if (maxHintsSize > 0)`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-opus-5-5 (Claude Code CLI, stage-3 autonomous agent, Band D triage), 2026-10-26 |
| Estimate | `positive`: once the on-disk size of a dead host's hint files exceeds the cap, `shouldHint` returns false and the coordinator stops creating hints for that host, so the host's hint files stop growing. It is a soft cap: the size is only checked when a hint is admitted, and it only counts files that have already been flushed, so usage overshoots by up to about one flush period's worth of hints (plus whatever is still in the hint buffers). |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `max_hints_size_per_host`, a configuration entry. It is declared at [`Config.java:448`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L448) as `volatile DataStorageSpec.LongBytesBound max_hints_size_per_host = new DataStorageSpec.LongBytesBound("0B"); // 0 means disabled`. Unit: a data size, read in bytes through `DatabaseDescriptor.getMaxHintsSizePerHost()` ([`DatabaseDescriptor.java:3601-3603`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3601-L3603)). The default is 0, which disables the check. The commented default in `conf/cassandra.yaml:108-111` is `# max_hints_size_per_host: 0MiB`. Ways to set it: the yaml key, which needs a restart, or JMX at `org.apache.cassandra.db:type=StorageProxy`, attribute `MaxHintsSizePerHostInMiB` ([`StorageProxy.java:2413-2421`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2413-L2421), [`StorageProxyMBean.java:35-36`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxyMBean.java#L35-L36), [`DatabaseDescriptor.java:3590-3593`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3590-L3593)). A JMX change takes effect at once because the field is volatile and is read on every call.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** It caps **disk**: the total size of the hint files that this coordinator keeps for one target host. The check compares `HintsService.instance.getTotalHintsSize(hostId)` (`HintsService.java:253-259`) with the limit. That call returns `HintsStore.getTotalFileSize()` (`HintsStore.java:260-271`), the sum of `descriptor.hintsFileSize()` over the dispatch queue, the corrupted files and the file currently being written.

**A3. Mechanism.**
1. Write path: `StorageProxy.performWrite`/`sendToHintedReplicas` loops over the contacts. For a replica that is not alive it calls `shouldHint(destination)` ([`StorageProxy.java:1553`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1553)). Only if that returns true is the replica added to `endpointsToHint`, which is then passed to `submitHint` (`:1563-1564`). The other gated callers are [`AbstractWriteResponseHandler.java:309`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/AbstractWriteResponseHandler.java#L309) (hint on write failure or timeout), Paxos commit ([`StorageProxy.java:818`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L818), `paxos/PaxosCommit.java:230`) and `HintsService.writeForAllReplicas` ([`HintsService.java:198`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L198)).
2. In `shouldHint(replica, true)` ([`StorageProxy.java:2442-2502`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2442-L2502)), the cap is checked after the hinted-handoff-enabled, DC, ring-membership and hint-window checks. At `:2488` it reads `maxHintsSize`. At `:2489`, if the value is > 0, it reads the actual size (`:2491`), and if `actualTotalHintsSize > maxHintsSize` (`:2492`) it traces the reason and returns false (`:2494-2496`).
3. Outcome at the limit: no hint is created for that host. The write still succeeds or fails on its consistency level alone, and the missed write has to be repaired later. Nothing is deleted.
4. How fresh the operand is: `hintsFileSize` is cached in the descriptor ([`HintsDescriptor.java:230-243`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsDescriptor.java#L230-L243)). It is set to the header length when the writer opens ([`HintsWriter.java:84`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriter.java#L84)) and updated only when a write session closes ([`HintsWriter.java:269-275`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriter.java#L269-L275)), that is, once per buffer flush. Flushes happen every `hints_flush_period` (default 10000ms, `conf/cassandra.yaml:102`) or when a hint buffer fills. A buffer is max(2 × max_mutation_size, 32 MiB) (`HintsService.java:79,110`), and there are at most `cassandra.MAX_HINT_BUFFERS` = 3 buffers ([`HintsBufferPool.java:41`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L41), [`CassandraRelevantProperties.java:351`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L351)).
5. Overshoot: every hint admitted between two flushes passes the check against a stale size. The expected overshoot is therefore about (hint bytes per second for that host) × `hints_flush_period`, and at most about the contents of the buffers (≤ 3 × 32 MiB at defaults). The check is also strictly `>`, so the size has to pass the cap before it binds.
6. Bypasses:
   - Batchlog replay writes hints directly with `HintsService.instance.write` and never calls `shouldHint` (`batchlog/BatchlogManager.java:443` and `:499`).
   - Hints received from a decommissioning peer go through [`HintVerbHandler.java:87`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintVerbHandler.java#L87), which also writes directly. (`:94` goes through `writeForAllReplicas`, which is gated.)
   - Hints already accepted into the buffer are always written.

**A4. Other consumers.** Other things in the hints directory are outside this cap:
- hints for other hosts (the cap is per host, so the total on disk scales with the number of dead hosts);
- `max_hints_file_size` (`conf/cassandra.yaml:106`), which only sets when a file rolls over;
- the in-memory hint buffers, off-heap through `HintsBuffer.create`, up to 3 × 32 MiB;
- expired or orphaned files, which are kept when `auto_hints_cleanup_enabled: false`.

The commit log, data files and the batchlog table are separate.

**A5. Evidence beyond the source.**
- `test/unit/org/apache/cassandra/service/StorageProxyTest.java:100-120`: Byteman forces `getTotalHintsSize` to return 2 MiB, the limit is set to 1 MiB, and the test asserts that `shouldHint` returns false.
- `test/distributed/org/apache/cassandra/distributed/test/HintsMaxSizeTest.java:47-115`: two nodes, `max_hints_size_per_host: 2MiB`, 70000 inserts while node2 is down. The test asserts that the per-host size is < 4,000,000 bytes, and its comment notes "there might be small overflow".
- `conf/cassandra.yaml:108-111`: the documented semantics.

## B. Verification solution

**B1. Claim under test.** With `max_hints_size_per_host = C` > 0 and one target host down, the on-disk size of that host's hint files on the coordinator stops growing at C plus a bounded overshoot (≤ one flush period of hint traffic plus ≤ 3 hint buffers). With C = 0 it grows in proportion to the write volume.

### B2. Unit tier

**B2a. Environment and build.**
1. Clone the tag to local disk: `git clone --branch cassandra-5.0.9 --depth 1 /path/to/cassandra-src /local/c509 && cd /local/c509`.
2. Build with JDK 11: `ant jar build-test`.
3. Put the test at `test/unit/org/apache/cassandra/hints/HintsSizeCapUnitTest.java`, in the local clone only.
4. Run it with `ant testsome -Dtest.name=org.apache.cassandra.hints.HintsSizeCapUnitTest`. The default test JVM options are fine, and the hints directory goes under `build/test/cassandra/hints`, which is local.

**Amendment 2026-10-27 (step-0 audit) — B2a, this machine.** Clone `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run48` (`W=~/Library/Caches/stage4`, commit `b5f2a54210`), built with `ant -Dlocal.repository=$W/m2 build-test` (JDK 11.0.32.1); no `/local` path and no `--depth 1`. The test is copied into the clone only for the run and removed afterwards; it runs with `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.hints.HintsSizeCapUnitTest`. Driver: `harness/max_hints_size_per_host-shouldHint-maxHintsSize--autonomous/unit-run.sh`. Reason: the filed paths do not exist on this machine.

**B2b. Knobs.** `DatabaseDescriptor.setMaxHintsSizePerHostInMiB(C)` with C ∈ {0 (control, disabled), 1, 4, 16} MiB. Small values keep the test fast, and a 4× spread separates the plateaus clearly. Set `DatabaseDescriptor.setMaxHintsFileSize`, if it is accessible, otherwise leave the default; the per-host sum does not depend on rollover.

**Amendment 2026-10-27 (step-0 audit) — B2b, file size.** `max_hints_file_size` is left at its default, 128 MiB (the unit yaml `test/conf/cassandra.yaml` does not set it; `Config.java:447`). The largest run (C = 0) writes 42 + 20,000·h bytes with h ≈ 4.1 KB, about 80 MiB, so no run rolls a file and each host has exactly one file. C values unchanged. Reason: "if it is accessible" left the setting open.

**B2c. Workload.** The test class extends `CQLTester`, so the schema and `HintsService` are initialised.
1. Register a fake dead endpoint the same way `StorageProxyTest.shouldHintTest` does (`StorageProxyTest.java:135-150`): `updateHostId(uuid, 192.168.1.1)` and `Gossiper.markDead`.
2. Build a `Mutation` for a table `t(k int PRIMARY KEY, v blob)` with a 4 KiB blob value.
3. Loop i = 0 … 20,000 (about 80 MiB of hints if every one is admitted, which is well past 16 MiB):
   - copy production behaviour exactly: `if (StorageProxy.shouldHint(replica)) StorageProxy.submitHint(mutation_i, replica, null);`
   - every 256 iterations, wait until `StorageProxy.instance.getHintsInProgress() == 0`, then call `HintsService.instance.flushAndFsyncBlockingly(List.of(uuid))`. This simulates the flush period: 256 × 4 KiB ≈ 1 MiB per "period".

**Amendment 2026-10-27 (step-0 audit) — B2c, exact loop, the wait, and one endpoint per C.**
(i) `StorageProxy.instance.getHintsInProgress()` does not exist at the tag; the wait is `StorageMetrics.totalHintsInProgress.getCount() == 0` (`StorageMetrics.java:45`, incremented in `StorageProxy.submitHint` `:2824`, decremented when the hint runnable ends `:2729`), polled every 1 ms, at most 60 s.
(ii) N = 20,000 iterations exactly (i = 0 … 19,999), key i (int), value a fixed 4,096-byte blob, built with `RowUpdateBuilder` at the current time. The wait and `flushAndFsyncBlockingly(List.of(uuid))` run after every iteration with (i + 1) mod 256 = 0 and once more after the last iteration (79 batches of 256 and one of 32).
(iii) **Each C gets its own fake dead endpoint and host id** (C = 0, 1, 4, 16 → `192.168.1.10`, `.11`, `.12`, `.13`, each with a fresh random UUID, registered and marked dead as in `StorageProxyTest.java:135-150`). Reason: `HintsService.deleteAllHints()` → `HintsCatalog.deleteAllHints` → `HintsStore.deleteAllHints()` (`HintsStore.java:167-181`, `HintsCatalog.java:118-133`: "Will not delete the files that are currently being dispatched, or written to") does not delete the file the open writer holds, and nothing in the loop closes the writer, so with one host id the C = 0 run's ~80 MiB file would stay in the operand and every later C would reject from its first hint. `deleteAllHints()` is still called before each C (B2h).
(iv) The replica is `ReplicaUtils.full(endpoint)`; production behaviour is copied exactly: `if (StorageProxy.shouldHint(replica)) StorageProxy.submitHint(mutation, replica, null)`.

**B2d. Observables and instruments.**
- The operand `HintsService.instance.getTotalHintsSize(uuid)`, recorded after each flush.
- The count of admitted vs rejected hints.
- An independent disk reading: the sum of `File.length()` over `hints_directory/<uuid>-*.hints`.

The content of the in-memory buffer between flushes cannot be observed directly.

**Amendment 2026-10-27 (step-0 audit) — B2d, exact sizes and the disallow evidence.** The test also prints, from the code's own objects: h = `Hint.serializer.serializedSize(Hint.create(m, now), MessagingService.current_version)` + `HintsBuffer.ENTRY_OVERHEAD_SIZE` (12) for every mutation (min and max; the buffer serializes at `MessagingService.current_version`, `HintsBufferPool.java:61`, `HintsBuffer.java:248`, and each buffered entry is the hint plus 12 bytes); the file header is 42 bytes (`HintsDescriptor.serialize`, `:381-405`: version 4 + timestamp 8 + host id 16 + params length 4 + its CRC 4 + params `{}` 2 + CRC 4; no hints compression or encryption in the unit yaml); and, for each C, the operand at the first rejected hint and its index. The admitted and rejected counts count `shouldHint` returning true and false. Reason: B2f and B2g need the exact per-hint and header sizes, and B2g needs direct evidence that the disallow branch fired.

**B2e. Procedure.**
1. For each C: call `HintsService.instance.deleteAllHints()`, set C, run the loop, and print a CSV row `C, i, operand, dirBytes, admitted, rejected` per flush.
2. At the end, assert `final dirBytes ≤ C·2^20 + 1 MiB + one file header`.
3. Restore the setting and remove the endpoint in `finally`.

**Amendment 2026-10-27 (step-0 audit) — B2e, exact bounds.** The end-of-run assertion "≤ C·2^20 + 1 MiB + one file header" is replaced: a batch is 256 hints of h > 4,096 bytes, more than 1 MiB, so the source gives final dirBytes ≤ C·2^20 + 256·h (the operand, header included, is ≤ C·2^20 at the start of the last admitted batch, and that batch adds at most 256·h). The test prints the values and records PASS/FAIL per relation; it does not stop at a failed relation. Reason: the filed bound is smaller than one batch.

**B2f. Predictions.**
- C = 0: all 20,000 hints are admitted, and operand ≈ dirBytes ≈ 20,000 × (4 KiB + per-hint overhead), about 80–85 MiB, growing linearly.
- C = 1, 4, 16 MiB: admission stops at the first check after the operand passes C. The final operand lies in (C, C + ~1 MiB], about 1–2, 4–5 and 16–17 MiB. Rejected = 20,000 − admitted, and admitted ≈ C / 4 KiB + ≤ 256.
- operand = dirBytes (to within headers) in every case.

**Amendment 2026-10-27 (step-0 audit) — B2f, exact form.** (a) C = 0: admitted = 20,000, rejected = 0, final operand = final dirBytes = 42 + 20,000·h (the filed "80–85 MiB" is this figure, about 79–80 MiB for h ≈ 4.1–4.2 KB). (b) C = 1, 4, 16: rejected ≥ 1; the operand at the first rejection is > C·2^20; C·2^20 < final operand ≤ C·2^20 + 256·h; admitted + rejected = 20,000. (c) Every run: after every flush, operand = dirBytes exactly, and final operand = 42 + admitted·h exactly (one file, nothing pending). (d) The final values increase with C: final(1) < final(4) < final(16) < final(0). Reason: B2f's ranges were approximate and in mixed units.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Plateau at C + ≤ 1 flush batch for each C > 0, linear growth for C = 0 | claim holds |
| Size keeps growing past C + 1 batch for some C > 0 | claim wrong: the cap does not bind on this path |
| operand ≠ dirBytes by more than headers | the operand does not track the real disk usage (stale cache), so the claim is wrong in its mechanism |
| C = 0 control also plateaus | the workload or setup is broken, so the result is inconclusive |
| operand never reaches C | workload too small, so the result is inconclusive |

**Amendment 2026-10-27 (step-0 audit) — B2g, row 1 made exact, rows added; the five rows above are unchanged.** Row 1 ("claim holds") needs every amended B2f item (a)–(d): the plateau bound for each C > 0 and the direct disallow evidence (rejected ≥ 1 with the operand at the first rejection > C·2^20), with the C = 0 control admitting all 20,000. Added rows: *rejected ≥ 1 for some C > 0 while the operand at the first rejection is ≤ C·2^20* → something other than the size branch refused the hint, so the result is inconclusive; *C = 0 rejects any hint* → another `shouldHint` branch fires, inconclusive; *every relation holds except (c), and dirBytes > operand* → the cap binds on the counted size but the real disk usage exceeds it (counter capped, real resource grows): claim wrong in its mechanism (row 3). Reason: the rows did not require disallow evidence or name these outcomes.

**B2h. Controls.**
- The C = 0 run is the positive control: the same workload grows usage when no cap binds.
- `deleteAllHints()` between runs.
- The disk is read independently of the operand.
- Dispatch is irrelevant because the endpoint is fake and dead. Call `HintsService.instance.pauseDispatch()` to be sure.

**Amendment 2026-10-27 (step-0 audit) — B2h.** `pauseDispatch()` is called once before the first C; `deleteAllHints()` before each C; each C's endpoint is removed from the token metadata and its store excised (`HintsService.excise`, which closes the writer and deletes its files) in `finally`. Reason: cleanup order was not exact.

### B3. Cluster tier

**B3a. Environment and build.**
- Nodes: two Linux nodes, n1 and n2 (or two loopback addresses, 127.0.0.1 and 127.0.0.2, on one host, each with its own conf directory, data/commitlog/hints directories on local disk and its own JMX port: 7199 and 7299).
- Build: `ant jar` in the local clone.
- `cassandra.yaml` on both nodes: `hinted_handoff_enabled: true`, `hints_flush_period: 1000ms`, `max_hints_file_size: 8MiB`, `max_hint_window: 3h`, `auto_hints_cleanup_enabled: false`, `hints_directory: /local/cN/hints`, `commitlog_directory`/`data_file_directories` on local disk, and a single-token setup (`num_tokens: 1` or default 16).
- JVM: `-Xms2G -Xmx2G` (conf/jvm11-server.options / `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`).
- Local disk needed: ≥ 2 GB free on n1.

**Amendment 2026-10-27 (step-0 audit) — B3a, this machine.** One macOS host (10 cores, 32 GiB, APFS SSD) with loopback aliases `127.0.0.1` and `127.0.0.2`. Both nodes run from the clone `$W/cassandra-run48` (built with `build-test`, which builds the jar and stress; no separate `ant jar`), each with its own `CASSANDRA_CONF` and directories under `$W/node-mhs48/n1|n2` (data, commitlog, hints, saved_caches, cdc_raw, logs); n1 JMX 7199, n2 JMX 7299; `listen_address`/`rpc_address` 127.0.0.N; `auto_bootstrap: false` on both (zero-copy streaming fails on this host); `num_tokens` left at the default 16 (RF = 2 on two nodes, so both nodes replicate every key either way); the other yaml lines as filed (`hinted_handoff_enabled: true`, `hints_flush_period: 1000ms`, `max_hints_file_size: 8MiB`, `max_hint_window: 3h`, `auto_hints_cleanup_enabled: false`). `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` on both. Nodes start as tracked background processes (`bin/cassandra -f`). Driver: `harness/max_hints_size_per_host-shouldHint-maxHintsSize--autonomous/cluster-run.sh`. Reason: the filed paths and build do not exist on this machine.

**B3b. Knobs.** `max_hints_size_per_host` on n1 ∈ {0 (positive control), 32MiB, 128MiB, 512MiB}. These values are well above one flush period of traffic, so the plateau separates clearly from the overshoot. Set each value in n1's yaml and restart n1, or set it live with `bin/nodetool -p 7199 sjk mx -b org.apache.cassandra.db:type=StorageProxy -ms -f MaxHintsSizePerHostInMiB -v 32`. Confirm with `-mg`.

**Amendment 2026-10-27 (step-0 audit) — B3b, how the knob is set and read.** Each round starts from fresh node directories (B3e step 7, "wipe and recreate"), so C is written into n1's yaml (`max_hints_size_per_host: <C>MiB`, `0MiB` for the control) before n1 starts, and read back over JMX (`org.apache.cassandra.db:type=StorageProxy`, attribute `MaxHintsSizePerHostInMiB`) with the harness JMX client `HintsSizeSampler.java` (`nodetool sjk mx` exits 0 on failure on this host). Values unchanged: 0, 32, 128, 512 MiB. Reason: the filed `sjk` command cannot be trusted here, and one route had to be chosen.

**B3c. Workload.**
1. Create the keyspace with RF=2: `CREATE KEYSPACE ks WITH replication={'class':'SimpleStrategy','replication_factor':2}`.
2. Stop n2 with `bin/nodetool -p 7299 stopdaemon`.
3. On n1, run `tools/bin/cassandra-stress write n=1000000 cl=ONE -schema keyspace=ks -col size=FIXED(1024) n=FIXED(1) -rate threads=32 -node 127.0.0.1`. This makes about 1 KiB per hint plus key and overhead, about 1.1 GB of hints for n2 if every write is hinted (≥ 2× the largest cap). The run takes about 5–15 minutes, well inside the 3h window.

**Amendment 2026-10-27 (step-0 audit) — B3c, exact commands.** Step 1 is run with `bin/cqlsh 127.0.0.1` while both nodes are UN. Step 3's stress command gets `no-warmup`: without it stress first runs min(50,000, n/4) × nodes = 50,000 extra writes (`StressAction.java:105-110`), which are hinted too and are not in the filed arithmetic (n = 1,000,000 writes ≈ 1.1 GB of hints). The table `ks.standard1` is created by stress itself (`CREATE TABLE IF NOT EXISTS`, `SettingsSchema.java:127`; the keyspace keeps RF = 2 because stress uses `CREATE KEYSPACE IF NOT EXISTS`, `:97`). Full command: `tools/bin/cassandra-stress write n=1000000 no-warmup cl=ONE -schema keyspace=ks -col 'size=FIXED(1024)' 'n=FIXED(1)' -rate threads=32 -node 127.0.0.1`. Reason: the warm-up changed the workload size.

**B3d. Observables and instruments.**
- Every 5 s: `du -cb /local/c1/hints/<n2-hostid>-*.hints | tail -1`. Get the host id from `nodetool -p 7199 status`.
- `nodetool -p 7199 listpendinghints`.
- Hints created: `nodetool -p 7199 sjk mx -mg -b org.apache.cassandra.metrics:type=Storage,name=TotalHints -f Count`.
- The trace message "has reached to the max hints size" in `system_traces`, if `nodetool settraceprobability 0.001` is on.
- `df` of the local disk.

The in-memory buffer contents are not observable.

**Amendment 2026-10-27 (step-0 audit) — B3d, instruments on this machine.** (i) `du -cb` is GNU-only; the sampler sums the file lengths (apparent bytes, what `du -cb` prints and what the operand counts) of `$W/node-mhs48/n1/hints/<n2-hostid>-*.hints` every 5 s, with the epoch time, the JMX counters `org.apache.cassandra.metrics:type=Storage,name=TotalHints` (Count) and `org.apache.cassandra.metrics:type=HintsService,name=Hints_created-…127.0.0.2…` (Count; ~~`type=HintedHandOffManager`~~ — see the runbook fix below), and `MaxHintsSizePerHostInMiB`. The host id is read from `nodetool -p 7199 status` while both nodes are UN. (ii) `nodetool -p 7199 settraceprobability 0.001` is **on in every round** (set after n2 is DN, before stress), and after the final reading the trace events are exported with `bin/cqlsh 127.0.0.1 -e "COPY system_traces.events (session_id, event_id, activity) TO '<file>'"`; the count of events containing `reached to the max hints size` (`StorageProxy.java:2494`) is the direct evidence of the disallow branch. (iii) `listpendinghints` and `df` once before and once after stress. Reason: `du -cb` does not exist here, and the trace was optional while B3g needs disallow evidence.

**Runbook fix 2026-10-27 (stage 4, found by the harness shakedown before run 1) — B3d (i).** The per-host created-hints counter is registered under `type=HintsService` (`HintedHandoffMetrics.java:43,53`: `new DefaultNameFactory("HintsService")`, name `Hints_created-` + the address with `:` replaced by `.`), not `type=HintedHandOffManager` as the audit amendment above said; the sampler reads the `HintsService` name. This observable is in no B3f relation or B3g row; B3f and B3g are unchanged.

**B3e. Procedure.**
1. For each C: start both nodes and wait until `nodetool status` shows UN UN.
2. Create the schema.
3. Stop n2.
4. Run `nodetool truncatehints` on n1 and confirm that du = 0.
5. Set C, start the du sampler, and run stress.
6. After stress ends, wait 5 s (more than the flush period) and take the final du.
7. Then run `nodetool truncatehints`, restart n2 for the next round (or wipe and recreate).

**Amendment 2026-10-27 (step-0 audit) — B3e, exact sequence.** Per round: create fresh node directories with C in n1's yaml; start n1, then n2; wait for UN UN; step 2; record n2's host id; stop n2 with `nodetool -p 7299 stopdaemon`; wait for `DN 127.0.0.2` on n1; step 4; read C back over JMX; set the trace probability; start the sampler; run stress; after stress ends wait 5 s, take the final reading, stop the sampler; export the trace events; `nodetool truncatehints`; stop n1; delete the round's node directories (the "wipe and recreate" option of step 7). The round order is 0, 32, 128, 512. Reason: the order and the reset were not exact.

**B3f. Predictions.**
- C = 0: du grows roughly linearly to about 1.0–1.2 GB.
- C > 0: du rises linearly and then flattens at C + overshoot. The overshoot is at most the stress hint rate × 1 s plus ≤ 3 × 32 MiB, so with a rate of a few tens of MB/s, the final du ≤ C + 100 MiB and typically C + a few MiB. Expected final values: about 32–130 MiB, 128–230 MiB and 512–610 MiB respectively.
- TotalHints stops increasing once the plateau is reached.

**Amendment 2026-10-27 (step-0 audit) — B3f, exact form.** du_final = the sum of n2's file lengths 5 s after stress ends. (a) C = 0: du_final ∈ [1.0·10^9, 1.2·10^9] bytes ("about 1.0–1.2 GB"; 1,000,000 hinted writes of about 1.1 KB, plus the hints of the traced sessions' `system_traces` writes, RF = 2, which are gated the same way), TotalHints_final ≥ 1,000,000, and 0 trace events with the size message. (b) C = 32, 128, 512 MiB: C·2^20 < du_final ≤ C·2^20 + 100·2^20 (the overshoot bound of A3.5: at most the 3 × 32 MiB of buffers, `HintsService.java:79,110`, `HintsBufferPool.java:41`, plus the hints in flight, at most about `maxHintsInProgress` = 128 × 10 processors = 1,280 hints ≈ 1.4 MB before `checkHintOverload` refuses, `StorageProxy.java:202,1592`; the check is strict `>` so du_final passes C); TotalHints_final < 1,000,000; at least one trace event with the size message. (c) du_final increases with C: du(32) < du(128) < du(512) < du(0). Reason: B3f's values were approximate and "TotalHints stops increasing" had no test.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| du plateaus near C (overshoot ≤ 100 MiB) for every C > 0 while C = 0 grows to ~1 GB | claim confirmed |
| du for some C > 0 grows past C + 100 MiB and keeps tracking the write volume | claim refuted |
| plateau value does not scale with C | something else bounds the hints, such as the hint window or stress errors, so the result is inconclusive |
| C = 0 control does not grow | n2 is not seen as down or hints are disabled, so the result is inconclusive |

**Amendment 2026-10-27 (step-0 audit) — B3g, row 1 made exact, rows added; the four rows above are unchanged.** Row 1 ("claim confirmed") needs every amended B3f item (a)–(c), including the disallow evidence (size-message trace events ≥ 1 and TotalHints_final < 1,000,000 for each C > 0). Added rows: *du_final ≤ C·2^20 for some C > 0* → the limit was never reached, inconclusive; *du_final within the bound for every C > 0 but no size-message trace event in some round* → the plateau has no direct disallow evidence, not confirmed; *n2 not DN during a round, or stress errors > 0* → invalid round. Reason: the rows did not require disallow evidence or name these outcomes.

**B3h. Controls.**
- The C = 0 run with the same workload is the positive control.
- Each run starts from truncated hints.
- n2 stays down for the whole run, and `nodetool status` shows DN.
- Plain writes only, no batches, so the batchlog bypass (`BatchlogManager.java:443,499`) is excluded.
- Only n2's host-id files are measured.

**Amendment 2026-10-27 (step-0 audit) — B3h.** n2 is checked DN on n1 before stress and again after the final reading (`nodetool -p 7199 status`). Reason: the second check was implied only.

**B4. Risks and cleanup.**
- Hints and data go only on local disk. Check `df` before each run, because the C = 0 run writes about 1.2 GB.
- After the runs: `nodetool truncatehints`, `nodetool stopdaemon` on both nodes, `pgrep -f CassandraDaemon` must show nothing, `pgrep -f cassandra-stress` must show nothing, and `rm -rf /local/c1 /local/c2`.
- Unit tier: `ant clean` in the local clone, or delete the clone.
- Never write into the shared source tree.

**Amendment 2026-10-27 (step-0 audit) — B4, this machine.** Node files are under `$W/node-mhs48` (removed after each round and at the end); after the runs `pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon'` and `pgrep -f 'org.apache.cassandra.stress.Stress'` must show nothing; the copied unit test is removed from the clone so `git status` of `$W/cassandra-run48` is clean. Reason: the filed paths do not exist on this machine.

## C. Sources read

- src/java/org/apache/cassandra/service/StorageProxy.java (lines 1490-1600, 2405-2502, 2700-2830)
- src/java/org/apache/cassandra/config/Config.java:448
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java:3590-3603
- src/java/org/apache/cassandra/service/StorageProxyMBean.java:35-36
- src/java/org/apache/cassandra/hints/HintsService.java (79-111, 161-259)
- src/java/org/apache/cassandra/hints/HintsStore.java (255-335)
- src/java/org/apache/cassandra/hints/HintsDescriptor.java:230-243
- src/java/org/apache/cassandra/hints/HintsWriter.java (75-90, 260-280)
- src/java/org/apache/cassandra/hints/HintsWriteExecutor.java (120-250)
- src/java/org/apache/cassandra/hints/HintsBufferPool.java
- src/java/org/apache/cassandra/batchlog/BatchlogManager.java (425-500)
- src/java/org/apache/cassandra/service/AbstractWriteResponseHandler.java:309
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java:351
- conf/cassandra.yaml (60-125)
- test/unit/org/apache/cassandra/service/StorageProxyTest.java
- test/distributed/org/apache/cassandra/distributed/test/HintsMaxSizeTest.java

## D. Stage-4 feedback

**2026-10-27, stage 4 (advisor's machine, Claude Opus 5.5): unit Confirmed — caps; cluster Confirmed — caps.** Run 1 used sha256 `5975b243…37a2`: seventeen step-0 amendments plus one runbook fix (B3d (i), the `Hints_created` bean is `type=HintsService`; found by the shakedown, in no relation), all before any reading. Results: [`../../stage4-runtime-verification/results/max_hints_size_per_host-shouldHint-maxHintsSize--autonomous.md`](../../stage4-runtime-verification/results/max_hints_size_per_host-shouldHint-maxHintsSize--autonomous.md).
- Unit (B2g row 1): h = 4,161 B per hint, header 42 B. C = 0 admitted all 20,000 (83,220,042 B). At C = 1, 4, 16 MiB, admission stopped at the first check after the operand passed C (256, 1,024, 4,096 admitted); finals were 1,065,258, 4,260,906 and 17,043,498 B, each in (C, C + 256·h]. The operand equalled the file length after every flush.
- Cluster (B3g row 1): the same 1,000,000 writes with n2 down gave 1,098,314,487 B of hints uncapped. At 32, 128 and 512 MiB the files stopped at 54.90, 146.80 and 556.85 MiB, an overshoot of 22.9, 18.8 and 44.9 MiB (bound 100 MiB). TotalHints was 52,674, 140,871 and 534,356, and 950, 857 and 456 traced writes carried "Not hinting … reached to the max hints size". The first refusals saw an operand just above C, and the files kept growing until the buffered hints were flushed: the stale-operand overshoot of A3.5.
- For stage 3: `HintsService.deleteAllHints()` (and `nodetool truncatehints`) does not delete the file the open writer holds (`HintsCatalog.java:126`, `HintsStore.java:167-181`), so a design that reuses one host id across values must close the writer or use a new host id. `StorageProxy.getHintsInProgress()` does not exist at the tag. A batch of 256 hints of a 4 KiB value is more than 1 MiB, so B2e's bound was one batch too small. Stress needs `no-warmup` for its n to be the write count.
