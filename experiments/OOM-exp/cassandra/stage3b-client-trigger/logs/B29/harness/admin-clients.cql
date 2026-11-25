# role nogrant via node 2 (the default superuser cassandra reads its role at QUORUM: refused with node 1 down): who is connected (attribution, operator view)
SELECT address, port, username, driver_name, request_count FROM system_views.clients
