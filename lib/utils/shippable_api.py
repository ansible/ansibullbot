#!/usr/bin/env python

# curl -H "Content-Type: application/json" -H "Authorization: apiToken XXXX"
# https://api.shippable.com/projects/573f79d02a8192902e20e34b | jq .

import datetime
import json
import logging
import lxml
import requests
import time

from lxml import objectify
#from pprint import pprint

import lib.constants as C

ANSIBLE_PROJECT_ID = '573f79d02a8192902e20e34b'
SHIPPABLE_URL = 'https://api.shippable.com'
ANSIBLE_RUNS_URL = '%s/runs?projectIds=%s&isPullRequest=True' % (
    SHIPPABLE_URL,
    ANSIBLE_PROJECT_ID
)


class ShippableRuns(object):

    def __init__(self, url=ANSIBLE_RUNS_URL):
        self.url = url

    def update(self):
        '''Fetch the latest data then send for processing'''
        success = False
        while not success:
            resp = requests.get(self.url)
            try:
                self._rawdata = resp.json()
                success = True
            except Exception as e:
                logging.error(e)
                time.sleep(2*60)
        self._process_raw_data()

    def _process_raw_data(self):
        '''Iterate through and fix data'''
        self.runs = [x for x in self._rawdata]
        for idx,x in enumerate(self.runs):
            for k,v in x.iteritems():
                if k.endswith('At'):
                    # 2017-02-07T00:27:06.482Z
                    if v:
                        ds = datetime.datetime.strptime(
                            v,
                            '%Y-%m-%dT%H:%M:%S.%fZ'
                        )
                        self.runs[idx][k] = ds

    def get_pullrequest_runs(self, number):
        '''All runs for the given PR number'''
        nruns = []
        for x in self.runs:
            if x['commitUrl'].endswith('/' + str(number)):
                nruns.append(x)
        return nruns

    def get_last_completion(self, number):
        '''Timestamp of last job completion for given PR number'''
        nruns = self.get_pullrequest_runs(number)
        if not nruns:
            return None
        ts = sorted([x['endedAt'] for x in nruns if x['endedAt']])
        if ts:
            return ts[-1]
        else:
            return None

    def get_updated_since(self, since):
        updated = []
        for x in self.runs:
            try:
                if x['createdAt'] > since or \
                        x['startedAt'] > since or \
                        x['endedAt'] > since:
                    updated.append(x['pullRequestNumber'])
            except Exception:
                pass
        updated = sorted(set(updated))
        return updated

    def get_test_results(self, run_id, dumpfile=None):

        '''Fetch and munge the test results into proper json'''

        # RUNID: 58b88d3fc2fe010500932af2
        # https://api.shippable.com/jobs?runIds=58b88d3fc2fe010500932af
        #JOBID: 58b88d4165094f0500a883ba
        #JOBNUM: 41
        #https://api.shippable.com/jobs/...83ba/consoles?download=true
        #https://api.shippable.com/jobs/...83ba/jobTestReports
        #https://api.shippable.com/jobs/...83ba/jobCoverageReports

        results = []

        headers = dict(
            Authorization='apiToken %s' % C.DEFAULT_SHIPPABLE_TOKEN
        )

        url = 'https://api.shippable.com/jobs?runIds=%s' % run_id
        resp = requests.get(url, headers=headers)
        rdata = resp.json()
        for rd in rdata:
            job_id = rd.get('id')
            jurl = 'https://api.shippable.com/jobs/%s/jobTestReports' % job_id
            jresp = requests.get(jurl, headers=headers)
            jdata = jresp.json()
            res = self.parse_test_json(jdata, job_id=job_id)
            if res:
                results.append(res)

        if dumpfile:
            with open(dumpfile, 'wb') as f:
                json.dump(results, f, indent=2, sort_keys=True)

        return results

    def parse_tests_json(self, jdata, job_id=None):

        result = {
            'testsuites': []
        }

        for block in jdata:

            contents = block['contents']
            if not contents:
                continue

            # test for json
            isjson = False
            try:
                json.loads(contents)
                isjson = True
            except ValueError:
                pass

            if not isjson:
                # sometimes it is xml ...
                root = None
                try:
                    root = objectify.fromstring(contents)
                except ValueError:
                    # sometimes it has non-serializable unicode
                    contents = contents.encode('ascii', 'ignore')
                    root = objectify.fromstring(contents)

                #xmls = lxml.etree.tostring(root)
                #with open('/tmp/root.xml', 'wb') as f:
                #    f.write(xmls)

                for k,v in root.attrib.items():
                    result[k] = v

                for testsuite in root.testsuite:

                    ts_attribs = {
                        'testcases': []
                    }

                    for k,v in testsuite.attrib.items():
                        ts_attribs[k] = v

                    if hasattr(testsuite, 'properties'):
                        ts_attribs['properties'] = {}
                        for x in testsuite.properties.property:
                            k = x.attrib.get('name')
                            v = x.attrib.get('value')
                            ts_attribs['properties'][k] = v

                        #import epdb; epdb.st()

                    for testcase in testsuite.testcase:

                        tc = {
                            'jobid': job_id
                        }

                        for k,v in testcase.attrib.items():
                            tc[k] = v

                        for node in ['failure', 'error', 'system-out']:
                            if hasattr(testcase, node):
                                tc[node] = {}
                                n = getattr(testcase, node)
                                for k,v in n.attrib.items():
                                    tc[node][k] = v
                                if node == 'system-out':
                                    tc[node]['text'] = n.text
                                    try:
                                        tc[node]['text'] = json.loads(tc[node]['text'])
                                    except:
                                        pass

                        ts_attribs['testcases'].append(tc)

                    result['testsuites'].append(ts_attribs)

        return result
