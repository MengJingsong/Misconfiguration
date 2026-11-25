// Stage-4 cluster tier (B3 + A5) client for dfs.client.socketcache.capacity-putInternal-capacity--autonomous.
// Default package; run with: hadoop jar probe.jar PeerCacheProbe -D ... <n> <dir> <holdMs>
import java.io.File;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.List;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.conf.Configured;
import org.apache.hadoop.fs.FSDataInputStream;
import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.hdfs.ClientContext;
import org.apache.hadoop.util.Tool;
import org.apache.hadoop.util.ToolRunner;

public class PeerCacheProbe extends Configured implements Tool {
  public int run(String[] a) throws Exception {
    int n = Integer.parseInt(a[0]);
    Path dir = new Path(a[1]);
    long holdMs = Long.parseLong(a[2]);
    Configuration conf = getConf();
    FileSystem fs = FileSystem.get(conf);
    System.out.println("PROBE C=" + conf.get("dfs.client.socketcache.capacity")
        + " expiryMsec=" + conf.get("dfs.client.socketcache.expiryMsec")
        + " context=" + conf.get("dfs.client.context", "default")
        + " pid=" + ManagementFactory.getRuntimeMXBean().getName().split("@")[0]
        + " args=" + ManagementFactory.getRuntimeMXBean().getInputArguments());
    phase("START", conf);
    Thread.sleep(40_000);                       // window 0: pre-open level
    FSDataInputStream[] in = new FSDataInputStream[n];
    byte[] b = new byte[65536];
    long bytes = 0;
    for (int i = 0; i < n; i++) {
      in[i] = fs.open(new Path(dir, "f" + i));
      int r;
      while ((r = in[i].read(b)) > 0) {
        bytes += r;
      }
    }
    System.out.println("BYTES read=" + bytes);
    phase("OPEN", conf);
    Thread.sleep(holdMs);                       // window 1: N readers open (positive control)
    for (FSDataInputStream s : in) {
      s.close();
    }
    in = null;
    System.gc();
    phase("CLOSED", conf);
    Thread.sleep(holdMs);                       // window 2: only cached peers remain
    phase("END", conf);
    return 0;
  }

  static void phase(String name, Configuration conf) throws Exception {
    int size = ClientContext.getFromConf(conf).getPeerCache().size();
    for (int i = 0; i < 3; i++) {
      System.gc();
    }
    Thread.sleep(200);
    long heap = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    long direct = -1;
    for (BufferPoolMXBean p : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
      if ("direct".equals(p.getName())) {
        direct = p.getMemoryUsed();
      }
    }
    String[] fds = new File("/proc/self/fd").list();
    List<String> gcs = new ArrayList<>();
    for (GarbageCollectorMXBean g : ManagementFactory.getGarbageCollectorMXBeans()) {
      gcs.add(g.getName().replace(' ', '_'));
    }
    System.out.println("PHASE " + name + " " + System.currentTimeMillis() + " size=" + size
        + " heapAfterGc=" + heap + " direct=" + direct + " fd=" + (fds == null ? -1 : fds.length)
        + " maxHeap=" + Runtime.getRuntime().maxMemory() + " gc=" + String.join(",", gcs));
    System.out.flush();
  }

  public static void main(String[] a) throws Exception {
    System.exit(ToolRunner.run(new PeerCacheProbe(), a));
  }
}
