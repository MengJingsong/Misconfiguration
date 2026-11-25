-- nogrant: login role, no grants
CREATE KEYSPACE ng WITH replication = {'class':'SimpleStrategy','replication_factor':1}
SELECT k FROM vks.kv LIMIT 1
SELECT keyspace_name, table_name, min_index_interval, max_index_interval FROM system_schema.tables WHERE keyspace_name = 'vks'
