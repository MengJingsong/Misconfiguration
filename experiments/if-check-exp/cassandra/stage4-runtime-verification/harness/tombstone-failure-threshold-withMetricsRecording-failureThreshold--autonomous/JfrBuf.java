// Stage-4 harness (tombstone_failure_threshold, B3d item 1): list allocation events of a JFR file.
// usage: java JfrBuf <file.jfr>   prints TSV: type, start_epoch_ms, thread, allocationSize, matched, top_frames
//   matched = "buf" when a frame is DataOutputBuffer.expandToFit (the response buffer's growth), "build" when only
//   ReadResponse$LocalDataResponse.build is (row deserialization inside the build), otherwise "-".
//   Every "buf" event is printed; others only when allocationSize >= 1 MiB.
import java.nio.file.Paths;
import jdk.jfr.consumer.*;

public class JfrBuf
{
    public static void main(String[] a) throws Exception
    {
        System.out.println("type\tstart_ms\tthread\tsize\tmatched\ttop");
        for (RecordedEvent e : RecordingFile.readAllEvents(Paths.get(a[0])))
        {
            String ty = e.getEventType().getName();
            if (!ty.equals("jdk.ObjectAllocationOutsideTLAB") && !ty.equals("jdk.ObjectAllocationInNewTLAB")) continue;
            long size = e.getLong("allocationSize");
            RecordedStackTrace st = e.getStackTrace();
            String m = "-"; StringBuilder top = new StringBuilder();
            if (st != null)
            {
                int k = 0;
                for (RecordedFrame f : st.getFrames())
                {
                    String cl = f.getMethod().getType().getName(), mn = f.getMethod().getName();
                    if (cl.endsWith("DataOutputBuffer") && mn.equals("expandToFit")) m = "buf";
                    else if (m.equals("-") && cl.endsWith("ReadResponse$LocalDataResponse") && mn.equals("build")) m = "build";
                    if (k++ < 6) top.append(cl.substring(cl.lastIndexOf('.') + 1)).append('.').append(mn).append(k < 6 ? ">" : "");
                }
            }
            if (!m.equals("buf") && size < (1 << 20)) continue;
            RecordedThread th = e.getThread();
            System.out.println(ty.substring(4) + "\t" + e.getStartTime().toEpochMilli() + "\t" + (th == null ? "?" : th.getJavaName()) + "\t" + size + "\t" + m + "\t" + top);
        }
    }
}
