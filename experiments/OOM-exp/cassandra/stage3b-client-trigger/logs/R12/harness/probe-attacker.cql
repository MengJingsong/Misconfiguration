-- run as role `attacker` before the seed load: what it may and may not do
LIST ALL PERMISSIONS OF attacker
SELECT k, c FROM r12.t WHERE k = 1 LIMIT 1
INSERT INTO r12.t (k, c, v) VALUES (-1, 0, 0x00)
DELETE FROM r12.t WHERE k = -1
SELECT k FROM vks.t LIMIT 1
INSERT INTO vks.t (k, v) VALUES (5000, 0x00)
CREATE KEYSPACE ak WITH replication = {'class':'SimpleStrategy','replication_factor':1}
CREATE TABLE r12.x (k int PRIMARY KEY)
CREATE INDEX ON r12.t (v)
ALTER TABLE r12.t ADD z int
DROP TABLE r12.t
CREATE ROLE x WITH LOGIN = true
GRANT SELECT ON TABLE vks.t TO attacker
