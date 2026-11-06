/* Diagnostic (not a frozen observable): print JFR allocation events of >= 16 MiB with their stacks.
   Usage: java JfrBigAllocs <file.jfr> */
import java.nio.file.Paths;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedFrame;
import jdk.jfr.consumer.RecordingFile;

public class JfrBigAllocs {
  public static void main(String[] a) throws Exception {
    int n = 0;
    for (RecordedEvent e : RecordingFile.readAllEvents(Paths.get(a[0]))) {
      String t = e.getEventType().getName();
      if (!t.contains("ObjectAllocation")) continue;
      long size = e.hasField("allocationSize") ? e.getLong("allocationSize") : 0;
      if (size < (16L << 20)) continue;
      n++;
      StringBuilder sb = new StringBuilder(e.getStartTime() + " " + t + " size=" + size + " class="
          + e.getClass("objectClass").getName() + " thread=" + e.getThread().getJavaName());
      if (e.getStackTrace() != null) {
        int k = 0;
        for (RecordedFrame f : e.getStackTrace().getFrames()) {
          sb.append("\n    at ").append(f.getMethod().getType().getName()).append('.').append(f.getMethod().getName())
            .append(':').append(f.getLineNumber());
          if (++k >= 10) break;
        }
      }
      System.out.println(sb);
    }
    System.out.println("events>=16MiB: " + n);
  }
}
