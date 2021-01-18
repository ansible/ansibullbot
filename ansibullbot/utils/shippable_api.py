# curl -H "Content-Type: application/json" -H "Authorization: apiToken XXXX"
# https://api.shippable.com/projects/573f79d02a8192902e20e34b | jq .

import json
import logging
import os
import re
import time

import requests
import pytz

import ansibullbot.constants as C
from ansibullbot._text_compat import to_text
from ansibullbot.ci.base import BaseCI
from ansibullbot.errors import NoCIError
from ansibullbot.utils.file_tools import compress_gzip_file, read_gzip_json_file, write_gzip_json_file
from ansibullbot.utils.net_tools import fetch, check_response
from ansibullbot.utils.timetools import strip_time_safely


ANSIBLE_PROJECT_ID = '573f79d02a8192902e20e34b'
SHIPPABLE_URL = C.DEFAULT_SHIPPABLE_URL
ANSIBLE_RUNS_URL = '%s/runs?projectIds=%s&isPullRequest=True' % (
    SHIPPABLE_URL,
    ANSIBLE_PROJECT_ID
)
NEW_BUILD_URL = "%s/projects/%s/newBuild" % (
    SHIPPABLE_URL,
    ANSIBLE_PROJECT_ID
)

TIMEOUT = 5  # seconds
HEADERS = {
    'Authorization': 'apiToken %s' % C.DEFAULT_SHIPPABLE_TOKEN
}


class ShippableNoData(Exception):
    """Shippable did not return data"""


