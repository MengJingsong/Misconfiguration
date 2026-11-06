/*
 * Stage-4 harness (if-check-exp, Hadoop, Jingsong's share), case
 * fs.s3a.prefetch.block.count-acquireHelper-size--autonomous, unit tier B2 (amended A1-A4).
 * Not upstream. Copied into hadoop-tools/hadoop-aws/src/test/java/org/apache/hadoop/fs/s3a/prefetch/ of a per-run copy.
 *
 * Per prefetchBlockCount c: sequential read of a 64 MiB fake object (1 MiB blocks) in 64 KiB chunks with a 20 ms sleep per MiB,
 * then 100 random 1-byte reads; observes the operand createdItems.size() (BoundedResourcePool.java:176) through toString() and a
 * block-manager hook, and counts "denials" (requestPrefetch for a block that gets no buffer = tryAcquire returned null).
 * Asserts nothing about the claim; prints IFCHK lines.
 */
package org.apache.hadoop.fs.s3a.prefetch;

import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.util.Random;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.zip.CRC32;

import javax.annotation.Nonnull;

import org.junit.After;
import org.junit.Test;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.impl.prefetch.BlockManager;
import org.apache.hadoop.fs.impl.prefetch.BlockManagerParameters;
import org.apache.hadoop.fs.impl.prefetch.BoundedResourcePool;
import org.apache.hadoop.fs.impl.prefetch.BufferData;
import org.apache.hadoop.fs.impl.prefetch.BufferPool;
import org.apache.hadoop.fs.impl.prefetch.CachingBlockManager;
import org.apache.hadoop.fs.impl.prefetch.ExecutorServiceFuturePool;
import org.apache.hadoop.fs.s3a.Constants;
import org.apache.hadoop.fs.s3a.S3AReadOpContext;
import org.apache.hadoop.fs.s3a.S3AUtils;
import org.apache.hadoop.fs.s3a.S3ObjectAttributes;
import org.apache.hadoop.fs.s3a.impl.streams.ObjectInputStreamCallbacks;
import org.apache.hadoop.fs.s3a.statistics.S3AInputStreamStatistics;

public class TestPrefetchPoolBound {

  private static final int BS = 1 << 20;            // prefetchBlockSize 1 MiB
  private static final int FILE = 64 * BS;          // 64 MiB, 64 blocks
  private static final int CHUNK = 64 * 1024;
  private static final Pattern POOL = Pattern.compile("size = (\\d+), #created = (\\d+)");

  private final ExecutorService threadPool = Executors.newFixedThreadPool(32);
  private final ExecutorServiceFuturePool futurePool = new ExecutorServiceFuturePool(threadPool);

  /** Set by ProbeStream.createBlockManager (called from the super constructor). */
  private static final ThreadLocal<ProbeBlockManager> LAST = new ThreadLocal<>();

  @After
  public void teardown() throws Exception {
    threadPool.shutdownNow();
    threadPool.awaitTermination(30, TimeUnit.SECONDS);
  }

  // ---------------------------------------------------------------- instruments

  private static Object field(Object o, Class<?> c, String name) {
    try {
      Field f = c.getDeclaredField(name);
      f.setAccessible(true);
      return f.get(o);
    } catch (ReflectiveOperationException e) {
      throw new IllegalStateException(e);
    }
  }

  /** Block manager with a read-only hook on the pool after every requestPrefetch/get. */
  static class ProbeBlockManager extends S3APrefetchFakes.FakeS3ACachingBlockManager {
    volatile int maxCreated;
    volatile int poolSize = -1;
    volatile int denials;
    volatile int denialsAtFull;
    volatile int prefetchCalls;

    ProbeBlockManager(@Nonnull BlockManagerParameters p, S3ARemoteObjectReader r) {
      super(p, r);
    }

    BufferPool bufferPool() {
      return (BufferPool) field(this, CachingBlockManager.class, "bufferPool");
    }

    @SuppressWarnings("unchecked")
    BoundedResourcePool<?> pool() {
      BufferPool bp = bufferPool();
      return bp == null ? null : (BoundedResourcePool<?>) field(bp, BufferPool.class, "pool");
    }

    int created() {
      BoundedResourcePool<?> p = pool();
      if (p == null) {
        return -1;
      }
      if (poolSize < 0) {
        poolSize = (Integer) field(p, BoundedResourcePool.class, "size");
      }
      int n = p.numCreated();
      if (n > maxCreated) {
        maxCreated = n;
      }
      return n;
    }

    boolean held(int b) {
      BufferPool bp = bufferPool();
      if (bp == null) {
        return false;
      }
      for (BufferData d : bp.getAll()) {
        if (d.getBlockNumber() == b) {
          return true;
        }
      }
      return false;
    }

    @Override
    public void requestPrefetch(int blockNumber) {
      boolean pre = held(blockNumber);
      super.requestPrefetch(blockNumber);
      boolean post = held(blockNumber);
      int n = created();
      prefetchCalls++;
      if (!pre && !post) {
        denials++;
        if (n == poolSize) {
          denialsAtFull++;
        }
      }
    }

    @Override
    public BufferData get(int blockNumber) throws IOException {
      BufferData d = super.get(blockNumber);
      created();
      return d;
    }
  }

  static class ProbeStream extends S3APrefetchFakes.FakeS3ACachingInputStream {
    ProbeStream(S3AReadOpContext context, PrefetchOptions options, S3ObjectAttributes attrs,
        ObjectInputStreamCallbacks client, S3AInputStreamStatistics stats) {
      super(context, options, attrs, client, stats);
    }

