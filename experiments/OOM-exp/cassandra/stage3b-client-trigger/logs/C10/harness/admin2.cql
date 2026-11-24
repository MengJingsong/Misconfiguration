# superuser: roles, the only GRANTs, and the victim's admin-made schema
CREATE ROLE attacker WITH PASSWORD = 'att-pw' AND LOGIN = true AND SUPERUSER = false
CREATE ROLE victim WITH PASSWORD = 'vic-pw' AND LOGIN = true AND SUPERUSER = false
CREATE ROLE nogrant WITH PASSWORD = 'nog-pw' AND LOGIN = true AND SUPERUSER = false
GRANT CREATE ON ALL KEYSPACES TO attacker
CREATE KEYSPACE vks WITH replication = {'class':'SimpleStrategy','replication_factor':3}
CREATE TABLE vks.kv (k int PRIMARY KEY, v blob)
GRANT SELECT ON TABLE vks.kv TO victim
GRANT MODIFY ON TABLE vks.kv TO victim
LIST ROLES
LIST ALL PERMISSIONS OF attacker
LIST ALL PERMISSIONS OF victim
LIST ALL PERMISSIONS OF nogrant
