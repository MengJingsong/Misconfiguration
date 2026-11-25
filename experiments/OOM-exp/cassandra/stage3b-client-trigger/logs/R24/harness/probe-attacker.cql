-- 3-b R24 probes as attacker (SELECT + MODIFY on r24.w2k only): every DDL and other tables refused
LIST ALL PERMISSIONS OF attacker;
CREATE KEYSPACE atk WITH replication = {'class':'SimpleStrategy','replication_factor':1};
CREATE TABLE r24.atk (k int PRIMARY KEY, v blob);
ALTER TABLE r24.w2k WITH gc_grace_seconds = 0;
CREATE INDEX ON r24.w2k (v);
SELECT k FROM vks.kv LIMIT 1;
INSERT INTO vks.kv (k, v) VALUES (1, 0x00);
GRANT SELECT ON TABLE vks.kv TO attacker;
SELECT keyspace_name, replication FROM system_schema.keyspaces WHERE keyspace_name = 'r24';
SELECT k, c, v FROM r24.w2k LIMIT 1;
