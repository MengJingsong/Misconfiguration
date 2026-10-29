import java.nio.ByteBuffer;
import java.util.Random;

import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.utils.MurmurHash;

/**
 * Collision keys for case B3 (amendment C1). usage: java CollKeys <t tokens> <g keys per token> <extra rows> <out.cql>
 * For token T_j (j = 1..t) and k = 1..g, key = the 16 bytes returned by MurmurHash.inv_hash3_x64_128({T_j, h2 = k}); its Murmur3
 * hash is (T_j, k), so its token is T_j for every k. Each key is checked with Murmur3Partitioner.instance.getToken before it is
 * written. Writes "INSERT INTO ks.t (pk, v) VALUES (0x.., 'x');" lines, plus <extra> ordinary random 16-byte keys (seed 7).
 * Prints "KEYCHECK" lines and a "COLLISION-GROUPS" line (token, count) that the run script compares with SELECT token(pk) on the node.
 */
public class CollKeys
{
    static String hex(ByteBuffer b)
    {
        StringBuilder s = new StringBuilder("0x");
        for (int i = b.position(); i < b.limit(); i++) s.append(String.format("%02x", b.get(i)));
        return s.toString();
    }

    public static void main(String[] a) throws Exception
    {
        int t = Integer.parseInt(a[0]), g = Integer.parseInt(a[1]), extra = Integer.parseInt(a[2]);
        try (java.io.PrintWriter w = new java.io.PrintWriter(a[3]))
        {
            StringBuilder groups = new StringBuilder();
            int bad = 0;
            for (int j = 1; j <= t; j++)
            {
                long token = 1_000_000_007L * j;
                for (int k = 1; k <= g; k++)
                {
                    long[] inv = MurmurHash.inv_hash3_x64_128(new long[]{ token, k });
                    ByteBuffer key = ByteBuffer.allocate(16);
                    key.putLong(inv[0]).putLong(inv[1]).position(0);
                    long got = ((Long) Murmur3Partitioner.instance.getToken(key).getTokenValue());
                    if (got != token) bad++;
                    System.out.println("KEYCHECK group=" + j + " k=" + k + " key=" + hex(key) + " wantToken=" + token + " gotToken=" + got + (got == token ? " ok" : " MISMATCH"));
                    w.println("INSERT INTO ks.t (pk, v) VALUES (" + hex(key) + ", 'x');");
                }
                groups.append(token).append(':').append(g).append(' ');
            }
            Random r = new Random(7);
            for (int i = 0; i < extra; i++)
            {
                byte[] b = new byte[16]; r.nextBytes(b);
                w.println("INSERT INTO ks.t (pk, v) VALUES (" + hex(ByteBuffer.wrap(b)) + ", 'x');");
            }
            System.out.println("COLLISION-GROUPS " + groups.toString().trim() + " mismatches=" + bad);
        }
    }
}
