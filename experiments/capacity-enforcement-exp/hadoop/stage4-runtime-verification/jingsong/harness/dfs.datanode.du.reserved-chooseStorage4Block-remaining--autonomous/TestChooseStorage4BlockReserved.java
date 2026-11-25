/*
 * Stage-4 unit tier (B2) for dfs.datanode.du.reserved-chooseStorage4Block-remaining--autonomous
 * (queue order 25, Jingsong). Lives only in the per-case source copy, never in the repository's
 * systems/hadoop/source. Prints readings (lines starting "O25,") and asserts only the U1 truth
 * table and the U2 preconditions (B2e 3.1-3.2); U2's counts are readings, compared offline.
 */
package org.apache.hadoop.hdfs.server.blockmanagement;

import java.io.File;
import java.io.IOException;
import java.lang.reflect.Method;
import java.util.Collection;

import org.apache.commons.io.FileUtils;
import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.FSDataOutputStream;
import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.fs.StorageType;
import org.apache.hadoop.hdfs.DFSConfigKeys;
import org.apache.hadoop.hdfs.DFSTestUtil;
import org.apache.hadoop.hdfs.MiniDFSCluster;
import org.apache.hadoop.hdfs.server.datanode.DataNode;
import org.apache.hadoop.hdfs.server.datanode.fsdataset.FsDatasetSpi;
import org.apache.hadoop.hdfs.server.datanode.fsdataset.impl.FsVolumeImpl;
import org.apache.hadoop.test.GenericTestUtils;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

public class TestChooseStorage4BlockReserved {
  static final String KEY_K = "dfs.namenode.block-placement.min-blocks-for.write";
  static final String KEY_RES = "dfs.datanode.du.reserved";
  static final String KEY_AAS =
      "dfs.datanode.round-robin-volume-choosing-policy.additional-available-space";
  static final long MIB = 1048576L;
  static final long B2 = 4L * MIB;          // U2 block size (B2b)
  static final long META = 7 + (B2 / 512) * 4; // CRC32C/512 meta length (B2c)
  static final long BPRIME = B2 + META;     // 4,227,079

  /** Amendment D2-1: the disallow branch is evidenced by the check's own DEBUG line
   *  (DatanodeDescriptor.java:834-837), logged by the NameNode's IPC handler threads. */
  @BeforeClass
  public static void debugPlacement() {
    org.apache.hadoop.test.GenericTestUtils.setLogLevel(BlockPlacementPolicy.LOG,
        org.slf4j.event.Level.DEBUG);
    out("thread," + Thread.currentThread().getName());
  }

  static void out(String s) {
    System.out.println("O25," + s);
    System.out.flush();
  }

  // ------------------------------- U1: the check alone ----------------------------------------
  @Test
  public void u1TruthTable() {
    final long b = 1024;
    int n = 0, mismatches = 0;
    out("U1header,k,s,R,registeredIsReturned,nnRemaining,sched,result,predNull,match");
    for (int k : new int[] {1, 3}) {
      for (int s = 0; s <= 2; s++) {
        for (long r : new long[] {k * b - 1, k * b, k * b + 1, (k + 1) * b, (k + 2) * b}) {
          DatanodeStorageInfo s0 = DFSTestUtil.createDatanodeStorageInfos(1)[0];
          DatanodeDescriptor dn = s0.getDatanodeDescriptor();
          // amendment D1-U1: the descriptor iterates its own registered storage object, which is
          // not the one createDatanodeStorageInfos returns; set utilization on the registered one.
          DatanodeStorageInfo st = dn.getStorageInfo(s0.getStorageID());
          st.setUtilizationForTesting(10 * b, 0, r, 0);
          dn.updateHeartbeat(BlockManagerTestUtil.getStorageReportsForDatanode(dn), 0, 0, 0, 0,
              null);
          for (int i = 0; i < s; i++) {
            dn.incrementBlocksScheduled(StorageType.DISK);
          }
          DatanodeStorageInfo res = dn.chooseStorage4Block(StorageType.DISK, b, k);
          boolean predNull = k * b > r - s * b;
          boolean match = (res == null) == predNull;
          n++;
          if (!match) {
            mismatches++;
          }
          out("U1," + k + "," + s + "," + r + "," + (s0 == st) + "," + st.getRemaining() + ","
              + dn.getBlocksScheduled(StorageType.DISK) + "," + (res == null ? "null" : "storage")
              + "," + predNull + "," + match);
        }
      }
    }
    out("U1summary,tuples=" + n + ",mismatches=" + mismatches);
    Assert.assertEquals("U1 truth table mismatches", 0, mismatches);
  }

