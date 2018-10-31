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
import operator
import os
import re
import shutil
import sys
import time
from datetime import datetime

import six

# remember to pip install PyGithub, kids!
import github

from ansibullbot._pickle_compat import pickle_dump, pickle_load
from ansibullbot._text_compat import to_text
from ansibullbot.utils.extractors import extract_template_sections
from ansibullbot.utils.extractors import extract_template_data
from ansibullbot.wrappers.historywrapper import HistoryWrapper

from ansibullbot.decorators.github import RateLimited
from ansibullbot.errors import RateLimitError

import ansibullbot.constants as C


class DefaultWrapper(object):

    ALIAS_LABELS = {
        u'core_review': [
            u'core_review_existing'
        ],
        u'community_review': [
            u'community_review_existing',
            u'community_review_new',
            u'community_review_owner_pr',
        ],
        u'shipit': [
            u'shipit_owner_pr'
        ],
        u'needs_revision': [
            u'needs_revision_not_mergeable'
        ],
        u'pending_action': [
            u'pending_action_close_me',
            u'pending_maintainer_unknown'
        ]
    }

    MANUAL_INTERACTION_LABELS = [
    ]

    MUTUALLY_EXCLUSIVE_LABELS = [
        u"bug_report",
        u"feature_idea",
        u"docs_report"
    ]

    TOPIC_MAP = {u'amazon': u'aws',
                 u'google': u'gce',
                 u'network': u'networking'}

    REQUIRED_SECTIONS = []

    TEMPLATE_HEADER = u'#####'

    def __init__(self, github=None, repo=None, issue=None, cachedir=None, file_indexer=None):
        self.meta = {}
        self.cachedir = cachedir
        self.github = github
        self.repo = repo
        self.instance = issue
        self._assignees = False
        self._comments = False
        self._committer_emails = False
        self._commits = False
        self._events = False
        self._history = False
        self._labels = False
        self._merge_commits = False
        self._migrated = None
        self._migrated_from = None
        self._migrated_issue = None
        self._pr = False
        self._pr_status = False
        self._pr_reviews = False
        self._reactions = False
        self._template_data = None
        self._required_template_sections = []
        self.desired_labels = []
        self.desired_assignees = []
        self.current_events = []
        self.current_comments = []
        self.current_bot_comments = []
        self.last_bot_comment = None
        self.current_reactions = []
        self.desired_comments = []
        self.current_state = u'open'
        self.desired_state = u'open'
        self.pr_status_raw = None
        self.pull_raw = None
        self.pr_files = []
        self.file_indexer = file_indexer

        self.full_cachedir = os.path.join(
            self.cachedir,
            u'issues',
            to_text(self.number)
        )

        self.valid_assignees = []
        #self.raw_data_issue = self.load_update_fetch('raw_data', obj='issue')
        self._raw_data_issue = None

    def get_rate_limit(self):
        return self.repo.gh.get_rate_limit()

    def get_current_time(self):
        return datetime.utcnow()

    def save_issue(self):
        pfile = os.path.join(
            self.cachedir,
            u'issues',
            to_text(self.instance.number),
            u'issue.pickle'
        )
        pdir = os.path.dirname(pfile)

        if not os.path.isdir(pdir):
            os.makedirs(pdir)

        logging.debug(u'dump %s' % pfile)
        with open(pfile, 'wb') as f:
            pickle_dump(self.instance, f)

    @RateLimited
    def get_comments(self):
        """Returns all current comments of the PR"""

        comments = self.load_update_fetch(u'comments')

        self.current_comments = [x for x in comments]
        self.current_comments.reverse()

        # look for any comments made by the bot
        for idx, x in enumerate(self.current_comments):
            body = x.body
            lines = body.split(u'\n')
            lines = [y.strip() for y in lines if y.strip()]

            if lines[-1].startswith(u'<!---') \
                    and lines[-1].endswith(u'--->') \
                    and u'boilerplate:' in lines[-1]\
                    and x.user.login == u'ansibot':

                parts = lines[-1].split()
                boilerplate = parts[2]
                self.current_bot_comments.append(boilerplate)

        return self.current_comments

    @property
    def raw_data_issue(self):
        if self._raw_data_issue is None:
            self._raw_data_issue = \
                self.load_update_fetch(u'raw_data', obj=u'issue')
        return self._raw_data_issue

    @property
    def events(self):
        if self._events is False:
            self._events = self.get_events()
        return self._events

    @RateLimited
    def get_events(self):
        self.current_events = self.load_update_fetch(u'events')
        return self.current_events

    #def get_commits(self):
    #    self.commits = self.load_update_fetch('commits')
    #    return self.commits

    def get_files(self):
        self.files = self.load_update_fetch(u'files')
        return self.files

    def get_review_comments(self):
        self.review_comments = self.load_update_fetch(u'review_comments')
        return self.review_comments

    @RateLimited
    def _fetch_api_url(self, url):
        # fetch the url and parse to json
        '''
        jdata = None
        try:
            resp = self.instance._requester.requestJson(
                'GET',
                url
            )
            data = resp[2]
            jdata = json.loads(data)
        except Exception as e:
            logging.error(e)
        '''

        jdata = None
        while True:
            resp = self.instance._requester.requestJson(
                u'GET',
                url
            )
            data = resp[2]
            jdata = json.loads(data)

            if isinstance(jdata, dict) and jdata.get(u'documentation_url'):
                if C.DEFAULT_BREAKPOINTS:
                    import epdb; epdb.st()
                else:
                    raise RateLimitError("rate limited")
            else:
                break

        return jdata

    def relocate_pickle_files(self):
        '''Move files to the correct location to fix bad pathing'''
        srcdir = os.path.join(
            self.cachedir,
            u'issues',
            to_text(self.instance.number)
        )
        destdir = os.path.join(
            self.cachedir,
            to_text(self.instance.number)
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

    @RateLimited
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
            u'issues',
            to_text(self.instance.number),
            u'%s.pickle' % property_name
        )
        pdir = os.path.dirname(pfile)
        logging.debug(pfile)

        if not os.path.isdir(pdir):
            os.makedirs(pdir)

        if os.path.isfile(pfile):
            try:
                with open(pfile, 'rb') as f:
                    edata = pickle_load(f)
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
            if obj == u'issue':
                baseobj = self.instance
            elif obj == u'pullrequest':
                baseobj = self.pullrequest
        else:
            if hasattr(self.instance, u'get_' + property_name):
                baseobj = self.instance
            else:
                if self.pullrequest:
                    if hasattr(self.pullrequest, u'get_' + property_name):
                        baseobj = self.pullrequest

        if not baseobj:
            logging.error(
                u'%s was not a property for the issue or the pullrequest'
                % property_name
            )
            if C.DEFAULT_BREAKPOINTS:
                logging.error(u'breakpoint!')
                import epdb; epdb.st()
            else:
                raise Exception(u'property error')

        # pull all events if timestamp is behind or no events cached
        if update or not events:
            write_cache = True
            updated = self.get_current_time()

            if not hasattr(baseobj, u'get_' + property_name) \
                    and hasattr(baseobj, property_name):
                # !callable properties
                try:
                    methodToCall = getattr(baseobj, property_name)
                except Exception as e:
                    logging.error(e)
                    if C.DEFAULT_BREAKPOINTS:
                        logging.error(u'breakpoint!')
                        import epdb; epdb.st()
                    else:
                        raise Exception(to_text(e))
                events = methodToCall
            else:
                # callable properties
                try:
                    methodToCall = getattr(baseobj, u'get_' + property_name)
                except Exception as e:
                    logging.error(e)
                    if C.DEFAULT_BREAKPOINTS:
                        logging.error(u'breakpoint!')
                        import epdb; epdb.st()
                    else:
                        raise Exception(to_text(e))
                events = [x for x in methodToCall()]

        if write_cache or not os.path.isfile(pfile):
            # need to dump the pickle back to disk
            edata = [updated, events]
            with open(pfile, 'wb') as f:
                pickle_dump(edata, f)

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
            if C.DEFAULT_BREAKPOINTS:
                logging.error(u'breakpoint!')
                import epdb; epdb.st()
            else:
                raise Exception(u'exception')
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
            reactions_url = baseurl + u'/reactions'
            headers = {
                u'Accept': u'application/vnd.github.squirrel-girl-preview',
            }
            jdata = []
            try:
                resp = self.instance._requester.requestJson(
                    u'GET',
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

    def get_template_data(self):
        """Extract templated data from an issue body"""

        if self.is_issue():
            tfile = u'.github/ISSUE_TEMPLATE.md'
        else:
            tfile = u'.github/PULL_REQUEST_TEMPLATE.md'

        # use the fileindexer whenever possible to conserve ratelimits
        if self.file_indexer:
            tf_content = self.file_indexer.get_file_content(tfile)
        else:
            try:
                tf = self.repo.get_file_contents(tfile)
                tf_content = tf.decoded_content
            except Exception:
                logging.warning(u'repo does not have {}'.format(tfile))
                tf_content = u''

        # pull out the section names from the tempalte
        tf_sections = extract_template_sections(tf_content, header=self.TEMPLATE_HEADER)

        # what is required?
        self._required_template_sections = \
            [x.lower() for x in tf_sections.keys()
             if tf_sections[x][u'required']]

        # extract ...
        template_data = \
            extract_template_data(
                self.instance.body,
                issue_number=self.number,
                issue_class=self.github_type,
                sections=tf_sections.keys()
            )

        # try comments if the description was insufficient
        if len(template_data.keys()) <= 2:
            s_comments = self.history.get_user_comments(self.submitter)
            for s_comment in s_comments:

                _template_data = extract_template_data(
                    s_comment,
                    issue_number=self.number,
                    issue_class=self.github_type,
                    sections=tf_sections.keys()
                )

                if _template_data:
                    for k, v in _template_data.items():
                        if not v:
                            continue
                        if v and (k not in template_data or not template_data.get(k)):
                            template_data[k] = v

        if u'ANSIBLE VERSION' in tf_sections and u'ansible version' not in template_data:

            # FIXME - abstract this into a historywrapper method
            vlabels = [x for x in self.history.history if x[u'event'] == u'labeled']
            vlabels = [x for x in vlabels if x[u'actor'] not in [u'ansibot', u'ansibotdev']]
            vlabels = [x[u'label'] for x in vlabels if x[u'label'].startswith(u'affects_')]
            vlabels = [x for x in vlabels if x.startswith(u'affects_')]

            versions = [x.split(u'_')[1] for x in vlabels]
            versions = [float(x) for x in versions]
            if versions:
                version = versions[-1]
                template_data[u'ansible version'] = to_text(version)

        if u'COMPONENT NAME' in tf_sections and u'component name' not in template_data:
            if self.is_pullrequest():
                fns = self.files
                if fns:
                    template_data[u'component name'] = u'\n'.join(fns)
                    template_data[u'component_raw'] = u'\n'.join(fns)
            else:
                clabels = [x for x in self.labels if x.startswith(u'c:')]
                if clabels:
                    fns = []
                    for clabel in clabels:
                        clabel = clabel.replace(u'c:', u'')
                        fns.append(u'lib/ansible/' + clabel)
                    template_data[u'component name'] = u'\n'.join(fns)
                    template_data[u'component_raw'] = u'\n'.join(fns)

                elif u'documentation' in template_data.get(u'issue type', u'').lower():
                    template_data[u'component name'] = u'docs'
                    template_data[u'component_raw'] = u'docs'

        if u'ISSUE TYPE' in tf_sections and u'issue type' not in template_data:

            # FIXME - turn this into a real classifier based on work done in
            # jctanner/pr-triage repo.

            itype = None

            while not itype:

                for label in self.labels:
                    if label.startswith(u'bug'):
                        itype = u'bug'
                        break
                    elif label.startswith(u'feature'):
                        itype = u'feature'
                        break
                    elif label.startswith(u'doc'):
                        itype = u'docs'
                        break
                if itype:
                    break

                if self.is_pullrequest():
                    fns = self.files
                    for fn in fns:
                        if fn.startswith(u'doc'):
                            itype = u'docs'
                            break
                if itype:
                    break

                msgs = [self.title, self.body]
                if self.is_pullrequest():
                    msgs += [x[u'message'] for x in self.history.history if x[u'event'] == u'committed']

                msgs = [x for x in msgs if x]
                msgs = [x.lower() for x in msgs]

                for msg in msgs:
                    if u'fix' in msg:
                        itype = u'bug'
                        break
                    if u'addresses' in msg:
                        itype = u'bug'
                        break
                    if u'broke' in msg:
                        itype = u'bug'
                        break
                    if u'add' in msg:
                        itype = u'feature'
                        break
                    if u'should' in msg:
                        itype = u'feature'
                        break
                    if u'please' in msg:
                        itype = u'feature'
                        break
                    if u'feature' in msg:
                        itype = u'feature'
                        break

                # quit now
                break

            if itype and itype == u'bug' and self.is_issue():
                template_data[u'issue type'] = u'bug report'
            elif itype and itype == u'bug' and not self.is_issue():
                template_data[u'issue type'] = u'bugfix pullrequest'
            elif itype and itype == u'feature' and self.is_issue():
                template_data[u'issue type'] = u'feature idea'
            elif itype and itype == u'feature' and not self.is_issue():
                template_data[u'issue type'] = u'feature pullrequest'
            elif itype and itype == u'docs' and self.is_issue():
                template_data[u'issue type'] = u'documentation report'
            elif itype and itype == u'docs' and not self.is_issue():
                template_data[u'issue type'] = u'documenation pullrequest'

        return template_data

    @property
    def template_data(self):
        if self._template_data is None:
            self._template_data = self.get_template_data()
        return self._template_data

    @property
    def missing_template_sections(self):
        td = self.template_data
        expected_keys = [x.lower() for x in self._required_template_sections]
        missing = [x for x in expected_keys
                   if x not in td or not td[x]]
        return missing

    def resolve_desired_labels(self, desired_label):
        for resolved_label, aliases in six.iteritems(self.ALIAS_LABELS):
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
                    [x.replace(u' ', u'_') for x in mutually_exclusive]
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
        assert state in [u'open', u'closed']
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
        if not hasattr(self.instance, u'assignees'):
            raw_assignees = self.raw_data_issue[u'assignees']
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

    @RateLimited
    def _edit_assignees(self, assignees):
        # https://github.com/PyGithub/PyGithub/pull/469/files
        # https://raw.githubusercontent.com/tmshn/PyGithub/ba007dc8a8bb5d5fdf75706db84dab6a69929d7d/github/Issue.py
        # http://pygithub.readthedocs.io/en/stable/github_objects/Issue.html#github.Issue.Issue.edit
        #self.instance.edit(body=description)

        vparms = inspect.getargspec(self.instance.edit)
        if u'assignees' in vparms.args:
            new_assignees = self.assignees + assignees
            new_assignees = sorted(set(new_assignees))
            self.instance.edit(assignees=assignees)
        else:
            post_parameters = {}
            post_parameters["assignees"] = [x for x in assignees]

            headers, data = self.instance._requester.requestJsonAndCheck(
                u"PATCH",
                self.instance.url,
                input=post_parameters
            )
            if headers[u'status'] != u'200 OK':
                print(u'ERROR: failed to edit assignees')
                sys.exit(1)

    @RateLimited
    def _delete_comment_by_url(self, url):
        # https://developer.github.com/v3/issues/comments/#delete-a-comment
        headers, data = self.instance._requester.requestJsonAndCheck(
            u"DELETE",
            url,
        )
        if headers[u'status'] != u'204 No Content':
            print(u'ERROR: failed to remove %s' % url)
            sys.exit(1)
        return True

    def is_pullrequest(self):
        if self.github_type == u'pullrequest':
            return True
        else:
            return False

    def is_issue(self):
        if self.github_type == u'issue':
            return True
        else:
            return False

    @property
    def age(self):
        created = self.created_at
        now = datetime.now()
        age = now - created
        return age

    @property
    def title(self):
        return self.instance.title

    @property
    @RateLimited
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
        if u'/pull/' in self.html_url:
            return u'pullrequest'
        else:
            return u'issue'

    @property
    def number(self):
        return self.instance.number

    @property
    def submitter(self):
        # auto-migrated issue by ansibot{-dev}
        # figure out the original submitter
        if self.instance.user.login.startswith(u'ansibot'):
            m = re.match(u'From @(.*) on', self.instance.body)
            if m:
                return m.group(1)

        return self.instance.user.login

    @property
    def comments(self):
        if self._comments is False:
            self._comments = self.get_comments()
        return self._comments

    @property
    def pullrequest(self):
        if not self._pr:
            logging.debug(u'@pullrequest.get_pullrequest #%s' % self.number)
            self._pr = self.repo.get_pullrequest(self.number)
            #self.repo.save_pullrequest(self._pr)
        return self._pr

    def update_pullrequest(self):
        if self.is_pullrequest():
            # the underlying call is wrapper with ratelimited ...
            self._pr = self.repo.get_pullrequest(self.number)
            self.get_pullrequest_status(force_fetch=True)
            self._pr_reviews = False
            self._merge_commits = False
            self._committer_emails = False

    @property
    @RateLimited
    def pullrequest_raw_data(self):
        if not self.pull_raw:
            logging.info(u'@pullrequest_raw_data')
            self.pull_raw = self.pullrequest.raw_data
        return self.pull_raw

    def get_pullrequest_status(self, force_fetch=False):

        def sort_unique_statuses(statuses):
            '''reduce redundant statuses to the final run for each id'''
            result = []
            groups = []
            thisgroup = []
            for idx, x in enumerate(statuses):
                if not thisgroup:
                    thisgroup.append(x)
                    if idx == len(statuses) - 1:
                        groups.append(thisgroup)
                    continue
                else:
                    if thisgroup[-1][u'target_url'] == x[u'target_url']:
                        thisgroup.append(x)
                    else:
                        groups.append(thisgroup)
                        thisgroup = []
                        thisgroup.append(x)

                    if idx == len(statuses) - 1:
                        groups.append(thisgroup)

            for group in groups:
                group.sort(key=operator.itemgetter(u'updated_at'))
                result.append(group[-1])

            return result

        fetched = False
        jdata = None
        pdata = None
        # pull out the status url from the raw data
        rd = self.pullrequest_raw_data
        surl = rd[u'statuses_url']

        pfile = os.path.join(
            self.cachedir,
            u'issues',
            to_text(self.number),
            u'pr_status.pickle'
        )
        pdir = os.path.dirname(pfile)
        if not os.path.isdir(pdir):
            os.makedirs(pdir)

        if os.path.isfile(pfile):
            logging.info(u'pullrequest_status load pfile')
            with open(pfile, 'rb') as f:
                pdata = pickle_load(f)

        if pdata:
            # is the data stale?
            if pdata[0] < self.pullrequest.updated_at or force_fetch:
                logging.info(u'fetching pr status: stale, previous from %s' % pdata[0])
                jdata = self._fetch_api_url(surl)
                self.log_ci_status(jdata)
                fetched = True
            else:
                jdata = pdata[1]

        # missing?
        if not jdata:
            logging.info(u'fetching pr status: !data')
            jdata = self._fetch_api_url(surl)
            fetched = True

        if fetched or not os.path.isfile(pfile):
            logging.info(u'writing %s' % pfile)
            pdata = (self.pullrequest.updated_at, jdata)
            with open(pfile, 'wb') as f:
                pickle_dump(pdata, f)

        # remove intermediate duplicates
        #jdata = sort_unique_statuses(jdata)

        return jdata

    def log_ci_status(self, status_data):
        '''Keep track of historical CI statuses'''

        logfile = os.path.join(
            self.cachedir,
            u'issues',
            to_text(self.number),
            u'pr_status_log.json'
        )

        jdata = {}
        if os.path.isfile(logfile):
            with open(logfile, 'r') as f:
                jdata = json.loads(f.read())

        # the "url" field is constant
        # the "target_url" field varies between CI providers

        for sd in status_data:
            try:
                turl = sd[u'target_url']
            except TypeError:
                # https://github.com/ansible/ansibullbot/issues/959
                # the above traceback sometimes occurs and cannot be reproduced
                # log the following info to have better idea how to handle this
                logging.error(u'sd = %s, type = %s' % (sd, type(sd)))
                logging.error(u'status_data = %s, type = %s' % (status_data, type(status_data)))
                raise

            if turl not in jdata:
                jdata[turl] = {
                    u'meta': sd.copy(),
                    u'history': {}
                }
            else:
                if jdata[turl][u'meta'][u'updated_at'] < sd[u'updated_at']:
                    jdata[turl][u'meta'] = sd.copy()
            ts = sd[u'updated_at']
            if ts not in jdata[turl][u'history']:
                jdata[turl][u'history'][ts] = sd[u'state']

        with open(logfile, 'w') as f:
            f.write(json.dumps(jdata))

    @property
    def pullrequest_status(self):
        if self._pr_status is False:
            self._pr_status = self.get_pullrequest_status(force_fetch=False)
        return self._pr_status

    @property
    def files(self):
        if self.is_issue():
            return None
        if not self.pr_files:
            self.pr_files = self.load_update_fetch(u'files')
        files = [x.filename for x in self.pr_files]
        return files

    @property
    def new_files(self):
        new_files = [x for x in self.files if x not in self.file_indexer.files]
        return new_files

    @property
    def new_modules(self):
        new_modules = self.new_files
        new_modules = [
            x for x in new_modules if x.startswith(u'lib/ansible/modules')
        ]
        new_modules = [
            x for x in new_modules if not os.path.basename(x) == u'__init__.py'
        ]
        new_modules = [
            x for x in new_modules if not os.path.basename(x).startswith(u'_')
        ]
        new_modules = [
            x for x in new_modules if not os.path.basename(x).endswith(u'.ps1')
        ]
        return new_modules

    @property
    def body(self):
        return self.instance.body

    @property
    def labels(self):
        if self._labels is False:
            logging.debug(u'_labels == False')
            self._labels = [x for x in self.get_labels()]
        return self._labels

    @property
    def reviews(self):
        if self._pr_reviews is False:
            self._pr_reviews = self.get_reviews()

        # https://github.com/ansible/ansibullbot/issues/881
        # https://github.com/ansible/ansibullbot/issues/883
        for idx, x in enumerate(self._pr_reviews):
            if u'commit_id' not in x:
                self._pr_reviews[idx][u'commit_id'] = None

        return self._pr_reviews

    @RateLimited
    def get_reviews(self):
        # https://developer.github.com/
        #   early-access/graphql/enum/pullrequestreviewstate/
        # https://developer.github.com/v3/
        #   pulls/reviews/#list-reviews-on-a-pull-request
        reviews_url = self.pullrequest.url + u'/reviews'
        headers = {
            u'Accept': u'application/vnd.github.black-cat-preview+json',
        }

        status, hdrs, body = self.instance._requester.requestJson(
            u'GET',
            reviews_url,
            headers=headers
        )
        jdata = json.loads(body)

        # need to catch rate limit message here
        if isinstance(jdata, dict) and u'rate' in jdata[u'message']:
            raise RateLimitError("rate limited")

        if isinstance(jdata, dict):
            logging.error(
                u'get_reviews | pr_reviews.keys=%s | pr_reviews.len=%s | '
                u'resp.headers=%s | resp.status=%s',
                jdata.keys(), len(jdata),
                hdrs, status,
            )

        return jdata

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
                if C.DEFAULT_BREAKPOINTS:
                    logging.error(u'breakpoint!')
                    import epdb; epdb.st()
                else:
                    raise Exception(u'issue date != pr date')

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
    def mergeable_state(self):
        if not self.is_pullrequest() or self.pullrequest.state == u'closed':
            return None

        # http://stackoverflow.com/a/30620973
        fetchcount = 0
        while self.pullrequest.mergeable_state == u'unknown':
            fetchcount += 1
            if fetchcount >= 10:
                logging.error(u'exceeded fetch threshold for mstate')
                #sys.exit(1)
                return False

            logging.warning(
                u're-fetch[%s] PR#%s because mergeable state is unknown' % (
                    fetchcount,
                    self.number
                 )
            )

            self.update_pullrequest()
            time.sleep(1)

        return self.pullrequest.mergeable_state

    @property
    def wip(self):
        '''Is this a WIP?'''
        if self.title.startswith(u'WIP'):
            return True
        elif u'[WIP]' in self.title:
            return True
        return False

    @property
    def from_fork(self):
        if self.pullrequest.head.repo is None:
            return True

        return self.pullrequest.head.repo.full_name != u'ansible/ansible'

    @RateLimited
    def get_commit_parents(self, commit):
        # https://github.com/ansible/ansibullbot/issues/391
        parents = commit.commit.parents
        return parents

    @RateLimited
    def get_commit_message(self, commit):
        # https://github.com/ansible/ansibullbot/issues/391
        msg = commit.commit.message
        return msg

    @RateLimited
    def get_commit_files(self, commit):
        files = commit.files
        return files

    @property
    def merge_commits(self):
        # https://api.github.com/repos/ansible/ansible/pulls/91/commits
        if self._merge_commits is False:
            self._merge_commits = []
            for commit in self.commits:
                parents = self.get_commit_parents(commit)
                message = self.get_commit_message(commit)
                if len(parents) > 1 or message.startswith(u'Merge branch'):
                    self._merge_commits.append(commit)
        return self._merge_commits

    @property
    def committer_emails(self):
        if self._committer_emails is False:
            self._committer_emails = []
            for commit in self.commits:
                self.committer_emails.append(commit.commit.author.email)
        return self._committer_emails

    def merge(self):

        # https://developer.github.com/v3/repos/merging/
        # def merge(self, commit_message=github.GithubObject.NotSet)

        # squash if 1 committer or just a few commits?
        # rebase if >1 committer
        # error otherwise

        # no merge commits allowed!
        if self.merge_commits:
            return None

        # unique the list of emails so that we can tell how many people
        # have worked on this particular pullrequest
        emails = sorted(set(self.committer_emails))

        if len(self.commits) == 1 or len(emails) == 1:
            # squash single committer PRs
            merge_method = u'squash'
        elif (len(self.commits) == len(emails)) and len(self.commits) <= 10:
            # rebase multi-committer PRs
            merge_method = u'rebase'
        else:
            logging.error(u'merge skipped for %s' % self.number)
            return

        url = os.path.join(self.pullrequest.url, u'merge')
        headers = {
            u'Accept': u'application/vnd.github.polaris-preview+json',
        }
        params = {
            'merge_method': merge_method,
        }
        resp = self.pullrequest._requester.requestJson(
            u"PUT",
            url,
            headers=headers,
            input=params
        )

        if resp[0] != 200 or u'successfully merged' not in resp[2]:
            logging.error(u'merge failed on %s' % self.number)
            logging.error(resp)
            if C.DEFAULT_BREAKPOINTS:
                logging.error(u'breakpoint!')
                import epdb; epdb.st()
            else:
                raise Exception(u'merge failed - %d - %s' % (resp[0], resp[1][u'status']))
        else:
            logging.info(u'merge successful for %s' % self.number)

    @property
    def migrated_from(self):
        self.migrated
        return self._migrated_from

    @property
    def migrated(self):
        if self._migrated is None:
            if self.body and u'Copied from original issue' in self.body:
                self._migrated = True
                migrated_issue = None
                idx = self.body.find(u'Copied from original issue')
                msg = self.body[idx:]
                try:
                    migrated_issue = msg.split()[4]
                except Exception as e:
                    logging.error(e)
                    if C.DEFAULT_BREAKPOINTS:
                        logging.error(u'breakpoint!')
                        import epdb; epdb.st()
                    else:
                        raise Exception(u'split failed')
                if migrated_issue.endswith(u'_'):
                    migrated_issue = migrated_issue.rstrip(u'_')
                self._migrated_from = migrated_issue
            else:
                for comment in self.comments:
                    if comment.body.lower().startswith(u'migrated from'):
                        self._migrated = True
                        bparts = comment.body.split()
                        self._migrated_from = bparts[2]
                        break
        return self._migrated

    def pullrequest_filepath_exists(self, filepath):
        ''' Check if a file exists on the submitters branch '''

        # https://github.com/ansible/ansibullbot/issues/406

        # https://developer.github.com/v3/repos/contents/
        #   GET /repos/:owner/:repo/readme
        # "contents_url":
        # "https://api.github.com/repos/ganeshrn/ansible/contents/{+path}",

        # self.pullrequest.head
        #   - ref --> branch name
        #   - repo.full_name

        sha = self.pullrequest.head.sha
        pdata = None
        resp = None
        cachefile = os.path.join(
            self.cachedir,
            u'issues',
            to_text(self.number),
            u'shippable_yml.pickle'
        )

        try:
            if os.path.isfile(cachefile):
                with open(cachefile, 'rb') as f:
                    pdata = pickle_load(f)
        except Exception as e:
            logging.error(u'failed to unpickle %s %s' % (cachefile, to_text(e)))

        if not pdata or pdata[0] != sha:

            if self.pullrequest.head.repo:

                url = u'https://api.github.com/repos/'
                url += self.pullrequest.head.repo.full_name
                url += u'/contents/'
                url += filepath

                resp = self.pullrequest._requester.requestJson(
                    u"GET",
                    url,
                    input={u'ref': self.pullrequest.head.ref}
                )

            else:
                # https://github.com/ansible/ansible/pull/19891
                # Sometimes the repo repo/branch has disappeared
                resp = [None]

            pdata = [sha, resp]
            with open(cachefile, 'wb') as f:
                pickle_dump(pdata, f)

        else:
            resp = pdata[1]

        result = False
        if resp[0]:
            result = True
        return result
