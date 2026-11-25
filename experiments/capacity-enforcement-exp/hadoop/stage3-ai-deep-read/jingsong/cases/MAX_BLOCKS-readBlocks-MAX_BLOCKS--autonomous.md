# MAX_BLOCKS — verification solution  <!-- file: cases/MAX_BLOCKS-readBlocks-MAX_BLOCKS--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`FSEditLogOp.java:695`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLogOp.java#L695): `} else if (numBlocks > MAX_BLOCKS) {` in `AddCloseOp.readBlocks` (row unit, no helper) |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `positive`. The check runs before `new Block[numBlocks]` (`FSEditLogOp.java:699`), so the up-front reference array that decoding one OP_ADD/OP_CLOSE allocates is capped at `MAX_BLOCKS` slots (64 Mi refs = 268,435,472 bytes with compressed oops). A larger block count read from the edit log is rejected with an `IOException` before anything is allocated. The bound is coarse: it caps a transient allocation triggered by a corrupt or crafted count. Legitimate ops never get close to it, because other limits bind long before (see A3). |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- **Name:** `MAX_BLOCKS` (`FSEditLogOp.AddCloseOp.MAX_BLOCKS`). This bare name is declared nowhere else in the main tree (`grep -rn "MAX_BLOCKS\b"` matches only `FSEditLogOp.java:510,511,687,695,697`).
- **Kind:** a hard-coded constant (`static final public int`).
- **Declaration:** [`FSEditLogOp.java:687`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLogOp.java#L687), `static final public int MAX_BLOCKS = 1024 * 1024 * 64;`. It is not a configuration key and has no `*-default.xml` entry.
- **Unit:** a count of `Block` entries in one AddCloseOp, i.e. slots of a `Block[]` array.
- **Value:** 67,108,864 (64 Mi).
- **How to set it:** it cannot be set through configuration. Changing it means editing the source and rebuilding the `hadoop-hdfs` jar, then restarting whichever process reads edits.
- **Who reads it:** every process that decodes edit-log ops through `FSEditLogOp.Reader`:
  - the NameNode at startup (`FSImage.loadEdits` → `FSEditLogLoader.loadEditRecords`, `FSEditLogLoader.java:243`);
  - the standby NameNode while tailing edits (same loader);
  - the Secondary or Checkpoint NameNode when merging;
  - the BackupNode (`EditLogBackupInputStream`);
  - the offline edits viewer `hdfs oev` (`OfflineEditsBinaryLoader.java:67`).

  The JournalNode only calls `scanOp()` on current-layout logs. For the length-prefixed format that is `decodeOpFrame()` alone (`FSEditLogOp.java:5214-5216`), so the JournalNode never reaches `readBlocks`.
- **Write side:** the same constant also guards the writer. `AddCloseOp.setBlocks` throws a `RuntimeException` when `blocks.length > MAX_BLOCKS` (`FSEditLogOp.java:509-516`), and `FSEditLog.logAddFile`/`logCloseFile`/`logAppendFile` call it (`FSEditLog.java:841,874,895`).
- **Related limits** (separate constraints, named here only):
  - `dfs.namenode.max.op.size` (`DFSConfigKeys.java:1251-1252`, default 50 MiB, `hdfs-default.xml:5386-5391`) bounds the bytes of one op;
  - `dfs.namenode.fs-limits.max-blocks-per-file` (`DFSConfigKeys.java:625-626`, default 10,000, `hdfs-default.xml:485-490`) bounds blocks per file on the client write path.

**A2. What it caps.**
- **Resource:** heap memory of the process decoding an edit log (NameNode heap in the cluster case).
- **Compared quantity:** `numBlocks`, the 32-bit count read with `in.readInt()` at `FSEditLogOp.java:692` from the AddCloseOp body. The code then sizes `new Block[numBlocks]` from it (`FSEditLogOp.java:699`).
- **Size of the capped allocation:** the array costs `16 + 4·numBlocks` bytes with compressed oops (`16 + 8·numBlocks` without). The cap therefore limits it to 268,435,472 bytes (256 MiB + 16), or 536,870,928 bytes without compressed oops.
- **What it replaces:** without the check, a count of up to `Integer.MAX_VALUE` would ask for up to about 8 GiB in a single allocation.
- **What it does not cap:** the `Block` objects themselves (`FSEditLogOp.java:701-703`). Those are created only as 24 bytes per block are actually read, so the bytes present in the stream bound them, not this constant.

**A3. Mechanism.**
1. `AddCloseOp.readFields` (`FSEditLogOp.java:599-684`) reads the fixed fields in this order: inodeId, path, replication, mtime, atime, blockSize. It then calls `readBlocks(in, logVersion)` at `FSEditLogOp.java:650`.
2. `readBlocks` reads `numBlocks = in.readInt()` (`FSEditLogOp.java:692`). A negative count throws `IOException("invalid negative number of blocks")` (`:693-694`).
3. **The check**, [`FSEditLogOp.java:695`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLogOp.java#L695-L698): when `numBlocks > MAX_BLOCKS` it throws `IOException("invalid number of blocks: <n>.  The maximum number of blocks per file is 67108864")`. This happens before any allocation, so the only memory used is the exception and its message.
4. Otherwise (`numBlocks ≤ MAX_BLOCKS`), `Block[] blocks = new Block[numBlocks]` is allocated eagerly (`:699`). The loop then reads 24 bytes per block (`Block.readHelper`, `hadoop-hdfs-client/.../protocol/Block.java:224-231`). If the stream holds fewer blocks than claimed, the loop fails with `EOFException`, or with `IOException("Unexpected block size")` on a negative length. Either way the full array has already been allocated, and it becomes garbage when the exception propagates.
5. Exceptions propagate to `Reader.readOp(skipBrokenEdits)` (`FSEditLogOp.java:5064-5092`):
   - `IOException` is rethrown;
   - any other `Throwable`, including an `OutOfMemoryError` from step 4, is wrapped as `IOException("got unexpected exception " + msg)` (`:5081-5085`).

   `FSEditLogLoader.loadEditRecords` logs "Error replaying edit log…" and throws `EditLogInputException` when not in recovery mode (`FSEditLogLoader.java:247-257`). The NameNode then fails to start.
6. **What reaches this check.** For current layouts the op passes `LengthPrefixedReader.decodeOpFrame` first (`FSEditLogOp.java:5228-5279`):
   - the op's total length must be ≤ `maxOpSize` (`:5248`);
   - the CRC32 over opcode+length+txid+body must match (`:5259-5273`).

   So `readBlocks` sees an over-large count only when:
   - the op's CRC is valid but its content is wrong (a software bug or a crafted file);
   - an old layout is read by `ChecksummedReader` or `LegacyReader` (`:5282-5390`). `LegacyReader` has no checksum at all.
   - recovery mode re-decodes at arbitrary offsets (`readOp(true)` advances one byte at a time, `:5087-5090`).
7. **Legitimate ops never reach the cap:**
   - a real op carries 24 bytes per block, so at the default `maxOpSize` of 50 MiB it holds at most about 2.18 M blocks;
   - files are capped at 10,000 blocks on write (`dfs.namenode.fs-limits.max-blocks-per-file`).
8. **Bypasses and overshoot:**
   - (a) up to 256 MiB is still allocated for any count ≤ `MAX_BLOCKS`, even when the op body is only a few bytes long, because the allocation does not depend on the bytes actually available;
   - (b) `FSImageSerialization.readCompactBlockArray` (`FSImageSerialization.java:502-520`) has no upper bound (only `num < 0` is checked) before `new Block[num]` (`:509`). OP_ADD_BLOCK (`FSEditLogOp.java:1026`), OP_UPDATE_BLOCKS (`:1125`) and OP_TRUNCATE (`:2908`) use it, so a crafted VInt count in those ops can request up to about 8 GiB.

**A4. Other consumers.** Other things that use the same heap or memory, outside this constant's control:
- the decode itself:
  - the `BufferedInputStream`/`mark(maxOpSize)` buffer (up to `dfs.namenode.max.op.size`, `FSEditLogOp.java:5199,5230`);
  - other op fields (strings bounded by 2-byte UTF8 lengths; ACL and XAttr protobufs, bounded by the stream limiter);
  - the unbounded `readCompactBlockArray` path above;
- the NameNode heap as a whole: namespace, `BlocksMap`, RPC buffers;
- fsimage loading, which uses protobuf sections and is a separate code path;
- the JournalNode edit cache (`dfs.journalnode.edit-cache-size.bytes`), a different constraint.

**A5. Evidence beyond the source.**
- HDFS-3440, "should more effectively limit stream memory consumption when reading corrupt edit logs" (<https://issues.apache.org/jira/browse/HDFS-3440>). Listed in `hadoop-common-project/hadoop-common/src/site/markdown/release/2.0.2-alpha/CHANGELOG.2.0.2-alpha.md`. Its title matches the purpose of the stream limiter and `maxOpSize`.
- HDFS-8965, "Harden edit log reading code against out of memory errors" (<https://issues.apache.org/jira/browse/HDFS-8965>). Listed in the 2.8.0 and 3.0.0-alpha1 changelogs. It matches the comment at `FSEditLogOp.java:5242-5246` about avoiding OOM on garbage data.
- I read only the JIRA titles in the in-tree changelogs, not the issues themselves. Which JIRA introduced `MAX_BLOCKS` was not established.
- No in-tree test exercises the `numBlocks > MAX_BLOCKS` branch (`grep -rn "invalid number of blocks" src/test` finds nothing).

## B. Verification solution

**B1. Claim under test.** When a process decodes an OP_ADD/OP_CLOSE whose block count is N:
- for N ≤ 67,108,864 (`MAX_BLOCKS`), it allocates a `Block[]` of `16 + r·N` bytes (r = 4 with compressed oops), however few block bytes follow;
- for N > 67,108,864, it allocates no such array and fails with "invalid number of blocks: N".

So the up-front allocation is capped at about 256 MiB, and the cap moves if the constant is changed. The claim is wrong if a count above `MAX_BLOCKS` still triggers a large allocation or OOM, or if a count at or below it is rejected or allocates nothing.

### B2. Unit tier

**B2a. Environment and build.**
- Linux host, JDK 8 (or 11), Maven 3.3+, about 10 GB of free local disk.
- Copy the tree to local disk first: `rsync -a ~/hadoop-3.4.2/ $SRC/`, where `$SRC` is on local disk, never on shared storage.
- Build: `cd $SRC && mvn -pl hadoop-hdfs-project/hadoop-hdfs -am install -DskipTests -Dmaven.javadoc.skip=true`.
- Test source: `$SRC/hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestReadBlocksMaxBlocks.java`. It lives in the same package because `AddCloseOp` and its setters are package-private.
- JVM options: the heap is set through the surefire property `maven-surefire-plugin.argLine` (default `-Xmx2048m …`, `hadoop-project/pom.xml:187`), overridden on the command line as shown in B2e.

**B2b. Knobs.**
- **N, the forged `numBlocks`** in a single serialized OP_CLOSE (the knob that matters here):
  - 4,194,304 (4 Mi, 16 MiB array);
  - 16,777,216 (16 Mi, 64 MiB);
  - 67,108,864 (= `MAX_BLOCKS`, at the boundary, accepted because the check is `>`);
  - 67,108,865 (`MAX_BLOCKS + 1`);
  - 134,217,728 (2·`MAX_BLOCKS`; would be 512 MiB);
  - 2,147,483,647 (`Integer.MAX_VALUE`; would exceed the VM array limit).
- **Test JVM heap:**
  - `-Xmx1g`: big enough that a 256 MiB array fits, so allocation can be observed;
  - `-Xmx200m`: a 256 MiB array cannot fit, so N = `MAX_BLOCKS` must OOM while `MAX_BLOCKS + 1` must not.
- **The constant itself, as a mutation control:** a second copy of the tree with `FSEditLogOp.java:687` changed to `1024 * 1024`, rebuilt the same way. It is only for B2h.

**B2c. Workload.**
1. Build one legitimate `CloseOp` (path `/s3/f`, 0 blocks, `blockSize` set to a sentinel `0x5A5A5A5A12345678L`) and serialize it with `FSEditLogOp.Writer` at `NameNodeLayoutVersion.CURRENT_LAYOUT_VERSION`.
2. Overwrite the 4-byte `numBlocks` field, which comes immediately after the sentinel (`writeFields`, `FSEditLogOp.java:569-577`), with N.
3. Recompute the trailing CRC32 over all bytes except the last 4 (as in `Writer.writeOp`, `FSEditLogOp.java:4978-4997`). The op length does not change.
4. Decode the bytes with `FSEditLogOp.Reader.create(...)` and `readOp(false)`.

The op body after `numBlocks` is only about 10 bytes (permissions + CRC). So for N ≤ `MAX_BLOCKS` the loop must fail at block 0 with `EOFException`, after the array is allocated. The array size for each N is `16 + 4N`: 16.0 MiB, 64.0 MiB and 256.0 MiB for the three accepted values. The check leaves the larger three at 0.

**B2d. Observables and instruments.**
- **Allocation:** `com.sun.management.ThreadMXBean.getThreadAllocatedBytes(tid)` around `readOp`. It counts TLAB and outside-TLAB allocations of the calling thread, so the result is ≥ the array size when the array was allocated.
- **Outcome:** the exception class and message (`invalid number of blocks`, `EOFException`, `got unexpected exception Java heap space`).
- **JVM facts:** `UseCompressedOops` via `HotSpotDiagnosticMXBean`, and `Runtime.maxMemory()`.
- All of these are printed as `S3RESULT` lines to stdout, which surefire saves in `target/surefire-reports/…-output.txt`.
- **Not directly observable:** the array's lifetime. It is garbage immediately after the exception; the counter shows that it was allocated, not how long it lived.

**B2e. Procedure.**
1. Write the test file:

```java
package org.apache.hadoop.hdfs.server.namenode;

import static org.junit.Assert.*;
import java.io.*;
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import java.util.zip.CRC32;
import org.apache.hadoop.fs.permission.FsPermission;
import org.apache.hadoop.fs.permission.PermissionStatus;
import org.apache.hadoop.hdfs.protocol.Block;
import org.apache.hadoop.io.DataOutputBuffer;
import org.junit.Test;

public class TestReadBlocksMaxBlocks {
  static final long SENTINEL = 0x5A5A5A5A12345678L;
  static final int LV = NameNodeLayoutVersion.CURRENT_LAYOUT_VERSION;
  static final int MAX = FSEditLogOp.AddCloseOp.MAX_BLOCKS;

  static byte[] craft(int n) throws IOException {
    FSEditLogOp.OpInstanceCache cache = new FSEditLogOp.OpInstanceCache();
    FSEditLogOp.CloseOp op = FSEditLogOp.CloseOp.getInstance(cache);
    op.setInodeId(16386L); op.setPath("/s3/f"); op.setReplication((short) 1);
    op.setModificationTime(1L); op.setAccessTime(1L); op.setBlockSize(SENTINEL);
    op.setBlocks(new Block[0]);
    op.setPermissionStatus(new PermissionStatus("u", "g", FsPermission.getFileDefault()));
    op.setTransactionId(1L);
    DataOutputBuffer buf = new DataOutputBuffer();
    new FSEditLogOp.Writer(buf).writeOp(op, LV);
    byte[] b = Arrays.copyOf(buf.getData(), buf.getLength());
    int s = -1;
    for (int i = 0; i + 8 <= b.length; i++) {
      long v = 0; for (int k = 0; k < 8; k++) v = (v << 8) | (b[i + k] & 0xff);
      if (v == SENTINEL) { s = i; break; }
    }
    assertTrue("sentinel not found", s >= 0);
    putInt(b, s + 8, n);                       // numBlocks follows blockSize
    CRC32 crc = new CRC32(); crc.update(b, 0, b.length - 4);
    putInt(b, b.length - 4, (int) crc.getValue());
    return b;
  }

  static void putInt(byte[] b, int at, int v) {
    b[at] = (byte) (v >>> 24); b[at + 1] = (byte) (v >>> 16);
    b[at + 2] = (byte) (v >>> 8); b[at + 3] = (byte) v;
  }

  @Test
  public void sweep() throws Exception {
    com.sun.management.ThreadMXBean mx =
        (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    String coops = ManagementFactory.getPlatformMXBean(
        com.sun.management.HotSpotDiagnosticMXBean.class)
        .getVMOption("UseCompressedOops").getValue();
    long maxHeap = Runtime.getRuntime().maxMemory();
    System.out.println("S3RESULT MAX_BLOCKS=" + MAX + " UseCompressedOops=" + coops
        + " maxHeap=" + maxHeap);
    int ref = "true".equals(coops) ? 4 : 8;
    int[] ns = {4 << 20, 16 << 20, MAX, MAX + 1, 2 * MAX, Integer.MAX_VALUE};
    long tid = Thread.currentThread().getId();
    for (int n : ns) {
      byte[] b = craft(n);
      FSEditLogLoader.PositionTrackingInputStream tracker =
          new FSEditLogLoader.PositionTrackingInputStream(
              new BufferedInputStream(new ByteArrayInputStream(b)));
      FSEditLogOp.Reader r =
          FSEditLogOp.Reader.create(new DataInputStream(tracker), tracker, LV);
      System.gc();
      long before = mx.getThreadAllocatedBytes(tid);
      String outcome;
      try { r.readOp(false); outcome = "NO_EXCEPTION"; }
      catch (Throwable t) { outcome = t.getClass().getName() + ": " + t.getMessage(); }
      long alloc = mx.getThreadAllocatedBytes(tid) - before;
      System.out.println("S3RESULT N=" + n + " alloc=" + alloc
          + " expectedArray=" + (16L + (long) ref * n) + " outcome=" + outcome);
      if ((long) n > MAX) {
        assertTrue(outcome, outcome.contains("invalid number of blocks: " + n));
        assertTrue("alloc=" + alloc, alloc < (1L << 20));
      } else if (16L + (long) ref * n < maxHeap / 2) {
        assertFalse(outcome, outcome.contains("invalid number of blocks"));
        assertTrue("alloc=" + alloc, alloc >= (long) ref * n);
      }
    }
  }
}
```

2. Large-heap run: `cd $SRC && mvn -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestReadBlocksMaxBlocks -Dmaven-surefire-plugin.argLine="-Xmx1g"`. Then `grep S3RESULT hadoop-hdfs-project/hadoop-hdfs/target/surefire-reports/*TestReadBlocksMaxBlocks-output.txt`.
3. Small-heap run: the same command with `-Dmaven-surefire-plugin.argLine="-Xmx200m"`. Record the `S3RESULT` lines. At this heap the assertion branch for N = `MAX_BLOCKS` is skipped, so read its `outcome` line directly.
4. Mutation control (B2h): in a second local copy `$SRC2`, change `FSEditLogOp.java:687` to `1024 * 1024`. Rebuild with step 1 of B2a and rerun step 2 there. Then read the `S3RESULT` lines; the assertions encode the threshold `MAX`, so they adapt automatically.

**B2f. Predictions.** All predictions assume `UseCompressedOops=true`; otherwise double every array size.

| N | `-Xmx1g` alloc (bytes) | `-Xmx1g` outcome | `-Xmx200m` outcome |
|---|---|---|---|
| 4,194,304 | ≥ 16,777,232 | `EOFException` (or "Unexpected block size") | same as 1g |
| 16,777,216 | ≥ 67,108,880 | `EOFException` | same, alloc ≥ 67,108,880 |
| 67,108,864 | ≥ 268,435,472 | `EOFException` | `IOException: got unexpected exception Java heap space` (alloc counter well below 268 M) |
| 67,108,865 | < 1 MiB | `IOException: invalid number of blocks: 67108865.  The maximum number of blocks per file is 67108864` | same |
| 134,217,728 | < 1 MiB | `invalid number of blocks: 134217728` | same |
| 2,147,483,647 | < 1 MiB | `invalid number of blocks: 2147483647` | same |

Mutation build (`MAX_BLOCKS = 1,048,576`): every N in the list gives "invalid number of blocks", with alloc < 1 MiB.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Alloc ≈ 16 + 4N for N ≤ 64 Mi, and < 1 MiB with "invalid number of blocks" for N > 64 Mi | Claim confirmed: allocation follows N up to the constant, then the check cuts it off. |
| At `-Xmx200m`: N = 64 Mi OOMs but N = 64 Mi + 1 fails cleanly | Confirms the check is what prevents the larger allocation (a bigger request fails more gracefully than a smaller one). |
| Any N > 64 Mi gives alloc ≥ 256 MiB, OOM, or `NegativeArraySize`/"Requested array size exceeds VM limit" | **Claim wrong**: the check does not guard the allocation. |
| N = 64 Mi gives "invalid number of blocks" | Off-by-one or different limit: claim wrong at the boundary (the trace says `>`). |
| Alloc for N ≤ 64 Mi is far below 4N | Allocation is lazy or bounded elsewhere; the constant would not be what governs memory. Mechanism mis-traced. |
| Mutation build still accepts N = 4 Mi | The rejection does not come from this constant. Claim wrong. |
| `sentinel not found` or a CRC/length failure before `readBlocks` | Harness defect. The result says nothing about the claim. Fix the crafting and rerun. |

**B2h. Controls.**
- **Positive control:** the accepted values (4 Mi, 16 Mi, 64 Mi) show the instrument does see an array allocation that scales with N. So "< 1 MiB" for rejected values is not a blind instrument.
- **Mutation control:** with the constant lowered to 1 Mi, values that were accepted are now rejected. This ties the cutoff to `MAX_BLOCKS`, and not to `maxOpSize`, the CRC, or the JVM array limit.
- **Frame checks are not the reason:** the same op bytes, differing only in the 4 count bytes and the CRC, pass `decodeOpFrame` in all cases. The op length is constant and far below `maxOpSize`.
- **Clean measurement:** `System.gc()` before each case and per-thread counters keep other threads' allocation out of the numbers.

### B3. Cluster tier

**B3a. Environment and build.**
- **Host:** one Linux host, pseudo-distributed. Only a NameNode is needed: an empty file (`touchz`) creates OP_ADD/OP_CLOSE without any DataNode or block.
- **JDK:** JDK 11 runtime, for JFR and the `jfr` tool. JDK 8u262+ also works for recording; parse with a JDK 11 `jfr`.
- **Build:**
  1. `rsync -a ~/hadoop-3.4.2/ $RUN/src/`, then `cd $RUN/src && mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`.
  2. `tar xzf hadoop-dist/target/hadoop-3.4.2.tar.gz -C $RUN`, giving `HADOOP_HOME=$RUN/hadoop-3.4.2`.
- **Directories:** all on local disk under `$RUN`, about 1 GB free is enough.
  - `export HADOOP_CONF_DIR=$RUN/conf` (copied from `$HADOOP_HOME/etc/hadoop`);
  - `HADOOP_LOG_DIR=$RUN/logs`, `HADOOP_PID_DIR=$RUN/pids`;
  - `mkdir -p $RUN/{logs,pids,jfr,name,tmp}`.
- **`core-site.xml`:** `fs.defaultFS=hdfs://localhost:19000`, `hadoop.tmp.dir=$RUN/tmp`.
- **`hdfs-site.xml`:**
  - `dfs.namenode.name.dir=file://$RUN/name`, `dfs.replication=1`;
  - `dfs.namenode.http-address=localhost:19870`;
  - `dfs.namenode.secondary.http-address=localhost:19868`. The SNN is never started, so no checkpoint can absorb the edits.
  - Leave `dfs.namenode.max.op.size` at its default.
- **NameNode JVM**, set per run in `hadoop-env.sh` or the shell; `HADOOP_HEAPSIZE_MAX` stays unset:

```
export HDFS_NAMENODE_OPTS="-Xms64m -Xmx${HEAP} -XX:+PrintCommandLineFlags \
  -Xlog:gc*:file=$RUN/logs/nn-gc-${TAG}.log \
  -XX:StartFlightRecording=filename=$RUN/jfr/nn-${TAG}.jfr,settings=profile,dumponexit=true"
```

**B3b. Knobs.**
- **N**, the forged `numBlocks` in the on-disk OP_CLOSE of `/s4/f`: unpatched (pristine), 4,194,304, 67,108,864, 67,108,865, 2,147,483,647.
- **`HEAP`:** `1g` (a 256 MiB array fits) and `256m` (a 256 MiB + 16 B array cannot fit: with G1 it needs 257 contiguous 1 MiB regions; with ParallelGC it is larger than the old generation).
- **Run count:** the full grid is 10 runs.
- **Restarts:** every change takes effect only through a NameNode restart, which is the event that replays the edits. The constant can only change by replacing `share/hadoop/hdfs/hadoop-hdfs-3.4.2.jar` with the mutation build from B2b and restarting (mutation control).

**B3c. Workload.**
- **Setup:** format the namespace, then create `/s4/f` with `touchz`. This writes OP_MKDIR, OP_ADD and OP_CLOSE into a finalized edits segment. A clean NameNode stop finalizes and truncates the segment (`EditLogFileOutputStream.java:164`).
- **Patch:** a script patches `numBlocks` of that OP_CLOSE and recomputes its CRC. The NameNode restart then decodes it through the normal startup path: `FSImage.loadEdits` → `EditLogFileInputStream` → `LengthPrefixedReader` → `AddCloseOp.readFields` → `readBlocks`.
- **Size of the decoded data:** the op body holds about 10 bytes after the count. With N ≤ `MAX_BLOCKS` the array of `16 + 4N` bytes is allocated, and decoding fails at once with `EOFException` (or "Unexpected block size").
- **Duration:** each run lasts until the NameNode exits, a few seconds; allow up to 60 s.
- **Patch script** (`$RUN/bin/patch_numblocks.py`, kept outside the data directories). Layout used: header = int layoutVersion + int layoutFlags (`EditLogFileOutputStream.java:141-145`); op = opcode(1) + length(4) + txid(8) + body + crc(4), where length = 12 + body (`FSEditLogOp.java:4983-4996`); OP_CLOSE = 9 (`FSEditLogOpCodes.java:41`); body = inodeId(8) + path(u16 len + bytes) + replication(2) + mtime(8) + atime(8) + blockSize(8) + numBlocks(4) …

```python
#!/usr/bin/env python3
import struct, sys, zlib
f, path, n = sys.argv[1], sys.argv[2].encode(), int(sys.argv[3])
b = bytearray(open(f, 'rb').read())
pos, hit = 8, None
while pos + 5 <= len(b):
    opc = b[pos]
    if opc == 0xFF:
        break
    length = struct.unpack('>i', bytes(b[pos+1:pos+5]))[0]
    body = pos + 13
    if opc == 9:
        plen = struct.unpack('>H', bytes(b[body+8:body+10]))[0]
        if bytes(b[body+10:body+10+plen]) == path:
            hit = pos
            break
    pos += 1 + length + 4
if hit is None:
    sys.exit("OP_CLOSE for %s not found" % path)
nb = hit + 13 + 8 + 2 + len(path) + 2 + 8 + 8 + 8
old = struct.unpack('>i', bytes(b[nb:nb+4]))[0]
b[nb:nb+4] = struct.pack('>i', n)
length = struct.unpack('>i', bytes(b[hit+1:hit+5]))[0]
end = hit + 1 + length
b[end:end+4] = struct.pack('>I', zlib.crc32(bytes(b[hit:end])) & 0xffffffff)
open(f, 'wb').write(b)
print("patched OP_CLOSE at offset %d: numBlocks %d -> %d" % (hit, old, n))
```

**B3d. Observables and instruments.**
- **Outcome:** the NameNode log `$RUN/logs/hadoop-*-namenode-*.log`. `grep -E "invalid number of blocks|Java heap space|OutOfMemoryError|Unexpected block size|EOFException|Error replaying edit log|Exiting with status"` gives the outcome per run.
- **Allocation:** JFR event `jdk.ObjectAllocationOutsideTLAB`, enabled with stack traces in the `profile` settings. Run `jfr print --events jdk.ObjectAllocationOutsideTLAB $RUN/jfr/nn-$TAG.jfr` and select events with `objectClass = org.apache.hadoop.hdfs.protocol.Block[]` whose stack contains `FSEditLogOp$AddCloseOp.readBlocks`. Their `allocationSize` field is the measured array size.
- **Heap occupancy:** the GC log `nn-gc-$TAG.log` (humongous or old-generation occupancy jumps of about 256 MiB at N = 64 Mi on the 1g heap).
- **Effective JVM flags:** confirmed from `-XX:+PrintCommandLineFlags` in `$RUN/logs/hadoop-*-namenode-*.out` (MaxHeapSize, UseCompressedOops).
- **Liveness:** `jps` shows whether the NameNode process is alive.
- **Not observable:** a failed allocation (OOM) emits no allocation event. For those runs the log is the evidence. The array's lifetime is not visible; it is garbage once the exception propagates.

**B3e. Procedure.**
1. `export HADOOP_HOME=$RUN/hadoop-3.4.2 HADOOP_CONF_DIR=$RUN/conf HADOOP_LOG_DIR=$RUN/logs HADOOP_PID_DIR=$RUN/pids; export PATH=$HADOOP_HOME/bin:$PATH`. Write the configuration from B3a. Check that ports 19000, 19870 and 19868 are free with `ss -ltn`.
2. `hdfs namenode -format -nonInteractive`.
3. `TAG=setup HEAP=1g` (export `HDFS_NAMENODE_OPTS` as in B3a), then `hdfs --daemon start namenode`.
4. `hdfs dfsadmin -safemode wait`, then `hdfs dfs -mkdir /s4`, then `hdfs dfs -touchz /s4/f`.
5. `hdfs --daemon stop namenode`. Check with `jps` that no NameNode is left.
6. `cp -a $RUN/name $RUN/name.pristine`.
7. `SEG=$(ls $RUN/name/current/edits_0* | tail -1)`, then `hdfs oev -i $SEG -o $RUN/pristine.xml`. Confirm the file contains `OP_CLOSE` with `<PATH>/s4/f</PATH>` and no `<BLOCK>`. If OP_CLOSE is in an earlier segment, use the segment that contains it.
8. For each `HEAP` in {1g, 256m} and `N` in {pristine, 4194304, 67108864, 67108865, 2147483647}:
   1. `rm -rf $RUN/name && cp -a $RUN/name.pristine $RUN/name`.
   2. Unless N is pristine: `python3 $RUN/bin/patch_numblocks.py $RUN/name/current/<segment> /s4/f $N`. It must print `numBlocks 0 -> N`.
   3. Set `TAG=h${HEAP}-n${N}`, export `HDFS_NAMENODE_OPTS`, and run `hdfs --daemon start namenode`.
   4. Wait for the NameNode to exit or reach active, up to 60 s: `for i in $(seq 60); do jps | grep -q NameNode || break; sleep 1; done`.
   5. Save the outcome: `grep -E "<pattern from B3d>" $RUN/logs/hadoop-*-namenode-*.log | tail -5 > $RUN/out-$TAG.txt`.
   6. For the pristine run, also run `hdfs dfs -ls /s4`; it must list `f`.
   7. `hdfs --daemon stop namenode 2>/dev/null; jps`. No NameNode may be left.
   8. Rotate the log (`mv $RUN/logs/hadoop-*-namenode-*.log $RUN/logs/nn-$TAG.log`) so the next grep is clean.
   9. `jfr print --events jdk.ObjectAllocationOutsideTLAB $RUN/jfr/nn-$TAG.jfr > $RUN/jfr/nn-$TAG.txt`. Record the `Block[]` allocation sizes from `readBlocks` frames.
9. Mutation control:
   1. Build `hadoop-hdfs` from `$SRC2` (B2b) with `mvn -pl hadoop-hdfs-project/hadoop-hdfs package -DskipTests -Dmaven.javadoc.skip=true`.
   2. Back up `$HADOOP_HOME/share/hadoop/hdfs/hadoop-hdfs-3.4.2.jar` and copy the mutated jar over it.
   3. Rerun step 8 for `HEAP=1g`, with N = 4194304 and N = pristine.
   4. Restore the original jar.

**B3f. Predictions.** All predictions assume compressed oops; double every array size otherwise.

| HEAP | N | NameNode outcome (log) | JFR `Block[]` from `readBlocks` |
|---|---|---|---|
| 1g | pristine | starts, `/s4/f` listed | none ≥ 1 MiB |
| 1g | 4,194,304 | startup fails: "Error replaying edit log", cause `EOFException` (or "Unexpected block size") | one event, 16,777,232 B |
| 1g | 67,108,864 | same failure kind as 4 Mi | one event, 268,435,472 B |
| 1g | 67,108,865 | startup fails: "invalid number of blocks: 67108865.  The maximum number of blocks per file is 67108864" | none ≥ 1 MiB |
| 1g | 2,147,483,647 | "invalid number of blocks: 2147483647" | none ≥ 1 MiB |
| 256m | pristine | starts | none |
| 256m | 4,194,304 | `EOFException`, as at 1g | 16,777,232 B |
| 256m | 67,108,864 | startup fails with "got unexpected exception Java heap space" (OOM wrapped by `readOp`, `FSEditLogOp.java:5081-5085`) | none (failed allocation) |
| 256m | 67,108,865 | "invalid number of blocks: 67108865", no OOM | none |
| 256m | 2,147,483,647 | "invalid number of blocks", no OOM | none |
| 1g, mutated jar | 4,194,304 | "invalid number of blocks: 4194304.  The maximum … is 1048576" | none ≥ 1 MiB |

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Matches B3f: allocation of 16 + 4N up to N = 64 Mi; none and a clean "invalid number of blocks" above | Claim confirmed on a real NameNode: the constant caps the up-front edit-decode allocation at 256 MiB. |
| At 256m, N = 64 Mi OOMs while N = 64 Mi + 1 fails cleanly | Discriminating confirmation: only the check explains why the larger count uses less memory. |
| N > 64 Mi produces a large `Block[]` event, an OOM, or "Requested array size exceeds VM limit" | **Claim wrong**: the constant does not guard the allocation on the daemon path. |
| N = 64 Mi rejected | Boundary differs from the trace: claim wrong at the boundary. |
| N ≤ 64 Mi decodes with no large `Block[]` event | Allocation is lazy or elsewhere; the trace is wrong. |
| 64 Mi at 256m does not OOM | Heap larger than intended (check `PrintCommandLineFlags`; another `-Xmx` won) or compressed oops off. Not confirmed; lower the heap (keeping the pristine control starting) and rerun. |
| Pristine run fails, or patched runs fail with a checksum or "has size" error | Harness or patch defect (wrong segment or offset). The result says nothing; fix and rerun. |
| Mutation jar still accepts 4 Mi | The cutoff is not this constant. Claim wrong. |

**B3h. Controls.**
- **Pristine run:** the same NameNode, heap and edits without the patch start normally. This shows the failures come from the forged count, not from the setup or the heap size.
- **Positive control:** the accepted values (4 Mi, 64 Mi) at 1g show the JFR instrument records a `Block[]` allocation that scales with N on the daemon path.
- **Mutation control:** a jar with `MAX_BLOCKS = 1 Mi` rejects 4 Mi. This ties the cutoff to the constant, and not to `dfs.namenode.max.op.size`, the CRC, or JVM limits.
- **Identical framing:** every patched file differs from the pristine one only in 4 count bytes and 4 CRC bytes. The op length, and therefore the `maxOpSize` frame check, is identical across runs.
- **Clean state:** each run restores the pristine name directory, so no state carries over.

**B4. Risks and cleanup.**
- **Disk:** a few hundred MB per tree copy plus build output (several GB for the full dist build, about 1–2 GB of `~/.m2`), JFR files of a few MB each, and tiny name directories. Everything lives under `$SRC`, `$SRC2` and `$RUN` on local disk, never on shared storage and never inside the shared source tree.
- **Memory:** the test JVM and the NameNode allocate at most about 1 GB of heap each. Runs are sequential.
- **Ports:** 19000, 19870 and 19868 (check they are free first). No DataNode or YARN is started.
- **Leftover processes:** after every run, `hdfs --daemon stop namenode` and `jps` must show no `NameNode`. Surefire forks exit by themselves; check `jps` for a leftover `surefirebooter`.
- **The patched edits file:** it is corrupt by design. It exists only in `$RUN/name`, which is restored from `name.pristine` before each run. Never point this configuration at a real name directory.
- **Mutation jar:** restore the original jar after step 9 (keep the backup).
- **Final cleanup:** `rm -rf $RUN $SRC2` (and `$SRC` if no longer needed) after the results are saved.

## C. Sources read

- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLogOp.java (159-200, 425-760, 820-880, 1018-1030, 1115-1130, 2900-2930, 4960-5390)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSImageSerialization.java (347-378, 423-427, 502-520)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLogLoader.java (238-262, 1341)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLog.java (841, 870-878, 895)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSImage.java (715-735)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/EditLogFileOutputStream.java (120-165)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/EditLogFileInputStream.java (188, 213-282, 530)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/EditLogInputStream.java (78-100)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/StreamLimiter.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/NameNodeLayoutVersion.java (36, 82)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSEditLogOpCodes.java (31, 41)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DFSConfigKeys.java (625-626, 1251-1252)
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/DeprecatedUTF8.java
- hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/tools/offlineEditsViewer/OfflineEditsBinaryLoader.java (41-92)
- hadoop-hdfs-project/hadoop-hdfs/src/main/resources/hdfs-default.xml (480-495, 5386-5391)
- hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocol/Block.java (48-56, 214-231)
- hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestEditLog.java (990-1010)
- hadoop-hdfs-project/hadoop-hdfs/pom.xml (478)
- hadoop-project/pom.xml (172-187)
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/util/DataChecksum.java (93-95)
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/ArrayWritable.java (104-109)
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/UTF8.java (150-153)
- hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/ShortWritable.java (62-64)
- hadoop-common-project/hadoop-common/src/main/conf/hadoop-env.sh (79, 285-294)
- hadoop-common-project/hadoop-common/src/site/markdown/release/2.0.2-alpha/CHANGELOG.2.0.2-alpha.md (HDFS-3440 entry)
- hadoop-common-project/hadoop-common/src/site/markdown/release/2.8.0/CHANGELOG.2.8.0.md and 3.0.0-alpha1/CHANGELOG.3.0.0-alpha1.md (HDFS-8965 entry)
- https://issues.apache.org/jira/browse/HDFS-3440 (cited by title only, not opened)
- https://issues.apache.org/jira/browse/HDFS-8965 (cited by title only, not opened)

## D. Stage-4 feedback

none yet
