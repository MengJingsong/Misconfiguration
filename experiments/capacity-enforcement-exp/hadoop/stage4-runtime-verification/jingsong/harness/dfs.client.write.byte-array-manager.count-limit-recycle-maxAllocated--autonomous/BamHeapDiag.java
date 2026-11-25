/*
 * Diagnostic for the unit-tier heap instrument (defect D1 of this run): same warm-up and heap
 * routine as TestByteArrayManagerCountLimitPool's child, but takes several consecutive readings
 * with per-pool numbers, so a baseline that drifts with no allocation can be seen. Not a reading
 * of the case; used only to find and check the instrument fix.
 * Usage: java -Xmx1g -XX:+UseSerialGC -cp <test cp> org.apache.hadoop.hdfs.util.BamHeapDiag [pauseSec]
 */
package org.apache.hadoop.hdfs.util;

import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryType;

public class BamHeapDiag {
  static volatile Object KEEP;

  static String read(String label) throws InterruptedException {
    for (int i = 0; i < 3; i++) {
      System.gc();
      Thread.sleep(200);
    }
    StringBuilder sb = new StringBuilder("DIAG," + label);
    long nonEden = 0;
    for (MemoryPoolMXBean p : ManagementFactory.getMemoryPoolMXBeans()) {
      if (p.getType() == MemoryType.HEAP) {
        long u = p.getUsage().getUsed();
        sb.append(',').append(p.getName().replace(' ', '_')).append('=').append(u);
        if (!p.getName().contains("Eden")) {
          nonEden += u;
        }
      }
    }
    sb.append(",nonEden=").append(nonEden);
    return sb.toString();
  }

  public static void main(String[] a) throws Exception {
    int pause = a.length > 0 ? Integer.parseInt(a[0]) : 0;
    System.out.println(TestByteArrayManagerCountLimitPool.envLine("diag"));
    {
      ByteArrayManager w = TestByteArrayManagerCountLimitPool.newBam("managed", 4, 0, 10000);
      TestByteArrayManagerCountLimitPool.case1Workload(w, 4, null);
      w = null;
    }
    System.out.println(read("A1"));
    System.out.println(read("A2"));
    System.out.println(read("A3"));
    if (pause > 0) {
      System.out.println("PAUSE " + pause);
      Thread.sleep(pause * 1000L);
      System.out.println(read("A4-after-pause"));
    }
    KEEP = new byte[65536];
    System.out.println(read("B1-after-alloc-64KiB"));
    System.out.println(read("B2"));
  }
}
