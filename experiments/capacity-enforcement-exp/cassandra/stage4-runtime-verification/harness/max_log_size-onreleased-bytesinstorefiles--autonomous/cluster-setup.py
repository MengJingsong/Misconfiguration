#!/usr/bin/env python3
"""o72 cluster tier: edit $RUN/src/conf/cassandra.yaml per B3a (literal paths). Usage: cluster-setup.py <RUN>"""
import re, sys
RUN = sys.argv[1]
f = f'{RUN}/src/conf/cassandra.yaml'
y = open(f).read()
def sub(pat, rep):
    global y
    y2, n = re.subn(pat, rep, y, count=1, flags=re.M)
    assert n == 1, pat
    y = y2
sub(r'^# data_file_directories:\n#\s*- /var/lib/cassandra/data', f'data_file_directories:\n    - {RUN}/data')
sub(r'^# commitlog_directory: .*$', f'commitlog_directory: {RUN}/commitlog')
sub(r'^# hints_directory: .*$', f'hints_directory: {RUN}/hints')
sub(r'^# saved_caches_directory: .*$', f'saved_caches_directory: {RUN}/saved_caches')
sub(r'^# cdc_raw_directory: .*$', f'cdc_raw_directory: {RUN}/cdc_raw')
sub(r'^auto_snapshot: true$', 'auto_snapshot: false')
sub(r'^# full_query_logging_options:\n', f'full_query_logging_options:\n  log_dir: {RUN}/fql\n  allow_nodetool_archive_command: true\n')
open(f, 'w').write(y)
print('edited', f)
