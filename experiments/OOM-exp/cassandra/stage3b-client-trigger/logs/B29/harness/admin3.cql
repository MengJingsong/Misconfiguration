# superuser: the attacker's privileges as they stand (no auto-grants: it created nothing)
LIST ALL PERMISSIONS OF attacker
SELECT keyspace_name, replication FROM system_schema.keyspaces
