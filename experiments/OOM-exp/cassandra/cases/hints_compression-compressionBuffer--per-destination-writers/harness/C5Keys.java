// C5 stage 2: one int key per dc2 range. dc2 node j has token T_j = -2^63 + j*2^58 + 2^57 (j = 0..63);
// range j = (T_{j-1}, T_j] (j = 0 wraps). The Murmur3 token of an int key is hash3_x64_128 of its 4-byte
// big-endian serialization, word 0, with Long.MIN_VALUE mapped to Long.MAX_VALUE (Murmur3Partitioner).
// Prints "range key token" for j = 0..63 (smallest k >= 0 in each range).
import java.nio.ByteBuffer;
import org.apache.cassandra.utils.MurmurHash;

public class C5Keys {
    static long tok(int k) {
        ByteBuffer b = ByteBuffer.allocate(4); b.putInt(0, k);
        long[] h = new long[2]; MurmurHash.hash3_x64_128(b, 0, 4, 0, h);
        return h[0] == Long.MIN_VALUE ? Long.MAX_VALUE : h[0];
    }
    static long T(int j) { return Long.MIN_VALUE + (long) j * (1L << 58) + (1L << 57); }
    static int range(long t) {           // smallest j with t <= T_j, else wraps to 0
        for (int j = 0; j < 64; j++) if (t <= T(j)) return j;
        return 0;
    }
    public static void main(String[] a) {
        int[] key = new int[64]; long[] tk = new long[64]; java.util.Arrays.fill(key, -1); int found = 0;
        for (int k = 0; found < 64; k++) {
            long t = tok(k); int r = range(t);
            if (key[r] < 0) { key[r] = k; tk[r] = t; found++; }
        }
        for (int j = 0; j < 64; j++) System.out.println(j + " " + key[j] + " " + tk[j]);
    }
}
