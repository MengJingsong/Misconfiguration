/* Stage-4 harness (amended B2a/B2b) of sai_vector_search_max_top_k-execute-pageSize--autonomous. Not upstream code. */
package org.apache.cassandra.index.sai.cql;

public class TopKProbe1500Test extends TopKProbeBase
{
    static
    {
        // amendment B2a: set before IndexWriterConfig is loaded (it loads with the first SAI index)
        System.setProperty("cassandra.sai.vector_search.max_top_k", "1500");
    }

    @Override
    protected int expected()
    {
        return 1500;
    }
}
