import java.nio.ByteBuffer;
import java.io.PrintWriter;
import java.util.SplittableRandom;
import org.apache.cassandra.dht.Murmur3Partitioner;

/**
 * Key generator for the cluster tier (audit amendment 2026-10-28, B3a/B3c).
 * usage: KeyGen window <count> <log2 of ring fraction> <outfile>   -> 16-byte keys whose Murmur3 token lies in [0, 2^(64-f)) (a window of 2^-f of the ring)
 *        KeyGen any <count> 0 <outfile>                            -> 16-byte keys at random over the whole ring
 * Output: one hex key per line; the final line printed is "KEYGEN mode=.. count=.. tried=.. minTok=.. maxTok=..".
 */
public class KeyGen
{
    public static void main(String[] a) throws Exception
    {
        String mode = a[0]; int count = Integer.parseInt(a[1]); int f = Integer.parseInt(a[2]);
        Murmur3Partitioner p = Murmur3Partitioner.instance;
        SplittableRandom r = new SplittableRandom(20261028L + (mode.equals("any") ? 1 : 0));
        long hi = f > 0 ? (1L << (64 - f)) : Long.MAX_VALUE; // window [0, hi)
        long tried = 0, minTok = Long.MAX_VALUE, maxTok = Long.MIN_VALUE; int got = 0;
        byte[] k = new byte[16];
        try (PrintWriter w = new PrintWriter(a[3]))
        {
            while (got < count)
            {
                long x = r.nextLong(), y = r.nextLong();
                for (int i = 0; i < 8; i++) { k[i] = (byte) (x >>> (8 * i)); k[8 + i] = (byte) (y >>> (8 * i)); }
                tried++;
                long t = ((Murmur3Partitioner.LongToken) p.getToken(ByteBuffer.wrap(k))).token;
                if (mode.equals("window") && !(t >= 0 && t < hi)) continue;
                StringBuilder sb = new StringBuilder();
                for (byte b : k) sb.append(String.format("%02x", b));
                w.println(sb);
                got++; minTok = Math.min(minTok, t); maxTok = Math.max(maxTok, t);
            }
        }
        System.out.println("KEYGEN mode=" + mode + " count=" + got + " tried=" + tried + " minTok=" + minTok + " maxTok=" + maxTok
                           + " windowSpanFraction=" + (maxTok - (double) minTok) / Math.scalb(1.0, 64));
    }
}