  // ------------------------------- U2: real DataNode ------------------------------------------
  static final class Ctx {
    MiniDFSCluster cluster;
    FileSystem fs;
    DataNode dn;
    DatanodeDescriptor nnDesc;
    DatanodeStorageInfo nnStorage;
    FsVolumeImpl vol;
    long reservedSet;
    long tprime;
    long eps;
  }

  static long tPrime(File f) {
    return f.getTotalSpace() - (f.getFreeSpace() - f.getUsableSpace());
  }

  static long reservedOf(FsVolumeImpl v) throws Exception {
    Method m = FsVolumeImpl.class.getDeclaredMethod("getReserved"); // package-private (A: D1-U2)
    m.setAccessible(true);
    return (Long) m.invoke(v);
  }

  static long finalizedBytes(FsVolumeImpl v) {
    long sum = 0;
    File base = new File(v.getBaseURI());
    Collection<File> all = FileUtils.listFiles(base, null, true);
    for (File f : all) {
      if (f.getPath().contains(File.separator + "finalized" + File.separator)) {
        sum += f.length();
      }
    }
    return sum;
  }

  static long blockFileBytes(FsVolumeImpl v) {
    long sum = 0;
    for (File f : FileUtils.listFiles(new File(v.getBaseURI()), null, true)) {
      if (f.getName().startsWith("blk_") && !f.getName().endsWith(".meta")) {
        sum += f.length();
      }
    }
    return sum;
  }

  /** B2e 3.1-3.2: create baseDir, compute T', start; returns null (skip) if precondition fails. */
  static Ctx start(String tag, long h, int k, boolean aasZero) throws Exception {
    File base = new File(GenericTestUtils.getTestDir("o25"), tag); // under -Dtest.build.data
    FileUtils.deleteQuietly(base);
    Assert.assertTrue(base.mkdirs());
    long tp = tPrime(base);
    long nonHdfs = base.getTotalSpace() - base.getFreeSpace();
    long reserved = tp - h;
    out(tag + ",pre,H=" + h + ",k=" + k + ",aasZero=" + aasZero + ",Tprime=" + tp
        + ",DFused=" + nonHdfs + ",reserved=" + reserved + ",base=" + base.getAbsolutePath());
    if (!(reserved > nonHdfs)) {
      out(tag + ",SKIP,reserved<=nonHdfsUse");
      return null;
    }
    Configuration conf = new Configuration();
    conf.set(MiniDFSCluster.HDFS_MINIDFS_BASEDIR, base.getAbsolutePath());
    conf.setLong(KEY_RES, reserved);
    conf.setInt(KEY_K, k);
    conf.setLong(DFSConfigKeys.DFS_BLOCK_SIZE_KEY, B2);
    conf.setInt(DFSConfigKeys.DFS_REPLICATION_KEY, 1);
    conf.setLong(DFSConfigKeys.DFS_HEARTBEAT_INTERVAL_KEY, 1L);
    MiniDFSCluster.Builder bld = new MiniDFSCluster.Builder(conf).numDataNodes(1)
        .storagesPerDatanode(1);
    // The Builder constructor forces additional-available-space = 0 (MiniDFSCluster.java:551-553);
    // set it explicitly after it, so Control B really runs with the 1 GiB default.
    conf.setLong(KEY_AAS, aasZero ? 0L : 1024L * MIB);
    Ctx c = new Ctx();
    c.reservedSet = reserved;
    c.tprime = tp;
    c.cluster = bld.build();
    c.cluster.waitActive();
    c.fs = c.cluster.getFileSystem();
    c.dn = c.cluster.getDataNodes().get(0);
    c.nnDesc = c.cluster.getNamesystem().getBlockManager().getDatanodeManager()
        .getDatanode(c.dn.getDatanodeId());
    try (FsDatasetSpi.FsVolumeReferences refs = c.dn.getFSDataset().getFsVolumeReferences()) {
      c.vol = (FsVolumeImpl) refs.get(0);
    }
    Thread.sleep(2500);
    c.nnStorage = c.nnDesc.getStorageInfos()[0];
    c.eps = c.nnStorage.getDfsUsed();
    long rem = c.nnStorage.getRemaining();
    long volRes = reservedOf(c.vol);
    out(tag + ",start,eps=" + c.eps + ",volReserved=" + volRes + ",volCapacity="
        + c.vol.getCapacity() + ",volAvailable=" + c.vol.getAvailable() + ",nnRemaining=" + rem
        + ",H-eps=" + (h - c.eps) + ",diff=" + (rem - (h - c.eps)) + ",aasConf="
        + c.dn.getConf().getLong(KEY_AAS, -1) + ",kConf="
        + c.cluster.getNameNode().getConf().getInt(KEY_K, -1) + ",volDir=" + c.vol.getBaseURI());
    Assert.assertEquals("getReserved == T'-H", reserved, volRes);
    Assert.assertTrue("|remaining-(H-eps)| <= 1 MiB", Math.abs(rem - (h - c.eps)) <= MIB);
    return c;
  }

