import hashlib
import logging
import json
import os.path
import pickle
import re

from io import BytesIO
from zipfile import ZipFile

import pytz

import ansibullbot.constants as C
from ansibullbot._text_compat import to_bytes
from ansibullbot.ci.base import BaseCI
from ansibullbot.errors import NoCIError
from ansibullbot.utils.net_tools import fetch
from ansibullbot.utils.timetools import strip_time_safely


DETAILS_URL_RE = \
    re.compile(
        r'https://dev\.azure\.com/(?P<organization>[^/]+)/(?P<project>[^/]+)/_build/results\?buildId=(?P<buildId>[0-9]+)'
    )
TIMELINE_URL_FMT = \
    'https://dev.azure.com/' + C.DEFAULT_AZP_ORG + '/' + C.DEFAULT_AZP_PROJECT + '/_apis/build/builds/%s/timeline/?api-version=6.0'
ARTIFACTS_URL_FMT = \
    'https://dev.azure.com/' + C.DEFAULT_AZP_ORG + '/' + C.DEFAULT_AZP_PROJECT + '/_apis/build/builds/%s/artifacts?api-version=6.0'
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

        try:
            self.created_at = min(
                (strip_time_safely(j['startTime']) for j in self.jobs if j['startTime'] is not None)
            )
        except ValueError:
            self.created_at = self.updated_at

        if self.state and self.build_id and self.jobs:
            self.last_run = {
                'state': self.state,
                'created_at': pytz.utc.localize(self.created_at),
                'updated_at': pytz.utc.localize(self.updated_at),
                'run_id': self.build_id,
            }

    @property
    def build_id(self):
        if self._build_id is None:
            build_ids = set()
            for check_run in self._iw.pullrequest_check_runs:
                match = re.match(DETAILS_URL_RE, check_run.details_url)
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
                if not os.path.isdir(self._cachedir):
                    os.makedirs(self._cachedir)
                cache_file = os.path.join(self._cachedir, u'timeline_%s.pickle' % self.build_id)

                url = TIMELINE_URL_FMT % self.build_id
                resp = fetch(url)
                if resp is None:
                    raise Exception("Unable to GET %s" % url)

                if resp.status_code == 404:
                    data = None
                    if os.path.isfile(cache_file):
                        logging.info(u'timeline was probably removed, load it from cache')
                        with open(cache_file, 'rb') as f:
                            data = pickle.load(f)
                else:
                    data = resp.json()
                    data = (strip_time_safely(data['lastChangedOn']), data)
                    logging.info(u'writing %s' % cache_file)
                    with open(cache_file, 'wb') as f:
                        pickle.dump(data, f)

                if data is not None:
                    data = data[1]
                    self._jobs = [r for r in data['records'] if r['type'] == 'Job']
                    self._updated_at = strip_time_safely(data['lastChangedOn'])  # FIXME
                    self._stages = [r for r in data['records'] if r['type'] == 'Stage']  # FIXME
                else:
                    self._jobs = []
                    self._updated_at = strip_time_safely('1970-01-01')
                    self._stages = []
            else:
                self._jobs = []
        return self._jobs

    @property
    def state(self):
        if self._state is None:
            if self.jobs:
                # pending, completed, inProgress
                state = list({j['state'] for j in self.jobs})
                # succeeded, failed, None
                result = list({j['result'] for j in self.jobs})
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
        if self.state is None and self.build_id is None:
            raise NoCIError
        # FIXME pending?
        #if self.state == u'pending':
        #    raise NoCIError
        if self.created_at is None:
            raise NoCIError
        return self.created_at

    @property
    def artifacts(self):
        if self._artifacts is None and self._jobs:
            # FIXME deduplicate code
            if not os.path.isdir(self._cachedir):
                os.makedirs(self._cachedir)

            data = None
            cache_file = os.path.join(self._cachedir, 'artifacts_%s.pickle' % self.build_id)
            if os.path.isfile(cache_file):
                logging.info('load artifacts cache')
                with open(cache_file, 'rb') as f:
                    data = pickle.load(f)

            if data is None or (data and data[0] < self.updated_at) or not data[1]:
                if data:
                    logging.info('fetching artifacts: stale, previous from %s' % data[0])
                else:
                    logging.info('fetching artifacts: stale, no previous data')

                url = ARTIFACTS_URL_FMT % self.build_id
                resp = fetch(url)
                if resp is None:
                    raise Exception("Unable to GET %s" % url)

                if resp.status_code != 404:
                    data = [a for a in resp.json()['value'] if a['name'].startswith('Bot')]
                    data = (self.updated_at, data)

                    logging.info('writing %s' % cache_file)
                    with open(cache_file, 'wb') as f:
                        pickle.dump(data, f)
            if data:
                self._artifacts = data[1]

        return self._artifacts

    def get_artifact(self, name, url):
        if not os.path.isdir(self._cachedir):
            os.makedirs(self._cachedir)

        data = None
        cache_file = os.path.join(self._cachedir, '%s_%s.pickle' % (name.replace(' ', '-'), self.build_id))
        if os.path.isfile(cache_file):
            logging.info('loading %s' % cache_file)
            with open(cache_file, 'rb') as f:
                data = pickle.load(f)

        if data is None or (data and data[0] < self.updated_at) or not data[1]:
            if data:
                logging.info('fetching artifacts: stale, previous from %s' % data[0])
            else:
                logging.info('fetching artifacts: stale, no previous data')

            resp = fetch(url, stream=True)
            if resp is None:
                raise Exception("Unable to GET %s" % url)

            if resp.status_code != 404:
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
                    logging.info('writing %s' % cache_file)
                    with open(cache_file, 'wb') as f:
                        pickle.dump(data, f)
        if data:
            return data[1]

    def get_test_results(self):
        if self.state in ('pending', 'inProgress', None):
            return [], False

        failed_jobs = [j for j in self.jobs if j['result'] == 'failed']
        if not failed_jobs:
            return [], False

        results = []
        ci_verified = True
        failed_jobs_with_artifact = 0
        for job in failed_jobs:
            for artifact in self.artifacts:
                if job['id'] != artifact['source']:
                    continue
                failed_jobs_with_artifact += 1
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

        if ci_verified and len(failed_jobs) != failed_jobs_with_artifact:
            ci_verified = False

        return results, ci_verified

    def rebuild(self, run_id, failed_only=False):
        if failed_only:
            api_version = '6.0-preview.1'
            data = '{"state":"retry"}'
            stages = [s['identifier'] for s in self.stages if s['result'] != 'succeeded']
        else:
            api_version = '6.1-preview.1'
            data = '{"state":"retry","forceRetryAllJobs":true}'
            stages = [s['identifier'] for s in self.stages]

        for stage in stages:
            url = 'https://dev.azure.com/' + C.DEFAULT_AZP_ORG + '/' + C.DEFAULT_AZP_PROJECT + '/_apis/build/builds/%s/stages/%s?api-version=%s' % (run_id, stage, api_version)

            resp = fetch(
                url,
                verb='patch',
                headers=HEADERS,
                data=data,
                timeout=TIMEOUT,
                auth=(C.DEFAULT_AZP_USER, C.DEFAULT_AZP_TOKEN),
            )
            if resp is not None and resp.status_code == 404:
                data = '{"definition":{"id":20},"reason":"pullRequest","sourceBranch":"refs/pull/%s/merge","repository":{"type":"github"},"triggerInfo":{"pr.sourceBranch":"%s","pr.sourceSha":"%s","pr.id":"%s","pr.title":"%s","pr.number":"%s","pr.isFork":"%s","pr.draft":"%s","pr.sender.name":"%s","pr.sender.avatarUrl":"%s","pr.providerId":"github","pr.autoCancel":"true"},"parameters":"{\\"system.pullRequest.pullRequestId\\":\\"%s\\",\\"system.pullRequest.pullRequestNumber\\":\\"%s\\",\\"system.pullRequest.mergedAt\\":\\"\\",\\"system.pullRequest.sourceBranch\\":\\"%s\\",\\"system.pullRequest.targetBranch\\":\\"%s\\",\\"system.pullRequest.sourceRepositoryUri\\":\\"https://github.com/ansible/ansible\\",\\"system.pullRequest.sourceCommitId\\":\\"%s\\"}"}' % (
                        self._iw.number,
                        self._iw._pr.head.ref,
                        self._iw._pr.head.sha,
                        self._iw._pr.id,
                        self._iw._pr.title,
                        self._iw._pr.number,
                        self._iw.from_fork,
                        self._iw._pr.draft,
                        self._iw._pr.user.login,
                        self._iw._pr.user.avatar_url,
                        self._iw._pr.id,
                        self._iw._pr.number,
                        self._iw._pr.head.ref,
                        self._iw._pr.base.ref,
                        self._iw._pr.head.sha,)

                url = 'https://dev.azure.com/' + C.DEFAULT_AZP_ORG + '/' + C.DEFAULT_AZP_PROJECT + '/_apis/build/builds?api-version=6.0'
                resp = fetch(
                    url,
                    verb='post',
                    headers=HEADERS,
                    data=data,
                    timeout=30,
                    auth=(C.DEFAULT_AZP_USER, C.DEFAULT_AZP_TOKEN),
                )
                if not resp:
                    raise Exception("Unable to POST %r to %r" % (data, url))
                break

    def rebuild_failed(self, run_id):
        self.rebuild(run_id, failed_only=True)

    def cancel(self, run_id):
        data = '{"state":"cancel"}'
        for stage in [s['identifier'] for s in self.stages if s['state'] != 'completed']:
            if stage == 'Summary':
                continue
            url = 'https://dev.azure.com/' + C.DEFAULT_AZP_ORG + '/' + C.DEFAULT_AZP_PROJECT + '/_apis/build/builds/%s/stages/%s?api-version=6.0-preview.1' % (run_id, stage)

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

    def cancel_on_branch(self, branch):
        # FIXME cancel() should be enough?
        pass
