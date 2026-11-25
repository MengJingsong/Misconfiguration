/*
 * Stage-4 harness (capacity-enforcement-exp, Hadoop, order 9, PriorityQueue_maxSize-insert-maxSize--autonomous).
 * Copied into hadoop-common/src/test/java/org/apache/hadoop/util/ of the run's private source copy only.
 * Case file B2c Part 1 with amendments A2 and A4: allocation of initialize(k) versus allocation of N inserts.
 * Prints lines prefixed PQCAP; asserts nothing about the readings (they are judged against B2f/B2g).
 */
package org.apache.hadoop.util;

import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.Random;

import org.junit.Assume;
import org.junit.Test;

public class TestPriorityQueueInsertCap {

  static final class LongQ extends PriorityQueue<Long> {
    LongQ(int n) { initialize(n); }
    @Override protected boolean lessThan(Object a, Object b) { return (Long) a < (Long) b; }
  }

  static final int[] KS = {1, 16, 1024, 65536};
  static final int N = 200000;
  static final long SEED = 20261124L;

  static final com.sun.management.ThreadMXBean TMX =
      (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
  static final long TID = Thread.currentThread().getId();

  static long alloc() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }

  static Object sink;

  static long baseline() {
    long[] w = new long[21];
    for (int i = 0; i < w.length; i++) {
      long a = alloc();
      long b = alloc();
      w[i] = b - a;
    }
    Arrays.sort(w);
    return w[10];
  }

  static Object field(Object o, String name) throws Exception {
    Field f = PriorityQueue.class.getDeclaredField(name);
    f.setAccessible(true);
    return f.get(o);
  }

  static Long[] items() {
    Long[] it = new Long[N];
    for (int i = 0; i < N; i++) it[i] = Long.valueOf(i);  // distinct objects for i >= 128 (outside the Long cache)
    Random r = new Random(SEED);
    for (int i = N - 1; i > 0; i--) { int j = r.nextInt(i + 1); Long t = it[i]; it[i] = it[j]; it[j] = t; }
    return it;
  }

  static void env() {
    StringBuilder sb = new StringBuilder("PQCAP env");
    sb.append(" java=").append(System.getProperty("java.version"));
    sb.append(" vm=").append(System.getProperty("java.vm.name"));
    sb.append(" maxHeapMiB=").append(Runtime.getRuntime().maxMemory() >> 20);
    try {
      com.sun.management.HotSpotDiagnosticMXBean hs =
          ManagementFactory.getPlatformMXBean(com.sun.management.HotSpotDiagnosticMXBean.class);
      sb.append(" UseTLAB=").append(hs.getVMOption("UseTLAB").getValue());
      sb.append(" UseCompressedOops=").append(hs.getVMOption("UseCompressedOops").getValue());
    } catch (Exception e) { sb.append(" vmopt-error=").append(e); }
    sb.append(" allocSupported=").append(TMX.isThreadAllocatedMemorySupported())
      .append(" allocEnabled=").append(TMX.isThreadAllocatedMemoryEnabled());
    System.out.println(sb);
  }

  @Test
  public void testInsertCap() throws Exception {
    Assume.assumeFalse(Boolean.getBoolean("pqcap.jdbcheck"));
    env();
    Long[] items = items();
    // Instrument known answer (A2 iv): new Object[1024] = 16 + 4*1024 = 4112 B.
    long kb = baseline();
    long a0 = alloc();
    sink = new Object[1024];
    long a1 = alloc();
    System.out.println("PQCAP instr object1024=" + (a1 - a0 - kb) + " baseline=" + kb + " expect=4112..4176");
    // Warm-up (A2 ii): three passes of new LongQ(1024) + 200000 inserts.
    for (int w = 0; w < 3; w++) {
      LongQ q = new LongQ(1024);
      for (Long x : items) q.insert(x);
      sink = q;
    }
    System.out.println("PQCAP header rep k N size heapLenBefore heapLenAfter maxSize allocCtor allocInsertLoop trues falses baseline");
    for (int rep = 1; rep <= 3; rep++) {
      for (int k : KS) {
        int[] ns = k >= 16 ? new int[] {N, k / 2} : new int[] {N};
        for (int n : ns) {
          long base = baseline();
          long c0 = alloc();
          LongQ q = new LongQ(k);
          long c1 = alloc();
          int hb = ((Object[]) field(q, "heap")).length;
          int trues = 0, falses = 0;
          long i0 = alloc();
          for (int i = 0; i < n; i++) {
            if (q.insert(items[i])) trues++; else falses++;
          }
          long i1 = alloc();
          int ha = ((Object[]) field(q, "heap")).length;
          int ms = (Integer) field(q, "maxSize");
          System.out.println("PQCAP row " + rep + " " + k + " " + n + " " + q.size() + " " + hb + " " + ha + " "
              + ms + " " + (c1 - c0 - base) + " " + (i1 - i0 - base) + " " + trues + " " + falses + " " + base);
          sink = q;
        }
      }
    }
  }

  @Test
  public void testPutControl() throws Exception {
    Assume.assumeFalse(Boolean.getBoolean("pqcap.jdbcheck"));
    for (int k : KS) {
      LongQ q = new LongQ(k);
      int thrownAt = -1;
      for (int i = 1; i <= k + 1; i++) {
        try {
          q.put(Long.valueOf(i));
        } catch (ArrayIndexOutOfBoundsException e) {
          thrownAt = i;
          break;
        }
      }
      System.out.println("PQCAP put k=" + k + " thrownAtPut=" + thrownAt + " expect=" + (k + 1));
    }
  }

  /** jdb known answer (A2 vi): exactly 1 initialize and 5 insert calls. Runs only with -Dpqcap.jdbcheck=true. */
  @Test
  public void testJdbKnownAnswer() {
    Assume.assumeTrue(Boolean.getBoolean("pqcap.jdbcheck"));
    LongQ q = new LongQ(3);
    int t = 0;
    for (long v = 10; v < 15; v++) if (q.insert(v)) t++;
    System.out.println("PQCAP jdbcheck initialize=1 insert=5 trues=" + t + " size=" + q.size());
  }
}
