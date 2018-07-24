#!/usr/bin/env python

# curl -H "Content-Type: application/json" -H "Authorization: apiToken XXXX"
# https://api.shippable.com/projects/573f79d02a8192902e20e34b | jq .

import ansibullbot.constants as C

import datetime
import gzip
import json
import logging
import os
import re
import requests_cache
import shutil
import time

import requests
from tenacity import retry, stop_after_attempt, wait_fixed, RetryError, TryAgain


ANSIBLE_PROJECT_ID = '573f79d02a8192902e20e34b'
SHIPPABLE_URL = 'https://api.shippable.com'
ANSIBLE_RUNS_URL = '%s/runs?projectIds=%s&isPullRequest=True' % (
    SHIPPABLE_URL,
    ANSIBLE_PROJECT_ID
)

TIMEOUT = 5  # seconds


def has_commentable_data(test_results):
    # https://github.com/ansible/ansibullbot/issues/421
    commentable = False
    if not test_results:
        return commentable
    for tr in test_results:
        if tr.get('contents', {}).get('failureDetails', []):
            commentable = True
            break
        if tr.get('contents', {}).get('results', []):
            commentable = True
            break
    return commentable


class ShippableNoData(Exception):
    def __init__(self,*args,**kwargs):
        Exception.__init__(self,*args,**kwargs)


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

        self.provider_id = '562dbd9710c5980d003b0451'
        self.subscription_org_name = 'ansible'
        self.project_name = 'ansible'
        self.run_meta = []

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
        for idx, x in enumerate(self.runs):
            for k, v in x.iteritems():
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

    def _load_cache_file(self, cfile):
        with gzip.open(cfile, 'r') as f:
            jdata = json.loads(f.read())
        return jdata

    def _write_cache_file(self, cfile, data):
        with gzip.open(cfile, 'w') as f:
            f.write(json.dumps(data))

    def _compress_cache_file(self, cfile, gzfile):
        with open(cfile, 'r') as f_in, gzip.open(gzfile, 'w') as f_out:
            shutil.copyfileobj(f_in, f_out)
        os.remove(cfile)

    def _get_url(self, url, usecache=False, timeout=TIMEOUT):
        cdir = os.path.join(self.cachedir, '.raw')
        if not os.path.isdir(cdir):
            os.makedirs(cdir)
        cfile = url.replace('https://api.shippable.com/', '')
        cfile = cfile.replace('/', '_')
        cfile = os.path.join(cdir, cfile + '.json')
        gzfile = cfile + '.gz'

        # transparently compress old logs
        if os.path.isfile(cfile) and not os.path.isfile(gzfile):
            self._compress_cache_file(cfile, gzfile)

        rc = None
        jdata = None
        if os.path.isfile(gzfile):
            try:
                fdata = self._load_cache_file(gzfile)
                rc = fdata[0]
                jdata = fdata[1]
            except ValueError:
                pass

            if rc == 400:
                return None

        resp = None
        if not os.path.isfile(gzfile) or not jdata or not usecache:

            resp = self.fetch(url, timeout=timeout)
            if not resp:
                return None

            if resp.status_code != 400:
                jdata = resp.json()
                self._write_cache_file(gzfile, [resp.status_code, jdata])
            else:
                self._write_cache_file(gzfile, [resp.status_code, {}])
                return None

        self.check_response(resp)

        if not jdata:
            if C.DEFAULT_BREAKPOINTS:
                logging.error('breakpoint!')
                import epdb; epdb.st()
            else:
                #raise Exception('no json data')
                raise ShippableNoData()

        return jdata

    def get_run_data(self, run_id, usecache=False):

        if len(run_id) == 24:
            # https://api.shippable.com/runs/58caf30337380a0800e31219
            run_url = 'https://api.shippable.com/runs/' + run_id
            logging.info('shippable: %s' % run_url)
            run_data = self._get_url(run_url, usecache=usecache)
        else:
            # https://github.com/ansible/ansibullbot/issues/513
            run_url = 'https://api.shippable.com/runs'
            run_url += '?'
            run_url += 'providerIds=%s' % self.provider_id
            run_url += '&'
            run_url += 'subscriptionOrgNames=%s' % self.subscription_org_name
            run_url += '&'
            run_url += 'projectNames=%s' % self.project_name
            run_url += '&'
            run_url += 'runNumbers=%s' % run_id

            logging.info('shippable: %s' % run_url)
            run_data = self._get_url(run_url, usecache=usecache)
            if run_data:
                run_data = run_data[0]

        return run_data

    def get_all_run_metadata(self, usecache=True):
        url = 'https://api.shippable.com/runs'
        run_data = self._get_url(url, usecache=usecache)
        return run_data

    def map_runid(self, runid):
        if not self.run_meta:
            self.run_meta = self.get_all_run_metadata(usecache=False)
        for x in self.run_meta:
            if x['id'] == runid:
                return runid
            elif x['runNumber'] == runid:
                return x['id']

        # try again with fresh meta
        self.run_meta = self.get_all_run_metadata(usecache=False)
        for x in self.run_meta:
            if x['id'] == runid:
                return runid
            elif x['runNumber'] == runid:
                return x['id']

        return None

    def get_test_results(self, run_id, usecache=False, filter_paths=[]):

        '''Fetch and munge the test results into proper json'''

        # statusCode(s):
        #   80: failed
        #   80: timeout
        #   30: success
        #   20: processing

        if filter_paths:
            fps = [re.compile(x) for x in filter_paths]

        # ci verified data map
        CVMAP = {}

        # get the run metdata
        logging.info('shippable: get %s run data' % run_id)
        run_data = self.get_run_data(run_id, usecache=usecache)

        # flip to the real runid
        if run_data and run_data['id'] != run_id:
            run_id = run_data['id']

        # https://github.com/ansible/ansibullbot/issues/472
        if not run_data:
            return run_data, None, [], False

        # need this for ci_verified association
        commitSha = run_data['commitSha']

        results = []
        url = 'https://api.shippable.com/jobs?runIds=%s' % run_id
        rdata = self._get_url(url, usecache=usecache)

        for rix, rd in enumerate(rdata):

            job_id = rd.get('id')
            #job_number = rd.get('jobNumber')

            dkey = '%s.%s' % (rd['runNumber'], rd['jobNumber'])
            if dkey not in CVMAP:
                CVMAP[dkey] = {
                    'files_matched': [],
                    'files_filtered': [],
                    'test_data': []
                }

            CVMAP[dkey]['statusCode'] = rd['statusCode']

            jurl = 'https://api.shippable.com/jobs/%s/jobTestReports' % job_id
            jdata = self._get_url(jurl, usecache=usecache)

            # 400 return codes ...
            if not jdata:
                continue

            for jid, td in enumerate(jdata):

                if filter_paths:
                    matches = [x.match(td['path']) for x in fps]
                    matches = [x for x in matches if x]
                else:
                    matches = True

                if not matches:
                    CVMAP[dkey]['files_filtered'].append(td['path'])

                if matches:
                    CVMAP[dkey]['files_matched'].append(td['path'])

                    td['run_id'] = run_id
                    td['job_id'] = job_id

                    try:
                        td['contents'] = json.loads(td['contents'])
                    except ValueError as e:
                        logging.error(e)

                    CVMAP[dkey]['test_data'].append(td)
                    results.append(td)

        ci_verified = False
        if run_data['statusCode'] == 80:
            ci_verified = True
            for k, v in CVMAP.items():
                if v['statusCode'] == 30:
                    continue
                if v['statusCode'] != 80:
                    ci_verified = False
                    break
                if not v['files_matched']:
                    ci_verified = False
                    break

                for td in v['test_data']:
                    if not td['contents']:
                        continue
                    if 'verified' not in td['contents']:
                        ci_verified = False
                        break
                    elif not td['contents']['verified']:
                        ci_verified = False
                        break

        return run_data, commitSha, results, ci_verified

    def get_run_id(self, run_number):
        """trigger a new run"""
        run_url = "%s&runNumbers=%s" % (self.url, run_number)
        response = self.fetch(run_url, timeout=TIMEOUT)
        if not response:
            raise Exception("Unable to fetch %r" % run_url)
        self.check_response(response)
        run_id = response.json()[0]['id']
        logging.debug(run_id)
        return run_id

    def rebuild(self, run_number, issueurl=None):
        """trigger a new run"""

        # always pass the runId in a dict() to requests
        run_id = self.get_run_id(run_number)
        data = {'runId': run_id}

        newbuild_url = "%s/projects/%s/newBuild" % (SHIPPABLE_URL, ANSIBLE_PROJECT_ID)
        response = self.fetch(newbuild_url, verb='post', data=data, timeout=TIMEOUT)
        if not response:
            raise Exception("Unable to POST %r to %r (%r)" % (data, newbuild_url, issueurl))
        self.check_response(response)
        return response

    def cancel(self, run_number, issueurl=None):
        """cancel existing run"""

        # always pass the runId in a dict() to requests
        run_id = self.get_run_id(run_number)
        data = {'runId': run_id}

        cancel_url = "%s/runs/%s/cancel" % (SHIPPABLE_URL, run_id)
        response = self.fetch(cancel_url, verb='post', data=data, timeout=TIMEOUT)
        if not response:
            raise Exception("Unable to POST %r to %r (%r)" % (data, cancel_url, issueurl))
        self.check_response(response)
        return response

    def fetch(self, url, verb='get', **kwargs):
        """return response or None in case of failure, try twice"""
        @retry(stop=stop_after_attempt(2), wait=wait_fixed(2))
        def _fetch():
            headers = dict(
                Authorization='apiToken %s' % C.DEFAULT_SHIPPABLE_TOKEN
            )

            http_method = getattr(requests, verb)
            resp = http_method(url, headers=headers, **kwargs)

            if resp.status_code not in [200, 302, 400]:
                logging.error('RC: %s', resp.status_code)
                raise TryAgain

            return resp

        try:
            logging.debug('%s', url)
            return _fetch()
        except RetryError:
            pass

    def check_response(self, response):
        if response and response.status_code == 404:
            if C.DEFAULT_BREAKPOINTS:
                logging.error('breakpoint!')
                import epdb; epdb.st()
            else:
                raise Exception('shippable 404')
