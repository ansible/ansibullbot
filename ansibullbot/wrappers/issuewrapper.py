# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible. If not, see <http://www.gnu.org/licenses/>.


import datetime
import json
import logging
import os
import pickle
import re
import time

import pytz

import ansibullbot.constants as C
from ansibullbot.decorators.github import RateLimited
from ansibullbot.utils.extractors import get_template_data
from ansibullbot.utils.timetools import strip_time_safely
from ansibullbot.wrappers.historywrapper import HistoryWrapper


class UnsetValue:
    def __str__(self):
        return "AnsibullbotUnsetValue()"


class IssueWrapper:
    def __init__(self, github=None, repo=None, issue=None, cachedir=None, gitrepo=None):
        self.github = github
        self.repo = repo
        self.instance = issue
        self.cachedir = cachedir
        self.gitrepo = gitrepo

        self.meta = {}
        self._assignees = UnsetValue
        self._committer_emails = False
        self._committer_logins = False
        self._commits = False
        self._events = UnsetValue
        self._history = False
        self._labels = False
        self._merge_commits = False
        self._migrated = None
        self._migrated_from = None
        self._migrated_issue = None
        self._pr = False
        self._pr_reviews = False
        self._repo_full_name = False
        self._template_data = None
        self._pull_raw = None
        self._pr_files = None
        self.full_cachedir = os.path.join(self.cachedir, 'issues', str(self.number))
        self._renamed_files = None
        self._pullrequest_check_runs = None

    @property
    def url(self):
        return self.instance.url

    @property
    def comments(self):
        return [x for x in self.history.history if x['event'] == 'commented']

    @property
    def events(self):
        if self._events is UnsetValue:
            self._events = self._parse_events(self._get_timeline())

        return self._events

    def _parse_events(self, events):
        processed_events = []
        for event_no, dd in enumerate(events):
            if dd['event'] == 'committed':
                # FIXME
                # commits are added through HistoryWrapper.merge_commits()
                continue

            # reviews do not have created_at keys
            if not dd.get('created_at') and dd.get('submitted_at'):
                dd['created_at'] = dd['submitted_at']

            # commits do not have created_at keys
            if not dd.get('created_at') and dd.get('author'):
                dd['created_at'] = dd['author']['date']

            # commit comments do not have created_at keys
            if not dd.get('created_at') and dd.get('comments'):
                dd['created_at'] = dd['comments'][0]['created_at']

            if not dd.get('created_at'):
                raise AssertionError(dd)

            # commits do not have actors
            if not dd.get('actor'):
                dd['actor'] = {'login': None}

            # fix commits with no message
            if dd['event'] == 'committed' and 'message' not in dd:
                dd['message'] = ''

            if not dd.get('id'):
                # set id as graphql node_id OR make one up
                if 'node_id' in dd:
                    dd['id'] = dd['node_id']
                else:
                    dd['id'] = '%s/%s/%s/%s' % (self.repo_full_name, self.number, 'timeline', event_no)

            event = {
                'id': dd['id'],
                'actor': dd['actor']['login'],
                'event': dd['event'],
            }
            if isinstance(dd['created_at'], str):
                dd['created_at'] = strip_time_safely(dd['created_at'])

            event['created_at'] = pytz.utc.localize(dd['created_at'])

            if dd['event'] in ['labeled', 'unlabeled']:
                event['label'] = dd.get('label', {}).get('name', None)
            elif dd['event'] == 'referenced':
                event['commit_id'] = dd['commit_id']
            elif dd['event'] == 'assigned':
                event['assignee'] = dd['assignee']['login']
                event['assigner'] = event['actor']
            elif dd['event'] == 'commented':
                event['body'] = dd['body']
            elif dd['event'] == 'cross-referenced':
                event['source'] = dd['source']

            processed_events.append(event)

        return sorted(processed_events, key=lambda x: x['created_at'])

    def _get_timeline(self):
        '''Use python-requests instead of pygithub'''
        data = None

        cache_data = os.path.join(self.full_cachedir, 'timeline_data.json')
        cache_meta = os.path.join(self.full_cachedir, 'timeline_meta.json')
        logging.debug(cache_data)

        if not os.path.exists(self.full_cachedir):
            os.makedirs(self.full_cachedir)

        meta = {}
        fetch = False
        if not os.path.exists(cache_data):
            fetch = True
        else:
            with open(cache_meta) as f:
                meta = json.loads(f.read())

        if not fetch and (not meta or meta.get('updated_at', 0) < self.updated_at.isoformat()):
            fetch = True

        # validate the data is not infected by ratelimit errors
        if not fetch:
            with open(cache_data) as f:
                data = json.loads(f.read())

            if isinstance(data, list):
                bad_events = [x for x in data if not isinstance(x, dict)]
                if bad_events:
                    fetch = True
            else:
                fetch = True

        if data is None:
            fetch = True

        if fetch:
            url = self.url + '/timeline'
            data = self.github.get_request(url)

            with open(cache_meta, 'w') as f:
                f.write(json.dumps({
                    'updated_at': self.updated_at.isoformat(),
                    'url': url
                }))
            with open(cache_data, 'w') as f:
                f.write(json.dumps(data))

        return data

    @RateLimited
    def load_update_fetch_files(self):
        edata = None
        events = []
        updated = None
        update = False
        write_cache = False

        pfile = os.path.join(self.full_cachedir, 'files.pickle')
        pdir = os.path.dirname(pfile)
        logging.debug(pfile)

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
            if updated < self.instance.updated_at:
                update = True
                write_cache = True

        # pull all events if timestamp is behind or no events cached
        if update or not events:
            write_cache = True
            updated = datetime.datetime.utcnow()
            events = [x for x in self.pullrequest.get_files()]

        if C.DEFAULT_PICKLE_ISSUES:
            if write_cache or not os.path.isfile(pfile):
                # need to dump the pickle back to disk
                edata = [updated, events]
                with open(pfile, 'wb') as f:
                    pickle.dump(edata, f)

        return events

    @RateLimited
    def get_labels(self):
        """Pull the list of labels on this Issue"""
        labels = []
        for label in self.instance.labels:
            labels.append(label.name)
        return labels

    @property
    def template_data(self):
        if self._template_data is None:
            self._template_data = get_template_data(self)
        return self._template_data

    @RateLimited
    def add_label(self, label=None):
        """Adds a label to the Issue using the GitHub API"""
        self.instance.add_to_labels(label)

    @RateLimited
    def remove_label(self, label=None):
        """Removes a label from the Issue using the GitHub API"""
        self.instance.remove_from_labels(label)

    @RateLimited
    def add_comment(self, comment=None):
        """Adds a comment to the Issue using the GitHub API"""
        self.instance.create_comment(comment)

    @RateLimited
    def remove_comment_by_id(self, commentid):
        if not isinstance(commentid, int):
            raise Exception("commentIds must be integers!")
        comment_url = os.path.join(
            C.DEFAULT_GITHUB_URL,
            'repos',
            self.repo_full_name,
            'issues',
            'comments',
            str(commentid)
        )
        current_data = self.github.get_request(comment_url)
        if current_data and current_data.get('message') != 'Not Found':
            ok = self.github.delete_request(comment_url)
            if not ok:
                raise Exception("failed to delete commentid %s for %s" % (commentid, self.html_url))

    @property
    def assignees(self):
        if self._assignees is UnsetValue:
            self._assignees = [x.login for x in self.instance.assignees]
        return self._assignees

    def is_pullrequest(self):
        return self.github_type == 'pullrequest'

    def is_issue(self):
        return self.github_type == 'issue'

    @property
    def age(self):
        created = self.created_at
        now = datetime.datetime.utcnow()
        age = now - created
        return age

    @property
    def title(self):
        return self.instance.title

    @property
    def repo_full_name(self):
        '''return the <org>/<repo> string'''
        # prefer regex over making GET calls
        if self._repo_full_name is False:
            try:
                url = self.url
                full_name = re.search(r'repos\/\w+\/\w+\/', url).group()
                full_name = full_name.replace('repos/', '')
                full_name = full_name.strip('/')
            except Exception:
                full_name = self.repo.repo.full_name

            self._repo_full_name = full_name

        return self._repo_full_name

    @property
    def html_url(self):
        return self.instance.html_url

    @property
    def created_at(self):
        return self.instance.created_at

    @property
    def updated_at(self):
        # this is a hack to fix unit tests
        if self.instance is not None:
            if self.instance.updated_at is not None:
                return self.instance.updated_at

        return datetime.datetime.utcnow()

    @property
    def closed_at(self):
        return self.instance.closed_at

    @property
    def merged_at(self):
        return self.instance.merged_at

    @property
    def state(self):
        return self.instance.state

    @property
    def github_type(self):
        if '/pull/' in self.html_url:
            return 'pullrequest'
        else:
            return 'issue'

    @property
    def number(self):
        return self.instance.number

    @property
    def submitter(self):
        # auto-migrated issue by ansibot{-dev}
        # figure out the original submitter
        if self.instance.user.login in C.DEFAULT_BOT_NAMES:
            m = re.match('From @(.*) on', self.instance.body)
            if m:
                return m.group(1)

        return self.instance.user.login

    @property
    def pullrequest(self):
        if not self._pr:
            logging.debug('@pullrequest.get_pullrequest #%s' % self.number)
            self._pr = self.repo.get_pullrequest(self.number)
        return self._pr

    def update_pullrequest(self):
        if self.is_pullrequest():
            # the underlying call is wrapper with ratelimited ...
            self._pr = self.repo.get_pullrequest(self.number)
            self._pr_reviews = False
            self._merge_commits = False
            self._committer_emails = False

    @property
    @RateLimited
    def pullrequest_check_runs(self):
        if self._pullrequest_check_runs is None:
            logging.info('fetching pull request check runs')
            self._pullrequest_check_runs = self.commits[-1].get_check_runs()
        return self._pullrequest_check_runs

    @property
    @RateLimited
    def pullrequest_raw_data(self):
        if not self._pull_raw:
            logging.info('@pullrequest_raw_data')
            self._pull_raw = self.pullrequest.raw_data
        return self._pull_raw

    @property
    def pr_files(self):
        if self._pr_files is None:
            self._pr_files = self.load_update_fetch_files()
        return self._pr_files

    @property
    def files(self):
        if self.is_issue():
            return None
        return [x.filename for x in self.pr_files]

    @property
    def new_files(self):
        new_files = [x for x in self.files if x not in self.gitrepo.files]
        new_files = [x for x in new_files if not self.gitrepo.existed(x)]
        return new_files

    @property
    def new_modules(self):
        new_modules = self.new_files
        new_modules = [
            x for x in new_modules if x.startswith('lib/ansible/modules')
        ]
        new_modules = [
            x for x in new_modules if not os.path.basename(x) == '__init__.py'
        ]
        new_modules = [
            x for x in new_modules if not os.path.basename(x).startswith('_')
        ]
        new_modules = [
            x for x in new_modules if not os.path.basename(x).endswith('.ps1')
        ]
        return new_modules

    @property
    def body(self):
        return self.instance.body

    @property
    def labels(self):
        if self._labels is False:
            self._labels = [x for x in self.get_labels()]
        return self._labels

    @property
    def reviews(self):
        if self._pr_reviews is False:
            self._pr_reviews = [r.raw_data for r in self.pullrequest.get_reviews()]

        # https://github.com/ansible/ansibullbot/issues/881
        # https://github.com/ansible/ansibullbot/issues/883
        for idx, x in enumerate(self._pr_reviews):
            if 'commit_id' not in x:
                self._pr_reviews[idx]['commit_id'] = None

        return self._pr_reviews

    @property
    def history(self):
        if self._history is False:
            self._history = HistoryWrapper(self, cachedir=self.cachedir)
        return self._history

    @property
    def commits(self):
        if self._commits is False:
            self._commits = self.get_commits()
        return self._commits

    @RateLimited
    def get_commits(self):
        if not self.is_pullrequest():
            return None
        commits = [x for x in self.pullrequest.get_commits()]
        return commits

    @property
    def mergeable(self):
        return self.pullrequest.mergeable

    @property
    def mergeable_state(self):
        if not self.is_pullrequest() or self.pullrequest.state == 'closed':
            return None

        # http://stackoverflow.com/a/30620973
        fetchcount = 0
        while self.pullrequest.mergeable_state == 'unknown':
            fetchcount += 1
            if fetchcount >= 10:
                logging.warning('exceeded fetch threshold for mstate')
                return False

            logging.warning(
                're-fetch[%s] PR#%s because mergeable state is unknown' % (
                    fetchcount,
                    self.number
                 )
            )

            self.update_pullrequest()
            time.sleep(1)

        return self.pullrequest.mergeable_state

    @property
    def wip(self):
        return (
            self.title.startswith('WIP') or
            '[WIP]' in self.title or
            (self.is_pullrequest() and self.pullrequest.draft)
        )

    @property
    def incoming_repo_exists(self):
        return self.pullrequest.head.repo is not None

    @property
    def incoming_repo_slug(self):
        try:
            return self.pullrequest.head.repo.full_name
        except TypeError:
            return None

    @property
    def from_fork(self):
        if not self.incoming_repo_exists:
            return True

        return self.incoming_repo_slug != 'ansible/ansible'

    @RateLimited
    def get_commit_files(self, commit):
        cdata = self.github.get_cached_request(commit.url)
        files = cdata.get('files', [])
        return files

    @RateLimited
    def get_commit_login(self, commit):
        cdata = self.github.get_cached_request(commit.url)

        # https://github.com/ansible/ansibullbot/issues/1265
        # some commits are created from outside github and have no assocatied login
        if ('author' in cdata and cdata['author'] is None) or \
            ('author' not in cdata):
            return ''
        login = cdata['author']['login']

        return login

    @property
    @RateLimited
    def merge_commits(self):
        # https://api.github.com/repos/ansible/ansible/pulls/91/commits
        if self._merge_commits is False:
            self._merge_commits = []
            for commit in self.commits:
                commit_data = self.github.get_cached_request(commit.url)
                if len(commit_data['parents']) > 1 or commit_data['commit']['message'].startswith('Merge branch'):
                    self._merge_commits.append(commit)
        return self._merge_commits

    @property
    def committer_emails(self):
        if self._committer_emails is False:
            self._committer_emails = []
            for commit in self.commits:
                self.committer_emails.append(commit.commit.author.email)
        return self._committer_emails

    @property
    def committer_logins(self):
        if self._committer_logins is False:
            self._committer_logins = []
            for commit in self.commits:
                self.committer_logins.append(self.get_commit_login(commit))
        return self._committer_logins

    def merge(self):
        if self.merge_commits:
            return None

        # unique the lists so that we can tell how many people
        # have worked on this particular pullrequest
        emails = sorted(set(self.committer_emails))
        logins = sorted(set(self.committer_logins))

        if len(self.commits) == 1 or len(emails) == 1 or len(logins) == 1:
            # squash single committer PRs
            merge_method = 'squash'
        elif (len(self.commits) == len(emails)) and len(self.commits) <= 10:
            # rebase multi-committer PRs
            merge_method = 'rebase'
        else:
            logging.error('merge skipped for %s' % self.number)
            return

        merge_status = self.pullrequest.merge(merge_method=merge_method)

        if merge_status.merged:
            logging.info('merge successful for %s' % self.number)
        else:
            logging.error('merge failed on %s - %s' % (self.number, merge_status.messsage))
            raise Exception('merge failed on %s - %s' % (self.number, merge_status.messsage))

    @property
    def migrated_from(self):
        self.migrated
        return self._migrated_from

    @property
    def migrated(self):
        if self._migrated is None:
            if self.body and 'Copied from original issue' in self.body:
                self._migrated = True
                idx = self.body.find('Copied from original issue')
                msg = self.body[idx:]
                try:
                    migrated_issue = msg.split()[4]
                except Exception as e:
                    logging.error(e)
                    raise Exception('split failed')
                if migrated_issue.endswith('_'):
                    migrated_issue = migrated_issue.rstrip('_')
                self._migrated_from = migrated_issue
            else:
                for comment in self.comments:
                    if comment['body'].lower().startswith('migrated from'):
                        self._migrated = True
                        bparts = comment['body'].split()
                        self._migrated_from = bparts[2]
                        break
        return self._migrated

    @property
    def renamed_files(self):
        ''' A map of renamed files to prevent other code from thinking these are new files '''
        if self._renamed_files is not None:
            return self._renamed_files

        self._renamed_files = {}
        if self.is_issue():
            return self._renamed_files

        for x in self.commits:
            rd = x.raw_data
            for filed in rd.get('files', []):
                if filed.get('previous_filename'):
                    src = filed['previous_filename']
                    dst = filed['filename']
                    self._renamed_files[dst] = src

        return self._renamed_files
