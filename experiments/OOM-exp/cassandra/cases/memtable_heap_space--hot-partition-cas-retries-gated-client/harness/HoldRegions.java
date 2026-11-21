import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

/** R16 known-answer check of hprof_scan.py (B18's HoldRegions plus a FieldProbe, design §2.5 Step A): holds 40 x byte[1048576],
 *  40 x byte[1048575], 1,000 instances of HoldRegions$Marker and one HoldRegions$FieldProbe (inherited long 0x0123456789ABCDEF and
 *  int 4242 from HoldRegions$ProbeBase; an object reference to an AtomicLong(31337); an AtomicInteger(77); enum Phase.C = ordinal 2;
 *  own int -5) live until <stop file> exists; writes <ready file> once allocated. */
public class HoldRegions
{
    static final class Marker { long a; int b; Marker(int i) { a = i; b = i; } }
    enum Phase { A, B, C }
    static class ProbeBase { long lb = 0x0123456789ABCDEFL; int ib = 4242; }
    static final class FieldProbe extends ProbeBase
    {
        Object ref = new AtomicLong(31337);
        AtomicInteger ai = new AtomicInteger(77);
        volatile Phase ph = Phase.C;
        int own = -5;
    }

    public static void main(String[] a) throws Exception
    {
        File ready = new File(a[0]), stop = new File(a[1]);
        List<byte[]> keep = new ArrayList<>();
        List<Marker> marks = new ArrayList<>();
        for (int i = 0; i < 40; i++) keep.add(new byte[1048576]);
        for (int i = 0; i < 40; i++) keep.add(new byte[1048575]);
        for (int i = 0; i < 1000; i++) marks.add(new Marker(i));
        FieldProbe fp = new FieldProbe();
        ready.createNewFile();
        while (!stop.exists()) Thread.sleep(100);
        System.out.println("held " + keep.size() + " " + marks.size() + " " + fp.own);
    }
}
