/*
 * Stage-4 harness, capacity-enforcement-exp (Hadoop, Jingsong), order 20:
 * dfs.journalnode.edit-cache-size.bytes-storeEdits-capacity--autonomous, unit tier (B2).
 * Prints readings only (lines starting with "CAPU "); the conclusion is drawn from the printed
 * readings against B2f/B2g, so no assertion stops a method before its readings are out.
 */
package org.apache.hadoop.hdfs.qjournal.server;

import static org.apache.hadoop.hdfs.qjournal.QJMTestUtil.createTxnData;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.NavigableMap;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.hdfs.DFSConfigKeys;
import org.apache.hadoop.hdfs.server.namenode.NameNodeLayoutVersion;
import org.apache.hadoop.test.GenericTestUtils.LogCapturer;
import org.junit.Test;

public class TestJournaledEditsCacheCap {

  private static final int LV = NameNodeLayoutVersion.CURRENT_LAYOUT_VERSION;

  private static void p(String s) {
    System.out.println("CAPU " + s);
    System.out.flush();
  }

  private static int totalSize(JournaledEditsCache c) throws Exception {
    Field f = JournaledEditsCache.class.getDeclaredField("totalSize");
    f.setAccessible(true);
    return f.getInt(c);
  }

  @SuppressWarnings("unchecked")
  private static NavigableMap<Long, byte[]> dataMap(JournaledEditsCache c) throws Exception {
    Field f = JournaledEditsCache.class.getDeclaredField("dataMap");
    f.setAccessible(true);
    return (NavigableMap<Long, byte[]>) f.get(c);
  }

  private static long sumLen(JournaledEditsCache c) throws Exception {
    long s = 0;
    for (byte[] b : dataMap(c).values()) {
      s += b.length;
    }
    return s;
  }

  private static String state(JournaledEditsCache c) throws Exception {
    return "totalSize=" + totalSize(c) + " entries=" + dataMap(c).size() + " sumLen=" + sumLen(c)
        + " capacity=" + c.getCapacity();
  }

  /** jcmd GC.class_histogram on this JVM (JDK 8 jcmd); prints the [B, TreeMap$Entry, Long rows. */
  private static void histogram(String tag) throws Exception {
    String pid = ManagementFactory.getRuntimeMXBean().getName().split("@")[0];
    String jcmd = System.getProperty("java.home").replaceAll("/jre$", "") + "/bin/jcmd";
    Process pr = new ProcessBuilder(jcmd, pid, "GC.class_histogram").redirectErrorStream(true).start();
    BufferedReader r = new BufferedReader(new InputStreamReader(pr.getInputStream(), "UTF-8"));
    String line;
    while ((line = r.readLine()) != null) {
      String t = line.trim();
      if (t.endsWith(" [B") || t.endsWith(" java.util.TreeMap$Entry") || t.endsWith(" java.lang.Long")
          || t.startsWith("Total")) {
        p("HISTO " + tag + " " + t.replaceAll("\\s+", " "));
      }
    }
    pr.waitFor();
    System.gc();
    p("HEAPUSED " + tag + " " + ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed());
  }

  private static JournaledEditsCache cacheWithBytes(int bytes) {
    Configuration conf = new Configuration();
    conf.setInt(DFSConfigKeys.DFS_JOURNALNODE_EDIT_CACHE_SIZE_KEY, bytes);
    return new JournaledEditsCache(conf);
  }

  private static void env() {
    p("ENV maxMemory=" + Runtime.getRuntime().maxMemory() + " java=" + System.getProperty("java.version")
        + " gcs=" + gcNames());
  }

  private static String gcNames() {
    StringBuilder sb = new StringBuilder();
    for (java.lang.management.GarbageCollectorMXBean g : ManagementFactory.getGarbageCollectorMXBeans()) {
      sb.append(g.getName().replace(' ', '_')).append(',');
    }
    return sb.toString();
  }

  /** U1: batches of 10 txns until cumulative bytes >= 10 x C, for C in 4096, 65536, 1048576. */
  @Test
  public void testCumulativeCap() throws Exception {
    env();
    int[] caps = {4096, 65536, 1048576};
    for (int cap : caps) {
      JournaledEditsCache c = cacheWithBytes(cap);
      long stored = 0;
      long calls = 0;
      int start = 1;
      int maxTotal = Integer.MIN_VALUE;
      int minB = Integer.MAX_VALUE;
      int maxB = 0;
      boolean sumMismatch = false;
      while (stored < 10L * cap) {
        byte[] b = createTxnData(start, 10);
        c.storeEdits(b, start, start + 9, LV);
        start += 10;
        calls++;
        stored += b.length;
        minB = Math.min(minB, b.length);
        maxB = Math.max(maxB, b.length);
        int ts = totalSize(c);
        maxTotal = Math.max(maxTotal, ts);
        if (sumLen(c) != ts) {
          sumMismatch = true;
        }
        if (calls % 100 == 0) {
          p("U1 SAMPLE C=" + cap + " calls=" + calls + " " + state(c) + " maxTotalSize=" + maxTotal);
        }
      }
      int lowest = dataMap(c).firstKey().intValue();
      String retrLowest;
      try {
        List<ByteBuffer> out = new ArrayList<>();
        int n = c.retrieveEdits(lowest, 5, out);
        retrLowest = "ok txns=" + n;
      } catch (Exception e) {
        retrLowest = "EXC " + e.getClass().getSimpleName() + ": " + e.getMessage();
      }
      String retrOne;
      try {
        List<ByteBuffer> out = new ArrayList<>();
        int n = c.retrieveEdits(1, 5, out);
        retrOne = "ok txns=" + n;
      } catch (Exception e) {
        retrOne = "EXC " + e.getClass().getSimpleName() + ": " + e.getMessage();
      }
      p("U1 FINAL C=" + cap + " calls=" + calls + " storedBytes=" + stored + " " + state(c)
          + " maxTotalSize=" + maxTotal + " bMin=" + minB + " bMax=" + maxB
          + " floorC_over_bMax=" + (cap / maxB) + " floorC_over_bMin=" + (cap / minB)
          + " sumMismatchEver=" + sumMismatch + " lowestTxn=" + lowest);
      p("U1 RETRIEVE C=" + cap + " retrieve(lowest=" + lowest + ")=" + retrLowest + " retrieve(1)=" + retrOne);
      if (cap == 1048576 && Boolean.getBoolean("capu.histo")) {
        histogram("U1-C1MiB-held entries=" + dataMap(c).size());
        p("U1 AFTER-HISTO entries=" + dataMap(c).size());
        c = null;
        System.gc();
        histogram("U1-C1MiB-released");
      }
    }
  }

