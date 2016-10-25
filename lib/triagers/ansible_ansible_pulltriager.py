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

import os
import pickle
import sys
import time
from datetime import datetime
from operator import itemgetter
from pprint import pprint
from github import Github

from pulltriager import TriagePullRequests


class AnsibleAnsibleTriagePullRequests(TriagePullRequests):

    VALID_COMMANDS = ['needs_info', 
                      '!needs_info', 
                      'notabug', 
                      'bot_broken', 
                      'bot_skip',
                      'wontfix', 
                      'bug_resolved', 
                      'resolved_by_pr', 
                      'needs_contributor', 
                      'duplicate_of']

    FILEMAP = {
        'contrib/inventory/': {
            'labels': ['contrib_inventory'],
        },
        'contrib/inventory/ec2*': {
            'labels': ['contrib_inventory', 'cloud', 'aws'],
        },
        'contrib/inventory/gce*': {
            'labels': ['contrib_inventory', 'cloud', 'gce'],
        },
        'contrib/inventory/vmware_*': {
            'labels': ['contrib_inventory', 'cloud', 'vmware'],
            'maintainers': ['jctanner']
        },
        'docsite/': {
            'labels': ['docs_pull_request'],
            'maintainers': ['dharmabumstead'],
            'inclusive': False,
        },
        'lib/': {
        },
        'lib/ansible/executor/': {
            'labels': ['executor'],
        },
        'lib/ansible/parsing/vault/': {
            'labels': ['vault'],
        },
        'lib/ansible/plugins/action/': {
            'labels': ['action_plugin'],
        },
        'lib/ansible/plugins/connection/': {
            'labels': ['connection_plugin'],
        },
        'lib/ansible/plugins/module_utils/': {
            'labels': ['module_util'],
        },
        'lib/ansible/plugins/module_utils/vmware*': {
            'labels': ['module_util', 'cloud', 'vmware'],
            'maintainers': ['jctanner']
        },
        'packaging/': {
            'labels': ['packaging'],
        },
        'test/': {
            'labels': ['test_pull_requests'],
        }

    }

    def process(self):
        # basic processing [builds self.meta]
        self._process()

        # keep current assignees
        self.keep_current_assignees()

        # keep existing labels
        self.keep_current_main_labels()
        self.debug('1. labels: %s' % self.issue.desired_labels)

        # determine new labels to add by itype
        self.add_desired_labels_by_issue_type(comments=False)
        self.debug('2. labels: %s' % self.issue.desired_labels)

        # determine new labels to add by patch filenames
        self.add_desired_labels_and_assignees_by_filenames()
        self.debug('3. labels: %s' % self.issue.desired_labels)

        # build the actions
        self.create_actions()

        self.debug('cur.labels: %s' % ' '.join(self.issue.current_labels))
        self.debug('submitter: %s' % self.issue.get_submitter())
        self.debug('assignee: %s' % self.issue.current_assignees)

        print("Total Comments: %s" % len(self.issue.current_comments))
        self.print_comment_list()

        # run the actions
        if self.verbose:
            pprint(self.actions)
        self.apply_actions()

    def keep_current_assignees(self):
        for assignee in self.issue.get_assignees():
            self.issue.add_desired_assignee(assignee)

    def keep_current_main_labels(self):
        current_labels = self.issue.get_current_labels()
        for current_label in current_labels:
            self.issue.add_desired_label(name=current_label, force=True)

    def add_desired_labels_and_assignees_by_filenames(self):
        fkeys = self.FILEMAP.keys()

        self.debug('match patch files to labels+maintainers')

        matches = []
        for pfile in self.issue.files:
            fn = pfile.filename

            match = None
            if fn in fkeys:
                # explicit match
                match = fn
            else:
                # best match: FIXME - use proper regex
                match = None
                for fk in fkeys:
                    fk_ = fk.replace('*', '')
                    if fn.startswith(fk_):
                        if not match:
                            match = fk
                            continue
                        elif len(fk) > len(match):
                            match = fk
                            continue

            self.debug('\t%s matches %s' % (fn, match))

            if match:
                matches.append(match)

        matches = sorted(set(matches))
        if matches:
            for match in matches:

                # if not inclusive and multiple matches, skip this 
                #   [prevents assigning features to docs maintainer]
                if not self.FILEMAP[match].get('inclusive', True) and len(matches) > 1:
                    continue

                for label in self.FILEMAP[match].get('labels', []):
                    if label in self.valid_labels:
                        self.issue.add_desired_label(label, mutually_exclusive=self.MUTUALLY_EXCLUSIVE_LABELS)
                for assignee in self.FILEMAP[match].get('maintainers', []):
                    if assignee in self.valid_assignees:
                        self.issue.add_desired_assignee(assignee)


    def create_actions(self):
        self.actions['assign'] = []
        self.actions['unassign'] = []
        self.actions['comments'] = []
        self.actions['newlabel'] = []
        self.actions['unlabel'] = []
        self.actions['close'] = False

        # assignment
        for user in self.issue.current_assignees:
            if user not in self.issue.desired_assignees:
                self.actions['unassign'].append(user)
        for user in self.issue.desired_assignees:
            if user not in self.issue.current_assignees:
                self.actions['assign'].append(user)

        # labels
        for label in self.issue.current_labels:
            if label not in self.issue.desired_labels:
                self.actions['unlabel'].append(label)            
        for label in self.issue.desired_labels:
            if label not in self.issue.current_labels:
                self.actions['newlabel'].append(label)

        # comments
        for com in self.issue.desired_comments:
            print('comments not yet implemented in this triager')
            sys.exit(1)

    def check_safe_match(self):
        """ Turn force on or off depending on match characteristics """

        if self.action_count() == 0:
            self.force = True
        else:
            safe_match = False

            if not self.actions['close'] and \
                (not self.actions['unlabel'] or self.actions['unlabel'] == ['needs_info'])\
                and not self.actions['unassign'] and not self.actions['assign']:
                safe_match = True

            if safe_match:
                self.force = True
            else:
                self.force = False
            #import epdb; epdb.st()



