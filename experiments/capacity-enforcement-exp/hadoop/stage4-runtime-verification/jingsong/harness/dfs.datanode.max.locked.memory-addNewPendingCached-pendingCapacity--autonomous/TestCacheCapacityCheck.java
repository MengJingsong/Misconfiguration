/*
 * Stage-4 harness, capacity-enforcement-exp (Hadoop, Jingsong), case
 * dfs.datanode.max.locked.memory-addNewPendingCached-pendingCapacity--autonomous (B2, unit tier, with the
 * stage-4 amendments A1-A3 of 2026-11-25). Not upstream. Copied into
 * hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/ of the case's local
 * source copy. Prints one IFCHK line per steady-state reading; makes no assertion on the predictions
 * (they are compared with B2f in the results file).
 *
 * Tests testC* are the unmutated run (B2e steps 1-4 and the B2h positive control);
 * mutantC32768 is run only with line 745 of CacheReplicationMonitor disabled (B2e step 5).
 */
package org.apache.hadoop.hdfs.server.namenode;

import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_BLOCK_SIZE_KEY;
import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_CACHEREPORT_INTERVAL_MSEC_KEY;
import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_DATANODE_MAX_LOCKED_MEMORY_KEY;
import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_HEARTBEAT_INTERVAL_KEY;
import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_NAMENODE_MIN_BLOCK_SIZE_KEY;
import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_NAMENODE_PATH_BASED_CACHE_REFRESH_INTERVAL_MS;
import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_REPLICATION_KEY;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.hadoop.fs.Path;
import org.apache.hadoop.fs.RemoteIterator;
import org.apache.hadoop.hdfs.DFSTestUtil;
import org.apache.hadoop.hdfs.DistributedFileSystem;
import org.apache.hadoop.hdfs.HdfsConfiguration;
import org.apache.hadoop.hdfs.MiniDFSCluster;
import org.apache.hadoop.hdfs.protocol.CacheDirectiveEntry;
import org.apache.hadoop.hdfs.protocol.CacheDirectiveInfo;
import org.apache.hadoop.hdfs.protocol.CacheDirectiveStats;
import org.apache.hadoop.hdfs.protocol.CachePoolInfo;
import org.apache.hadoop.hdfs.server.blockmanagement.CacheReplicationMonitor;
import org.apache.hadoop.hdfs.server.blockmanagement.DatanodeDescriptor;
import org.apache.hadoop.hdfs.server.datanode.DataNode;
import org.apache.hadoop.hdfs.server.datanode.fsdataset.impl.FsDatasetCache;
import org.apache.hadoop.io.nativeio.NativeIO;
import org.apache.hadoop.io.nativeio.NativeIO.POSIX.CacheManipulator;
import org.apache.hadoop.io.nativeio.NativeIO.POSIX.NoMlockCacheManipulator;
import org.apache.hadoop.test.GenericTestUtils;
import org.apache.hadoop.test.GenericTestUtils.LogCapturer;
import org.junit.After;
import org.junit.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.event.Level;

public class TestCacheCapacityCheck {
  static final long B = 4096;
  static final Pattern REJ = Pattern.compile("is not a valid possibility because the block has size");
  static final Pattern NORES = Pattern.compile("could not reserve more bytes");
  static final Pattern ADDED = Pattern.compile("added to PENDING_CACHED on DataNode");

  static {
    NativeIO.POSIX.setCacheManipulator(new NoMlockCacheManipulator());
  }

  private MiniDFSCluster cluster;
  private DistributedFileSystem dfs;
  private CacheManipulator prev;
  private LogCapturer crmCap;
  private LogCapturer dnCap;
  private long cap;

