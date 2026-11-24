# superuser (default 'cassandra'): raise system_auth RF as the shipped yaml comments advise (repair follows)
ALTER KEYSPACE system_auth WITH replication = {'class':'SimpleStrategy','replication_factor':3}