class ShippableCI(BaseCI):

    name = 'shippable'

    def __init__(self, cachedir, iw):
        self.cachedir = os.path.join(cachedir, 'shippable.runs')
        self.last_run = None
        self._runs = None
        self._state = None
        self.pr_number = iw.number

        self.states = iw.pullrequest_status_by_context('Shippable')
        if self.states:
            self.last_run = self._get_processed_run(self.states[0])
            self._state = self.last_run['state']

    @property
    def state(self):
        return self._state

    @property
    def required_file(self):
        return 'shippable.yml'

    @property
    def runs(self):
        if self._runs is None:
            success = False
            while not success:
                resp = requests.get(ANSIBLE_RUNS_URL)
                try:
                    self._rawdata = resp.json()
                    success = True
                except Exception as e:
                    logging.error(e)
                    time.sleep(2*60)

            self._runs = [x for x in self._rawdata]
            for idx, x in enumerate(self.runs):
                for k, v in x.items():
                    if k.endswith('At'):
                        # 2017-02-07T00:27:06.482Z
                        if v:
                            self._runs[idx][k] = strip_time_safely(v)
        return self._runs

    def _get_run_id_from_status(self, status):
        target_url = status.get('target_url')

        if target_url is None:
            raise ValueError('Could not get run ID from state: "%s"' % status)

        target_url = target_url.split('/')

        if target_url[-1] == 'summary':
            # https://app.shippable.com/github/ansible/ansible/runs/21001/summary
            run_id = target_url[-2]
        else:
            # https://app.shippable.com/github/ansible/ansible/runs/21001
            run_id = target_url[-1]

        try:
            int(run_id)
        except ValueError:
            # 'Run 16560 status is WAITING. '
            run_id = status.get('description', '').split()[1]
            if not run_id.isdigit():
                raise ValueError('Could not get run ID from state: "%s"' % status)

        return run_id

    def _get_processed_run(self, status):
        run = status.copy()
        run_id = self._get_run_id_from_status(run)

        run['created_at'] = pytz.utc.localize(strip_time_safely(run.get('created_at')))
        run['updated_at'] = pytz.utc.localize(strip_time_safely(run.get('updated_at')))
        run['run_id'] = run_id
        return run

    @property
    def updated_at(self):
        nruns = []
        for x in self.runs:
            if x['commitUrl'].endswith('/' + to_text(self.pr_number)):
                nruns.append(x)
        if not nruns:
            return None
        nruns = sorted([x['endedAt'] for x in nruns if x['endedAt']])
        if nruns:
            return nruns[-1]

    def _get_url(self, url, usecache=False, timeout=TIMEOUT):
        cdir = os.path.join(self.cachedir, '.raw')
        if not os.path.isdir(cdir):
            os.makedirs(cdir)
        cfile = url.replace(SHIPPABLE_URL + '/', '')
        cfile = cfile.replace('/', '_')
        cfile = os.path.join(cdir, cfile + '.json')
        gzfile = cfile + '.gz'

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
        elif isinstance(jdata, dict) and jdata.get('endedAt'):
            is_finished = True

        resp = None
        if not os.path.isfile(gzfile) or not jdata or (not usecache and not is_finished):
            if os.path.isfile(gzfile):
                logging.error(gzfile)

            resp = fetch(url, headers=HEADERS, timeout=timeout)
            if not resp:
                return None

            if resp.status_code != 400:
                jdata = resp.json()
                write_gzip_json_file(gzfile, [resp.status_code, jdata])
            else:
                write_gzip_json_file(gzfile, [resp.status_code, {}])
                return None

        check_response(resp)

        if not jdata:
            raise ShippableNoData

        return jdata

    def _get_run_data(self, run_id, usecache=False):
        if len(run_id) == 24:
            # https://api.shippable.com/runs/58caf30337380a0800e31219
            run_url = SHIPPABLE_URL + '/runs/' + run_id
        else:
            # https://github.com/ansible/ansibullbot/issues/982
            # https://api.shippable.com/runs?projectIds=573f79d02a8192902e20e34b&runNumbers=75680
            run_url = SHIPPABLE_URL + '/runs'
            run_url += '?'
            run_url += 'projectIds=%s' % ANSIBLE_PROJECT_ID
            run_url += '&'
            run_url += 'runNumbers=%s' % run_id

        logging.info('shippable: %s' % run_url)
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

    def get_test_results(self):
        '''Fetch and munge the test results into proper json'''
        # statusCode(s):
        #   80: failed
        #   80: timeout
        #   30: success
        #   20: processing
        usecache = True
        run_id = self.last_run['run_id']
        fps = [re.compile(x) for x in ['/testresults/ansible-test-.*.json']]

        # ci verified data map
        CVMAP = {}

        # get the run metdata
        logging.info('shippable: get %s run data' % run_id)
        run_data = self._get_run_data(run_id, usecache=usecache)

        # flip to the real runid
        if run_data and run_data['id'] != run_id:
            run_id = run_data['id']

        # https://github.com/ansible/ansibullbot/issues/472
        if not run_data:
            return [], False

        results = []
        url = SHIPPABLE_URL + '/jobs?runIds=%s' % run_id
        rdata = self._get_url(url, usecache=usecache)

        for rd in rdata:
            dkey = '%s.%s' % (rd['runNumber'], rd['jobNumber'])
            if dkey not in CVMAP:
                CVMAP[dkey] = {
                    'files_matched': [],
                    'files_filtered': [],
                    'test_data': []
                }

            CVMAP[dkey]['statusCode'] = rd['statusCode']

            job_id = rd.get('id')
            jurl = SHIPPABLE_URL + '/jobs/%s/jobTestReports' % job_id
            jdata = self._get_url(jurl, usecache=usecache)

            # 400 return codes ...
            if not jdata:
                continue

            # shippable breaks sometimes ... gzip: stdin: not in gzip format
            jdata = [x for x in jdata if 'path' in x]

            for td in jdata:
                try:
                    matches = [x.match(td['path']) for x in fps]
                    matches = [x for x in matches if x]
                except Exception as e:
                    logging.error(e)

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
            for v in CVMAP.values():
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
                    if not td['contents']['verified']:
                        ci_verified = False
                        break

        # https://github.com/ansible/ansibullbot/issues/421
        for tr in results:
            if tr.get('contents', {}).get('failureDetails', []) or tr.get('contents', {}).get('results', []):
                return results, ci_verified

        return [], ci_verified

    def _get_run_id(self, run_number):
        run_url = "%s&runNumbers=%s" % (ANSIBLE_RUNS_URL, run_number)
        response = fetch(run_url, headers=HEADERS, timeout=TIMEOUT)
        if not response:
            raise Exception("Unable to fetch %r" % run_url)
        check_response(response)
        run_id = response.json()[0]['id']
        logging.debug(run_id)
        return run_id

    def rebuild(self, run_number, failed_only=False):
        """trigger a new run"""
        # always pass the runId in a dict() to requests
        run_id = self._get_run_id(run_number)
        data = {'runId': run_id}

        if failed_only:
            data['rerunFailedOnly'] = True

        response = fetch(NEW_BUILD_URL, verb='post', headers=HEADERS, data=data, timeout=TIMEOUT)
        if not response:
            raise Exception("Unable to POST %r to %r" % (data, NEW_BUILD_URL))
        check_response(response)
        return response

    def rebuild_failed(self, run_number):
        """trigger a new run"""
        return self.rebuild(run_number, failed_only=True)

    def cancel(self, run_number):
        """cancel existing run"""
        # always pass the runId in a dict() to requests
        run_id = self._get_run_id(run_number)
        data = {'runId': run_id}

        cancel_url = "%s/runs/%s/cancel" % (SHIPPABLE_URL, run_id)
        response = fetch(cancel_url, verb='post', headers=HEADERS, data=data, timeout=TIMEOUT)
        if not response:
            raise Exception("Unable to POST %r to %r" % (data, cancel_url))
        check_response(response)
        return response

    def cancel_on_branch(self, branch):
        """Cancel all Shippable runs on a given branch"""
        run_url = SHIPPABLE_URL + '/runs?projectIds=%s&branch=%s&' \
                  'status=waiting,queued,processing,started' \
                  % (ANSIBLE_PROJECT_ID, branch)

        logging.info('shippable: %s' % run_url)
        try:
            run_data = self._get_url(run_url)
        except ShippableNoData:
            return

        for r in run_data:
            run_number = r.get('runNumber', None)
            if run_number:
                self.cancel(run_number)

    def get_last_full_run_date(self):
        '''Map partial re-runs back to their last full run date'''
        # https://github.com/ansible/ansibullbot/issues/935
        # extract and unique the run ids from the target urls
        if not self.states:
            raise NoCIError('No shippable states')

        runids = [self._get_run_id_from_status(x) for x in self.states]

        # get rid of duplicates and sort
        runids = sorted(set(runids))

        # always use the numerically higher run id
        runid = runids[-1]

        # build a datastructure to hold the info collected
        rundata = {
            'runid': runid,
            'created_at': None,
            'rerun_batch_id': None,
            'rerun_batch_createdat': None
        }

        # query the api for all data on this runid
        try:
            rdata = self._get_run_data(to_text(runid), usecache=True)
        except ShippableNoData:
            return None

        # whoops ...
        if rdata is None:
            return None

        # get the referenced run for the last runid if it exists
        pbag = rdata.get('propertyBag')
        if pbag:
            rundata['rerun_batch_id'] = pbag.get('originalRunId')

        # keep the timestamp too
        rundata['created_at'] = rdata.get('createdAt')

        # if it had a rerunbatchid it was a partial run and
        # we need to go get the date on the original run
        while rundata['rerun_batch_id']:
            # the original run data
            rjdata = self._get_run_data(rundata['rerun_batch_id'])
            # swap the timestamp
            rundata['rerun_batch_createdat'] = rundata['created_at']
            # get the old timestamp
            rundata['created_at'] = rjdata.get('createdAt')
            # get the new batchid
            pbag = rjdata.get('propertyBag')
            if pbag:
                rundata['rerun_batch_id'] = pbag.get('originalRunId')
            else:
                rundata['rerun_batch_id'] = None

        # return only the timestamp from the last full run
        return strip_time_safely(rundata['created_at'])
