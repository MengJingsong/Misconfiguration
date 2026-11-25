/*
 * Stage-4 harness (capacity-enforcement-exp, Hadoop, Jingsong's share) for the case file
 *   MAX_KEY_SIZE-write-limit-2--autonomous.md, unit tier B2 (with the 2026-11-25 audit amendments).
 * Not part of Apache Hadoop. Copied into a per-run source copy, never into the repository's source.
 *
 * Check under test: BoundedByteArrayOutputStream.java:91  if (currentPointer + len > limit)  in write(byte[],int,int).
 * Prints IFCHK CSV lines (to the surefire -output.txt file):
 *   IFCHK,instr,...   instrument (support, enabled, zero, known answer: 1 MiB array), JVM heap and GC
 *   IFCHK,U1,...      mechanism: cap 65536, lim {1024,32768,65536}, 1000-byte writes until EOFException
 *   IFCHK,U2,...      ctorAlloc / writeAlloc at cap 1 MiB, lim {1024,524288,1048576}, warm-up 20, median of 5
 *   IFCHK,U3,...      positive control: ctorAlloc at cap {64Ki,1Mi,16Mi}, lim = cap
 *   IFCHK,U3b,...     positive control: java.io.ByteArrayOutputStream, 200 x 1024 B
 *   IFCHK,U4,...      TFile key via prepareAppendKey(-1), 1024-byte writes until EOFException; prepareAppendKey(65537)
 *   IFCHK,U5,...      TFile file length after N appends of a 65536-byte key and empty value, N {1,10,100}
 */
package org.apache.hadoop.io;

import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.File;
import java.io.IOException;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.Arrays;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.FSDataOutputStream;
import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.file.tfile.TFile;
import org.junit.Assert;
import org.junit.Test;

