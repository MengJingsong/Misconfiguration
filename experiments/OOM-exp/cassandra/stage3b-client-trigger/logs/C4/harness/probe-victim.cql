-- victim: SELECT + MODIFY on vks.kv only (a data role on an admin table)
SELECT k FROM vks.kv LIMIT 1
ALTER TABLE vks.kv WITH min_index_interval = 1
CREATE KEYSPACE vx WITH replication = {'class':'SimpleStrategy','replication_factor':1}