  private void start(long c) throws Exception {
    cap = c;
    HdfsConfiguration conf = new HdfsConfiguration();
    conf.setLong(DFS_BLOCK_SIZE_KEY, B);
    conf.setLong(DFS_NAMENODE_MIN_BLOCK_SIZE_KEY, B);
    conf.setLong(DFS_DATANODE_MAX_LOCKED_MEMORY_KEY, c);
    conf.setLong(DFS_HEARTBEAT_INTERVAL_KEY, 1);
    conf.setLong(DFS_CACHEREPORT_INTERVAL_MSEC_KEY, 1000);
    conf.setLong(DFS_NAMENODE_PATH_BASED_CACHE_REFRESH_INTERVAL_MS, 1000);
    conf.setInt(DFS_REPLICATION_KEY, 1);
    prev = NativeIO.POSIX.getCacheManipulator();
    NativeIO.POSIX.setCacheManipulator(new NoMlockCacheManipulator());
    Logger crm = LoggerFactory.getLogger(CacheReplicationMonitor.class);
    GenericTestUtils.setLogLevel(crm, Level.TRACE);
    crmCap = LogCapturer.captureLogs(crm);
    dnCap = LogCapturer.captureLogs(LoggerFactory.getLogger(FsDatasetCache.class));
    cluster = new MiniDFSCluster.Builder(conf).numDataNodes(1).build();
    cluster.waitActive();
    dfs = cluster.getFileSystem();
    System.out.println("IFCHK,instr,C=" + c + ",manipulator="
        + NativeIO.POSIX.getCacheManipulator().getClass().getSimpleName()
        + ",pageSize=" + NativeIO.POSIX.getCacheManipulator().getOperatingSystemPageSize()
        + ",dnCacheCapacity=" + dn().getFSDataset().getCacheCapacity()
        + ",testBuildData=" + System.getProperty("test.build.data"));
  }

  private DataNode dn() {
    return cluster.getDataNodes().get(0);
  }

  @After
  public void teardown() throws Exception {
    if (cluster != null) {
      RemoteIterator<CacheDirectiveEntry> it = dfs.listCacheDirectives(null);
      List<Long> ids = new ArrayList<>();
      while (it.hasNext()) {
        ids.add(it.next().getInfo().getId());
      }
      for (long id : ids) {
        dfs.removeCacheDirective(id);
      }
      long t0 = System.currentTimeMillis();
      while (dn().getFSDataset().getCacheUsed() != 0
          && System.currentTimeMillis() - t0 < 60000) {
        Thread.sleep(500);
      }
      System.out.println("IFCHK,teardown,C=" + cap + ",dnCacheUsed=" + dn().getFSDataset().getCacheUsed()
          + ",waitMs=" + (System.currentTimeMillis() - t0));
      cluster.shutdown();
      cluster = null;
    }
    if (crmCap != null) {
      crmCap.stopCapturing();
      crmCap = null;
    }
    if (dnCap != null) {
      dnCap.stopCapturing();
      dnCap = null;
    }
    if (prev != null) {
      NativeIO.POSIX.setCacheManipulator(prev);
    }
  }

  private static int count(Pattern p, String s) {
    Matcher m = p.matcher(s);
    int n = 0;
    while (m.find()) {
      n++;
    }
    return n;
  }

  /**
   * Tuple: dnCacheUsed, dnBlocksCached, dnFailedToCache, nnCacheRemaining, nnCached, nnPendingCached,
   * bytesNeeded, bytesCached, filesCached.
   */
  private long[] read() throws Exception {
    long used = dn().getFSDataset().getCacheUsed();
    long nb = dn().getFSDataset().getNumBlocksCached();
    long fail = dn().getFSDataset().getNumBlocksFailedToCache();
    FSNamesystem ns = cluster.getNamesystem();
    long rem;
    long cached;
    long pending;
    ns.readLock();
    try {
      DatanodeDescriptor d = ns.getBlockManager().getDatanodeManager()
          .getDatanode(dn().getDatanodeId());
      rem = d.getCacheRemaining();
      cached = d.getCached().size();
      pending = d.getPendingCached().size();
    } finally {
      ns.readUnlock();
    }
    long need = 0;
    long bc = 0;
    long fc = 0;
    RemoteIterator<CacheDirectiveEntry> it = dfs.listCacheDirectives(null);
    while (it.hasNext()) {
      CacheDirectiveStats s = it.next().getStats();
      need += s.getBytesNeeded();
      bc += s.getBytesCached();
      fc += s.getFilesCached();
    }
    return new long[] {used, nb, fail, rem, cached, pending, need, bc, fc};
  }

