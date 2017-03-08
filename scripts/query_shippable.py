#!/usr/bin/env python

# Fetch and parse all test results from shippable

import logging
import os
import sys

from pprint import pprint
from lib.utils.shippable_api import ShippableRuns

spath = os.path.expanduser('~/.ansibullbot/cache/shippable.runs')
SR = ShippableRuns(cache=False, cachedir=spath)
SR.update()

logging.basicConfig(level=logging.DEBUG)

#import epdb; epdb.st()

runs = []
if len(sys.argv) > 1:
    for run in sys.argv[1:]:
        runs.append({'id': run})
else:
    runs = SR.runs

for run in runs:

    # You can update the bot to look only for `ansible-test-*.json` files from
    # the test results.
    print(run['id'])
    trs = SR.get_test_results(
        run['id'],
        usecache=True,
        filter_paths=['/testresults/ansible-test-.*.json'],
        #filter_classes=['sanity']
    )
    pprint(trs)
    if trs:
        #import epdb; epdb.st()
        pass

    '''
    if not trs:
        continue

    if not trs[0]['testresults']:
        continue

    if not [x for x in trs[0]['testresults'] if x['failureDetails']]:
        continue

    for td in trs[0]['testresults']:
        has_sanity = False
        for fd in td['failureDetails']:
            if fd['className'] == 'sanity':
                has_sanity = True
        if has_sanity:
            print(td['run_id'], td['job_id'])
            with open('/tmp/testableruns.txt', 'a') as f:
                f.write('%s %s\n' % (td['run_id'], td['job_id']))
    '''

#import epdb; epdb.st()

#SR.get_test_results('58b88d3fc2fe010500932af2')
#SR.get_test_results('58b9d25865094f0500a97cbf', dumpfile='/tmp/results.json')

#with open('tdata.json', 'rb') as f:
#    tdata = json.load(f)

#res = SR.parse_tests_json(tdata)
#pprint(res)
#print(json.dumps(res, indent=2, sort_keys=True))

#import epdb; epdb.st()
