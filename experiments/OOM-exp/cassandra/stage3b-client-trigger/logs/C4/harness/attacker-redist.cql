-- attacker (diagnostic lifetime): two own tables at interval 1, one also with max_index_interval = 1
CREATE KEYSPACE atk WITH replication = {'class':'SimpleStrategy','replication_factor':1}
CREATE TABLE atk.t1 (pk text PRIMARY KEY, v int) WITH min_index_interval = 1
CREATE TABLE atk.tmax (pk text PRIMARY KEY, v int) WITH min_index_interval = 1 AND max_index_interval = 1
SELECT keyspace_name, table_name, min_index_interval, max_index_interval FROM system_schema.tables WHERE keyspace_name = 'atk'
