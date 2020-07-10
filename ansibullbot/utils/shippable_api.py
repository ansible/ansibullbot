# curl -H "Content-Type: application/json" -H "Authorization: apiToken XXXX"
# https://api.shippable.com/projects/573f79d02a8192902e20e34b | jq .

import datetime
import json
import logging
import os
import re
import time

import pytz
import six

import requests
from tenacity import retry, stop_after_attempt, wait_fixed, RetryError, TryAgain

import ansibullbot.constants as C
from ansibullbot._text_compat import to_text
from ansibullbot.errors import ShippableNoData
from ansibullbot.utils.file_tools import compress_gzip_file, read_gzip_json_file, write_gzip_json_file
from ansibullbot.utils.timetools import strip_time_safely


ANSIBLE_PROJECT_ID = u'573f79d02a8192902e20e34b'
SHIPPABLE_URL = C.DEFAULT_SHIPPABLE_URL
ANSIBLE_RUNS_URL = u'%s/runs?projectIds=%s&isPullRequest=True' % (
    SHIPPABLE_URL,
    ANSIBLE_PROJECT_ID
)

TIMEOUT = 5  # seconds


def _has_commentable_data(test_results):
    # https://github.com/ansible/ansibullbot/issues/421
    if not test_results:
        return False
    for tr in test_results:
        if tr.get(u'contents', {}).get(u'failureDetails', []):
            return True
        if tr.get(u'contents', {}).get(u'results', []):
            return True
    return False


