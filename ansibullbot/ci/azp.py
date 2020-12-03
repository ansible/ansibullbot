import hashlib
import logging
import json
import os.path
import re

from io import BytesIO
from zipfile import ZipFile

import pytz

import ansibullbot.constants as C
from ansibullbot._pickle_compat import pickle_dump, pickle_load
from ansibullbot._text_compat import to_bytes
from ansibullbot.ci.base import BaseCI
from ansibullbot.errors import NoCIError
from ansibullbot.utils.net_tools import fetch, check_response
from ansibullbot.utils.timetools import strip_time_safely


DETAILS_URL_RE = \
    re.compile(
        r'https://dev\.azure\.com/(?P<organization>[^/]+)/(?P<project>[^/]+)/_build/results\?buildId=(?P<buildId>[0-9]+)'
    )
TIMELINE_URL_FMT = \
    u'https://dev.azure.com/' + C.DEFAULT_AZP_ORG + '/' + C.DEFAULT_AZP_PROJECT + '/_apis/build/builds/%s/timeline/?api-version=6.0'
ARTIFACTS_URL_FMT = \
    u'https://dev.azure.com/' + C.DEFAULT_AZP_ORG + '/' + C.DEFAULT_AZP_PROJECT + '/_apis/build/builds/%s/artifacts?api-version=6.0'
TIMEOUT = 5  # seconds
HEADERS = {
    'Content-Type': 'application/json',
}


