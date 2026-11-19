import java.io.File;
import java.util.ArrayList;
import java.util.List;

/** B18 known-answer check of hprof_scan.py (from C6's HoldRegions, 2026-11-18): holds 40 x byte[1048576], 40 x byte[1048575]
 *  and 1,000 instances of HoldRegions$Marker live until <stop file> exists; writes <ready file> once allocated. The scan of a
 *  GC.heap_dump must report exactly 40 region arrays, 40 near-region arrays and 1,000 HoldRegions$Marker instances. */
public class HoldRegions
{
    static final class Marker { long a; int b; Marker(int i) { a = i; b = i; } }

    public static void main(String[] a) throws Exception
    {
        File ready = new File(a[0]), stop = new File(a[1]);
        List<byte[]> keep = new ArrayList<>();
        List<Marker> marks = new ArrayList<>();
        for (int i = 0; i < 40; i++) keep.add(new byte[1048576]);
        for (int i = 0; i < 40; i++) keep.add(new byte[1048575]);
        for (int i = 0; i < 1000; i++) marks.add(new Marker(i));
        ready.createNewFile();
        while (!stop.exists()) Thread.sleep(100);
        System.out.println("held " + keep.size() + " " + marks.size());
    }
}
