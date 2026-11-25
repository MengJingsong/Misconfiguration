# dfs.data.transfer.max.packet.size — verification solution  <!-- file: cases/dfs.data.transfer.max.packet.size-initWritePacketSize-PacketReceiver.MAX_PACKET_SIZE--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DFSOutputStream.java:251`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DFSOutputStream.java#L251), `if (writePacketSize > PacketReceiver.MAX_PACKET_SIZE)` in `DFSOutputStream.initWritePacketSize()` |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `negative`. The check clamps only the private field `writePacketSize`. That field is read in one place, `adjustChunkBoundary()` (`DFSOutputStream.java:540`), which runs only after a packet has already been filled and queued. The first packet of every replicated create or append stream is sized from the raw `dfs.client-write-packet-size` (`:267`, `:362`, `:402`) and allocated in full (`:140-143`). So the largest client packet buffer follows the configured packet size, not `MAX_PACKET_SIZE`. |
| Ground | Usage side: the client heap byte[] of each `DFSPacket` (`PKT_MAX_HEADER_LEN + packetSize` bytes). `packetSize` comes from `computePacketChunkSize(psize, …)` (`:426-430`). In the constructors, `psize` is `dfsClient.getConf().getWritePacketSize()`, the unclamped value. The clamped value is not used there. The cap binds only from the second packet on. The first packet is up to the configured size (for example 256 MiB) whatever the value of `dfs.data.transfer.max.packet.size`. A first packet that holds more than `MAX_PACKET_SIZE` bytes is then refused by the DataNode's own check (`PacketReceiver.java:166`), which is a different enforcement point, and the write fails. The striped (EC) stream is the exception: its constructor calls `adjustChunkBoundary()` (`DFSStripedOutputStream.java:324` → `:364`) before the first packet. |

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (the check; the Entry pointer row above and
> A3). Use a permalink at the pinned tag,
> `[`File.java:123`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/<full path under the repository root>#L123)`
> (a range is `#L123-L130`). Check that the line number is the line you mean. Other citations may
> stay plain `file:line`.

Naming parts: constraint = `dfs.data.transfer.max.packet.size` (the key from which the limit-side constant
`PacketReceiver.MAX_PACKET_SIZE` is first initialized); function = `initWritePacketSize` (directly encloses the
given if); operand = `PacketReceiver.MAX_PACKET_SIZE` (limit-side operand as written at the check). The
usage-side operand is the field `writePacketSize` (from key `dfs.client-write-packet-size`).

## A. Constraint trace

**A1. The constraint.**
- Name: `dfs.data.transfer.max.packet.size`. Kind: configuration key, held in the static final int
  `PacketReceiver.MAX_PACKET_SIZE`.
