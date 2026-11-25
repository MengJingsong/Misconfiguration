/*
 * Stage-4 harness, case dfs.client.write.byte-array-manager.count-limit-recycle-maxAllocated--autonomous
 * (capacity-enforcement-exp, Hadoop, Jingsong). Unit tier B2 with amendments A1, A2, A3, A8, A9.
 *
 * Placed in the per-case source copy at
 *   hadoop-hdfs-project/hadoop-hdfs-client/src/test/java/org/apache/hadoop/hdfs/util/
 * and run with
 *   mvn -B test -pl hadoop-hdfs-project/hadoop-hdfs-client -Dtest=TestByteArrayManagerCountLimitPool \
 *     -Dmaven-surefire-plugin.argLine="-Xmx1g -XX:+UseSerialGC -Dbam.mode=<managed|disabled|mutation>"
 *
 * Every reading is printed as one CSV line (prefix ENV/KNOWN/CASE1/TRACE1/CASE2/CASE3/WIRE).
 * Heap readings (known answer, case 1) are taken in one child JVM per reading (A9), with heap used =
 * sum of the non-eden heap pools after System.gc() x3 with 200 ms sleeps (A8); the MemoryMXBean total
 * is printed alongside for comparison. A10: one unrecorded settling reading after the warm-up, before
 * the first recorded reading.
 */
package org.apache.hadoop.hdfs.util;

import static org.junit.Assert.assertTrue;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryType;
import java.util.ArrayList;
import java.util.List;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.hdfs.ClientContext;
import org.apache.hadoop.hdfs.client.impl.DfsClientConf;
import org.junit.Test;

public class TestByteArrayManagerCountLimitPool {
  static final int REQ = 65049;          // default packet buffer request (rounds to 65536)
  static final int LEN = 65536;
  static final int[] LS = {1, 4, 16, 64, 1024};
  static final int REPS = 3;

  /** Keeps the manager (and so its pool) reachable across the second heap reading. */
  static volatile Object KEEP;

  static String mode() {
    return System.getProperty("bam.mode", "managed");
  }

  // ---------------------------------------------------------------- helpers

  static String envLine(String who) {
    StringBuilder gcs = new StringBuilder();
    for (GarbageCollectorMXBean g : ManagementFactory.getGarbageCollectorMXBeans()) {
      gcs.append(g.getName()).append('|');
    }
    return "ENV," + who + "," + mode() + "," + System.getProperty("java.version") + ","
        + Runtime.getRuntime().maxMemory() + "," + gcs + ","
        + ManagementFactory.getRuntimeMXBean().getInputArguments().toString().replace(',', ';');
  }

  /** Returns {nonEdenUsed, memoryMXBeanUsed} after System.gc() x3 with 200 ms sleeps. */
  static long[] heap() throws InterruptedException {
    for (int i = 0; i < 3; i++) {
      System.gc();
      Thread.sleep(200);
    }
    long nonEden = 0;
    for (MemoryPoolMXBean p : ManagementFactory.getMemoryPoolMXBeans()) {
      if (p.getType() == MemoryType.HEAP && !p.getName().contains("Eden")) {
        nonEden += p.getUsage().getUsed();
      }
    }
    long mx = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    return new long[] {nonEden, mx};
  }

  static ByteArrayManager newBam(String mode, int limit, int threshold, long resetMs) {
    if ("disabled".equals(mode)) {
      return ByteArrayManager.newInstance(null);
    }
    return ByteArrayManager.newInstance(new ByteArrayManager.Conf(threshold, limit, resetMs));
  }

  static String mgr(ByteArrayManager bam, int len) {
    if (!(bam instanceof ByteArrayManager.Impl)) {
      return "no-manager(" + bam.getClass().getSimpleName() + ")";
    }
    ByteArrayManager.FixedLengthManager m =
        ((ByteArrayManager.Impl) bam).getManagers().get(len, false);
    return m == null ? "no-manager-for-" + len : m.toString();
  }

