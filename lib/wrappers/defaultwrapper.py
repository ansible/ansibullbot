#!/usr/bin/python
#
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

from __future__ import print_function

import inspect
import json
import logging
import os
import pickle
import shutil
import sys
from datetime import datetime

# remember to pip install PyGithub, kids!
import github

from lib.utils.extractors import extract_template_data
from lib.wrappers.decorators import RateLimited
from lib.wrappers.historywrapper import HistoryWrapper


class DefaultWrapper(object):

    ALIAS_LABELS = {
        'core_review': [
            'core_review_existing'
        ],
        'community_review': [
            'community_review_existing',
            'community_review_new',
            'community_review_owner_pr',
        ],
        'shipit': [
            'shipit_owner_pr'
        ],
        'needs_revision': [
            'needs_revision_not_mergeable'
        ],
        'pending_action': [
            'pending_action_close_me',
            'pending_maintainer_unknown'
        ]
    }

    MANUAL_INTERACTION_LABELS = [
    ]

    MUTUALLY_EXCLUSIVE_LABELS = [
        "bug_report",
        "feature_idea",
        "docs_report"
    ]

    TOPIC_MAP = {'amazon': 'aws',
                 'google': 'gce',
                 'network': 'networking'}

    REQUIRED_SECTIONS = []

    def __init__(self, repo=None, issue=None, cachedir=None):
        self.cachedir = cachedir
        self.repo = repo
        self.instance = issue
        #self.number = self.instance.number
        #self.current_labels = self.get_current_labels()
        #self.current_labels = []
        self._assignees = False
        self._comments = False
        self._commits = False
        self._events = False
        self._history = False
        self._labels = False
        self._pr = False
        self._pr_status = False
        self._pr_reviews = False
        self._reactions = False
        self.template_data = {}
        self.desired_labels = []
        self.desired_assignees = []
        self.current_events = []
        self.current_comments = []
        self.current_bot_comments = []
        self.last_bot_comment = None
        self.current_reactions = []
        self.desired_comments = []
        self.current_state = 'open'
        self.desired_state = 'open'
        self.pr_status_raw = None
        self.pull_raw = None
        self.pr_files = []
        #self.history = None

        self.full_cachedir = os.path.join(
            self.cachedir,
            'issues',
            str(self.number)
        )

        self.valid_assignees = []
        self.raw_data_issue = self.load_update_fetch('raw_data', obj='issue')

    def get_rate_limit(self):
        return self.repo.gh.get_rate_limit()

    def get_current_time(self):
        return datetime.utcnow()

    def save_issue(self):
        pfile = os.path.join(
            self.cachedir,
            'issues',
            str(self.instance.number),
            'issue.pickle'
        )
        pdir = os.path.dirname(pfile)

        if not os.path.isdir(pdir):
            os.makedirs(pdir)

        logging.debug('dump %s' % pfile)
        with open(pfile, 'wb') as f:
            pickle.dump(self.instance, f)

    @RateLimited
    def get_comments(self):
        """Returns all current comments of the PR"""

        #import epdb; epdb.st()
        comments = self.load_update_fetch('comments')

        self.current_comments = [x for x in comments]
        self.current_comments.reverse()

        # look for any comments made by the bot
        for idx,x in enumerate(self.current_comments):
            body = x.body
            lines = body.split('\n')
            lines = [y.strip() for y in lines if y.strip()]

            if lines[-1].startswith('<!---') \
                    and lines[-1].endswith('--->') \
                    and 'boilerplate:' in lines[-1]\
                    and x.user.login == 'ansibot':

                parts = lines[-1].split()
                boilerplate = parts[2]
                self.current_bot_comments.append(boilerplate)

        return self.current_comments

    @property
    def events(self):
        if self._events is False:
            self._events = self.get_events()
        return self._events

    @RateLimited
    def get_events(self):
        self.current_events = self.load_update_fetch('events')
        return self.current_events

    #def get_commits(self):
    #    self.commits = self.load_update_fetch('commits')
    #    return self.commits

    def get_files(self):
        self.files = self.load_update_fetch('files')
        return self.files

    def get_review_comments(self):
        self.review_comments = self.load_update_fetch('review_comments')
        return self.review_comments

    @RateLimited
    def _fetch_api_url(self, url):
        # fetch the url and parse to json
        jdata = None
        try:
            resp = self.instance._requester.requestJson(
                'GET',
                url
            )
            data = resp[2]
            jdata = json.loads(data)
        except Exception as e:
            print(e)
            pass
        return jdata

    def relocate_pickle_files(self):
        '''Move files to the correct location to fix bad pathing'''
        srcdir = os.path.join(
            self.cachedir,
            'issues',
            str(self.instance.number)
        )
        destdir = os.path.join(
            self.cachedir,
            str(self.instance.number)
        )

        if not os.path.isdir(srcdir):
            return True

        if not os.path.isdir(destdir):
            os.makedirs(destdir)

        # move the files
        pfiles = os.listdir(srcdir)
        for pf in pfiles:
            src = os.path.join(srcdir, pf)
            dest = os.path.join(destdir, pf)
            shutil.move(src, dest)

        # get rid of the bad dir
        shutil.rmtree(srcdir)

    def load_update_fetch(self, property_name, obj=None):
        '''Fetch a property for an issue object'''

        # A pygithub issue object has methods such as ...
        #   - get_events()
        #   - get_comments()
        # Those methods return a list with no update() property,
        # so we can't take advantage of the caching scheme used
        # for the issue it's self. Instead this function calls
        # those methods by their given name, and write the data
        # to a pickle file with a timestamp for the fetch time.
        # Upon later loading of the pickle, the timestamp is
        # compared to the issue's update_at timestamp and if the
        # pickle data is behind, the process will be repeated.

        edata = None
        events = []
        updated = None
        update = False
        write_cache = False

        pfile = os.path.join(
            self.cachedir,
            'issues',
            str(self.instance.number),
            '%s.pickle' % property_name
        )
        pdir = os.path.dirname(pfile)

        if not os.path.isdir(pdir):
            os.makedirs(pdir)

        if os.path.isfile(pfile):
            try:
                with open(pfile, 'rb') as f:
                    edata = pickle.load(f)
            except Exception as e:
                update = True
                write_cache = True

        # check the timestamp on the cache
        if edata:
            updated = edata[0]
            events = edata[1]
            if updated < self.instance.updated_at:
                update = True
                write_cache = True

        baseobj = None
        if obj:
            if obj == 'issue':
                baseobj = self.instance
            elif obj == 'pullrequest':
                baseobj = self.pullrequest
        else:
            if hasattr(self.instance, 'get_' + property_name):
                baseobj = self.instance
            else:
                if self.pullrequest:
                    if hasattr(self.pullrequest, 'get_' + property_name):
                        baseobj = self.pullrequest

        if not baseobj:
            print('%s was not a property for the issue or the pullrequest'
                  % property_name)
            import epdb; epdb.st()
            sys.exit(1)

        # pull all events if timestamp is behind or no events cached
        if update or not events:
            write_cache = True
            updated = self.get_current_time()

            if not hasattr(baseobj, 'get_' + property_name) \
                    and hasattr(baseobj, property_name):
                # !callable properties
                try:
                    methodToCall = getattr(baseobj, property_name)
                except Exception as e:
                    print(e)
                    import epdb; epdb.st()
                events = methodToCall
            else:
                # callable properties
                try:
                    methodToCall = getattr(baseobj, 'get_' + property_name)
                except Exception as e:
                    print(e)
                    import epdb; epdb.st()
                events = [x for x in methodToCall()]

        if write_cache or not os.path.isfile(pfile):
            # need to dump the pickle back to disk
            edata = [updated, events]
            with open(pfile, 'wb') as f:
                pickle.dump(edata, f)

        return events

    def get_assignee(self):
        assignee = None
        if self.instance.assignee is None:
            pass
        elif type(self.instance.assignee) != list:
            assignee = self.instance.assignee.login
        else:
            assignee = []
            for x in self.instance.assignee:
                assignee.append(x.login)
            import epdb; epdb.st()
        return assignee

    @property
    def reactions(self):
        if self._reactions is False:
            self._reactions = [x for x in self.get_reactions()]
        return self._reactions

    @RateLimited
    def get_reactions(self):
        # https://developer.github.com/v3/reactions/
        if not self.current_reactions:
            baseurl = self.instance.url
            reactions_url = baseurl + '/reactions'
            headers = {}
            headers['Accept'] = 'application/vnd.github.squirrel-girl-preview'
            jdata = []
            try:
                resp = self.instance._requester.requestJson(
                    'GET',
                    reactions_url,
                    headers=headers
                )
                data = resp[2]
                jdata = json.loads(data)
            except Exception as e:
                print(e)
                pass
            self.current_reactions = jdata
        return self.current_reactions

    @RateLimited
    def get_submitter(self):
        """Returns the submitter"""
        return self.instance.user.login

    @RateLimited
    def get_labels(self):
        """Pull the list of labels on this Issue"""
        labels = []
        for label in self.instance.labels:
            labels.append(label.name)
        return labels

    @RateLimited
    def get_template_data(self):
        """Extract templated data from an issue body"""

        #if self.instance.pull_request:

        if self.is_pullrequest():
            issue_class = 'pullrequest'
        else:
            issue_class = 'issue'

        if not self.template_data:
            self.template_data = \
                extract_template_data(
                    self.instance.body,
                    issue_number=self.number,
                    issue_class=issue_class
                )
        return self.template_data

    def resolve_desired_labels(self, desired_label):
        for resolved_label, aliases in self.ALIAS_LABELS.iteritems():
            if desired_label in aliases:
                return resolved_label
        return desired_label

    def process_mutually_exclusive_labels(self, name=None):
        resolved_name = self.resolve_desired_labels(name)
        if resolved_name in self.MUTUALLY_EXCLUSIVE_LABELS:
            for label in self.desired_labels:
                resolved_label = self.resolve_desired_labels(label)
                if resolved_label in self.MUTUALLY_EXCLUSIVE_LABELS:
                    self.desired_labels.remove(label)

    def add_desired_label(self, name=None, mutually_exclusive=[], force=False):
        """Adds a label to the desired labels list"""
        if name and name not in self.desired_labels:
            if force:
                self.desired_labels.append(name)
            elif not mutually_exclusive:
                self.process_mutually_exclusive_labels(name=name)
                self.desired_labels.append(name)
            else:
                mutually_exclusive = \
                    [x.replace(' ', '_') for x in mutually_exclusive]
                me = [x for x in self.desired_labels if x in mutually_exclusive]
                if len(me) == 0:
                    self.desired_labels.append(name)

    def pop_desired_label(self, name=None):
        """Deletes a label to the desired labels list"""
        if name in self.desired_labels:
            self.desired_labels.remove(name)

    def is_labeled_for_interaction(self):
        """Returns True if issue is labeld for interaction"""
        for current_label in self.get_current_labels():
            if current_label in self.MANUAL_INTERACTION_LABELS:
                return True
        return False

    def add_desired_comment(self, boilerplate=None):
        """Adds a boilerplate key to the desired comments list"""
        if boilerplate and boilerplate not in self.desired_comments:
            self.desired_comments.append(boilerplate)

    def get_missing_sections(self):
        missing_sections = \
            [x for x in self.REQUIRED_SECTIONS
                if x not in self.template_data or
                not self.template_data.get(x)]
        return missing_sections

    def get_issue(self):
        """Gets the issue from the GitHub API"""
        return self.instance

    @RateLimited
    def add_label(self, label=None):
        """Adds a label to the Issue using the GitHub API"""
        self.get_issue().add_to_labels(label)

    @RateLimited
    def remove_label(self, label=None):
        """Removes a label from the Issue using the GitHub API"""
        self.get_issue().remove_from_labels(label)

    @RateLimited
    def add_comment(self, comment=None):
        """Adds a comment to the Issue using the GitHub API"""
        self.get_issue().create_comment(comment)

    def set_desired_state(self, state):
        assert state in ['open', 'closed']
        self.desired_state = state

    def set_description(self, description):
        # http://pygithub.readthedocs.io/en/stable/github_objects/Issue.html#github.Issue.Issue.edit
        self.instance.edit(body=description)

    @property
    def assignees(self):
        if self._assignees is False:
            self._assignees = self.get_assignees()
        return self._assignees

    def get_assignees(self):
        # https://developer.github.com/v3/issues/assignees/
        # https://developer.github.com/changes/2016-5-27-multiple-assignees/
        # https://github.com/PyGithub/PyGithub/pull/469
        # the pygithub issue object only offers a single assignee (right now)

        assignees = []
        if not hasattr(self.instance, 'assignees'):
            raw_assignees = self.raw_data_issue['assignees']
            assignees = \
                [x.login for x in self.instance._makeListOfClassesAttribute(
                    github.NamedUser.NamedUser,
                    raw_assignees).value]
        else:
            assignees = [x.login for x in self.instance.assignees]

        res = [x for x in assignees]
        return res

    def add_desired_assignee(self, assignee):
        if assignee not in self.desired_assignees \
                and assignee in self.valid_assignees:
            self.desired_assignees.append(assignee)

    def assign_user(self, user):
        assignees = [x for x in self.assignees]
        if user not in self.assignees:
            assignees.append(user)
            self._edit_assignees(assignees)

    def unassign_user(self, user):
        assignees = [x for x in self.current_assignees]
        if user in self.assignees:
            assignees.remove(user)
            self._edit_assignees(assignees)

    def _edit_assignees(self, assignees):
        # https://github.com/PyGithub/PyGithub/pull/469/files
        # https://raw.githubusercontent.com/tmshn/PyGithub/ba007dc8a8bb5d5fdf75706db84dab6a69929d7d/github/Issue.py
        # http://pygithub.readthedocs.io/en/stable/github_objects/Issue.html#github.Issue.Issue.edit
        #self.instance.edit(body=description)

        vparms = inspect.getargspec(self.instance.edit)
        if 'assignees' in vparms.args:
            print('time to implement the native call for edit on assignees')
            sys.exit(1)
        else:
            post_parameters = dict()
            post_parameters["assignees"] = [x for x in assignees]

            headers, data = self.instance._requester.requestJsonAndCheck(
                "PATCH",
                self.instance.url,
                input=post_parameters
            )
            if headers['status'] != '200 OK':
                print('ERROR: failed to edit assignees')
                sys.exit(1)

    def is_pullrequest(self):
        if self.github_type == 'pullrequest':
            return True
        else:
            return False

    def is_issue(self):
        if self.github_type == 'issue':
            return True
        else:
            return False

    @property
    def title(self):
        return self.instance.title

    @property
    def repo_full_name(self):
        return self.repo.repo.full_name

    @property
    def html_url(self):
        return self.instance.html_url

    @property
    def created_at(self):
        return self.instance.created_at

    @property
    def updated_at(self):
        return self.instance.updated_at

    @property
    def closed_at(self):
        return self.instance.closed_at

    @property
    def merged_at(self):
        # only pullrequest objects have merged_at
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
        return self.instance.user.login

    @property
    def comments(self):
        if self._comments is False:
            self._comments = self.get_comments()
        return self._comments

    @property
    def pullrequest(self):
        if not self._pr:
            logging.debug('@pullrequest.get_pullrequest #%s' % self.number)
            self._pr = self.repo.get_pullrequest(self.number)
            #self.repo.save_pullrequest(self._pr)
        return self._pr

    def update_pullrequest(self):
        # the underlying call is wrapper with ratelimited ...
        self._pr = self.repo.get_pullrequest(self.number)

    @property
    @RateLimited
    def pullrequest_raw_data(self):
        if not self.pull_raw:
            logging.info('@pullrequest_raw_data')
            self.pull_raw = self.pullrequest.raw_data
        return self.pull_raw

    def get_pullrequest_status(self, force_fetch=False):
        fetched = False
        jdata = None
        pdata = None
        # pull out the status url from the raw data
        rd = self.pullrequest_raw_data
        surl = rd['statuses_url']

        pfile = os.path.join(
            self.cachedir,
            'issues',
            str(self.number),
            'pr_status.pickle'
        )

        if os.path.isfile(pfile):
            logging.info('pullrequest_status load pfile')
            with open(pfile, 'rb') as f:
                pdata = pickle.load(f)

        if pdata:
            # is the data stale?
            if pdata[0] < self.pullrequest.updated_at or force_fetch:
                logging.info('fetching pr status: <date')
                jdata = self._fetch_api_url(surl)
                fetched = True
            else:
                jdata = pdata[1]

        # missing?
        if not jdata:
            logging.info('fetching pr status: !data')
            jdata = self._fetch_api_url(surl)
            fetched = True

        if fetched or not os.path.isfile(pfile):
            logging.info('writing %s' % pfile)
            pdata = (self.pullrequest.updated_at, jdata)
            with open(pfile, 'wb') as f:
                pickle.dump(pdata, f, protocol=2)

        return jdata

    @property
    def pullrequest_status(self):
        if self._pr_status is False:
            self._pr_status = self.get_pullrequest_status()
        return self._pr_status

    @property
    def files(self):
        if not self.pr_files:
            self.pr_files = self.load_update_fetch('files')
        files = [x.filename for x in self.pr_files]
        return files

    @property
    def body(self):
        return self.instance.body

    @property
    def labels(self):
        if self._labels is False:
            logging.debug('_labels == False')
            self._labels = [x for x in self.get_labels()]
        return self._labels

    @property
    def reviews(self):
        if self._pr_reviews is False:
            self._pr_reviews = self.get_pullrequest_reviews()
        return self._pr_reviews

    @RateLimited
    def get_pullrequest_reviews(self):
        # https://developer.github.com/
        #   early-access/graphql/enum/pullrequestreviewstate/
        # https://developer.github.com/v3/
        #   pulls/reviews/#list-reviews-on-a-pull-request
        reviews_url = self.pullrequest.url + '/reviews'
        headers = {}
        headers['Accept'] = 'application/vnd.github.black-cat-preview+json'
        resp = self.instance._requester.requestJson(
            'GET',
            reviews_url,
            headers=headers
        )
        jdata = json.loads(resp[2])
        #import epdb; epdb.st()
        return jdata

    def scrape_pr_state(self):
        # https://github.com/ansible/ansible/pulls?
        #   utf8=%E2%9C%93&q=is%3Apr%20is%3Aopen%2019995
        '''
        import requests
        from datetime import datetime
        from bs4 import BeautifulSoup

        username= os.environ.get('GITHUB_USERNAME')
        password = os.environ.get('GITHUB_PASSWORD')
        url = self.html_url
        login_url = 'https://github.com/login'

        headers = {'User-Agent': 'Mozilla/5.0'}
        payload = {
            'login': username,
            'password': password
        }

        session = requests.Session()
        rr = session.post(login_url, headers=headers, data=payload)

        #rr = requests.get(url, auth=(username, password))
        #soup = BeautifulSoup(rr.text, 'html.parser')
        #resp = self.instance._requester.requestJson('GET', url)
        import epdb; epdb.st()
        '''
        pass

    @property
    def history(self):
        if self._history is False:
            self._history = \
                HistoryWrapper(self, cachedir=self.cachedir, usecache=True)
        return self._history

    @RateLimited
    def update(self):
        self.instance.update()
        self._history = \
            HistoryWrapper(self, cachedir=self.cachedir, usecache=True)
        if self.is_pullrequest():
            self.pullrequest.update()

            if self.instance.updated_at > self.pullrequest.updated_at:
                import epdb; epdb.st()

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

    def scrape_reviews(self):
        import epdb; epdb.st()
        return commits
