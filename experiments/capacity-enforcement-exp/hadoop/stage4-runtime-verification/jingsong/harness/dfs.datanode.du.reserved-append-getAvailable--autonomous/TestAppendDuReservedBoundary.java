/*
 * Stage-4 unit tier (B2, as amended D1-1..D1-3 and D2-1, 2026-11-25) for
 * dfs.datanode.du.reserved-append-getAvailable--autonomous (queue order 28, Jingsong).
 * Lives only in the per-case source copy, never in the repository's systems/hadoop/source.
 * Prints readings as lines starting "O28," and asserts B2e step 5 per row:
 *   (append refused with DiskOutOfSpaceException) == (A < B - L).
 * System properties: o28.base = MiniDFSCluster base dir on the ext2 image,
 *                    o28.snap = snapshot dir (off the image).
 */
package org.apache.hadoop.hdfs.server.datanode.fsdataset.impl;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.FSDataOutputStream;
import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.hdfs.DFSTestUtil;
import org.apache.hadoop.hdfs.MiniDFSCluster;
import org.apache.hadoop.hdfs.protocol.ExtendedBlock;
import org.apache.hadoop.hdfs.server.datanode.DataNode;
import org.apache.hadoop.hdfs.server.datanode.DataNodeTestUtils;
import org.apache.hadoop.hdfs.server.datanode.ReplicaHandler;
import org.apache.hadoop.hdfs.server.datanode.fsdataset.FsDatasetSpi;
import org.apache.hadoop.util.DiskChecker.DiskOutOfSpaceException;
import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.FixMethodOrder;
import org.junit.Test;
import org.junit.runners.MethodSorters;

@FixMethodOrder(MethodSorters.NAME_ASCENDING)
public class TestAppendDuReservedBoundary {
  static final long KIB = 1024L, MIB = 1048576L;
  static final long B = 16 * MIB;   // block size
  static final long L = 1 * MIB;    // seeded replica length
  static final long C = 1 * MIB;    // appended chunk (client path)
  static final long NEED = B - L;   // 15728640
  static final Path P = new Path("/t/f1");
  static final String BASE = System.getProperty("o28.base");
  static final String SNAP = System.getProperty("o28.snap");
  static long T = -1, D = -1;
  static final List<String> SUMMARY = new ArrayList<>();

  static void out(String s) {
    System.out.println("O28," + s);
    System.out.flush();
  }

  static Configuration conf(long r) {
    Configuration c = new Configuration();
    c.setLong("dfs.datanode.du.reserved", r);
    c.setLong("fs.du.interval", 500);
    c.setLong("fs.getspaceused.jitterMillis", 0);
    c.setLong("dfs.datanode.cached-dfsused.check.interval.ms", 0);
    c.setLong("dfs.blocksize", B);
    c.setInt("dfs.replication", 1);
    c.setInt("dfs.datanode.scan.period.hours", -1);
    return c;
  }

  static FsVolumeImpl volume(MiniDFSCluster cluster) throws IOException {
    DataNode dn = cluster.getDataNodes().get(0);
    FsDatasetSpi<?> ds = DataNodeTestUtils.getFSDataset(dn);
    try (FsDatasetSpi.FsVolumeReferences refs = ds.getFsVolumeReferences()) {
      Assert.assertEquals("one volume", 1, refs.size());
      return (FsVolumeImpl) refs.get(0);
    }
  }

  static String vol(FsVolumeImpl v) throws IOException {
    long cap = v.getCapacity(), used = v.getDfsUsed(), rfr = v.getReservedForReplicas();
    long res = v.getReserved(), dfAvail = v.getDfAvailable();
    long dfUsed = v.getDfUsed();
    long nonDfs = dfUsed - used;
    return "capacity=" + cap + ",dfsUsed=" + used + ",reservedForReplicas=" + rfr + ",reserved="
        + res + ",dfAvailable=" + dfAvail + ",dfUsed=" + dfUsed + ",nonDfsDerived=" + nonDfs
        + ",available=" + v.getAvailable();
  }

