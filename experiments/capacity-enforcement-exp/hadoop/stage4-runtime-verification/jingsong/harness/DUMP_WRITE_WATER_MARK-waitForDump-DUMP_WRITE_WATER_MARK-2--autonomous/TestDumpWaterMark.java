/*
 * Stage-4 unit tier (B2) for DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-2--autonomous
 * (check OpenFileCtx.java:284). Copied only into the per-case source copy (never the repository):
 *   hadoop-hdfs-project/hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3/TestDumpWaterMark.java
 *
 * B2c workload: N = 255 out-of-order WRITEs of r = 64 KiB at offsets k*r (k = 1..255); offset 0 is
 * never written. DUMP_WRITE_WATER_MARK (M) is set by reflection per arm: 256 KiB, 1 MiB, 4 MiB;
 * control arm: dumpFilePath = null (dump disabled, no cap). Sequential sub-test: one write at
 * offset 0. Bypass probe (B2e step 5): dump file under a missing directory, M = 1 MiB.
 *
 * Amendment 2026-11-25 (instrument only): every receivedNewWrite runs on a daemon worker thread
 * and the test waits at most 10 s per call, so a blocked call is recorded (BLOCKED row) instead
 * of hanging the JVM; the blocked writer is freed afterwards for cleanup.
 *
 * Rows printed after each returned call (B2d):
 *   ROW,arm,M,k,counted,dumpLen,dumpedEntries,heldBytes,inCallPeakInferred
 *     counted   = nonSequentialWriteInMemory (operand of the :284 check)
 *     dumpLen   = length of the dump file
 *     dumpedEntries = pendingWrites entries in state DUMPED
 *     heldBytes = sum of capacities of WriteCtx.data buffers still referenced (heap held)
 *     inCallPeakInferred = counted before the call + r
 */
package org.apache.hadoop.hdfs.nfs.nfs3;

import java.io.File;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicLong;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.hadoop.hdfs.DFSClient;
import org.apache.hadoop.hdfs.client.HdfsDataOutputStream;
import org.apache.hadoop.hdfs.nfs.conf.NfsConfiguration;
import org.apache.hadoop.nfs.nfs3.FileHandle;
import org.apache.hadoop.nfs.nfs3.Nfs3Constant.WriteStableHow;
import org.apache.hadoop.nfs.nfs3.Nfs3FileAttributes;
import org.apache.hadoop.nfs.nfs3.request.WRITE3Request;
import org.apache.hadoop.security.ShellBasedIdMapping;
import org.apache.hadoop.test.GenericTestUtils;
import org.junit.After;
import org.junit.BeforeClass;
import org.junit.Test;
import org.mockito.Mockito;

public class TestDumpWaterMark {
  static final int R = 65536;
  static final int N = 255;
  static final long STOCK = 1024L * 1024;
  static final File TMP = new File(System.getProperty("dumpwm.tmp",
      GenericTestUtils.getTestDir("dumpwm").getPath()));
  static final Pattern UPD = Pattern.compile(
      "Update nonSequentialWriteInMemory by (-?\\d+) new value: (\\d+)");

  static NfsConfiguration conf;
  static ShellBasedIdMapping iug;

  OpenFileCtx ctx;
  ExecutorService ex;
  GenericTestUtils.LogCapturer logs;
  Future<?> lastBlocked;

  @BeforeClass
  public static void setupClass() throws Exception {
    conf = new NfsConfiguration();
    RpcProgramNfs3.metrics = Nfs3Metrics.create(conf, "dumpwm-test");
    iug = new ShellBasedIdMapping(conf);
    TMP.mkdirs();
    System.out.println("ENV,java=" + System.getProperty("java.version")
        + ",maxHeap=" + Runtime.getRuntime().maxMemory() + ",tmp=" + TMP);
  }

  static Field field(Class<?> c, String n) throws Exception {
    Field f = c.getDeclaredField(n);
    f.setAccessible(true);
    return f;
  }

  static void setMark(long m) throws Exception {
    Field f = field(OpenFileCtx.class, "DUMP_WRITE_WATER_MARK");
    f.setLong(null, m);
    System.out.println("KNOB,DUMP_WRITE_WATER_MARK=" + f.getLong(null));
  }

  static AtomicLong counter(OpenFileCtx c) throws Exception {
    return (AtomicLong) field(OpenFileCtx.class, "nonSequentialWriteInMemory").get(c);
  }

