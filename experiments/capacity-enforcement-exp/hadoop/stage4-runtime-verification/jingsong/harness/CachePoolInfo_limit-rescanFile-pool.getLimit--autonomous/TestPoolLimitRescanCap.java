/*
 * Stage-4 harness, capacity-enforcement-exp, case
 * CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous (B2, unit tier, with amendments A1-A3, A7).
 * Not upstream. Copied into hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/
 * of the case's local source copy. Prints one IFCHK line per steady-state reading; makes no assertion on the
 * predictions (selfcheck.py compares them with B2f).
 */
package org.apache.hadoop.hdfs.server.namenode;

import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_BLOCK_SIZE_KEY;
import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_CACHEREPORT_INTERVAL_MSEC_KEY;
import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_DATANODE_MAX_LOCKED_MEMORY_KEY;
import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_HEARTBEAT_INTERVAL_KEY;
import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_NAMENODE_PATH_BASED_CACHE_REFRESH_INTERVAL_MS;
import static org.apache.hadoop.hdfs.DFSConfigKeys.DFS_REPLICATION_KEY;

import java.util.ArrayList;
import java.util.EnumSet;
import java.util.Iterator;
import java.util.List;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.hadoop.fs.CacheFlag;
import org.apache.hadoop.fs.InvalidRequestException;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.fs.RemoteIterator;
import org.apache.hadoop.hdfs.DFSTestUtil;
import org.apache.hadoop.hdfs.DistributedFileSystem;
import org.apache.hadoop.hdfs.HdfsConfiguration;
import org.apache.hadoop.hdfs.MiniDFSCluster;
import org.apache.hadoop.hdfs.protocol.CacheDirectiveEntry;
import org.apache.hadoop.hdfs.protocol.CacheDirectiveInfo;
import org.apache.hadoop.hdfs.protocol.CachePoolEntry;
import org.apache.hadoop.hdfs.protocol.CachePoolInfo;
import org.apache.hadoop.hdfs.protocol.CachePoolStats;
import org.apache.hadoop.hdfs.server.blockmanagement.CacheReplicationMonitor;
import org.apache.hadoop.hdfs.server.blockmanagement.DatanodeDescriptor.CachedBlocksList.Type;
import org.apache.hadoop.hdfs.server.datanode.DataNode;
import org.apache.hadoop.io.nativeio.NativeIO;
import org.apache.hadoop.io.nativeio.NativeIO.POSIX.CacheManipulator;
import org.apache.hadoop.io.nativeio.NativeIO.POSIX.NoMlockCacheManipulator;
import org.apache.hadoop.test.GenericTestUtils;
import org.apache.hadoop.test.GenericTestUtils.LogCapturer;
import org.apache.hadoop.util.GSet;
import org.junit.After;
import org.junit.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.event.Level;

public class TestPoolLimitRescanCap {
  static final long B = 4096;
  static final long DN_CAP = 16 * B;          // 65536
  static final long UNL = CachePoolInfo.LIMIT_UNLIMITED;
  static final Pattern SKIP = Pattern.compile("not scanning file (\\S+) because");

  static {
    NativeIO.POSIX.setCacheManipulator(new NoMlockCacheManipulator());
  }

  private MiniDFSCluster cluster;
  private DistributedFileSystem dfs;
  private CacheManipulator prev;
  private LogCapturer cap;

