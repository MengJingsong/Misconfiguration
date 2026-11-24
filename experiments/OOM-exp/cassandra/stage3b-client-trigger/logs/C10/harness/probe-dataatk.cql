# role 'dataatk' (SELECT, MODIFY on adm.t only): no DDL anywhere
CREATE KEYSPACE probe_dr WITH replication = {'class':'SimpleStrategy','replication_factor':1}
CREATE TABLE adm.x (k int PRIMARY KEY)
CREATE INDEX ON adm.t (b)
ALTER KEYSPACE adm WITH replication = {'class':'SimpleStrategy','replication_factor':1}
SELECT pk FROM c10.t LIMIT 1
SELECT k FROM vks.kv LIMIT 1
SELECT pk, b FROM adm.t LIMIT 2
