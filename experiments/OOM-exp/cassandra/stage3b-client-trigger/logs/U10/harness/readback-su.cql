# 3-b confirm U10: read-only instrument reads by the superuser at the start of an attack lifetime (not part of the attack)
LIST ROLES
LIST ALL PERMISSIONS OF u10atk
LIST ALL PERMISSIONS OF u10victim
SELECT name, value FROM system_views.settings
