import java.nio.file.Paths;
import java.util.List;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedFrame;
import jdk.jfr.consumer.RecordedStackTrace;
import jdk.jfr.consumer.RecordingFile;

/**
 * JDK 11 JFR summary for the cluster tier (B3d): jdk.ObjectAllocationSample does not exist in JDK 11 (it is JDK 16+), so the
 * allocation events jdk.ObjectAllocationInNewTLAB (weight tlabSize) and jdk.ObjectAllocationOutsideTLAB (weight allocationSize)
 * are summed, and the weight whose stack holds ByteSourceInverse.ensureCapacity / readBytes is reported.
 * usage: java JfrSum <recording.jfr>   prints one JSON line.
 */
public class JfrSum
{
    public static void main(String[] a) throws Exception
    {
        long total = 0, ec = 0, rb = 0, nEv = 0, nEc = 0, nRb = 0;
        for (RecordedEvent e : RecordingFile.readAllEvents(Paths.get(a[0])))
        {
            String n = e.getEventType().getName();
            long w;
            if (n.equals("jdk.ObjectAllocationInNewTLAB")) w = e.getLong("tlabSize");
            else if (n.equals("jdk.ObjectAllocationOutsideTLAB")) w = e.getLong("allocationSize");
            else continue;
            total += w; nEv++;
            RecordedStackTrace st = e.getStackTrace();
            if (st == null) continue;
            boolean hasEc = false, hasRb = false;
            for (RecordedFrame f : st.getFrames())
            {
                if (!f.getMethod().getType().getName().endsWith("ByteSourceInverse")) continue;
                String m = f.getMethod().getName();
                if (m.equals("ensureCapacity")) hasEc = true;
                if (m.equals("readBytes")) hasRb = true;
            }
            if (hasEc) { ec += w; nEc++; }
            if (hasEc || hasRb) { rb += w; nRb++; }
        }
        System.out.println("{\"events\":" + nEv + ",\"total_weight\":" + total + ",\"ensureCapacity_weight\":" + ec + ",\"ensureCapacity_events\":" + nEc
                           + ",\"readBytes_or_ensureCapacity_weight\":" + rb + ",\"readBytes_events\":" + nRb
                           + ",\"share_ensureCapacity\":" + (total == 0 ? 0 : (double) ec / total) + ",\"share_readBytes\":" + (total == 0 ? 0 : (double) rb / total) + "}");
    }
}
