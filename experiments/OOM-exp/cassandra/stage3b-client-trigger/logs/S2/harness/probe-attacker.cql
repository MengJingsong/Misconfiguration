# as attacker (MODIFY on b6.t_blob only): what it can and cannot do
SELECT key, release_version, tokens FROM system.local
SELECT peer, data_center, tokens FROM system.peers
INSERT INTO b6.t_blob (pk, b) VALUES (-1, 0x00)
SELECT pk FROM b6.t_blob LIMIT 1
SELECT k FROM vks.kv LIMIT 1
INSERT INTO vks.kv (k, v) VALUES (-1, 0x00)
CREATE KEYSPACE atk WITH replication = {'class':'SimpleStrategy','replication_factor':1}
CREATE TABLE b6.t2 (pk int PRIMARY KEY)
ALTER TABLE b6.t_blob WITH gc_grace_seconds = 0
GRANT MODIFY ON TABLE vks.kv TO attacker
LIST ALL PERMISSIONS OF attacker
