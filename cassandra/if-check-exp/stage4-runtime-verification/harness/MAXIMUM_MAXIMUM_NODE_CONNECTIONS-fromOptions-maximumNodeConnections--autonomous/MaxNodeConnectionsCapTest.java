/*
 * Stage-4 harness, unit tier (B2, as amended 2026-10-26) of
 * MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous.
 * Not upstream code. Copied by unit-run.sh into
 * test/unit/org/apache/cassandra/index/sai/disk/v1/ of the run clone and removed after the run.
 *
 * Test A (CQLTester): CREATE CUSTOM INDEX ... WITH OPTIONS = {'maximum_node_connections': M}
 *   for M in {16, 64, 256, 512, 513, 1024}; one fresh table per M; prints accepted/rejected and the root cause.
 * Test B (jvector directly): for (M, beam) in {(16,100),(64,100),(256,100),(512,100),(16,400)}:
 *   GraphIndexBuilder(ravv, FLOAT32, COSINE, M, beam, 1.2f, 1.4f) over N vectors (dim 8, Random(42), unit length),
 *   sum of addGraphNode(i, ravv) for i in 0..N-1, complete(), OnDiskGraphIndex.write to a temp file, Files.size.
 * Every reading is one stdout line starting "PROBE "; the test never fails on a reading (the run records, the
 * self-check judges). N defaults to 5000; the environment variable MNC_N overrides it (shakedown only).
 */
package org.apache.cassandra.index.sai.disk.v1;

import java.io.BufferedOutputStream;
import java.io.DataOutputStream;
import java.io.FileOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

import org.junit.Test;

import io.github.jbellis.jvector.disk.OnDiskGraphIndex;
import io.github.jbellis.jvector.graph.GraphIndexBuilder;
import io.github.jbellis.jvector.graph.ListRandomAccessVectorValues;
import io.github.jbellis.jvector.graph.OnHeapGraphIndex;
import io.github.jbellis.jvector.vector.VectorEncoding;
import io.github.jbellis.jvector.vector.VectorSimilarityFunction;
import org.apache.cassandra.config.CassandraRelevantProperties;
import org.apache.cassandra.cql3.CQLTester;

public class MaxNodeConnectionsCapTest extends CQLTester
{
    static
    {
        // amended B2a: the filed fallback; the property is read on every fromOptions call (IndexWriterConfig.java:120)
        System.setProperty("cassandra.sai.vector.allow_custom_parameters", "true");
    }

    static final int DIM = 8;
    static final int N = System.getenv("MNC_N") == null ? 5000 : Integer.parseInt(System.getenv("MNC_N"));
    static final int[] A_VALUES = { 16, 64, 256, 512, 513, 1024 };
    static final int[][] B_CASES = { { 16, 100 }, { 64, 100 }, { 256, 100 }, { 512, 100 }, { 16, 400 } };

    static void out(String s)
    {
        System.out.println("PROBE " + s);
        System.out.flush();
    }

    static Throwable root(Throwable t)
    {
        while (t.getCause() != null && t.getCause() != t)
            t = t.getCause();
        return t;
    }

    @Test
    public void capAndGraphBytes() throws Throwable
    {
        out("PROP allow_custom_parameters=" + CassandraRelevantProperties.SAI_VECTOR_ALLOW_CUSTOM_PARAMETERS.getBoolean()
            + " MAXIMUM_MAXIMUM_NODE_CONNECTIONS=" + IndexWriterConfig.MAXIMUM_MAXIMUM_NODE_CONNECTIONS
            + " DEFAULT_MAXIMUM_NODE_CONNECTIONS=" + IndexWriterConfig.DEFAULT_MAXIMUM_NODE_CONNECTIONS
            + " N=" + N + " dim=" + DIM);

        // ---- Test A ----
        for (int m : A_VALUES)
        {
            createTable("CREATE TABLE %s (pk int PRIMARY KEY, v vector<float, 8>)");
            String q = "CREATE CUSTOM INDEX ON %s(v) USING 'StorageAttachedIndex' WITH OPTIONS = {'maximum_node_connections':'" + m + "'}";
            try
            {
                String name = createIndex(q);
                out("A M=" + m + " result=accepted index=" + name);
            }
            catch (Throwable t)
            {
                Throwable r = root(t);
                out("A M=" + m + " result=rejected outer=" + t.getClass().getSimpleName() + " root=" + r.getClass().getSimpleName()
                    + " msg=" + String.valueOf(r.getMessage()).replace('\n', ' '));
            }
        }

        // ---- Test B ----
        List<float[]> vectors = new ArrayList<>(N);
        Random rnd = new Random(42);
        for (int i = 0; i < N; i++)
        {
            float[] v = new float[DIM];
            double norm = 0;
            for (int d = 0; d < DIM; d++)
            {
                v[d] = rnd.nextFloat() * 2 - 1;
                norm += (double) v[d] * v[d];
            }
            float inv = (float) (1.0 / Math.sqrt(norm));
            for (int d = 0; d < DIM; d++)
                v[d] *= inv;
            vectors.add(v);
        }
        long checksum = 0;
        for (float[] v : vectors)
            for (float f : v)
                checksum = checksum * 31 + Float.floatToIntBits(f);
        out("VECTORS n=" + vectors.size() + " checksum=" + checksum);

        for (int[] c : B_CASES)
        {
            int m = c[0], beam = c[1];
            ListRandomAccessVectorValues ravv = new ListRandomAccessVectorValues(vectors, DIM);
            GraphIndexBuilder<float[]> builder = new GraphIndexBuilder<>(ravv, VectorEncoding.FLOAT32, VectorSimilarityFunction.COSINE,
                                                                         m, beam, 1.2f, 1.4f);
            long sumAdd = 0;
            for (int i = 0; i < N; i++)
                sumAdd += builder.addGraphNode(i, ravv);
            builder.complete();
            OnHeapGraphIndex<float[]> graph = builder.getGraph();
            int maxNeighbours = 0;
            long totalNeighbours = 0;
            for (int i = 0; i < graph.size(); i++)
            {
                int s = graph.getNeighbors(i).size();
                maxNeighbours = Math.max(maxNeighbours, s);
                totalNeighbours += s;
            }
            Path tmp = Files.createTempFile("mnc-graph-M" + m + "-b" + beam + "-", ".bin");
            try (DataOutputStream dos = new DataOutputStream(new BufferedOutputStream(new FileOutputStream(tmp.toFile()))))
            {
                OnDiskGraphIndex.write(graph, ravv, dos);
            }
            long fileBytes = Files.size(tmp);
            boolean deleted = Files.deleteIfExists(tmp);
            out("B M=" + m + " beam=" + beam + " n=" + N + " dim=" + DIM + " graphSize=" + graph.size() + " maxDegree=" + graph.maxDegree()
                + " sumAddBytes=" + sumAdd + " fileBytes=" + fileBytes + " maxNeighboursAfterComplete=" + maxNeighbours
                + " meanNeighbours=" + String.format("%.2f", totalNeighbours / (double) graph.size())
                + " tmpDeleted=" + deleted);
        }
        out("END");
    }
}
