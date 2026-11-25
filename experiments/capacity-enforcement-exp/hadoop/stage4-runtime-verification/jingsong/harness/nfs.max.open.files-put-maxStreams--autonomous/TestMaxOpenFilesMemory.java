/*
 * Stage-4 instrument (capacity-enforcement-exp, Hadoop, Jingsong) for case
 * nfs.max.open.files-put-maxStreams--autonomous, unit tier B2 (with the audit amendments of 2026-11-25).
 * Not upstream. Copied into hadoop-hdfs-nfs/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3/ of a per-run copy.
 *
 * One test method per K (fresh MiniDFSCluster each). M files are CREATEd back to back (phase 1), then one
 * out-of-order UNSTABLE WRITE of CHUNK bytes at offset 1 MiB is sent to each (phase 2). Readings are printed
 * as "ROW ..." lines; WRITE statuses are captured through a Netty EmbeddedChannel (amendment 2026-11-25:
 * with a null channel the JUKEBOX reply is not visible).
 */
package org.apache.hadoop.hdfs.nfs.nfs3;

import io.netty.buffer.ByteBuf;
import io.netty.channel.embedded.EmbeddedChannel;
import java.io.File;
import java.lang.management.ManagementFactory;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.apache.hadoop.fs.FileUtil;
import org.apache.hadoop.hdfs.DFSClient;
import org.apache.hadoop.hdfs.DFSUtilClient;
import org.apache.hadoop.hdfs.MiniDFSCluster;
import org.apache.hadoop.hdfs.nfs.conf.NfsConfigKeys;
import org.apache.hadoop.hdfs.nfs.conf.NfsConfiguration;
import org.apache.hadoop.hdfs.protocol.HdfsFileStatus;
import org.apache.hadoop.nfs.nfs3.FileHandle;
import org.apache.hadoop.nfs.nfs3.Nfs3Constant;
import org.apache.hadoop.nfs.nfs3.Nfs3Constant.WriteStableHow;
import org.apache.hadoop.nfs.nfs3.Nfs3Status;
import org.apache.hadoop.nfs.nfs3.request.CREATE3Request;
import org.apache.hadoop.nfs.nfs3.request.SetAttr3;
import org.apache.hadoop.nfs.nfs3.request.WRITE3Request;
import org.apache.hadoop.nfs.nfs3.response.CREATE3Response;
import org.apache.hadoop.nfs.nfs3.response.WRITE3Response;
import org.apache.hadoop.oncrpc.RpcReply;
import org.apache.hadoop.oncrpc.XDR;
import org.apache.hadoop.oncrpc.security.SecurityHandler;
import org.apache.hadoop.security.authorize.DefaultImpersonationProvider;
import org.apache.hadoop.security.authorize.ProxyUsers;
import org.apache.log4j.AppenderSkeleton;
import org.apache.log4j.Level;
import org.apache.log4j.spi.LoggingEvent;
import org.junit.FixMethodOrder;
import org.junit.Test;
import org.junit.runners.MethodSorters;
import org.mockito.Mockito;

@FixMethodOrder(MethodSorters.NAME_ASCENDING)
public class TestMaxOpenFilesMemory {
  static final int M = 64;
  static final long OFFSET = 1048576L;
  static final int CHUNK = 983040;
  static final String STREAMER_PREFIX = "DataStreamer for file /.reserved/.inodes/";

  static final AtomicInteger cantAddNew = new AtomicInteger();   // WriteManager (WRITE path)
  static final AtomicInteger cantAddMore = new AtomicInteger();  // RpcProgramNfs3 (CREATE path)
  static final AtomicInteger busyWarn = new AtomicInteger();     // OpenFileCtxCache "All opened streams are busy"
  static final AtomicInteger noCandWarn = new AtomicInteger();   // OpenFileCtxCache "No eviction candidate"
  static final AtomicInteger evictDebug = new AtomicInteger();   // "Evict stream ctx" (debug)
  static final AtomicInteger maxStreamsLine = new AtomicInteger(-1);
  static boolean appenderAdded = false;