  @After
  public void tearDown() throws Exception {
    if (ctx != null) {
      unstick(ctx);
      ctx.cleanup();
      ctx = null;
    }
    if (logs != null) {
      logs.stopCapturing();
      logs = null;
    }
    if (ex != null) {
      ex.shutdownNow();
      ex = null;
    }
    setMark(STOCK);
  }

  /** Free a writer stuck in waitForDump (it ignores interrupts): counter to 0 and notifyAll. */
  static void unstick(OpenFileCtx c) throws Exception {
    synchronized (c) {
      counter(c).set(0);
      c.notifyAll();
    }
  }

  OpenFileCtx newCtx(String dumpPath) throws Exception {
    if (dumpPath != null) {
      new File(dumpPath).delete();
    }
    HdfsDataOutputStream fos = Mockito.mock(HdfsDataOutputStream.class);
    Mockito.when(fos.getPos()).thenReturn(0L);
    DFSClient dfs = Mockito.mock(DFSClient.class);
    OpenFileCtx c = new OpenFileCtx(fos, new Nfs3FileAttributes(), dumpPath, dfs, iug,
        false, new NfsConfiguration());
    GenericTestUtils.setLogLevel(OpenFileCtx.LOG, org.slf4j.event.Level.DEBUG);
    logs = GenericTestUtils.LogCapturer.captureLogs(OpenFileCtx.LOG);
    ex = Executors.newCachedThreadPool(r -> {
      Thread t = new Thread(r, "dumpwm-writer");
      t.setDaemon(true);
      return t;
    });
    return c;
  }

  static WRITE3Request req(long offset) {
    return new WRITE3Request(new FileHandle(1), offset, R, WriteStableHow.UNSTABLE,
        ByteBuffer.wrap(new byte[R]));
  }

  /** {counted, dumpLen, dumpedEntries, heldBytes, allowDumpBytes} */
  long[] state(OpenFileCtx c, String dumpPath) throws Exception {
    long counted = counter(c).get();
    long dumpLen = dumpPath == null ? -1 : new File(dumpPath).length();
    long dumped = 0, held = 0, allow = 0;
    Field data = field(WriteCtx.class, "data");
    for (Map.Entry<OffsetRange, WriteCtx> e : c.getPendingWritesForTest().entrySet()) {
      WriteCtx w = e.getValue();
      if (w.getDataState() == WriteCtx.DataState.DUMPED) {
        dumped++;
      } else if (w.getDataState() == WriteCtx.DataState.ALLOW_DUMP) {
        allow += w.getCount();
      }
      ByteBuffer bb = (ByteBuffer) data.get(w);
      if (bb != null) {
        held += bb.capacity();
      }
    }
    return new long[] {counted, dumpLen, dumped, held, allow};
  }

  /** {log peak of the counter, number of 'Create dump file' lines, number of decrements} */
  long[] parseLog() {
    String out = logs.getOutput();
    long peak = 0, dec = 0;
    Matcher mt = UPD.matcher(out);
    while (mt.find()) {
      long by = Long.parseLong(mt.group(1));
      peak = Math.max(peak, Long.parseLong(mt.group(2)));
      if (by < 0) {
        dec++;
      }
    }
    long create = out.split("Create dump file", -1).length - 1;
    return new long[] {peak, create, dec};
  }

  /** Runs one call on a worker; returns true if it returned within 10 s. */
  boolean call(final long offset, final int xid) throws Exception {
    final DFSClient dfs = Mockito.mock(DFSClient.class);
    final AsyncDataService ads = Mockito.mock(AsyncDataService.class);
    final WRITE3Request r = req(offset);
    Future<?> f = ex.submit(() -> ctx.receivedNewWrite(dfs, r, null, xid, ads, iug));
    try {
      f.get(10, TimeUnit.SECONDS);
      return true;
    } catch (TimeoutException te) {
      lastBlocked = f;
      return false;
    }
  }