  /**
   * Case-1 workload: allocate L, release L, then release L+10 extra new byte[65536] arrays allocated
   * one by one just before their release. Returns {poolAfterManaged, maxPoolDuringExtra, finalPool}.
   * trace receives every release return value.
   */
  static int[] case1Workload(ByteArrayManager bam, int L, StringBuilder trace)
      throws InterruptedException {
    byte[][] held = new byte[L][];
    for (int i = 0; i < L; i++) {
      held[i] = bam.newByteArray(REQ);
    }
    int poolAfterManaged = -2;
    for (int i = 0; i < L; i++) {
      poolAfterManaged = bam.release(held[i]);
      held[i] = null;
      if (trace != null) {
        trace.append(poolAfterManaged).append(' ');
      }
    }
    if (trace != null) {
      trace.append("| ");
    }
    int maxExtra = Integer.MIN_VALUE;
    int last = -2;
    for (int i = 0; i < L + 10; i++) {
      byte[] extra = new byte[LEN];
      last = bam.release(extra);
      extra = null;
      maxExtra = Math.max(maxExtra, last);
      if (trace != null) {
        trace.append(last).append(' ');
      }
    }
    return new int[] {poolAfterManaged, maxExtra, last};
  }

  // ------------------------------------------------------- child JVM (A9)

  /** Child entry point: args = kind (known|case1), mode, L, rep. Prints one result line. */
  public static void main(String[] args) throws Exception {
    String kind = args[0];
    String mode = args[1];
    System.setProperty("bam.mode", mode);
    System.out.println(envLine("child-" + kind + "-" + args[2] + "-" + args[3]));
    // Unrecorded warm-up pass (L = 4), with its own manager, discarded.
    {
      ByteArrayManager w = newBam(mode, 4, 0, 10000);
      case1Workload(w, 4, null);
      w = null;
    }
    // A10 (defect D1 of this run): one unrecorded settling reading after the warm-up. The first
    // post-warm-up reading carried ~0.6 MB that the next GC round frees (diagnostic diag1.txt).
    long[] settle = heap();
    System.out.println("SETTLE," + mode + "," + settle[0] + "," + settle[1]);
    if ("known".equals(kind)) {
      long[] a = heap();
      KEEP = new byte[LEN];
      long[] b = heap();
      System.out.println("KNOWN," + mode + "," + a[0] + "," + b[0] + "," + (b[0] - a[0]) + ","
          + a[1] + "," + b[1] + "," + (b[1] - a[1]));
      return;
    }
    int L = Integer.parseInt(args[2]);
    int rep = Integer.parseInt(args[3]);
    ByteArrayManager bam = newBam(mode, L, 0, 10000);
    KEEP = bam;
    long[] a = heap();
    StringBuilder trace = new StringBuilder();
    int[] r = case1Workload(bam, L, trace);
    bam = null; // only KEEP holds the manager now
    long[] b = heap();
    System.out.println("CASE1," + mode + "," + L + "," + rep + "," + r[0] + "," + r[1] + "," + r[2]
        + "," + a[0] + "," + b[0] + "," + (b[0] - a[0]) + "," + (b[1] - a[1]) + ","
        + mgr((ByteArrayManager) KEEP, LEN).replace(',', ';'));
    System.out.println("TRACE1," + mode + "," + L + "," + rep + "," + trace.toString().trim());
  }

  static void runChild(String kind, String mode, int L, int rep) throws Exception {
    String java = System.getProperty("java.home") + File.separator + "bin" + File.separator + "java";
    String cp = System.getProperty("surefire.test.class.path");
    if (cp == null || cp.isEmpty()) {
      cp = System.getProperty("java.class.path");
    }
    List<String> cmd = new ArrayList<>();
    cmd.add(java);
    cmd.add("-Xmx1g");
    cmd.add("-XX:+UseSerialGC");
    cmd.add("-Dbam.mode=" + mode);
    cmd.add("-cp");
    cmd.add(cp);
    cmd.add(TestByteArrayManagerCountLimitPool.class.getName());
    cmd.add(kind);
    cmd.add(mode);
    cmd.add(String.valueOf(L));
    cmd.add(String.valueOf(rep));
    ProcessBuilder pb = new ProcessBuilder(cmd);
    pb.redirectErrorStream(true);
    Process p = pb.start();
    boolean sawResult = false;
    try (BufferedReader rd = new BufferedReader(new InputStreamReader(p.getInputStream(), "UTF-8"))) {
      String line;
      while ((line = rd.readLine()) != null) {
        System.out.println(line);
        if (line.startsWith("KNOWN,") || line.startsWith("CASE1,")) {
          sawResult = true;
        }
      }
    }
    int rc = p.waitFor();
    System.out.println("CHILD-EXIT," + kind + "," + mode + "," + L + "," + rep + "," + rc);
    assertTrue("child " + kind + " L=" + L + " rep=" + rep + " exit " + rc, rc == 0 && sawResult);
  }

