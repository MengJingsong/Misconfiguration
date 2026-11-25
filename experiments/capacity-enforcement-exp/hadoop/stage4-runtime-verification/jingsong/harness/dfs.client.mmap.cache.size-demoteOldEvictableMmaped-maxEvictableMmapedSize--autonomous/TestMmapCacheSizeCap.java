/*
 * Stage-4 unit tier (B2 + A1-A5) for
 * dfs.client.mmap.cache.size-demoteOldEvictableMmaped-maxEvictableMmapedSize--autonomous.
 * Not upstream code: copied into the local source copy only.
 */
package org.apache.hadoop.fs;

import java.io.File;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.EnumSet;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.apache.commons.collections4.map.LinkedMap;
import org.apache.hadoop.hdfs.ClientContext;
import org.apache.hadoop.hdfs.DFSConfigKeys;
import org.apache.hadoop.hdfs.DFSTestUtil;
import org.apache.hadoop.hdfs.ExtendedBlockId;
import org.apache.hadoop.hdfs.HdfsConfiguration;
import org.apache.hadoop.hdfs.MiniDFSCluster;
import org.apache.hadoop.hdfs.client.HdfsClientConfigKeys;
import org.apache.hadoop.hdfs.shortcircuit.ShortCircuitCache;
import org.apache.hadoop.hdfs.shortcircuit.ShortCircuitCache.CacheVisitor;
import org.apache.hadoop.hdfs.shortcircuit.ShortCircuitReplica;
import org.apache.hadoop.io.ElasticByteBufferPool;
import org.apache.hadoop.io.nativeio.NativeIO;
import org.apache.hadoop.net.unix.DomainSocket;
import org.apache.hadoop.net.unix.TemporarySocketDirectory;
import org.apache.hadoop.security.token.SecretManager.InvalidToken;
import org.apache.hadoop.test.GenericTestUtils;
import org.apache.log4j.AppenderSkeleton;
import org.apache.log4j.Level;
import org.apache.log4j.spi.LoggingEvent;
import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

public class TestMmapCacheSizeCap {
  static final int N = 12;
  static final int BLK = 1 << 20;
  static TemporarySocketDirectory sockDir;

  /** Counts the TRACE messages of the three trimming branches (A3). */
  static class Counter extends AppenderSkeleton {
    final AtomicInteger need = new AtomicInteger(), old = new AtomicInteger(), purge = new AtomicInteger();
    volatile boolean on = false;
    @Override protected void append(LoggingEvent e) {
      if (!on) return;
      String m = e.getRenderedMessage();
      if (m == null) return;
      if (m.startsWith("demoteOldEvictable: demoting")) {
        if (m.contains("because we need more space")) need.incrementAndGet();
        else if (m.contains("because it's too old")) old.incrementAndGet();
      } else if (m.contains("trimEvictionMaps is purging")) {
        purge.incrementAndGet();
      }
    }
    void reset() { need.set(0); old.set(0); purge.set(0); }
    String fmt() { return "demoteNeed=" + need.get() + " demoteOld=" + old.get() + " purge=" + purge.get(); }
    @Override public void close() { }
    @Override public boolean requiresLayout() { return false; }
  }
  static final Counter COUNTER = new Counter();

  @BeforeClass
  public static void init() {
    // A loud failure instead of the Assume-skip of TestEnhancedByteBufferAccess (B2e step 3).
    Assert.assertTrue("native libhadoop not loaded: NativeIO.isAvailable()=false", NativeIO.isAvailable());
    Assert.assertNull("DomainSocket not loadable: " + DomainSocket.getLoadingFailureReason(),
        DomainSocket.getLoadingFailureReason());
    sockDir = new TemporarySocketDirectory();
    DomainSocket.disableBindPathValidation();
    org.apache.log4j.Logger l = org.apache.log4j.Logger.getLogger(ShortCircuitCache.class);
    l.setLevel(Level.TRACE);
    l.addAppender(COUNTER);
    System.out.println("IFCHK,env native=" + NativeIO.isAvailable() + " java=" + System.getProperty("java.version")
        + " sockDir=" + sockDir.getDir());
  }

  @AfterClass
  public static void teardown() throws Exception {
    if (sockDir != null) sockDir.close();
  }

  /** blk_ data-file mappings under base (A2b) and in the whole JVM. */
  static String maps(String base) throws Exception {
    long n = 0, bytes = 0, nj = 0;
    for (String l : Files.readAllLines(Paths.get("/proc/self/maps"))) {
      if (l.contains("/blk_") && !l.endsWith(".meta") && !l.contains(".meta ")) {
        nj++;
        if (l.contains(base)) {
          String[] r = l.split(" ")[0].split("-");
          n++;
          bytes += Long.parseLong(r[1], 16) - Long.parseLong(r[0], 16);
        }
      }
    }
    return "blkMaps=" + n + " blkMappedBytes=" + bytes + " blkMapsJvm=" + nj;
  }

  static String cache(ShortCircuitCache c) {
    final StringBuilder sb = new StringBuilder();
    c.accept(new CacheVisitor() {
      @Override
      public void visit(int numOutstandingMmaps, Map<ExtendedBlockId, ShortCircuitReplica> replicas,
          Map<ExtendedBlockId, InvalidToken> failedLoads, LinkedMap evictable, LinkedMap evictableMmapped) {
        sb.append("evictableMmapped=").append(evictableMmapped.size())
          .append(" outstanding=").append(numOutstandingMmaps)
          .append(" evictable=").append(evictable.size())
          .append(" replicas=").append(replicas.size())
          .append(" failedLoads=").append(failedLoads.size());
      }
    });
    return sb.toString();
  }

