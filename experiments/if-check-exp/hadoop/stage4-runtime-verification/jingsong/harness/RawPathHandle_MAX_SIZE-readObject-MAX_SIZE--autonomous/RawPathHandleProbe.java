/*
 * Stage-4 harness, case RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous, cluster tier (B3 as amended by A7).
 * Compiled against the distribution's hadoop-common-3.4.2.jar and run with `hadoop jar probe.jar RawPathHandleProbe ...`.
 *   write <raw|ctl> <g|p> <len> <file>   genuine (g) or sentinel-patched (p) serialized stream
 *   read <id> <file> <N> <keep|drop>     deserialize N times; one PROBE line with the readings
 */
import java.io.*;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;
import org.apache.hadoop.fs.RawPathHandle;

public class RawPathHandleProbe {
  static final int SENTINEL = 0x00012345;

  /** Unchecked twin of RawPathHandle's serialized form (positive control). */
  public static final class UncheckedProbeHandle implements Serializable {
    private static final long serialVersionUID = 0x5eed0002L;
    private transient byte[] data;
    UncheckedProbeHandle(byte[] d) { data = d; }
    private void writeObject(ObjectOutputStream out) throws IOException {
      out.defaultWriteObject(); out.writeInt(data.length); out.write(data);
    }
    private void readObject(ObjectInputStream in) throws IOException, ClassNotFoundException {
      in.defaultReadObject(); int len = in.readInt(); byte[] x = new byte[len]; in.readFully(x); data = x;
    }
  }

  static long alloc() {
    return ((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean())
        .getThreadAllocatedBytes(Thread.currentThread().getId());
  }

  static byte[] pattern(int len) { byte[] b = new byte[len]; for (int i = 0; i < len; i++) b[i] = (byte) (i & 0xff); return b; }

  static byte[] ser(Object o) throws IOException {
    ByteArrayOutputStream bos = new ByteArrayOutputStream();
    try (ObjectOutputStream oos = new ObjectOutputStream(bos)) { oos.writeObject(o); }
    return bos.toByteArray();
  }

  static Object make(boolean ctl, byte[] p) { return ctl ? new UncheckedProbeHandle(p) : new RawPathHandle(ByteBuffer.wrap(p)); }

  static String vmhwm() throws IOException {
    for (String l : Files.readAllLines(Paths.get("/proc/self/status"))) {
      if (l.startsWith("VmHWM:")) return l.replaceAll("[^0-9]", "");
    }
    return "-1";
  }

  public static void main(String[] a) throws Exception {
    if (a[0].equals("write")) {
      boolean ctl = a[1].equals("ctl");
      int len = Integer.parseInt(a[3]);
      byte[] s;
      if (a[2].equals("g")) {
        s = ser(make(ctl, pattern(len)));
      } else {
        s = ser(make(ctl, new byte[SENTINEL]));
        int found = -1, count = 0;
        for (int i = 0; i + 4 <= s.length; i++)
          if (s[i] == 0 && s[i + 1] == 1 && s[i + 2] == 0x23 && s[i + 3] == 0x45) { if (found < 0) found = i; count++; }
        if (count != 1) throw new IllegalStateException("sentinel count " + count);
        s[found] = (byte) (len >>> 24); s[found + 1] = (byte) (len >>> 16); s[found + 2] = (byte) (len >>> 8); s[found + 3] = (byte) len;
      }
      Files.write(Paths.get(a[4]), s);
      System.out.println("WROTE," + a[4] + ",bytes=" + s.length + ",class=" + (ctl ? "UncheckedProbeHandle" : "RawPathHandle") + ",kind=" + a[2] + ",len=" + len);
      return;
    }
    String id = a[1];
    byte[] bytes = Files.readAllBytes(Paths.get(a[2]));
    int n = Integer.parseInt(a[3]);
    boolean keep = a[4].equals("keep");
    List<Object> kept = new ArrayList<>();
    long objects = 0, ioex = 0, other = 0, oom = 0, oomAt = -1, contentBad = 0;
    String oomMsg = "", resultClass = "";
    Set<String> msgs = new TreeSet<>();
    long t0 = System.nanoTime();
    long a0 = alloc();
    for (int it = 1; it <= n; it++) {
      try {
        ObjectInputStream ois = new ObjectInputStream(new ByteArrayInputStream(bytes));
        Object o = ois.readObject();
        objects++;
        resultClass = o.getClass().getSimpleName();
        if (keep) kept.add(o);
      } catch (IOException e) {
        if (e.getClass() == IOException.class) ioex++; else other++;
        msgs.add(e.getClass().getSimpleName().equals("IOException") ? String.valueOf(e.getMessage()) : e.getClass().getSimpleName() + ":" + e.getMessage());
      } catch (OutOfMemoryError e) {
        oom++; oomAt = it; oomMsg = String.valueOf(e.getMessage());
        break;
      }
    }
    long total = alloc() - a0;
    long ms = (System.nanoTime() - t0) / 1000000;
    if (keep && !kept.isEmpty()) {
      Object o = kept.get(kept.size() - 1);
      if (o instanceof RawPathHandle) {
        ByteBuffer bb = ((RawPathHandle) o).bytes(); byte[] got = new byte[bb.remaining()]; bb.get(got);
        if (!Arrays.equals(got, pattern(got.length))) contentBad++;
      }
    }
    String src = String.valueOf(RawPathHandle.class.getProtectionDomain().getCodeSource().getLocation());
    String args = String.join(" ", ManagementFactory.getRuntimeMXBean().getInputArguments());
    System.out.println("PROBE,id=" + id + ",file=" + a[2] + ",streamBytes=" + bytes.length + ",n=" + n + ",keep=" + keep
        + ",kept=" + kept.size() + ",resultClass=" + resultClass + ",objects=" + objects + ",ioexceptions=" + ioex
        + ",otherex=" + other + ",oom=" + oom + ",oomAt=" + oomAt + ",oomMsg=" + oomMsg.replace(',', ';')
        + ",msgs=" + String.join("|", msgs).replace(',', ';') + ",contentBad=" + contentBad + ",total=" + total
        + ",ms=" + ms + ",maxMemory=" + Runtime.getRuntime().maxMemory() + ",vmhwmKiB=" + vmhwm()
        + ",codeSource=" + src + ",jvmArgs=" + args.replace(',', ';'));
  }
}
