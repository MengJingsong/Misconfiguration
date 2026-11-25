package org.apache.cassandra.utils.binlog;

import java.io.File; // checkstyle: permit this import
import java.lang.reflect.Field;
import java.nio.file.*;
import java.util.*;
import java.util.stream.*;
import org.junit.*;
import org.apache.cassandra.config.DatabaseDescriptor;

public class DeletingArchiverBoundTest
{
    static final long MiB = 1L << 20;

    @BeforeClass public static void init() { DatabaseDescriptor.daemonInitialization(); }

    static long env(String k, long d) { String v = System.getenv(k); return v == null ? d : Long.parseLong(v); }
    static List<Path> cq4(Path dir) throws Exception
    {
        try (Stream<Path> s = Files.list(dir)) { return s.filter(p -> p.toString().endsWith(".cq4")).sorted().collect(Collectors.toList()); }
    }
    static long sum(List<Path> ps) { long t = 0; for (Path p : ps) t += p.toFile().length(); return t; }
    @SuppressWarnings("unchecked")
    static Queue<File> tracked(DeletingArchiver da) throws Exception
    { Field f = DeletingArchiver.class.getDeclaredField("chronicleStoreFiles"); f.setAccessible(true); return (Queue<File>) f.get(da); }

    /** A: synthetic 1 MiB files, three limits. A4: delete-failure branch. */
    @Test public void synthetic() throws Exception
    {
        Path base = Paths.get(System.getenv("O72_DIR"));
        for (long limit : new long[]{ 512 * 1024, 7 * MiB / 2, 10 * MiB })
        {
            Path dir = Files.createDirectories(base.resolve("A-" + limit));
            DeletingArchiver da = new DeletingArchiver(limit);
            for (int i = 0; i < 20; i++)
            {
                Path p = dir.resolve(String.format("f%02d.cq4", i));
                Files.write(p, new byte[(int) MiB]);
                da.onReleased(i, p.toFile());
                List<Path> on = cq4(dir);
                System.out.printf("O72A limit=%d step=%d operand=%d onDisk=%d files=%d%n", limit, i, da.getBytesInStoreFiles(), sum(on), on.size());
            }
        }
        // A4: an undeletable file (its directory read-only) in the middle of the stream
        Path ok = Files.createDirectories(base.resolve("A4-ok")), ro = Files.createDirectories(base.resolve("A4-ro"));
        DeletingArchiver da = new DeletingArchiver(7 * MiB / 2);
        for (int i = 0; i < 12; i++)
        {
            Path d = (i == 0) ? ro : ok;
            Path p = d.resolve(String.format("g%02d.cq4", i));
            Files.write(p, new byte[(int) MiB]);
            if (i == 0) ro.toFile().setWritable(false);
            da.onReleased(i, p.toFile());
            System.out.printf("O72A4 step=%d operand=%d onDiskOk=%d onDiskRo=%d tracked=%d%n", i, da.getBytesInStoreFiles(), sum(cq4(ok)), sum(cq4(ro)), tracked(da).size());
        }
        ro.toFile().setWritable(true);
    }

    /** B: real BinLog with TEST_SECONDLY roll; limit from O72_LIMIT; ~2 MiB/s for O72_SECONDS. */
    @Test public void realBinLog() throws Exception
    {
        long limit = env("O72_LIMIT", 1L << 30);
        long seconds = env("O72_SECONDS", 40);
        Path dir = Files.createDirectories(Paths.get(System.getenv("O72_DIR")).resolve("B-" + limit));
        BinLog bl = new BinLog.Builder().path(dir).rollCycle("TEST_SECONDLY").maxQueueWeight(256 * 1024 * 1024)
                                        .maxLogSize(limit).blocking(true).build(false);
        Field af = BinLog.class.getDeclaredField("archiver"); af.setAccessible(true);
        DeletingArchiver da = (DeletingArchiver) af.get(bl);
        char[] c = new char[64 * 1024]; Arrays.fill(c, 'a'); String payload = new String(c);
        Map<String, Long> firstSeen = new HashMap<>();
        long end = System.currentTimeMillis() + seconds * 1000, maxOperand = 0, maxRolled = 0, maxTotal = 0;
        while (System.currentTimeMillis() < end)
        {
            for (int i = 0; i < 6; i++) bl.put(BinLogTest.record(payload));   // 6 x 64 KiB per 200 ms = ~1.9 MiB/s
            Thread.sleep(200);
            List<Path> on = cq4(dir);
            List<Path> rolled = on.isEmpty() ? on : on.subList(0, on.size() - 1);
            long operand = da.getBytesInStoreFiles(), r = sum(rolled), t = sum(on);
            for (File f : tracked(da)) firstSeen.putIfAbsent(f.getName(), f.length());
            maxOperand = Math.max(maxOperand, operand); maxRolled = Math.max(maxRolled, r); maxTotal = Math.max(maxTotal, t);
            System.out.printf("O72B limit=%d t=%d operand=%d tracked=%d rolledOnDisk=%d totalOnDisk=%d files=%d%n",
                              limit, System.currentTimeMillis(), operand, tracked(da).size(), r, t, on.size());
        }
        for (File f : tracked(da))
            System.out.printf("O72B-LEN file=%s lenAtFirstSeen=%d lenNow=%d%n", f.getName(), firstSeen.getOrDefault(f.getName(), -1L), f.length());
        System.out.printf("O72B-MAX limit=%d maxOperand=%d maxRolled=%d maxTotal=%d%n", limit, maxOperand, maxRolled, maxTotal);
        bl.stop();
    }
}
