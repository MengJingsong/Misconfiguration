# dfs.qjournal.queued-edits.limit.mb — verification solution  <!-- file: cases/dfs.qjournal.queued-edits.limit.mb-reserveQueueSpace-queueSizeLimitBytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`IPCLoggerChannel.java:451`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/qjournal/client/IPCLoggerChannel.java#L451), in `IPCLoggerChannel.reserveQueueSpace(int)` (the if statement is the enforcement point itself) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive`: the key sets the per-JournalNode limit on edit bytes that the NameNode's `IPCLoggerChannel` may hold queued for one JournalNode. Each queued batch is a `byte[]` on the NameNode heap that its executor task keeps reachable. Once the counter would go over the limit, new batches are refused, so the NameNode heap pinned for a lagging JournalNode stays at or below the limit, with one documented exception: a single batch may exceed the limit when the queue is empty. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- Name: `dfs.qjournal.queued-edits.limit.mb` (exact key, no placeholder).
- Kind: configuration key (HDFS).
- First declared: [`DFSConfigKeys.java:1477`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java#L1477) (`DFS_QJOURNAL_QUEUE_SIZE_LIMIT_KEY`). The default constant is `DFS_QJOURNAL_QUEUE_SIZE_LIMIT_DEFAULT = 10` at `DFSConfigKeys.java:1478`. The `hdfs-default.xml:5765-5770` entry also has value `10` ("Queue size in MB for quorum journal edits"). The Java constant and the XML agree, so the effective default is 10.
- Unit: MiB, read as an `int`. It is converted to bytes once in the `IPCLoggerChannel` constructor, `queueSizeLimitBytes = 1024 * 1024 * conf.getInt(KEY, DEFAULT)` (`IPCLoggerChannel.java:171-173`), into the `final int queueSizeLimitBytes` field (`IPCLoggerChannel.java:138`). The javadoc at `:132-137` states the purpose: "keeps the writer from hitting OOME if one of the loggers starts responding really slowly".
- Arithmetic edge: the multiplication is in `int`. A value of 2048 or more overflows, because 2048·2^20 = 2^31 wraps to a negative number. A negative product makes every batch fail whenever anything is already queued. Fractions of a MiB cannot be set. A value of 0 is allowed and is used by `TestJournalNodeSync.java:80`.
- How to set it: `hdfs-site.xml` on the NameNode, which is the QJM writer. It is read once per `IPCLoggerChannel` construction. A channel is created for each JournalNode when the `QuorumJournalManager` for a `qjournal://` edits URI is built (`FSEditLog.java:306`, `FSEditLog.createJournal` at `:1878`). The key is not reconfigurable, so a change needs a NameNode restart.
- Reader: the NameNode process (active NN, or any process that writes through QJM).

**A2. What it caps.** The NameNode JVM heap held by edit-log batches that were handed to one JournalNode channel and are not yet acknowledged or failed. The quantity compared is `queuedEditsSizeBytes + size`, where `queuedEditsSizeBytes` is `IPCLoggerChannel.java:112` and `size` is `data.length` of the new batch. That is checked against `queueSizeLimitBytes`. Each batch is a freshly allocated `byte[]` (`QuorumOutputStream.flushAndSync`, `QuorumOutputStream.java:104-107`) captured by the lambda queued on the channel's single-thread executor (`IPCLoggerChannel.java:357-390`). That executor comes from `Executors.newSingleThreadExecutor` (`:243-250`), whose queue is unbounded, so this counter is the only bound on it. The limit applies to each channel. All channels share the same `byte[]` for a batch (`AsyncLoggerSet.sendEdits`, `AsyncLoggerSet.java:254-262`). The retained heap is therefore the union of the arrays still queued on any channel: at most N·limit for N JournalNodes, and in practice about the queue of the slowest channel.

**A3. Mechanism.**
1. `FSEditLog` → `QuorumOutputStream.flushAndSync` copies the ready buffer into a new `byte[]` (`QuorumOutputStream.java:104-107`). It then calls `AsyncLoggerSet.sendEdits`, which calls `IPCLoggerChannel.sendEdits` on every logger (`AsyncLoggerSet.java:254-262`). It then waits only for a write quorum, up to `dfs.qjournal.write-txns.timeout.ms` (`QuorumOutputStream.java:113`, `AsyncLoggerSet.java:124-148`). The writer therefore moves on while a minority channel is still busy, and that channel's queue grows.
2. `IPCLoggerChannel.sendEdits` calls `reserveQueueSpace(data.length)` first (`IPCLoggerChannel.java:346`).
3. The check is [`IPCLoggerChannel.java:451`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/qjournal/client/IPCLoggerChannel.java#L451): `if (queuedEditsSizeBytes + size > queueSizeLimitBytes && queuedEditsSizeBytes > 0)`.
   - True (over the limit and the queue is not empty): it logs WARN "Pending edits to … is going to exceed limit size: …, will silently drop … bytes of edits!" (`:452-454`) and throws `LoggerTooFarBehindException` (`:455`). `sendEdits` catches it and returns `Futures.immediateFailedFuture(e)` (`:347-349`). The batch is never queued for this channel, and only the caller's quorum call holds a reference to it. That logger counts as a failure in the `QuorumCall`. If a majority of loggers are refused or fail, `waitForWriteQuorum` throws (`AsyncLoggerSet.java:142-145`) and the NameNode's journal write fails.
   - False: the counter is incremented (`:457`), and the task is submitted to the single-thread executor (`:357`). When the RPC succeeds or fails, a callback calls `unreserveQueueSpace` (`:399-410`, `:460-463`). If the submit throws, the counter is decremented at once (`:392-395`).
4. Bypass or overshoot: the `queuedEditsSizeBytes > 0` clause admits any one batch when the queue is empty, even if that batch is larger than the limit. The bound is therefore queued ≤ max(limit, largest single batch). A batch is normally about `OUTPUT_BUFFER_CAPACITY_DEFAULT = 512 KiB` (`QuorumJournalManager.java:108`, `:194`; flush when `bufCurrent.size() >= initBufferSize`, `EditsDoubleBuffer.java:99-101`), plus whatever arrives before the sync. It is also bounded by `ipc.maximum.data.length` (`QuorumJournalManager.java:455-461`). With limit 0, at most one batch is queued at a time.
5. A refused batch leaves a txid gap on that JournalNode. The next accepted batch is rejected by the JN, `outOfSync=true` is set (`IPCLoggerChannel.java:363-369`), and the remaining queued tasks fail fast in `throwIfOutOfSync` (`:416-423`). This continues until the next `startLogSegment` (`:474-486`). That keeps the channel from refilling indefinitely.
6. The counter is exported as metric `QueuedEditsSize` (`IPCLoggerChannelMetrics.java:107-110`), in metrics source `IPCLoggerChannel-<ip>-<port>` (`IPCLoggerChannelMetrics.java:83-102`).

**A4. Other consumers.**
- NameNode side:
  - `EditsDoubleBuffer`: two buffers of about 512 KiB for each output stream.
  - The async edit-log pending queue `dfs.namenode.edits.asynclogging.pending.queue.size`. It defaults to 4096 ops (`DFSConfigKeys.java:427-430`) and counts operations, not bytes.
  - The protobuf copy made while one `journal` RPC is in flight (`QJournalProtocolTranslatorPB.journal` → `PBHelperClient.getByteString(records)`), plus IPC client socket buffers.
  - Queued non-edit tasks (`startLogSegment`, `finalizeLogSegment`, heartbeats). These are not counted.
  - The namespace itself (inodes created by the workload).
- JournalNode side: JN heap and edits disk. That is a different process and is not governed by this key.

**A5. Evidence beyond the source.**
- `TestIPCLoggerChannel#testQueueLimiting` (`hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/qjournal/client/TestIPCLoggerChannel.java:90-131`) sets the limit to 1 MiB. It fills the queue with 256 × 4096-byte batches, asserts that `getQueuedEditsSize() == 1 MiB`, and expects the next send to fail with `LoggerTooFarBehindException`.
- `TestNNWithQJM.java:66-72` shows that a non-HA NameNode can use a `qjournal://` URI directly as `dfs.namenode.edits.dir`.
- Hadoop docs on remote mode for `NNThroughputBenchmark`: `hadoop-common/src/site/markdown/Benchmarking.md:25-37`, https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-common/Benchmarking.html.
- I did not consult or rely on any JIRA.

## B. Verification solution

**B1. Claim under test.** For one JournalNode that stops acknowledging while the other JournalNodes keep up, the NameNode's `queuedEditsSizeBytes` for that channel, and the heap it pins, rises until it reaches L·2^20 bytes and then stops, where L = `dfs.qjournal.queued-edits.limit.mb`. It ends up within one batch below that cap, and later batches are refused with `LoggerTooFarBehindException`. The only overshoot is a single batch larger than L admitted into an empty queue. With L above what the workload produces, the queue instead follows the workload.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 8 and Maven 3.3+. Work on a local copy of the tag, for example `rsync -a ~/hadoop-3.4.2/ /mydata/<run>/src/`. Do not build in a shared tree.
- Build: `cd /mydata/<run>/src && mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
- Test source: new file `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/qjournal/client/TestQueuedEditsCapProbe.java`. It must be in this package because `LoggerTooFarBehindException` and `waitForAllPendingCalls` are package-private.
- Surefire's default JVM options are enough. The heap involved is at most 8 MiB.

> **Amendment A1 (stage-4 audit, 2026-11-24; B2a and B3a; before any reading).** Paths on the stage-4 node (Jingsong's
> Hadoop environment, `environment.md`): `~/hadoop-3.4.2` and `/mydata/<run>/hadoop-base` do not exist as written. Let
> `R = /mydata/jingsong-s4/dfs.qjournal.queued-edits.limit.mb-reserveQueueSpace-queueSizeLimitBytes-run1`. Unit tier: the
> local copy is `R/src`, made with `copy-source.sh` from the repository's `systems/hadoop/source/` (rel/release-3.4.2); every
> 3.4.2 module is already in `~/.m2` from the node's base build, so no `install` is run: `cd R/src && mvn -B -o -pl
> hadoop-hdfs-project/hadoop-hdfs test -Dtest=<Class> -DfailIfNoTests=false` with `JAVA_HOME` = JDK 8. Surefire failures do not
> fail `mvn test` here; read the surefire counts. Cluster tier: `$H` = `R/hadoop`, a `cp -a` of the node's built distribution
> `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2`; all run directories of B3a are under `R/cluster/`
> (`R/cluster/nn/name`, `R/cluster/jn1` …, `R/cluster/conf-nn` …) in place of `/mydata/<run>/`.
> *A1 fix (run 1, 2026-11-24, runbook defect 1):* the unit command runs **without** `-o`: the node's base build skipped
> tests, so the surefire JUnit4 provider was not in `~/.m2` and the offline run failed before any test ran (no reading).
> Maven Central is reachable; nothing else changes.

**B2b. Knobs.** Vary `L` = `dfs.qjournal.queued-edits.limit.mb`, set with `conf.setInt(DFSConfigKeys.DFS_QJOURNAL_QUEUE_SIZE_LIMIT_KEY, L)` before the channel is constructed:
- L = 0: degenerate case, one batch at a time.
- L = 1: the existing test's value.
- L = 4: shows that the cap scales.
- Unset: default 10.

For each L, use two batch sizes:
- b = 4096 bytes (fine granularity).
- b = 512 KiB, the real QJM flush size (`QuorumJournalManager.java:108`).

The overshoot case uses one batch of 3 MiB with L = 1.

**B2c. Workload.**
- Build the channel as in `TestIPCLoggerChannel.setupMock` (`TestIPCLoggerChannel.java:65-78`): override `getProxy()` to return a Mockito `QJournalProtocol`, then `setEpoch(1)`.
- Block every `journal` call with `GenericTestUtils.DelayAnswer`, using `Mockito.doAnswer(delayer).when(mockProxy).journal(any(), anyLong(), anyLong(), anyInt(), any())`. The first task then blocks the single executor thread, and later tasks wait in the queue.
- Send `N = 2·⌈L·2^20 / b⌉ + 4` batches (for L = 0, N = 4). Each batch is a new `byte[b]` with `firstTxnId = i`, and the test keeps no strong reference to the array; for each array keep only a `WeakReference`. N is twice the number of batches that fit, so the limit is certainly crossed.
- Overshoot case: on an empty queue with L = 1, send one 3 MiB batch, then one 4 KiB batch.
- Positive control: the same sends with a mock `journal` that returns at once (no `DelayAnswer`).

**B2d. Observables and instruments.**
- `ch.getQueuedEditsSize()`: the operand `queuedEditsSizeBytes`, read after every send and recorded as its maximum and final value.
- For each returned future: `isDone()`, and whether `get()` throws an `ExecutionException` whose cause is a `LoggerTooFarBehindException`. These give the accepted count A and the refused count R.
- Pinned heap: after `System.gc()` repeated three times with a 100 ms sleep, count the cleared `WeakReference`s. Arrays of refused batches should be collectible, and arrays of accepted batches should stay reachable from the executor queue.
- Optional and coarse: `MemoryMXBean.getHeapMemoryUsage().getUsed()` after GC, with sends of b = 512 KiB versus none.
- Not observable here: the real IPC and socket buffers, which the mock replaces.

**B2e. Procedure.**
1. Write `TestQueuedEditsCapProbe`. It has one `@Test` method per (L, b) pair and one for the overshoot case. Each method creates a fresh `Configuration` and channel, runs B2c, prints `L, b, N, A, R, maxQueued, finalQueued, weakClearedAccepted, weakClearedRefused` as one line on stdout, and asserts the B2f relations.
2. Release with `delayer.proceed()`. Then `GenericTestUtils.waitFor(() -> ch.getQueuedEditsSize() == 0, 10, 10000)`. Then `ch.close()`.
3. Run `cd /mydata/<run>/src && mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestQueuedEditsCapProbe`. Also run `-Dtest=TestIPCLoggerChannel#testQueueLimiting` as the reference.
4. Collect the lines from `hadoop-hdfs-project/hadoop-hdfs/target/surefire-reports/org.apache.hadoop.hdfs.qjournal.client.TestQueuedEditsCapProbe-output.txt`.

> **Amendment A2 (stage-4 audit, 2026-11-24; B2c–B2e; before any reading).**
> (1) **Positive control pacing.** "The same sends with a mock that returns at once" leaves the pacing open: a tight send loop
> can still outrun the single executor thread and fill the queue, which would make B2g's "control shows R > 0 → invalid" row
> fire for the wrong reason. The control awaits each send's future (`get()`) before the next send, so the queue never holds
> more than one batch; it then answers the question B2h gives it (refusals are not caused by batch size alone). It is run for
> every (L, b) pair. (2) **Readings are printed, not asserted.** Each method prints one line
> `IFCHK,<case>,L,b,N,A,R,firstRefusedIdx,maxQueued,finalQueuedBeforeProceed,queuedAfterDrain,acceptedWeakCleared,acceptedTotal,refusedWeakCleared,refusedTotal,refusedCauseOK`
> and does not fail on a reading, so that one deviation does not hide the others; the conclusion is drawn from the printed
> lines. `refusedCauseOK` = every refused future's cause is a `LoggerTooFarBehindException`. (3) **Harness details that do not
> change the test:** each channel gets its own address (`127.0.0.1:<distinct port>`, never connected because `getProxy()` is
> overridden) and is closed at the end, so its metrics source name is unique in the JVM; the `DelayAnswer` returns `null`
> instead of calling the interface's (abstract) real method, so the drain after `proceed()` is by success, not by failure;
> the mock is `stubOnly()`, so Mockito does not keep the argument arrays. (4) The overshoot case runs with the `DelayAnswer`
> blocking (3 MiB batch first, then the 4 KiB batch, on one channel), and its line uses the same format.

**B2f. Predictions.** Let C = L·2^20. The relations below are stated before any run.

When C ≥ b:
- A = ⌊C/b⌋.
- maxQueued = finalQueued(before proceed) = ⌊C/b⌋·b, so C − b < maxQueued ≤ C.
- R = N − A.

Per pair:

| L | b | A | maxQueued (bytes) |
|---|---|---|---|
| 1 | 4096 | 256 | 1 048 576 |
| 1 | 512 KiB | 2 | 1 048 576 |
| 4 | 4096 | 1024 | 4 194 304 |
| 4 | 512 KiB | 8 | 4 194 304 |
| unset (10) | 4096 | 2560 | 10 485 760 |
| unset (10) | 512 KiB | 20 | 10 485 760 |

- L = 0 (both b): A = 1 and maxQueued = b.
- Overshoot (L = 1): the 3 MiB batch is accepted and maxQueued = 3 145 728 > C. The following 4 KiB batch is refused.
- After `proceed()`, the queue drains to 0.
- After GC, the weak references of every refused array are cleared, and those of every accepted array are not cleared before `proceed()`.
- Positive control: R = 0 and finalQueued = 0 for every L.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| maxQueued tracks ⌊C/b⌋·b across L ∈ {1, 4, 10}, and R > 0 starts exactly at batch ⌊C/b⌋+1 | The mechanism works as traced. The claim is supported at unit level. |
| maxQueued > C with no single batch > C | The claim is wrong: the check overshoots. |
| maxQueued is the same for every L (for example N·b) | The claim is wrong: the key is not applied, for example it is read from a different conf. |
| Refused-batch arrays are not collectible, or accepted arrays are collectible while queued | The counter does not match the heap it is meant to bound, so the memory claim is wrong even if the counter is capped. |
| The 3 MiB batch is accepted on an empty queue | The expected documented overshoot, not a refutation. |
| Positive control shows R > 0 | Refusals come from something other than queue depth. The test is invalid. |
| The DelayAnswer does not block (A = N and finalQueued = 0 immediately) | The limit was never reached. Not confirmed; fix the harness. |

> **Amendment A3 (stage-4 audit, 2026-11-24; B2g; before any reading).** Verdict wording for each row, in order:
> row 1 → **Confirmed — caps** (requires the control row not to fire, refused arrays collectible and accepted arrays not,
> `refusedCauseOK`, and the 3 MiB overshoot as in row 5); row 2 → **Refuted — does not cap**; row 3 → **Refuted — does not
> cap** (unless a harness cause is found, then Invalid and rerun); row 4 → **Refuted — does not cap (memory)**; row 5 →
> consistent with row 1 (the documented one-batch overshoot); row 6 → **Invalid**; row 7 → **Not confirmed**. Added rows:
> (8) maxQueued ≤ C and follows L, refusals start, but A, R or maxQueued differ from the exact B2f numbers → **Not confirmed**
> (the cap holds but the traced arithmetic is wrong; feedback to stage 3); (9) the queue does not drain to 0 after
> `proceed()` → the cap verdict stands on rows 1–8, and the accounting leak is recorded as a finding; (10) a refused future's
> cause is not `LoggerTooFarBehindException` → **Not confirmed** (refusal by another path).

**B2h. Controls.**
- Unblocked-proxy run: rules out refusals caused by batch size alone.
- L sweep: rules out a fixed internal bound.
- The 4096-byte batch reproduces the existing `testQueueLimiting` numbers, which anchors the harness.
- Fresh arrays per batch, with no test-side strong references, so heap reachability reflects only the channel's queue.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux host, pseudo-distributed, running:
  - 1 NameNode (non-HA) whose `dfs.namenode.edits.dir` is a `qjournal://` URI (supported, see `TestNNWithQJM.java:66-72`).
  - 3 JournalNodes on the same host, JN1/JN2/JN3, each with its own config directory.
  - No DataNodes, ResourceManager, NodeManagers or SecondaryNameNode.
- Build: from the local copy, `mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`. Use `hadoop-dist/target/hadoop-3.4.2` as `$H`, where `$H=/mydata/<run>/hadoop-base`.
- Directories: everything under `/mydata/<run>/` on local disk, with at least 5 GB free:
  - `nn/name`
  - `jn1`, `jn2`, `jn3`
  - `logs/{nn,jn1,jn2,jn3}`
  - `pids/{nn,jn1,jn2,jn3}`
- Config directories: copy `$H/etc/hadoop` four times, to `conf-nn`, `conf-jn1`, `conf-jn2` and `conf-jn3`.
- `hadoop-env.sh` in each conf directory: `export HADOOP_LOG_DIR=/mydata/<run>/logs/<role>`, `export HADOOP_PID_DIR=/mydata/<run>/pids/<role>`, and `export JAVA_HOME=<jdk8>`.
  - In `conf-nn`, also set `export HDFS_NAMENODE_OPTS="-Xms2g -Xmx2g -XX:+UseG1GC"`.
  - In each JN conf, also set `export HDFS_JOURNALNODE_OPTS="-Xmx512m"`.
- `core-site.xml` in all four directories:
  - `fs.defaultFS = hdfs://127.0.0.1:9000`
  - `hadoop.tmp.dir = /mydata/<run>/tmp`
  - In `conf-nn` only, also `ipc.client.rpc-timeout.ms = 0`. With `ipc.client.ping=true` (the default), the NN's `journal` RPC to a stopped JN then waits indefinitely instead of failing after 120 s (`core-default.xml:2470-2497`). This holds the window open.
- `hdfs-site.xml` in `conf-jn<k>` (k = 1, 2, 3), with ports 8485/8480/8481, 8487/8482/8483 and 8489/8484/8486:
  - `dfs.journalnode.rpc-address = 127.0.0.1:<rpc>`
  - `dfs.journalnode.http-address = 127.0.0.1:<http>`
  - `dfs.journalnode.https-address = 127.0.0.1:<https>`
  - `dfs.journalnode.edits.dir = /mydata/<run>/jn<k>`
- `hdfs-site.xml` in `conf-nn`:
  - `dfs.namenode.name.dir = file:///mydata/<run>/nn/name`
  - `dfs.namenode.edits.dir = qjournal://127.0.0.1:8485;127.0.0.1:8487;127.0.0.1:8489/capjournal`
  - `dfs.namenode.edit.log.autoroll.multiplier.threshold = 100`, so no roll happens during a run.
  - `dfs.namenode.safemode.extension = 0`
  - `dfs.replication = 1`
  - `dfs.namenode.http-address = 127.0.0.1:9870`
  - Plus the knob from B3b.

**B3b. Knobs.** `dfs.qjournal.queued-edits.limit.mb` in `conf-nn/hdfs-site.xml`. The values are:

| L | Why |
|---|---|
| 1 | Small, binds early |
| unset → 10 (default) | Default |
| 64 | Large; the heap difference is clearly visible |
| 512 | Ungoverned contrast: above what the workload produces. Still below the int overflow at 2048. |

Each change needs a NameNode restart: `hdfs --config conf-nn --daemon stop namenode`, then start it again. JournalNodes do not need a restart.

**B3c. Workload.**
- Load: NameNode mkdirs in remote mode with `NNThroughputBenchmark`, from the hadoop-hdfs tests jar in the distribution:
  ```
  HADOOP_CLASSPATH=$H/share/hadoop/hdfs/hadoop-hdfs-3.4.2-tests.jar \
    $H/bin/hadoop --config conf-nn org.apache.hadoop.hdfs.server.namenode.NNThroughputBenchmark \
    -fs hdfs://127.0.0.1:9000 -op mkdirs -threads 16 -dirs 1000000 -dirsPerDir 128
  ```
  Each `OP_MKDIR` edit is on the order of 100–200 bytes, so 1 M ops is about 100–200 MB of edits. That is well above 64 MiB and below 512 MiB.
- The exact amount sent during the stopped window is W. It is measured directly as the growth of a healthy JN's in-progress segment, so the bytes-per-op estimate is not relied on.
- The JN is stopped for the whole benchmark and resumed afterward. Expected duration is a few minutes per run. If W < 64 MiB in the 64 run, raise `-dirs` to 2 000 000.

**B3d. Observables and instruments.**
1. Operand: NameNode JMX, sampled every 2 s from start of the stop until drain with `curl -s 'http://127.0.0.1:9870/jmx?qry=Hadoop:service=NameNode,name=IPCLoggerChannel-127.0.0.1-8489'`. Read the attributes `QueuedEditsSize`, `IsOutOfSync` and `CurrentLagTxns`. If the name differs, list the beans with `qry=Hadoop:service=NameNode,name=IPCLoggerChannel*`.
2. Actual heap pinned by queued edits:
   - `jmap -histo:live <nnpid> | awk '$4=="[B"'` gives the total bytes of `byte[]`. It forces a full GC.
   - `jcmd <nnpid> GC.heap_info` gives used heap after that GC.
   - Take these at three points: (a) before the stop with the workload idle, (b) at the plateau after the benchmark ends with JN3 still stopped, and (c) after `SIGCONT` and drain to `QueuedEditsSize = 0`.
   - The namespace growth (inodes) is the same in (b) and (c), so (b) − (c) isolates the queued edits.
3. W: `stat -c %s` of the newest `edits_inprogress_*` under `/mydata/<run>/jn1/capjournal/current/`, at the stop and at the end of the benchmark. The difference is W.
4. NN log: `grep -c "is going to exceed limit size" /mydata/<run>/logs/nn/*namenode*.log` counts refusals. Also check that the NN stays up: `jps` and `hdfs dfs -ls /`.
5. Not directly observable: which exact array belongs to which batch, and protobuf or socket-buffer copies. Those are bounded by one in-flight batch plus kernel buffers.

**B3e. Procedure.** Run as one non-root user from `/mydata/<run>`.
1. Build (B3a) and create the directories and configs.
2. `for k in 1 2 3; do $H/bin/hdfs --config conf-jn$k --daemon start journalnode; done`. Check with `jps` that there are 3 JournalNodes.
3. `$H/bin/hdfs --config conf-nn namenode -format -force -nonInteractive`. This formats the qjournal through the JNs.
4. For each L in {1, 10, 64, 512}:
   1. Set L in `conf-nn/hdfs-site.xml`. For L = 10, remove the property.
   2. `$H/bin/hdfs --config conf-nn --daemon start namenode`, then `$H/bin/hdfs --config conf-nn dfsadmin -fs hdfs://127.0.0.1:9000 -safemode leave`.
   3. Warm-up: `$H/bin/hdfs --config conf-nn dfs -mkdir -p /warm/$L`. This opens the RPC connections to all JNs.
   4. Take heap snapshot (a). Record W0, the in-progress size on jn1. Start the JMX sampler (a background loop writing to `/mydata/<run>/jmx-L$L.csv`).
   5. `JN3=$(cat pids/jn3/hadoop-*-journalnode.pid); kill -STOP $JN3`.
   6. Run the B3c benchmark with `-baseDirName /bench$L`, so names do not collide across runs. Wait until it exits.
   7. Wait 10 s. Take heap snapshot (b). Record W = in-progress size − W0. Record the refusal count from the NN log.
   8. `kill -CONT $JN3`. Wait until `QueuedEditsSize` is 0 (it falls through out-of-sync fast-fail). Take heap snapshot (c).
   9. Stop the sampler. `$H/bin/hdfs --config conf-nn --daemon stop namenode`.
5. Positive control run: repeat step 4 with L = 64 but without `kill -STOP`. Expect `QueuedEditsSize` to stay near 0, with only transient batches.
6. Cleanup (B4).

> **Amendment A4 (stage-4 audit, 2026-11-24; B3c–B3e; before any reading).** Exact procedure details, none of which
> changes B3f or B3g. (1) **Tools:** `JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64` in every shell and conf; heap snapshots use
> `$JAVA_HOME/bin/jmap` and `$JAVA_HOME/bin/jcmd` (the node's default `jmap` is JDK 11 and cannot attach to the JDK 8 NN).
> A heap snapshot records, from `jmap -histo:live`, the `[B` row's bytes (column 3) and instance count, and the `Total` line,
> then `jcmd GC.heap_info`. (2) **Benchmark classpath:** `NNThroughputBenchmark` also uses `GenericTestUtils` (hadoop-common
> tests jar), so `HADOOP_CLASSPATH` is the hdfs tests jar plus `$H/share/hadoop/common/hadoop-common-3.4.2-tests.jar`, and,
> only if the class does not load without them, the `junit`/`hamcrest-core` jars from `~/.m2` (recorded). (3) **W exactly:**
> the JN preallocates its in-progress file in 1 MiB steps, so `stat -c %s` is a ±1 MiB cross-check only; W is the growth of
> JN1's `BytesWritten` (`http://127.0.0.1:8480/jmx?qry=Hadoop:service=JournalNode,name=Journal-capjournal`) between the stop
> (step 4.5) and snapshot (b), and the file size is recorded beside it. (4) **Sampler:** a Python loop (no `jq` on the node)
> polls the NN bean of B3d.1 and JN1's `BytesWritten` every 2 s and writes `epoch_ms,QueuedEditsSize,IsOutOfSync,CurrentLagTxns,jn1BytesWritten`
> to `R/cluster/logs/jmx-<label>.csv`; the plateau is the maximum `QueuedEditsSize` sampled between the stop and snapshot (b)
> and the value at (b). (5) **Order and state:** the qjournal is formatted once; runs are L = 1, 10, 64, 512, then the control
> (L = 64, no stop), each with a fresh NN start (new segment, so `outOfSync` is reset) and its own `-baseDirName /bench<label>`.
> The benchmark runs without `-keepResults`, so its `cleanUp()` deletes the base directory before it exits; the namespace is
> then the same at (b) and (c). (6) **Stop conditions:** a benchmark longer than 20 min, an NN exit, or a drain to 0 that takes
> longer than 10 min after `kill -CONT` stops the tier and is recorded. (7) **Refusal count:** the WARN line of
> `IPCLoggerChannel.java:452-454` ("is going to exceed limit size"), counted per run from the NN log lines written between the
> stop and snapshot (b).

**B3f. Predictions.** Let C = L·2^20 and B = largest batch, about 512 KiB plus one sync's worth of ops (B ≤ ~1 MiB). These are stated before any run.

| L | Plateau `QueuedEditsSize` | (b) − (c) byte[] live | NN log refusals | NN state |
|---|---|---|---|---|
| 1 | in (C − B, C] ≈ 0–1 MiB (if B > C, then exactly one batch ≤ B) | ≈ plateau ± 1 MiB | > 0 | up; JN3 out of sync after resume |
| 10 | in (10 MiB − B, 10 MiB] | ≈ 10 MiB ± 1 MiB | > 0 | up |
| 64 | in (64 MiB − B, 64 MiB] | ≈ 64 MiB ± 2 MiB | > 0 | up |
| 512 | ≈ W (100–200 MB, ≤ 512 MiB), growing for the whole benchmark | ≈ W | 0 | up; JN3 catches up in order after resume |

- Relation across L ∈ {1, 10, 64}: the plateau grows linearly with L, and the (b) − (c) heap difference grows with it, about 1 MiB of heap per MiB of L.
- At L = 512, the plateau is independent of L and equal to W.
- For L ∈ {1, 10, 64}, the plateau stays flat while W keeps growing on JN1/JN2. That shows the cap binds and not the workload.
- The claim is wrong if any of these is seen:
  - The plateau exceeds C + B for L ∈ {1, 10, 64}.
  - The (b) − (c) heap difference is well above C + B, for example ≈ W.
  - The plateau is the same for 10 and 64.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Plateau ≈ C for L = 1/10/64, heap (b) − (c) ≈ C, refusals logged, and W ≫ C | The limit governs the NN heap pinned for a lagging JN. Claim confirmed. |
| L = 512 run plateau ≈ W, heap (b) − (c) ≈ W | Expected ungoverned contrast: usage follows the workload when the cap does not bind. This also serves as the positive control that the workload does move heap. |
| Plateau ≈ C but heap (b) − (c) ≈ W or much larger than C | The counter is capped but the heap is not. Something else retains the arrays, such as the quorum calls or the async logger. Claim wrong for memory. |
| Plateau > C + B | The check overshoots. Claim wrong. |
| Plateau identical for L = 10 and 64 | The key is not applied (wrong conf dir, NN not restarted). The run is invalid. |
| `QueuedEditsSize` never rises (≈ 0) during the stop | The window was not held open: the RPC failed fast, or the connection is not to JN3. Not confirmed. Check `ipc.client.rpc-timeout.ms`, the bean name and `IsOutOfSync`. |
| NN aborts with a quorum error | More than a minority was stopped or refused. Invalid setup. |
| Without-stop control has `QueuedEditsSize` ≫ 0 | The JNs cannot keep up even when healthy. Reduce `-threads`. |

> **Amendment A5 (stage-4 audit, 2026-11-24; B3g; before any reading).** Verdict wording for each row, in order: row 1 →
> **Confirmed — caps** (it also needs the L = 512 row to hold, the control row not to fire, and W > C for each L ∈ {1, 10, 64});
> row 2 → required for row 1 (the ungoverned contrast); row 3 → **Refuted — does not cap (memory)**; row 4 → **Refuted — does
> not cap**; row 5 → **Invalid**; row 6 → **Not confirmed**; row 7 → **Invalid**; row 8 → **Invalid** (rerun with fewer
> threads). Added rows: (9) the plateau follows C for L ∈ {1, 10, 64} with refusals, but the heap difference (b) − (c) is
> outside the B3f tolerance and not ≈ W either (for example far below C, or negative) → **Not confirmed** (the counter is
> capped but the heap instrument does not resolve the queued bytes); (10) W ≤ C for some L ∈ {1, 10, 64} (the workload never
> reached that limit) → that L is not evidence; with fewer than two binding values of L the tier is **Not confirmed**;
> (11) at L = 512 the plateau stays well below W (for example a fixed value) → **Not confirmed** (another bound or a stalled
> window, not the key, limits the queue).

**B3h. Controls.**
- The without-stop run isolates the lag as the cause.
- The L sweep at fixed workload, plus L = 512, separates cap from workload.
- Heap snapshot (c) after drain removes namespace growth, which is common to (b) and (c), from the comparison.
- W measured on a healthy JN shows that the workload produced more than C.
- The NN-only setup (no DataNodes, no checkpointing, autoroll threshold raised) removes other heap and edit sources.
- `IsOutOfSync=false` during the stop confirms that the queue grows for lack of an acknowledgement, not because of a gap.

**B4. Risks and cleanup.**
- Disk: the unit tier writes only under `target/`. The cluster tier puts 3 × (≤ 0.5 GB) of JN edits and the NN image under `/mydata/<run>`, all on local disk. Never use NFS or the shared source tree.
- Memory: NN 2 GB heap, 3 JNs × 512 MB, benchmark client ~1 GB. Check the free memory first.
- Ports in use: 9000, 9870, 8480–8489. Check them first with `ss -ltn`, and change the ports if any are taken.
- A JN left in SIGSTOP holds its ports. Always `kill -CONT` it before stopping it.
- Cleanup: `$H/bin/hdfs --config conf-nn --daemon stop namenode`; `for k in 1 2 3; do kill -CONT $(cat pids/jn$k/*.pid) 2>/dev/null; $H/bin/hdfs --config conf-jn$k --daemon stop journalnode; done`. Then `jps` must show no NameNode, JournalNode or NNThroughputBenchmark. Kill any stray benchmark JVM. Then `rm -rf /mydata/<run>/{nn,jn1,jn2,jn3,tmp}` if the data is not kept.

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/qjournal/client/IPCLoggerChannel.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/qjournal/client/IPCLoggerChannelMetrics.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/qjournal/client/QuorumOutputStream.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/qjournal/client/AsyncLoggerSet.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/qjournal/client/QuorumJournalManager.java (lines 93-194, 438-462)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/qjournal/client/LoggerTooFarBehindException.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/qjournal/protocolPB/QJournalProtocolTranslatorPB.java (journal)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/EditsDoubleBuffer.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLog.java (306, 1567, 1878)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/JournalSet.java (575-582)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java (423-430, 692, 1477-1501)
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml (523, 2638-2691, 3100, 5022, 5765-5770)
- hadoop-common-project/hadoop-common/src/main/resources/core-default.xml (2466-2497)
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/qjournal/client/TestIPCLoggerChannel.java
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/qjournal/TestNNWithQJM.java (60-80)
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/qjournal/server/TestJournalNodeSync.java (80)
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/NNThroughputBenchmark.java (usage, remote mode)
- hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/test/GenericTestUtils.java (DelayAnswer)
- hadoop-common-project/hadoop-common/src/site/markdown/Benchmarking.md
- https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-common/Benchmarking.html (cited, same content as the markdown above)

## D. Stage-4 feedback

**D1. Design audit (2026-11-24, stage-4 agent, node `pc72`).** Bottom line: **Ready after amendments.** Applied before any
reading: A1 (node paths, offline `mvn test`, surefire counts), A2 (control pacing, printed readings, harness details), A3
(B2g verdict wording and rows 8–10), A4 (cluster tools, classpath, exact W, sampler, order, stop conditions), A5 (B3g verdict
wording and rows 9–11). Whole-file sha256 before the audit: `882377eb683c4530ebf26c6bebb9ca00d509bb87504db931c54a1a7ebc5abe86`;
the frozen version is recorded in the results file §1 (`~/writeup-hadoop/out/o19/results.md`). Left for stage 3: none that
changes the test.

**D2. Run 1 verdict (2026-11-24, node `pc72`; results `~/writeup-hadoop/out/o19/results.md`).** Unit tier **Confirmed —
caps** (B2g row 1): every (L, b) pair matched B2f exactly (A = ⌊C/b⌋, maxQueued = ⌊C/b⌋·b, first refusal at batch ⌊C/b⌋+1;
L = 0 one batch; 3 MiB overshoot accepted, then refused), refused arrays collectible and queued ones not, control R = 0.
Cluster tier **Confirmed — caps** (B3g rows 1 and 2): plateau `QueuedEditsSize` 1 048 569 / 10 485 698 / 67 108 812 B for
L = 1 / 10 (unset) / 64, flat while JN1 took W ≈ 149.5 MB; NN `byte[]` (b) − (c) 1.26 / 10.35 / 65.27 MiB; 129 959 / 137 436 /
71 020 refusal WARNs; L = 512 plateau = W = 150 518 374 B with 0 refusals and 147.4 MiB of `byte[]`; no-stop control peak
1 356 B. Outcome class: **true positive**. Runbook defect 1 fixed in A1 (unit `mvn` without `-o`). Findings: real batches
on this workload were ≤ 2 361 B (one sync per few ops), not ~512 KiB, so B ≪ C; the `IsOutOfSync` metric is a JMX *tag*
(`tag.IsOutOfSync`), so the A4 sampler column read NA (not used by any row).
