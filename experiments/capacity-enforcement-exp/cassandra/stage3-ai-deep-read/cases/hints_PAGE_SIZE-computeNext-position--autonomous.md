# `HintsReader.PAGE_SIZE` (512 KiB hint dispatch page) — verification solution  <!-- file: cases/hints_PAGE_SIZE-computeNext-position--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`HintsReader.java:186`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsReader.java#L186) (also covers `HintsReader.java:292#1`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code at Meta (`claude --version` prints no version number), 2026-10-26 |
| Estimate | `undetermined` — the check caps the hint bytes one dispatcher sends before waiting for all acknowledgements (≤ 512 KiB plus one hint), but the sender drops each message once it is written to the connection, so whether node heap follows the page depends on where the hints wait (outbound queue, or the receiver's MUTATION stage); the bound is per dispatcher and small. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `HintsReader.PAGE_SIZE`, a `private static final int` constant, `512 << 10` = 524,288 bytes ([`HintsReader.java:55-56`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsReader.java#L55-L56), comment "don't read more than 512 KiB of hints at a time"). Not settable (no yaml key, no `-D` property, no JMX); changing it needs a code change and rebuild.


**Limit type (2026-10-29).** non-config: hard-coded constant. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Heap held by hint dispatch: the number of hint bytes read from a hints file and sent to one target node as one page before the dispatcher waits for every response. The operand is `position.subtract(offset)`: the uncompressed bytes read since the page started (`HintsReader.java:186` in `HintsIterator.computeNext`, `:292` in `BuffersIterator.computeNext`). For compressed/encrypted files `subtract` also counts uncompressed bytes (`CompressedChecksummedDataInput.java:76-81`); for plain files the file offset (`ChecksummedDataInput.java:101-105`).

**A3. Mechanism.**
1. `HintsDispatchExecutor.DispatchHintsTask` opens one `HintsDispatcher` per hints file of one target host, at most one task per host, on `max_hints_delivery_threads` threads (default 2, `conf/cassandra.yaml:93`; `HintsDispatchExecutor.java:97-111, 270-296`); the reader is throttled by `hinted_handoff_throttle` / (nodes − 1) ([`HintsDispatchExecutor.java:219-221`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsDispatchExecutor.java#L219-L221), applied per hint at `HintsReader.java:232-233, 340-341`).
2. `HintsDispatcher.dispatch()` iterates pages ([`HintsDispatcher.java:97-106`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsDispatcher.java#L97-L106)); `PagesIterator` starts a page at the current seek position ([`HintsReader.java:150-161`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsReader.java#L150-L161)).
3. `sendHintsAndAwait` ([`HintsDispatcher.java:122-162`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsDispatcher.java#L122-L162)) picks the raw path (`buffersIterator`, same messaging version) or the decode path (`hintsIterator`), and `sendHints` sends every hint of the page with `MessagingService.sendWithCallback`, adding a `Callback` per hint (`:180-192, 194-215`).
4. The page iterator stops at EOF or when `position − offset ≥ PAGE_SIZE` (**:186**, **:292**). The test runs **before** each read, so a page holds k = ⌈524,288 / e⌉ entries of equal size e (entry = hint + 12 bytes of length/CRC framing), and its bytes are in [524,288, 524,288 + e_last). An entry larger than 512 KiB forms a page by itself. Dead hints (`readBufferIfLive`/`deserializeIfLive` return null) count toward the page but are not sent.
5. After sending, the dispatcher awaits every callback ([`HintsDispatcher.java:144-151`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsDispatcher.java#L144-L151)) up to the `HINT_REQ` timeout (write timeout, [`Verb.java:118`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/Verb.java#L118)); any failure or timeout aborts and the page is retried later from its start (`:155-159`, [`HintsDispatchExecutor.java:320-322`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsDispatchExecutor.java#L320-L322)).
6. Memory per hint: the raw path copies each hint into a fresh heap `byte[size]` ([`Hint.java:239-242`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/Hint.java#L239-L242)) wrapped in `HintMessage.Encoded`; the decode path deserializes a `Mutation`. The sender's references are the outbound message (until serialized to the socket) and the `Callback`, which keeps no payload ([`HintsDispatcher.java:217-260`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsDispatcher.java#L217-L260)). On the receiver, `HINT_REQ` runs on the MUTATION stage ([`Verb.java:118`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/Verb.java#L118)), so up to k decoded hints from one dispatcher wait or run there at once.

Overshoot: one entry past 512 KiB (up to a hint of `max_mutation_size`, 16 MiB by default). Node-wide on the sender: ≤ (delivery threads) × page. The internode outbound queue has its own byte limits (`internode_application_send_queue_*`), outside this constraint.

**A4. Other consumers.** The hints write path (`HintsBuffer` slabs, direct memory), the hints writer buffer, MUTATION-stage work from normal writes on the receiver, internode buffers, memtables. Disk of hints files is governed by `max_hints_size_per_host` / `max_hint_window`, not by PAGE_SIZE.

**A5. Evidence beyond the source.** `test/unit/org/apache/cassandra/hints/HintsReaderTest.java:95-160` (writes a file and reads it page by page through both iterators) — the pattern the unit tier reuses. Byteman: https://byteman.jboss.org/ (rule language, `incrementCounter`, `readCounter`, `traceln`).

## B. Verification solution

**B1. Claim under test.** (1) Each dispatch page contains k = ⌈524,288 / e⌉ hints of entry size e (k = 1 when e ≥ 524,288), so the hint bytes one dispatcher has outstanding are < 512 KiB + e, independent of the file size. (2) On a real two-node cluster, the hints held at once on the receiving node from one dispatcher (and so the heap they occupy) are ≤ k, not the whole backlog N. Part (1) failing refutes the cap; part (1) holding with part (2) failing means the page caps the operand but not node memory.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. `git clone --branch cassandra-5.0.9 --depth 1 <origin> ~/hp-run && cd ~/hp-run && ant jar build-test`. Test: `~/hp-run/test/unit/org/apache/cassandra/hints/HintsPageCapTest.java` (package `org.apache.cassandra.hints`; `HintsReader`, `HintsWriter`, `HintsDescriptor` are package-private). Run `ant testsome -Dtest.name=org.apache.cassandra.hints.HintsPageCapTest`. Default test JVM options.

> **Amendment B2a (2026-10-26, stage-4 audit, before any run-1 reading).** On the advisor's machine (macOS 27, arm64, JDK 11.0.32.1, Ant 1.10.18; `environment-advisor.md`): the clone is
> `$W/cassandra-run37` (`W=~/Library/Caches/stage4`), a fresh `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run37`, built with
> `ant -Dlocal.repository=$W/m2 build-test` (it builds the jar classes too). The test file is
> `cassandra/stage4-runtime-verification/harness/hints_PAGE_SIZE-computeNext-position--autonomous/HintsPageCapTest.java`; `unit-run.sh` in the same folder copies it into
> `test/unit/org/apache/cassandra/hints/`, runs it and removes it, so the clone's `git status` stays clean. Default test JVM options.
**B2b. Knobs.** PAGE_SIZE itself is a constant and is not varied. Varied: the hint entry size, value v ∈ {1 KiB, 16 KiB, 600 KiB} (many per page; few per page; larger than a page), and file format ∈ {plain, LZ4-compressed} (descriptor params `{"compression": {"class_name": "LZ4Compressor"}}`, as in `HintsCompressionTest`).

**B2c. Workload.** `SchemaLoader.prepareServer()`, keyspace `hpcap` with table `t (k int PRIMARY KEY, v blob)` via `SchemaLoader.standardCFMD`. For each v: write N hints into one file, N = ⌈8 MiB / v⌉ (8,192 / 512 / 14), each a single-row mutation with a random v-byte value, using `HintsDescriptor d = new HintsDescriptor(hostId, now, params)` and `try (HintsWriter w = HintsWriter.create(dir, d); HintsWriter.Session s = w.newSession(ByteBuffer.allocateDirect(256 << 10))) { s.append(hint) ... }` (the pattern of `HintsReaderTest.java:84-101`). The file is ≈ 8 MiB ≈ 16 pages, so the limit is reached repeatedly. Then `try (HintsReader r = HintsReader.open(d.file(dir)))`: for each `Page p : r`, drain `p.buffersIterator()` into a list (holding every buffer until the page ends, as the dispatcher holds callbacks), record count c, Σ`remaining()`, and `r.getInput().getSeekPosition().subtract(p.position)` = page bytes P. Repeat with `p.hintsIterator()`.

> **Amendment B2c (2026-10-26, stage-4 audit, before any run-1 reading).**
> - **Schema.** `SchemaLoader.standardCFMD` does not build `t (k int PRIMARY KEY, v blob)` (it makes a clustered ascii table). The table is made with
>   `SchemaLoader.createKeyspace("hpcap", KeyspaceParams.simple(1), CreateTableStatement.parse("CREATE TABLE t (k int PRIMARY KEY, v blob)", "hpcap"))`;
>   each hint is `Hint.create(new RowUpdateBuilder(t, ts, i).add("v", value).build(), now)`.
> - **Values.** Every value is the v-byte pattern `(byte)(j % 13)`, not random bytes. Reason (group A/B, from source): random bytes do not compress, so
>   the LZ4 file would be as large as the plain one and row 3 of B2g ("the cap counts on-disk bytes") could not be told from row 1. With a compressible
>   value the LZ4 file is many times smaller, so a cap on on-disk bytes would give many more hints per page. The uncompressed entry size e is unchanged.
> - **Sizes.** v = 1,024 / 16,384 / 614,400 bytes ("600 KiB"); N = ⌈8,388,608 / v⌉ = 8,192 / 512 / 14 hints, one file per (v, format), in a fresh
>   temporary directory removed after the class. Per hint e = `Hint.serializer.serializedSize(hint, descriptor.messagingVersion()) + 12` is computed at
>   write time (min and max are printed), and the hints file's size on disk is printed.
> - The page bytes are P = `r.getInput().getSeekPosition().subtract(p.position)` read after the page's iterator is drained; for the decode iterator the
>   sum is Σ `serializedSize` of the decoded hints (the buffers iterator: Σ `remaining()`).
**B2d. Observables and instruments.** Per page: c, P, Σ remaining; per run: e = P / c for full pages, number of pages, N. Printed `HPCAP v=%d fmt=%s page=%d c=%d P=%d sum=%d`. `Hint.serializer.serializedSize(hint, current_version) + 12` gives e independently. Not observable: heap is not measured in this tier (the list holds exactly Σ remaining bytes of payload).

> **Amendment B2d (2026-10-26, stage-4 audit, before any run-1 reading).** Line formats (stdout, in `build/test/logs/**/TEST-org.apache.cassandra.hints.HintsPageCapTest.log`):
> `HPCAP-FILE v=<v> fmt=<plain|lz4> N=<n> emin=<e> emax=<e> fileBytes=<bytes>`;
> `HPCAP v=<v> fmt=<fmt> it=<buffers|hints> page=<i> c=<count> P=<page bytes> sum=<payload bytes>` (one per page);
> `HPCAP-END v=<v> fmt=<fmt> it=<it> pages=<pages> read=<hints read>`. The filed format had no iterator field.
**B2e. Procedure.** 1. Clone, build. 2. Add the test with one `@Test` per (v, fmt). 3. `ant testsome -Dtest.name=org.apache.cassandra.hints.HintsPageCapTest 2>&1 | tee ~/hp-unit.log`. 4. `grep HPCAP ~/hp-unit.log`. 5. Delete the temp hints dir in `@After`.

> **Amendment B2e (2026-10-26, stage-4 audit, before any run-1 reading).** `source ~/Library/Caches/stage4/env.sh; cassandra/stage4-runtime-verification/harness/hints_PAGE_SIZE-computeNext-position--autonomous/unit-run.sh` (one `ant testsome`
> JVM; six `@Test` methods, one per (v, format), each reading its file with both iterators). Logs: `$W/logs/<stem>/unit/` (`ant.log`, `TEST.log`,
> `hpcap.txt`, `summary.txt`, `readings.txt`, `commands.log`).
**B2f. Predictions.** With e from `serializedSize + 12`: every page except the last has c = ⌈524,288 / e⌉ and 524,288 ≤ P < 524,288 + e; for v = 1 KiB c ≈ 480–500, for 16 KiB c = 32, for 600 KiB c = 1 and P = e > 524,288. Number of pages = ⌈N / c⌉. Same c and P (uncompressed) for the LZ4 file and for both iterators. Σ remaining = P − 12c.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| c = ⌈524,288/e⌉, P < 524,288 + e for every full page, all v and formats | claim (1) confirmed |
| one page holds all N hints, or P ≫ 524,288 + e | claim (1) wrong: the page does not cap |
| compressed file gives c differing from plain by the compression ratio | claim (1) wrong for compressed files (the cap counts on-disk bytes) |
| fewer than two pages for the 8 MiB file | not confirmed: the limit was not reached |

> **Amendment B2g (2026-10-26, stage-4 audit, before any run-1 reading).** Verdict words and added rows. "Non-last page" = every page of a (v, format, iterator) read except the last.
> - Row 1: for every (v, format, iterator), every non-last page has c = ⌈524,288 / e⌉ (1 when e ≥ 524,288) and 524,288 ≤ P < 524,288 + e (P = e when
>   e ≥ 524,288); the last page has P < 524,288 + e; pages = ⌈N / c⌉; sum = P − 12c on every page; read = N; and c and P are the same for both formats
>   and both iterators → **Confirmed**. Effect: **caps** (the hint bytes one page holds).
> - Row 2 (one page holds all N, or any P ≥ 524,288 + e) → **Refuted**. Effect: **does not cap**.
> - Row 3 (the LZ4 file's c or P differs from the plain file's) → **Refuted** for compressed files. Effect: **caps only on some paths**.
> - Row 4 (fewer than two pages) → **Not confirmed**. Effect: **undetermined**.
> - emin ≠ emax (c cannot be predicted exactly), a non-last page with c ≠ ⌈524,288 / e⌉ but P < 524,288 + e, sum ≠ P − 12c, or an LZ4 file not
>   smaller than half the plain file (the compressed arm cannot discriminate) → **Not confirmed**. Effect: **undetermined**.
> - The test did not run or failed, or a (v, format, iterator) has no `HPCAP` lines → **Invalid**.

**B2h. Controls.** N ≫ c (8 MiB vs 512 KiB) is the positive control: if the check did not bind, c would equal N; three entry sizes show c moves inversely with e as the formula predicts; `serializedSize` gives e without relying on the reader.

### B3. Cluster tier

**B3a. Environment and build.** One Linux host, nodes on 127.0.0.1 (sender) and 127.0.0.2 (receiver), copies `~/hp-n1`, `~/hp-n2` of the built clone, data/commitlog/hints on local disk (≥ 10 GiB free). JVM `-Xms2g -Xmx2g`. yaml on both: `cluster_name: hpcap`, seeds `127.0.0.1`, `num_tokens: 16`, `hinted_handoff_enabled: true`, `max_hint_window: 3h`, `hinted_handoff_throttle: 0KiB` (0 = unthrottled, `HintsDispatchExecutor.java:221`), `max_hints_delivery_threads: 1`, `concurrent_writes: 64`, `write_request_timeout: 5000ms`. Byteman agent on both nodes (`-javaagent:.../build/lib/jars/byteman-<ver>.jar=script:<file>` via `JVM_EXTRA_OPTS`).

Node 1 `hp1.btm`:
```
RULE count sent
CLASS org.apache.cassandra.hints.HintsDispatcher
METHOD sendEncodedHint
AT ENTRY
IF true
DO incrementCounter("sent"); incrementCounter("bytes", $1.remaining())
ENDRULE

RULE page end
CLASS org.apache.cassandra.hints.HintsDispatcher
METHOD sendHintsAndAwait
AT EXIT
IF true
DO traceln("HPCAP page sent=" + readCounter("sent") + " bytes=" + readCounter("bytes") + " action=" + $!); deleteCounter("sent"); deleteCounter("bytes")
ENDRULE
```
Node 2 `hp2.btm` (holds each hint 300 ms on the MUTATION stage so a page's hints coexist):
```
RULE hold hint
CLASS org.apache.cassandra.hints.HintVerbHandler
METHOD doVerb
AT ENTRY
IF true
DO java.lang.Thread.sleep(300L)
ENDRULE
```

> **Amendment B3a (2026-10-26, stage-4 audit, before any run-1 reading).** On the advisor's machine (one macOS host, no `setsid`; loopback aliases 127.0.0.1–.3 checked with `ifconfig lo0`):
> - Both nodes run from the one built clone `$W/cassandra-run37` with their own `CASSANDRA_CONF` and directories `$W/node-hp1`, `$W/node-hp2`
>   (`conf`, `data`, `commitlog`, `hints`, `saved_caches`, `cdc_raw`, `logs`), not two copies of the clone. Node 2's `cassandra-env.sh` has
>   `JMX_PORT="7299"`. Heap through `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` (`-Xms2G -Xmx2G`). Each node is a tracked background `bin/cassandra -f`;
>   `JVM_EXTRA_OPTS` (the agent) is scoped to that command only.
> - yaml on both nodes as filed, plus `auto_bootstrap: false` (zero-copy bootstrap streaming fails on this host with `transferTo`: Operation not
>   permitted, `environment-advisor.md` and the `hints_buffer_size` run; the ring is empty when node 2 first joins, so nothing needs streaming).
> - **Node 2 has `memtable_allocation_type: offheap_buffers`** (node 1 keeps the default `heap_buffers`). Reason (group A/B, from source, before any
>   reading): with the default `heap_buffers` every applied hint's value is copied into on-heap memtable regions (`SlabAllocator.java:89-139`), so the
>   `[B` total on node 2 would grow by the whole delivered backlog (up to 256 MiB) and B3f's "`[B` ≤ baseline + k × v + 8 MiB" could not hold whatever
>   the page does. A4 names memtables as another consumer; `offheap_buffers` moves their values to direct memory, out of the `[B` reading.
> - The agent is `-javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:<rules>` (no listener) on every start of each node. `hp1.btm` keeps the two
>   filed rules unchanged and adds three observe-only rules: `file start` / `file end` (entry and exit of `HintsDispatcher.dispatch()`, one per hints
>   file, so a file's last page is known) and `count sent decoded` (`sendHint`, the decode path, expected never to fire because both nodes have the
>   same messaging version, `HintsDispatcher.java:135-137`). `hp2.btm` is as filed. Both are in `cassandra/stage4-runtime-verification/harness/hints_PAGE_SIZE-computeNext-position--autonomous/` and type-check with
>   Byteman's `TestScript`.

**B3b. Knobs.** PAGE_SIZE is not settable. Varied: stress value size v ∈ {16 KiB, 64 KiB, 1 MiB} (k ≈ 32, 8, 1 per page). With 64 MUTATION threads and 300 ms per hint, a page of ≤ 64 hints completes in one 300 ms wave, inside the 5 s timeout.

**B3c. Workload.** Start both nodes; `nodetool -p 7299 drain` and kill node 2. On node 1: `tools/bin/cassandra-stress write n=N cl=ONE -col size=FIXED(v) n=FIXED(1) -schema "replication(factor=2)" keyspace=hp -rate threads=16 -node 127.0.0.1` with N = ⌈256 MiB / v⌉ (16,384 / 4,096 / 256), so the backlog is ≈ 512 pages per arm. `nodetool -p 7199 flush` and wait 15 s (hints flush period 10 s) so hints are on disk. Start node 2 with `hp2.btm`; dispatch begins at the next 10 s trigger. Delivery takes ≈ 512 pages × ~0.35 s ≈ 3 min.

> **Amendment B3c (2026-10-26, stage-4 audit, before any run-1 reading).**
> - The stress command adds `no-warmup`: `tools/bin/cassandra-stress write n=N no-warmup cl=ONE -col 'size=FIXED(v)' 'n=FIXED(1)' -schema
>   'replication(factor=2)' keyspace=hp -rate threads=16 -node 127.0.0.1`, with v = 16384 / 65536 / 1048576. Reason: without it cassandra-stress first
>   writes a warm-up of n/4 (at most 50,000) operations (`StressAction.java:70`), so the backlog would be 1.25 N, not the filed N.
> - Before node 2 is restarted, `nodetool -p 7199 pausehandoff` stops dispatch, and `nodetool -p 7199 resumehandoff` starts it after node 2 is UN, its
>   schema agrees with node 1's (`nodetool describecluster` shows one schema version) and a 20 s baseline window has been sampled. Reason (group B/C):
>   the filed procedure gives no pre-delivery window for the `[B` baseline, since dispatch can begin at the first 10 s trigger after node 2 is seen
>   alive; and a hint delivered before node 2 knows table `hp.standard1` is dropped by `HintVerbHandler` (`hint == null`, `HintVerbHandler.java:61-69`)
>   without a `Hint` instance on node 2.

**B3d. Observables and instruments.** (1) Node 1 `HPCAP page` lines (stdout/system.log): sent, bytes per page. (2) Node 2 live `Hint` instances: `jcmd <pid2> GC.class_histogram | awk '$4=="org.apache.cassandra.hints.Hint"{print $2}'` every 2 s during delivery (forces a full GC, so only live objects are counted), and the `[B` total bytes from the same histogram. (3) `nodetool -p 7199 listpendinghints` before and after (total backlog N). Not observable directly: the bytes of the outbound queue on node 1.

> **Amendment B3d (2026-10-26, stage-4 audit, before any run-1 reading).**
> 1. **Node 1 lines.** `HPCAP page sent=<n> bytes=<b> action=<CONTINUE|ABORT>` as filed, plus `HPCAP file start ms=…`, `HPCAP file end result=… ms=…`
>    and `HPCAP decoded total=…` (amendment B3a), in node 1's stdout `node1.out`. k for an arm = the `sent` of its non-last pages (pages that are not
>    the last of their file); "the last page of a file" is the last page line before that file's `file end`.
> 2. **Node 2 sampler.** A shell loop runs `jcmd <node-2 pid> GC.class_histogram` (live objects only: it forces a full GC) back to back, at most one
>    start per 2 s, from node 2's launch until the tail ends, and writes to `hist.txt` a `#SAMPLE t0=<epoch ms> t1=<epoch ms>` line followed by the
>    raw histogram lines for `org.apache.cassandra.hints.Hint` and `[B` and the `Total` line (a sample with no `Hint` line has count 0); other output
>    is written as `ERR …`.
> 3. **Windows.** Baseline window = from the `baseline-start` mark to the `baseline-end` mark (20 s, node 2 UN, handoff paused). Delivery window =
>    from the `resume` mark to the `delivery-end` mark. A sample belongs to the window that contains its t0. Baseline `[B` = the median `[B` bytes of
>    the baseline samples; the `[B` reading of B3f is (max `[B` over the delivery samples) − baseline `[B`.
> 4. **Counters.** `listpendinghints` is recorded before and after as filed, but it lists only files queued for dispatch, not the open writer nor the
>    file being dispatched (`HintsStore.java:108-125`), so it is not evidence of the backlog. The backlog is read by `HpJmx` (a JMX client in the
>    harness folder; `nodetool sjk mx` exits 0 on failure): node 1's `Storage.TotalHints` (written; N expected) and `HintsService.HintsSucceeded`,
>    `HintsFailed`, `HintsTimedOut`, before `pausehandoff` and after the tail. The `.hints` files in node 1's hints directory are listed before and
>    after.

**B3e. Procedure.** Per v: 1. wipe data, start nodes, wait UN/UN. 2. Stop node 2, run stress (B3c), flush, wait 15 s, record `listpendinghints`. 3. Start the 2 s histogram sampler against node 2's pid once it is up; start node 2 with Byteman. 4. When `listpendinghints` on node 1 is empty (or 10 min), stop the sampler. 5. `grep HPCAP` node 1 log. 6. Drain and kill both nodes.

> **Amendment B3e (2026-10-26, stage-4 audit, before any run-1 reading).** One script, `cassandra/stage4-runtime-verification/harness/hints_PAGE_SIZE-computeNext-position--autonomous/cluster-run.sh`, runs the arms 16k, 64k, 1m in order. Per arm:
> 1. wipe, write both yamls, start node 1 then node 2, wait for UN/UN and `statusbinary` running;
> 2. `nodetool -p 7299 drain`, kill node 2, wait until node 1 shows `DN 127.0.0.2`; stress (amendment B3c); `nodetool -p 7199 flush`; wait 15 s;
>    record `listpendinghints`, the JMX counters and the hints directory; `nodetool -p 7199 pausehandoff`;
> 3. start node 2 with `hp2.btm` and the sampler; wait for UN and `statusbinary`; wait for schema agreement (≤ 60 s); 20 s baseline window;
>    `nodetool -p 7199 resumehandoff`;
> 4. poll every 5 s until `listpendinghints` on node 1 is empty **and** node 1's hints directory holds no `.hints` file (a file is deleted only after
>    its whole dispatch, `HintsDispatchExecutor.java:296-300`), or 600 s; then a 10 s tail; stop the sampler; record the counters again;
> 5. extract the `HPCAP` lines; 6. drain and stop both nodes; check no daemon is left; delete the node directories.
> Every mark is logged with epoch ms and the byte offset of `node1.out`. *The filed stop condition ("`listpendinghints` empty") was found in cluster
> shakedown 1 (64k, N = 512) to fire while the only file was still being dispatched (only 352 of 512 hints delivered at the end); defect S1, fixed here
> before the freeze; §9a unchanged.*

**B3f. Predictions.** Node 1: every page line has `action=CONTINUE` (no timeouts), and for all pages but the last of each file, sent = ⌈524,288 / (bytes/sent + 12)⌉ — 32 ± 1 at 16 KiB, 8 at 64 KiB, 1 at 1 MiB — and bytes < 524,288 + v + 100. Node 2: maximum sampled `Hint` count ≤ k + 2 (k from node 1's lines) in every arm, median > 0, while N is 16,384 / 4,096 / 256; the maximum ratio Hint-count / k ≤ 1.1. The `[B` total during delivery exceeds its pre-delivery baseline by ≤ k × v + 8 MiB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| sent per page = k, node-2 Hint count ≤ k + 2, scaling 32 : 8 : 1 | both parts confirmed: the page caps outstanding hints and the receiver's hint heap |
| sent per page = k but node-2 Hint count ≫ k (approaching N) | part (2) wrong: the page caps the operand, not node memory |
| sent per page ≫ k (e.g. whole file) | part (1) wrong on the node |
| `action=ABORT` on most pages | not confirmed: the hold caused timeouts; lower the sleep or raise the timeout and rerun |
| Hint count always 0 | not confirmed: sampling missed the hold windows or hints were not dispatched |

> **Amendment B3g (2026-10-26, stage-4 audit, before any run-1 reading).** Verdict words, definitions and added rows. "Confirmed" means B1 held; all three arms are needed for it.
> - Row 1 holds when, in every arm: every page line has `action=CONTINUE`; every non-last page has sent = ⌈524,288 / (bytes/sent + 12)⌉ = k, with
>   k = 31–33 (16k), 8 (64k), 1 (1m), and no page has sent > k; every page has bytes < 524,288 + v + 100; the node-2 maximum sampled `Hint` count over
>   the delivery window is ≤ min(k + 2, ⌊1.1 k⌋) and ≥ ⌈k / 2⌉ (the receiver held a page's worth: the limit was reached), and its median is > 0; the
>   `[B` reading is ≤ k × v + 8 MiB; and across arms the maximum counts are ordered 16k > 64k > 1m ("scaling 32 : 8 : 1") → **Confirmed**. Effect:
>   **caps**.
> - Row 2 (sent per page = k, but a node-2 maximum `Hint` count > k + 2 in an arm) → **Refuted** (part 2). Effect: **does not cap** (node memory).
> - Row 3 (a non-last page with sent > k from the formula, e.g. the whole file in one page) → **Refuted** (part 1). Effect: **does not cap**.
> - Row 4 (`action=ABORT` on most pages) → **Not confirmed**, as filed; `ABORT` on any page fails B3f's first prediction and also gives **Not
>   confirmed**. Effect: **undetermined**.
> - Row 5 (`Hint` count always 0) → **Not confirmed**, as filed. Effect: **undetermined**.
> - Added: the maximum `Hint` count < ⌈k / 2⌉ in an arm, or the maxima not ordered → **Not confirmed** (the receiver never held a page; the limit was
>   not reached on node 2). Effect: **undetermined**.
> - Added: every `Hint` reading as in row 1 but the `[B` reading > k × v + 8 MiB → **Not confirmed** (the hint count is capped, but node-2 heap grew by
>   more than the held hints; another consumer the instrument cannot separate). Effect: **undetermined**.
> - Added: any other B3f prediction fails (a maximum in (⌊1.1 k⌋, k + 2], a non-last page with sent < k, a bytes bound exceeded) → **Not confirmed**.
>   Effect: **undetermined**.
> - **Invalid:** a node died; stress errors > 0 or partitions ≠ N; node 2 not DN during stress; no schema agreement; the backlog not delivered
>   within 600 s; node 1's TotalHints ≠ N, or HintsSucceeded rose by ≠ N; a Byteman rule error; no page lines; a `decoded` line (the counted path was
>   not the one used); fewer than 5 baseline samples.
> - Arms combine: Refuted in any arm → Refuted; otherwise Invalid in any arm → Invalid; otherwise Not confirmed in any arm → Not confirmed.

**B3h. Controls.** The backlog N ≫ k is the positive control: without the page cap, the receiver would hold up to N (or 64 running + the rest queued) hints at once; varying v shows the node-2 count moves with k; `listpendinghints` before/after shows the backlog was delivered; `max_hints_delivery_threads: 1` and one target host ensure exactly one dispatcher.

> **Amendment B3h (2026-10-26, stage-4 audit, before any run-1 reading).** Added controls: the baseline samples (node 2 UN, handoff paused) must show `Hint` count 0, so a non-zero count during
> delivery comes from dispatch; node 1's TotalHints = N and HintsSucceeded + N show the whole backlog was written and delivered (`listpendinghints`
> cannot show it, amendment B3d); no `HPCAP page` line before the `resume` mark shows the pause held.

**B4. Risks and cleanup.** Hints ≤ ~300 MiB and data ≤ 1 GiB per node under `~/hp-n*` on local disk, never in the shared clone. After each arm: drain and kill both nodes; `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` print nothing; `rm -rf ~/hp-n*/data`. At the end `rm -rf ~/hp-run ~/hp-n1 ~/hp-n2`. The unit JVM exits with Ant.

> **Amendment B4 (2026-10-26, stage-4 audit, before any run-1 reading).** On this host the nodes are `$W/node-hp1` and `$W/node-hp2` under `W=~/Library/Caches/stage4` (local SSD), deleted after each
> arm and at the end; the clone is `$W/cassandra-run37` and stays clean. Daemon checks use `pgrep -f` with the class-name pattern split in the scripts.

## C. Sources read

- `src/java/org/apache/cassandra/hints/HintsReader.java`
- `src/java/org/apache/cassandra/hints/HintsDispatcher.java`
- `src/java/org/apache/cassandra/hints/HintsDispatchExecutor.java`
- `src/java/org/apache/cassandra/hints/Hint.java`
- `src/java/org/apache/cassandra/hints/HintVerbHandler.java`
- `src/java/org/apache/cassandra/hints/ChecksummedDataInput.java`
- `src/java/org/apache/cassandra/hints/CompressedChecksummedDataInput.java`
- `src/java/org/apache/cassandra/net/Verb.java` (line 118)
- `conf/cassandra.yaml`
- `test/unit/org/apache/cassandra/hints/HintsReaderTest.java`
- https://byteman.jboss.org/

## D. Stage-4 feedback

**2026-10-26, stage 4 run 1** (advisor's machine; [results](../../stage4-runtime-verification/results/hints_PAGE_SIZE-computeNext-position--autonomous.md);
frozen at sha256 `86862af8…5a09` after twelve audit amendments; uncommitted).
- **Unit: Not confirmed — undetermined** (amended B2g row "a non-last page with c ≠ ⌈524,288 / e⌉ but P < 524,288 + e").
  - In 11 of 12 reads every page but the last held c = ⌈524,288 / e⌉ = 482 / 32 / 1 entries (e = 1,089 / 16,450 / 614,466 B), with
    P = 524,898 / 526,400 / 614,466 B. This holds for both iterators and for plain and LZ4 files, although the LZ4 files are 61× to 243×
    smaller. The cap counts uncompressed bytes.
  - The LZ4 file of 600 KiB entries gave 28 pages, not 14: empty pages (c = 0, P = 0, each with an `Unexpected EOF replaying hints … continuing`
    warning) alternate with c = 1. From source, `HintsWriter.Session.append(ByteBuffer)` (`:205-210`) flushes an empty aggregation buffer before
    an entry larger than its free space. `CompressedHintsWriter.writeBuffer` (`:48-69`) then writes a zero-length chunk, which ends the page early
    on read. The production writer uses the same path with a 256 KiB buffer (`HintsWriteExecutor.java:50, 241-245`), so `hints_compression` with
    hints over 256 KiB likely does the same on a node. Not run on a node.
  - No page in any read exceeded 524,288 + e. Claim (1)'s wording "each page contains k" is what fails.
- **Cluster: Confirmed — caps** (B3g row 1). Two nodes; backlogs of N = 16,384 / 4,096 / 256 hints of 16 KiB / 64 KiB / 1 MiB; node 2 holds
  each hint 300 ms.
  - Every page was `CONTINUE`. Non-last pages carried k = 32 / 8 / 1 hints (= ⌈524,288 / (bytes/sent + 12)⌉).
  - Node 2's live `Hint` count peaked at exactly k (median k), against 0 with handoff paused. Its live `[B` rose by ≤ 1.39 MB.
  - HintsSucceeded rose by N with no failure or timeout.
- Audit amendments that stage 3 may want to carry:
  - `standardCFMD` does not build the filed table.
  - Random values cannot test the LZ4 arm.
  - A `heap_buffers` memtable on the receiver puts every delivered value into `[B`.
  - Stress `no-warmup`.
  - `listpendinghints` omits the open writer and the file being dispatched (`HintsStore.java:108-125`), so it cannot show that delivery is
    complete.
