-- 3-b confirm U4: admin setup as the default superuser 'cassandra' (single node: system_auth RF 1 is the whole ring).
CREATE KEYSPACE u4 WITH replication = {'class':'SimpleStrategy','replication_factor':1};
CREATE TABLE u4.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck));
CREATE ROLE attacker WITH PASSWORD = 'att-pw' AND LOGIN = true AND SUPERUSER = false;
CREATE ROLE reader WITH PASSWORD = 'rd-pw' AND LOGIN = true AND SUPERUSER = false;
CREATE ROLE nogrant WITH PASSWORD = 'ng-pw' AND LOGIN = true AND SUPERUSER = false;
CREATE ROLE victim WITH PASSWORD = 'vic-pw' AND LOGIN = true AND SUPERUSER = false;
GRANT SELECT ON TABLE u4.t TO attacker;
GRANT MODIFY ON TABLE u4.t TO attacker;
GRANT SELECT ON TABLE u4.t TO reader;
CREATE KEYSPACE vks WITH replication = {'class':'SimpleStrategy','replication_factor':1};
CREATE TABLE vks.kv (k int PRIMARY KEY, v blob);
GRANT SELECT ON TABLE vks.kv TO victim;
GRANT MODIFY ON TABLE vks.kv TO victim;
LIST ALL PERMISSIONS OF attacker;
LIST ALL PERMISSIONS OF reader;
LIST ALL PERMISSIONS OF nogrant;
LIST ALL PERMISSIONS OF victim;
LIST ROLES;
