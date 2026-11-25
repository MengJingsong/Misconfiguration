/*
 * Stage-4 unit-tier probe for case DEFAULT_MAX_LEN-readFields-maxLength--autonomous (B2).
 * Not upstream. Copied into hadoop-common/src/test/java/org/apache/hadoop/io/ of a per-run
 * source copy, run with -Dmaven-surefire-plugin.argLine="-Xmx512m", deleted afterwards (B2e.4).
 *
 * Each measured call prints one line:
 *   PROBE <case> M=<maxLength> L=<claimed> A=<payload bytes present> rep=<i> outcome=<...> alloc=<bytes> net=<alloc-baseline>
 * and each case a summary line with the median of 5 reps:
 *   SUMMARY <case> M=.. L=.. A=.. outcome=<rep-1 outcome> medianAlloc=.. medianNet=.. baseline=..
 */
package org.apache.hadoop.io;

import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import java.util.concurrent.Callable;

import org.apache.hadoop.security.token.delegation.web.DelegationTokenIdentifier;
import org.junit.Test;

public class TestTextMaxLenProbe {

  private static final int REPS = 5;
  private static final int ONE_MIB = 1024 * 1024;
  private static final int ONE_GIB = 1024 * 1024 * 1024;
  private static final Text KIND = new Text("PROBE");

