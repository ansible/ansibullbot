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
import os
import pickle
import shutil
import sys
import time
from datetime import datetime

# remember to pip install PyGithub, kids!
import github
from github import Github

from jinja2 import Environment, FileSystemLoader

from lib.utils.moduletools import ModuleIndexer
from lib.utils.extractors import extract_template_data


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
        self.number = self.instance.number
        self.current_labels = self.get_current_labels()
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

        self.valid_assignees = []
        self.pullrequest = None

        self.raw_data_issue = self.load_update_fetch('raw_data', obj='issue')


    def get_current_time(self):
        return datetime.utcnow()

    def get_comments(self):
        """Returns all current comments of the PR"""

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

    def get_events(self):
        self.current_events = self.load_update_fetch('events')
        return self.current_events

    def get_commits(self):
        self.commits = self.load_update_fetch('commits')
        return self.commits

    def get_files(self):
        self.files = self.load_update_fetch('files')
        return self.files

    def get_review_comments(self):
        self.review_comments = self.load_update_fetch('review_comments')
        return self.review_comments

    def relocate_pickle_files(self):
        '''Move files to the correct location to fix bad pathing'''
        srcdir = os.path.join(self.cachedir, 'issues', str(self.instance.number))
        destdir = os.path.join(self.cachedir, str(self.instance.number))

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

    # self.raw_data_issue = self.load_update_fetch('raw_data', obj='issue')
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

        # fix bad pathing
        self.relocate_pickle_files()

        pfile = os.path.join(self.cachedir, str(self.instance.number), '%s.pickle' % property_name)
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
            print('%s was not a property for the issue or the pullrequest' % property_name)
            import epdb; epdb.st()
            sys.exit(1)

        # pull all events if timestamp is behind or no events cached
        if update or not events:        
            write_cache = True
            updated = self.get_current_time()

            if not hasattr(baseobj, 'get_' + property_name) and hasattr(baseobj, property_name):
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
        if self.instance.assignee == None:
            pass
        elif type(self.instance.assignee) != list:
            assignee = self.instance.assignee.login
        else:
            assignee = []
            for x in self.instance.assignee:
                assignee.append(x.login)
            import epdb; epdb.st()
        return assignee

    def get_reactions(self):
        # https://developer.github.com/v3/reactions/
        if not self.current_reactions:
            baseurl = self.instance.url
            reactions_url = baseurl + '/reactions'
            headers = {}
            headers['Accept'] = 'application/vnd.github.squirrel-girl-preview'
            jdata = []
            try:
                resp = self.instance._requester.requestJson('GET', 
                                        reactions_url, headers=headers)
                data = resp[2]
                jdata = json.loads(data)
            except Exception as e:
                pass
            self.current_reactions = jdata
        return self.current_reactions

    def get_submitter(self):
        """Returns the submitter"""
        return self.instance.user.login

    def get_current_labels(self):
        """Pull the list of labels on this Issue"""
        labels = []
        for label in self.instance.labels:
            labels.append(label.name)
        return labels

    def get_template_data(self):
        """Extract templated data from an issue body"""

        if self.instance.pull_request:
            issue_class = 'pullrequest'
        else:
            issue_class = 'issue'

        if not self.template_data:
            self.template_data = \
                extract_template_data(self.instance.body, issue_number=self.number, issue_class=issue_class)
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
                mutually_exclusive = [x.replace(' ', '_') for x in mutually_exclusive]
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
        missing_sections = [x for x in self.REQUIRED_SECTIONS \
                            if not x in self.template_data \
                            or not self.template_data.get(x)]
        return missing_sections

    def get_issue(self):
        """Gets the issue from the GitHub API"""
        return self.instance

    def add_label(self, label=None):
        """Adds a label to the Issue using the GitHub API"""
        self.get_issue().add_to_labels(label)

    def remove_label(self, label=None):
        """Removes a label from the Issue using the GitHub API"""
        self.get_issue().remove_from_labels(label)

    def add_comment(self, comment=None):
        """Adds a comment to the Issue using the GitHub API"""
        self.get_issue().create_comment(comment)

    def set_desired_state(self, state):
        assert state in ['open', 'closed']
        self.desired_state = state

    def set_description(self, description):
        # http://pygithub.readthedocs.io/en/stable/github_objects/Issue.html#github.Issue.Issue.edit
        self.instance.edit(body=description)

    def get_assignees(self):
        # https://developer.github.com/v3/issues/assignees/
        # https://developer.github.com/changes/2016-5-27-multiple-assignees/
        # https://github.com/PyGithub/PyGithub/pull/469
        # the pygithub issue object only offers a single assignee (right now)

        assignees = []
        if not hasattr(self.instance, 'assignees'):
            raw_assignees = self.raw_data_issue['assignees']
            assignees = [x.login for x in self.instance._makeListOfClassesAttribute(github.NamedUser.NamedUser, raw_assignees).value]
        else:
            assignees = [x.login for x in self.instance.assignees]

        self.current_assignees = [x for x in assignees]
        return self.current_assignees

    def add_desired_assignee(self, assignee):
        if assignee not in self.desired_assignees and assignee in self.valid_assignees:
            self.desired_assignees.append(assignee)

    def assign_user(self, user):
        assignees = [x for x in self.current_assignees]
        if user not in self.current_assignees:
            assignees.append(user)
            self._edit_assignees(assignees)

    def unassign_user(self, user):
        assignees = [x for x in self.current_assignees]
        if user in self.current_assignees:
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
            #import epdb; epdb.st()


