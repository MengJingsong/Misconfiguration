import re, sys
T = sys.argv[1]
p = T + '/conf/cassandra.yaml'; y = open(p).read()
for k, v in [('native_transport_port', '19142'), ('storage_port', '17100'), ('ssl_storage_port', '17101'),
             ('listen_address', '127.0.0.1'), ('rpc_address', '127.0.0.1')]:
    y, n = re.subn(r'(?m)^%s:.*$' % k, '%s: %s' % (k, v), y); assert n == 1, k
y, n = re.subn(r'(?m)^(\s*- seeds:).*$', r'\1 "127.0.0.1:17100"', y); assert n == 1
open(p, 'w').write(y)
p = T + '/conf/cassandra-env.sh'; e = open(p).read()
e, n = re.subn(r'(?m)^JMX_PORT="7199"', 'JMX_PORT="17199"', e); assert n == 1 or 'JMX_PORT="17199"' in e
open(p, 'w').write(e)
print('conf edited')
