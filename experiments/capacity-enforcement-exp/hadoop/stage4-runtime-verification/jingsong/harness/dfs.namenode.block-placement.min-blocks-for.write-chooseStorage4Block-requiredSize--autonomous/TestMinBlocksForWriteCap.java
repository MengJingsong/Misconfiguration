/*
 * Stage-4 unit tier (B2) for
 * dfs.namenode.block-placement.min-blocks-for.write-chooseStorage4Block-requiredSize--autonomous.
 * Lives only in the per-case source copy (never in the repository's systems/hadoop/source).
 * Prints readings; does not assert exact K (B2e step 4), so a mismatch is a reading, not a crash.
 * Every reading line starts with "O24," so it can be grepped from the surefire output.
 */
package org.apache.hadoop.hdfs.server.blockmanagement;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

import org.apache.commons.io.FileUtils;
import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.fs.StorageType;
import org.apache.hadoop.hdfs.DFSConfigKeys;
import org.apache.hadoop.hdfs.DFSTestUtil;
import org.apache.hadoop.hdfs.MiniDFSCluster;
import org.apache.hadoop.hdfs.server.datanode.DataNode;
import org.apache.hadoop.hdfs.server.datanode.DataNodeTestUtils;
import org.apache.hadoop.hdfs.server.datanode.fsdataset.FsDatasetSpi;
import org.apache.hadoop.hdfs.server.datanode.fsdataset.impl.FsVolumeImpl;
import org.apache.hadoop.hdfs.server.protocol.DatanodeStorage;
import org.apache.hadoop.test.GenericTestUtils;
import org.junit.BeforeClass;
import org.junit.Test;

public class TestMinBlocksForWriteCap {
  static final String KEY = DFSConfigKeys.DFS_NAMENODE_BLOCKPLACEMENTPOLICY_MIN_BLOCKS_FOR_WRITE_KEY;
  static final long B = 1048576L;          // dfs.blocksize for U2
  static final long C = 32L * 1048576L;    // storage capacity for U2

  @BeforeClass
  public static void logLevels() {
    GenericTestUtils.setLogLevel(BlockPlacementPolicy.LOG, org.slf4j.event.Level.DEBUG);
  }

  static void out(String s) {
    System.out.println("O24," + s);
    System.out.flush();
  }

  static String sid(DatanodeStorageInfo s) {
    return s == null ? "null" : s.getStorageID();
  }

  // ---------------- U1: pure placement, no I/O (B = 1024, N = 4, requiredSize = 4096) -------------

  /**
   * The DatanodeStorageInfo returned by DFSTestUtil.createDatanodeStorageInfo is a second object,
   * not the one in the descriptor's storageMap (BlockManagerTestUtil.newDatanodeStorageInfo); set
   * utilization on the registered one, which chooseStorage4Block iterates (attempt-1 harness bug).
   */
  static DatanodeStorageInfo newStorage() {
    DatanodeDescriptor dn = DFSTestUtil.createDatanodeStorageInfo("s1", "1.1.1.1")
        .getDatanodeDescriptor();
    return dn.getStorageInfo("s1");
  }

  @Test
  public void u1aThreshold() {
    for (long r : new long[] {4095, 4096, 4097, 8192}) {
      DatanodeStorageInfo s = newStorage();
      DatanodeDescriptor dn = s.getDatanodeDescriptor();
      s.setUtilizationForTesting(1L << 20, (1L << 20) - r, r, (1L << 20) - r);
      out("U1a,r=" + r + ",result=" + sid(dn.chooseStorage4Block(StorageType.DISK, 1024, 4)));
    }
  }

  @Test
  public void u1bScheduled() {
    DatanodeStorageInfo s = newStorage();
    DatanodeDescriptor dn = s.getDatanodeDescriptor();
    s.setUtilizationForTesting(1L << 20, (1L << 20) - 8192, 8192, (1L << 20) - 8192);
    for (int k = 0; k <= 5; k++) {
      out("U1b,r=8192,k=" + k + ",scheduled=" + dn.getBlocksScheduled(StorageType.DISK)
          + ",result=" + sid(dn.chooseStorage4Block(StorageType.DISK, 1024, 4)));
      dn.incrementBlocksScheduled(StorageType.DISK);
    }
  }

  @Test
  public void u1cPerStorageFilter() {
    DatanodeStorageInfo s1 = newStorage();
    DatanodeDescriptor dn = s1.getDatanodeDescriptor();
    DatanodeStorageInfo s2 = dn.updateStorage(new DatanodeStorage("s2"));
    s1.setUtilizationForTesting(1L << 20, (1L << 20) - 3072, 3072, (1L << 20) - 3072);
    s2.setUtilizationForTesting(1L << 20, (1L << 20) - 3072, 3072, (1L << 20) - 3072);
    out("U1c,storages=" + dn.getStorageInfos().length + ",r=3072+3072,sum=6144,result="
        + sid(dn.chooseStorage4Block(StorageType.DISK, 1024, 4)));
  }

