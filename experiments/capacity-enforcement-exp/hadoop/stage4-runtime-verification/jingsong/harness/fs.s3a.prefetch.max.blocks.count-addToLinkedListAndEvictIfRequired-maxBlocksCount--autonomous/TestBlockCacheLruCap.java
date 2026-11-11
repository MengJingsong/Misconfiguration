/*
 * Stage-4 unit tier (case-file B2, amended A1-A3) for
 * fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.
 * Copied into hadoop-common/src/test/java/org/apache/hadoop/fs/impl/prefetch/ of a per-run source copy.
 * Logs readings as IFCHK lines on stdout; asserts only that the setup ran (A2c), never on readings.
 */
package org.apache.hadoop.fs.impl.prefetch;

import java.io.File;
import java.io.IOException;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import org.junit.rules.Timeout;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.LocalDirAllocator;
import org.apache.hadoop.fs.statistics.DurationTracker;
import org.apache.hadoop.fs.statistics.IOStatistics;

import static org.junit.Assert.assertTrue;

public class TestBlockCacheLruCap {

  private static final int BLOCK = 1024 * 1024;
  private static final int PUTS = 20;
  private static final int REPS = 3;
  private static final int[] MAXES = {1, 2, 4, 8, 1000};

  @Rule
  public TemporaryFolder tmp = new TemporaryFolder(
      new File(System.getProperty("ifchk.tmp", System.getProperty("java.io.tmpdir"))));

  @Rule
  public Timeout timeout = new Timeout(600_000);

  /** Counting statistics (B2c). */
  static final class CountingStats implements PrefetchingStatistics {
    final AtomicInteger added = new AtomicInteger();
    final AtomicInteger removed = new AtomicInteger();
    final AtomicInteger evicted = new AtomicInteger();
    @Override public DurationTracker prefetchOperationStarted() { return null; }
    @Override public void blockAddedToFileCache() { added.incrementAndGet(); }
    @Override public void blockRemovedFromFileCache() { removed.incrementAndGet(); }
    @Override public void blockEvictedFromFileCache() { evicted.incrementAndGet(); }
    @Override public void prefetchOperationCompleted() { }
    @Override public void executorAcquired(Duration timeInQueue) { }
    @Override public void memoryAllocated(int size) { }
    @Override public void memoryFreed(int size) { }
    @Override public IOStatistics getIOStatistics() { return null; }
  }

  /** writeFile samples the in-put peak; readFile sleeps 7 s while the flag is set (B2b, A2b). */
  static final class InstrumentedCache extends SingleFilePerBlockCache {
    final File dir;
    final AtomicBoolean slowRead = new AtomicBoolean(false);
    volatile int lastPeak;
    volatile int maxPeak;

    InstrumentedCache(PrefetchingStatistics s, int max, File dir) {
      super(s, max, null);
      this.dir = dir;
    }

    @Override
    protected void writeFile(Path path, ByteBuffer buffer) throws IOException {
      super.writeFile(path, buffer);
      int n = (int) countFiles(dir)[0];
      lastPeak = n;
      maxPeak = Math.max(maxPeak, n);
    }

    @Override
    protected int readFile(Path path, ByteBuffer buffer) throws IOException {
      if (slowRead.get()) {
        try {
          Thread.sleep(7000);
        } catch (InterruptedException e) {
          Thread.currentThread().interrupt();
        }
      }
      return super.readFile(path, buffer);
    }

    int entryListSize() throws Exception {
      Field f = SingleFilePerBlockCache.class.getDeclaredField("entryListSize");
      f.setAccessible(true);
      return f.getInt(this);
    }
  }

  /** {count, bytes} of fs-cache-*.bin files directly in dir. */
  static long[] countFiles(File dir) throws IOException {
    long n = 0, bytes = 0;
    try (DirectoryStream<Path> ds = Files.newDirectoryStream(dir.toPath(), "fs-cache-*.bin")) {
      for (Path p : ds) {
        n++;
        bytes += Files.size(p);
      }
    }
    return new long[]{n, bytes};
  }

  static ByteBuffer block(int b) {
    ByteBuffer buf = ByteBuffer.allocate(BLOCK);
    for (int i = 0; i < BLOCK; i++) {
      buf.put((byte) b);
    }
    buf.flip();
    return buf;
  }

