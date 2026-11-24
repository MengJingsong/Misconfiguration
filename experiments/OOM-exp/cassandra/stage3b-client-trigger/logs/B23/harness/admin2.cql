-- superuser, step 2: the two login roles, the admin-made schema, and the grants (nothing else is granted)
CREATE ROLE attacker WITH PASSWORD = 'atk-pw-3b' AND LOGIN = true AND SUPERUSER = false;
CREATE ROLE victim WITH PASSWORD = 'vic-pw-3b' AND LOGIN = true AND SUPERUSER = false;
CREATE KEYSPACE app WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 2};
CREATE TABLE app.data (key blob PRIMARY KEY, v blob);
GRANT MODIFY ON TABLE app.data TO attacker;
CREATE KEYSPACE vks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 2};
CREATE TABLE vks.t (k int PRIMARY KEY, v blob);
GRANT SELECT ON TABLE vks.t TO victim;
GRANT MODIFY ON TABLE vks.t TO victim;
LIST ROLES;
LIST ALL PERMISSIONS OF attacker;
LIST ALL PERMISSIONS OF victim;
