# MAX_CONCAT_SRC — verification solution  <!-- file: cases/MAX_CONCAT_SRC-readFields-MAX_CONCAT_SRC--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`FSEditLogOp.java:1328`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLogOp.java#L1328) — `} else if (srcSize > MAX_CONCAT_SRC) {` in `FSEditLogOp.ConcatDeleteOp#readFields` (row unit; this is also the main enforcement point on the read side) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive` — the check runs before `this.srcs = new String[srcSize]` (`FSEditLogOp.java:1333`), so any edit-log `OP_CONCAT_DELETE` whose source count exceeds 1,048,576 is rejected with an `IOException` before the array is sized from the untrusted count. The `String[]` (and the per-source `String`s and the loader's copies sized from it) is therefore capped at 1,048,576 entries (4 MiB of references with compressed oops, 8 MiB without), where an uncapped count could ask for up to ~8–16 GiB. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `MAX_CONCAT_SRC`, a hard-coded constant (kind: constant), declared
`final static public int MAX_CONCAT_SRC = 1024 * 1024;` in the nested class
`FSEditLogOp.ConcatDeleteOp` at
[`FSEditLogOp.java:1250`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLogOp.java#L1250).
Unit: number of source paths in one concat edit-log op (count of `String` elements). Value
1,048,576; there is no `*-default.xml` entry, no configuration key and no system property — it is
**not settable** without recompiling `hadoop-hdfs`. The bare name is unique in the tree (only
`FSEditLogOp.java:1250,1274,1276,1328,1330` reference it), so no class qualification is needed.
It is read by every process that decodes edit-log ops: the NameNode at startup (loading edits after
the fsimage, `FSImage.java:715-728` → `FSEditLogLoader`), a Standby/Observer NameNode tailing
edits, the BackupNode, `hdfs namenode -recover`, and the offline edits viewer `hdfs oev`; and the
active NameNode on the write side (`setSources`, `FSEditLogOp.java:1273-1280`).
Related limit that interacts with it (not the constraint, but on the same path):
`dfs.namenode.max.op.size` (`DFSConfigKeys.java:1251-1252`, default 50 MiB = 52428800,
`hdfs-default.xml:5386-5391`; the Java default and the XML value agree), applied per op by the
reader (`FSEditLogOp.java:5044`, `FSImage.java:724-728`).

**A2. What it caps.** NameNode (or edit-reader process) **heap**: the length of the `String[] srcs`
array allocated while decoding one `OP_CONCAT_DELETE` (`FSEditLogOp.java:1333`), and through it the
number of `String` objects decoded into it (`FSEditLogOp.java:1334-1336`) and the two further arrays
the loader sizes from it when applying the op (`String[]` at `FSEditLogLoader.java:594`, `INodeFile[]`
at `FSEditLogLoader.java:600`). The quantity compared against the limit is `srcSize`, the 4-byte
count read from the edit log (`FSEditLogOp.java:1320`; legacy layouts derive it from the op's
`length` field, `FSEditLogOp.java:1322`). Size arithmetic: a `String[N]` costs 16 + 4·N bytes with
compressed oops (default for heaps < 32 GiB) or 16 + 8·N without; at the cap N = 1,048,576 that is
4,194,320 B (4 MiB) or 8,388,624 B (8 MiB). An unchecked count up to `Integer.MAX_VALUE` would
request ~8 GiB (or ~16 GiB), which is a NameNode-killing allocation for normal heaps.

**A3. Mechanism.**
1. Writing: `FSDirConcatOp.concat` applies the concat in memory (`FSDirConcatOp.java:70-75`) and then
   calls `FSEditLog.logConcat` (`FSDirConcatOp.java:76`, `FSEditLog.java:1015-1022`), which calls
   `ConcatDeleteOp.setSources`; that throws a `RuntimeException` if `srcs.length > MAX_CONCAT_SRC`
   (`FSEditLogOp.java:1274-1277`). `writeFields` itself has no check: it writes the count via
   `ArrayWritable` (`FSEditLogOp.java:1288-1303`). The op is framed by `FSEditLogOp.Writer.writeOp`
   as `[opcode 1B][length 4B][txid 8B][fields][CRC32 4B]` (`FSEditLogOp.java:4978-4997`).
2. Reading (current layouts, `EDITLOG_LENGTH`, `NameNodeLayoutVersion.java:82`):
   `Reader.create` picks `LengthPrefixedReader` (`FSEditLogOp.java:5011-5031`).
   `decodeOpFrame` sets the stream limiter to `maxOpSize` (`FSEditLogOp.java:5229`), rejects an op
   whose stored length exceeds `maxOpSize` (`FSEditLogOp.java:5247-5254`) and verifies the CRC over the
   whole frame **before** decoding (`FSEditLogOp.java:5256-5272`); then `decodeOp` calls
   `op.readFields(in, logVersion)` (`FSEditLogOp.java:5193-5210`).
3. `ConcatDeleteOp.readFields` (`FSEditLogOp.java:1306-1346`) reads the target path (`:1316`), the
   count `srcSize` (`:1320`), and then the check:
   [`FSEditLogOp.java:1324-1332`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLogOp.java#L1324-L1332),
   with the cap branch at
   [`FSEditLogOp.java:1328`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLogOp.java#L1328).
   - `srcSize > MAX_CONCAT_SRC`: throws `IOException("Incorrect data format. ConcatDeleteOp can have
     at most 1048576 sources, but we tried to have " + (length - 3) + " sources.")` before any
     allocation. Note the message bug: on current layouts `length` is never read (it is only set on
     the legacy path, `:1310`), so it stays 0 and the message says **"-3 sources"**, not the real count.
   - otherwise: `new String[srcSize]` (`:1333`) and `srcSize` calls to `readString` (`:1334-1336`),
     each reading a 2-byte length plus bytes (`FSImageSerialization.java:347-351`, `UTF8.java:132-136`).
4. The exception propagates: `Reader.readOp` resets the stream and rethrows when not skipping broken
   edits (`FSEditLogOp.java:5064-5091`); `FSEditLogLoader.loadEditRecords` logs
   `"Error replaying edit log at offset ..."` (`FSEditLogLoader.java:246-257`, `:1060-1075`) and throws
   `EditLogInputException`, so the NameNode fails to start (or, in recovery mode, prompts to skip).
5. When the op passes, the loader applies it and allocates two more arrays of the same length
   (`FSEditLogLoader.java:591-613`).

Bypasses and overshoot:
- The cap is only on the count. Each source string is bounded by the 2-byte UTF8 length (≤ 65,535
  bytes) and, in total, by `maxOpSize` via the limiter — not by `MAX_CONCAT_SRC`. At the cap, the
  decoded op can hold 1,048,576 `String`s (≥ ~40 B each even if empty), i.e. tens of MiB besides the
  4 MiB array.
- At `srcSize ≤ MAX_CONCAT_SRC` the array is allocated **before** the strings are read, so a count at
  the cap with no matching data still allocates 4 MiB and then fails in `readString`
  (`EOFException`, limiter `"Tried to read ... past the limit"`, `FSEditLogLoader.java:1351-1356`, or a
  UTF8 decode error); the limiter's window is `maxOpSize` from the op start, not the frame length.
- On `LengthPrefixedReader` the CRC is verified before `readFields`, so random on-disk corruption of
  the count is caught by the checksum and never reaches line 1328; only a validly-checksummed op with a
  large count does (crafted, or produced by a writer that bypasses `setSources`, e.g. `hdfs oev -p
  binary` from XML, whose `fromXml` sets `srcs` directly, `FSEditLogOp.java:1384-1401`). On older
  layouts `ChecksummedReader` and `LegacyReader` call `readFields` before/without a checksum
  (`FSEditLogOp.java:5293-5316`, `:5351-5376`), so a corrupted count reaches the check directly.
- Write side: `setSources` rejects > 1M sources only **after** `unprotectedConcat` has changed the
  namespace (`FSDirConcatOp.java:70-76`), with a `RuntimeException`; not a memory overshoot, but an
  inconsistency path (namespace changed, op not logged). The RPC size (`ipc.maximum.data.length`,
  128 MiB, `core-default.xml:2585-2586`) does not prevent a > 1M-source concat request of short paths.

**A4. Other consumers.** The rest of the NameNode heap during edit replay (namespace, blocks map,
retry cache, other ops), the op-decoding buffers (`UTF8` thread-local buffer, the `BufferedInputStream`
marked for up to `maxOpSize`), the log line from `op.toString()` when apply fails (it renders all
sources, `FSEditLogOp.java:1348-1366`, `FSEditLogLoader.java:296`), and on the write side the RPC
request buffer and `srcs` array built from the client request — none of these are governed by
`MAX_CONCAT_SRC`.

**A5. Evidence beyond the source.** The comment in `decodeOpFrame` states the purpose of validating
size before constructing an op: "otherwise we may encounter an OutOfMemoryException which could bring
down the NameNode or JournalNode when reading garbage data" (`FSEditLogOp.java:5242-5246`). Hadoop
3.4.2 HDFS docs for the offline edits viewer, used by the cluster workload:
https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/HdfsEditsViewer.html. No JIRA
relied on. No existing test exercises `MAX_CONCAT_SRC` (grep of `hadoop-hdfs/src/test` finds only an
unrelated `ConcatDeleteOp` use in `TestDFSInotifyEventInputStream.java`).

## B. Verification solution

**B1. Claim under test.** When an edit-log `OP_CONCAT_DELETE` is decoded, the `String[]` of sources
(and the decoded source strings) is allocated only if its count is ≤ 1,048,576: a count of 1,048,577
or more is rejected with `IOException` "can have at most 1048576 sources" and no array proportional to
the count is allocated, so the decode allocation stays ≤ 16 + r·1,048,576 bytes (r = reference size)
however large the stored count is. The claim is wrong if a count > 1,048,576 produces an allocation
proportional to that count (or an `OutOfMemoryError`), or if a count ≤ 1,048,576 is rejected by this
check.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 8 (e.g. OpenJDK 8u3xx), Maven 3.6+. Copy the source to
local disk (`rsync -a <source>/ /local/$USER/hadoop-src/`; all paths below relative to that copy).
Build once: `mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests
-Dmaven.javadoc.skip=true`. Add one test file
`hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestConcatDeleteOpSrcCap.java`
(package `org.apache.hadoop.hdfs.server.namenode`, needed because `ConcatDeleteOp()`, `readFields`,
`writeFields` and the `srcs` field are package-private). Run:
`mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestConcatDeleteOpSrcCap
-Dmaven-surefire-plugin.argLine="-Xmx<H> <oops>"` (the default argLine is `-Xmx2048m
-XX:+HeapDumpOnOutOfMemoryError`, `hadoop-project/pom.xml:187`). Variants: `<oops>` =
`-XX:+UseCompressedOops` (r = 4) and `-XX:-UseCompressedOops` (r = 8); `<H>` = 2048m for the main
runs and 256m for the "huge count" runs.

For the counterfactual control (B2h) make a **second** copy `/local/$USER/hadoop-src-nocheck/` with
`FSEditLogOp.java:1328-1331` replaced by `}` (i.e. delete the `else if (srcSize > MAX_CONCAT_SRC)`
branch), build it the same way, and run the same test class there.

**B2b. Knobs.** The constant cannot be changed, so the knob is the operand: the stored count
`srcSize` ∈ {0, 3, 1,048,575, 1,048,576 (= cap), 1,048,577 (= cap + 1), 2,097,152, 200,000,000,
2,000,000,000, `Integer.MAX_VALUE` (2,147,483,647), −1}. These bracket the boundary exactly, include
values whose uncapped array (0.8 GB, 8 GB, ~8.6 GB at r = 4) would exceed the 256 MiB test heap, and
the negative branch. Second knob: reference size r ∈ {4, 8} (to tie the measured allocation to
16 + r·N). Third (interaction): `Reader.setMaxOpSize` ∈ {50 MiB default, 1 MiB} for the framed variant.

**B2c. Workload.** Three input shapes, each fed to a fresh `new FSEditLogOp.ConcatDeleteOp()`
via `op.readFields(new DataInputStream(new ByteArrayInputStream(bytes)),
NameNodeLayoutVersion.CURRENT_LAYOUT_VERSION)`:
- **Count-only:** `FSImageSerialization.writeString("/t", out); out.writeInt(N);` and nothing else
  (6 + 4 bytes). Exercises the check and the allocation without needing N strings; when the check
  passes, decoding ends in `EOFException` at the first `readString` (or at `readLong` for N = 0).
- **Full op:** build `ConcatDeleteOp op`, `op.setTarget("/t")`, assign `op.srcs` directly to an
  array of N paths `String.format("/c/x%07d", i)` (bypassing `setSources`), `op.setTimestamp(1L)`,
  `op.setRpcClientId(ClientId.getClientId())`, `op.setRpcCallId(1)`, `op.writeFields(out)`. Only for
  N ∈ {3, 1,048,575, 1,048,576, 1,048,577} (each path = 2 + 10 bytes → ≤ 12.6 MB of data; fits in
  the 2 GiB test heap).
- **Framed (end-to-end reader):** write the full op with `setTransactionId(1)` through
  `EditLogFileOutputStream(conf, file, 1024*1024)` → `create(NameNodeLayoutVersion.CURRENT_LAYOUT_VERSION)`
  → `write(op)` → `setReadyToFlush()` → `flushAndSync(true)` → `close()` into a JUnit temp dir on local
  disk, then read with `new EditLogFileInputStream(file)` (`EditLogFileInputStream.java:85`),
  `setMaxOpSize(...)`, `readOp()`. Op size for N = cap + 1 is ~12.6 MB < 50 MiB, so the frame
  passes `maxOpSize` and CRC and reaches line 1328.

**B2d. Observables and instruments.**
- Outcome per call: exception class and message (assert on substrings `"can have at most 1048576"`,
  `"negative number"`), or success with `op.srcs.length`.
- Allocated bytes of the decoding thread: `com.sun.management.ThreadMXBean#getThreadAllocatedBytes(
  Thread.currentThread().getId())` read immediately before and after `readFields`/`readOp`
  (ΔA). Run each case 5 times after a 3-call warm-up and report the median; baseline ΔA of a
  `readFields` on a 3-source op is the noise floor.
- r is confirmed by reading `HotSpotDiagnosticMXBean.getVMOption("UseCompressedOops")`.
- Heap failures: catch `Throwable` and record `OutOfMemoryError` (only expected in the no-check copy).
- Not directly observable: the exact array object (allocation is attributed to the thread, so ΔA
  includes the exception, its message and the `String`s); the array part is isolated by comparing
  count-only cases, which read no strings.

**B2e. Procedure.**
1. Copy source; build (B2a).
2. Write `TestConcatDeleteOpSrcCap` with: a helper `byte[] countOnly(int n)`, `byte[] fullOp(int n)`,
   `long allocDuring(Runnable r)`; one `@Test` per shape that loops over the N values of B2b
   applicable to it, prints `shape, N, r, outcome, message, srcs.length, ΔA` as one CSV line per run
   to stdout, and asserts the predictions of B2f.
3. Run with `-Xmx2048m -XX:+UseCompressedOops`, then `-Xmx2048m -XX:-UseCompressedOops`, then
   `-Xmx256m -XX:+UseCompressedOops` (count-only shape only).
4. Framed shape: run with maxOpSize 50 MiB and 1 MiB.
5. Repeat steps 3 (count-only, `-Xmx256m` and `-Xmx2048m`) in the no-check copy.
6. Collect `target/surefire-reports/*TestConcatDeleteOpSrcCap*-output.txt`.

**B2f. Predictions.** (stock build; ΔA “≈0” means < 64 KiB above the noise floor)

| Shape | N | Outcome | ΔA, r = 4 | ΔA, r = 8 |
|---|---|---|---|---|
| count-only | −1 | IOException "negative number" | ≈0 | ≈0 |
| count-only | 0 | EOFException at `readLong` (after the check) | ≈0 (16 B array) | ≈0 |
| count-only | 1,048,575 | EOFException (after the check) | 4,194,316 + ≈0 | 8,388,616 + ≈0 |
| count-only | 1,048,576 | EOFException (after the check) | 4,194,320 + ≈0 | 8,388,624 + ≈0 |
| count-only | 1,048,577 | IOException "can have at most 1048576 sources, but we tried to have -3 sources." | ≈0 | ≈0 |
| count-only | 2,097,152 / 2·10^8 / 2·10^9 / 2^31−1 | same IOException; no OOM even at `-Xmx256m` | ≈0 | ≈0 |
| full op | 3 | success, `srcs.length` = 3 | baseline | baseline |
| full op | 1,048,576 | success, `srcs.length` = 1,048,576 | ≥ 4 MiB + 1,048,576·(String + char[20]) ≈ 4 MiB + ~60–100 MiB incl. builder garbage | ≥ 8 MiB + similar |
| full op | 1,048,577 | IOException "can have at most" | ≈0 (no strings read) | ≈0 |
| framed, 50 MiB | 1,048,576 / 1,048,577 | `readOp` returns op / throws IOException with the same message | as full op | as full op |
| framed, 1 MiB | 1,048,576 / 1,048,577 | both throw "Op 16 has size ..., but maxOpSize = 1048576" before `readFields` | ≈0 beyond the CRC pass | ≈0 |

Relation that must hold: for count-only cases with N ≤ cap, ΔA − floor ≈ 16 + r·N (slope r per
entry, ± 1 KiB); for every N > cap, ΔA is independent of N.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| N ≤ 1,048,576 decodes past the check and ΔA tracks 16 + r·N; every N > 1,048,576 throws "can have at most" with ΔA ≈ 0 | Claim confirmed: the cap bounds the allocation. |
| Some N > 1,048,576 shows ΔA ∝ N, an `OutOfMemoryError`, or a different failure after allocation | Claim wrong: the check does not precede the allocation (or another path allocates first). |
| N = 1,048,576 rejected by the check | Off-by-one versus the traced `>`; claim wrong at the boundary. |
| ΔA ≈ 0 also for N = 1,048,576 count-only | Instrument blind (TLAB/JIT eliminated, or wrong thread); not confirmed — fix the instrument (see controls). |
| Message says "-3 sources" | Confirms the traced message bug (A3), and that the current-layout branch was taken. |
| framed 1 MiB rejects both at "maxOpSize" | `dfs.namenode.max.op.size` binds first for full ops; the count cap is still the only bound for count-only (array-before-data) cases. |

**B2h. Controls.**
- **Instrument control:** count-only N = 1,048,576 with r = 4 and r = 8 must show a 4 MiB vs 8 MiB
  ΔA difference; otherwise ΔA is not measuring the array.
- **Counterfactual (positive control, cap removed):** in the no-check copy, count-only N = 2·10^8 at
  `-Xmx2048m` must show ΔA ≈ 800,000,016 B (r = 4) then EOFException, and N = 2·10^9 / 2^31−1 at
  `-Xmx256m` must give `OutOfMemoryError` ("Java heap space" / "Requested array size exceeds VM
  limit"). This shows the same workload moves memory when the check is absent, so the flat ΔA in the
  stock build is due to line 1328.
- Fresh op instance per call (no cached-op state); warm-up runs; same thread for before/after reads.
- The full-op N = 3 case shows ordinary decoding works, so rejections are not format errors in the
  hand-built bytes.

### B3. Cluster tier

**B3a. Environment and build.** One Linux host, pseudo-distributed HDFS (NameNode + DataNode; no
YARN needed). Build the distribution from the local copy: `mvn package -Pdist -DskipTests -Dtar
-Dmaven.javadoc.skip=true`; unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `$S/hadoop` where
`$S` is a local-disk directory with ≥ 5 GB free (not shared storage). Run the daemons on **JDK 11**
(supported runtime; needed for JFR with the `jfr` tool; JDK 8u262+ also has JFR but no `jfr` CLI —
then read the recording with a JDK 11 `jfr`). For the counterfactual (B3h) build a second
distribution from the no-check copy (B2a) into `$S/hadoop-nocheck` (or just replace
`share/hadoop/hdfs/hadoop-hdfs-3.4.2.jar` in a copy of `$S/hadoop`).

`etc/hadoop/core-site.xml`: `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir=$S/tmp`.
`etc/hadoop/hdfs-site.xml`: `dfs.replication=1`, `dfs.namenode.name.dir=$S/name`,
`dfs.datanode.data.dir=$S/data`, `dfs.namenode.max.op.size=52428800` (explicit default).
`etc/hadoop/hadoop-env.sh`: `export JAVA_HOME=<jdk11>`, `export HADOOP_LOG_DIR=$S/logs`,
`export HDFS_NAMENODE_OPTS="-Xms1g -Xmx1g -XX:+UseCompressedOops -Xlog:gc*:file=$S/logs/nn-gc.log
-XX:StartFlightRecording=filename=$S/logs/nn-%p.jfr,settings=profile,dumponexit=true"`
(per run, use a run-specific file name). For the client tool `oev`:
`export HADOOP_CLIENT_OPTS=-Xmx4g`. All settings need a NameNode restart (each case starts it fresh).

**B3b. Knobs.** As in the unit tier, the stored count N of the single `OP_CONCAT_DELETE` in the edit
segment the NameNode replays at startup: count-only forgery N ∈ {3 (unmodified), 1,048,576,
1,048,577, 200,000,000, 2,000,000,000}; full-op forgery (all N strings present) N ∈ {1,048,576,
1,048,577}. Heap is fixed at 1 GiB so that an uncapped 2·10^8 count (800 MB array) is visible and a
2·10^9 count (8 GB) cannot fit.

**B3c. Workload.** Real client path to create the op, then forge only its count (or source list):
1. `hdfs namenode -format -force`, `start-dfs.sh`.
2. `hdfs dfs -mkdir /c; for i in 1 2 3 4; do head -c 1048576 /dev/urandom > $S/f$i; hdfs dfs -put
   $S/f$i /c/f$i; done; hdfs dfs -concat /c/f1 /c/f2 /c/f3 /c/f4` (the shell `concat` command,
   `hadoop-common/.../fs/shell/Concat.java:37-44`) → one `OP_CONCAT_DELETE` with 3 sources.
3. `hdfs dfsadmin -rollEdits` (finalizes the segment containing it), `stop-dfs.sh`.
4. Locate the segment: `for f in $S/name/current/edits_0*; do hdfs oev -i $f -o $f.xml -p xml; grep -l
   OP_CONCAT_DELETE $f.xml; done` → `$SEG` (back it up: `cp $SEG $S/seg.orig`).
5. Forge (choose one):
   - **Count-only:** `python3 $S/forge-count.py $S/seg.orig $SEG N` (script below; rewrites the 4-byte
     count after the target path and recomputes the frame CRC32, so the frame length and checksum stay
     valid and the op reaches line 1328).
   - **Full op:** take `$SEG.xml`, replace the `<SOURCES>…</SOURCES>` element of the
     `OP_CONCAT_DELETE` record with N children `<SOURCEi>/c/x%07d</SOURCEi>` (i = 1..N; small Python
     script), then `hdfs oev -i forged.xml -o $SEG -p binary` (`fromXml` sets `srcs` directly and the
     binary writer frames and checksums it; op ≈ 12.6 MB < 50 MiB).
6. Start only the NameNode: `hdfs --daemon start namenode`; it replays the segment.

`forge-count.py` (keep outside the source tree, e.g. `$S/forge-count.py`):
```python
import struct, sys, zlib
src, dst, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
b = bytearray(open(src, 'rb').read())
pos, done = 8, False                    # header: layout version (4) + layout flags count (4)
while pos + 13 <= len(b) and b[pos] != 0xFF:  # 0xFF = OP_INVALID / preallocation fill
    L = struct.unpack('>i', b[pos+1:pos+5])[0]   # = 4 + 8 + len(fields)
    if b[pos] == 16 and not done:       # OP_CONCAT_DELETE
        t = pos + 13                    # opcode(1) + length(4) + txid(8)
        cnt = t + 2 + struct.unpack('>H', b[t:t+2])[0]   # after target path (UTF8)
        old = struct.unpack('>i', b[cnt:cnt+4])[0]
        b[cnt:cnt+4] = struct.pack('>i', n)
        b[pos+1+L:pos+5+L] = struct.pack('>I', zlib.crc32(bytes(b[pos:pos+1+L])) & 0xffffffff)
        print('txid', struct.unpack('>q', b[pos+5:pos+13])[0], 'count', old, '->', n); done = True
    pos += 1 + L + 4                    # opcode + L bytes + CRC
open(dst, 'wb').write(b); assert done
```
(Frame layout from `FSEditLogOp.java:4978-4997`; header from `EditLogFileOutputStream.java:141-145`
and `LayoutFlags.java:56-58`; Hadoop's CRC32 is the standard IEEE CRC-32 that `zlib.crc32` computes.)
Sanity check after forging: `hdfs oev -i $SEG -o /dev/null -p stats` must fail with the same
message as the NameNode for N > cap, and `cmp` must show exactly 8 changed bytes (count + CRC).

Duration: each case is one NameNode start (< 1 min).

**B3d. Observables and instruments.**
- Outcome: `$S/logs/hadoop-*-namenode-*.log` — grep `"can have at most 1048576 sources"`,
  `"Error replaying edit log at offset"`, `"Encountered exception on operation ConcatDeleteOp"`,
  `"Tried to read"`, `EOFException`, `OutOfMemoryError`, `"got unexpected exception"` (the reader wraps
  any `Throwable`, `FSEditLogOp.java:5081-5086`); `jps` (NameNode gone = startup failed).
- Actual heap allocation: JFR `jdk.ObjectAllocationOutsideTLAB` and `jdk.ObjectAllocationSample`
  events: `jfr print --events jdk.ObjectAllocationOutsideTLAB $S/logs/nn-<pid>.jfr | grep -A12
  'java.lang.String\[\]'`, filter on stack frames containing `ConcatDeleteOp.readFields`; record
  `allocationSize`. Large arrays are always allocated outside a TLAB, so the `String[]` from line 1333
  appears with its exact size.
- Heap occupancy: the unified GC log (`nn-gc.log`): heap before/after around the edit-loading phase
  (timestamps between the log lines "Loading edits" / "Start loading edits file" and the failure).
- Not observable directly: whether the strings of a full op are retained vs. garbage (use the GC log
  heap-after values as an upper bound).

**B3e. Procedure.** For each case (fresh state each time):
1. `rm -rf $S/name $S/data $S/tmp $S/logs/*`; steps 1–4 of B3c.
2. Step 5 with the case's N (count-only or full op); verify with `cmp`/`oev` as above.
3. Set the run-specific JFR file name in `HDFS_NAMENODE_OPTS`; `hdfs --daemon start namenode`.
4. Wait until `jps` no longer lists `NameNode` or 120 s pass; if it is still running (expected only
   for the unmodified N = 3 baseline), check `hdfs dfs -ls /c` (only `/c/f1`, 4 MiB) and stop it with
   `hdfs --daemon stop namenode`.
5. Save the NameNode log, GC log and JFR file under `$S/results/<case>/`; extract outcome line,
   `String[]` allocation sizes from `ConcatDeleteOp.readFields`, and peak heap during edit load.
6. Restore `cp $S/seg.orig $SEG` (or reformat at the next case's step 1).
7. Counterfactual: repeat count-only N ∈ {200,000,000, 2,000,000,000} with `$S/hadoop-nocheck`.

**B3f. Predictions.** (stock build, 1 GiB heap, compressed oops)

| Case | NameNode outcome | `String[]` allocated in `readFields` (JFR) | Heap during load |
|---|---|---|---|
| unmodified, N = 3 | starts; `/c/f1` is 4 MiB | none large (3-entry array is TLAB-allocated) | baseline |
| count-only N = 1,048,576 | fails; cause EOFException / "Tried to read … past the limit" / UTF8 decode error, **not** "can have at most" | one event, 4,194,320 B | baseline + ≥ 4 MiB |
| count-only N = 1,048,577 | fails; "Error replaying edit log at offset …" with cause "ConcatDeleteOp can have at most 1048576 sources, but we tried to have -3 sources." | none | baseline |
| count-only N = 2·10^8, 2·10^9 | same "can have at most" failure; no OOM, no full GC | none | baseline |
| full op N = 1,048,576 | decode succeeds; fails at apply with "Encountered exception on operation ConcatDeleteOp" (NullPointerException: sources `/c/x…` do not exist) | 4,194,320 B in `readFields`, plus 4,194,320 B `String[]` and `INodeFile[]` in `FSEditLogLoader.applyEditLogOp` | baseline + tens of MiB (1,048,576 strings) |
| full op N = 1,048,577 | fails with "can have at most" before any source string is read | none | baseline (no tens-of-MiB rise) |

The claim is wrong if any N > 1,048,576 case shows a `String[]` allocation from `readFields`, an
`OutOfMemoryError`, or a heap rise proportional to N; or if N = 1,048,576 is rejected by the check.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| N ≤ cap: JFR shows a 4,194,320 B `String[]` from `readFields`; N > cap: "can have at most" and no such allocation, heap flat for 2·10^8 / 2·10^9 | Claim confirmed on a real NameNode. |
| N > cap: JFR shows a `String[]` of 16 + 4·N B, GC log shows an ~800 MB jump, or `OutOfMemoryError` / "got unexpected exception Java heap space" | Claim wrong: the count reaches the allocation in the shipped daemon. |
| Count-only N > cap fails with a CRC/`ChecksumException` or "maxOpSize" instead | Forgery broken (frame not valid); not confirmed — fix the forging step. |
| N = 1,048,576 count-only shows no 4 MiB `String[]` event | JFR not recording large allocations; not confirmed — check JFR settings/stack filter. |
| Counterfactual (no-check build) N = 2·10^8 shows ~800 MB `String[]` and heap jump; N = 2·10^9 gives OOM wrapped as "got unexpected exception" | Positive control moved: the same workload drives memory when the cap is absent, so the stock result is due to line 1328. |
| Counterfactual does not move either | Instruments or workload cannot show the effect; not confirmed. |

**B3h. Controls.**
- Unmodified N = 3 baseline proves the segment, the replay and the concat apply work (only the
  count differs between cases).
- `cmp` shows only the count and CRC bytes changed; `oev -p stats` reproduces the same outcome off-line.
- Counterfactual distribution with the `else if` at line 1328 removed (positive control, B3e step 7).
- JFR instrument control: the at-cap count-only case must show the 4 MiB array.
- Same heap, same JDK, same data across cases; one NameNode at a time.

**B4. Risks and cleanup.**
- Disk: unit tier uses JUnit temp dirs in the local copy's `target/` (≤ 100 MB); cluster tier
  `$S` ≤ ~5 GB (distribution, ~16 MB of block data, edit segments ≤ 20 MB, XML of the full-op
  forgery ~60 MB, JFR files ~10–50 MB each). All on local disk; never write into the shared source tree.
- Memory: test JVMs ≤ 2 GiB (+ Maven), NameNode 1 GiB, `oev` ≤ 4 GiB; the no-check runs are
  bounded by `-Xmx`, so the 8 GB request fails inside the JVM rather than consuming host memory.
- Ports: 9000, 9870, 9866, 9864, 9867 — check they are free (`ss -ltn`) on a shared host; change
  them in `hdfs-site.xml` if not.
- The forged NameNode cases end with the NameNode exiting; the DataNode is left from step 1 of each
  case: after every case run `stop-dfs.sh` (and `hdfs --daemon stop namenode` for the baseline),
  then `jps` must list no `NameNode`, `DataNode`, `SecondaryNameNode`; kill leftovers by PID.
- Cleanup: `rm -rf $S/name $S/data $S/tmp`; keep `$S/results`; delete the no-check copies when done.
- Never point `dfs.namenode.name.dir` at a real cluster's metadata: the procedure deliberately
  corrupts edit segments.

## C. Sources read

hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLogOp.java (1200-1400, 4962-5380, 296-309)
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLogOpCodes.java (50)
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLog.java (1010-1030)
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirConcatOp.java (40-120)
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLogLoader.java (225-300, 591-613, 1055-1075, 1341-1400)
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSImage.java (715-735)
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSImageSerialization.java (345-360, 431-478)
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/EditLogFileInputStream.java (85-95, 148, 188, 530-533)
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/EditLogFileOutputStream.java (53-61, 76, 102, 123-145, 235-241)
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/NameNodeLayoutVersion.java (82)
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/protocol/LayoutVersion.java (90, 102)
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/protocol/LayoutFlags.java (56-58)
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java (1251-1252)
hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml (5386-5391)
hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/tools/offlineEditsViewer/OfflineEditsViewer.java (42-120)
hadoop-hdfs-project/hadoop-hdfs/src/test/java (grep for ConcatDeleteOp / MAX_CONCAT_SRC)
hadoop-hdfs-project/hadoop-hdfs/pom.xml (478)
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/UTF8.java (60-190)
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/shell/Concat.java (37-80)
hadoop-common-project/hadoop-common/src/main/resources/core-default.xml (2585-2588)
hadoop-common-project/hadoop-common/src/main/conf/hadoop-env.sh (285-291)
hadoop-project/pom.xml (187, 2469)
https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/HdfsEditsViewer.html (cited for `oev` usage; content as in OfflineEditsViewer.java usage text)

## D. Stage-4 feedback

none yet
