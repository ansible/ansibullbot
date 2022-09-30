import logging
import os
import pickle
import shutil
from datetime import datetime

import requests
from github import Github

import ansibullbot.constants as C

from ansibullbot.utils.github import RateLimited
from ansibullbot.exceptions import RateLimitError


HEADERS = [
    'application/json',
    'application/vnd.github.mockingbird-preview',
    'application/vnd.github.sailor-v-preview+json',
    'application/vnd.github.starfox-preview+json',
    'application/vnd.github.squirrel-girl-preview',
    'application/vnd.github.v3+json',
]


class GithubWrapper:
    def __init__(self, url=None, user=None, passw=None, token=None, cachedir='~/.ansibullbot/cache'):
        self.gh = self._connect(url, user, passw, token)
        self.token = token
        self.cachedir = os.path.expanduser(cachedir)
        self.cached_requests_dir = os.path.join(self.cachedir, 'cached_requests')

    @RateLimited
    def _connect(self, url, user, passw, token):
        """Connects to GitHub's API"""
        if token:
            return Github(base_url=url, login_or_token=token)
        else:
            return Github(
                base_url=url,
                login_or_token=user,
                password=passw
            )

    @RateLimited
    def get_request(self, url):
        '''Get an arbitrary API endpoint'''

        headers = {
            'Accept': ','.join(HEADERS),
            'Authorization': 'Bearer %s' % self.token,
        }

        rr = requests.get(url, headers=headers)
        data = rr.json()

        # handle ratelimits ...
        if isinstance(data, dict) and data.get('message'):
            if data['message'].lower().startswith('api rate limit exceeded'):
                raise RateLimitError()

        # pagination
        if hasattr(rr, 'links') and rr.links and rr.links.get('next'):
            _data = self.get_request(rr.links['next']['url'])
            if isinstance(data, list):
                data += _data
            elif isinstance(data, dict):
                data.update(_data)

        return data


class RepoWrapper:
    def __init__(self, gh, repo_path, cachedir='~/.ansibullbot/cache'):
        self.gh = gh
        self.cachedir = os.path.join(os.path.expanduser(cachedir), repo_path)

        self._assignees = False
        self._labels = False
        self.repo = self.get_repo(repo_path)

    def has_in_assignees(self, login):
        logins = [x.login for x in self.assignees]
        return login in logins

    @RateLimited
    def get_repo(self, repo_path):
        logging.getLogger('github.Requester').setLevel(logging.INFO)
        repo = self.gh.get_repo(repo_path)
        return repo

    @RateLimited
    def get_issue(self, number):
        while True:
            try:
                issue = self.load_issue(number)
                if issue and C.DEFAULT_GITHUB_TOKEN in issue._requester._Requester__authorizationHeader:
                    if issue.update():
                        self.save_issue(issue)
                else:
                    issue = self.repo.get_issue(number)
                    self.save_issue(issue)
                break
            except UnicodeDecodeError:
                # https://github.com/ansible/ansibullbot/issues/610
                logging.warning('cleaning cache for %s' % number)
                shutil.rmtree(os.path.join(self.cachedir, 'issues', str(number)))

        return issue

    @RateLimited
    def get_pullrequest(self, number):
        pr = self.repo.get_pull(number)
        return pr

    def is_pr_merged(self, number):
        try:
            return self.get_pullrequest(number).merged
        except Exception as e:
            logging.debug(e)
            return False

    @property
    def labels(self):
        if self._labels is False:
            self._labels = self.load_update_fetch('labels')
        return self._labels

    @property
    def assignees(self):
        if self._assignees is False:
            self._assignees = self.load_update_fetch('assignees')
        return self._assignees

    def get_issues(self, since=None):
        if since:
            return self.repo.get_issues(since=since)
        else:
            return self.repo.get_issues()

    def load_issue(self, number):
        if not C.DEFAULT_PICKLE_ISSUES:
            return False

        pfile = os.path.join(
            self.cachedir,
            'issues',
            str(number),
            'issue.pickle'
        )
        if os.path.isfile(pfile):
            with open(pfile, 'rb') as f:
                try:
                    issue = pickle.load(f)
                except TypeError:
                    return False
            return issue
        else:
            return False

    def save_issue(self, issue):
        if not C.DEFAULT_PICKLE_ISSUES:
            return

        cfile = os.path.join(
            self.cachedir,
            'issues',
            str(issue.number),
            'issue.pickle'
        )
        cdir = os.path.dirname(cfile)
        if not os.path.isdir(cdir):
            os.makedirs(cdir)
        logging.debug('dump %s' % cfile)
        with open(cfile, 'wb') as f:
            pickle.dump(issue, f)

    @RateLimited
    def load_update_fetch(self, property_name):
        '''Fetch a get() property for an object'''
        edata = None
        events = []
        updated = None
        update = False
        write_cache = False

        self.repo.update()

        pfile = os.path.join(self.cachedir, '%s.pickle' % property_name)
        pdir = os.path.dirname(pfile)

        if not os.path.isdir(pdir):
            os.makedirs(pdir)

        if os.path.isfile(pfile):
            try:
                with open(pfile, 'rb') as f:
                    edata = pickle.load(f)
            except Exception:
                update = True
                write_cache = True

            # check the timestamp on the cache
            if edata:
                updated = edata[0]
                events = edata[1]
                if updated < self.repo.updated_at:
                    update = True
                    write_cache = True

        # pull all events if timestamp is behind or no events cached
        if update or not events:
            write_cache = True
            updated = datetime.utcnow()
            methodToCall = getattr(self.repo, 'get_' + property_name)
            events = [x for x in methodToCall()]

        if C.DEFAULT_PICKLE_ISSUES:
            if write_cache or not os.path.isfile(pfile):
                # need to dump the pickle back to disk
                edata = [updated, events]
                with open(pfile, 'wb') as f:
                    pickle.dump(edata, f)

        return events

    @RateLimited
    def get_file_contents(self, filepath):
        try:
            return self.repo.get_file_contents(filepath)
        except Exception:
            pass
