/*
 * Stage-4 harness, cluster tier B3 (A5, A6) of
 * dfs.client.write.byte-array-manager.count-limit-recycle-maxAllocated--autonomous.
 *
 * Usage: hadoop org.apache.hadoop.hdfs.util.BamProbe <tag> <enabled> <countLimit> <countThreshold>
 *                                                     <threads> <bytesPerFile> <dir> <windowSec>
 * One FileSystem (one DFSClient, one ClientContext). T writers start behind a CyclicBarrier, each
 * writes S bytes to <dir>/f<i> in 64 KiB write() calls and closes. After all join: sleep 2 s,
 * System.gc() x3 (200 ms apart), print heap and the 1 MiB manager string (POSTGC line), then sleep
 * windowSec seconds for external jcmd sampling, then exit.
 */
package org.apache.hadoop.hdfs.util;

import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.Random;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.atomic.AtomicInteger;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.FSDataOutputStream;
import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.hdfs.DistributedFileSystem;

public class BamProbe {
  static void out(String s) {
    System.out.println("[" + System.currentTimeMillis() + "] " + s);
    System.out.flush();
  }

  static String mgrString(ByteArrayManager bam, int len) {
    if (!(bam instanceof ByteArrayManager.Impl)) {
      return "no manager (" + bam.getClass().getSimpleName() + ")";
    }
    ByteArrayManager.FixedLengthManager m = ((ByteArrayManager.Impl) bam).getManagers().get(len, false);
    return m == null ? "no manager for " + len : m.toString();
  }

  public static void main(String[] a) throws Exception {
    final String tag = a[0];
    final boolean enabled = Boolean.parseBoolean(a[1]);
    final int limit = Integer.parseInt(a[2]);
    final int threshold = Integer.parseInt(a[3]);
    final int T = Integer.parseInt(a[4]);
    final long S = Long.parseLong(a[5]);
    final String dir = a[6];
    final int windowSec = Integer.parseInt(a[7]);

    StringBuilder gcs = new StringBuilder();
    for (GarbageCollectorMXBean g : ManagementFactory.getGarbageCollectorMXBeans()) {
      gcs.append(g.getName()).append('|');
    }
    out("ENV tag=" + tag + " pid=" + ManagementFactory.getRuntimeMXBean().getName()
        + " maxHeap=" + Runtime.getRuntime().maxMemory() + " gc=" + gcs
        + " java=" + System.getProperty("java.version")
        + " args=" + ManagementFactory.getRuntimeMXBean().getInputArguments());

    Configuration conf = new Configuration();
    conf.setBoolean("dfs.client.write.byte-array-manager.enabled", enabled);
    conf.setInt("dfs.client.write.byte-array-manager.count-limit", limit);
    conf.setInt("dfs.client.write.byte-array-manager.count-threshold", threshold);
    conf.setInt("dfs.client-write-packet-size", 1048576);
    conf.setInt("dfs.client.write.max-packets-in-flight", 4);
    out("CONF enabled=" + conf.get("dfs.client.write.byte-array-manager.enabled")
        + " count-limit=" + conf.get("dfs.client.write.byte-array-manager.count-limit")
        + " count-threshold=" + conf.get("dfs.client.write.byte-array-manager.count-threshold")
        + " packet-size=" + conf.get("dfs.client-write-packet-size")
        + " max-packets-in-flight=" + conf.get("dfs.client.write.max-packets-in-flight")
        + " blocksize=" + conf.get("dfs.blocksize")
        + " fs=" + conf.get("fs.defaultFS")
        + " context=" + conf.get("dfs.client.context", "default"));

    final FileSystem fs = FileSystem.get(conf);
    final DistributedFileSystem dfs = (DistributedFileSystem) fs;
    final ByteArrayManager bam = dfs.getClient().getClientContext().getByteArrayManager();
    out("MANAGER-CLASS " + bam.getClass().getName());

    final CyclicBarrier barrier = new CyclicBarrier(T);
    final AtomicInteger failures = new AtomicInteger();
    Thread[] ts = new Thread[T];
    final long start = System.nanoTime();
    for (int i = 0; i < T; i++) {
      final int id = i;
      ts[i] = new Thread(() -> {
        try {
          byte[] buf = new byte[65536];
          new Random(id).nextBytes(buf);
          barrier.await();
          try (FSDataOutputStream o = fs.create(new Path(dir + "/f" + id), true)) {
            long left = S;
            while (left > 0) {
              int n = (int) Math.min(buf.length, left);
              o.write(buf, 0, n);
              left -= n;
            }
          }
        } catch (Throwable e) {
          failures.incrementAndGet();
          out("WRITER-FAIL " + id + " " + e);
          e.printStackTrace(System.out);
        }
      }, "writer-" + i);
      ts[i].start();
    }
    for (Thread t : ts) {
      t.join();
    }
    long ms = (System.nanoTime() - start) / 1000000;
    out("WRITERS-DONE ms=" + ms + " failures=" + failures.get() + " mid-manager=" + mgrString(bam, 1048576));
    ts = null;
    Thread.sleep(2000);
    for (int i = 0; i < 3; i++) {
      System.gc();
      Thread.sleep(200);
    }
    long used = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    out("POSTGC tag=" + tag + " heapUsed=" + used + " manager1M=" + mgrString(bam, 1048576)
        + " manager64=" + mgrString(bam, 64) + " failures=" + failures.get() + " writeMs=" + ms);
    Thread.sleep(windowSec * 1000L);
    out("EXIT tag=" + tag + " manager1M=" + mgrString(bam, 1048576));
    System.exit(failures.get() == 0 ? 0 : 3);
  }
}
