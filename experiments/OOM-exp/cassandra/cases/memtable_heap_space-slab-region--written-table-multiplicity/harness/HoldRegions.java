import java.io.File;
import java.util.ArrayList;
import java.util.List;

/** C6 known-answer check of hprof_scan.py: holds 40 x byte[1048576] and 40 x byte[1048575] live until <stop file> exists;
 *  writes <ready file> once allocated. The scan of a GC.heap_dump must report exactly 40 region arrays. */
public class HoldRegions
{
    public static void main(String[] a) throws Exception
    {
        File ready = new File(a[0]), stop = new File(a[1]);
        List<byte[]> keep = new ArrayList<>();
        for (int i = 0; i < 40; i++) keep.add(new byte[1048576]);
        for (int i = 0; i < 40; i++) keep.add(new byte[1048575]);
        ready.createNewFile();
        while (!stop.exists()) Thread.sleep(100);
        System.out.println("held " + keep.size());
    }
}
