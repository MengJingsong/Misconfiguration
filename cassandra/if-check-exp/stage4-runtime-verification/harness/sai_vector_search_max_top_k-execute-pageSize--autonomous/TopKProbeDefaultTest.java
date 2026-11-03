/* Stage-4 harness (amended B2a/B2b) of sai_vector_search_max_top_k-execute-pageSize--autonomous. Not upstream code. */
package org.apache.cassandra.index.sai.cql;

public class TopKProbeDefaultTest extends TopKProbeBase
{
    // the default class sets nothing: CassandraRelevantProperties.java:479 default "1000"

    @Override
    protected int expected()
    {
        return 1000;
    }
}