  private void start(long dnCap) throws Exception {
    HdfsConfiguration conf = new HdfsConfiguration();
    conf.setLong(DFS_BLOCK_SIZE_KEY, B);
    conf.setLong(DFS_DATANODE_MAX_LOCKED_MEMORY_KEY, dnCap);
    conf.setLong(DFS_HEARTBEAT_INTERVAL_KEY, 1);
    conf.setLong(DFS_CACHEREPORT_INTERVAL_MSEC_KEY, 1000);
    conf.setLong(DFS_NAMENODE_PATH_BASED_CACHE_REFRESH_INTERVAL_MS, 1000);
    conf.setInt(DFS_REPLICATION_KEY, 1);
    prev = NativeIO.POSIX.getCacheManipulator();
    NativeIO.POSIX.setCacheManipulator(new NoMlockCacheManipulator());
    Logger crm = LoggerFactory.getLogger(CacheReplicationMonitor.class);
    GenericTestUtils.setLogLevel(crm, Level.DEBUG);
    cap = LogCapturer.captureLogs(crm);
    cluster = new MiniDFSCluster.Builder(conf).numDataNodes(1).build();
    cluster.waitActive();
    dfs = cluster.getFileSystem();
    System.out.println("IFCHK,instr,dnCap=" + dnCap + ",manipulator="
        + NativeIO.POSIX.getCacheManipulator().getClass().getSimpleName()
        + ",dnCacheCapacity=" + dn().getFSDataset().getCacheCapacity());
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
      System.out.println("IFCHK,teardown,dnCacheUsed=" + dn().getFSDataset().getCacheUsed()
          + ",waitMs=" + (System.currentTimeMillis() - t0));
      cluster.shutdown();
      cluster = null;
    }
    if (cap != null) {
      cap.stopCapturing();
      cap = null;
    }
    if (prev != null) {
      NativeIO.POSIX.setCacheManipulator(prev);
    }
  }

  private CachePoolStats poolStats(String pool) throws Exception {
    RemoteIterator<CachePoolEntry> it = dfs.listCachePools();
    while (it.hasNext()) {
      CachePoolEntry e = it.next();
      if (e.getInfo().getPoolName().equals(pool)) {
        return e.getStats();
      }
    }
    throw new IllegalStateException("no pool " + pool);
  }

  private int nnCachedBlocks() {
    FSNamesystem ns = cluster.getNamesystem();
    int n = 0;
    ns.readLock();
    try {
      GSet<CachedBlock, CachedBlock> cbs = ns.getCacheManager().getCachedBlocks();
      if (cbs != null) {
        for (Iterator<CachedBlock> i = cbs.iterator(); i.hasNext();) {
          if (!i.next().getDatanodes(Type.CACHED).isEmpty()) {
            n++;
          }
        }
      }
    } finally {
      ns.readUnlock();
    }
    return n;
  }

  /** Tuple: bytesNeeded, bytesCached, bytesOverlimit, filesNeeded, filesCached, nnCached, dnUsed, dnBlocks. */
  private long[] read(String pool) throws Exception {
    CachePoolStats s = poolStats(pool);
    return new long[] {s.getBytesNeeded(), s.getBytesCached(), s.getBytesOverlimit(),
        s.getFilesNeeded(), s.getFilesCached(), nnCachedBlocks(),
        dn().getFSDataset().getCacheUsed(), dn().getFSDataset().getNumBlocksCached()};
  }

  private static TreeSet<String> skipped(String log) {
    TreeSet<String> s = new TreeSet<>();
    Matcher m = SKIP.matcher(log);
    while (m.find()) {
      s.add(m.group(1));
    }
    return s;
  }

  private static String join(TreeSet<String> s) {
    StringBuilder b = new StringBuilder();
    for (String x : s) {
      if (b.length() > 0) {
        b.append(';');
      }
      b.append(x);
    }
    return b.length() == 0 ? "-" : b.toString();
  }

  /**
   * A2: poll every 500 ms; steady when the tuple is unchanged for 10 consecutive polls and at
   * least 5 s after the change; give up at 60 s (settled=false).
   */
  private void steady(String test, String phase, String pool, long limit, long changeMs,
      int logOffset) throws Exception {
    List<long[]> hist = new ArrayList<>();
    List<Integer> logLen = new ArrayList<>();
    long maxDnUsed = 0;
    boolean settled = false;
    while (true) {
      long[] r = read(pool);
      hist.add(r);
      logLen.add(cap.getOutput().length());
      maxDnUsed = Math.max(maxDnUsed, r[6]);
      long el = System.currentTimeMillis() - changeMs;
      int n = hist.size();
      if (n >= 11 && el >= 5000) {
        boolean same = true;
        for (int i = n - 11; i < n - 1; i++) {
          if (!java.util.Arrays.equals(hist.get(i), r)) {
            same = false;
            break;
          }
        }
        if (same) {
          settled = true;
          break;
        }
      }
      if (el >= 60000) {
        break;
      }
      Thread.sleep(500);
    }
    long[] r = hist.get(hist.size() - 1);
    String all = cap.getOutput();
    int winStart = logLen.get(Math.max(0, logLen.size() - 11));
    String window = all.substring(Math.max(winStart, logOffset));
    String since = all.substring(Math.min(logOffset, all.length()));
    System.out.println("IFCHK,row," + test + "," + phase + ",L=" + (limit == UNL ? "unlimited" : limit)
        + ",settled=" + settled + ",elapsedMs=" + (System.currentTimeMillis() - changeMs)
        + ",bytesNeeded=" + r[0] + ",bytesCached=" + r[1] + ",bytesOverlimit=" + r[2]
        + ",filesNeeded=" + r[3] + ",filesCached=" + r[4] + ",nnCached=" + r[5]
        + ",dnCacheUsed=" + r[6] + ",dnBlocks=" + r[7] + ",maxDnCacheUsed=" + maxDnUsed
        + ",skipWindow=" + join(skipped(window)) + ",skipSince=" + join(skipped(since)));
  }

  private void mkPoolAndDirective(String pool, long limit, String dir) throws Exception {
    dfs.mkdirs(new Path(dir));
    dfs.addCachePool(new CachePoolInfo(pool).setLimit(limit));
    long id = dfs.addCacheDirective(new CacheDirectiveInfo.Builder()
        .setPool(pool).setPath(new Path(dir)).setReplication((short) 1).build());
    System.out.println("IFCHK,directive,pool=" + pool + ",dir=" + dir + ",id=" + id + ",noForce=accepted");
  }

  private void writeFiles(String dir, String[] names, long[] sizes) throws Exception {
    for (int i = 0; i < names.length; i++) {
      DFSTestUtil.createFile(dfs, new Path(dir + "/" + names[i]), 1024, sizes[i], B, (short) 1,
          0x5150 + i);
    }
  }

  private static final String[] F = {"f01", "f02", "f03", "f04", "f05", "f06"};
  private static final long[] FS = {B, B, B, B, B, B};

  private void limitRow(String test, long limit) throws Exception {
    start(DN_CAP);
    mkPoolAndDirective("p", limit, "/d");
    int off = cap.getOutput().length();
    long t = System.currentTimeMillis();
    writeFiles("/d", F, FS);
    steady(test, "steady", "p", limit, t, off);
  }

  @Test(timeout = 180000)
  public void testL0() throws Exception {
    limitRow("L0", 0);
  }

  @Test(timeout = 180000)
  public void testL2B() throws Exception {
    limitRow("L2B", 2 * B);
  }

  @Test(timeout = 180000)
  public void testL25B() throws Exception {
    limitRow("L2.5B", 5 * B / 2);
  }

  @Test(timeout = 180000)
  public void testL4B() throws Exception {
    limitRow("L4B", 4 * B);
  }

  @Test(timeout = 180000)
  public void testL6B() throws Exception {
    limitRow("L6B", 6 * B);
  }

  @Test(timeout = 180000)
  public void testUnlimited() throws Exception {
    limitRow("unlimited", UNL);
  }

  @Test(timeout = 240000)
  public void testLowering() throws Exception {
    limitRow("lowering", UNL);
    int off = cap.getOutput().length();
    long t = System.currentTimeMillis();
    dfs.modifyCachePool(new CachePoolInfo("p").setLimit(3 * B));
    System.out.println("IFCHK,modify,pool=p,limit=" + (3 * B));
    steady("lowering", "after", "p", 3 * B, t, off);
  }

  @Test(timeout = 180000)
  public void testOrder() throws Exception {
    start(DN_CAP);
    mkPoolAndDirective("q", 3 * B, "/e");
    int off = cap.getOutput().length();
    long t = System.currentTimeMillis();
    writeFiles("/e", new String[] {"a1", "a2", "a3"}, new long[] {B, 3 * B, B});
    steady("order", "steady", "q", 3 * B, t, off);
  }

  @Test(timeout = 180000)
  public void testAddTimeContrast() throws Exception {
    start(DN_CAP);
    dfs.mkdirs(new Path("/d"));
    writeFiles("/d", F, FS);
    dfs.addCachePool(new CachePoolInfo("r").setLimit(2 * B));
    CacheDirectiveInfo info = new CacheDirectiveInfo.Builder()
        .setPool("r").setPath(new Path("/d")).setReplication((short) 1).build();
    String noForce;
    try {
      dfs.addCacheDirective(info, EnumSet.noneOf(CacheFlag.class));
      noForce = "accepted";
    } catch (InvalidRequestException e) {
      noForce = "InvalidRequestException:" + e.getMessage().replace(',', ' ');
    }
    int nDir = 0;
    RemoteIterator<CacheDirectiveEntry> it = dfs.listCacheDirectives(null);
    while (it.hasNext()) {
      it.next();
      nDir++;
    }
    System.out.println("IFCHK,addtime,noForce=" + noForce + ",directivesAfterNoForce=" + nDir);
    int off = cap.getOutput().length();
    long t = System.currentTimeMillis();
    long id = dfs.addCacheDirective(info, EnumSet.of(CacheFlag.FORCE));
    System.out.println("IFCHK,addtime,force=accepted,id=" + id);
    steady("force", "steady", "r", 2 * B, t, off);
  }

  @Test(timeout = 180000)
  public void testDnCapControl() throws Exception {
    start(3 * B);
    mkPoolAndDirective("p", UNL, "/d");
    int off = cap.getOutput().length();
    long t = System.currentTimeMillis();
    writeFiles("/d", F, FS);
    steady("dncap", "steady", "p", UNL, t, off);
  }
}