  private static final class Env {
    final File dir;
    final Configuration conf = new Configuration(false);
    final LocalDirAllocator alloc;
    final CountingStats stats = new CountingStats();
    final InstrumentedCache cache;

    Env(TemporaryFolder tmp, int max) throws IOException {
      dir = tmp.newFolder();
      conf.set("test.prefetch.dir", dir.getAbsolutePath());
      alloc = new LocalDirAllocator("test.prefetch.dir");
      cache = new InstrumentedCache(stats, max, dir);
    }

    void put(int b) throws IOException {
      cache.put(b, block(b), conf, alloc);
    }

    String row() throws Exception {
      long[] fb = countFiles(dir);
      return cache.size() + "," + fb[0] + "," + fb[1] + "," + cache.entryListSize() + ","
          + cache.lastPeak + "," + stats.evicted.get() + "," + stats.added.get() + ","
          + stats.removed.get();
    }
  }

  private static void out(String s) {
    System.out.println("IFCHK," + s);
  }

  @Test
  public void testCapScales() throws Exception {
    out("instr,java=" + System.getProperty("java.version") + ",block=" + BLOCK + ",puts=" + PUTS
        + ",tmp=" + tmp.getRoot());
    int rows = 0;
    for (int max : MAXES) {
      for (int rep = 1; rep <= REPS; rep++) {
        Env e = new Env(tmp, max);
        for (int b = 0; b < PUTS; b++) {
          e.put(b);
          out("cap," + max + "," + rep + "," + b + "," + e.row());
          rows++;
        }
        out("peak," + max + "," + rep + "," + e.cache.maxPeak);
        e.cache.close();
        out("close," + max + "," + rep + "," + countFiles(e.dir)[0] + "," + e.stats.removed.get());
      }
    }
    assertTrue("setup ran", rows == MAXES.length * REPS * PUTS);
  }

  @Test
  public void testLruOrder() throws Exception {
    for (int rep = 1; rep <= REPS; rep++) {
      Env e = new Env(tmp, 4);
      for (int b = 0; b < 4; b++) {
        e.put(b);
      }
      ByteBuffer buf = ByteBuffer.allocate(BLOCK);
      e.cache.get(0, buf);
      e.put(4);
      out("lru," + rep + "," + e.cache.containsBlock(0) + "," + e.cache.containsBlock(1) + ","
          + e.row());
      e.cache.close();
      out("lruclose," + rep + "," + countFiles(e.dir)[0]);
    }
  }

  @Test
  public void testEvictionLockTimeoutLeaks() throws Exception {
    for (int rep = 1; rep <= REPS; rep++) {
      final Env e = new Env(tmp, 2);
      e.put(0);
      e.put(1);
      out("bypass," + rep + ",after1,-1," + e.cache.containsBlock(0) + "," + e.row());
      e.cache.slowRead.set(true);
      final AtomicInteger errs = new AtomicInteger();
      Thread a = new Thread(() -> {
        try {
          e.cache.get(0, ByteBuffer.allocate(BLOCK));
        } catch (Exception ex) {
          errs.incrementAndGet();
          ex.printStackTrace(System.out);
        }
      }, "ifchk-A");
      Thread bt = new Thread(() -> {
        try {
          e.cache.get(1, ByteBuffer.allocate(BLOCK));
        } catch (Exception ex) {
          errs.incrementAndGet();
          ex.printStackTrace(System.out);
        }
      }, "ifchk-B");
      a.start();
      Thread.sleep(200);
      bt.start();
      Thread.sleep(200);
      long t0 = System.nanoTime();
      e.put(2);
      long ms = (System.nanoTime() - t0) / 1_000_000;
      out("bypass," + rep + ",after2," + ms + "," + e.cache.containsBlock(0) + "," + e.row());
      a.join();
      bt.join();
      e.cache.slowRead.set(false);
      e.put(3);
      out("bypass," + rep + ",after3,-1," + e.cache.containsBlock(0) + "," + e.row());
      e.put(4);
      out("bypass," + rep + ",after4,-1," + e.cache.containsBlock(0) + "," + e.row());
      e.cache.close();
      out("bypass," + rep + ",close,-1," + e.cache.containsBlock(0) + "," + countFiles(e.dir)[0]
          + ",getErrors=" + errs.get());
    }
  }
}
