# superuser: roles, the only GRANTs, and the admin-made schema (attack table b6.t_blob as in stage 2; the victim's own keyspace)
CREATE ROLE attacker WITH PASSWORD = 'att-pw' AND LOGIN = true AND SUPERUSER = false
CREATE ROLE victim WITH PASSWORD = 'vic-pw' AND LOGIN = true AND SUPERUSER = false
CREATE KEYSPACE b6 WITH replication = {'class':'NetworkTopologyStrategy','c':3}
CREATE TABLE b6.t_blob (pk int PRIMARY KEY, b blob)
GRANT MODIFY ON TABLE b6.t_blob TO attacker
CREATE KEYSPACE vks WITH replication = {'class':'NetworkTopologyStrategy','c':3}
CREATE TABLE vks.kv (k int PRIMARY KEY, v blob)
GRANT SELECT ON TABLE vks.kv TO victim
GRANT MODIFY ON TABLE vks.kv TO victim
LIST ROLES
LIST ALL PERMISSIONS OF attacker
LIST ALL PERMISSIONS OF victim
SELECT keyspace_name, replication FROM system_schema.keyspaces
