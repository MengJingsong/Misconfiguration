package org.apache.hadoop.hdfs.nfs.nfs3;

import static org.junit.Assert.assertTrue;
import java.io.File;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import org.apache.hadoop.fs.FileUtil;
import org.apache.hadoop.hdfs.DFSClient;
import org.apache.hadoop.hdfs.client.HdfsDataOutputStream;
import org.apache.hadoop.hdfs.nfs.conf.NfsConfiguration;
import org.apache.hadoop.nfs.nfs3.FileHandle;
import org.apache.hadoop.nfs.nfs3.Nfs3Constant.WriteStableHow;
import org.apache.hadoop.nfs.nfs3.Nfs3FileAttributes;
import org.apache.hadoop.nfs.nfs3.request.WRITE3Request;
import org.apache.hadoop.security.ShellBasedIdMapping;
import org.junit.Test;
import org.mockito.Mockito;

public class TestDumpWaterMark {
  static final int CHUNK = 64 * 1024;
  static final int NCHUNK = 1024;               // 64 MiB of out-of-order data
  static final long MIB = 1024L * 1024;

  static long heapAfterGc() throws InterruptedException {
    for (int i = 0; i < 3; i++) { System.gc(); Thread.sleep(200); }
    return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
  }

  /** dump=false -> null dump path; badDir=true -> dump path whose parent does not exist. */
  static void run(long m, boolean dump, boolean badDir, File dir) throws Exception {
    Field wm = OpenFileCtx.class.getDeclaredField("DUMP_WRITE_WATER_MARK");
    wm.setAccessible(true);
    long saved = wm.getLong(null);
    wm.setLong(null, m);
    NfsConfiguration conf = new NfsConfiguration();
    ShellBasedIdMapping iug = new ShellBasedIdMapping(conf);
    DFSClient dfs = Mockito.mock(DFSClient.class);
    HdfsDataOutputStream fos = Mockito.mock(HdfsDataOutputStream.class);
    Mockito.when(fos.getPos()).thenReturn(0L);
    File dumpFile = badDir ? new File(dir, "no-such-dir/f") : new File(dir, "dump-" + m + "-" + dump);
    OpenFileCtx ctx = new OpenFileCtx(fos, new Nfs3FileAttributes(),
        dump ? dumpFile.getAbsolutePath() : null, dfs, iug, false, conf);
    Field cf = OpenFileCtx.class.getDeclaredField("nonSequentialWriteInMemory");
    cf.setAccessible(true);
    AtomicLong counter = (AtomicLong) cf.get(ctx);
    AtomicLong maxSampled = new AtomicLong();
    AtomicBoolean stop = new AtomicBoolean();
    Thread sampler = new Thread(() -> {
      while (!stop.get()) { long v = counter.get(); if (v > maxSampled.get()) maxSampled.set(v); }
    });
    sampler.setDaemon(true);
    sampler.start();
    AsyncDataService ads = new AsyncDataService();
    ExecutorService ex = Executors.newCachedThreadPool(r -> {
      Thread t = new Thread(r); t.setDaemon(true); return t; });
    FileHandle fh = new FileHandle(16386L);
    long heap0 = heapAfterGc();
    long maxAfter = 0, maxInHeap = 0;
    int rounds = 0, stuck = 0;
    for (int k = NCHUNK; k >= 1; k--) {            // offsets 64 MiB .. 64 KiB; offset 0 never sent
      byte[] b = new byte[CHUNK];
      Arrays.fill(b, (byte) k);
      WRITE3Request req = new WRITE3Request(fh, (long) k * CHUNK, CHUNK,
          WriteStableHow.UNSTABLE, ByteBuffer.wrap(b));
      int xid = k;
      long before = counter.get();
      Future<?> f = ex.submit(() -> ctx.receivedNewWrite(dfs, req, null, xid, ads, iug));
      try { f.get(10, TimeUnit.SECONDS); } catch (TimeoutException te) { stuck++; }
      long after = counter.get();
      if (after < before + CHUNK) rounds++;        // a dump drained the counter
      maxAfter = Math.max(maxAfter, after);
      long inHeap = 0;
      for (WriteCtx w : ctx.getPendingWritesForTest().values()) {
        if (w.getDataState() != WriteCtx.DataState.DUMPED) inHeap += w.getCount();
      }
      maxInHeap = Math.max(maxInHeap, inHeap);
    }
    long heap1 = heapAfterGc();
    stop.set(true);
    long dumpLen = dumpFile.exists() ? dumpFile.length() : -1;
    System.out.println(String.format("DUMPWM M=%d dump=%b badDir=%b maxAfterReturn=%d maxSampled=%d "
        + "maxInHeap=%d final=%d rounds=%d stuck=%d dumpFileLen=%d heapDelta=%d",
        m, dump, badDir, maxAfter, maxSampled.get(), maxInHeap, counter.get(), rounds, stuck,
        dumpLen, heap1 - heap0));
    ctx.cleanup();
    ads.shutdown();
    ex.shutdownNow();
    wm.setLong(null, saved);
  }

  @Test
  public void sweep() throws Exception {
    if (RpcProgramNfs3.metrics == null) {
      RpcProgramNfs3.metrics = Nfs3Metrics.create(new NfsConfiguration(), "dumpwm");
    }
    File dir = new File(System.getProperty("dumpwm.dir", "target/dumpwm"));
    FileUtil.fullyDelete(dir);
    assertTrue(dir.mkdirs());
    for (long m : new long[] {256 * 1024L, MIB, 4 * MIB, 16 * MIB, 128 * MIB}) {
      run(m, true, false, dir);
    }
    run(MIB, false, false, dir);   // U6: dumping disabled (null path) -> no cap
    run(MIB, true, true, dir);     // U7: dump file cannot be created -> bypass / stuck writer
  }
}
