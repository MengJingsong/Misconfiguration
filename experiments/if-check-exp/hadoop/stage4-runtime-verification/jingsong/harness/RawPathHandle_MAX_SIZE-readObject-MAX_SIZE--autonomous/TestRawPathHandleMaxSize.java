/*
 * Stage-4 harness (if-check-exp, Hadoop, Jingsong's share), case
 * RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous, unit tier B2 as amended by A1-A6.
 * Copied into hadoop-common's src/test/java/org/apache/hadoop/fs/ of a per-run copy by unit-run.sh.
 * System properties: ifchk.arm (D | K16 | K24), ifchk.max (the arm's MAX_SIZE).
 * Output: CSV lines starting with IFCHK on stdout (surefire *-output.txt). Predictions are evaluated
 * by analyze.py, not here; the assertions below are validity checks only.
 */
package org.apache.hadoop.fs;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.io.serializer.Deserializer;
import org.apache.hadoop.io.serializer.SerializationFactory;
import org.apache.hadoop.io.serializer.Serializer;
import org.junit.Assert;
import org.junit.Assume;
import org.junit.Test;

public class TestRawPathHandleMaxSize {

  static final String ARM = System.getProperty("ifchk.arm", "D");
  static final int M = Integer.getInteger("ifchk.max", 1 << 20);
  static final int SENTINEL = 0x00012345; // 74,565
  static final int WARM = 5, MEAS = 20;
  static volatile Object sink;

