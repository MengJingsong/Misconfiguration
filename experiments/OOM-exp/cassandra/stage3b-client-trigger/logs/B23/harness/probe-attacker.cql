-- as attacker: what the role can and cannot do (expected: the two system reads and the INSERT OK, the rest Unauthorized)
SELECT peer, data_center FROM system.peers;
SELECT keyspace_name, replication FROM system_schema.keyspaces WHERE keyspace_name = 'app';
INSERT INTO app.data (key, v) VALUES (0x00, 0x00);
SELECT key FROM app.data LIMIT 1;
SELECT k FROM vks.t LIMIT 1;
INSERT INTO vks.t (k, v) VALUES (1, 0x00);
CREATE KEYSPACE atk WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 2};
CREATE TABLE app.extra (k int PRIMARY KEY);
ALTER TABLE app.data WITH gc_grace_seconds = 0;
LIST ALL PERMISSIONS OF attacker;
