/*
 * Stage-4 cluster-tier instrument (B3d) for DEFAULT_MAX_LEN-readFields-maxLength--autonomous. JDK 11.
 * Usage: java JfrCount <file.jfr> <minSize>
 * Counts jdk.ObjectAllocationOutsideTLAB events with objectClass byte[] and allocationSize >= minSize,
 * split by whether the stack contains org.apache.hadoop.io.Text.readWithKnownLength; prints a size
 * histogram for the matching ones and the top frames of up to 5 non-matching large byte[] events.
 */
import java.nio.file.Paths;
import java.util.Map;
import java.util.TreeMap;

import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedFrame;
import jdk.jfr.consumer.RecordedStackTrace;
import jdk.jfr.consumer.RecordingFile;

public class JfrCount {
  public static void main(String[] args) throws Exception {
    long min = Long.parseLong(args[1]);
    int total = 0, large = 0, viaText = 0, other = 0;
    Map<Long, Integer> sizes = new TreeMap<>();
    StringBuilder others = new StringBuilder();
    for (RecordedEvent e : RecordingFile.readAllEvents(Paths.get(args[0]))) {
      if (!e.getEventType().getName().equals("jdk.ObjectAllocationOutsideTLAB")) continue;
      total++;
      String cls = e.getClass("objectClass") == null ? "?" : e.getClass("objectClass").getName();
      long size = e.getLong("allocationSize");
      // RecordedClass.getName() gives the binary name "[B" for byte[] (fixed 2026-11-25, defect 1)
      if (!(cls.equals("[B") || cls.equals("byte[]")) || size < min) continue;
      large++;
      boolean hit = false;
      RecordedStackTrace st = e.getStackTrace();
      StringBuilder top = new StringBuilder();
      if (st != null) {
        int n = 0;
        for (RecordedFrame f : st.getFrames()) {
          String m = f.getMethod().getType().getName() + "." + f.getMethod().getName();
          if (m.equals("org.apache.hadoop.io.Text.readWithKnownLength")) hit = true;
          if (n++ < 8) top.append("    ").append(m).append(':').append(f.getLineNumber()).append('\n');
        }
      }
      if (hit) {
        viaText++;
        sizes.merge(size, 1, Integer::sum);
      } else {
        other++;
        if (other <= 5) others.append("  OTHER size=").append(size).append('\n').append(top);
      }
    }
    System.out.println("JFR file=" + args[0] + " outsideTlabEvents=" + total + " byteArray>=" + min
        + "=" + large + " viaTextReadWithKnownLength=" + viaText + " other=" + other);
    for (Map.Entry<Long, Integer> s : sizes.entrySet()) {
      System.out.println("  SIZE " + s.getKey() + " x" + s.getValue());
    }
    System.out.print(others);
  }
}