  void arm(String name, long m, String dumpPath) throws Exception {
    setMark(m);
    ctx = newCtx(dumpPath);
    long maxAfter = 0, maxInferred = 0, prevCounted = 0;
    int returned = 0, sumViolations = 0, heldViolations = 0;
    boolean blocked = false;
    for (int k = 1; k <= N; k++) {
      boolean ok = call((long) k * R, k);
      long[] s = state(ctx, dumpPath);
      long inferred = prevCounted + R;
      if (!ok) {
        System.out.println("BLOCKED," + name + "," + m + "," + k + "," + s[0] + "," + s[1] + ","
            + s[2] + "," + s[3] + "," + inferred);
        blocked = true;
        break;
      }
      returned = k;
      maxAfter = Math.max(maxAfter, s[0]);
      maxInferred = Math.max(maxInferred, inferred);
      long dl = Math.max(s[1], 0);
      if (s[0] + dl != (long) k * R) {
        sumViolations++;
      }
      if (s[0] != s[3]) {
        heldViolations++;
      }
      System.out.println("ROW," + name + "," + m + "," + k + "," + s[0] + "," + s[1] + ","
          + s[2] + "," + s[3] + "," + inferred);
      prevCounted = s[0];
    }
    long[] lg = parseLog();
    long[] fin = state(ctx, dumpPath);
    boolean failLogged = logs.getOutput().contains("Got failure when creating dump stream");
    boolean enabledDump = field(OpenFileCtx.class, "enabledDump").getBoolean(ctx);
    System.out.println("SUMMARY," + name + ",M=" + m + ",returned=" + returned
        + ",blocked=" + blocked + ",maxCountedAfterCall=" + maxAfter
        + ",maxInCallPeakInferred=" + maxInferred + ",logPeak=" + lg[0]
        + ",finalCounted=" + fin[0] + ",finalDumpLen=" + fin[1]
        + ",finalDumpLenModM=" + (fin[1] < 0 ? -1 : fin[1] % m)
        + ",finalDumpedEntries=" + fin[2] + ",finalHeld=" + fin[3]
        + ",sumViolations=" + sumViolations + ",heldViolations=" + heldViolations
        + ",createDumpLines=" + lg[1] + ",logDecrements=" + lg[2]
        + ",dumpFailureLogged=" + failLogged + ",enabledDump=" + enabledDump);
    if (blocked) {
      // Extra observation (not a B2f prediction): with enabledDump now false, a second writer on
      // the same ctx is not held back by the mark (A3 "every later waitForDump returns").
      int k2 = returned + 2;
      int ret2 = 0;
      for (; k2 <= returned + 17; k2++) {
        if (!call((long) k2 * R, k2)) {
          break;
        }
        ret2++;
      }
      long[] s2 = state(ctx, dumpPath);
      System.out.println("PROBE2," + name + ",secondWriterCallsReturned=" + ret2
          + ",countedAfter=" + s2[0] + ",heldAfter=" + s2[3] + ",M=" + m
          + ",firstWriterStillBlocked=" + (lastBlocked != null && !lastBlocked.isDone()));
    }
    if (dumpPath != null) {
      unstick(ctx);
      ctx.cleanup();
      System.out.println("CLEANUP," + name + ",dumpFileExistsAfterCleanup="
          + new File(dumpPath).exists());
    }
  }

  @Test(timeout = 120000)
  public void mark256k() throws Exception {
    arm("m256k", 256L * 1024, new File(TMP, "dump-262144").getPath());
  }

  @Test(timeout = 120000)
  public void mark1m() throws Exception {
    arm("m1m", 1024L * 1024, new File(TMP, "dump-1048576").getPath());
  }

  @Test(timeout = 120000)
  public void mark4m() throws Exception {
    arm("m4m", 4L * 1024 * 1024, new File(TMP, "dump-4194304").getPath());
  }

  @Test(timeout = 120000)
  public void controlNoDump() throws Exception {
    arm("control", STOCK, null);
  }

  @Test(timeout = 60000)
  public void sequentialNotCounted() throws Exception {
    setMark(STOCK);
    String p = new File(TMP, "dump-seq").getPath();
    ctx = newCtx(p);
    boolean ok = call(0L, 1);
    long[] s = state(ctx, p);
    WriteCtx w = ctx.getPendingWritesForTest().firstEntry().getValue();
    System.out.println("SEQ,returned=" + ok + ",counted=" + s[0] + ",state="
        + w.getDataState() + ",pending=" + ctx.getPendingWritesForTest().size()
        + ",held=" + s[3]);
  }

  @Test(timeout = 120000)
  public void bypassProbeDumpDirMissing() throws Exception {
    arm("probeMissingDir", STOCK, new File(TMP, "no-such-dir/dump").getPath());
  }
}