  static synchronized void addAppender() {
    if (appenderAdded) {
      return;
    }
    org.apache.log4j.Logger.getLogger(WriteManager.class).setLevel(Level.INFO);
    org.apache.log4j.Logger.getLogger(RpcProgramNfs3.class).setLevel(Level.INFO);
    org.apache.log4j.Logger.getLogger(OpenFileCtxCache.class).setLevel(Level.DEBUG);
    org.apache.log4j.Logger.getRootLogger().addAppender(new AppenderSkeleton() {
      @Override
      protected void append(LoggingEvent e) {
        String m = String.valueOf(e.getMessage());
        if (m.startsWith("Can't add new stream")) {
          cantAddNew.incrementAndGet();
        } else if (m.startsWith("Can't add more stream")) {
          cantAddMore.incrementAndGet();
        } else if (m.startsWith("All opened streams are busy")) {
          busyWarn.incrementAndGet();
        } else if (m.startsWith("No eviction candidate")) {
          noCandWarn.incrementAndGet();
        } else if (m.startsWith("Evict stream ctx")) {
          evictDebug.incrementAndGet();
        } else if (m.startsWith("Maximum open streams is ")) {
          try {
            maxStreamsLine.set(Integer.parseInt(m.substring(24).trim()));
          } catch (NumberFormatException ignored) {
          }
        }
      }

      @Override
      public void close() {
      }

      @Override
      public boolean requiresLayout() {
        return false;
      }
    });
    appenderAdded = true;
  }

  static long heapAfterGc() throws InterruptedException {
    for (int i = 0; i < 3; i++) {
      System.gc();
      Thread.sleep(200);
    }
    return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
  }

  static int streamerThreads() {
    int n = 0;
    for (Thread t : Thread.getAllStackTraces().keySet()) {
      // Fix of 2026-11-25 (runbook defect 3): a DataStreamer thread is named "DataStreamer for file ..." only once a
      // block pipeline exists (DataStreamer.java:664 initDataStreaming, :680 endBlock); before that it keeps the
      // default "Thread-N" name. Count live threads of class org.apache.hadoop.hdfs.DataStreamer instead.
      if (t.isAlive() && t.getClass().getName().equals("org.apache.hadoop.hdfs.DataStreamer")) {
        n++;
      }
    }
    return n;
  }

  /** Fix of 2026-11-25 (runbook defect 3): every thread whose name contains "DataStreamer", with sample names. */
  static String streamerDiag() {
    int n = 0;
    java.util.TreeSet<String> names = new java.util.TreeSet<String>();
    for (Thread t : Thread.getAllStackTraces().keySet()) {
      if (t.isAlive() && t.getName().startsWith(STREAMER_PREFIX)) {
        n++;
        names.add(t.getName());
      }
    }
    StringBuilder sb = new StringBuilder("namedPrefix=" + n + " sample=[");
    int i = 0;
    for (String s : names) {
      if (i++ == 3) {
        break;
      }
      sb.append(s).append("; ");
    }
    return sb.append("]").toString();
  }

  static int countFiles(File d) {
    if (d == null || !d.exists()) {
      return 0;
    }
    if (d.isFile()) {
      return 1;
    }
    int n = 0;
    File[] fs = d.listFiles();
    if (fs != null) {
      for (File f : fs) {
        n += countFiles(f);
      }
    }
    return n;
  }

  static int replyStatus(EmbeddedChannel ch) {
    Object o = ch.readOutbound();
    if (o == null) {
      return -1; // no reply written
    }
    ByteBuf b = (ByteBuf) o;
    byte[] all = new byte[b.readableBytes()];
    b.readBytes(all);
    b.release();
    XDR x = new XDR(Arrays.copyOfRange(all, 4, all.length));
    RpcReply.read(x);
    return x.readInt();
  }

  @Test
  public void testA_K8() throws Exception {
    run("K8", 8, CHUNK);
  }

  @Test
  public void testB_K32() throws Exception {
    run("K32", 32, CHUNK);
  }

