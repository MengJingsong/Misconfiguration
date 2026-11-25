-- admin (default superuser cassandra; this setup only). Single node: system_auth keeps its shipped RF 1.
CREATE ROLE attacker WITH PASSWORD = 'att-pw' AND LOGIN = true AND SUPERUSER = false
CREATE ROLE victim WITH PASSWORD = 'vic-pw' AND LOGIN = true AND SUPERUSER = false
CREATE ROLE nogrant WITH PASSWORD = 'ng-pw' AND LOGIN = true AND SUPERUSER = false
GRANT CREATE ON ALL KEYSPACES TO attacker
CREATE KEYSPACE vks WITH replication = {'class':'SimpleStrategy','replication_factor':1}
CREATE TABLE vks.kv (k int PRIMARY KEY, v blob)
GRANT SELECT ON TABLE vks.kv TO victim
GRANT MODIFY ON TABLE vks.kv TO victim
LIST ROLES
LIST ALL PERMISSIONS OF attacker
LIST ALL PERMISSIONS OF victim
LIST ALL PERMISSIONS OF nogrant
