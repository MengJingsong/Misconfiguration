-- 3-b R24 admin step 1 (superuser cassandra): system_auth to RF 2 (the shipped yaml's advice for these authenticators), then repair -full on both nodes
ALTER KEYSPACE system_auth WITH replication = {'class':'SimpleStrategy','replication_factor':2};
