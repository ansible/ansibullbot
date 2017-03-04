#!/usr/bin/env python

# curl -H "Content-Type: application/json" -H "Authorization: apiToken XXXX"
# https://api.shippable.com/projects/573f79d02a8192902e20e34b | jq .

import datetime
import json
import logging
import lxml
import os
import requests
import requests_cache
import time

from lxml import objectify

import lib.constants as C

ANSIBLE_PROJECT_ID = '573f79d02a8192902e20e34b'
SHIPPABLE_URL = 'https://api.shippable.com'
ANSIBLE_RUNS_URL = '%s/runs?projectIds=%s&isPullRequest=True' % (
    SHIPPABLE_URL,
    ANSIBLE_PROJECT_ID
)


class ShippableRuns(object):

    def __init__(self, url=ANSIBLE_RUNS_URL, cache=False):
        self.url = url

        if cache:
            requests_cache.install_cache('/tmp/shippable.cache')

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

    def get_test_results(self, run_id, dumpdir=None):

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

            jdumpdir = None
            if dumpdir:
                jdumpdir = os.path.join(dumpdir, run_id, job_id)
                if not os.path.isdir(jdumpdir):
                    os.makedirs(jdumpdir)

            res = self.parse_tests_json(
                jdata,
                run_id=run_id,
                job_id=job_id,
                url=jurl,
                dumpdir=jdumpdir
            )
            if res:
                results.append(res)

        if dumpdir:
            dumpfile = os.path.join(dumpdir, run_id, 'results.json')
            with open(dumpfile, 'wb') as f:
                json.dump(results, f, indent=2, sort_keys=True)

        return results

    def _objectify_to_xml(self, obj):
        return lxml.etree.tostring(obj)

    def parse_tests_json(self, jdata, run_id=None, job_id=None,
                         url=None, dumpdir=None):

        result = {
            'testsuites': [],
            'testcases': [],
            'testresults': [],
        }

        if isinstance(jdata, dict):
            return jdata

        for idb,block in enumerate(jdata):

            print(block['path'])
            contents = block['contents']
            for k,v in block.items():
                if k != 'contents':
                    result[k] = v

            if not contents:
                continue

            if block['path'].endswith('json'):
                # /testresults.json
                bdata = json.loads(contents)
                key = block['path'][1:]
                key = key.replace('.json', '')
                result[key].append(bdata)
                #import epdb; epdb.st()
                self._dump_block_contents(dumpdir, block, bdata)
                continue

            root = None
            try:
                root = objectify.fromstring(contents)
            except ValueError:
                # sometimes it has non-serializable unicode
                acontents = contents.encode('ascii', 'ignore')
                root = objectify.fromstring(acontents)
                import q; q([url, run_id, job_id, block['path'], idb])
                #import epdb; epdb.st()

            for k,v in root.attrib.items():
                result[k] = v

            if hasattr(root, 'testsuite'):
                #import epdb; epdb.st()
                pass
            elif hasattr(root, 'testcase'):
                tc = self.parse_testcase(
                    root.testcase,
                    run_id=run_id,
                    job_id=job_id,
                    url=url
                )
                result['testcases'].append(tc)
                self._dump_block_contents(dumpdir, block, tc)
                continue
            else:
                ccount = root.testsuite.countchildren()
                import epdb; epdb.st()

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

                if hasattr(testsuite, 'testcase'):
                    for testcase in testsuite.testcase:
                        tc = self.parse_testcase(
                            testcase,
                            run_id=run_id,
                            job_id=job_id,
                            url=url
                        )
                        ts_attribs['testcases'].append(tc)

                result['testsuites'].append(ts_attribs)

            # dump the contents
            if dumpdir:
                self._dump_block_contents(dumpdir, block, root)

        return result

    def parse_testcase(self, testcase, run_id=None, job_id=None, url=None):
        '''Parse a testcase node'''
        tc = {
            'jobid': job_id
        }

        for k,v in testcase.attrib.items():
            tc[k] = v

        for node in ['failure', 'error', 'system-out', 'skipped']:
            if hasattr(testcase, node):
                tc[node] = {}
                n = getattr(testcase, node)
                for k,v in n.attrib.items():
                    tc[node][k] = v
                if node == 'system-out' or node == 'skipped':
                    tc[node]['text'] = n.text
                    try:
                        tc[node]['text'] = json.loads(tc[node]['text'])
                    except:
                        pass

        return tc

    def _dump_block_contents(self, dumpdir, block, data):
        cpath = os.path.join(dumpdir, block['path'][1:])
        ddir = os.path.dirname(cpath)
        if not os.path.isdir(ddir):
            os.makedirs(ddir)
        try:
            with open(cpath, 'wb') as f:
                f.write(block['contents'])
        except Exception as e:
            with open(cpath, 'wb') as f:
                f.write(e.reason)

        if isinstance(data, dict):
            cleanxml = json.dumps(data, indent=2, sort_keys=2)
            cpath = os.path.join(
                dumpdir,
                block['path'][1:] + '-formatted.json'
            )
        else:
            cleanxml = self._objectify_to_xml(data)
            cpath = os.path.join(
                dumpdir,
                block['path'][1:] + '-formatted.xml'
            )
        with open(cpath, 'wb') as f:
            f.write(cleanxml)

