/*
 * Stage-4 unit tier for super_block_size-flushsuperblock-datablockscnt--autonomous (B2, as amended 2026-10-28, U1-U4).
 * Builds an OnDiskIndexBuilder over N distinct Int32 terms (one key each, fixed seed), calls finish(File), then reads the file
 * tail independently of the builder: level index, data-block offsets, super-block offsets. Parameters (system properties):
 * probe.n, probe.mode (SPARSE|PREFIX), probe.out (file), probe.label. The value of SUPER_BLOCK_SIZE is read by reflection
 * from the loaded class and the class's code source is printed.
 */
package org.apache.cassandra.index.sasi.disk;

import java.io.PrintWriter;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import java.util.Random;

import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.index.sasi.disk.OnDiskIndexBuilder.Mode;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.utils.ByteBufferUtil;

public class SuperBlockProbeTest
{
    @Test
    public void probe() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        int n = Integer.getInteger("probe.n", 200000);
        Mode mode = Mode.valueOf(System.getProperty("probe.mode", "SPARSE"));
        String label = System.getProperty("probe.label", "x");
        PrintWriter out = new PrintWriter(new java.io.FileWriter(System.getProperty("probe.out", "/dev/stdout")), true);
        Runtime rt = Runtime.getRuntime();

        int constant = OnDiskIndexBuilder.class.getField("SUPER_BLOCK_SIZE").getInt(null);
        out.println("PROBE label=" + label + " SUPER_BLOCK_SIZE=" + constant + " source=" + OnDiskIndexBuilder.class.getProtectionDomain().getCodeSource().getLocation()
                    + " n=" + n + " mode=" + mode + " maxHeap=" + rt.maxMemory());

        // N distinct int terms in a shuffled (fixed seed) order, one key each
        int[] vals = new int[n];
        for (int i = 0; i < n; i++) vals[i] = i * 3 + 1;
        Random rnd = new Random(42);
        for (int i = n - 1; i > 0; i--) { int j = rnd.nextInt(i + 1); int t = vals[i]; vals[i] = vals[j]; vals[j] = t; }
        OnDiskIndexBuilder b = new OnDiskIndexBuilder(Int32Type.instance, Int32Type.instance, mode);
        for (int i = 0; i < n; i++)
        {
            DecoratedKey k = Murmur3Partitioner.instance.decorateKey(ByteBufferUtil.bytes("key" + i));
            b.add(ByteBufferUtil.bytes(vals[i]), k, 1000L + i);
        }
        System.gc();
        long liveBefore = rt.totalMemory() - rt.freeMemory();
        java.io.File jf = java.io.File.createTempFile("sbp", ".db", new java.io.File(System.getProperty("probe.tmp", "/tmp")));
        jf.delete();
        long t0 = System.nanoTime();
        b.finish(new File(jf));
        long ms = (System.nanoTime() - t0) / 1000000;
        System.gc();
        long liveAfter = rt.totalMemory() - rt.freeMemory();

        long len = jf.length();
        // tail parse
        long superBlocks = -1, dataBlocks = -1, levels = -1;
        try (RandomAccessFile raf = new RandomAccessFile(jf, "r"))
        {
            raf.seek(len - 8);
            long levelIdx = raf.readLong();
            raf.seek(levelIdx);
            levels = raf.readInt();
            for (int i = 0; i < levels; i++) { int c = raf.readInt(); raf.skipBytes(c * 8); }
            dataBlocks = raf.readInt();
            raf.skipBytes((int) dataBlocks * 8);
            if (mode == Mode.SPARSE) { superBlocks = raf.readInt(); raf.skipBytes((int) superBlocks * 8); }
            long pos = raf.getFilePointer();
            out.println("TAIL levelIndexPosition=" + levelIdx + " endOfParsedMetadata=" + pos + " fileLengthMinus8=" + (len - 8)
                        + " parsedToEnd=" + (pos == len - 8));
        }
        MessageDigest md = MessageDigest.getInstance("MD5");
        byte[] bytes = java.nio.file.Files.readAllBytes(jf.toPath());
        StringBuilder hex = new StringBuilder();
        for (byte x : md.digest(bytes)) hex.append(String.format("%02x", x));
        long expectedSuper = mode == Mode.SPARSE ? (dataBlocks - 1) / constant + 1 : -1;
        out.println("RESULT label=" + label + " constant=" + constant + " n=" + n + " mode=" + mode + " dataBlocks=" + dataBlocks + " levels=" + levels
                    + " superBlocks=" + superBlocks + " expectedSuperBlocksFormula=" + expectedSuper + " formulaMatches=" + (superBlocks == expectedSuper)
                    + " fileBytes=" + len + " md5=" + hex + " liveHeapBeforeFinish=" + liveBefore + " liveHeapAfterFinish=" + liveAfter
                    + " finishMs=" + ms + " estimatedMemoryUse=" + b.estimatedMemoryUse());
        jf.delete();
        out.close();
    }
}