public class TestBoundedLimitMemory {
  static final com.sun.management.ThreadMXBean T =
      (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
  static final byte[] C1000 = new byte[1000];
  static final byte[] C1024 = new byte[1024];
  static final int WARM = 20;
  static final int MEAS = 5;

  static long alloc() {
    return T.getThreadAllocatedBytes(Thread.currentThread().getId());
  }

  static long base() {
    long b0 = alloc();
    long b1 = alloc();
    return b1 - b0;
  }

  static long median(long[] v) {
    long[] c = v.clone();
    Arrays.sort(c);
    return c[c.length / 2];
  }

  static String j(long[] v) {
    StringBuilder sb = new StringBuilder();
    for (long x : v) {
      if (sb.length() > 0) {
        sb.append(';');
      }
      sb.append(x);
    }
    return sb.toString();
  }

  static void p(String s) {
    System.out.println("IFCHK," + s);
    System.out.flush();
  }

  static File tmpDir() {
    File d = new File(System.getProperty("ifchk.tmp", "target/test-dir/ifchk"));
    d.mkdirs();
    return d;
  }

  // Result of one fill: ctorAlloc, writeAlloc, size at EOF, limit at EOF, successful writes, line of throw frame
  static String lastMsg;
  static String lastFrame;

  static long[] fill(int cap, int lim) throws IOException {
    long base = base();
    long a0 = alloc();
    BoundedByteArrayOutputStream s = new BoundedByteArrayOutputStream(cap, lim);
    long a1 = alloc();
    int n = 0;
    lastMsg = "none";
    lastFrame = "none";
    try {
      while (true) {
        s.write(C1000, 0, 1000);
        n++;
      }
    } catch (EOFException e) {
      lastMsg = e.getMessage();
      StackTraceElement f = e.getStackTrace()[0];
      lastFrame = f.getClassName().replace("org.apache.hadoop.io.", "") + "." + f.getMethodName()
          + ":" + f.getLineNumber();
    }
    long a2 = alloc();
    return new long[] {a1 - a0 - base, a2 - a1 - base, s.size(), s.getLimit(), n,
        s.getBuffer().length};
  }

  @Test
  public void u0instr() {
    Assert.assertTrue(T.isThreadAllocatedMemorySupported());
    if (!T.isThreadAllocatedMemoryEnabled()) {
      T.setThreadAllocatedMemoryEnabled(true);
    }
    long zero = base();
    long b = base();
    long a0 = alloc();
    byte[] ka = new byte[1 << 20];
    long a1 = alloc();
    StringBuilder gc = new StringBuilder();
    for (GarbageCollectorMXBean g : ManagementFactory.getGarbageCollectorMXBeans()) {
      gc.append(g.getName()).append('|');
    }
    p("instr,supported=" + T.isThreadAllocatedMemorySupported() + ",enabled="
        + T.isThreadAllocatedMemoryEnabled() + ",zero=" + zero + ",knownAnswer1MiB=" + (a1 - a0 - b)
        + ",len=" + ka.length + ",maxHeap=" + Runtime.getRuntime().maxMemory() + ",gc=" + gc
        + ",java=" + System.getProperty("java.version") + ",vm=" + System.getProperty("java.vm.name"));
  }

  @Test
  public void u1mechanism() throws IOException {
    for (int lim : new int[] {1024, 32768, 65536}) {
      long[] r = fill(65536, lim);
      p("U1,cap=65536,lim=" + lim + ",size=" + r[2] + ",writes=" + r[4] + ",limitAtEOF=" + r[3]
          + ",bufLen=" + r[5] + ",msg=" + lastMsg + ",frame=" + lastFrame);
    }
  }

  @Test
  public void u2heapVsLimit() throws IOException {
    int cap = 1 << 20;
    for (int lim : new int[] {1024, 524288, 1048576}) {
      for (int w = 0; w < WARM; w++) {
        fill(cap, lim);
      }
      long[] ctor = new long[MEAS];
      long[] wr = new long[MEAS];
      long size = 0;
      long writes = 0;
      for (int m = 0; m < MEAS; m++) {
        long[] r = fill(cap, lim);
        ctor[m] = r[0];
        wr[m] = r[1];
        size = r[2];
        writes = r[4];
      }
      p("U2,cap=" + cap + ",lim=" + lim + ",ctorAllocMedian=" + median(ctor) + ",writeAllocMedian="
          + median(wr) + ",size=" + size + ",writes=" + writes + ",ctorRaw=" + j(ctor) + ",writeRaw="
          + j(wr) + ",msg=" + lastMsg + ",frame=" + lastFrame);
    }
  }

  @Test
  public void u3control() throws IOException {
    for (int cap : new int[] {65536, 1 << 20, 1 << 24}) {
      for (int w = 0; w < WARM; w++) {
        fill(cap, cap);
      }
      long[] ctor = new long[MEAS];
      long[] wr = new long[MEAS];
      for (int m = 0; m < MEAS; m++) {
        long[] r = fill(cap, cap);
        ctor[m] = r[0];
        wr[m] = r[1];
      }
      p("U3,cap=" + cap + ",lim=" + cap + ",ctorAllocMedian=" + median(ctor) + ",writeAllocMedian="
          + median(wr) + ",ctorRaw=" + j(ctor) + ",writeRaw=" + j(wr));
    }
    long[] v = new long[MEAS];
    for (int m = 0; m < WARM + MEAS; m++) {
      long base = base();
      long a0 = alloc();
      java.io.ByteArrayOutputStream b = new java.io.ByteArrayOutputStream();
      for (int i = 0; i < 200; i++) {
        b.write(C1024, 0, 1024);
      }
      long a1 = alloc();
      if (m >= WARM) {
        v[m - WARM] = a1 - a0 - base;
      }
      Assert.assertEquals(204800, b.size());
    }
    p("U3b,written=204800,allocMedian=" + median(v) + ",raw=" + j(v));
  }

  @Test
  public void u4tfileKey() throws IOException {
    Configuration conf = new Configuration();
    FileSystem fs = FileSystem.getLocal(conf);
    File dir = tmpDir();
    long[] ctor = new long[MEAS];
    long[] wr = new long[MEAS];
    long writes = -1;
    String msg = "none";
    String frame = "none";
    for (int m = 0; m < WARM + MEAS; m++) {
      Path path = new Path(new File(dir, "u4-" + m + ".tfile").getAbsolutePath());
      FSDataOutputStream out = fs.create(path, true);
      long base = base();
      long a0 = alloc();
      TFile.Writer w = new TFile.Writer(out, 64 * 1024, TFile.COMPRESSION_NONE, null, conf);
      long a1 = alloc();
      DataOutputStream k = w.prepareAppendKey(-1);
      long a2 = alloc();
      int n = 0;
      String em = "none";
      String ef = "none";
      for (int i = 0; i < 200; i++) {
        try {
          k.write(C1024, 0, 1024);
          n++;
        } catch (EOFException e) {
          em = e.getMessage();
          StackTraceElement f = e.getStackTrace()[0];
          ef = f.getClassName().replace("org.apache.hadoop.io.", "") + "." + f.getMethodName() + ":"
              + f.getLineNumber();
          break;
        }
      }
      long a3 = alloc();
      if (m >= WARM) {
        ctor[m - WARM] = a1 - a0 - base;
        wr[m - WARM] = a3 - a2 - base;
        writes = n;
        msg = em;
        frame = ef;
      }
      try {
        w.close();
      } catch (IllegalStateException expected) {
        // the writer is left IN_KEY by the failed key (case A3 step 5)
      }
      out.close();
    }
    p("U4,keyPrepare=-1,writesOk=" + writes + ",attempt=" + (writes + 1) + ",msg=" + msg + ",frame="
        + frame + ",ctorAllocMedian=" + median(ctor) + ",writeAllocMedian=" + median(wr) + ",ctorRaw="
        + j(ctor) + ",writeRaw=" + j(wr));
    // prepareAppendKey(65537) on a fresh writer
    Path path = new Path(new File(dir, "u4-big.tfile").getAbsolutePath());
    FSDataOutputStream out = fs.create(path, true);
    TFile.Writer w2 = new TFile.Writer(out, 64 * 1024, TFile.COMPRESSION_NONE, null, conf);
    String cls = "none";
    String m2 = "none";
    try {
      w2.prepareAppendKey(65537);
    } catch (Exception e) {
      cls = e.getClass().getName();
      m2 = e.getMessage();
    }
    try {
      w2.close();
    } catch (Exception e) {
      // ignore
    }
    out.close();
    p("U4,keyPrepare=65537,exception=" + cls + ",msg=" + m2);
  }

  @Test
  public void u5tfileDisk() throws IOException {
    Configuration conf = new Configuration();
    FileSystem fs = FileSystem.getLocal(conf);
    File dir = tmpDir();
    for (int nrec : new int[] {1, 10, 100}) {
      File f = new File(dir, "u5-" + nrec + ".tfile");
      Path path = new Path(f.getAbsolutePath());
      FSDataOutputStream out = fs.create(path, true);
      TFile.Writer w = new TFile.Writer(out, 64 * 1024, TFile.COMPRESSION_NONE, null, conf);
      for (int i = 0; i < nrec; i++) {
        w.append(new byte[65536], new byte[0]);
      }
      w.close();
      out.close();
      p("U5,N=" + nrec + ",fileLength=" + f.length() + ",keyBytes=" + (65536L * nrec));
    }
  }
}
