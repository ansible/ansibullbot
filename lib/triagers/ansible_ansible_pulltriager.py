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

# remember to pip install PyGithub, kids!
from github import Github

#from jinja2 import Environment, FileSystemLoader

#from lib.wrappers.issuewrapper import IssueWrapper
#from lib.wrappers.historywrapper import HistoryWrapper
from pulltriager import TriagePullRequests

#loader = FileSystemLoader(os.path.join(os.path.dirname(__file__), 'templates'))
#environment = Environment(loader=loader, trim_blocks=True)


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
            'maintainers': ['dharmabumstead']
        },
        'lib/ansible/plugins/module_utils/': {
            'labels': ['module_util'],
        },
        'lib/ansible/plugins/module_utils/vmware*': {
            'labels': ['module_util', 'cloud', 'vmware'],
            'maintainers': ['jctanner']
        },
        'lib/ansible/plugins/action/': {
            'labels': ['action_plugin'],
        },
        'packaging/': {
            'labels': ['packaging'],
            'maintainers': ['dharmabumstead']
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

        # determine new labels to add by itype
        self.add_desired_labels_by_issue_type(comments=False)

        # determine new labels to add by patch filenames
        self.add_desired_labels_and_assignees_by_filenames()

        import epdb; epdb.st()

    def keep_current_assignees(self):
        for assignee in self.issue.get_assignees():
            self.issue.add_desired_assignee(assignee)

    def keep_current_main_labels(self):
        current_labels = self.issue.get_current_labels()
        for current_label in current_labels:
            self.issue.add_desired_label(name=current_label)

    def add_desired_labels_and_assignees_by_filenames(self):
        fkeys = self.FILEMAP.keys()

        for pfile in self.issue.files:
            print(pfile.filename)
            fn = pfile.filename

            match = None
            if fn in fkeys:
                # explicit match
                match = fn
            else:
                # best match
                match = None
                for fk in fkeys:
                    fk_ = fk.replace('*', '')
                    if fn.startswith(fk_):
                        if not match:
                            match = fk
                            continue
                        elif len(fk) > match:
                            match = fk
                            continue

            print('%s match %s' % (fn, match))
            if match:
                for label in self.FILEMAP[match].get('labels', []):
                    if label in self.valid_labels:
                        self.add_desired_label(label)
                for assignee in self.FILEMAP[match].get('maintainers', []):
                    if assignee in self.ansible_members:
                        self.add_desired_assignee(assignee)


        import epdb; epdb.st()        




