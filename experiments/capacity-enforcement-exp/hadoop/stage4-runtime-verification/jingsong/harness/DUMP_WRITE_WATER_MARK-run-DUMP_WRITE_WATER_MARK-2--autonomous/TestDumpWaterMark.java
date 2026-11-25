package org.apache.hadoop.hdfs.nfs.nfs3;

// Stage-4 unit tier (B2, amendment 2026-11-25) for
// DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK-2--autonomous (check OpenFileCtx.java:383).
// Every reading goes through log4j (same appender as OpenFileCtx's DEBUG lines) as "DUMPWM ..." lines.

import java.io.File;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Paths;
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
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.mockito.Mockito;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class TestDumpWaterMark {
  static final Logger LOG = LoggerFactory.getLogger(TestDumpWaterMark.class);
  static final long KIB = 1024L, MIB = 1024L * 1024;
  static final long DEFAULT_MARK = 1048576L;
  enum Mode { ENABLED, DISABLED, BROKEN }

  NfsConfiguration conf;
  ShellBasedIdMapping iug;
  File base;

  static Field f(Class<?> c, String n) throws Exception {
    Field x = c.getDeclaredField(n); x.setAccessible(true); return x;
  }
  static void wm(long v) throws Exception { f(OpenFileCtx.class, "DUMP_WRITE_WATER_MARK").setLong(null, v); }
  static long wmGet() throws Exception { return f(OpenFileCtx.class, "DUMP_WRITE_WATER_MARK").getLong(null); }
  static AtomicLong ctrRef(OpenFileCtx c) throws Exception {
    return (AtomicLong) f(OpenFileCtx.class, "nonSequentialWriteInMemory").get(c);
  }
  static long inHeap(OpenFileCtx c) throws Exception {
    Field d = f(WriteCtx.class, "data");
    long s = 0;
    for (WriteCtx w : c.getPendingWritesForTest().values()) {
      if (d.get(w) != null && w.getDataState() != WriteCtx.DataState.DUMPED) s += w.getCount();
    }
    return s;
  }
  static int dumped(OpenFileCtx c) {
    int n = 0;
    for (WriteCtx w : c.getPendingWritesForTest().values()) {
      if (w.getDataState() == WriteCtx.DataState.DUMPED) n++;
    }
    return n;
  }
  static Thread dumper(OpenFileCtx c) throws Exception { return (Thread) f(OpenFileCtx.class, "dumpThread").get(c); }
  static boolean enabledDump(OpenFileCtx c) throws Exception { return f(OpenFileCtx.class, "enabledDump").getBoolean(c); }

  @Before
  public void setUp() throws Exception {
    conf = new NfsConfiguration();
    iug = new ShellBasedIdMapping(conf);
    if (RpcProgramNfs3.metrics == null) {
      RpcProgramNfs3.metrics = Nfs3Metrics.create(conf, "wm-test");
    }
    base = new File(System.getProperty("dumpwm.dir", "target/dumpwm"));
    base.mkdirs();
    if (wmGet() != DEFAULT_MARK) throw new IllegalStateException("mark not default at start: " + wmGet());
  }

  @After
  public void tearDown() throws Exception {
    wm(DEFAULT_MARK);
    LOG.info("DUMPWM RESTORED mark={}", wmGet());
  }

  WRITE3Request req(long off, int w, int i) {
    byte[] b = new byte[w];
    for (int j = 0; j < w; j += 4096) b[j] = (byte) i;
    return new WRITE3Request(new FileHandle(16386, 0), off, w, WriteStableHow.UNSTABLE, ByteBuffer.wrap(b));
  }

  void arm(String name, long mark, int w, int n, Mode mode) throws Exception {
    wm(mark);
    File dumpDir = Files.createTempDirectory(Paths.get(base.getAbsolutePath()), "wm-" + name + "-").toFile();
    String path = mode == Mode.DISABLED ? null
        : mode == Mode.BROKEN ? dumpDir + "/missing/16386" : dumpDir + "/16386";
    File dumpFile = new File(dumpDir, "16386");
    DFSClient dfs = Mockito.mock(DFSClient.class);
    HdfsDataOutputStream fos = Mockito.mock(HdfsDataOutputStream.class);
    Mockito.when(fos.getPos()).thenReturn(0L);
    OpenFileCtx ctx = new OpenFileCtx(fos, new Nfs3FileAttributes(), path, dfs, iug, false, conf);
    AsyncDataService ads = new AsyncDataService();
    AtomicLong ctr = ctrRef(ctx);
    AtomicLong maxSampled = new AtomicLong();
    AtomicBoolean stop = new AtomicBoolean();
    Thread sampler = new Thread(() -> {
      while (!stop.get()) { long v = ctr.get(); if (v > maxSampled.get()) maxSampled.set(v); }
    }, "wm-sampler");
    sampler.setDaemon(true);
    sampler.start();
    LOG.info("DUMPWM ARM-BEGIN {} mark={} w={} n={} G={} mode={} path={}", name, wmGet(), w, n, (long) n * w, mode, path);
    long maxAfter = 0, maxHeap = 0; int stuck = 0, done = 0;
    if (mode != Mode.BROKEN) {
      ExecutorService ex = Executors.newSingleThreadExecutor(r -> { Thread t = new Thread(r, "wm-writer"); t.setDaemon(true); return t; });
      for (int i = 1; i <= n; i++) {
        final long off = (long) i * w;
        final WRITE3Request rq = req(off, w, i);
        final int xid = i;
        Future<?> fut = ex.submit(() -> ctx.receivedNewWrite(dfs, rq, null, xid, ads, iug));
        try { fut.get(30, TimeUnit.SECONDS); } catch (TimeoutException te) {
          stuck++; LOG.info("DUMPWM STUCK {} i={} off={} ctr={}", name, i, off, ctr.get()); break;
        }
        done = i;
        long c = ctr.get(), h = inHeap(ctx);
        Thread dt = dumper(ctx);
        maxAfter = Math.max(maxAfter, c); maxHeap = Math.max(maxHeap, h);
        LOG.info("DUMPWM ROW,{},{},{},{},{},{},{},{}", name, i, off, c, h,
            dumpFile.exists() ? dumpFile.length() : -1, dumped(ctx), dt != null && dt.isAlive());
      }
      ex.shutdownNow();
    } else {
      final int[] issued = {0};
      Thread writer = new Thread(() -> {
        for (int i = 1; i <= n; i++) {
          issued[0] = i;
          ctx.receivedNewWrite(dfs, req((long) i * w, w, i), null, i, ads, iug);
          LOG.info("DUMPWM BROKEN-RETURNED i={} ctr={}", i, ctr.get());
        }
      }, "wm-broken-writer");
      writer.setDaemon(true);
      writer.start();
      writer.join(10_000);
      Thread dt = dumper(ctx);
      StringBuilder st = new StringBuilder();
      StackTraceElement[] ss = writer.getStackTrace();
      for (int k = 0; k < Math.min(6, ss.length); k++) st.append(ss[k]).append(" | ");
      LOG.info("DUMPWM BROKEN {} writerState={} issued={} ctr={} inHeap={} dumpFileExists={} dumperExists={} dumperAlive={} enabledDump={} stack={}",
          name, writer.getState(), issued[0], ctr.get(), inHeap(ctx), new File(path).exists(),
          dt != null, dt != null && dt.isAlive(), enabledDump(ctx), st);
      maxAfter = ctr.get(); maxHeap = inHeap(ctx); done = issued[0];
    }
    Thread dt = dumper(ctx);
    LOG.info("DUMPWM SUMMARY,{},mark={},w={},n={},done={},maxCtrAfterReturn={},maxInHeap={},maxSampled={},finalCtr={},finalInHeap={},dumpLen={},dumped={},dumperExists={},stuck={}",
        name, mark, w, n, done, maxAfter, maxHeap, maxSampled.get(), ctr.get(), inHeap(ctx),
        dumpFile.exists() ? dumpFile.length() : -1, dumped(ctx), dt != null, stuck);
    stop.set(true);
    ctx.cleanup();
    ads.shutdown();
    LOG.info("DUMPWM CLEANUP {} dumpFileExistsAfterCleanup={}", name, dumpFile.exists());
    LOG.info("DUMPWM ARM-END {}", name);
    FileUtil.fullyDelete(dumpDir);
  }

  @Test public void e256k_w64k() throws Exception { arm("e256k_w64k", 256 * KIB, 64 * 1024, 256, Mode.ENABLED); }
  @Test public void e1m_w64k() throws Exception { arm("e1m_w64k", MIB, 64 * 1024, 256, Mode.ENABLED); }
  @Test public void e4m_w64k() throws Exception { arm("e4m_w64k", 4 * MIB, 64 * 1024, 256, Mode.ENABLED); }
  @Test public void e1m_w1m() throws Exception { arm("e1m_w1m", MIB, 1024 * 1024, 16, Mode.ENABLED); }
  @Test public void e1m_w96k() throws Exception { arm("e1m_w96k", MIB, 96 * 1024, 171, Mode.ENABLED); }
  @Test public void disabled_1m_w64k() throws Exception { arm("disabled_1m_w64k", MIB, 64 * 1024, 256, Mode.DISABLED); }
  @Test public void broken_1m_w64k() throws Exception { arm("broken_1m_w64k", MIB, 64 * 1024, 256, Mode.BROKEN); }
}