  @Test
  public void u1dFirstStorageReturned() {
    // (a) the design's case: s1 r=4096, s2 r=1000
    // (b) supplementary: the same two values swapped between the first- and second-iterated storage
    for (String variant : new String[] {"a", "b"}) {
      DatanodeStorageInfo s1 = newStorage();
      DatanodeDescriptor dn = s1.getDatanodeDescriptor();
      DatanodeStorageInfo s2 = dn.updateStorage(new DatanodeStorage("s2"));
      DatanodeStorageInfo[] order = dn.getStorageInfos();
      long r1 = variant.equals("a") ? 4096 : 1000;
      long r2 = variant.equals("a") ? 1000 : 4096;
      s1.setUtilizationForTesting(1L << 20, (1L << 20) - r1, r1, (1L << 20) - r1);
      s2.setUtilizationForTesting(1L << 20, (1L << 20) - r2, r2, (1L << 20) - r2);
      out("U1d" + variant + ",iterationOrder=" + sid(order[0]) + "|" + sid(order[1])
          + ",s1.r=" + r1 + ",s2.r=" + r2 + ",result="
          + sid(dn.chooseStorage4Block(StorageType.DISK, 1024, 4)));
    }
  }

  // ---------------- U2: MiniDFSCluster, real block files -----------------------------------------

  static Configuration conf(int n, boolean dnHeadroomZero) {
    Configuration conf = new Configuration();
    conf.setLong(DFSConfigKeys.DFS_BLOCK_SIZE_KEY, B);
    conf.setInt(DFSConfigKeys.DFS_REPLICATION_KEY, 1);
    if (dnHeadroomZero) {
      conf.setLong(DFSConfigKeys
          .DFS_DATANODE_ROUND_ROBIN_VOLUME_CHOOSING_POLICY_ADDITIONAL_AVAILABLE_SPACE_KEY, 0L);
    }
    conf.setBoolean(DFSConfigKeys.DFS_NAMENODE_REDUNDANCY_CONSIDERLOAD_KEY, false);
    conf.setLong(DFSConfigKeys.DFS_HEARTBEAT_INTERVAL_KEY, 1L);
    conf.setInt(KEY, n);
    return conf;
  }

  static final class Ctx {
    MiniDFSCluster cluster;
    FileSystem fs;
    DataNode dn;
    DatanodeDescriptor nnDesc;
    FsVolumeImpl vol;
    String tag;
  }

  static Ctx start(Configuration conf, String tag, boolean dnHeadroomZero) throws Exception {
    Ctx c = new Ctx();
    c.tag = tag;
    MiniDFSCluster.Builder b = new MiniDFSCluster.Builder(conf).numDataNodes(1)
        .storagesPerDatanode(1).storageCapacities(new long[][] {{C}});
    // the Builder constructor sets additional-available-space = 0 (MiniDFSCluster.java:551-553)
    conf.setLong(DFSConfigKeys
        .DFS_DATANODE_ROUND_ROBIN_VOLUME_CHOOSING_POLICY_ADDITIONAL_AVAILABLE_SPACE_KEY,
        dnHeadroomZero ? 0L : DFSConfigKeys
            .DFS_DATANODE_ROUND_ROBIN_VOLUME_CHOOSING_POLICY_ADDITIONAL_AVAILABLE_SPACE_DEFAULT);
    c.cluster = b.build();
    c.cluster.waitActive();
    c.fs = c.cluster.getFileSystem();
    c.dn = c.cluster.getDataNodes().get(0);
    c.nnDesc = c.cluster.getNamesystem().getBlockManager().getDatanodeManager()
        .getDatanode(c.dn.getDatanodeId());
    try (FsDatasetSpi.FsVolumeReferences refs = c.dn.getFSDataset().getFsVolumeReferences()) {
      c.vol = (FsVolumeImpl) refs.get(0);
    }
    sync(c);
    out(tag + ",start,N=" + conf.getInt(KEY, -1) + ",additionalAvailableSpace=" + conf.getLong(
        DFSConfigKeys.DFS_DATANODE_ROUND_ROBIN_VOLUME_CHOOSING_POLICY_ADDITIONAL_AVAILABLE_SPACE_KEY,
        -1) + ",capacity=" + c.vol.getCapacity()
        + ",d0(dfsUsed)=" + c.vol.getDfsUsed() + ",available=" + c.vol.getAvailable()
        + ",nnRemaining=" + c.nnDesc.getRemaining() + ",volDir=" + new File(c.vol.getBaseURI()));
    return c;
  }

