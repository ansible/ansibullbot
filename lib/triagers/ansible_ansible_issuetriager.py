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

from jinja2 import Environment, FileSystemLoader

from lib.wrappers.issuewrapper import IssueWrapper
from lib.wrappers.historywrapper import HistoryWrapper
from lib.utils.moduletools import ModuleIndexer
from lib.utils.extractors import extract_template_data
from lib.utils.descriptionfixer import DescriptionFixer

from issuetriager import TriageIssues

loader = FileSystemLoader(os.path.join(os.path.dirname(__file__), 'templates'))
environment = Environment(loader=loader, trim_blocks=True)


class AnsibleAnsibleTriageIssues(TriageIssues):

    # triage label should be added by bot, removed by human ... later by commands?

    VALID_COMMANDS = ['needs_info', '!needs_info', 'notabug', 
                      'wontfix', 'bug_resolved', 'resolved_by_pr', 
                      'needs_contributor', 'duplicate_of']

    IGNORE_LABELS_ADD = ['cloud', 'networking', 'vmware']


    def process(self, usecache=True):
        '''Does the real work on the issue'''

        # baseline processing
        self._process()

        # unique processing workflow for this repo ...
        self.process_history(usecache=usecache) # use events to add desired labels or comments
        self.add_desired_labels_by_issue_type() # only adds desired labels
        self.create_label_actions() # creates the label actions

        # do the actions ...
        self.debug('current labels: %s' % ' '.join(self.issue.current_labels))
        import pprint; pprint.pprint(self.actions)
        import epdb; epdb.st()
        action_meta = self.apply_actions()
        return action_meta


    def process_history(self, usecache=True):
        today = self.get_current_time()

        # Build the history
        self.debug(msg="Building event history ...")
        self.history = HistoryWrapper(self.issue, usecache=usecache)
        self.meta.update(self.get_history_facts())

        #################################################
        # FINAL LOGIC LOOP TO SET STATE
        #################################################

        if self.meta['bot_broken']:

            self.debug(msg='broken bot stanza')

            self.issue.add_desired_label('bot_broken')

        elif self.github_repo != self.match.get('repository', 'ansible'):

            self.debug(msg='wrong repo stanza')

            self.issue.desired_comments = ['issue_wrong_repo']
            self.actions['close'] = True

        elif self.meta['maintainer_waiting_on']:

            self.debug(msg='maintainer wait stanza')

            # FIXME - apply the triage label if needed

            self.issue.add_desired_label('waiting_on_maintainer')
            if len(self.issue.current_comments) == 0:
                self.issue.add_desired_comment('issue_new')
            else:
                # maintainers in ansible/ansible are not a a real thing -yet-
                pass

        elif self.meta['submitter_waiting_on']:

            self.debug(msg='submitter wait stanza')

            if 'waiting_on_maintainer' in self.issue.desired_labels:
                self.issue.desired_labels.remove('waiting_on_maintainer')

            if self.meta['needsinfo_add']:

                self.issue.add_desired_label('needs_info')
                if len(self.issue.current_comments) == 0:
                    self.issue.add_desired_comment('issue_needs_info')

                # needs_info: warn if stale, close if expired
                elif self.meta['needsinfo_expired']:
                    self.issue.add_desired_comment('issue_closure')
                    self.issue.set_desired_state('closed')
                elif self.meta['needsinfo_stale'] \
                    and (self.meta['submitter_to_ping'] or self.meta['submitter_to_reping']):
                    self.issue.add_desired_comment('issue_pending_closure')
