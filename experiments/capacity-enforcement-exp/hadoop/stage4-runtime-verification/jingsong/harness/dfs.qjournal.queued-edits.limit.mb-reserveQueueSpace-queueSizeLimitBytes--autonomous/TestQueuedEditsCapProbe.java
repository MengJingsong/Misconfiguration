/*
 * Stage-4 unit-tier probe for dfs.qjournal.queued-edits.limit.mb
 * (case dfs.qjournal.queued-edits.limit.mb-reserveQueueSpace-queueSizeLimitBytes--autonomous, B2 + A2).
 * Not upstream. Copied into a local source copy at
 * hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/qjournal/client/.
 * Prints readings as IFCHK lines; does not assert on readings (A2.2).
 */
package org.apache.hadoop.hdfs.qjournal.client;

import java.lang.management.ManagementFactory;
import java.lang.ref.WeakReference;
import java.net.InetSocketAddress;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeoutException;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.hdfs.DFSConfigKeys;
import org.apache.hadoop.hdfs.qjournal.protocol.QJournalProtocol;
import org.apache.hadoop.hdfs.server.protocol.NamespaceInfo;
import org.apache.hadoop.test.GenericTestUtils;
import org.apache.hadoop.test.GenericTestUtils.DelayAnswer;
import org.apache.hadoop.thirdparty.com.google.common.util.concurrent.ListenableFuture;
import org.junit.Test;
import org.mockito.ArgumentMatchers;
import org.mockito.Mockito;
import org.mockito.invocation.InvocationOnMock;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class TestQueuedEditsCapProbe {
  private static final Logger LOG =
      LoggerFactory.getLogger(TestQueuedEditsCapProbe.class);
  private static final NamespaceInfo NSINFO =
      new NamespaceInfo(12345, "mycluster", "my-bp", 0L);
  private static int nextPort = 20001;

  private static final int KIB4 = 4096;
  private static final int KIB512 = 512 * 1024;

  private static synchronized InetSocketAddress nextAddr() {
    return new InetSocketAddress("127.0.0.1", nextPort++);
  }

  private static IPCLoggerChannel newChannel(Integer limitMb,
      final QJournalProtocol proxy) {
    Configuration conf = new Configuration();
    if (limitMb != null) {
      conf.setInt(DFSConfigKeys.DFS_QJOURNAL_QUEUE_SIZE_LIMIT_KEY, limitMb);
    }
    IPCLoggerChannel ch = new IPCLoggerChannel(conf, NSINFO, "probe-jid",
        nextAddr()) {
      @Override
      protected QJournalProtocol getProxy() {
        return proxy;
      }
    };
    ch.setEpoch(1);
    return ch;
  }

  private static void gc() throws InterruptedException {
    for (int i = 0; i < 3; i++) {
      System.gc();
      Thread.sleep(100);
    }
  }

  private static long heapUsed() {
    return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
  }

  private static int numBatches(Integer limitMb, int b) {
    int l = limitMb == null ? 10 : limitMb;
    if (l == 0) {
      return 4;
    }
    long c = (long) l * 1024 * 1024;
    return (int) (2 * ((c + b - 1) / b) + 4);
  }

  /** Blocked run (B2c): DelayAnswer holds the single executor thread. */
  private void blocked(String label, Integer limitMb, int[] sizes)
      throws Exception {
    QJournalProtocol mock = Mockito.mock(QJournalProtocol.class,
        Mockito.withSettings().stubOnly());
    DelayAnswer delayer = new DelayAnswer(LOG) {
      @Override
      protected Object passThrough(InvocationOnMock invocation) {
        return null;
      }
    };
    Mockito.doAnswer(delayer).when(mock).journal(ArgumentMatchers.any(),
        ArgumentMatchers.anyLong(), ArgumentMatchers.anyLong(),
        ArgumentMatchers.anyInt(), ArgumentMatchers.any());
    gc();
    long heap0 = heapUsed();
    final IPCLoggerChannel ch = newChannel(limitMb, mock);
    int n = sizes.length;
    List<ListenableFuture<Void>> futs = new ArrayList<>(n);
    List<WeakReference<byte[]>> refs = new ArrayList<>(n);
    long maxQueued = 0;
    for (int i = 0; i < n; i++) {
      byte[] d = new byte[sizes[i]];
      refs.add(new WeakReference<>(d));
      futs.add(ch.sendEdits(1L, i + 1, 1, d));
      d = null;
      maxQueued = Math.max(maxQueued, ch.getQueuedEditsSize());
      if (i == 0) {
        delayer.waitForCall(); // first batch is in flight, executor blocked
      }
    }
    long finalQueued = ch.getQueuedEditsSize();
    int accepted = 0, refused = 0, firstRefused = -1, doneOk = 0;
    boolean causeOk = true;
    boolean[] isRefused = new boolean[n];
    for (int i = 0; i < n; i++) {
      ListenableFuture<Void> f = futs.get(i);
      if (f.isDone()) {
        try {
          f.get();
          doneOk++;
          accepted++;
        } catch (ExecutionException ee) {
          refused++;
          isRefused[i] = true;
          if (firstRefused < 0) {
            firstRefused = i + 1;
          }
          if (!(ee.getCause() instanceof LoggerTooFarBehindException)) {
            causeOk = false;
            System.out.println("IFCHK-CAUSE," + label + "," + (i + 1) + ","
                + ee.getCause());
          }
        }
      } else {
        accepted++;
      }
    }
    futs = null; // the test keeps no futures of its own during GC
    gc();
    long heapQueued = heapUsed();
    int accCleared = 0, refCleared = 0;
    for (int i = 0; i < n; i++) {
      boolean cleared = refs.get(i).get() == null;
      if (isRefused[i]) {
        if (cleared) refCleared++;
      } else {
        if (cleared) accCleared++;
      }
    }
    delayer.proceed();
    long afterDrain;
    try {
      GenericTestUtils.waitFor(() -> ch.getQueuedEditsSize() == 0, 10, 10000);
    } catch (TimeoutException te) {
      LOG.warn("queue did not drain", te);
    }
    afterDrain = ch.getQueuedEditsSize();
    ch.close();
    gc();
    long heapAfter = heapUsed();
    System.out.println("IFCHK," + label + "," + limitMb + "," + sizes[n - 1]
        + "," + n + "," + accepted + "," + refused + "," + firstRefused + ","
        + maxQueued + "," + finalQueued + "," + afterDrain + ","
        + accCleared + "," + accepted + "," + refCleared + "," + refused + ","
        + causeOk);
    System.out.println("IFCHK-HEAP," + label + "," + heap0 + "," + heapQueued
        + "," + heapAfter + ",doneOkBeforeProceed=" + doneOk);
  }

  /** Positive control (B2c, A2.1): mock returns at once, each send awaited. */
  private void control(String label, Integer limitMb, int[] sizes)
      throws Exception {
    QJournalProtocol mock = Mockito.mock(QJournalProtocol.class,
        Mockito.withSettings().stubOnly());
    final IPCLoggerChannel ch = newChannel(limitMb, mock);
    int n = sizes.length;
    int accepted = 0, refused = 0, firstRefused = -1;
    boolean causeOk = true;
    long maxQueued = 0;
    for (int i = 0; i < n; i++) {
      ListenableFuture<Void> f = ch.sendEdits(1L, i + 1, 1, new byte[sizes[i]]);
      maxQueued = Math.max(maxQueued, ch.getQueuedEditsSize());
      try {
        f.get();
        accepted++;
      } catch (ExecutionException ee) {
        refused++;
        if (firstRefused < 0) {
          firstRefused = i + 1;
        }
        if (!(ee.getCause() instanceof LoggerTooFarBehindException)) {
          causeOk = false;
        }
      }
    }
    try {
      GenericTestUtils.waitFor(() -> ch.getQueuedEditsSize() == 0, 10, 10000);
    } catch (TimeoutException te) {
      LOG.warn("control queue did not drain", te);
    }
    long finalQueued = ch.getQueuedEditsSize();
    ch.close();
    System.out.println("IFCHK," + label + "," + limitMb + "," + sizes[n - 1]
        + "," + n + "," + accepted + "," + refused + "," + firstRefused + ","
        + maxQueued + "," + finalQueued + "," + finalQueued + ",-,-,-,-,"
        + causeOk);
  }

  private void pair(Integer limitMb, int b) throws Exception {
    int n = numBatches(limitMb, b);
    int[] sizes = new int[n];
    java.util.Arrays.fill(sizes, b);
    String tag = "L" + (limitMb == null ? "unset" : limitMb) + "-b" + b;
    blocked("blocked-" + tag, limitMb, sizes);
    control("control-" + tag, limitMb, sizes);
  }

  @Test(timeout = 300000) public void testL0b4k() throws Exception { pair(0, KIB4); }
  @Test(timeout = 300000) public void testL0b512k() throws Exception { pair(0, KIB512); }
  @Test(timeout = 300000) public void testL1b4k() throws Exception { pair(1, KIB4); }
  @Test(timeout = 300000) public void testL1b512k() throws Exception { pair(1, KIB512); }
  @Test(timeout = 300000) public void testL4b4k() throws Exception { pair(4, KIB4); }
  @Test(timeout = 300000) public void testL4b512k() throws Exception { pair(4, KIB512); }
  @Test(timeout = 300000) public void testLunsetb4k() throws Exception { pair(null, KIB4); }
  @Test(timeout = 300000) public void testLunsetb512k() throws Exception { pair(null, KIB512); }

  /** Overshoot (B2c, A2.4): 3 MiB into an empty queue at L = 1, then 4 KiB. */
  @Test(timeout = 300000)
  public void testOvershoot() throws Exception {
    blocked("overshoot-L1", 1, new int[] {3 * 1024 * 1024, KIB4});
  }
}