  static void writeOne(FileSystem fs, Path p, long seed) throws IOException {
    byte[] buf = new byte[(int) B2];
    new java.util.Random(seed).nextBytes(buf);
    FSDataOutputStream o = fs.create(p, true, 4096, (short) 1, B2);
    try {
      o.write(buf);
      o.close();
    } catch (IOException e) {
      try {
        o.close();
      } catch (Exception ignored) {
        // same failure
      }
      throw e;
    }
  }

  /** B2c/B2e step 3.3: one line per file; stops at two consecutive failures or maxFiles. */
  static int loop(Ctx c, String tag, long h, int k, int maxFiles) throws Exception {
    out(tag + "header,i,remaining,sched,pred,outcome,finalizedBytes,blockFileBytes,volDfsUsed,"
        + "volAvailable,leH,msg");
    int ok = 0, consecFail = 0, mismatches = 0, overH = 0;
    for (int i = 1; i <= maxFiles; i++) {
      Thread.sleep(2500);
      long rem = c.nnStorage.getRemaining();
      int sched = c.nnDesc.getBlocksScheduled(StorageType.DISK);
      boolean pred = c.nnDesc.chooseStorage4Block(StorageType.DISK, B2, k) != null;
      String outcome;
      String msg = "";
      try {
        writeOne(c.fs, new Path("/fill/f" + i), i);
        outcome = "OK";
        ok++;
        consecFail = 0;
      } catch (IOException e) {
        outcome = "FAIL";
        msg = String.valueOf(e.getMessage()).replace('\n', ' ').replace(',', ';');
        if (msg.length() > 300) {
          msg = msg.substring(0, 300);
        }
        consecFail++;
      }
      long fin = finalizedBytes(c.vol);
      boolean leH = fin <= h;
      if (!leH) {
        overH++;
      }
      if (pred != outcome.equals("OK")) {
        mismatches++;
      }
      out(tag + "," + i + "," + rem + "," + sched + "," + pred + "," + outcome + "," + fin + ","
          + blockFileBytes(c.vol) + "," + c.vol.getDfsUsed() + "," + c.vol.getAvailable() + ","
          + leH + "," + msg);
      if (consecFail >= 2) {
        break;
      }
    }
    long nPred = (h - c.eps - k * B2) / BPRIME + 1;
    out(tag + ",summary,H=" + h + ",k=" + k + ",eps=" + c.eps + ",successes=" + ok
        + ",N_pred(eps)=" + nPred + ",predMismatches=" + mismatches + ",filesOverH=" + overH
        + ",finalBytesEnd=" + finalizedBytes(c.vol) + ",nnRemainingEnd="
        + c.nnStorage.getRemaining());
    return ok;
  }

  static void u2(String tag, long h, int k, boolean aasZero, int maxFiles) throws Exception {
    Ctx c = null;
    try {
      c = start(tag, h, k, aasZero);
      if (c == null) {
        return;
      }
      c.fs.mkdirs(new Path("/fill"));
      loop(c, tag, h, k, maxFiles);
    } finally {
      if (c != null && c.cluster != null) {
        c.cluster.shutdown();
      }
      out(tag + ",shutdown");
    }
  }

  @Test public void u2H32k1() throws Exception { u2("U2_H32_k1", 32 * MIB, 1, true, 40); }
  @Test public void u2H32k3() throws Exception { u2("U2_H32_k3", 32 * MIB, 3, true, 40); }
  @Test public void u2H64k1() throws Exception { u2("U2_H64_k1", 64 * MIB, 1, true, 40); }
  @Test public void u2H64k3() throws Exception { u2("U2_H64_k3", 64 * MIB, 3, true, 40); }
  /** Control A (B2h): cap far away, 40 files of 4 MiB should all succeed. */
  @Test public void u2CtlA() throws Exception { u2("U2_CtlA_H512", 512 * MIB, 1, true, 40); }
  /** Control B (B2h): DataNode headroom gate left at its 1 GiB default. */
  @Test public void u2CtlB() throws Exception { u2("U2_CtlB_H64", 64 * MIB, 1, false, 40); }
}
