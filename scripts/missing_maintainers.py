#!/usr/bin/env python

# missing_maintainers.py - List community supported modules without maintainers.
#
#   * Uses the ModuleIndexer to get the list of modules and their meta
#

from lib.triagers.ansible import AnsibleTriage

AT = AnsibleTriage(args={})

mkeys = sorted(AT.module_indexer.modules.keys())
for mkey in mkeys:
    v = AT.module_indexer.modules[mkey]
    if v.get('deprecated') is True:
        continue
    if v['metadata']:
        if 'supported_by' not in v['metadata']:
            #import epdb; epdb.st()
            continue
        if v['metadata']['supported_by'] != 'community':
            continue
        if not v['maintainers'] or v['maintainers'] == ['ansible']:
            print(
                '%s,%s,%s,%s' %
                (
                    mkey,
                    v['metadata']['supported_by'],
                    v['maintainers'],
                    v['authors']
                )
            )