  static String replicaWhere(long blockId) {
    List<File> hits = new ArrayList<>();
    find(new File(BASE), "blk_" + blockId, hits);
    StringBuilder sb = new StringBuilder();
    for (File f : hits) {
      String p = f.getPath();
      String dir = p.contains("/finalized/") ? "finalized" : p.contains("/rbw/") ? "rbw" : "other";
      sb.append(dir).append(":").append(f.length()).append(";");
    }
    return hits.isEmpty() ? "none" : sb.toString();
  }

  static void find(File d, String name, List<File> hits) {
    File[] fs = d.listFiles();
    if (fs == null) {
      return;
    }
    for (File f : fs) {
      if (f.isDirectory()) {
        find(f, name, hits);
      } else if (f.getName().equals(name)) {
        hits.add(f);
      }
    }
  }

  static void sh(String... cmd) throws Exception {
    Process p = new ProcessBuilder(cmd).inheritIO().start();
    int rc = p.waitFor();
    out("sh," + String.join(" ", cmd) + ",rc=" + rc);
    Assert.assertEquals("command failed: " + String.join(" ", cmd), 0, rc);
  }

  static MiniDFSCluster start(long r) throws Exception {
    sh("rsync", "-a", "--delete", SNAP + "/", BASE + "/");
    MiniDFSCluster c = new MiniDFSCluster.Builder(conf(r), new File(BASE)).format(false)
        .numDataNodes(1).storagesPerDatanode(1).build();
    c.waitActive();
    // amendment D2-1: wait for the DataNode's block report before getFirstBlock reads the file
    DFSTestUtil.waitReplication(c.getFileSystem(), P, (short) 1);
    out("started,R=" + r + ",blockReported=true");
    return c;
  }

  @BeforeClass
  public static void calibrate() throws Exception {
    Assert.assertNotNull("o28.base", BASE);
    Assert.assertNotNull("o28.snap", SNAP);
    out("jvm,maxHeap=" + Runtime.getRuntime().maxMemory() + ",B=" + B + ",L=" + L + ",need=" + NEED);
    sh("rm", "-rf", BASE, SNAP);
    sh("mkdir", "-p", BASE, SNAP);
    MiniDFSCluster c = new MiniDFSCluster.Builder(conf(0), new File(BASE)).numDataNodes(1)
        .storagesPerDatanode(1).build();
    try {
      c.waitActive();
      FileSystem fs = c.getFileSystem();
      try (FSDataOutputStream o = fs.create(P, true, 4096, (short) 1, B)) {
        o.write(new byte[(int) L]);
      }
      Thread.sleep(1500);
      FsVolumeImpl v = volume(c);
      T = v.getCapacity();
      D = v.getDfsUsed();
      ExtendedBlock eb = DFSTestUtil.getFirstBlock(fs, P);
      out("calib,T=" + T + ",D=" + D + ",len=" + fs.getFileStatus(P).getLen() + ",block=" + eb
          + ",where=" + replicaWhere(eb.getBlockId()) + "," + vol(v));
    } finally {
      c.shutdown(false);
    }
    sh("rsync", "-a", "--delete", BASE + "/", SNAP + "/");
  }

  /** δ in bytes; Long.MIN_VALUE = control R = 0. */
  static long reserveFor(long delta) {
    return delta == Long.MIN_VALUE ? 0 : T - D - NEED - delta;
  }