  private static final com.sun.management.ThreadMXBean TMX =
      (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

  static final class Result {
    final long alloc;
    final String outcome;
    Result(long alloc, String outcome) { this.alloc = alloc; this.outcome = outcome; }
  }

  /** B2e.2: allocation of the calling thread around c.call(); catches Throwable. */
  static Result allocDelta(Callable<?> c) {
    long tid = Thread.currentThread().getId();
    long before = TMX.getThreadAllocatedBytes(tid);
    String outcome;
    try {
      Object r = c.call();
      outcome = "OK:" + r;
    } catch (Throwable t) {
      outcome = t.getClass().getName() + ": " + t.getMessage();
    }
    long after = TMX.getThreadAllocatedBytes(tid);
    return new Result(after - before, outcome.replace('\n', ' '));
  }

  /** B2e.2: [vint L][A bytes 'a']. */
  static byte[] crafted(int L, int A) throws Exception {
    DataOutputBuffer out = new DataOutputBuffer(A + 16);
    WritableUtils.writeVInt(out, L);
    byte[] pay = new byte[A];
    Arrays.fill(pay, (byte) 'a');
    out.write(pay);
    return Arrays.copyOf(out.getData(), out.getLength());
  }

  /** B2c real caller: [byte 0][vint L][A owner bytes] + (if A==L) renewer, realUser, 2 vlong, 2 vint. */
  static byte[] craftedIdentifier(int L, int A) throws Exception {
    DataOutputBuffer out = new DataOutputBuffer(A + 32);
    out.writeByte(0); // AbstractDelegationTokenIdentifier.VERSION
    WritableUtils.writeVInt(out, L);
    byte[] pay = new byte[A];
    Arrays.fill(pay, (byte) 'a');
    out.write(pay);
    if (A == L) {
      WritableUtils.writeVInt(out, 0);  // renewer
      WritableUtils.writeVInt(out, 0);  // realUser
      WritableUtils.writeVLong(out, 0); // issueDate
      WritableUtils.writeVLong(out, 0); // maxDate
      WritableUtils.writeVInt(out, 0);  // sequenceNumber
      WritableUtils.writeVInt(out, 0);  // masterKeyId
    }
    return Arrays.copyOf(out.getData(), out.getLength());
  }

  static DataInputStream in(byte[] b) {
    return new DataInputStream(new ByteArrayInputStream(b));
  }

  static long median(long[] v) {
    long[] c = v.clone();
    Arrays.sort(c);
    return c[c.length / 2];
  }

  /** Runs one case REPS times (fresh objects each time) and prints PROBE and SUMMARY lines. */
  static void measure(String name, int M, int L, int A, long baseline, Callable<?> call) {
    long[] allocs = new long[REPS];
    String first = null;
    for (int i = 0; i < REPS; i++) {
      Result r = allocDelta(call);
      allocs[i] = r.alloc;
      if (first == null) first = r.outcome;
      System.out.println("PROBE " + name + " M=" + M + " L=" + L + " A=" + A + " rep=" + i
          + " outcome=" + r.outcome + " alloc=" + r.alloc + " net=" + (r.alloc - baseline));
      System.gc();
    }
    long med = median(allocs);
    System.out.println("SUMMARY " + name + " M=" + M + " L=" + L + " A=" + A
        + " outcome=" + first + " medianAlloc=" + med + " medianNet=" + (med - baseline)
        + " baseline=" + baseline);
    System.out.flush();
  }

  /** B2d baseline: same call with L = 0 (median of REPS). */
  static long baselineDirect(final int M) throws Exception {
    final byte[] b = crafted(0, 0);
    long[] v = new long[REPS];
    for (int i = 0; i < REPS; i++) {
      v[i] = allocDelta(() -> { Text t = new Text(); t.readFields(in(b), M); return t.getLength(); }).alloc;
    }
    long med = median(v);
    System.out.println("BASELINE direct M=" + M + " L=0 medianAlloc=" + med + " all=" + Arrays.toString(v));
    return med;
  }

  static long baselineIdentifier() throws Exception {
    final byte[] b = craftedIdentifier(0, 0);
    long[] v = new long[REPS];
    for (int i = 0; i < REPS; i++) {
      v[i] = allocDelta(() -> {
        DelegationTokenIdentifier id = new DelegationTokenIdentifier(KIND);
        id.readFields(in(b));
        return id.getOwner().getLength();
      }).alloc;
    }
    long med = median(v);
    System.out.println("BASELINE identifier L=0 medianAlloc=" + med + " all=" + Arrays.toString(v));
    return med;
  }

  /** B2b/B2c: maxLength M in {1024, 1 MiB, 64 MiB} x L in {M-1, M, M+1, 1 GiB}. */
  @Test
  public void directLimit() throws Exception {
    int[] Ms = {1024, ONE_MIB, 64 * ONE_MIB};
    for (final int M : Ms) {
      long base = baselineDirect(M);
      int[] Ls = {M - 1, M, M + 1, ONE_GIB};
      for (final int L : Ls) {
        final int A = (L < M && L <= 64 * ONE_MIB) ? L : 8;
        final byte[] b = crafted(L, A);
        measure("directLimit", M, L, A, base,
            () -> { Text t = new Text(); t.readFields(in(b), M); return t.getLength(); });
      }
    }
  }

  /** B2b/B2c: real caller, owner L in {524288, 1048575, 1048576, 1 GiB}, limit DEFAULT_MAX_LEN. */
  @Test
  public void realCaller() throws Exception {
    long base = baselineIdentifier();
    int[] Ls = {524288, 1048575, 1048576, ONE_GIB};
    for (final int L : Ls) {
      final int A = (L < Text.DEFAULT_MAX_LEN) ? L : 8;
      final byte[] b = craftedIdentifier(L, A);
      measure("realCaller", Text.DEFAULT_MAX_LEN, L, A, base, () -> {
        DelegationTokenIdentifier id = new DelegationTokenIdentifier(KIND);
        id.readFields(in(b));
        return id.getOwner().getLength();
      });
    }
  }

  /** B2e.2: owner of exactly DEFAULT_MAX_LEN bytes: write() succeeds, readFields throws. */
  @Test
  public void writerReaderMismatch() throws Exception {
    byte[] own = new byte[Text.DEFAULT_MAX_LEN];
    Arrays.fill(own, (byte) 'a');
    Text owner = new Text(own);
    DelegationTokenIdentifier id =
        new DelegationTokenIdentifier(KIND, owner, new Text("r"), new Text("u"));
    DataOutputBuffer out = new DataOutputBuffer();
    String w;
    try {
      id.write(out);
      w = "OK:wrote " + out.getLength() + " bytes";
    } catch (Throwable t) {
      w = t.getClass().getName() + ": " + t.getMessage();
    }
    final byte[] b = Arrays.copyOf(out.getData(), out.getLength());
    Result r = allocDelta(() -> {
      DelegationTokenIdentifier back = new DelegationTokenIdentifier(KIND);
      back.readFields(in(b));
      return back.getOwner().getLength();
    });
    System.out.println("MISMATCH ownerLen=" + owner.getLength() + " write=" + w
        + " read=" + r.outcome + " alloc=" + r.alloc);
    System.out.flush();
  }

  /** B2h(1): uncapped Text.readFields(DataInput), L = 256 MiB and 1 GiB, short input. */
  @Test
  public void uncappedControl() throws Exception {
    final byte[] b0 = crafted(0, 0);
    long[] v = new long[REPS];
    for (int i = 0; i < REPS; i++) {
      v[i] = allocDelta(() -> { Text t = new Text(); t.readFields(in(b0)); return t.getLength(); }).alloc;
    }
    long base = median(v);
    System.out.println("BASELINE uncapped L=0 medianAlloc=" + base + " all=" + Arrays.toString(v));
    int[] Ls = {256 * ONE_MIB, ONE_GIB};
    for (final int L : Ls) {
      final byte[] b = crafted(L, 8);
      measure("uncappedControl", -1, L, 8, base,
          () -> { Text t = new Text(); t.readFields(in(b)); return t.getLength(); });
    }
  }
}
