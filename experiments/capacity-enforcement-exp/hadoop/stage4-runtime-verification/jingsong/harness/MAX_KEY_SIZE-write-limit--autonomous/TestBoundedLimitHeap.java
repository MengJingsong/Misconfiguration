/*
 * Stage-4 harness (if-check-exp, Hadoop, Jingsong's share) for the case file
 *   MAX_KEY_SIZE-write-limit--autonomous.md, unit tier B2 with amendments A1-A6.
 * Not part of Apache Hadoop. Copied into a per-run source copy, never into the repository's source.
 *
 * Prints IFCHK CSV lines (to the surefire -output.txt file):
 *   IFCHK,instr,...    instrument check (support, zero, known-answer 1 MiB array)
 *   IFCHK,direct,...   one row per (C, L): A3e columns
 *   IFCHK,tfile,...    TFile key path (B2c TFile steps, A4)
 *   IFCHK,control,...  positive control (A5)
 */
package org.apache.hadoop.io;

import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.FSDataOutputStream;
import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.file.tfile.TFile;
import org.junit.Assert;
import org.junit.Test;

public class TestBoundedLimitHeap {

  private static final com.sun.management.ThreadMXBean TMX =
      (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
  private static final int E = 1024;          // past-limit writes per pass (A2)
  private static final int PASSES = 100;      // measured passes (A2)
  private static final int EXC_N = 1000;      // exception-cost baseline (A3a)
  private static final int CTRL_PASSES = 10;  // control passes (A5)
  private static final int[] CAPS = {65536, 1048576, 16777216};

  private static long alloc() {
    return TMX.getThreadAllocatedBytes(Thread.currentThread().getId());
  }

  private static long used() {
    for (int i = 0; i < 3; i++) {
      System.gc();
    }
    Runtime r = Runtime.getRuntime();
    return r.totalMemory() - r.freeMemory();
  }

  private static void checkInstrument() {
    Assert.assertTrue("thread allocated memory not supported",
        TMX.isThreadAllocatedMemorySupported());
    if (!TMX.isThreadAllocatedMemoryEnabled()) {
      TMX.setThreadAllocatedMemoryEnabled(true);
    }
    Assert.assertTrue("thread allocated memory not enabled", TMX.isThreadAllocatedMemoryEnabled());
    Assert.assertTrue("allocation reading is -1", alloc() >= 0);
  }

  private static long allocZero() {
    long a = alloc();
    long b = alloc();
    return b - a;
  }

  // The write loop of A2: n passes of reset(L) + W single-byte writes. Called from the test method, so a throw
  // from write(int) is two frames below the test method, like throwEof() in excBaseline().
  // out: [0] exceptions, [1] passes whose first failure is not at L+1, [2] first failure index (pass 0),
  //      [3] size() at the first failure (pass 0)
  private static void passes(BoundedByteArrayOutputStream s, int l, int w, int n, long[] out)
      throws IOException {
    long exc = 0;
    long bad = 0;
    long firstFail = -1;
    long sizeAtFail = -1;
    for (int p = 0; p < n; p++) {
      s.reset(l);
      int ff = -1;
      for (int i = 1; i <= w; i++) {
        try {
          s.write(0x5A);
        } catch (EOFException e) {
          exc++;
          if (ff < 0) {
            ff = i;
            if (p == 0) {
              sizeAtFail = s.size();
            }
          }
        }
      }
      if (ff != l + 1) {
        bad++;
      }
      if (p == 0) {
        firstFail = ff;
      }
    }
    out[0] = exc;
    out[1] = bad;
    out[2] = firstFail;
    out[3] = sizeAtFail;
  }

  // In-limit-only loop of A2: n passes of reset(L) + L writes, no exception.
  private static void inPasses(BoundedByteArrayOutputStream s, int l, int n) throws IOException {
    for (int p = 0; p < n; p++) {
      s.reset(l);
      for (int i = 0; i < l; i++) {
        s.write(0x5A);
      }
    }
  }

  private static void throwEof() throws EOFException {
    throw new EOFException("Reaching the limit of the buffer.");
  }

  // A3a: n throws from a one-frame helper, at the same depth as passes() -> write(int).
  private static long excBaseline(int n) {
    long caught = 0;
    for (int i = 0; i < n; i++) {
      try {
        throwEof();
      } catch (EOFException e) {
        caught++;
      }
    }
    return caught;
  }

  private static double excCost() {
    excBaseline(EXC_N); // warm
    long a0 = alloc();
    long c = excBaseline(EXC_N);
    long a1 = alloc();
    Assert.assertEquals(EXC_N, c);
    return (a1 - a0) / (double) EXC_N;
  }

  @Test
  public void testDirect() throws Exception {
    checkInstrument();
    // Instrument known answer: one 1 MiB array.
    long z = allocZero();
    long k0 = alloc();
    byte[] known = new byte[1 << 20];
    long k1 = alloc();
    System.out.println("IFCHK,instr,supported=" + TMX.isThreadAllocatedMemorySupported()
        + ",enabled=" + TMX.isThreadAllocatedMemoryEnabled() + ",allocZero=" + z
        + ",knownAnswer1MiB=" + (k1 - k0) + ",len=" + known.length
        + ",jvm=" + System.getProperty("java.vm.name") + " " + System.getProperty("java.version")
        + ",maxHeap=" + Runtime.getRuntime().maxMemory()
        + ",gc=" + ManagementFactory.getGarbageCollectorMXBeans().get(0).getName());
    known = null;
    System.out.println("IFCHK,direct,C,L,W,sizeAtFail,failIndex,allocCtor,allocWritesPerPass,allocInPerPass,"
        + "exceptions,excCost,residualPerPass,allocZero,retainedDelta,retainedLoop,bufIdentitySame,bufLength,"
        + "badPasses");
    long[] out = new long[4];
    for (int c : CAPS) {
      int[] limits = {1024, c / 2, c};
      for (int l : limits) {
        int w = l + E;
        long u0 = used();
        long a0 = alloc();
        BoundedByteArrayOutputStream s = new BoundedByteArrayOutputStream(c);
        long a1 = alloc();
        long u1 = used();
        byte[] buf0 = s.getBuffer();
        // warm-up pass (discarded)
        passes(s, l, w, 1, out);
        inPasses(s, l, 1);
        long zero = allocZero();
        // measured passes
        long b0 = alloc();
        passes(s, l, w, PASSES, out);
        long b1 = alloc();
        long exceptions = out[0];
        long bad = out[1];
        long failIndex = out[2];
        long sizeAtFail = out[3];
        long i0 = alloc();
        inPasses(s, l, PASSES);
        long i1 = alloc();
        double exc = excCost();
        long u2 = used();
        boolean same = s.getBuffer() == buf0;
        int bufLen = s.getBuffer().length;
        double writesPerPass = (b1 - b0) / (double) PASSES;
        double inPerPass = (i1 - i0) / (double) PASSES;
        double residual = writesPerPass - E * exc;
        System.out.println(String.format("IFCHK,direct,%d,%d,%d,%d,%d,%d,%.2f,%.2f,%d,%.2f,%.2f,%d,%d,%d,%s,%d,%d",
            c, l, w, sizeAtFail, failIndex, a1 - a0, writesPerPass, inPerPass, exceptions, exc, residual,
            zero, u1 - u0, u2 - u1, same, bufLen, bad));
        // drop every reference so the next row's baseline does not hold this stream
        s = null;
        buf0 = null;
      }
    }
  }

  private static BoundedByteArrayOutputStream keyBuffer(TFile.Writer w) throws Exception {
    Field f = TFile.Writer.class.getDeclaredField("currentKeyBufferOS");
    f.setAccessible(true);
    return (BoundedByteArrayOutputStream) f.get(w);
  }

  // One TFile case: fresh Writer, one key stream, calls until the first EOFException (or maxCalls).
  // mode 0: writeByte, mode 1: writeInt. Returns nothing; prints a row when print is true.
  private static void tfileCase(FileSystem fs, Path file, Configuration conf, String name, int declared,
      int mode, int maxCalls, double exc, boolean print) throws Exception {
    FSDataOutputStream fsdos = fs.create(file, true);
    try {
      long a0 = alloc();
      TFile.Writer w = new TFile.Writer(fsdos, 256 * 1024, "none", "memcmp", conf);
      long a1 = alloc();
      DataOutputStream k = w.prepareAppendKey(declared);
      BoundedByteArrayOutputStream kb = keyBuffer(w);
      int failAt = -1;
      long b0 = alloc();
      for (int i = 1; i <= maxCalls; i++) {
        try {
          if (mode == 0) {
            k.writeByte(0x41);
          } else {
            k.writeInt(i);
          }
        } catch (EOFException e) {
          failAt = i;
          break;
        }
      }
      long b1 = alloc();
      if (print) {
        System.out.println(String.format("IFCHK,tfile,%s,%d,%d,%d,%d,%d,%d,%.2f,%.2f,%d,%d", name, declared,
            maxCalls, failAt, kb.size(), a1 - a0, b1 - b0, exc, (b1 - b0) - exc, kb.getBuffer().length,
            kb.getLimit()));
      }
    } finally {
      fsdos.close(); // the Writer is left in state IN_KEY after the failure; only the file stream is closed
    }
  }

  @Test
  public void testTFileKey() throws Exception {
    checkInstrument();
    Configuration conf = new Configuration();
    FileSystem fs = FileSystem.getLocal(conf);
    String tmp = System.getProperty("ifchk.tmp", "target/ifchk-tmp");
    Path dir = new Path(tmp, "tfile-" + System.currentTimeMillis());
    fs.mkdirs(dir);
    double exc = excCost();
    System.out.println("IFCHK,tfile,case,declared,maxCalls,failAt,sizeAtFail,allocWriter,allocLoop,excCost,"
        + "residual,keyBufLength,keyLimit");
    for (int round = 0; round < 2; round++) { // round 0 = warm-up (discarded)
      boolean print = round == 1;
      tfileCase(fs, new Path(dir, "byte-" + round), conf, "writeByte", -1, 0, 65537, exc, print);
      tfileCase(fs, new Path(dir, "decl100-" + round), conf, "writeByteDecl100", 100, 0, 101, exc, print);
      tfileCase(fs, new Path(dir, "int-" + round), conf, "writeInt", -1, 1, 16385, exc, print);
    }
    System.out.println("IFCHK,tfiledir," + dir);
  }

  private static long ctrlBaos(int w) {
    java.io.ByteArrayOutputStream b = new java.io.ByteArrayOutputStream(32);
    for (int i = 0; i < w; i++) {
      b.write(0x5A);
    }
    return b.size();
  }

  private static long ctrlDob(int w) throws IOException {
    DataOutputBuffer d = new DataOutputBuffer();
    for (int i = 0; i < w; i++) {
      d.write(0x5A);
    }
    return d.getLength();
  }

  @Test
  public void testControl() throws Exception {
    checkInstrument();
    System.out.println("IFCHK,control,stream,C,L,W,allocPerPass,ratio,lastSize");
    for (int c : CAPS) {
      int[] limits = {1024, c / 2, c};
      for (int l : limits) {
        int w = l + E;
        for (int which = 0; which < 2; which++) {
          long size = which == 0 ? ctrlBaos(w) : ctrlDob(w); // warm-up
          long a0 = alloc();
          for (int p = 0; p < CTRL_PASSES; p++) {
            size = which == 0 ? ctrlBaos(w) : ctrlDob(w);
          }
          long a1 = alloc();
          double per = (a1 - a0) / (double) CTRL_PASSES;
          System.out.println(String.format("IFCHK,control,%s,%d,%d,%d,%.2f,%.4f,%d",
              which == 0 ? "ByteArrayOutputStream" : "DataOutputBuffer", c, l, w, per, per / w, size));
        }
      }
    }
  }
}
