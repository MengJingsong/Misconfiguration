-- expected refused: no CREATE/ALTER/AUTHORIZE, no access to the victim's table
CREATE KEYSPACE atk WITH replication = {'class':'SimpleStrategy','replication_factor':1};
CREATE TABLE u4.t2 (k int PRIMARY KEY, v blob);
ALTER TABLE u4.t WITH comment = 'x';
CREATE INDEX ON u4.t (v);
SELECT k FROM vks.kv LIMIT 1;
INSERT INTO vks.kv (k, v) VALUES (1, 0x00);
GRANT SELECT ON TABLE vks.kv TO attacker;
ALTER ROLE attacker WITH SUPERUSER = true;
-- expected allowed
INSERT INTO u4.t (pk, ck, v) VALUES (99, 0, 0x00);
DELETE FROM u4.t WHERE pk = 99;
SELECT pk, ck FROM u4.t WHERE pk = 0 LIMIT 1;
SELECT release_version, tokens FROM system.local;
LIST ALL PERMISSIONS OF attacker;
