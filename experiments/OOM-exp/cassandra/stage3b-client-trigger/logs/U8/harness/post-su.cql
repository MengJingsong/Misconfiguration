# read-only instrument reads by the superuser after the attacker's load (not part of the attack)
LIST ALL PERMISSIONS OF u8atk
SELECT keyspace_name, table_name, column_name, type FROM system_schema.columns WHERE keyspace_name = 'u8'