  static final com.sun.management.ThreadMXBean TMX =
      (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

  static long alloc() {
    return TMX.getThreadAllocatedBytes(Thread.currentThread().getId());
  }

  /** Unchecked twin of RawPathHandle's serialized form (A6). */
  static final class UncheckedHandle implements Serializable {
    private static final long serialVersionUID = 0x5eed0001L;
    private transient byte[] data;
    UncheckedHandle(byte[] d) { data = d; }
    private void writeObject(ObjectOutputStream out) throws IOException {
      out.defaultWriteObject();
      out.writeInt(data.length);
      out.write(data);
    }
    private void readObject(ObjectInputStream in) throws IOException, ClassNotFoundException {
      in.defaultReadObject();
      int len = in.readInt();
      byte[] x = new byte[len];
      in.readFully(x);
      data = x;
    }
  }

  static byte[] pattern(int len) {
    byte[] b = new byte[len];
    for (int i = 0; i < len; i++) {
      b[i] = (byte) (i & 0xff);
    }
    return b;
  }

  static byte[] serialize(Object o, boolean header) throws IOException {
    ByteArrayOutputStream bos = new ByteArrayOutputStream();
    ObjectOutputStream oos = header ? new ObjectOutputStream(bos)
        : new ObjectOutputStream(bos) {
          @Override protected void writeStreamHeader() { }
        };
    oos.writeObject(o);
    oos.close();
    return bos.toByteArray();
  }

  static Object make(boolean control, byte[] payload) {
    return control ? new UncheckedHandle(payload) : new RawPathHandle(ByteBuffer.wrap(payload));
  }

  /** Stream for a row: genuine (g) or sentinel-patched (p). */
  static byte[] stream(boolean control, char kind, int len) throws IOException {
    if (kind == 'g') {
      return serialize(make(control, pattern(len)), true);
    }
    byte[] s = serialize(make(control, new byte[SENTINEL]), true);
    byte[] pat = {0x00, 0x01, 0x23, 0x45};
    int found = -1, count = 0;
    for (int i = 0; i + 4 <= s.length; i++) {
      if (s[i] == pat[0] && s[i + 1] == pat[1] && s[i + 2] == pat[2] && s[i + 3] == pat[3]) {
        if (found < 0) {
          found = i;
        }
        count++;
      }
    }
    Assert.assertEquals("sentinel must occur exactly once", 1, count);
    s[found] = (byte) (len >>> 24);
    s[found + 1] = (byte) (len >>> 16);
    s[found + 2] = (byte) (len >>> 8);
    s[found + 3] = (byte) len;
    return s;
  }

  interface Reader {
    Object read() throws Exception;
  }

  interface ReaderFactory {
    Reader open(byte[] bytes) throws Exception;
  }

  static final ReaderFactory OIS = bytes -> {
    final ObjectInputStream ois = new ObjectInputStream(new ByteArrayInputStream(bytes));
    return ois::readObject;
  };

  static final class Row {
    String outcome, exClass = "", msg = "";
    long remaining = -1;
    String contentOk = "na";
    boolean same = true;
    long[] deltas;
    int iterations;
  }

  static String clean(String s) {
    return s == null ? "" : s.replace(',', ';').replace('\n', ' ');
  }

  static Row run(ReaderFactory rf, byte[] bytes, int warm, int meas, int len, char kind) throws Exception {
    Row r = new Row();
    r.deltas = new long[meas];
    r.iterations = warm + meas;
    String first = null;
    for (int it = 0; it < warm + meas; it++) {
      Reader rd = rf.open(bytes);
      Object obj = null;
      Throwable thr = null;
      long a0 = alloc();
      long a1;
      try {
        obj = rd.read();
      } catch (Throwable t) {
        thr = t;
      } finally {
        a1 = alloc();
      }
      String oc;
      if (thr != null) {
        oc = "exception:" + thr.getClass().getName() + ":" + thr.getMessage();
        r.outcome = "exception";
        r.exClass = thr.getClass().getName();
        r.msg = clean(thr.getMessage());
      } else {
        oc = "object";
        r.outcome = "object";
        if (it == warm + meas - 1) {
          ByteBuffer bb;
          if (obj instanceof RawPathHandle) {
            bb = ((RawPathHandle) obj).bytes();
          } else {
            bb = ByteBuffer.wrap(((UncheckedHandle) obj).data);
          }
          r.remaining = bb.remaining();
          if (kind == 'g') {
            byte[] got = new byte[bb.remaining()];
            bb.get(got);
            r.contentOk = String.valueOf(Arrays.equals(got, pattern(len)));
          }
        }
      }
      sink = obj;
      sink = null;
      if (first == null) {
        first = oc;
      } else if (!first.equals(oc)) {
        r.same = false;
      }
      if (it >= warm) {
        r.deltas[it - warm] = a1 - a0;
      }
    }
    return r;
  }

  static long median(long[] d) {
    long[] c = d.clone();
    Arrays.sort(c);
    return c[c.length / 2];
  }

  static long min(long[] d) {
    return Arrays.stream(d).min().getAsLong();
  }

  static long max(long[] d) {
    return Arrays.stream(d).max().getAsLong();
  }

  static void emit(String id, String cls, char kind, int len, Row r, long base) {
    long med = median(r.deltas);
    long mx = max(r.deltas);
    System.out.println("IFCHK,row," + ARM + "," + M + "," + id + "," + cls + "," + kind + "," + len + ","
        + r.outcome + "," + r.exClass + "," + r.msg + "," + r.remaining + "," + r.contentOk + ","
        + r.iterations + "," + r.same + "," + med + "," + min(r.deltas) + "," + mx + ","
        + base + "," + (med - base) + "," + (mx - base));
  }

  static long baseline(int armMax) throws Exception {
    byte[] b0 = stream(false, 'g', 0);
    Row r0 = run(OIS, b0, WARM, MEAS, 0, 'g');
    return median(r0.deltas);
  }

  @Test
  public void testInstrument() throws Exception {
    boolean sup = TMX.isThreadAllocatedMemorySupported();
    boolean en = TMX.isThreadAllocatedMemoryEnabled();
    long a0 = alloc();
    byte[] x = new byte[1 << 20];
    long a1 = alloc();
    sink = x;
    sink = null;
    int maxSize = RawPathHandle.class.getField("MAX_SIZE").getInt(null);
    List<String> args = ManagementFactory.getRuntimeMXBean().getInputArguments();
    String src = String.valueOf(RawPathHandle.class.getProtectionDomain().getCodeSource().getLocation());
    System.out.println("IFCHK,instr," + ARM + "," + M + ",supported=" + sup + ",enabled=" + en
        + ",knownAnswer1MiB=" + (a1 - a0) + ",maxMemory=" + Runtime.getRuntime().maxMemory()
        + ",MAX_SIZE=" + maxSize + ",codeSource=" + clean(src) + ",jvmArgs=" + clean(String.join(" ", args))
        + ",java=" + System.getProperty("java.version"));
    Assert.assertTrue(sup && en);
    Assert.assertEquals("MAX_SIZE of the build must equal ifchk.max", M, maxSize);
  }

  @Test
  public void testArmRows() throws Exception {
    Assert.assertEquals(M, RawPathHandle.class.getField("MAX_SIZE").getInt(null));
    long base = baseline(M);
    List<Object[]> rows = new ArrayList<>();
    if (ARM.equals("D")) {
      rows.add(new Object[]{"L0", 'g', 0});
      rows.add(new Object[]{"L1", 'g', 1024});
      rows.add(new Object[]{"L2", 'g', M - 1});
      rows.add(new Object[]{"L3", 'g', M});
      rows.add(new Object[]{"L4", 'g', M + 1});
      rows.add(new Object[]{"L5", 'g', 16777216});
      rows.add(new Object[]{"L6", 'p', Integer.MAX_VALUE});
      rows.add(new Object[]{"L7", 'p', -1});
      rows.add(new Object[]{"L8", 'p', 67108864});
    } else if (ARM.equals("K16")) {
      rows.add(new Object[]{"K0", 'g', 0});
      rows.add(new Object[]{"K1", 'g', 1024});
      rows.add(new Object[]{"KMm1", 'g', M - 1});
      rows.add(new Object[]{"KM", 'g', M});
      rows.add(new Object[]{"KMp1", 'g', M + 1});
      rows.add(new Object[]{"K1MiB", 'g', 1048576});
      rows.add(new Object[]{"KMAXINT", 'p', Integer.MAX_VALUE});
      rows.add(new Object[]{"Kneg1", 'p', -1});
    } else {
      rows.add(new Object[]{"K0", 'g', 0});
      rows.add(new Object[]{"K1", 'g', 1024});
      rows.add(new Object[]{"KMm1", 'g', M - 1});
      rows.add(new Object[]{"KM", 'g', M});
      rows.add(new Object[]{"KMp1", 'g', M + 1});
      rows.add(new Object[]{"K64MiB", 'p', 67108864});
      rows.add(new Object[]{"KMAXINT", 'p', Integer.MAX_VALUE});
      rows.add(new Object[]{"Kneg1", 'p', -1});
    }
    for (Object[] row : rows) {
      String id = (String) row[0];
      char kind = (Character) row[1];
      int len = (Integer) row[2];
      byte[] bytes = stream(false, kind, len);
      Row r = run(OIS, bytes, WARM, MEAS, len, kind);
      bytes = null;
      emit(id, "RawPathHandle", kind, len, r, base);
      Assert.assertTrue(id + ": outcome must be the same in every iteration", r.same);
      Assert.assertTrue(id + ": no Error", !r.exClass.endsWith("Error"));
    }
  }

  @Test
  public void testJavaSerializationPath() throws Exception {
    Assume.assumeTrue(ARM.equals("D"));
    long base = baseline(M);
    Configuration conf = new Configuration(false);
    conf.set("io.serializations", "org.apache.hadoop.io.serializer.JavaSerialization");
    final SerializationFactory sf = new SerializationFactory(conf);
    for (Object[] row : new Object[][]{{"J3", M}, {"J4", M + 1}}) {
      String id = (String) row[0];
      int len = (Integer) row[1];
      @SuppressWarnings("unchecked")
      Serializer<RawPathHandle> ser = sf.getSerializer(RawPathHandle.class);
      ByteArrayOutputStream bos = new ByteArrayOutputStream();
      ser.open(bos);
      ser.serialize(new RawPathHandle(ByteBuffer.wrap(pattern(len))));
      ser.close();
      byte[] bytes = bos.toByteArray();
      ReaderFactory jf = b -> {
        final Deserializer<RawPathHandle> de = sf.getDeserializer(RawPathHandle.class);
        de.open(new ByteArrayInputStream(b));
        return () -> de.deserialize(null);
      };
      Row r = run(jf, bytes, WARM, MEAS, len, 'g');
      emit(id, "RawPathHandle/JavaSerialization", 'g', len, r, base);
      Assert.assertTrue(id + ": outcome must be the same in every iteration", r.same);
    }
  }

  @Test
  public void testPositiveControlUncheckedAlloc() throws Exception {
    Assume.assumeTrue(ARM.equals("D"));
    long base = baseline(M);
    Object[][] rows = {
        {"C5", 'g', 16777216, WARM, MEAS},
        {"C8", 'p', 67108864, WARM, MEAS},
        {"C9", 'p', 536870912, 0, 3},
        {"C6", 'p', Integer.MAX_VALUE, 0, 3}};
    for (Object[] row : rows) {
      String id = (String) row[0];
      char kind = (Character) row[1];
      int len = (Integer) row[2];
      byte[] bytes = stream(true, kind, len);
      Row r = run(OIS, bytes, (Integer) row[3], (Integer) row[4], len, kind);
      bytes = null;
      emit(id, "UncheckedHandle", kind, len, r, base);
    }
  }
}