  /** U2: the :283 boundary with capacity = L and L - 1, L = createTxnData(1, 200).length. */
  @Test
  public void testSingleBatchBoundary() throws Exception {
    env();
    byte[] big = createTxnData(1, 200);
    int L = big.length;
    byte[] next = createTxnData(201, 10);
    p("U2 L=" + L + " size(201-210)=" + next.length);

    LogCapturer logs = LogCapturer.captureLogs(Journal.LOG);
    JournaledEditsCache a = cacheWithBytes(L);
    a.storeEdits(big, 1, 200, LV);
    p("U2 CAP=L after store(1-200): " + state(a));
    a.storeEdits(next, 201, 210, LV);
    p("U2 CAP=L after store(201-210): " + state(a) + " firstKey=" + dataMap(a).firstKey());
    boolean warnA = logs.getOutput().contains("A single batch of edits was too large");
    p("U2 CAP=L warnTooLarge=" + warnA);
    logs.stopCapturing();

    LogCapturer logs2 = LogCapturer.captureLogs(Journal.LOG);
    JournaledEditsCache b = cacheWithBytes(L - 1);
    b.storeEdits(big, 1, 200, LV);
    p("U2 CAP=L-1 after store(1-200): " + state(b));
    boolean warnB = logs2.getOutput().contains("A single batch of edits was too large");
    String retr;
    try {
      List<ByteBuffer> out = new ArrayList<>();
      int n = b.retrieveEdits(1, 1, out);
      retr = "ok txns=" + n;
    } catch (Exception e) {
      retr = "EXC " + e.getClass().getSimpleName() + ": " + e.getMessage();
    }
    p("U2 CAP=L-1 warnTooLarge=" + warnB + " retrieve(1,1)=" + retr);
    logs2.stopCapturing();
  }

  /** U3: bytes key unset; fraction 0.1 and 0.5. 2000 batches of about 1 KB. */
  @Test
  public void testDerivedDefault() throws Exception {
    env();
    float[] fs = {0.1f, 0.5f};
    for (float f : fs) {
      Configuration conf = new Configuration();
      conf.setFloat(DFSConfigKeys.DFS_JOURNALNODE_EDIT_CACHE_SIZE_FRACTION_KEY, f);
      JournaledEditsCache c = new JournaledEditsCache(conf);
      int expected = (int) (Runtime.getRuntime().maxMemory() * f);
      int maxTotal = 0;
      int start = 1;
      for (int i = 0; i < 2000; i++) {
        byte[] b = createTxnData(start, 22);
        c.storeEdits(b, start, start + 21, LV);
        start += 22;
        maxTotal = Math.max(maxTotal, totalSize(c));
      }
      p("U3 f=" + f + " maxMemory=" + Runtime.getRuntime().maxMemory() + " getCapacity=" + c.getCapacity()
          + " expected=" + expected + " equal=" + (c.getCapacity() == expected) + " " + state(c)
          + " maxTotalSize=" + maxTotal + " le=" + (maxTotal <= c.getCapacity()));
    }
  }

  private static void runU4(String tag, int capBytes, int calls) throws Exception {
    JournaledEditsCache c = cacheWithBytes(capBytes);
    long txn = 1;
    int maxEntries = 0;
    boolean wentNegative = false;
    int firstNegativeCall = -1;
    for (int i = 1; i <= calls; i++) {
      byte[] b = new byte[1 << 20];
      c.storeEdits(b, txn, txn + 999, LV);
      txn += 1000;
      int ts = totalSize(c);
      int n = dataMap(c).size();
      maxEntries = Math.max(maxEntries, n);
      if (ts < 0 && !wentNegative) {
        wentNegative = true;
        firstNegativeCall = i;
      }
      if (i % 100 == 0 || (i >= 1022 && i <= 1026) || (i >= 2045 && i <= 2050) || i == calls) {
        p("U4 " + tag + " call=" + i + " totalSize=" + ts + " entries=" + n + " capacity=" + c.getCapacity());
      }
    }
    p("U4 " + tag + " FINAL " + state(c) + " maxEntries=" + maxEntries + " wentNegative=" + wentNegative
        + " firstNegativeCall=" + firstNegativeCall);
    histogram("U4-" + tag + "-held");
    p("U4 " + tag + " AFTER-HISTO entries=" + dataMap(c).size() + " totalSize=" + totalSize(c));
  }

  /** U4: overflow probe. Control 1 GiB first, then Integer.MAX_VALUE; 2600 x 1 MiB batches each. */
  @Test
  public void testIntOverflowAtMaxCapacity() throws Exception {
    env();
    runU4("control1GiB", 1073741824, 2600);
    System.gc();
    histogram("U4-after-control-released");
    runU4("max", Integer.MAX_VALUE, 2600);
  }
}
