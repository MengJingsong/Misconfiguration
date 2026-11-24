# superuser, instrumentation only: who is connected to n1 during the attack
SELECT address, port, username, request_count, protocol_version FROM system_views.clients
