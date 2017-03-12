#!/usr/bin/env python

# curl -H "Content-Type: application/json" -H "Authorization: apiToken XXXX"
# https://api.shippable.com/projects/573f79d02a8192902e20e34b | jq .

import datetime
import json
import logging
import os
import re
import requests
import requests_cache
import time

import lib.constants as C

ANSIBLE_PROJECT_ID = '573f79d02a8192902e20e34b'
SHIPPABLE_URL = 'https://api.shippable.com'
ANSIBLE_RUNS_URL = '%s/runs?projectIds=%s&isPullRequest=True' % (
    SHIPPABLE_URL,
    ANSIBLE_PROJECT_ID
)


class ShippableRuns(object):
    '''An abstraction for the shippable API'''

    def __init__(self, url=ANSIBLE_RUNS_URL, cachedir=None, cache=False,
                 writecache=True):

        self.writecache = writecache
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

        rc = None
        jdata = None
        if os.path.isfile(cfile):
            try:
                with open(cfile, 'rb') as f:
                    fdata = json.load(f)
                rc = fdata[0]
                jdata = fdata[1]
            except ValueError:
                pass

            if rc == 400:
                return None

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
                if resp.status_code not in [200, 302, 400]:
                    logging.error('RC: %s' % (resp.status_code))
                    retries += 1
                    time.sleep(2)
                    continue
                success = True

            if not success:
                return None

            if resp.status_code != 400:
                jdata = resp.json()
                with open(cfile, 'wb') as f:
                    json.dump([resp.status_code, jdata], f)
            else:
                with open(cfile, 'wb') as f:
                    json.dump([resp.status_code, {}], f)
                return None

        return jdata

    def get_test_results(self, run_id, usecache=False, filter_paths=[]):

        '''Fetch and munge the test results into proper json'''

        # A "run" has many "jobs"
        # A "job" has a "path"
        # A "job" has many "testresults"
        # A "testresult" has many "failureDetails"
        # A "failureDetal" has a "classname"

        # RUNID: 58b88d3fc2fe010500932af2
        # https://api.shippable.com/jobs?runIds=58b88d3fc2fe010500932af
        #JOBID: 58b88d4165094f0500a883ba
        #JOBNUM: 41
        #https://api.shippable.com/jobs/...83ba/consoles?download=true
        #https://api.shippable.com/jobs/...83ba/jobTestReports
        #https://api.shippable.com/jobs/...83ba/jobCoverageReports

        if filter_paths:
            fps = [re.compile(x) for x in filter_paths]

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

            for td in jdata:
                if filter_paths:
                    matches = [x.match(td['path']) for x in fps]
                    matches = [x for x in matches if x]
                else:
                    matches = True
                if matches:
                    td['run_id'] = run_id
                    td['job_id'] = job_id

                    try:
                        td['contents'] = json.loads(td['contents'])
                    except ValueError as e:
                        print(e)
                        #import epdb; epdb.st()
                        pass

                    results.append(td)

        return results