  /**
   * One phase: fresh MiniDFSCluster + fresh context; write N x 1 MiB, zero-copy read each block,
   * release, snapshot; close; snapshot; 2 s later snapshot.
   */
  void phase(int rep, String tag, int s, int streamsCache, long timeoutMs, boolean baseline, long postCloseWaitMs)
      throws Exception {
    String name = "mmapcap-r" + rep + "-" + tag;
    HdfsConfiguration conf = new HdfsConfiguration();
    conf.setBoolean(HdfsClientConfigKeys.Read.ShortCircuit.KEY, true);
    conf.setBoolean(HdfsClientConfigKeys.Read.ShortCircuit.SKIP_CHECKSUM_KEY, true);
    conf.setBoolean(HdfsClientConfigKeys.Mmap.ENABLED_KEY, !baseline);
    conf.setInt(HdfsClientConfigKeys.Mmap.CACHE_SIZE_KEY, s);
    conf.setLong(HdfsClientConfigKeys.Mmap.CACHE_TIMEOUT_MS_KEY, timeoutMs);
    conf.setInt(HdfsClientConfigKeys.Read.ShortCircuit.STREAMS_CACHE_SIZE_KEY, streamsCache);
    conf.setInt(HdfsClientConfigKeys.DFS_CLIENT_SHORT_CIRCUIT_NUM, 1);
    conf.set(DFSConfigKeys.DFS_DOMAIN_SOCKET_PATH_KEY,
        new File(sockDir.getDir(), "mmapcap._PORT.sock").getAbsolutePath());
    conf.setLong(DFSConfigKeys.DFS_BLOCK_SIZE_KEY, BLK);
    conf.set(HdfsClientConfigKeys.DFS_CLIENT_CONTEXT, name);
    File base = GenericTestUtils.getTestDir(name);
    String basePath = base.getAbsolutePath();
    String hdr = "IFCHK,rep=" + rep + ",tag=" + tag + ",S=" + s + ",streams=" + streamsCache + ",timeoutMs=" + timeoutMs
        + ",baseline=" + baseline + ",";
    MiniDFSCluster cluster = new MiniDFSCluster.Builder(conf, base).numDataNodes(1).build();
    ShortCircuitCache c = null;
    try {
      cluster.waitActive();
      FileSystem fs = FileSystem.newInstance(cluster.getURI(), conf);
      Path p = new Path("/mmapcap");
      DFSTestUtil.createFile(fs, p, (long) N * BLK, (short) 1, 0xBEEFL + rep);
      DFSTestUtil.waitReplication(fs, p, (short) 1);
      Assert.assertEquals(N, fs.getFileBlockLocations(p, 0, (long) N * BLK).length);
      c = ClientContext.get(name, conf).getShortCircuitCache(0);
      System.out.println(hdr + "conf mmapCacheSize=" + conf.get(HdfsClientConfigKeys.Mmap.CACHE_SIZE_KEY)
          + " context=" + name + " cache=" + c + " base=" + basePath);
      System.out.println(hdr + "step=before " + cache(c) + " " + maps(basePath) + " " + COUNTER.fmt());
      COUNTER.reset();
      COUNTER.on = true;
      ElasticByteBufferPool pool = baseline ? new ElasticByteBufferPool() : null;
      FSDataInputStream in = fs.open(p);
      long total = 0;
      int i = 0;
      while (true) {
        ByteBuffer b = in.read(pool, BLK, EnumSet.of(ReadOption.SKIP_CHECKSUMS));
        if (b == null) break;
        if (!baseline) Assert.assertEquals("zero-copy read length at step " + i, BLK, b.remaining());
        long sum = 0;
        int len = b.remaining();
        for (int o = b.position(); o < b.limit(); o += 4096) sum += b.get(o);
        total += len;
        in.releaseBuffer(b);
        System.out.println(hdr + "step=" + i + " len=" + len + " sum=" + sum + " " + cache(c) + " " + maps(basePath)
            + " " + COUNTER.fmt());
        i++;
        if (!baseline && i == N) break;
        if (baseline && total >= (long) N * BLK) break;
      }
      in.close();
      System.out.println(hdr + "step=after-close reads=" + i + " bytes=" + total + " " + cache(c) + " " + maps(basePath)
          + " " + COUNTER.fmt());
      Thread.sleep(postCloseWaitMs);
      System.out.println(hdr + "step=end waitMs=" + postCloseWaitMs + " " + cache(c) + " " + maps(basePath) + " "
          + COUNTER.fmt());
      COUNTER.on = false;
      fs.close();
    } finally {
      COUNTER.on = false;
      COUNTER.reset();
      if (c != null) c.close(); // A2c: after the last reading
      cluster.shutdown();
      System.out.println(hdr + "step=cleanup " + maps(basePath));
    }
  }

  @Test(timeout = 1800000)
  public void testCap() throws Exception {
    int[] sv = {0, 1, 2, 3, 5, 8, 13, 256};
    for (int rep = 1; rep <= 2; rep++) {
      for (int s : sv) {
        phase(rep, "S" + s, s, 256, 3600000L, false, 2000L);
      }
      // B2h positive control: S=256, streams cache 4
      phase(rep, "posctl", 256, 4, 3600000L, false, 2000L);
      // B2h time control: S=256, mmap timeout 500 ms, wait 3 s after close
      phase(rep, "timectl", 256, 256, 500L, false, 3000L);
      // B2h baseline: heap pool, mmap disabled
      phase(rep, "baseline", 256, 256, 3600000L, true, 2000L);
    }
  }
}
