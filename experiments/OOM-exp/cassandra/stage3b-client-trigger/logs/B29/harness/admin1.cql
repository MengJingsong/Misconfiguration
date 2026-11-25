# superuser (default 'cassandra'): raise system_auth RF to the ring size, as the shipped yaml advises (repair follows)
ALTER KEYSPACE system_auth WITH replication = {'class':'SimpleStrategy','replication_factor':2}
