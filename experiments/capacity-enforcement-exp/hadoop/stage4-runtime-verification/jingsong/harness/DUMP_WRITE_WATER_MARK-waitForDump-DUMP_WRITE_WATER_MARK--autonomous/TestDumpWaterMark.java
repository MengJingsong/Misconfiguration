/*
 * Stage-4 unit tier (B2) for DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK--autonomous.
 * Copied into the per-case source copy only (never into the repository's source tree):
 *   hadoop-hdfs-project/hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3/TestDumpWaterMark.java
 * Drives OpenFileCtx.receivedNewWrite directly with out-of-order WRITEs (the hole [0, C) is never
 * filled), varies DUMP_WRITE_WATER_MARK by reflection, and records after every WRITE:
 *   M  = nonSequentialWriteInMemory (the check's operand, OpenFileCtx.java:278)
 *   D  = dump file length
 *   AD = summed count of ALLOW_DUMP entries in pendingWrites, DC = number of DUMPED entries
 *   HB = bytes of payload ByteBuffers still referenced by WriteCtx.data (the heap actually held)
 * Peak of M: from the DEBUG log line "Update nonSequentialWriteInMemory by X new value: Y"
 * (OpenFileCtx.java:213-214). (An AtomicLong-subclass peak instrument was planned but cannot compile:
 * AtomicLong.addAndGet is final on JDK 8; removed 2026-11-25 before any reading.)
 */