  /**
   * A2: poll every 500 ms; steady when the tuple is unchanged for 10 consecutive polls and at least
   * 35 s after the directive (one 30-s cache-command resend window); give up at 90 s (settled=false).
   */
  private void steady(String test, String path, long t0, int crmOff, int dnOff) throws Exception {
    List<long[]> hist = new ArrayList<>();
    long maxUsed = 0;
    long maxPending = 0;
    long maxBlocks = 0;
    boolean settled = false;
    while (true) {
      long[] r = read();
      hist.add(r);
      maxUsed = Math.max(maxUsed, r[0]);
      maxBlocks = Math.max(maxBlocks, r[1]);
      maxPending = Math.max(maxPending, r[5]);
      long el = System.currentTimeMillis() - t0;
      int n = hist.size();
      if (n >= 10 && el >= 35000) {
        boolean same = true;
        for (int i = n - 10; i < n - 1; i++) {
          if (!Arrays.equals(hist.get(i), r)) {
            same = false;
            break;
          }
        }
        if (same) {
          settled = true;
          break;
        }
      }
      if (el >= 90000) {
        break;
      }
      Thread.sleep(500);
    }
    long[] r = hist.get(hist.size() - 1);
    String crm = crmCap.getOutput();
    String dnl = dnCap.getOutput();
    crm = crm.substring(Math.min(crmOff, crm.length()));
    dnl = dnl.substring(Math.min(dnOff, dnl.length()));
    System.out.println("IFCHK,row," + test + ",path=" + path + ",C=" + cap + ",settled=" + settled
        + ",elapsedMs=" + (System.currentTimeMillis() - t0) + ",polls=" + hist.size()
        + ",dnCacheUsed=" + r[0] + ",dnBlocksCached=" + r[1] + ",dnFailedToCache=" + r[2]
        + ",nnCacheRemaining=" + r[3] + ",nnCached=" + r[4] + ",nnPendingCached=" + r[5]
        + ",bytesNeeded=" + r[6] + ",bytesCached=" + r[7] + ",filesCached=" + r[8]
        + ",maxDnCacheUsed=" + maxUsed + ",maxDnBlocksCached=" + maxBlocks
        + ",maxNnPendingCached=" + maxPending
        + ",traceRejectLines=" + count(REJ, crm) + ",traceAddedLines=" + count(ADDED, crm)
        + ",dnCouldNotReserveLines=" + count(NORES, dnl)
        + ",withinCap=" + (r[0] <= cap && maxUsed <= cap));
  }

  private void row(String test, long c, String path, int blocks) throws Exception {
    start(c);
    DFSTestUtil.createFile(dfs, new Path(path), 1024, blocks * B, B, (short) 1, 0x0723L + blocks);
    dfs.addCachePool(new CachePoolInfo("p"));
    int crmOff = crmCap.getOutput().length();
    int dnOff = dnCap.getOutput().length();
    long t0 = System.currentTimeMillis();
    long id = dfs.addCacheDirective(new CacheDirectiveInfo.Builder()
        .setPool("p").setPath(new Path(path)).setReplication((short) 1).build());
    System.out.println("IFCHK,directive,test=" + test + ",path=" + path + ",blocks=" + blocks
        + ",fileBytes=" + (blocks * B) + ",id=" + id);
    steady(test, path, t0, crmOff, dnOff);
  }

  @Test(timeout = 240000)
  public void testC0() throws Exception {
    row("C0", 0, "/big", 32);
  }

  @Test(timeout = 240000)
  public void testC16384() throws Exception {
    row("C16384", 16384, "/big", 32);
  }

  @Test(timeout = 240000)
  public void testC32768() throws Exception {
    row("C32768", 32768, "/big", 32);
  }

  @Test(timeout = 240000)
  public void testC65536() throws Exception {
    row("C65536", 65536, "/big", 32);
  }

  /** B2h positive control: a 2-block file under C = 32768 is cached whole. */
  @Test(timeout = 240000)
  public void testCSmallControl() throws Exception {
    row("small-C32768", 32768, "/small", 2);
  }

  /** B2e step 5: run only on a copy whose line 745 is disabled. */
  @Test(timeout = 240000)
  public void mutantC32768() throws Exception {
    row("MUTANT-C32768", 32768, "/big", 32);
  }
}
