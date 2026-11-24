# superuser, after the attacker made its schema: what the attacker holds now (creator auto-grants)
LIST ALL PERMISSIONS OF attacker
SELECT keyspace_name, replication FROM system_schema.keyspaces WHERE keyspace_name = 'c10'