package org.apache.hadoop.hdfs.nfs.nfs3;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.io.File;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
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
  static final int C = 65536;
  static final int N = 250;
  static final long STOCK = 1048576L;
  static final File TMP = new File(System.getProperty("dumpwm.tmp",
      System.getProperty("java.io.tmpdir") + "/dumpwm"));
  static final Pattern UPD = Pattern.compile(
      "Update nonSequentialWriteInMemory by (-?\\d+) new value: (\\d+)");

  static NfsConfiguration conf;
  static ShellBasedIdMapping iug;
  OpenFileCtx ctx;
  AsyncDataService ads;
  ExecutorService ex;
  GenericTestUtils.LogCapturer logs;

  @BeforeClass
  public static void setup() throws Exception {
    conf = new NfsConfiguration();
    RpcProgramNfs3.metrics = Nfs3Metrics.create(conf, "dumpwm");
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

  static void setW(long w) throws Exception {
    Field f = field(OpenFileCtx.class, "DUMP_WRITE_WATER_MARK");
    f.setLong(null, w);
    System.out.println("KNOB,DUMP_WRITE_WATER_MARK=" + f.getLong(null));
  }

  @After
  public void tearDown() throws Exception {
    if (logs != null) {
      logs.stopCapturing();
    }
    if (ctx != null) {
      unstick(ctx);
      ctx.cleanup();
    }
    if (ads != null) {
      ads.shutdown();
    }
    if (ex != null) {
      ex.shutdownNow();
    }
    setW(STOCK);
  }

  /** Free a writer stuck in waitForDump (it ignores interrupts): counter to 0, notifyAll. */
  static void unstick(OpenFileCtx c) throws Exception {
    AtomicLong cnt = (AtomicLong) field(OpenFileCtx.class,
        "nonSequentialWriteInMemory").get(c);
    synchronized (c) {
      cnt.set(0);
      c.notifyAll();
    }
  }

  OpenFileCtx newCtx(String dumpPath) throws Exception {
    Nfs3FileAttributes attr = new Nfs3FileAttributes();
    HdfsDataOutputStream fos = Mockito.mock(HdfsDataOutputStream.class);
    Mockito.when(fos.getPos()).thenReturn(0L);
    DFSClient dfs = Mockito.mock(DFSClient.class);
    OpenFileCtx c = new OpenFileCtx(fos, attr, dumpPath, dfs, iug, false, conf);
    ads = new AsyncDataService();
    GenericTestUtils.setLogLevel(OpenFileCtx.LOG, org.slf4j.event.Level.DEBUG);
    logs = GenericTestUtils.LogCapturer.captureLogs(OpenFileCtx.LOG);
    ThreadFactory tf = r -> {
      Thread t = new Thread(r, "dumpwm-writer");
      t.setDaemon(true);
      return t;
    };
    ex = Executors.newCachedThreadPool(tf);
    return c;
  }

  static WRITE3Request req(long offset, int i) {
    byte[] b = new byte[C];
    for (int k = 0; k < C; k++) {
      b[k] = (byte) (i + k);
    }
    return new WRITE3Request(new FileHandle(1), offset, C, WriteStableHow.UNSTABLE,
        ByteBuffer.wrap(b));
  }

  long[] state(OpenFileCtx c, String dumpPath) throws Exception {
    long m = ((AtomicLong) field(OpenFileCtx.class, "nonSequentialWriteInMemory")
        .get(c)).get();
    long d = dumpPath == null ? -1 : new File(dumpPath).length();
    long ad = 0, dc = 0, hb = 0;
    Field data = field(WriteCtx.class, "data");
    for (Map.Entry<OffsetRange, WriteCtx> e : c.getPendingWritesForTest().entrySet()) {
      WriteCtx w = e.getValue();
      if (w.getDataState() == WriteCtx.DataState.ALLOW_DUMP) {
        ad += w.getCount();
      } else if (w.getDataState() == WriteCtx.DataState.DUMPED) {
        dc++;
      }
      ByteBuffer bb = (ByteBuffer) data.get(w);
      if (bb != null) {
        hb += bb.capacity();
      }
    }
    return new long[] {m, d, ad, dc, hb};
  }

  /** Saves the captured OpenFileCtx log of one case next to the dump files (evidence). */
  void saveLog(String name) throws Exception {
    java.nio.file.Files.write(new File(TMP, name + "-openfilectx.log").toPath(),
        logs.getOutput().getBytes(java.nio.charset.StandardCharsets.UTF_8));
  }

  /** Returns {logPeak, createDumpLines, negativeUpdates (dump decrements)}. */
  long[] parseLog() {
    long peak = 0, neg = 0;
    Matcher mt = UPD.matcher(logs.getOutput());
    while (mt.find()) {
      long by = Long.parseLong(mt.group(1));
      long v = Long.parseLong(mt.group(2));
      if (by < 0) {
        neg++;
      }
      peak = Math.max(peak, v);
    }
    String out = logs.getOutput();
    long create = out.split("Create dump file", -1).length - 1;
    return new long[] {peak, create, neg};
  }

  /** Single writer, offsets i*C for i = 1..N; stops at the first WRITE not returning in 10 s. */
  void runSingle(String name, long w, String dumpPath) throws Exception {
    setW(w);
    ctx = newCtx(dumpPath);
    DFSClient dfs = Mockito.mock(DFSClient.class);
    int lastReturned = 0;
    boolean blocked = false;
    long maxMAfterReturn = 0;
    int dumpRounds = 0;
    long prevD = 0;
    for (int i = 1; i <= N; i++) {
      final WRITE3Request r = req((long) i * C, i);
      final int xid = i;
      Future<?> f = ex.submit(() -> ctx.receivedNewWrite(dfs, r, null, xid, ads, iug));
      try {
        f.get(10, TimeUnit.SECONDS);
      } catch (TimeoutException te) {
        long[] s = state(ctx, dumpPath);
        String stack = "";
        for (Map.Entry<Thread, StackTraceElement[]> e : Thread.getAllStackTraces().entrySet()) {
          if (e.getKey().getName().equals("dumpwm-writer")) {
            stack = e.getKey().getState() + " " + java.util.Arrays.toString(e.getValue());
          }
        }
        System.out.println("BLOCKED," + name + "," + i + "," + s[0] + "," + s[1] + "," + s[2]
            + "," + s[3] + "," + s[4]);
        System.out.println("BLOCKSTACK," + name + "," + stack);
        blocked = true;
        break;
      }
      lastReturned = i;
      long[] s = state(ctx, dumpPath);
      maxMAfterReturn = Math.max(maxMAfterReturn, s[0]);
      if (dumpPath != null && s[1] > prevD) {
        dumpRounds++;
        prevD = s[1];
      }
      System.out.println("ROW," + name + "," + i + "," + s[0] + "," + s[1] + "," + s[2] + ","
          + s[3] + "," + s[4]);
    }
    long[] lg = parseLog();
    saveLog(name);
    long[] fin = state(ctx, dumpPath);
    String failLine = logs.getOutput().contains("Got failure when creating dump stream")
        ? "yes" : "no";
    System.out.println("SUMMARY," + name + ",W=" + w + ",lastReturned=" + lastReturned
        + ",blocked=" + blocked + ",maxMAfterReturn=" + maxMAfterReturn + ",logPeak=" + lg[0]
        + ",finalM=" + fin[0] + ",finalD=" + fin[1]
        + ",finalAD=" + fin[2] + ",finalDC=" + fin[3] + ",finalHB=" + fin[4]
        + ",dumpRoundsObserved=" + dumpRounds + ",createDumpLines=" + lg[1]
        + ",dumpDecrements=" + lg[2] + ",dumpFailureLogged=" + failLine);
    // dump file removed by cleanup (checked after cleanup)
    if (dumpPath != null && !blocked) {
      unstick(ctx);
      ctx.cleanup();
      System.out.println("CLEANUP," + name + ",dumpFileExistsAfterCleanup="
          + new File(dumpPath).exists());
    }
  }

  @Test
  public void wm256k() throws Exception {
    runSingle("wm256k", 262144L, new File(TMP, "ctx-wm256k").getPath());
  }

  @Test
  public void wm1m() throws Exception {
    runSingle("wm1m", 1048576L, new File(TMP, "ctx-wm1m").getPath());
  }

  @Test
  public void wm4m() throws Exception {
    runSingle("wm4m", 4194304L, new File(TMP, "ctx-wm4m").getPath());
  }

  @Test
  public void dumpDisabled() throws Exception {
    runSingle("dumpDisabled", 1048576L, null);
  }

  @Test
  public void dumpDirMissing() throws Exception {
    runSingle("dumpDirMissing", 1048576L, new File(TMP, "no-such-dir/1").getPath());
  }

  /** Optional: 4 writer threads on disjoint offsets of the same file, W = 1 MiB. */
  @Test
  public void concurrent4() throws Exception {
    final String dumpPath = new File(TMP, "ctx-concurrent4").getPath();
    setW(STOCK);
    ctx = newCtx(dumpPath);
    final DFSClient dfs = Mockito.mock(DFSClient.class);
    final AtomicLong maxAfter = new AtomicLong();
    List<Future<?>> fs = new ArrayList<>();
    for (int t = 0; t < 4; t++) {
      final int tt = t;
      fs.add(ex.submit(() -> {
        for (int i = 1 + tt; i <= N; i += 4) {
          ctx.receivedNewWrite(dfs, req((long) i * C, i), null, i, ads, iug);
          try {
            long m = ((AtomicLong) field(OpenFileCtx.class, "nonSequentialWriteInMemory")
                .get(ctx)).get();
            maxAfter.accumulateAndGet(m, Math::max);
          } catch (Exception e) {
            throw new RuntimeException(e);
          }
        }
        return null;
      }));
    }
    boolean ok = true;
    for (Future<?> f : fs) {
      try {
        f.get(60, TimeUnit.SECONDS);
      } catch (TimeoutException te) {
        ok = false;
      }
    }
    long[] lg = parseLog();
    saveLog("concurrent4");
    long[] fin = state(ctx, dumpPath);
    System.out.println("SUMMARY,concurrent4,W=" + STOCK + ",allReturned=" + ok
        + ",maxMAfterReturn=" + maxAfter.get() + ",logPeak=" + lg[0]
        + ",finalM=" + fin[0] + ",finalD=" + fin[1] + ",finalAD=" + fin[2] + ",finalDC="
        + fin[3] + ",finalHB=" + fin[4] + ",createDumpLines=" + lg[1]
        + ",sumCheck=" + (fin[0] + fin[1]) + "/" + ((long) N * C));
  }
}
