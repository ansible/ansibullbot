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
from issuetriager import TriageIssues

loader = FileSystemLoader(os.path.join(os.path.dirname(__file__), 'templates'))
environment = Environment(loader=loader, trim_blocks=True)


class AnsibleAnsibleTriageIssues(TriageIssues):

    # triage label should be added by bot, removed by human ... later by commands?

    VALID_COMMANDS = ['needs_info', '!needs_info', 'notabug', 
                      'wontfix', 'bug_resolved', 'resolved_by_pr', 
                      'needs_contributor', 'duplicate_of']

    IGNORE_LABELS_ADD = ['cloud', 'networking', 'vmware', 'windows', 'openstack']

    def process(self, usecache=True):
        '''Does the real work on the issue'''

        # baseline processing [creates no actions]
        self._process()

        # unique processing workflow for this repo ...
        #self.debug('des.labels.1: %s' % ' '.join(self.issue.desired_labels))
        self.process_history(usecache=usecache) # use events to add desired labels or comments
        #self.debug('des.labels.2: %s' % ' '.join(self.issue.desired_labels))
        self.add_desired_labels_by_issue_type(comments=False) # only adds desired labels
        #self.debug('des.labels.3: %s' % ' '.join(self.issue.desired_labels))
        self.create_label_actions() # creates the label actions
        self.create_commment_actions() # renders the desired comments

        # do the actions ...
        self.debug('cur.labels: %s' % ' '.join(self.issue.current_labels))
        self.debug('component: %s' % self.template_data.get('component name'))
        self.debug('match: %s' % self.match)
        self.debug('module: %s' % self.module)
        self.debug('submitter: %s' % self.issue.get_submitter())
        self.debug('assignee: %s' % self.issue.get_assignee())
        self.debug('comments: %s' % len(self.issue.current_comments))
        import pprint; pprint.pprint(self.actions)
        #import epdb; epdb.st()
        action_meta = self.apply_actions()
        return action_meta


    def process_history(self, usecache=True):

        #################################################
        #           SET STATE FROM HISTORY              #
        #################################################

        ## Build the history
        self.debug(msg="Building event history ...")
        self.meta.update(self.get_history_facts(usecache=usecache))

        ## state workflow ...
        if self.meta['bot_broken']:

            self.debug(msg='broken bot stanza')

            self.issue.add_desired_label('bot_broken')

        elif (self.match and (self.github_repo != self.match.get('repository', 'ansible')))\
            or 'needs_to_be_moved' in self.issue.current_labels:

            self.debug(msg='wrong repo stanza')

            if not self.match:
                import epdb; epdb.st()

            self.issue.add_desired_comment('issue_wrong_repo')
            self.issue.desired_comments = ['issue_wrong_repo']
            self.actions['close'] = True

        elif self.meta['maintainer_waiting_on']:

            self.debug(msg='maintainer wait stanza')

            # A) no [admin?] comments + no assingee == triage
            # B) [admin] comments or assignee == !triage
            if not self.meta['maintainer_commented'] and not self.issue.instance.assignee:
                self.issue.add_desired_label(name='triage')
            else:
                self.issue.pop_desired_label(name='triage')

        elif self.meta['submitter_waiting_on']:

            self.debug(msg='submitter wait stanza')

            # it's not triage if it's WOS
            self.issue.pop_desired_label(name='triage')
            # do not use WOM for ansible/ansible
            self.issue.pop_desired_label(name='waiting_on_maintainer')

            if self.meta['needsinfo_remove']:
                self.issue.pop_desired_label('needs_info')
            else:

                if self.meta['needsinfo_add']:
                    self.issue.add_desired_label('needs_info')

                if self.meta['missing_sections'] and not self.meta['last_commentor_ismaintainer']:
                    self.issue.add_desired_comment('issue_needs_info')

                # needs_info: warn if stale, close if expired
                if self.meta['needsinfo_expired']:
                    self.issue.add_desired_comment('issue_closure')
                    self.issue.set_desired_state('closed')
                elif self.meta['needsinfo_stale'] \
                    and (self.meta['submitter_to_ping'] or self.meta['submitter_to_reping']):
                    self.issue.add_desired_comment('issue_pending_closure')