class AzurePipelinesCI(BaseCI):

    name = 'azp'

    def __init__(self, cachedir, iw):
        self._cachedir = os.path.join(cachedir, 'azp.runs')
        self._iw = iw

        self._build_id = None
        self._jobs = None
        self._state = None
        self._updated_at = None
        self._stages = None
        self._artifacts = None
        self.last_run = None
        self.created_at = None

        if self.state and self.build_id and self.jobs:
            try:
                self.created_at = min(
                    (strip_time_safely(j['startTime']) for j in self.jobs if j['startTime'] is not None)
                )
            except ValueError:
                self.created_at = self.updated_at

            self.last_run = {
                'state': self.state,
                'created_at': self.created_at,
                'updated_at': pytz.utc.localize(self.updated_at),
                'run_id': self.build_id,
            }

    @property
    def build_id(self):
        if self._build_id is None:
            build_ids = set()
            for check_run in self._iw.pullrequest_check_runs:
                match = re.match(DETAILS_URL_RE, check_run[u'details_url'])
                if not match:
                    continue
                org, project, buildid = match.groups()
                if org == C.DEFAULT_AZP_ORG and project == C.DEFAULT_AZP_PROJECT:
                    build_ids.add(buildid)
            # FIXME more than one Pipeline
            logging.debug("Azure Pipelines build IDs found: %s" % ', '.join(build_ids))
            try:
                self._build_id = max(build_ids)
            except ValueError:
                self._build_id = None

        return self._build_id

    @property
    def jobs(self):
        if self._jobs is None:
            if self.build_id:
                # FIXME cache this? We need lastChangedOn always anyway...
                resp = fetch(TIMELINE_URL_FMT % self.build_id)
                check_response(resp)
                data = resp.json()
                self._jobs = [r for r in data['records'] if r['type'] == 'Job']
                self._updated_at = strip_time_safely(data['lastChangedOn'])  # FIXME
                self._stages = [r for r in data['records'] if r['type'] == 'Stage']  # FIXME
            else:
                self._jobs = []
        return self._jobs

    @property
    def state(self):
        if self._state is None:
            if self.jobs:
                # pending, completed, inProgress
                state = list(set([j['state'] for j in self.jobs]))
                # succeeded, failed, None
                result = list(set([j['result'] for j in self.jobs]))
                if 'canceled' in result or 'cancelled' in result:
                    self._state = 'failure'
                elif len(state) == 1 and 'completed' in state:
                    if len(result) == 1 and 'succeeded' in result:
                        self._state = 'success'
                    elif 'failed' in result:
                        self._state = 'failure'
                elif 'pending' in state or 'inProgress' in state:
                    self._state = 'pending'
                else:
                    raise ValueError(
                        'Unknown state for buildId: %s, state: %s' % (self.build_id, state)
                    )

        return self._state

    @property
    def updated_at(self):
        if self._updated_at is None:
            self.jobs

        return self._updated_at

    @property
    def stages(self):
        if self._stages is None:
            self.jobs

        return self._stages

    def get_last_full_run_date(self):
        # FIXME fix the method name, it makes sense for shippable but not for azp
        if self.state is None:
            raise NoCIError
        # FIXME pending?
        #if self.state == u'pending':
        #    raise NoCIError
        if self.created_at is None:
            raise NoCIError
        return self.created_at

    @property
    def artifacts(self):
        if self._artifacts is None:
            # FIXME deduplicate code
            if not os.path.isdir(self._cachedir):
                os.makedirs(self._cachedir)

            data = None
            cache_file = os.path.join(self._cachedir, u'artifacts_%s.pickle' % self.build_id)
            if os.path.isfile(cache_file):
                logging.info(u'load artifacts cache')
                with open(cache_file, 'rb') as f:
                    data = pickle_load(f)

            if data is None or (data and data[0] < self.updated_at) or not data[1]:
                if data:
                    logging.info(u'fetching artifacts: stale, previous from %s' % data[0])
                else:
                    logging.info(u'fetching artifacts: stale, no previous data')

                resp = fetch(ARTIFACTS_URL_FMT % self.build_id)
                check_response(resp)
                data = [a for a in resp.json()['value'] if a['name'].startswith('Bot')]
                data = (self.updated_at, data)

                logging.info(u'writing %s' % cache_file)
                with open(cache_file, 'wb') as f:
                    pickle_dump(data, f)

            self._artifacts = data[1]

        return self._artifacts

    def get_artifact(self, name, url):
        if not os.path.isdir(self._cachedir):
            os.makedirs(self._cachedir)

        data = None
        cache_file = os.path.join(self._cachedir, u'%s_%s.pickle' % (name.replace(' ', '-'), self.build_id))
        if os.path.isfile(cache_file):
            logging.info(u'loading %s' % cache_file)
            with open(cache_file, 'rb') as f:
                data = pickle_load(f)

        if data is None or (data and data[0] < self.updated_at) or not data[1]:
            if data:
                logging.info(u'fetching artifacts: stale, previous from %s' % data[0])
            else:
                logging.info(u'fetching artifacts: stale, no previous data')

            resp = fetch(url, stream=True)
            check_response(resp)
            with BytesIO() as data:
                for chunk in resp.iter_content(chunk_size=128):
                    data.write(chunk)
                artifact_zip = ZipFile(data)

                artifact_data = []
                for fn in artifact_zip.namelist():
                    if 'ansible-test-' not in fn:
                        continue
                    with artifact_zip.open(fn) as f:
                        artifact_data.append(json.load(f))

                data = (self.updated_at, artifact_data)
                logging.info(u'writing %s' % cache_file)
                with open(cache_file, 'wb') as f:
                    pickle_dump(data, f)

        return data[1]

    def get_test_results(self):
        if self.state in ('pending', 'inProgress', None):
            return [], False

        failed_jobs = [j for j in self.jobs if j['result'] == 'failed']
        if not failed_jobs:
            return [], False

        results = []
        ci_verified = True
        for job in failed_jobs:
            for artifact in self.artifacts:
                if job['id'] != artifact['source']:
                    continue
                for artifact_json in self.get_artifact(artifact['name'], artifact['resource']['downloadUrl']):
                    if not artifact_json['verified']:
                        ci_verified = False

                    result_data = ''
                    for result in artifact_json['results']:
                        result_data += result['message'] + result['output']

                    results.append({
                        'contents': {
                            'results': artifact_json['results'],
                        },
                        'run_id': self.build_id,
                        'job_id': hashlib.md5(to_bytes(result_data)).hexdigest(),
                        'path': None,
                    })

        return results, ci_verified

    def rebuild(self, run_id, failed_only=False):
        if failed_only:
            api_version = u'6.0-preview.1'
            data = '{"state":"retry"}'
            stages = [s['identifier'] for s in self.stages if s['result'] != 'succeeded']
        else:
            api_version = u'6.1-preview.1'
            data = '{"state":"retry","forceRetryAllJobs":true}'
            stages = [s['identifier'] for s in self.stages]

        for stage in stages:
            if stage == 'Summary':
                continue
            url = u'https://dev.azure.com/' + C.DEFAULT_AZP_ORG + '/' + C.DEFAULT_AZP_PROJECT + '/_apis/build/builds/%s/stages/%s?api-version=%s' % (run_id, stage, api_version)

            resp = fetch(
                url,
                verb='patch',
                headers=HEADERS,
                data=data,
                timeout=TIMEOUT,
                auth=(C.DEFAULT_AZP_USER, C.DEFAULT_AZP_TOKEN),
            )

            if not resp:
                raise Exception("Unable to PATCH %r to %r" % (data, url))
            check_response(resp)

    def rebuild_failed(self, run_id):
        self.rebuild(run_id, failed_only=True)

    def cancel(self, run_id):
        data = '{"state":"cancel"}'
        for stage in [s['identifier'] for s in self.stages if s['state'] != 'completed']:
            if stage == 'Summary':
                continue
            url = u'https://dev.azure.com/' + C.DEFAULT_AZP_ORG + '/' + C.DEFAULT_AZP_PROJECT + '/_apis/build/builds/%s/stages/%s?api-version=6.0-preview.1' % (run_id, stage)

            resp = fetch(
                url,
                verb='patch',
                headers=HEADERS,
                data=data,
                timeout=TIMEOUT,
                auth=(C.DEFAULT_AZP_USER, C.DEFAULT_AZP_TOKEN),
            )

            if not resp:
                raise Exception("Unable to PATCH %r to %r" % (data, url))
            check_response(resp)

    def cancel_on_branch(self, branch):
        # FIXME cancel() should be enough?
        pass