  // ------------------------------------------------------------------ tests

  @Test(timeout = 600000)
  public void testCase1PoolCapPerChildJvm() throws Exception {
    String mode = mode();
    System.out.println(envLine("surefire"));
    System.out.println("CHILD-CP-SOURCE," + (System.getProperty("surefire.test.class.path") != null
        ? "surefire.test.class.path" : "java.class.path"));
    runChild("known", mode, 0, 0);
    for (int rep = 1; rep <= REPS; rep++) {
      for (int L : LS) {
        runChild("case1", mode, L, rep);
      }
    }
  }

  @Test(timeout = 120000)
  public void testCase2InUseCap() throws Exception {
    if (!"managed".equals(mode())) {
      System.out.println("CASE2,skipped-in-mode-" + mode());
      return;
    }
    for (int L : LS) {
      final ByteArrayManager bam = newBam("managed", L, 0, 10000);
      case1Workload(bam, L, null);
      String before = mgr(bam, LEN);
      byte[][] held = new byte[L][];
      for (int i = 0; i < L; i++) {
        held[i] = bam.newByteArray(REQ);
      }
      String afterAlloc = mgr(bam, LEN);
      final byte[][] got = new byte[1][];
      Thread t = new Thread(() -> {
        try {
          got[0] = bam.newByteArray(REQ);
        } catch (InterruptedException e) {
          Thread.currentThread().interrupt();
        }
      }, "extra-allocator-L" + L);
      t.start();
      Thread.sleep(500);
      Thread.State s500 = t.getState();
      long t0 = System.nanoTime();
      bam.release(held[0]);
      held[0] = null;
      t.join(1000);
      long ms = (System.nanoTime() - t0) / 1000000;
      Thread.State sAfter = t.getState();
      System.out.println("CASE2," + L + "," + before.replace(',', ';') + "," + afterAlloc.replace(',', ';')
          + "," + s500 + "," + sAfter + "," + ms + "," + (got[0] != null ? got[0].length : -1) + ","
          + mgr(bam, LEN).replace(',', ';'));
      if (t.isAlive()) {
        t.interrupt();
        t.join(1000);
      }
    }
  }

  @Test(timeout = 120000)
  public void testCase3UnmanagedReleases() throws Exception {
    if (!"managed".equals(mode())) {
      System.out.println("CASE3,skipped-in-mode-" + mode());
      return;
    }
    ByteArrayManager bam = newBam("managed", 4, 16, 60000);
    byte[][] a = new byte[20][];
    for (int i = 0; i < 20; i++) {
      a[i] = bam.newByteArray(REQ);
      System.out.println("CASE3,alloc," + (i + 1) + "," + a[i].length + "," + mgr(bam, LEN).replace(',', ';'));
    }
    // release the 16 unmanaged first, then the 4 managed
    for (int i = 0; i < 20; i++) {
      int r = bam.release(a[i]);
      System.out.println("CASE3,release," + (i + 1) + "," + (i < 16 ? "unmanaged" : "managed") + "," + r
          + "," + mgr(bam, LEN).replace(',', ';'));
      a[i] = null;
    }
    System.out.println("CASE3,final," + mgr(bam, LEN).replace(',', ';'));
  }

  @Test(timeout = 120000)
  public void testWiring() throws Exception {
    if (!"managed".equals(mode())) {
      System.out.println("WIRE,skipped-in-mode-" + mode());
      return;
    }
    Configuration on = new Configuration(false);
    on.setBoolean("dfs.client.write.byte-array-manager.enabled", true);
    on.setInt("dfs.client.write.byte-array-manager.count-limit", 16);
    on.setInt("dfs.client.write.byte-array-manager.count-threshold", 0);
    ByteArrayManager bOn =
        ClientContext.get("bam-wire-on", new DfsClientConf(on), on).getByteArrayManager();
    byte[] x = bOn.newByteArray(REQ);
    System.out.println("WIRE,on," + bOn.getClass().getName() + "," + x.length + ","
        + mgr(bOn, LEN).replace(',', ';'));
    Configuration off = new Configuration(false);
    ByteArrayManager bOff =
        ClientContext.get("bam-wire-off", new DfsClientConf(off), off).getByteArrayManager();
    System.out.println("WIRE,off," + bOff.getClass().getName());
  }
}