- Declaration: key constant `HdfsClientConfigKeys.DFS_DATA_TRANSFER_MAX_PACKET_SIZE` at
  [`HdfsClientConfigKeys.java:244-245`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/HdfsClientConfigKeys.java#L244-L245).
  Default `DFS_DATA_TRANSFER_MAX_PACKET_SIZE_DEFAULT = 16 * 1024 * 1024` at `HdfsClientConfigKeys.java:246-247`.
- `hdfs-default.xml`: entry at `hadoop-hdfs/src/main/resources/hdfs-default.xml:4763-4769`, value `16777216`,
  "The max size of any single packet." The Java default and the XML value agree (16 MiB). The XML wins
  whenever `hdfs-default.xml` is on the classpath, which it is for every HDFS client and daemon.
- Unit: bytes.
- How it is read: once per JVM, in the static initializer `PacketReceiver.java:80-85`, which does
  `new HdfsConfiguration().getInt(...)`. That `Configuration` loads only the default resources
  (`hdfs-default.xml`, `hdfs-site.xml`, `hdfs-rbf-*.xml`; `HdfsConfiguration.java:37-40`) and whatever
  `Configuration.addDefaultResource(...)` registered before the class loads. Consequences:
  - It can be set only in `hdfs-site.xml` on the process classpath (`$HADOOP_CONF_DIR`).
  - A per-client `Configuration`, `hdfs dfs -D ...`, or a per-job setting does **not** change it.
  - A change needs a new JVM (daemon restart, or a new client process). It cannot be reconfigured at runtime.
- Who reads it: every JVM that loads `PacketReceiver`. That includes HDFS clients (this check, and
  `BlockReaderRemote`'s receiver) and DataNodes (`BlockReceiver`'s receiver, `BlockReceiver.java:96`).
  The client and the DataNode each use their own copy, from their own `hdfs-site.xml`.
- Related source (usage side of this check): `dfs.client-write-packet-size`
  (`HdfsClientConfigKeys.java:86-87`, default `64*1024`; `hdfs-default.xml:1308-1310`, 65536). It is read per
  `DFSClient` in `DfsClientConf.java:219-221` and can be set per client, including with `-D`.

**A2. What it caps.**
- Resource: memory. Specifically, the size of a single data-transfer packet buffer.
- At this check (client write side): the configured write packet size is clamped to at most `MAX_PACKET_SIZE`.
  The clamped value sets the byte[] the client allocates for each outgoing `DFSPacket`
  (`createPacket`, `DFSOutputStream.java:136-153`: `bufferSize = PKT_MAX_HEADER_LEN + packetSize`, allocated
  with `byteArrayManager.newByteArray(bufferSize)`; by default this is a plain `new byte[size]`,
  `ByteArrayManager.java:296-306`). It also bounds the size of the packet on the wire, which the DataNode
  checks against its own `MAX_PACKET_SIZE`.
- Quantity compared at the check: `writePacketSize`, the configured `dfs.client-write-packet-size` in bytes,
  against `PacketReceiver.MAX_PACKET_SIZE` in bytes.
- Heap use per stream is roughly (packets in flight, up to `dfs.client.write.max-packets-in-flight` = 80,
  `DataStreamer.java:1010-1011`) × (packet buffer size). The per-packet cap is meant to bound that product
  at about 81 × 16 MiB.

**A3. Mechanism.**
1. `DFSOutputStream` base constructor (`:193-243`) calls `initWritePacketSize()` at `:229`.
2. `initWritePacketSize()` (`:249-258`) sets `writePacketSize = dfsClient.getConf().getWritePacketSize()` (`:250`).
   Then the check
   [`DFSOutputStream.java:251`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DFSOutputStream.java#L251)
   runs `if (writePacketSize > PacketReceiver.MAX_PACKET_SIZE)`:
   - Over the limit: log WARN "Configured write packet exceeds {} bytes as max, using {} bytes." and set
     `writePacketSize = MAX_PACKET_SIZE` (`:252-256`). No exception is thrown.
   - At or under the limit: nothing happens. Equality is allowed.
3. **Where the clamped value is used: only `adjustChunkBoundary()`** (`:531-543`). There,
   `psize = min(blockSize - bytesCurBlock, writePacketSize)` (`:539-540`) and then
   `computePacketChunkSize(psize, bytesPerChecksum)`. `adjustChunkBoundary()` is called from
   `enqueueCurrentPacketFull()` (`:509-517`), *after* the current packet is full and queued, and from
   `DFSStripedOutputStream.setCurrentStreamer` (`:364`).
4. **Where the clamp is bypassed: the raw configured value sets the first packet's size.**
   - Create (replicated): the constructor at `:261-274` calls
     `computePacketChunkSize(dfsClient.getConf().getWritePacketSize(), bytesPerChecksum)` at `:267`.
   - Append, new block: `:362`, same raw value.
   - Append to a partial last block: `adjustPacketChunkSize` `:401-403`,
     `min(dfsClient.getConf().getWritePacketSize(), freeInLastBlock)`.
   - Effect: `computePacketChunkSize` (`:426-430`) sets
     `chunksPerPacket = max((psize-33)/516, 1)` and `packetSize = 516*chunksPerPacket`
     (with `PKT_MAX_HEADER_LEN` = 33 and CRC32C 4-byte checksum per 512 B chunk).
   - The first write calls `writeChunkPrepare` (`:494-495`), which calls `createPacket(packetSize, …)` and
     allocates `33 + packetSize` bytes at once, before any data is written into the packet.
   - Only after that packet fills (`:452-455`) does `adjustChunkBoundary` shrink the size of later packets to
     the clamped value.
5. Worked numbers (bytes):

   | configured | clamped `writePacketSize` (MAX=16777216) | first packet buffer | later packet buffers | data in a full first packet |
   |---|---|---|---|---|
   | 65536 | 65536 | 65049 | 65049 | 64512 |
   | 16777216 | 16777216 | 16776741 | 16776741 | 16646656 |
   | 33554432 | 16777216 | **33553965** | 16776741 | 33293824 |
   | 268435456 | 16777216 | **268435101** | 16776741 | 266354176 |

   With `MAX` = 4194304 (4 MiB) and a configured size of 8388608: clamped value 4194304, first buffer
   **8388129**, later buffers 4194081.
6. Downstream effect when the first packet carries more than `MAX`:
   - The DataNode's `BlockReceiver.receivePacket` (`BlockReceiver.java:553`) calls
     `PacketReceiver.receiveNextPacket`, which throws
     `IOException("Incorrect value for packet payload size: …")` when `payloadLen + headerLen > MAX_PACKET_SIZE`
     (`PacketReceiver.java:164-169`). This is the DataNode's own check against its own `MAX`.
   - The pipeline breaks, and resending the same packet fails again. With one DataNode the write fails.
   - So when the configured size is above MAX, a replicated write whose first packet fills past MAX (more than
     about 16.6 MB of data in the first block) **fails**. A smaller write succeeds, but it has still allocated
     the full oversized first buffer.
7. Other bypasses and overshoots:
   - `setChunksPerPacket` (`:1031-1034`) is test-only and can only shrink.
   - `DataStreamer.computeTransferReadTimeout` (`DataStreamer.java:1576`) uses the raw value. It affects a
     timeout only.
   - The EC path is clamped before its first packet: `DFSStripedOutputStream` constructor `:324`
     → `setCurrentStreamer` → `adjustChunkBoundary` `:364`.
8. The existing test `TestDFSOutputStream#testPreventOverflow` (`TestDFSOutputStream.java:169-185`) sets
   1000 MiB, calls `adjustChunkBoundary` by reflection, and asserts the clamped `writePacketSize`,
   `chunksPerPacket` and `packetSize`. It never writes data. That is why it does not see the first-packet
   bypass: it overwrites `packetSize` through the clamped path before any packet exists.

**A4. Other consumers.**
- Packets in flight: up to `dfs.client.write.max-packets-in-flight` (80) + 1 packets per stream
  (`DataStreamer.java:1010-1011`). Total client packet heap is about that count × the buffer size; no single
  limit covers the total.
- `ByteArrayManager`, if `dfs.client.write.byte-array-manager.enabled=true` (default false,
  `HdfsClientConfigKeys.java:417-421`): it rounds allocations up to a power of two (`ByteArrayManager.java:361`)
  and keeps arrays for reuse. That adds to the per-packet figure.
- `FSOutputSummer` buffer: 9 × `bytesPerChecksum` (`FSOutputSummer.java:51-56`), small.
- EC streams: cell buffers of `cellSize` × number of units (`DFSStripedOutputStream.java:215-223`).
- Read side: `BlockReaderRemote`'s `PacketReceiver(true)` uses a direct buffer that grows to the largest packet
  received (`PacketReceiver.java:273-283`). It is bounded by the reader's own MAX check at `:166`, not by this one.
- DataNode side: `BlockReceiver`'s heap `PacketReceiver(false)` buffer, bounded by the DN's `:166` check.
- Other JVM heap of the client: RPC, `DFSClient`, and so on.

**A5. Evidence beyond the source.**
- HDFS-11608, "HDFS write crashed with block size greater than 2 GB"
  (https://issues.apache.org/jira/browse/HDFS-11608; fix versions 2.7.4, 2.8.2, 2.9.0, 3.0.0-alpha4). The report
  shows a client OOM and the DataNode error "Incorrect value for packet payload size". The patch contents
  were not visible on the page. `testPreventOverflow` and `initWritePacketSize` match that fix, but this is
  inferred, not confirmed.
- HDFS-15469, "Dynamically configure the size of PacketReceiver#MAX_PACKET_SIZE"
  (https://issues.apache.org/jira/browse/HDFS-15469; fix version 3.4.0). This made the 16 MiB constant
  configurable. The page does not name the key.
- Test `TestDFSOutputStream#testPreventOverflow` (A3 step 8) and `TestPacketReceiver` (`:63-64`, asserts the
  default).

## B. Verification solution

**B1. Claim under test.**
- Main claim: with `dfs.client-write-packet-size` > `dfs.data.transfer.max.packet.size`, a replicated HDFS
  output stream still allocates its first packet buffer at the *configured* size
  (`33 + 516·⌊(C−33)/516⌋` bytes). That is above the cap, and it follows the configured value C, not MAX.
  Only the packets after the first are capped at about MAX.
- Consequence: a write whose first packet fills past MAX fails at the DataNode.
- If the first-packet buffer is ≤ MAX + 33 for every C > MAX, the claim is wrong and the cap holds.

### B2. Unit tier

**B2a. Environment and build.**
- Toolchain: JDK 8 and Maven 3.3+.
- Source: copy the tree to local disk, for example
  `rsync -a ~/hadoop-3.4.2/ /mydata/<run>/hadoop-src/`. Do not build in the shared copy.
- Build:
  ```
  cd /mydata/<run>/hadoop-src
  mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true
  ```
- New test sources in `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/`
  (package `org.apache.hadoop.hdfs`, so the protected fields `packetSize`, `chunksPerPacket` and
  `currentPacket` are reachable):
  - `TestWritePacketSizeCap.java`: uses the default MAX of 16 MiB.
  - `TestWritePacketSizeCap4M.java`: uses MAX = 4 MiB.
- New resource `hadoop-hdfs-project/hadoop-hdfs/src/test/resources/maxpkt-4m-site.xml`:
  ```xml
  <configuration><property><name>dfs.data.transfer.max.packet.size</name><value>4194304</value></property></configuration>
  ```
  `TestWritePacketSizeCap4M` registers it in a `static {}` block with
  `Configuration.addDefaultResource("maxpkt-4m-site.xml");`, before anything touches `PacketReceiver`.
  Surefire runs each test class in its own JVM (`reuseForks=false`, `hadoop-project/pom.xml:2467`,
  `hadoop-hdfs/pom.xml:477`), so the static value is fresh for each class.
- JVM: the module default `-Xmx2048m` (`hadoop-project/pom.xml:187`).
- Test data: `MiniDFSCluster` with 1 DataNode, `dfs.replication=1`, base dir under the module `target/`
  (local disk).

> **Amendment A1 (2026-11-25, stage-4 audit, before any reading):** Paths and build on the stage-4 node. The local copy is `/mydata/jingsong-s4/<stem>-run1/src` (made with `jingsong/copy-source.sh`, not `~/hadoop-3.4.2`). No `install` build is run: every 3.4.2 module is already in `~/.m2` from the node's base build of the same source (`environment.md` §3), so the tests run with `mvn -B -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=<Class> -DfailIfNoTests=false` from the copy's root. Surefire failures do not fail `mvn test` in this build: read the surefire counts, not the exit code. JDK 8 (`/usr/lib/jvm/java-8-openjdk-amd64`) is exported as `JAVA_HOME` explicitly.


> **Amendment A2 (2026-11-25, stage-4 audit, before any reading):** The 4 MiB class's `static {}` block must first load `HdfsConfiguration` (`new HdfsConfiguration();` or `HdfsConfiguration.init();`) and only then call `Configuration.addDefaultResource("maxpkt-4m-site.xml")`. Default resources are loaded in the order they are added and later ones win; added first, `maxpkt-4m-site.xml` would be overridden by `hdfs-default.xml`, which `HdfsConfiguration`'s static initializer adds after it (`HdfsConfiguration.java:33-40`). The assertion `PacketReceiver.MAX_PACKET_SIZE == 4194304` (B2e step 3) stays and would catch this.


**B2b. Knobs.**
- `dfs.client-write-packet-size` (C), set with `conf.setInt` on the `MiniDFSCluster` conf. Values:
  - 65536: default, control.
  - 16777216: equal to MAX, the boundary. Not clamped.
  - 33554432: 2 × MAX.
  - 268435456: 16 × MAX. Fits within `-Xmx2048m`.
- MAX: 16777216 (default class) and 4194304 (4M class).
- In the 4M class, C ∈ {4194304 (= MAX, control), 8388608 (2 × MAX)}.
- Each C gets a fresh cluster (or at least a fresh `FileSystem`).

**B2c. Workload.**
- For each C, create `/t/small` and write `S` bytes, where S = 1 MiB (1048576), in 64 KiB `write` calls. Then
  `hflush()` and `close()`. The first packet holds only 1 MiB, far below MAX on the wire, so the DataNode
  accepts it.
- For each C, also create `/t/big` (block size 128 MiB) and write 48 MiB (50331648 bytes), then `close()`.
  - For C = 33554432, the first packet fills at 33293824 data bytes, below the 48 MiB written. On the wire it
    is 4 + 65027·4 + 33293824 + 27 ≈ 33.55 MB, which is more than 16777216, so the DataNode should refuse it.
  - For C = 268435456, the first packet does not fill within 48 MiB. It is sent at `close()` carrying 48 MiB,
    more than MAX, so the DataNode should refuse it.
  - For C = 16777216, full packets are 16776739 B on the wire, which is ≤ MAX, so the write succeeds.
- 4M class: C = 8388608, with the same small and big writes.
  - Full first packet: 8323072 data bytes, about 8.39 MB on the wire. That is more than the DataNode's MAX of
    4 MiB (DataNode and client share the JVM), so it is refused.

**B2d. Observables and instruments.** All are read inside the test, through Whitebox or reflection where the
field is private.
- (a) `writePacketSize` right after `create()`. This is the check's own operand after clamping.
- (b) `packetSize` and `chunksPerPacket` right after `create()`.
- (c) Length of the first packet's byte[]: after the first 64 KiB `write`, read `dos.currentPacket`, then its
  private field `buf`, then `.length`.
- (d) Bytes allocated by the writing thread during the first `write` call:
  `((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId())`,
  read before and after.
- (e) For the big write: `packetSize`, and the length of `currentPacket.buf` on the first new packet after
  the first full one. Observe this by writing exactly `chunksPerPacket·512` bytes, then one more 512 B chunk,
  then reading `currentPacket.buf.length`.
- (f) Whether `close()` throws an `IOException`, and its message. Also the DataNode log line
  "Incorrect value for packet payload size", captured with `GenericTestUtils.LogCapturer` on the
  `PacketReceiver` / `DataNode` loggers.
- (g) The client WARN "Configured write packet exceeds" (LogCapturer on the `DFSOutputStream` logger).

> **Amendment A3 (2026-11-25, stage-4 audit, before any reading):** How (e), (f) and (g) are read. (e): the big file is written in 64 KiB `write` calls; the first packet object is taken from `currentPacket` after the first call, and after each later call the test checks whether `currentPacket` is a different, non-null object; the first such object is the second packet, and (e) is its `buf.length` (with `packetSize` and `chunksPerPacket` at that moment). FSOutputSummer hands chunks to `writeChunk` in groups of up to 9 (`FSOutputSummer.java:51-56`), so "exactly `chunksPerPacket`·512 bytes, then one more chunk" is not observable at a `write` boundary; the identity change is. If the stream fails before a second packet exists, (e) is recorded as `none` (expected only for C = 268435456, whose first packet never fills). (f): the DataNode's refusal can surface in a later `write`, in `hflush` or in `close`; the test records which call threw first, the exception class and message, and the file length the NameNode reports afterwards. The DataNode line "Incorrect value for packet payload size" and the client WARN (g) are counted in the test's surefire output file (`*-output.txt`, which holds the in-JVM DataNode and client log), between per-test `BEGIN`/`END` marker lines the test prints; LogCapturer is not needed. Test timeout 300 s per test (pipeline recovery with one DataNode retries before failing).

> **Amendment A7 (2026-11-25, runbook defect found in unit run 1, attempt 1; B2f, B2g and B2h unchanged):** the first
> `write` of each file is **4608 bytes** (one FSOutputSummer group of 9 chunks), not 64 KiB, and (c) and (d) are read
> after it; the rest of the file follows in 64 KiB writes (the last one shorter) to exactly 1 MiB / 48 MiB. Reason: at
> C = 65536 the first packet holds 126 chunks (64512 B), so a 64 KiB first write fills and queues it before (c) is read
> and `currentPacket` is null (attempt 1 read -1). 9 chunks cannot fill a packet at any C in B2b. The unit tier
> restarts from its beginning.

- Not observable here: the real resident memory of a separate client process. That is measured in the
  cluster tier.

**B2e. Procedure.**
1. Write both test classes. Each has one `@Test` per C. Each test does:
   1. Build the cluster.
   2. `create`.
   3. Read (a) and (b).
   4. `write` 64 KiB; read (c) and (d).
   5. Write the rest of the small file and `close`; record (f).
   6. Repeat with `/t/big`: (e) and (f).
   7. Print every value on one `RESULT C=… MAX=… …` line.
   8. Shut the cluster down.
2. Run the default-MAX class:
   ```
   mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestWritePacketSizeCap
   ```
3. Run the 4 MiB class:
   ```
   mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestWritePacketSizeCap4M
   ```
   The test first asserts `PacketReceiver.MAX_PACKET_SIZE == 4194304`.
4. Collect the `RESULT` lines from `target/surefire-reports/*-output.txt`.

**B2f. Predictions.** Bytes; these follow from A3 step 5.

| MAX | C | (a) writePacketSize | (b) packetSize after create | (c) first buf | (d) first-write alloc | (e) 2nd-packet buf | small write | big write |
|---|---|---|---|---|---|---|---|---|
| 16777216 | 65536 | 65536 | 65016 | 65049 | ≈ 65 KB + small | 65049 | ok | ok |
| 16777216 | 16777216 | 16777216 | 16776708 | 16776741 | ≈ 16.78 MB | 16776741 | ok | ok |
| 16777216 | 33554432 | **16777216** | **33553932** | **33553965** | ≈ 33.55 MB | 16776741 | ok | **fails**, DN "Incorrect value for packet payload size" |
| 16777216 | 268435456 | **16777216** | **268435068** | **268435101** | ≈ 268.4 MB | n/a (first never fills) | ok | **fails** at close |
| 4194304 | 4194304 | 4194304 | 4194048 | 4194081 | ≈ 4.19 MB | 4194081 | ok | ok |
| 4194304 | 8388608 | **4194304** | **8388096** | **8388129** | ≈ 8.39 MB | 4194081 | ok | **fails** |

The WARN (g) should appear exactly when C > MAX.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| For C > MAX, (a) = MAX but (c) = 33 + 516⌊(C−33)/516⌋ > MAX, and (c) grows with C (33.55 MB → 268.4 MB) | Usage follows the configured size, not the cap, for the first packet. **Claim confirmed** (negative estimate). |
| For C > MAX, (c) ≤ MAX + 33 (for example 16776741) | The clamp does govern the first packet. **Claim refuted**; the estimate becomes positive. |
| (e) second-packet buffer = 33 + 516⌊(MAX−33)/516⌋ when C > MAX | Positive control: the cap binds where `adjustChunkBoundary` runs, with the same workload. |
| (e) also equals the unclamped size | The clamp is not effective anywhere. Still a negative, for a different reason; record it. |
| (c) for C = 65536 is not 65049, or (a) differs from C when C ≤ MAX | The instrument or arithmetic is wrong. **Not confirmed**; fix the reflection before reading the other rows. |
| Big write succeeds with C > MAX | The DataNode accepted a packet larger than MAX, or the first packet was split. Recheck the DN MAX value; this contradicts A3 step 6. |
| (d) far below (c) | The allocation was satisfied elsewhere (for example ByteArrayManager enabled). Check the config. |

**B2h. Controls.**
- C = 65536 and C = MAX run the same code path with no clamp.
- The second packet in the same stream is the in-stream positive control.
- The 4 MiB class shows the relation scales with MAX, not just the 16 MiB constant.
- Assert `ByteArrayManager` is the default `NewByteArrayWithoutLimit`
  (`dfs.client.write.byte-array-manager.enabled` unset), so (c) equals the allocation.
- Thread-allocated bytes (d) cross-checks (c) without reflection.
- The fresh JVM per class rules out a stale static MAX.

### B3. Cluster tier

**B3a. Environment and build.**
- Host: one Linux host, at least 8 GB RAM and at least 10 GB free local disk under `/mydata/<run>/`.
- Toolchain: JDK 8 (JDK 11 also fine for running; JFR is needed, see B3d).
- Build the distribution from the local copy:
  ```
  mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true
  ```
  Then unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `/mydata/<run>/hadoop`.
- Daemons: pseudo-distributed, with 1 NameNode, 1 DataNode, no YARN.
  `HADOOP_CONF_DIR=/mydata/<run>/conf-dn` (the daemon conf), `HADOOP_LOG_DIR=/mydata/<run>/logs`,
  `HADOOP_PID_DIR=/mydata/<run>/pids`, `HADOOP_HEAPSIZE_MAX=1g` for the daemons.
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:<free port, e.g. 19000>`,
  `hadoop.tmp.dir=/mydata/<run>/tmp`.
- `hdfs-site.xml` (daemon):
  - `dfs.replication=1`
  - `dfs.namenode.name.dir=/mydata/<run>/nn`
  - `dfs.datanode.data.dir=/mydata/<run>/dn`
  - `dfs.namenode.http-address=localhost:19870`
  - `dfs.datanode.address=localhost:19866`, `dfs.datanode.http.address=localhost:19864`,
    `dfs.datanode.ipc.address=localhost:19867` (avoid default-port clashes on a shared host)
  - `dfs.data.transfer.max.packet.size` left at its default (16777216), except in run set 3.
- Client conf dirs (copies of `conf-dn` with only `hdfs-site.xml` changed):
  - `/mydata/<run>/conf-c16`: MAX at its default.
  - `/mydata/<run>/conf-c4`: `dfs.data.transfer.max.packet.size=4194304`.
- Client JVM: `unset HADOOP_HEAPSIZE_MAX`. Set
  ```
  HADOOP_CLIENT_OPTS="-Xmx<H> -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/mydata/<run>/dumps -XX:StartFlightRecording=filename=/mydata/<run>/jfr/<tag>.jfr,settings=profile"
  ```
  - JDK 8u262+ supports `-XX:StartFlightRecording`. If the JDK 8 at hand does not, run the client on JDK 11.
  - Client `-Xmx` comes last on the command line and so wins.
- Format and start:
  ```
  hdfs namenode -format
  start-dfs.sh
  hdfs dfs -mkdir /t
  ```

**B3b. Knobs.**
- `dfs.client-write-packet-size` (C), per client command, with
  `hdfs dfs -D dfs.client-write-packet-size=<C> -put …`. FsShell is a Tool, so `-D` reaches `DfsClientConf`.
  No restart is needed.
- Client MAX: chosen by `HADOOP_CONF_DIR`, `conf-c16` or `conf-c4`. A new client JVM per command picks it up.
- DataNode MAX: edit `conf-dn/hdfs-site.xml`, then `hdfs --daemon stop datanode; hdfs --daemon start datanode`.
- Client heap H: 192m by default, 1024m for one control.
- Run sets:

  | Set | Client MAX | DN MAX | C values | H |
  |---|---|---|---|---|
  | 1 | 16M | 16M | 65536, 16777216, 33554432, 268435456 | 1024m |
  | 2 | 16M | 16M | 268435456 | 192m (heap-bound test) |
  | 2-ctl | 16M | 16M | 16777216 | 192m (control) |
  | 3 | 4M | 16M (default; DN accepts first packet ≤ 16M) | 4194304, 8388608 | 1024m |

**B3c. Workload.**
- Local input files on `/mydata/<run>/in/`:
  - `f1m`: 1 MiB, from `head -c 1048576 /dev/urandom`.
  - `f48m`: 48 MiB.
- Commands, one client JVM per command:
  ```
  hdfs dfs -D dfs.client-write-packet-size=<C> -put -f <file> /t/<tag>
  ```
- Arithmetic:
  - `f1m` leaves the first packet partly full (1 MiB, below every MAX), so on the wire it is always accepted.
    Only the client buffer size differs.
  - `f48m`:
    - C = 33554432 fills the first packet at 33293824 bytes and sends about 33.55 MB, which the DataNode refuses.
    - C = 268435456 sends 48 MiB at close, which is refused.
    - C = 16777216 sends packets ≤ 16776739 B, which are accepted.
  - Set 3, C = 8388608 with `f48m`: the first packet holds 8323072 data bytes, about 8.39 MB on the wire. That is
    ≤ the DataNode's 16 MiB, so it is accepted. The rest are ≤ 4194081 B.
- Each command takes a few seconds.

> **Amendment A4 (2026-11-25, stage-4 audit, before any reading):** Cluster set-up on the stage-4 node. The distribution is copied from the node's base build (`cp -a /mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2 <run>/hadoop`, `environment.md` §4), which is built from the same pinned source; it is not rebuilt. SSH to `localhost` does not work on these nodes, so `start-dfs.sh` / `stop-dfs.sh` are replaced by `hdfs --daemon start|stop namenode` and `hdfs --daemon start|stop datanode`; no SecondaryNameNode is started (it plays no part in a write). `dfs.namenode.rpc-address` is the `fs.defaultFS` port 19000; the B3a ports are used and checked free with `ss -ltn` first. `JAVA_HOME` is the JDK 8 path (8u514, which has JFR and `jfr`). The client options add `dumponexit=true` to `-XX:StartFlightRecording` so the recording is written however the client JVM ends, and the client heap actually in force is read from the recording's `jdk.JVMInformation` / `jdk.GCHeapConfiguration` events (a known-answer check of `-Xmx`). The file argument is `-put -f <file> /t/<tag>`; between runs `hdfs dfs -rm -f -skipTrash /t/*`.


**B3d. Observables and instruments.**
- (1) JFR, `jdk.ObjectAllocationOutsideTLAB` events (enabled in the `profile` settings; packet arrays are far
  larger than a TLAB):
  ```
  jfr print --events jdk.ObjectAllocationOutsideTLAB /mydata/<run>/jfr/<tag>.jfr
  ```
  Keep the `byte[]` events whose stack has `DFSOutputStream.createPacket`. Record each `allocationSize` in
  order. The first such event is the first packet buffer. Array objects carry a 16-byte header, so expect
  buffer length + 16.
- (2) Client exit code and stderr: OutOfMemoryError, or "All datanodes … are bad" / IOException.
- (3) Client stderr WARN "Configured write packet exceeds 16777216 bytes as max".
- (4) DataNode log (`/mydata/<run>/logs/hadoop-*-datanode-*.log`): `grep "Incorrect value for packet payload size"`.
- (5) `hdfs dfs -ls /t` and `hdfs fsck /t/<tag> -files -blocks`: was the file completed, and at what length?
- (6) For set 2, the heap dump file presence and size (an OOM dump in `/mydata/<run>/dumps`).
- (7) Optional: GC log `-verbose:gc -XX:+PrintGCDetails -Xloggc:/mydata/<run>/gc-<tag>.log` (JDK 8). Old-gen
  occupancy jumps by about C at the first write.
- Not observable directly: which Java statement chose the size. JFR stack frames give
  `createPacket` ← `writeChunkPrepare`, and that is the link to the code.

> **Amendment A5 (2026-11-25, stage-4 audit, before any reading):** Reading the JFR sizes. `allocationSize` of a `byte[]` is the array length plus the 16-byte header, rounded up to a multiple of 8, so the expected value is `ceil((L + 16)/8)·8` for a buffer of length L (for example 65049 → 65072, 16776741 → 16776760, 33553965 → 33553984, 268435101 → 268435120, 8388129 → 8388152, 4194081 → 4194104). A reading matches when it equals that value. So that every packet buffer, including the 65049-byte one of the C = 65536 control, is an allocation outside a TLAB, the client options also get `-XX:TLABSize=16k -XX:-ResizeTLAB` (a fixed 16 KiB TLAB: any array above it is allocated outside one); `jdk.ObjectAllocationInNewTLAB` events with a `createPacket` frame are read as well, as a backup. Only `byte[]` events whose stack contains `DFSOutputStream.createPacket` are counted; packet buffers of length 33 (`createPacket(0, …)`, the end-of-block packet) and any below 1 KiB stay in TLABs or are ignored. 'First buffer' is the first such event of the run; 'later buffers' are the rest that are not the end-of-block packet. Set 2: the `OutOfMemoryError` is read from the client's stderr; the JFR recording of an OOM run may still lack the allocation event (the allocation did not succeed), which is not an instrument failure for set 2.


**B3e. Procedure.**
1. Build, unpack, write the configs, format, `start-dfs.sh`. Check `jps` shows NameNode, DataNode,
   SecondaryNameNode, and `hdfs dfsadmin -report` shows 1 live DN.
2. Set 1: for each C and each file (`f1m`, `f48m`), run with H = 1024m and a JFR file `s1-<C>-<file>.jfr`.
   Record (1) to (5). Run `hdfs dfs -rm -f /t/*` between runs.
3. Set 2 / 2-ctl: H = 192m, file `f1m`, C = 268435456, then C = 16777216. Record (2) and (6).
4. Set 3: `HADOOP_CONF_DIR=/mydata/<run>/conf-c4` for the client only (the DN stays at 16M). C ∈ {4194304,
   8388608}, files `f1m` and `f48m`, H = 1024m. Record (1) to (5).
5. Run `stop-dfs.sh`, then check `jps` shows no NameNode, DataNode or SecondaryNameNode.

> **Amendment A6 (2026-11-25, stage-4 audit, before any reading):** Step 1 and step 5 use `hdfs --daemon start|stop` (A4). After step 5 the check is `ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode'` and `jps` on the node; nothing of this run may remain.


**B3f. Predictions.** JFR first `createPacket` allocation ≈ buffer + 16 B.

| Set | C | `f1m` first buffer | `f48m` first buffer | `f48m` later buffers | `f48m` result |
|---|---|---|---|---|---|
| 1 | 65536 | 65049 | 65049 | 65049 | ok, 50331648 B |
| 1 | 16777216 | 16776741 | 16776741 | 16776741 | ok |
| 1 | 33554432 | **33553965** | **33553965** | 16776741 | **put fails**; DN log has "Incorrect value for packet payload size" |
| 1 | 268435456 | **268435101** | **268435101** | none | **put fails** at close; DN log line present |
| 3 | 4194304 | 4194081 | 4194081 | 4194081 | ok |
| 3 | 8388608 | **8388129** | **8388129** | 4194081 | ok (DN MAX 16M) |

- All `f1m` puts succeed in sets 1 and 3.
- WARN (3) appears exactly when C > client MAX.
- Set 2: C = 268435456 with `-Xmx192m` gives `java.lang.OutOfMemoryError: Java heap space` on the first write,
  a heap dump, and no `/t` file. A buffer clamped to 16 MiB would have fit.
- Set 2-ctl (C = 16777216, 192m): succeeds.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| First buffer ≈ 33 + 516⌊(C−33)/516⌋ for C > MAX, rising with C; later buffers ≈ MAX-sized | **Claim confirmed** (negative): actual client heap per packet follows the configured size for the first packet; the cap applies only after it. |
| First buffer ≤ MAX + 33 + 16 for every C | **Claim refuted**: the cap governs actual allocation. |
| Set 2 OOM with C = 268435456 and success with C = 16777216 at the same 192m | Actual heap demand follows C, not MAX. Confirms. |
| Set 2 succeeds with C = 268435456 at 192m | The first buffer was capped. Refutes; check JFR. |
| Later buffers ≈ 33 + 516⌊(MAX−33)/516⌋ (16776741 or 4194081), with the same workload | Positive control: the cap binds on the `adjustChunkBoundary` path. |
| Later buffers also ≈ C | The clamp binds nowhere. Still negative; record it. |
| No createPacket events in JFR, or C = 65536 not ≈ 65065 B (65049 + 16) | Instrument failure. **Not confirmed**; fix the JFR settings and rerun. |
| `f48m` with C > DN MAX succeeds | Contradicts A3 step 6. Recheck the DN MAX and the DN log. |

**B3h. Controls.**
- C = 65536 and C = MAX (no clamp).
- Set 2-ctl: same heap, small C.
- Set 3 varies MAX independently on the client while the DataNode stays at 16 MiB. That separates the client
  clamp from the DataNode check.
- The `f1m` file keeps wire size below every MAX, so a failure cannot hide the allocation.
- One client JVM per command, so each run starts from an empty heap.
- `dfs.client.write.byte-array-manager.enabled` is left at its default (false), so allocations are the exact
  sizes.

**B4. Risks and cleanup.**
- Disk: under 1 GB. All under `/mydata/<run>/`; nothing on shared storage.
- Memory: the client allocates up to 268 MB in sets 1 and 3 (H = 1024m) and the daemons 1 GB each. The
  unit tier forks one JVM at 2 GiB.
- Ports: use the non-default ports in B3a and check them first with `ss -ltn`.
- Heap dumps, up to about 200 MB each, go in `/mydata/<run>/dumps`.
- JFR files, a few MB each.
- Cleanup:
  ```
  stop-dfs.sh
  jps    # no NameNode/DataNode/SecondaryNameNode/surefire left
  rm -rf /mydata/<run>/{nn,dn,tmp,dumps,jfr,logs}
  ```
  For the unit tier, `MiniDFSCluster.shutdown()` runs in `finally`. Kill any stray surefire JVM (`jps -l`).

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DFSOutputStream.java (100-160, 189-440, 440-560, 1020-1040)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DFSStripedOutputStream.java (200-225, 286-370, 607-613)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DataStreamer.java (1000-1020, 1570-1578)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocol/datatransfer/PacketReceiver.java (40-110, 130-215, 273-290)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocol/datatransfer/PacketHeader.java (50-70)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/HdfsClientConfigKeys.java (86-87, 236-250, 405-423)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/client/impl/DfsClientConf.java (215-226, 511-521)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/util/ByteArrayManager.java (284-310, 361)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/HdfsConfiguration.java (37-40)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/DFSPacket.java (49-130)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/BlockReceiver.java (96, 548-560)
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml (1300-1311, 4760-4770)
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/TestDFSOutputStream.java (165-275)
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/protocol/datatransfer/TestPacketReceiver.java (grep)
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/FSOutputSummer.java (51-56)
- hadoop-project/pom.xml (187, 2467-2469); hadoop-hdfs-project/hadoop-hdfs/pom.xml (476-478)
- https://issues.apache.org/jira/browse/HDFS-11608
- https://issues.apache.org/jira/browse/HDFS-15469

## D. Stage-4 feedback

**D1. Stage-4 audit amendments (2026-11-25, before any reading).** A1 (unit paths, no install build, read surefire
counts), A2 (order of default resources in the 4 MiB class), A3 (how (e), (f), (g) are read; per-test timeout), A4
(cluster set-up on the node: base distribution, `hdfs --daemon`, ports, JFR `dumponexit`, heap check), A5 (reading
JFR sizes, with exact expected values), A6 (stop and check); A7 (after unit attempt 1: first write of 4608 bytes, so (c) sees the first packet at C = 65536). None changes the claim (B1), the predictions (B2f,
B3f) or the readings tables (B2g, B3g). Results: `hadoop/stage4-runtime-verification/jingsong/results/<stem>.md`.

**D2. Stage-4 result (2026-11-25).** Unit **Confirmed** (B2g row 1), cluster **Confirmed** (B3g row 1); effect `does not
cap`; outcome class **true negative**. Run on `pc72`, one run 1 per tier (each restarted once after a runbook defect:
A7 for the unit tier, a harness input-file fix for the cluster tier). Every reading equalled B2f / B3f to the byte:
first packet buffer 33553965 / 268435101 B at MAX 16 MiB and 8388129 B at MAX 4 MiB while the clamped `writePacketSize`
read MAX; packets after the first 16776741 / 4194081 B (positive control); big writes whose first packet exceeded the
DataNode's MAX failed with "Incorrect value for packet payload size"; a `-Xmx192m` client ran out of heap at C = 256 MiB
and succeeded at C = 16 MiB. Results: `hadoop/stage4-runtime-verification/jingsong/results/dfs.data.transfer.max.packet.size-initWritePacketSize-PacketReceiver.MAX_PACKET_SIZE--autonomous.md`
(§8 notes that the clamp binds on packets 2..n, so the Effect field could be read as a bypass).
