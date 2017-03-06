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

    def __init__(self, url=ANSIBLE_RUNS_URL, cachedir=None, cache=False):
        if cachedir:
            self.cachedir = cachedir
        else:
            self.cachedir = '/tmp/shippable.cache'
        self.url = url
        if cache:
            requests_cache.install_cache(self.cachedir)

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

    def _get_url(self, url, usecache=False):
        cdir = os.path.join(self.cachedir, '.raw')
        if not os.path.isdir(cdir):
            os.makedirs(cdir)
        cfile = url.replace('https://api.shippable.com/', '')
        cfile = cfile.replace('/', '_')
        cfile = os.path.join(cdir, cfile + '.json')

        jdata = None
        if os.path.isfile(cfile):
            try:
                with open(cfile, 'rb') as f:
                    jdata = json.load(f)
            except ValueError:
                pass

        if not os.path.isfile(cfile) or not jdata:

            headers = dict(
                Authorization='apiToken %s' % C.DEFAULT_SHIPPABLE_TOKEN
            )

            resp = None
            success = False
            retries = 0
            while not success and retries < 2:
                logging.debug('%s' % url)
                resp = requests.get(url, headers=headers)
                if resp.status_code not in [200, 302]:
                    logging.error('RC: %s' % (resp.status_code))
                    retries += 1
                    time.sleep(2)
                    continue
                success = True

            if not success:
                return None

            jdata = resp.json()

            with open(cfile, 'wb') as f:
                json.dump(jdata, f)

        return jdata

    def get_test_results(self, run_id, usecache=False, filter_paths=[],
                         filter_classes=[]):

        '''Fetch and munge the test results into proper json'''

        # RUNID: 58b88d3fc2fe010500932af2
        # https://api.shippable.com/jobs?runIds=58b88d3fc2fe010500932af
        #JOBID: 58b88d4165094f0500a883ba
        #JOBNUM: 41
        #https://api.shippable.com/jobs/...83ba/consoles?download=true
        #https://api.shippable.com/jobs/...83ba/jobTestReports
        #https://api.shippable.com/jobs/...83ba/jobCoverageReports

        results = []
        url = 'https://api.shippable.com/jobs?runIds=%s' % run_id
        rdata = self._get_url(url, usecache=usecache)

        for rd in rdata:
            job_id = rd.get('id')
            jurl = 'https://api.shippable.com/jobs/%s/jobTestReports' % job_id
            jdata = self._get_url(jurl, usecache=usecache)
            # 400 return codes ...
            if not jdata:
                continue

            if not os.path.isdir(self.cachedir):
                os.makedirs(self.cachedir)

            res = self.parse_tests_json(
                jdata,
                run_id=run_id,
                job_id=job_id,
                url=jurl,
                filter_paths=filter_paths
            )
            if res:
                results.append(res)

        dumpfile = os.path.join(self.cachedir, run_id, 'results.json')
        dumpdir = os.path.dirname(dumpfile)
        if not os.path.isdir(dumpdir):
            os.makedirs(dumpdir)

        with open(dumpfile, 'wb') as f:
            logging.debug(dumpfile)
            #import epdb; epdb.st()
            json.dump(results, f, indent=2, sort_keys=True)

        if filter_classes:
            results = self._filter_failures_by_classes(results, filter_classes)

        return results

    def _filter_failures_by_classes(self, results, filter_classes):
        jobs = []
        for job in results:
            # we only care about jobs with results
            if 'testresults' not in job:
                continue

            # we only care about testresults with failuredetails
            try:
                trs = [x for x in job['testresults'] if 'failureDetails' in x]
            except:
                continue
            if not trs:
                continue

            # reduced testresults
            filtered_trs = []

            for tr in trs:

                # reduced failuredetails
                filtered_fd = []

                for fd in tr['failureDetails']:
                    if fd['className'] in filter_classes:
                        filtered_fd.append(fd)

                if filtered_fd:
                    # clean up the failures list
                    ntr = tr.copy()
                    ntr['failureDetails'] = filtered_fd
                    filtered_trs.append(ntr)

            if filtered_trs:
                # keep this job with the filtered tests
                njob = job.copy()
                njob['testresults'] = filtered_trs
                jobs.append(njob)

        results = jobs
        return results

    def _objectify_to_xml(self, obj):
        return lxml.etree.tostring(obj)

    def parse_tests_json(self, jdata, run_id=None, job_id=None,
                         url=None, filter_paths=[]):

        result = {
            'url': url,
            'run_id': run_id,
            'job_id': job_id,
            'testsuites': [],
            'testcases': [],
            'testresults': [],
        }

        if isinstance(jdata, dict):
            return jdata

        for idb,block in enumerate(jdata):

            if filter_paths and block['path'] not in filter_paths:
                continue

            contents = block['contents']
            for k,v in block.items():
                if k != 'contents':
                    result[k] = v

            if not contents:
                continue

            if block['path'].endswith('json'):
                # /testresults.json
                bdata = json.loads(contents)
                bdata['job_url'] = url
                bdata['run_id'] = run_id
                bdata['job_id'] = job_id
                key = block['path'][1:]
                key = key.replace('.json', '')
                if key not in result:
                    result[key] = []
                result[key].append(bdata)
                self._dump_block_contents(self.cachedir, block, bdata)
                continue

            # treat as xml ...
            root = objectify.fromstring(contents.encode('utf-8'))

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
                    url=url,
                )
                tc['path'] = block['path']
                tc['run_id'] = run_id
                tc['job_url'] = url
                tc['job_id'] = job_id
                result['testcases'].append(tc)
                self._dump_block_contents(self.cachedir, block, tc)
                continue
            else:
                #ccount = root.testsuite.countchildren()
                #import epdb; epdb.st()
                pass

            for testsuite in root.testsuite:

                ts_attribs = {
                    'job_url': url,
                    'path': block['path'],
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
                        tc['run_id'] = run_id
                        tc['job_url'] = url
                        tc['job_id'] = job_id
                        ts_attribs['testcases'].append(tc)

                result['testsuites'].append(ts_attribs)

            # dump the contents
            self._dump_block_contents(self.cachedir, block, root)

        return result

    def parse_testcase(self, testcase, run_id=None, job_id=None, url=None):
        '''Parse a testcase node'''
        tc = {
            'job_id': job_id,
            'run_id': run_id
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
        if not dumpdir or block['path'] is None:
            return None
        try:
            cpath = os.path.join(
                dumpdir,
                data.get('run_id'),
                data.get('job_id'),
                block['path'][1:]
            )
        except:
            return None
        ddir = os.path.dirname(cpath)
        if not os.path.isdir(ddir):
            os.makedirs(ddir)
        logging.debug(cpath)
        try:
            with open(cpath, 'wb') as f:
                f.write(block['contents'])
        except Exception as e:
            with open(cpath, 'wb') as f:
                f.write(e.reason)

        if isinstance(data, dict):
            cleanxml = json.dumps(data, indent=2, sort_keys=2)
            cpath = os.path.join(
                ddir,
                block['path'][1:] + '-formatted.json'
            )
        else:
            cleanxml = self._objectify_to_xml(data)
            cpath = os.path.join(
                ddir,
                block['path'][1:] + '-formatted.xml'
            )
        with open(cpath, 'wb') as f:
            f.write(cleanxml)
