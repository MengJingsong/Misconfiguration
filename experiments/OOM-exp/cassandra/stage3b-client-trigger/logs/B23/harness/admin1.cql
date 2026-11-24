-- superuser, step 1: system_auth replicated to all three nodes (operator practice) so logins work with one node down
ALTER KEYSPACE system_auth WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 3};
