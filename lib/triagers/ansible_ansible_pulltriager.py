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
import re
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

    # The filemap is a way to match a filepath, a directory
    # or a regex to a specific label or a set of assignees.
    # The 'inclusive' key is an indication that the match
    # should override all other matches.
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
        'contrib/inventory/openstack*': {
            'labels': ['contrib_inventory', 'cloud', 'openstack'],
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
        '.*gce.*': {
            'labels': ['cloud', 'gce'],
        },
        '.*ec2.*': {
            'labels': ['cloud', 'aws'],
        },
        '.*rax.*': {
            'labels': ['cloud', 'rax'],
        },
        '.*openstack.*': {
            'labels': ['cloud', 'openstack'],
        },
        '.*azure.*': {
            'labels': ['cloud', 'azure'],
        },
        '.*vmware.*': {
            'labels': ['module_util', 'cloud', 'vmware'],
            'maintainers': ['jctanner']
        },
        '.*docker.*': {
            'labels': ['cloud', 'docker'],
        },
        'packaging/': {
            'labels': ['packaging'],
        },
        'test/': {
            'labels': ['test_pull_requests'],
            'inclusive': True
        }

    }

    def process(self):

        # create the filemap regexes
        self.build_filemap_regexes()

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

        # check if the PR is related to py3
        self.check_for_python3()

        self.check_for_merge_issues()

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

    def build_filemap_regexes(self):
        '''Create regex matchers for each key in the map'''
        for k,v in self.FILEMAP.iteritems():
            if not 'regex' in self.FILEMAP:
                reg = k
                if reg.endswith('/'):
                    reg += '*'
                self.FILEMAP[k]['regex'] = re.compile(reg)

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

            for fk in fkeys:
                if self.FILEMAP[fk]['regex'].match(fn):
                    self.debug('\t%s matches %s' % (fn, fk))
                    if not fk in matches:
                        matches.append(fk)

        # FIXME - do the inclusive checking here
        matches = sorted(set(matches))

        if matches:
            for match in matches:

                # if not inclusive and multiple matches, skip this 
                #   [prevents assigning features to docs maintainer]
                if not self.FILEMAP[match].get('inclusive', True) and len(matches) > 1:
                    self.debug('%s is not inclusive, skipping' % match)
                    continue

                for label in self.FILEMAP[match].get('labels', []):
                    if label in self.valid_labels:
                        self.debug('add %s from %s' % (label, match))
                        if self.FILEMAP[match].get('inclusive') == True:
                            me = []
                        else:
                            me = self.MUTUALLY_EXCLUSIVE_LABELS
                        self.issue.add_desired_label(label, mutually_exclusive=me)

                for assignee in self.FILEMAP[match].get('maintainers', []):
                    if assignee in self.valid_assignees:
                        self.debug('assign %s from %s' % (assignee, match))
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

            # just adding test_pull_requests label
            if not self.actions['close'] \
                and not self.actions['unlabel'] \
                and not self.actions['assign'] \
                and not self.actions['unassign'] \
                and self.actions['newlabel'] == ['test_pull_requests']:
                safe_match = True

            if safe_match:
                self.force = True
            else:
                self.force = False
            #import epdb; epdb.st()



    def check_for_python3(self):
        ispy3 = False
        py3strings = ['python 3', 'python3', 'py3', 'py 3'] 

        for py3str in py3strings:

            if py3str in self.issue.instance.title.lower():
                ispy3 = True
                break

            if py3str in self.template_data.get('component_raw', ''):
                ispy3 = True
                break

            if py3str in self.template_data.get('component name', ''):
                ispy3 = True
                break

            if py3str in self.template_data.get('summary', ''):
                ispy3 = True
                break

        if ispy3:
            for comment in self.issue.current_comments:
                if '!python3' in comment.body:
                    self.debug('!python3 override in comments')
                    ispy3 = False
                    break

        if ispy3:
            self.debug('python3 reference detected')
            self.issue.add_desired_label('python3')


    def check_for_merge_issues(self):

        # clean == no test failure and no merge conflicts
        # unstable == test failures
        # dirty == merge conflict

        mergeable = self.issue.pullrequest.mergeable
        mergeable_state = self.issue.pullrequest.mergeable_state
        #import epdb; epdb.st()