    @Override
    protected BlockManager createBlockManager(@Nonnull BlockManagerParameters p,
        S3ARemoteObjectReader reader) {
      ProbeBlockManager m = new ProbeBlockManager(p, reader);
      LAST.set(m);
      return m;
    }
  }

  private ProbeStream open(int count) {
    S3ObjectAttributes attrs = S3APrefetchFakes.createObjectAttributes("bucket", "key", FILE);
    S3AReadOpContext ctx = S3APrefetchFakes.createReadContext(futurePool, "key", FILE);
    ObjectInputStreamCallbacks cb = S3APrefetchFakes.createInputStreamCallbacks("bucket");
    S3AInputStreamStatistics stats = ctx.getS3AStatisticsContext().newInputStreamStatistics();
    return new ProbeStream(ctx, new PrefetchOptions(BS, count), attrs, cb, stats);
  }

  private static long heap() {
    for (int i = 0; i < 3; i++) {
      System.gc();
    }
    return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
  }

  /** [printedSize, printedCreated] from stream.toString(), or null. */
  private static int[] printed(Object stream) {
    Matcher m = POOL.matcher(stream.toString());
    return m.find() ? new int[] {Integer.parseInt(m.group(1)), Integer.parseInt(m.group(2))} : null;
  }

  // ---------------------------------------------------------------- the knob sweep (B2b, B2c, B2e step 1)

  private void runCount(int c) throws Exception {
    long heapBefore = heap();
    ProbeStream s = open(c);
    ProbeBlockManager m = LAST.get();
    int printedSize = -1;
    int seqMax = 0;
    long heapPeak = -1;
    byte[] buf = new byte[CHUNK];
    CRC32 crc = new CRC32();
    long total = 0;
    long nextMiB = BS;
    int r;
    while ((r = s.read(buf, 0, CHUNK)) > 0) {
      crc.update(buf, 0, r);
      total += r;
      if (total >= nextMiB) {
        int[] p = printed(s);
        if (p != null) {
          printedSize = p[0];
          seqMax = Math.max(seqMax, p[1]);
        }
        if (heapPeak < 0 && total >= 32L * BS) {
          heapPeak = heap();
        }
        nextMiB += BS;
        Thread.sleep(20);
      }
    }
    int seqDenials = m.denials;
    int seqHookMax = m.maxCreated;
    // A2: random sub-workload on the same stream
    Random rnd = new Random(20261106L + c);
    int rndMax = 0;
    int mismatches = 0;
    for (int i = 0; i < 100; i++) {
      int off = rnd.nextInt(FILE);
      s.seek(off);
      int v = s.read();
      if (v != (MockS3ARemoteObject.byteAtOffset(off) & 0xff)) {
        mismatches++;
      }
      int[] p = printed(s);
      if (p != null) {
        rndMax = Math.max(rndMax, p[1]);
      }
    }
    int rndDenials = m.denials - seqDenials;
    int hookMax = m.maxCreated;
    int poolSize = m.poolSize;
    int atFull = m.denialsAtFull;
    s.close();
    long heapAfter = heap();
    System.out.println(String.format(
        "IFCHK,count,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d",
        c, printedSize, poolSize, seqMax, rndMax, hookMax, seqDenials, rndDenials, atFull,
        crc.getValue(), mismatches, heapBefore, heapPeak, heapAfter));
    System.out.println(String.format("IFCHK-DETAIL,count,%d,bytes=%d,seqHookMax=%d,prefetchCalls=%d",
        c, total, seqHookMax, m.prefetchCalls));
  }

  @Test(timeout = 300000)
  public void testCount01() throws Exception {
    runCount(1);
  }

  @Test(timeout = 300000)
  public void testCount02() throws Exception {
    runCount(2);
  }

  @Test(timeout = 300000)
  public void testCount04() throws Exception {
    runCount(4);
  }

  @Test(timeout = 300000)
  public void testCount08() throws Exception {
    runCount(8);
  }

  @Test(timeout = 300000)
  public void testCount16() throws Exception {
    runCount(16);
  }

  // ---------------------------------------------------------------- controls (B2h)

  @Test(timeout = 300000)
  public void testControls() throws Exception {
    // (2) in-memory bypass: 512 KiB file, block 1 MiB -> S3AInMemoryInputStream, no pool
    S3APrefetchFakes.FakeS3AInMemoryInputStream mem =
        S3APrefetchFakes.createS3InMemoryInputStream(futurePool, "bucket", "key", 512 * 1024);
    byte[] buf = new byte[CHUNK];
    long total = 0;
    int r;
    while ((r = mem.read(buf, 0, CHUNK)) > 0) {
      total += r;
    }
    String ts = mem.toString().replace('\n', '|');
    System.out.println("IFCHK-CTL,inmemory,bytes=" + total + ",hasCreated=" + ts.contains("#created")
        + ",toString=" + ts);
    mem.close();
    // (4) count = 0: PrefetchOptions and the factory's intOption must reject it
    String opt;
    try {
      new PrefetchOptions(BS, 0);
      opt = "accepted";
    } catch (IllegalArgumentException e) {
      opt = "rejected:" + e.getMessage();
    }
    String conf;
    try {
      Configuration cf = new Configuration(false);
      cf.setInt(Constants.PREFETCH_BLOCK_COUNT_KEY, 0);
      S3AUtils.intOption(cf, Constants.PREFETCH_BLOCK_COUNT_KEY, Constants.PREFETCH_BLOCK_DEFAULT_COUNT, 1);
      conf = "accepted";
    } catch (IllegalArgumentException e) {
      conf = "rejected:" + e.getMessage();
    }
    System.out.println("IFCHK-CTL,count0,PrefetchOptions=" + opt + ",intOption=" + conf);
  }
}
