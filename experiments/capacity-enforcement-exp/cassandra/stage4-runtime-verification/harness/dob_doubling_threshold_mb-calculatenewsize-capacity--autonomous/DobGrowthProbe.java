package org.apache.cassandra.io.util;

import java.nio.BufferOverflowException;
import java.nio.ByteBuffer;

public class DobGrowthProbe
{
    static long prev = -1;
    // usage: DobGrowthProbe <mode: bytes|rows|fixed> <n: MiB for bytes/fixed, row count for rows>
    public static void main(String[] a) throws Exception
    {
        String mode = a[0];
        long n = Long.parseLong(a[1]);
        System.out.println("DOUBLING_THRESHOLD_MB=" + DataOutputBuffer.DOUBLING_THRESHOLD);
        DataOutputBuffer dob;
        if (mode.equals("fixed"))
            dob = new DataOutputBufferFixed(1 << 20);
        else
            dob = new DataOutputBuffer()
            {
                @Override
                protected void expandToFit(long count)
                {
                    long before = capacity();
                    super.expandToFit(count);
                    long after = capacity();
                    System.out.printf("EXPAND count=%d %d -> %d ratio=%.4f transient=%d%n",
                                      count, before, after, (double) after / before, before + after);
                }
            };
        System.out.println("INITIAL capacity=" + dob.capacity());
        try
        {
            if (mode.equals("rows"))
            {
                dob.write(new byte[40]);                        // "partition header"
                byte[] rowHdr = new byte[12];
                ByteBuffer value = ByteBuffer.allocate(1 << 20); // 1 MiB cell value
                for (long i = 0; i < n; i++)
                {
                    dob.write(rowHdr);
                    dob.write(value.duplicate());
                }
            }
            else
            {
                byte[] chunk = new byte[65536];
                for (long w = 0; w < (n << 20); w += chunk.length)
                    dob.write(chunk);
            }
        }
        catch (BufferOverflowException e)
        {
            System.out.println("OVERFLOW position=" + dob.position() + " capacity=" + dob.capacity());
        }
        System.out.printf("FINAL written=%d capacity=%d ratio=%.4f%n",
                          dob.position(), dob.capacity(), (double) dob.capacity() / Math.max(1, dob.position()));
    }
}
