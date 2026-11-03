// Expected number of distinct partition keys written by the legacy cassandra-stress write of B3c / C2 / C4 (6)
// (Amendment 2026-10-27 (after run 1, authorised by the user) — B3g C6 I1/I3). Runs cassandra-stress's own key generator
// classes from the run clone, outside any node; reads no file of any run.
//
// What the source determines (cassandra-5.0.9, tools/stress/src/org/apache/cassandra/stress/):
//  - partition key generator: HexBytes("key", GeneratorConfig("randomstrkey", null, fixed(keysize=10), null))
//    (settings/SettingsCommandPreDefined.java:77-82, keysize default 10 at :108); identity distribution default
//    uniform(1..100B) (generate/values/Generator.java:59-62), i.e. UniformRealDistribution over a JDKRandomGenerator
//    (settings/OptionDistribution.java:489-502, DistributionBoundApache.java:40-59), salt = murmur3 of "randomstrkey"
//    (GeneratorConfig.java:39-48), setSeed(seed ^ salt) (Generator.java:51-55).
//  - one key per seed: PartitionIterator.setSeed -> generator.setSeed(seed.seed); generate() (generate/PartitionIterator.java:87-101);
//    HexBytes.generate draws the size seed, then one value, 10 chars ('0'-'9', 'K'-'P': one per 4 bits) from its low 40 bits (generate/values/HexBytes.java:39-55).
//  - seeds: -pop seq=a..b -> SeriesGenerator, seed = (start + (next % totalCount)) * multiplier for next = 0, 1, ...
//    (generate/SeedManager.java:57-69, 156-182); multiplier = 1 + round(10^(22 - log10(sampleSize))), sampleSize from the
//    revisit distribution, default uniform(1..1M) (SeedManager.java:46-54, settings/SettingsInsert.java:62).
//  - exactly n seed fetches for n=<n>: n permits (WorkManager.java:36-55), one seed per permit, reset() of a single-row
//    write always succeeds (operations/PartitionOperation.java:89-119, PartitionIterator.java:140-146); visits fixed(1)
//    (SettingsInsert.java:61) so the revisit sample is never used (SeedManager.java:81, 95-111, PartitionIterator.java:175-176).
// So the set of keys of a load over seq=a..b is {key(i * multiplier) : a <= i <= b}, a deterministic function of the source.
//
// usage: java -cp build/classes/stress:build/classes/main:lib/* StressKeyCount <a>..<b> [<a>..<b> ...]
//   each argument: a seed range; prints the distinct-key count of the union of all ranges given so far.
//   "selftest" as the only argument: known-answer test of the counting (no stress classes involved in the count).
import java.nio.ByteBuffer;
import java.util.Arrays;

import org.apache.cassandra.stress.generate.Distribution;
import org.apache.cassandra.stress.generate.values.GeneratorConfig;
import org.apache.cassandra.stress.generate.values.HexBytes;
import org.apache.cassandra.stress.settings.OptionDistribution;

public class StressKeyCount
{
    static long distinct(long[] a, int n)
    {
        long[] b = Arrays.copyOf(a, n);
        Arrays.parallelSort(b);
        long d = n == 0 ? 0 : 1;
        for (int i = 1; i < n; i++)
            if (b[i] != b[i - 1])
                d++;
        return d;
    }

    public static void main(String[] args)
    {
        if (args.length == 1 && args[0].equals("selftest"))
        {
            long[] t = { 5, 3, 5, 9, 3, 3, 1, 0, 0 };   // distinct {0,1,3,5,9} = 5
            System.out.println("SELFTEST distinct=" + distinct(t, t.length) + " expected=5 " + (distinct(t, t.length) == 5 ? "OK" : "FAIL"));
            return;
        }
        // SeedManager.java:46-54 with the default revisit distribution (SettingsInsert.java:62)
        Distribution tSample = OptionDistribution.get("uniform(1..1M)").get();
        long sampleOffset = Math.min(tSample.minValue(), tSample.maxValue());
        long sampleSize = 1 + Math.max(tSample.minValue(), tSample.maxValue()) - sampleOffset;
        long multiplier = 1 + Math.round(Math.pow(10D, 22 - Math.log10(sampleSize)));
        // SettingsCommandPreDefined.java:80-82, keysize 10
        HexBytes gen = new HexBytes("key", new GeneratorConfig("randomstrkey", null, OptionDistribution.get("fixed(10)"), null));
        System.out.println("MULTIPLIER " + multiplier + " sampleSize " + sampleSize);
        long total = 0;
        long[][] ranges = new long[args.length][];
        for (int r = 0; r < args.length; r++)
        {
            String[] ab = args[r].split("\\.\\.");
            ranges[r] = new long[]{ Long.parseLong(ab[0]), Long.parseLong(ab[1]) };
            total += ranges[r][1] - ranges[r][0] + 1;
        }
        long[] keys = new long[(int) total];
        java.util.HashSet<ByteBuffer> set = total <= 1000000 ? new java.util.HashSet<>() : null;   // cross-check of the encoding
        int n = 0;
        for (int r = 0; r < args.length; r++)
        {
            long a = ranges[r][0], b = ranges[r][1];
            long totalCount = 1 + b - a;
            for (long next = 0; next < totalCount; next++)
            {
                long seed = (a + (next % totalCount)) * multiplier;   // SeedManager.java:181
                gen.setSeed(seed);                                    // PartitionIterator.java:94
                ByteBuffer k = gen.generate();                         // PartitionIterator.java:95
                if (k.remaining() != 10)
                    throw new IllegalStateException("key length " + k.remaining());
                long v = 0;   // HexBytes.java:49-50 writes ('0' + v) for v < 10 and ('A' + v) for v >= 10, i.e. '0'-'9', 'K'-'P':
                for (int j = 0; j < 10; j++)   // 10 chars, 16 symbols each -> 40 bits, injective
                {
                    int c = k.get(k.position() + j);
                    int d = c >= 'A' ? c - 'A' : c - '0';
                    if (d < 0 || d > 15 || (c >= 'A' && d < 10))
                        throw new IllegalStateException("unexpected key byte " + c);
                    v = (v << 4) | d;
                }
                keys[n++] = v;
                if (set != null)
                    set.add(k);
                if (next < 3 || next == totalCount - 1)
                    System.out.println("KEY seq=" + (a + next) + " key=" + new String(Arrays.copyOfRange(k.array(), k.arrayOffset() + k.position(), k.arrayOffset() + k.position() + 10)));
            }
            System.out.println("RANGES-UPTO " + args[r] + " seeds=" + n + " distinct=" + distinct(keys, n) + " lost=" + (n - distinct(keys, n))
                               + (set == null ? "" : " hashset-distinct=" + set.size()));
        }
    }
}