  @Test
  public void testC_K128() throws Exception {
    run("K128", 128, CHUNK);
  }

  @Test
  public void testD_Kdefault() throws Exception {
    run("Kdefault", -1, CHUNK); // key unset: the Java default, 256
  }

  @Test
  public void testE_K8null() throws Exception {
    run("K8null", 8, 1); // overhead-only control (1-byte payload)
  }

  void run(String label, int k, int chunk) throws Exception {
    addAppender();
    cantAddNew.set(0);
    cantAddMore.set(0);
    busyWarn.set(0);
    noCandWarn.set(0);
    evictDebug.set(0);
    maxStreamsLine.set(-1);

    NfsConfiguration config = new NfsConfiguration();
    String user = System.getProperty("user.name");
    config.set(DefaultImpersonationProvider.getTestProvider().getProxySuperuserGroupConfKey(user), "*");
    config.set(DefaultImpersonationProvider.getTestProvider().getProxySuperuserIpConfKey(user), "*");
    ProxyUsers.refreshSuperUserGroupsConfiguration(config);
    if (k >= 0) {
      config.setInt(NfsConfigKeys.DFS_NFS_MAX_OPEN_FILES_KEY, k);
    }
    File dump = new File(System.getProperty("test.build.data", "target/test/data"), "nfsdump-" + label);
    FileUtil.fullyDelete(dump);
    config.set(NfsConfigKeys.DFS_NFS_FILE_DUMP_DIR_KEY, dump.getAbsolutePath());
    config.setLong(NfsConfigKeys.DFS_NFS_STREAM_TIMEOUT_KEY, 600000L);
    config.setInt("nfs3.mountd.port", 0);
    config.setInt("nfs3.server.port", 0);

    SecurityHandler sh = Mockito.mock(SecurityHandler.class);
    Mockito.when(sh.getUser()).thenReturn(user);
    InetSocketAddress addr = new InetSocketAddress("localhost", 1234);

    MiniDFSCluster cluster = null;
    Nfs3 nfs3 = null;
    try {
      cluster = new MiniDFSCluster.Builder(config).numDataNodes(1).build();
      cluster.waitActive();
      DFSClient client = new DFSClient(DFSUtilClient.getNNAddress(config), config);
      int nnId = Nfs3Utils.getNamenodeId(config);
      nfs3 = new Nfs3(config);
      nfs3.startServiceInternal(false);
      RpcProgramNfs3 nfsd = (RpcProgramNfs3) nfs3.getRpcProgram();
      OpenFileCtxCache cache = nfsd.getWriteManager().getOpenFileCtxCache();
      HdfsFileStatus st = client.getFileInfo("/");
      FileHandle root = new FileHandle(st.getFileId(), nnId);

      int streamersBefore1 = streamerThreads();
      long heap0 = heapAfterGc();
      int maxSize = cache.size();

      // Phase 1: M CREATEs back to back
      List<FileHandle> handles = new ArrayList<FileHandle>();
      int createOk = 0;
      int createCached = 0;
      long t1 = System.nanoTime();
      for (int i = 0; i < M; i++) {
        CREATE3Request req = new CREATE3Request(root, "f" + i, Nfs3Constant.CREATE_UNCHECKED, new SetAttr3(), 0);
        XDR x = new XDR();
        req.serialize(x);
        CREATE3Response rsp = nfsd.create(x.asReadOnlyWrap(), sh, addr);
        if (rsp.getStatus() == Nfs3Status.NFS3_OK) {
          createOk++;
        }
        FileHandle h = rsp.getObjHandle();
        handles.add(h);
        if (h != null && cache.get(h) != null) {
          createCached++;
        }
        maxSize = Math.max(maxSize, cache.size());
      }
      double phase1Sec = (System.nanoTime() - t1) / 1e9;
      int sizeAfter1 = cache.size();
      int streamersAfter1 = streamerThreads();
      System.out.println("STREAMERS " + label + " afterPhase1 " + streamerDiag());
      int cantMoreAfter1 = cantAddMore.get();

      long heap1 = heapAfterGc();

      // Phase 2: one out-of-order UNSTABLE write per file
      int wOk = 0;
      int wJukebox = 0;
      int wOther = 0;
      int wNoReply = 0;
      long t2 = System.nanoTime();
      for (int i = 0; i < M; i++) {
        FileHandle h = handles.get(i);
        WRITE3Request req = new WRITE3Request(h, OFFSET, chunk, WriteStableHow.UNSTABLE,
            ByteBuffer.wrap(new byte[chunk]));
        XDR x = new XDR();
        req.serialize(x);
        req = null;
        EmbeddedChannel ch = new EmbeddedChannel();
        WRITE3Response direct = nfsd.write(x.asReadOnlyWrap(), ch, 1000 + i, sh, addr);
        x = null;
        int s = direct != null ? direct.getStatus() : replyStatus(ch);
        if (s == Nfs3Status.NFS3_OK) {
          wOk++;
        } else if (s == Nfs3Status.NFS3ERR_JUKEBOX) {
          wJukebox++;
        } else if (s == -1) {
          wNoReply++;
        } else {
          wOther++;
          System.out.println("WSTATUS " + label + " file=f" + i + " status=" + s);
        }
        maxSize = Math.max(maxSize, cache.size());
      }
      double phase2Sec = (System.nanoTime() - t2) / 1e9;
      Thread.sleep(2000);

      int cached = 0;
      long pendingBytes = 0;
      int pendingWrites = 0;
      int withPendingWork = 0;
      for (FileHandle h : handles) {
        OpenFileCtx ctx = h == null ? null : cache.get(h);
        if (ctx != null) {
          cached++;
          if (ctx.hasPendingWork()) {
            withPendingWork++;
          }
          for (WriteCtx w : ctx.getPendingWritesForTest().values()) {
            pendingWrites++;
            pendingBytes += w.getCount();
          }
        }
      }
      int streamersAfter2 = streamerThreads();
      System.out.println("STREAMERS " + label + " afterPhase2 " + streamerDiag());
      int sizeAfter2 = cache.size();
      long heap2 = heapAfterGc();
      int dumpFiles = countFiles(dump);

      System.out.println("ROW label=" + label + " K=" + (k >= 0 ? k : "unset") + " logMaxStreams="
          + maxStreamsLine.get() + " M=" + M + " chunk=" + chunk
          + " maxSize=" + maxSize + " sizeAfter1=" + sizeAfter1 + " sizeAfter2=" + sizeAfter2
          + " createOk=" + createOk + " createCached=" + createCached
          + " cantAddMore=" + cantMoreAfter1 + "/" + cantAddMore.get()
          + " cantAddNew=" + cantAddNew.get() + " busyWarn=" + busyWarn.get()
          + " noCandWarn=" + noCandWarn.get() + " evict=" + evictDebug.get()
          + " writeOk=" + wOk + " writeJukebox=" + wJukebox + " writeOther=" + wOther
          + " writeNoReply=" + wNoReply
          + " cached=" + cached + " withPendingWork=" + withPendingWork
          + " pendingWrites=" + pendingWrites + " pendingBytes=" + pendingBytes
          + " streamersBefore1=" + streamersBefore1 + " streamersAfter1=" + streamersAfter1
          + " streamersAfter2=" + streamersAfter2
          + " heap0=" + heap0 + " heap1=" + heap1 + " heap2=" + heap2
          + " heapDelta=" + (heap2 - heap1) + " heapDeltaMiB="
          + String.format("%.2f", (heap2 - heap1) / 1048576.0)
          + " streamHeapMiB=" + String.format("%.2f", (heap1 - heap0) / 1048576.0)
          + " dumpFiles=" + dumpFiles
          + " phase1Sec=" + String.format("%.2f", phase1Sec)
          + " phase2Sec=" + String.format("%.2f", phase2Sec));
    } finally {
      if (nfs3 != null) {
        nfs3.stop();
      }
      if (cluster != null) {
        cluster.shutdown();
      }
    }
  }
}
