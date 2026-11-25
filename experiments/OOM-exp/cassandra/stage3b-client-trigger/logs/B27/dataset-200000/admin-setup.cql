CREATE KEYSPACE victim WITH replication = {'class':'SimpleStrategy','replication_factor':1};
CREATE TABLE victim.kv (k int PRIMARY KEY, v text);
CREATE ROLE attacker WITH PASSWORD = 'atkpw' AND LOGIN = true;
GRANT SELECT ON TABLE ks.t TO attacker;
CREATE ROLE nogrant WITH PASSWORD = 'ngpw' AND LOGIN = true;
CREATE ROLE victim WITH PASSWORD = 'vicpw' AND LOGIN = true;
GRANT SELECT ON TABLE victim.kv TO victim;
GRANT MODIFY ON TABLE victim.kv TO victim;
