# superuser (default 'cassandra'): system_auth replicated to all three nodes, as the shipped yaml advises for these authenticators (repair follows)
ALTER KEYSPACE system_auth WITH replication = {'class':'NetworkTopologyStrategy','c':3}