  void datasetAppend(String label, long delta) throws Exception {
    long r = reserveFor(delta);
    MiniDFSCluster c = start(r);
    try {
      FileSystem fs = c.getFileSystem();
      FsVolumeImpl v = volume(c);
      FsDatasetSpi<?> ds = DataNodeTestUtils.getFSDataset(c.getDataNodes().get(0));
      ExtendedBlock eb = DFSTestUtil.getFirstBlock(fs, P);
      ExtendedBlock req = new ExtendedBlock(eb);
      req.setNumBytes(B);
      out(label + ",pre,R=" + r + ",delta=" + delta + ",block=" + eb + ",where="
          + replicaWhere(eb.getBlockId()) + "," + vol(v));
      long a = v.getAvailable();
      String outcome;
      String msg = "";
      boolean refused;
      try {
        ReplicaHandler h = ds.append(req, eb.getGenerationStamp() + 1, L);
        outcome = "handler";
        refused = false;
        long aAfter = v.getAvailable();
        out(label + ",post,A=" + a + ",outcome=" + outcome + ",A_after=" + aAfter + ",drop="
            + (a - aAfter) + ",where=" + replicaWhere(eb.getBlockId()) + "," + vol(v));
        h.close();
      } catch (DiskOutOfSpaceException e) {
        outcome = "DiskOutOfSpaceException";
        msg = e.getMessage();
        refused = true;
        long aAfter = v.getAvailable();
        out(label + ",post,A=" + a + ",outcome=" + outcome + ",A_after=" + aAfter + ",drop="
            + (a - aAfter) + ",where=" + replicaWhere(eb.getBlockId()) + "," + vol(v)
            + ",msg=" + msg.replace(',', ';'));
      }
      boolean pred = a < NEED;
      String line = label + ",summary,R=" + r + ",A=" + a + ",A-(15MiB+delta)="
          + (delta == Long.MIN_VALUE ? "n/a" : String.valueOf(a - (NEED + delta)))
          + ",refused=" + refused + ",predRefused(A<B-L)=" + pred + ",match=" + (refused == pred);
      out(line);
      SUMMARY.add(line);
      Assert.assertEquals("B2e step 5: refused == (A < B - L) for " + label, pred, refused);
    } finally {
      c.shutdown(false);
    }
  }

  void clientAppend(String label, long delta) throws Exception {
    long r = reserveFor(delta);
    MiniDFSCluster c = start(r);
    try {
      FileSystem fs = c.getFileSystem();
      FsVolumeImpl v = volume(c);
      ExtendedBlock eb = DFSTestUtil.getFirstBlock(fs, P);
      out(label + ",pre,R=" + r + ",delta=" + delta + ",where=" + replicaWhere(eb.getBlockId())
          + "," + vol(v));
      long a = v.getAvailable();
      boolean refused = false;
      String msg = "";
      out(label + ",appendStart,A=" + a);
      FSDataOutputStream o = null;
      try {
        o = fs.append(P);
        o.write(new byte[(int) C]);
        o.hflush();
        o.close();
        o = null;
      } catch (IOException e) {
        refused = true;
        msg = e.toString();
        if (o != null) {
          try {
            o.close();
          } catch (IOException e2) {
            out(label + ",closeAfterFailure," + e2.toString().replace(',', ';'));
          }
        }
      }
      out(label + ",appendEnd");
      Thread.sleep(1000);
      long len = fs.getFileStatus(P).getLen();
      out(label + ",post,A=" + a + ",refused=" + refused + ",fileLen=" + len + ",where="
          + replicaWhere(eb.getBlockId()) + "," + vol(v) + ",msg=" + msg.replace(',', ';'));
      boolean pred = a < NEED;
      String line = label + ",summary,R=" + r + ",A=" + a + ",A-(15MiB+delta)="
          + (a - (NEED + delta)) + ",refused=" + refused + ",predRefused(A<B-L)=" + pred
          + ",fileLen=" + len + ",match=" + (refused == pred);
      out(line);
      SUMMARY.add(line);
      Assert.assertEquals("B2e step 5 (client path): refused == (A < B - L) for " + label, pred,
          refused);
    } finally {
      c.shutdown(false);
    }
  }

  @Test public void t1Control() throws Exception { datasetAppend("ctrlR0", Long.MIN_VALUE); }
  @Test public void t2DeltaMinus4M() throws Exception { datasetAppend("dM4M", -4 * MIB); }
  @Test public void t3DeltaMinus256K() throws Exception { datasetAppend("dM256K", -256 * KIB); }
  @Test public void t4DeltaPlus256K() throws Exception { datasetAppend("dP256K", 256 * KIB); }
  @Test public void t5DeltaPlus4M() throws Exception { datasetAppend("dP4M", 4 * MIB); }
  @Test public void t6ClientAppendMinus4M() throws Exception { clientAppend("cliM4M", -4 * MIB); }
  @Test public void t7ClientAppendPlus4M() throws Exception { clientAppend("cliP4M", 4 * MIB); }

  @AfterClass
  public static void report() {
    for (String s : SUMMARY) {
      out("final," + s);
    }
  }
}