class ShippableRuns(object):
    '''An abstraction for the shippable API'''

    def __init__(self, cachedir, url=ANSIBLE_RUNS_URL):
        self.cachedir = cachedir
        self.url = url

        self.provider_id = u'562dbd9710c5980d003b0451'
        self.subscription_org_name = u'ansible'
        self.project_name = u'ansible'
        # FIXME might be a list of files in the future
        # FIXME might be a class attribute
        self.required_file = u'shippable.yml'

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

        # Fix data
        self.runs = [x for x in self._rawdata]
        for idx, x in enumerate(self.runs):
            for k, v in six.iteritems(x):
                if k.endswith(u'At'):
                    # 2017-02-07T00:27:06.482Z
                    if v:
                        self.runs[idx][k] = strip_time_safely(v)

    def _get_pullrequest_runs(self, number):
        '''All runs for the given PR number'''
        nruns = []
        for x in self.runs:
            if x[u'commitUrl'].endswith(u'/' + to_text(number)):
                nruns.append(x)
        return nruns

    @classmethod
    def get_processed_last_run(cls, pullrequest_status):
        last_run = cls.get_states(pullrequest_status)[0]
        return cls.get_processed_run(last_run)

    @classmethod
    def get_processed_run(cls, run):
        run = run.copy()
        target_url = run.get('target_url')

        if target_url is None:
            raise ValueError('Could not get run ID from state: "%s"' % run)

        target_url = target_url.split(u'/')

        if target_url[-1] == u'summary':
            # https://app.shippable.com/github/ansible/ansible/runs/21001/summary
            run_id = target_url[-2]
        else:
            # https://app.shippable.com/github/ansible/ansible/runs/21001
            run_id = target_url[-1]

        try:
            int(run_id)
        except ValueError:
            # strip new id out of the description
            run_id = run.get('description', '').split()[1]
            if not run_id.isdigit():
                raise ValueError('Could not get run ID from state: "%s"' % run)

        run[u'created_at'] = pytz.utc.localize(strip_time_safely(run.get(u'created_at')))
        run[u'updated_at'] = pytz.utc.localize(strip_time_safely(run.get(u'updated_at')))
        run[u'run_id'] = run_id
        return run

    def get_last_completion(self, number):
        '''Timestamp of last job completion for given PR number'''
        nruns = self._get_pullrequest_runs(number)
        if not nruns:
            return None
        ts = sorted([x[u'endedAt'] for x in nruns if x[u'endedAt']])
        if ts:
            return ts[-1]
        else:
            return None

    def _get_url(self, url, usecache=False, timeout=TIMEOUT):
        cdir = os.path.join(self.cachedir, u'.raw')
        if not os.path.isdir(cdir):
            os.makedirs(cdir)
        cfile = url.replace(SHIPPABLE_URL + '/', u'')
        cfile = cfile.replace(u'/', u'_')
        cfile = os.path.join(cdir, cfile + u'.json')
        gzfile = cfile + u'.gz'

        # transparently compress old logs
        if os.path.isfile(cfile) and not os.path.isfile(gzfile):
            compress_gzip_file(cfile, gzfile)

        rc = None
        jdata = None
        if os.path.isfile(gzfile):
            try:
                fdata = read_gzip_json_file(gzfile)
                rc = fdata[0]
                jdata = fdata[1]
            except ValueError:
                pass

            if rc == 400:
                return None

        # always use cache for finished jobs...
        is_finished = False
        if isinstance(jdata, list):
            ts = [x.get('endedAt') for x in jdata]
            if None not in ts:
                is_finished = True
        elif isinstance(jdata, dict) and jdata.get(u'endedAt'):
            is_finished = True

        resp = None
        if not os.path.isfile(gzfile) or not jdata or (not usecache and not is_finished):
            if os.path.isfile(gzfile):
                logging.error(gzfile)

            resp = self._fetch(url, timeout=timeout)
            if not resp:
                return None

            if resp.status_code != 400:
                jdata = resp.json()
                write_gzip_json_file(gzfile, [resp.status_code, jdata])
            else:
                write_gzip_json_file(gzfile, [resp.status_code, {}])
                return None

        self._check_response(resp)

        if not jdata:
            if C.DEFAULT_BREAKPOINTS:
                logging.error(u'breakpoint!')
                import epdb; epdb.st()
            else:
                raise ShippableNoData

        return jdata

    def get_run_data(self, run_id, usecache=False):
        # https://api.shippable.com/runs?projectIds=573f79d02a8192902e20e34b&runNumbers=75680
        if len(run_id) == 24:
            # https://api.shippable.com/runs/58caf30337380a0800e31219
            run_url = SHIPPABLE_URL + '/runs/' + run_id
            logging.info(u'shippable: %s' % run_url)
            run_data = self._get_url(run_url, usecache=usecache)
        else:
            '''
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
            '''

            # https://github.com/ansible/ansibullbot/issues/982
            run_url = SHIPPABLE_URL + '/runs'
            run_url += u'?'
            run_url += u'projectIds=%s' % ANSIBLE_PROJECT_ID
            run_url += u'&'
            run_url += u'runNumbers=%s' % run_id

            logging.info(u'shippable: %s' % run_url)
            run_data = self._get_url(run_url, usecache=usecache)
            if run_data:
                if isinstance(run_data, list):
                    try:
                        run_data = run_data[0]
                    except KeyError as e:
                        logging.error(e)
                elif isinstance(run_data, dict) and 'message' in run_data:
                    run_data = {}

        return run_data

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
        logging.info(u'shippable: get %s run data' % run_id)
        run_data = self.get_run_data(run_id, usecache=usecache)

        # flip to the real runid
        if run_data and run_data[u'id'] != run_id:
            run_id = run_data[u'id']

        # https://github.com/ansible/ansibullbot/issues/472
        if not run_data:
            return [], False

        results = []
        url = SHIPPABLE_URL + '/jobs?runIds=%s' % run_id
        rdata = self._get_url(url, usecache=usecache)

        for rd in rdata:
            job_id = rd.get(u'id')

            dkey = u'%s.%s' % (rd[u'runNumber'], rd[u'jobNumber'])
            if dkey not in CVMAP:
                CVMAP[dkey] = {
                    u'files_matched': [],
                    u'files_filtered': [],
                    u'test_data': []
                }

            CVMAP[dkey][u'statusCode'] = rd[u'statusCode']

            jurl = SHIPPABLE_URL + '/jobs/%s/jobTestReports' % job_id
            jdata = self._get_url(jurl, usecache=usecache)

            # 400 return codes ...
            if not jdata:
                continue

            # shippable breaks sometimes ... gzip: stdin: not in gzip format
            jdata = [x for x in jdata if 'path' in x]

            for td in jdata:
                if filter_paths:
                    try:
                        matches = [x.match(td[u'path']) for x in fps]
                        matches = [x for x in matches if x]
                    except Exception as e:
                        logging.error(e)
                else:
                    matches = True

                if not matches:
                    CVMAP[dkey][u'files_filtered'].append(td[u'path'])

                if matches:
                    CVMAP[dkey][u'files_matched'].append(td[u'path'])

                    td[u'run_id'] = run_id
                    td[u'job_id'] = job_id

                    try:
                        td[u'contents'] = json.loads(td[u'contents'])
                    except ValueError as e:
                        logging.error(e)

                    CVMAP[dkey][u'test_data'].append(td)
                    results.append(td)

        ci_verified = False
        if run_data[u'statusCode'] == 80:
            ci_verified = True
            for k, v in CVMAP.items():
                if v[u'statusCode'] == 30:
                    continue
                if v[u'statusCode'] != 80:
                    ci_verified = False
                    break
                if not v[u'files_matched']:
                    ci_verified = False
                    break

                for td in v[u'test_data']:
                    if not td[u'contents']:
                        continue
                    if u'verified' not in td[u'contents']:
                        ci_verified = False
                        break
                    elif not td[u'contents'][u'verified']:
                        ci_verified = False
                        break

        # https://github.com/ansible/ansibullbot/issues/421
        # FIXME is this hack for shippable or will this be common for other CI providers?
        if not _has_commentable_data(results):
            results = []

        return results, ci_verified

    def _get_run_id(self, run_number):
        run_url = u"%s&runNumbers=%s" % (self.url, run_number)
        response = self._fetch(run_url, timeout=TIMEOUT)
        if not response:
            raise Exception("Unable to fetch %r" % run_url)
        self._check_response(response)
        run_id = response.json()[0][u'id']
        logging.debug(run_id)
        return run_id

    def rebuild(self, run_number, issueurl=None, rerunFailedOnly=False):
        """trigger a new run"""
        # always pass the runId in a dict() to requests
        run_id = self._get_run_id(run_number)
        data = {u'runId': run_id}

        # failed jobs only
        if rerunFailedOnly:
            data[u'rerunFailedOnly'] = True

        newbuild_url = u"%s/projects/%s/newBuild" % (SHIPPABLE_URL, ANSIBLE_PROJECT_ID)
        response = self._fetch(newbuild_url, verb='post', data=data, timeout=TIMEOUT)
        if not response:
            raise Exception("Unable to POST %r to %r (%r)" % (data, newbuild_url, issueurl))
        self._check_response(response)
        return response

    def rebuild_failed(self, run_number, issueurl=None):
        """trigger a new run"""
        return self.rebuild(run_number, issueurl=issueurl, rerunFailedOnly=True)

    def cancel(self, run_number, issueurl=None):
        """cancel existing run"""
        # always pass the runId in a dict() to requests
        run_id = self._get_run_id(run_number)
        data = {u'runId': run_id}

        cancel_url = u"%s/runs/%s/cancel" % (SHIPPABLE_URL, run_id)
        response = self._fetch(cancel_url, verb='post', data=data, timeout=TIMEOUT)
        if not response:
            raise Exception("Unable to POST %r to %r (%r)" % (data, cancel_url, issueurl))
        self._check_response(response)
        return response

    def cancel_branch_runs(self, branch):
        """Cancel all Shippable runs on a given branch"""
        run_url = SHIPPABLE_URL + '/runs?projectIds=%s&branch=%s&' \
                  u'status=waiting,queued,processing,started' \
                  % (ANSIBLE_PROJECT_ID, branch)

        logging.info(u'shippable: %s' % run_url)
        try:
            run_data = self._get_url(run_url)
        except ShippableNoData:
            return

        for r in run_data:
            run_number = r.get(u'runNumber', None)
            if run_number:
                self.cancel(run_number)
    @classmethod
    def get_states(cls, ci_status):
        # https://github.com/ansible/ansibullbot/issues/935
        return [
            x for x in ci_status
            if isinstance(x, dict) and x.get('context') == 'Shippable'
        ]

    @classmethod
    def get_state(cls, states):
        if states:
            return states[0].get('state')

    def is_stale(self, states):
        ci_date = self._get_last_shippable_full_run_date(states)

        # https://github.com/ansible/ansibullbot/issues/458
        if ci_date:
            ci_date = strip_time_safely(ci_date)
            ci_delta = (datetime.datetime.now() - ci_date).days
            return ci_delta > 7

        return False

    def _fetch(self, url, verb='get', **kwargs):
        """return response or None in case of failure, try twice"""
        @retry(stop=stop_after_attempt(2), wait=wait_fixed(2))
        def _inner_fetch(verb='get'):
            headers = {
                'Authorization': 'apiToken %s' % C.DEFAULT_SHIPPABLE_TOKEN
            }

            logging.info(u'%s %s' % (verb, url))
            http_method = getattr(requests, verb)
            resp = http_method(url, headers=headers, **kwargs)
            logging.info(u'shippable status code: %s' % resp.status_code)
            logging.info(u'shippable reason: %s' % resp.reason)

            if resp.status_code not in [200, 302, 400]:
                logging.error(u'RC: %s', resp.status_code)
                raise TryAgain

            return resp

        try:
            logging.debug(u'%s' % url)
            return _inner_fetch(verb=verb)
        except RetryError as e:
            logging.error(e)

    def _check_response(self, response):
        if response and response.status_code == 404:
            if C.DEFAULT_BREAKPOINTS:
                logging.error(u'breakpoint!')
                import epdb; epdb.st()
            else:
                raise Exception(u'shippable 404')

    def _get_last_shippable_full_run_date(self, ci_status):
        '''Map partial re-runs back to their last full run date'''
        # https://github.com/ansible/ansibullbot/issues/935
        # (Epdb) pp [x['target_url'] for x in ci_status]
        # [u'https://app.shippable.com/github/ansible/ansible/runs/67039/summary',
        # u'https://app.shippable.com/github/ansible/ansible/runs/67039/summary',
        # u'https://app.shippable.com/github/ansible/ansible/runs/67039',
        # u'https://app.shippable.com/github/ansible/ansible/runs/67037/summary',
        # u'https://app.shippable.com/github/ansible/ansible/runs/67037/summary',
        # u'https://app.shippable.com/github/ansible/ansible/runs/67037']

        # extract and unique the run ids from the target urls
        runids = [_get_runid_from_status(x) for x in ci_status]

        # get rid of duplicates and sort
        runids = sorted(set(runids))

        # always use the numerically higher run id
        runid = runids[-1]

        # build a datastructure to hold the info collected
        rundata = {
            u'runid': runid,
            u'created_at': None,
            u'rerun_batch_id': None,
            u'rerun_batch_createdat': None
        }

        # query the api for all data on this runid
        try:
            rdata = self.get_run_data(to_text(runid), usecache=True)
        except ShippableNoData:
            return None

        # whoops ...
        if rdata is None:
            return None

        # get the referenced run for the last runid if it exists
        pbag = rdata.get(u'propertyBag')
        if pbag:
            rundata[u'rerun_batch_id'] = pbag.get(u'originalRunId')

        # keep the timestamp too
        rundata[u'created_at'] = rdata.get(u'createdAt')

        # if it had a rerunbatchid it was a partial run and
        # we need to go get the date on the original run
        while rundata[u'rerun_batch_id']:
            # the original run data
            rjdata = self.get_run_data(rundata[u'rerun_batch_id'])
            # swap the timestamp
            rundata[u'rerun_batch_createdat'] = rundata[u'created_at']
            # get the old timestamp
            rundata[u'created_at'] = rjdata.get(u'createdAt')
            # get the new batchid
            pbag = rjdata.get(u'propertyBag')
            if pbag:
                rundata[u'rerun_batch_id'] = pbag.get(u'originalRunId')
            else:
                rundata[u'rerun_batch_id'] = None

        # return only the timestamp from the last full run
        return rundata[u'created_at']