  static void sync(Ctx c) throws Exception {
    DataNodeTestUtils.triggerHeartbeat(c.dn);
    GenericTestUtils.waitFor(() -> {
      try {
        return c.nnDesc.getRemaining() == c.vol.getAvailable();
      } catch (IOException e) {
        return false;
      }
    }, 100, 10000);
  }

  /** One full block of B bytes, replication 1, block size B; closes the file. */
  static void writeOneBlock(FileSystem fs, Path p, long seed) throws IOException {
    byte[] buf = new byte[(int) B];
    new java.util.Random(seed).nextBytes(buf);
    org.apache.hadoop.fs.FSDataOutputStream o = fs.create(p, true, 4096, (short) 1, B);
    try {
      o.write(buf);
      o.close();
    } catch (IOException e) {
      try {
        o.close();
      } catch (Exception ignored) {
        // the same failure again
      }
      throw e;
    }
  }

  /** Writes one-block files from index i0 on until the first IOException; returns the next index. */
  static int fill(Ctx c, int i0, String phase) throws Exception {
    out("header," + c.tag + ",phase,i,result,nnRemaining,volDfsUsed,volAvailable,blocksScheduled,msg");
    int i = i0;
    while (true) {
      long remBefore = c.nnDesc.getRemaining();
      try {
        writeOneBlock(c.fs, new Path("/fill/f" + i), i);
      } catch (IOException e) {
        String msg = String.valueOf(e.getMessage()).replace('\n', ' ').replace(',', ';');
        out(c.tag + "," + phase + "," + i + ",REFUSED," + remBefore + "," + c.vol.getDfsUsed()
            + "," + c.vol.getAvailable() + "," + c.nnDesc.getBlocksScheduled(StorageType.DISK)
            + "," + msg);
        return i;
      }
      sync(c);
      out(c.tag + "," + phase + "," + i + ",OK," + c.nnDesc.getRemaining() + ","
          + c.vol.getDfsUsed() + "," + c.vol.getAvailable() + ","
          + c.nnDesc.getBlocksScheduled(StorageType.DISK) + ",");
      i++;
      if (i > 200) {
        out(c.tag + "," + phase + ",STOP,i>200 without refusal");
        return i;
      }
    }
  }

  static void finish(Ctx c, int total) throws IOException {
    File dir = new File(c.vol.getBaseURI());
    List<File> blk = new ArrayList<>();
    for (File f : FileUtils.listFiles(dir, null, true)) {
      if (f.getName().startsWith("blk_") && !f.getName().endsWith(".meta")) {
        blk.add(f);
      }
    }
    out(c.tag + ",end,K=" + total + ",volDirBytes=" + FileUtils.sizeOfDirectory(dir)
        + ",blkFiles=" + blk.size() + ",volDfsUsed=" + c.vol.getDfsUsed()
        + ",volAvailable=" + c.vol.getAvailable() + ",nnRemaining=" + c.nnDesc.getRemaining());
  }

  static void u2Fill(int n) throws Exception {
    Ctx c = null;
    try {
      c = start(conf(n, true), "U2N" + n, true);
      int next = fill(c, 1, "fill");
      finish(c, next - 1);
    } finally {
      if (c != null && c.cluster != null) {
        c.cluster.shutdown();
      }
    }
  }

  @Test public void u2FillN1() throws Exception { u2Fill(1); }
  @Test public void u2FillN4() throws Exception { u2Fill(4); }
  @Test public void u2FillN8() throws Exception { u2Fill(8); }
  @Test public void u2FillN16() throws Exception { u2Fill(16); }

  @Test
  public void u2Reconfigure() throws Exception {
    Ctx c = null;
    try {
      c = start(conf(16, true), "U2R", true);
      int next = fill(c, 1, "N16");
      out("U2R,refusedAtN16,K1=" + (next - 1));
      c.cluster.getNameNode().reconfigureProperty(KEY, "1");
      out("U2R,reconfigured,N=" + c.cluster.getNameNode().getConf().get(KEY)
          + ",policyN=" + ((BlockPlacementPolicyDefault) c.cluster.getNamesystem().getBlockManager()
          .getBlockPlacementPolicy()).getMinBlocksForWrite());
      int next2 = fill(c, next + 1, "N1"); // f<next> was refused (no block); continue with a new name
      finish(c, (next - 1) + (next2 - (next + 1)));
    } finally {
      if (c != null && c.cluster != null) {
        c.cluster.shutdown();
      }
    }
  }

  /** B2h side control: DataNode headroom left at its 1 GiB default with C = 32 MiB; expect K = 0. */
  @Test
  public void u2DnSideControl() throws Exception {
    Ctx c = null;
    try {
      c = start(conf(1, false), "U2DN", false);
      int next = fill(c, 1, "fill");
      finish(c, next - 1);
    } finally {
      if (c != null && c.cluster != null) {
        c.cluster.shutdown();
      }
    }
  }
}
