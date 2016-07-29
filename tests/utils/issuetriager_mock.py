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
import sys
import time
from datetime import datetime

from lib.triagers.issuetriager import TriageIssues
from tests.utils.repo_mock import RepoMock

class ModuleIndexerMock(object):
    match = {'name': 'THISISNOTREAL', 'repository': 'NOREPO', 'topic': '', 'subtopic': ''}
    def find_match(self, name):
        return self.match
    def is_valid(self, name):
        if self.match['name'] == name:
            return True
        else:
            return False
    def get_repository_for_module(self, name):
        return self.match['repository']        

class TriageIssuesMock(TriageIssues):

    def __init__(self, verbose=None, github_user=None, github_pass=None,
                 github_token=None, github_repo=None, number=None,
                 start_at=None, always_pause=False, force=False, dry_run=False):

        self.verbose = verbose
        self.github_user = github_user
        self.github_pass = github_pass
        self.github_token = github_token
        self.github_repo = github_repo
        self.number = number
        self.start_at = start_at
        self.always_pause = always_pause
        self.force = force
        self.dry_run = dry_run

        self.repo = RepoMock()
        self.module_indexer = ModuleIndexerMock()
        self.ansible_members = None
        self.valid_labels = ['needs_info', 'bug_report', 'feature_request', 'docs_report',
                             'cloud', 'waiting_on_maintainer', 'waiting_on_contributor']
        self.meta = {}

        self._module = None           #set by test
        self.module = None            #do not set
        self.match = {}               #do not set?
        self._module_maintainers = [] #set by test
        self.module_maintainers = []  #do not set
        self._ansible_members = []    #set by test
        self.ansible_members = []     #do not test

    def get_ansible_members(self):
        return self._ansible_members

    def get_module_maintainers(self, expand=True):
        return self._module_maintainers