def _get_runid_from_status(status):
    # (Epdb) pp [(x['target_url'], x['description']) for x in ci_status]
    # [(u'https://app.shippable.com/runs/58cb6ad937380a0800e36940',
    # u'Run 16560 status is SUCCESS. '),
    # (u'https://app.shippable.com/runs/58cb6ad937380a0800e36940',
    # u'Run 16560 status is PROCESSING. '),
    # (u'https://app.shippable.com/github/ansible/ansible/runs/16560',
    # u'Run 16560 status is WAITING. ')]

    # (Epdb) pp [x['target_url'] for x in ci_status]
    # [u'https://app.shippable.com/github/ansible/ansible/runs/67039/summary',
    # u'https://app.shippable.com/github/ansible/ansible/runs/67039/summary',
    # u'https://app.shippable.com/github/ansible/ansible/runs/67039',
    # u'https://app.shippable.com/github/ansible/ansible/runs/67037/summary',
    # u'https://app.shippable.com/github/ansible/ansible/runs/67037/summary',
    # u'https://app.shippable.com/github/ansible/ansible/runs/67037']

    paths = status[u'target_url'].split(u'/')
    if paths[-1].isdigit():
        return int(paths[-1])
    if paths[-2].isdigit():
        return int(paths[-2])
    for x in status[u'description'].split():
        if x.isdigit():
            return int(x)

    return None
