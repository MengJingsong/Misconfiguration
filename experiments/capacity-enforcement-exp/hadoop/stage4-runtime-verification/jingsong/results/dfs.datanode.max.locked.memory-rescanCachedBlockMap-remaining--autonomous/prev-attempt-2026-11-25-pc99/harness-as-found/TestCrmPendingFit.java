/*
 * Stage-4 unit tier (B2, with audit amendments A1-A4) for
 * dfs.datanode.max.locked.memory-rescanCachedBlockMap-remaining--autonomous.
 * Not upstream. Copied into a local source copy only (never into the repository's source tree).
 *
 * Every reading is printed as one line starting with "IFCHK," (parsed by selfcheck.py).
 */
package org.apache.hadoop.hdfs.server.namenode;

import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_BLOCK_SIZE_KEY;
import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_CACHEREPORT_INTERVAL_MSEC_KEY;
import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_DATANODE_MAX_LOCKED_MEMORY_KEY;
import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_HEARTBEAT_INTERVAL_KEY;
import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_NAMENODE_PATH_BASED_CACHE_REFRESH_INTERVAL_MS;

import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.hadoop.fs.Path;
import org.apache.hadoop.fs.RemoteIterator;
import org.apache.hadoop.hdfs.DFSTestUtil;
import org.apache.hadoop.hdfs.DistributedFileSystem;
import org.apache.hadoop.hdfs.HdfsConfiguration;
import org.apache.hadoop.hdfs.MiniDFSCluster;
import org.apache.hadoop.hdfs.protocol.Block;
import org.apache.hadoop.hdfs.protocol.CacheDirectiveEntry;
import org.apache.hadoop.hdfs.protocol.CacheDirectiveInfo;
import org.apache.hadoop.hdfs.protocol.CachePoolInfo;
import org.apache.hadoop.hdfs.server.blockmanagement.BlockInfo;
import org.apache.hadoop.hdfs.server.blockmanagement.DatanodeDescriptor;
import org.apache.hadoop.hdfs.server.datanode.DataNode;
import org.apache.hadoop.hdfs.server.datanode.DataNodeTestUtils;
import org.apache.hadoop.io.nativeio.NativeIO;
import org.apache.hadoop.io.nativeio.NativeIO.POSIX.CacheManipulator;
import org.apache.hadoop.io.nativeio.NativeIO.POSIX.NoMlockCacheManipulator;
import org.apache.hadoop.test.GenericTestUtils;
import org.apache.hadoop.test.GenericTestUtils.LogCapturer;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class TestCrmPendingFit {
  private static final Logger LOG = LoggerFactory.getLogger(TestCrmPendingFit.class);
  private static final long B = 4096;
  private static final long FILE_LEN = 131072;            // 32 blocks of 4096 (B2c)
  private static final long C_B = 65536;                   // Test B capacity
  private static final Logger CRM_LOG = LoggerFactory.getLogger(
      "org.apache.hadoop.hdfs.server.blockmanagement.CacheReplicationMonitor");
  private static final Pattern DROP = Pattern.compile(
      "Block (\\d+): removing from PENDING_CACHED for node (\\S+) because it "
      + "cannot fit in remaining cache size (-?\\d+)");

  static {
    NativeIO.POSIX.setCacheManipulator(new NoMlockCacheManipulator());
  }

  private MiniDFSCluster cluster;
  private CacheManipulator prev;
  private LogCapturer cap;

  @Before
  public void setup() {
    prev = NativeIO.POSIX.getCacheManipulator();
    NativeIO.POSIX.setCacheManipulator(new NoMlockCacheManipulator());
    GenericTestUtils.setLogLevel(CRM_LOG, org.slf4j.event.Level.DEBUG);
  }

  @After
  public void teardown() {
    if (cap != null) {
      cap.stopCapturing();
      cap = null;
    }
    if (cluster != null) {
      cluster.shutdown();
      cluster = null;
    }
    NativeIO.POSIX.setCacheManipulator(prev);
  }

  private static HdfsConfiguration conf(long c) {
    HdfsConfiguration conf = new HdfsConfiguration();
    conf.setLong(DFS_BLOCK_SIZE_KEY, B);
    conf.setLong(DFS_DATANODE_MAX_LOCKED_MEMORY_KEY, c);
    conf.setLong(DFS_HEARTBEAT_INTERVAL_KEY, 1);
    conf.setLong(DFS_CACHEREPORT_INTERVAL_MSEC_KEY, 1000);
    conf.setLong(DFS_NAMENODE_PATH_BASED_CACHE_REFRESH_INTERVAL_MS, 1000);
    return conf;
  }

  private void start(long c) throws Exception {
    cluster = new MiniDFSCluster.Builder(conf(c)).numDataNodes(1).build();
    cluster.waitActive();
    LOG.info("IFCHK-instr manipulator={} pageSize={} memlock={} C={}",
        NativeIO.POSIX.getCacheManipulator().getClass().getSimpleName(),
        NativeIO.POSIX.getCacheManipulator().getOperatingSystemPageSize(),
        NativeIO.POSIX.getCacheManipulator().getMemlockLimit(), c);
    System.out.println("IFCHK,instr,manipulator="
        + NativeIO.POSIX.getCacheManipulator().getClass().getSimpleName()
        + ",pageSize=" + NativeIO.POSIX.getCacheManipulator().getOperatingSystemPageSize()
        + ",dnCacheCapacity=" + dn().getFSDataset().getCacheCapacity() + ",C=" + c);
  }

  private DataNode dn() {
    return cluster.getDataNodes().get(0);
  }

  private DatanodeDescriptor desc() throws Exception {
    return cluster.getNamesystem().getBlockManager().getDatanodeManager()
        .getDatanode(dn().getDatanodeId());
  }

  /** {pending bytes, pending count, cacheRemaining, cacheCapacity, cacheUsed} at the NameNode. */
  private long[] nn() throws Exception {
    FSNamesystem ns = cluster.getNamesystem();
    ns.readLock();
    try {
      DatanodeDescriptor d = desc();
      long bytes = 0;
      long n = 0;
      for (CachedBlock cb : d.getPendingCached()) {
        BlockInfo bi = ns.getBlockManager().getStoredBlock(new Block(cb.getBlockId()));
        n++;
        if (bi != null) {
          bytes += bi.getNumBytes();
        }
      }
      return new long[] {bytes, n, d.getCacheRemaining(), d.getCacheCapacity(), d.getCacheUsed()};
    } finally {
      ns.readUnlock();
    }
  }

  private void workload() throws Exception {
    DistributedFileSystem dfs = cluster.getFileSystem();
    DFSTestUtil.createFile(dfs, new Path("/f"), 4096, FILE_LEN, B, (short) 1, 0xFADED);
    dfs.addCachePool(new CachePoolInfo("p"));
    dfs.addCacheDirective(new CacheDirectiveInfo.Builder().setPool("p")
        .setPath(new Path("/f")).setReplication((short) 1).build());
  }

  private long directiveBytesCached() throws Exception {
    RemoteIterator<CacheDirectiveEntry> it = cluster.getFileSystem().listCacheDirectives(null);
    long s = 0;
    while (it.hasNext()) {
      s += it.next().getStats().getBytesCached();
    }
    return s;
  }

  /** "lines/ids/idlist" of the line-534 DEBUG message in the captured window, then clears it. */
  private String drops() {
    String out = cap.getOutput();
    cap.clearOutput();
    Matcher m = DROP.matcher(out);
    int lines = 0;
    Set<String> ids = new TreeSet<>();
    StringBuilder rem = new StringBuilder();
    while (m.find()) {
      lines++;
      ids.add(m.group(1));
      if (lines <= 3) {
        rem.append(m.group(3)).append(';');
      }
    }
    return "dropLines=" + lines + ",dropIds=" + ids.size() + ",dropRemaining=" + rem;
  }

  /** Wait until the DN's cached block count is unchanged for 3 s (max 30 s). Returns {settled, t, maxUsed}. */
  private long[] waitDnStable() throws Exception {
    long t0 = System.currentTimeMillis();
    long last = -1;
    long since = t0;
    long maxUsed = 0;
    while (true) {
      long now = System.currentTimeMillis();
      long nb = dn().getFSDataset().getNumBlocksCached();
      maxUsed = Math.max(maxUsed, dn().getFSDataset().getCacheUsed());
      if (nb != last) {
        last = nb;
        since = now;
      }
      if (now - since >= 3000 && now - t0 >= 3000) {
        return new long[] {1, now - t0, maxUsed};
      }
      if (now - t0 > 30000) {
        return new long[] {0, now - t0, maxUsed};
      }
      Thread.sleep(100);
    }
  }

  private String dnState() {
    return "dnCacheUsed=" + dn().getFSDataset().getCacheUsed()
        + ",dnCacheCapacity=" + dn().getFSDataset().getCacheCapacity()
        + ",dnBlocks=" + dn().getFSDataset().getNumBlocksCached()
        + ",dnFailed=" + dn().getFSDataset().getNumBlocksFailedToCache();
  }

  // ---------------------------------------------------------------- Test A
  private void testA(long c) throws Exception {
    start(c);
    cap = LogCapturer.captureLogs(CRM_LOG);
    workload();
    long[] w = waitDnStable();
    long[] p = nn();
    String line = "IFCHK,A,C=" + c + ",settled=" + (w[0] == 1) + ",t_ms=" + w[1] + ","
        + dnState() + ",maxDnCacheUsed=" + w[2] + ",bytesCached=" + directiveBytesCached()
        + ",nnPendingBytes=" + p[0] + ",nnPendingN=" + p[1] + ",nnRemaining=" + p[2]
        + "," + drops();
    System.out.println(line);
  }

  @Test(timeout = 120000)
  public void testA_C16384() throws Exception {
    testA(16384);
  }

  @Test(timeout = 120000)
  public void testA_C32768() throws Exception {
    testA(32768);
  }

  @Test(timeout = 120000)
  public void testA_C65536() throws Exception {
    testA(65536);
  }

  // ---------------------------------------------------------------- Test B (+ C)
  /** mode "U": setCacheUsed(v); mode "Cp": setCacheCapacity(v) with U = 0. */
  private void testB(String mode, long v, boolean testC) throws Exception {
    start(C_B);
    GenericTestUtils.waitFor(() -> {
      try {
        return desc().getCacheCapacity() == C_B;
      } catch (Exception e) {
        return false;
      }
    }, 100, 10000);
    DataNodeTestUtils.setHeartbeatsDisabledForTests(dn(), true);
    cap = LogCapturer.captureLogs(CRM_LOG);
    workload();
    Thread.sleep(3000);
    long[] p0 = nn();
    String pre = drops();
    FSNamesystem ns = cluster.getNamesystem();
    ns.writeLock();
    try {
      if (mode.equals("U")) {
        desc().setCacheUsed(v);
      } else {
        desc().setCacheCapacity(v);
      }
    } finally {
      ns.writeUnlock();
    }
    Thread.sleep(3000);
    long[] p1 = nn();
    String w1 = drops();
    Thread.sleep(3000);
    long[] p2 = nn();
    String w2 = drops();
    System.out.println("IFCHK,B,mode=" + mode + ",v=" + v
        + ",P0=" + p0[0] + ",P0n=" + p0[1] + ",P0remaining=" + p0[2]
        + ",pre_" + pre.replace(",", ",pre_")
        + ",P1=" + p1[0] + ",P1n=" + p1[1] + ",remaining=" + p1[2]
        + ",nnCap=" + p1[3] + ",nnUsed=" + p1[4]
        + ",w1_" + w1.replace(",", ",w1_")
        + ",P2=" + p2[0] + ",P2n=" + p2[1]
        + ",w2_" + w2.replace(",", ",w2_")
        + "," + dnState());
    if (testC) {
      DataNodeTestUtils.setHeartbeatsDisabledForTests(dn(), false);
      DataNodeTestUtils.triggerHeartbeat(dn());
      long[] w = waitDnStable();
      long[] p = nn();
      System.out.println("IFCHK,C,settled=" + (w[0] == 1) + ",t_ms=" + w[1] + "," + dnState()
          + ",maxDnCacheUsed=" + w[2] + ",bytesCached=" + directiveBytesCached()
          + ",nnPendingBytes=" + p[0] + ",nnPendingN=" + p[1] + ",nnRemaining=" + p[2]
          + "," + drops());
    }
  }

  @Test(timeout = 120000)
  public void testB_U0() throws Exception {
    testB("U", 0, false);
  }

  @Test(timeout = 120000)
  public void testB_U16384() throws Exception {
    testB("U", 16384, false);
  }

  @Test(timeout = 120000)
  public void testB_U32768() throws Exception {
    testB("U", 32768, false);
  }

  @Test(timeout = 120000)
  public void testB_U49152() throws Exception {
    testB("U", 49152, true);
  }

  @Test(timeout = 120000)
  public void testB_U65536() throws Exception {
    testB("U", 65536, false);
  }

  @Test(timeout = 120000)
  public void testB_U81920() throws Exception {
    testB("U", 81920, false);
  }

  @Test(timeout = 120000)
  public void testBc_C65536() throws Exception {
    testB("Cp", 65536, false);
  }

  @Test(timeout = 120000)
  public void testBc_C32768() throws Exception {
    testB("Cp", 32768, false);
  }

  @Test(timeout = 120000)
  public void testBc_C0() throws Exception {
    testB("Cp", 0, false);
  }
}
