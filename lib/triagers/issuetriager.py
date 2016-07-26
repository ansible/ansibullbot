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
from operator import itemgetter

# remember to pip install PyGithub, kids!
from github import Github

from jinja2 import Environment, FileSystemLoader

from lib.wrappers.issuewrapper import IssueWrapper
from lib.wrappers.historywrapper import HistoryWrapper
from lib.utils.moduletools import ModuleIndexer
from lib.utils.extractors import extract_template_data

from defaulttriager import DefaultTriager

loader = FileSystemLoader(os.path.join(os.path.dirname(__file__), 'templates'))
environment = Environment(loader=loader, trim_blocks=True)


class TriageIssues(DefaultTriager):


    def run(self):
        """Starts a triage run"""
        self.repo = self._connect().get_repo("ansible/ansible-modules-%s" %
                                        self.github_repo)

        if self.number:
            issue = self.repo.get_issue(int(self.number))
            self.issue = IssueWrapper(repo=self.repo, issue=issue)
            self.issue.get_events()
            self.issue.get_comments()
            self.process()
        else:
            issues = self.repo.get_issues()
            for issue in issues:
                if self.start_at and issue.number > self.start_at:
                    continue
                if self.is_pr(issue):
                    continue
                self.issue = IssueWrapper(repo=self.repo, issue=issue)
                self.issue.get_events()
                self.issue.get_comments()
                self.process()


    def process(self):
        """Processes the Issue"""
        # clear all actions
        self.actions = {
            'newlabel': [],
            'unlabel':  [],
            'comments': [],
        }

        # clear module maintainers
        self.module_maintainers = []

        # print some general info about the Issue to be processed
        print("\nIssue #%s: %s" % (self.issue.number,
                                (self.issue.instance.title).encode('ascii','ignore')))
        print("Created at %s" % self.issue.instance.created_at)
        print("Updated at %s" % self.issue.instance.updated_at)

        # get the template data
        self.template_data = self.issue.get_template_data()
        # was the issue type defined correctly?
        issue_type_defined = False
        issue_type_valid = False
        issue_type = False
        if 'issue type' in self.template_data:
            issue_type_defined = True
            issue_type = self.template_data['issue type']
            if issue_type.lower() in self.VALID_ISSUE_TYPES:
                issue_type_valid = True

        # was component specified?
        component_defined = 'component name' in self.template_data
        # extract the component
        component = self.template_data.get('component name', None)
        # save the real name
        self.match = self.module_indexer.find_match(component) or {}
        self.module = self.match.get('name', None)
        # check if component is a known module
        component_isvalid = self.module_indexer.is_valid(component)

        # filed under the correct repository?
        this_repo = False
        correct_repo = None
        # who maintains this?
        maintainers = []

        if not component_isvalid:
            pass
        else:
            correct_repo = self.module_indexer.\
                            get_repository_for_module(component)
            if correct_repo == self.github_repo:
                this_repo = True
                maintainers = self.get_module_maintainers()

        # Has the maintainer -ever- commented?
        maintainer_commented = False
        if component_isvalid:
            maintainer_commented = self.has_maintainer_commented()

        waiting_on_maintainer = False
        if component_isvalid:
            waiting_on_maintainer = self.is_waiting_on_maintainer()

        # How long ago did the maintainer last comment?
        maintainer_last_comment_age = -1
        if component_isvalid:
            maintainer_last_comment_age = self.age_of_last_maintainer_comment()


        ###########################################################
        #                   Enumerate Actions
        ###########################################################

        self.keep_current_main_labels()
        self.debug(msg='desired_comments: %s' % self.issue.desired_comments)

        self.add_desired_labels_by_issue_type()
        self.debug(msg='desired_comments: %s' % self.issue.desired_comments)

        self.add_desired_labels_by_ansible_version()
        self.debug(msg='desired_comments: %s' % self.issue.desired_comments)

        self.add_desired_labels_by_namespace()
        self.debug(msg='desired_comments: %s' % self.issue.desired_comments)

        '''
        self.add_desired_labels_by_maintainers()
        self.debug(msg='desired_comments: %s' % self.issue.desired_comments)
        '''

        #self.process_comments()
        self.process_history()
        self.debug(msg='desired_comments: %s' % self.issue.desired_comments)
        
        self.create_actions()
        self.debug(msg='desired_comments: %s' % self.issue.desired_comments)


        ###########################################################
        #                        LOG 
        ###########################################################
        print("Submitter: %s" % self.issue.get_submitter())
        print("Issue Type Defined: %s" % issue_type_defined)
        print("Issue Type Valid: %s" % issue_type_valid)
        print("Issue Type: %s" % issue_type)
        print("Component Defined: %s" % component_defined)
        print("Component Name: %s" % component)
        print("Component is Valid Module: %s" % component_isvalid)
        print("Component in this repo: %s" % this_repo)
        print("Module: %s" % self.module)
        print("Maintainer(s): %s" % ', '.join(maintainers))
        #print("Maintainer(s) Have Commented: %s" % maintainer_commented)
        #print("Maintainer(s) Comment Age: %s days" % maintainer_last_comment_age)
        #print("Waiting on Maintainer(s): %s" % waiting_on_maintainer)
        print("Current Labels: %s" % ', '.join(sorted(self.issue.current_labels)))
        print("Desired Labels: %s" % ', '.join(sorted(self.issue.desired_labels)))
        print("Current Comments: %s" % len(self.issue.current_comments))
        print("Desired Comments: %s" % ', '.join(self.issue.desired_comments))
        print("Actions: ...")
        print("NEWLABEL:")
        import pprint; pprint.pprint(self.actions['newlabel'])
        print("UNLABEL:")
        import pprint; pprint.pprint(self.actions['unlabel'])

        #if not component_isvalid:
        #    import epdb; epdb.st()
        
        #if not issue_type_valid and 'issue type' in self.issue.instance.body.lower():
        #    import epdb; epdb.st()

        #if 'ansible' in self.module_maintainers and maintainer_commented:
        #    import epdb; epdb.st()

        #if waiting_on_maintainer and maintainer_commented:
        #    import epdb; epdb.st()

        if self.always_pause:
            import epdb; epdb.st()

    def create_actions(self):
        """Create actions from the desired label/unlabel/comment actions"""
        resolved_desired_labels = []
        for desired_label in self.issue.desired_labels:
            resolved_desired_label = self.issue.resolve_desired_labels(
                desired_label
            )
            if desired_label != resolved_desired_label:
                resolved_desired_labels.append(resolved_desired_label)
                if (resolved_desired_label not in self.issue.get_current_labels()):
                    self.issue.add_desired_comment(desired_label)
                    self.actions['newlabel'].append(resolved_desired_label)
            else:
                #import epdb; epdb.st()
                resolved_desired_labels.append(desired_label)
                if desired_label not in self.issue.get_current_labels():
                    self.actions['newlabel'].append(desired_label)
                    if os.path.exists("templates/" + 'issue_' + desired_label + ".j2"):
                        self.issue.add_desired_comment('issue_' + desired_label)

        for current_label in self.issue.get_current_labels():
            if current_label in self.IGNORE_LABELS:
                continue
            if current_label not in resolved_desired_labels:
                self.actions['unlabel'].append(current_label)

        for boilerplate in self.issue.desired_comments:
            comment = self.render_comment(boilerplate=boilerplate)
            #self.debug(msg=comment)
            self.debug(msg=boilerplate)
            self.actions['comments'].append(comment)
            #import epdb; epdb.st()

    def process_history(self):
        self.meta = {}
        today = datetime.today()

        # Build the history
        self.history = HistoryWrapper(self.issue)
        self.meta['event_count'] = len(self.history.history)

        # who made this and when did they last comment?
        submitter = self.issue.get_submitter()
        self.meta['submitter'] = submitter
        submitter_last_commented = self.history.last_commented_at(submitter)
        self.meta['submitter_last_commented'] = submitter_last_commented

        # what did they not provide?
        missing_sections = self.issue.get_missing_sections()
        self.meta['missing_sections'] = missing_sections

        # Who are the maintainers?
        maintainers = self.get_module_maintainers()
        if 'ansible' in maintainers:
            maintainers.remove('ansible')
            maintainers += self.ansible_members
        self.meta['maintainers'] = maintainers

        # Has maintainer viewed issue?
        maintainer_viewed = self.history.has_viewed(maintainers)
        self.meta['maintainer_viewed'] = maintainer_viewed
        maintainer_last_viewed = self.history.last_viewed_at(maintainers)
        self.meta['maintainer_last_viewed'] = maintainer_last_viewed

        # Has maintainer been mentioned?
        maintainer_mentioned = self.history.is_mentioned(maintainers)
        self.meta['maintainer_mentioned'] = maintainer_mentioned

        # Has maintainer viewed issue?
        maintainer_viewed = self.history.has_viewed(maintainers)
        self.meta['maintainer_viewed'] = maintainer_viewed

        # Has the maintainer ever responded?
        maintainer_commented = self.history.has_commented(maintainers)
        self.meta['maintainer_commented'] = maintainer_commented
        maintainer_last_commented = self.history.last_commented_at(maintainers)
        self.meta['maintainer_last_commented'] = maintainer_last_commented

        # Has the maintainer ever subscribed?
        maintainer_subscribed = self.history.has_subscribed(maintainers)
        self.meta['maintainer_subscribed'] = maintainer_subscribed

        # Was it ever needs_info?
        was_needs_info = self.history.was_labeled(label='needs_info')
        needsinfo_last_applied = self.history.label_last_applied('needs_info')
        self.meta['was_needs_info'] = was_needs_info
        self.meta['needsinfo_last_applied'] = needsinfo_last_applied

        # Still needs_info?
        needsinfo_remove = False
        needsinfo_last_applied = None
        if 'needs_info' in self.issue.current_labels:
            if submitter_last_commented:
                if submitter_last_commented > needsinfo_last_applied \
                    and not missing_sections:
                    needsinfo_remove = True                
        self.meta['needsinfo_remove'] = needsinfo_remove

        # Is needs_info stale or expired?
        needsinfo_stale = False
        needsinfo_expired = False
        if not needsinfo_remove and needsinfo_last_applied:
            time_delta = today - needsinfo_last_applied
            needsinfo_age = time_delta.days
            if needsinfo_age > 14:
                needsinfo_stale = True
            if needsinfo_age > 30:
                needsinfo_expired = True
        self.meta['needsinfo_stale'] = needsinfo_stale
        self.meta['needsinfo_expired'] = needsinfo_expired

        # Time to [re]ping maintainer?
        maintainer_to_ping = False
        maintainer_to_reping = False
        if (needsinfo_remove or not needsinfo_last_applied)\
            and not missing_sections:

            if maintainer_viewed:
                time_delta = today - maintainer_last_viewed
                view_age = time_delta.days
                if view_age > 14:
                    maintainer_to_reping = True
            else:
                maintainer_to_ping = True
        self.meta['maintainer_to_ping'] = maintainer_to_ping
        self.meta['maintainer_to_reping'] = maintainer_to_reping

        # Should we be in waiting_on_maintainer mode?
        maintainer_waiting_on = False
        if needsinfo_remove or not was_needs_info and not missing_sections:
            maintainer_waiting_on = True
        self.meta['maintainer_waiting_on'] = maintainer_waiting_on

        # Should we [re]notify the submitter?
        submitter_waiting_on = False
        submitter_to_ping = False
        submitter_to_reping = False
        needsinfo_add = False
        if not maintainer_waiting_on:
            submitter_waiting_on = True
            if needsinfo_stale or needsinfo_expired:
                submitter_to_reping = True
            else:                                                        
                submitter_to_ping = True
            if missing_sections:
                needsinfo_add = True

        self.meta['submitter_waiting_on'] = submitter_waiting_on
        self.meta['submitter_to_ping'] = submitter_to_ping
        self.meta['submitter_to_reping'] = submitter_to_reping
        self.meta['needsinfo_add'] = needsinfo_add

        #issue_bug_report, issue_docs_report, issue_feature_idea
        issue_type = self.template_data.get('issue type', None)
        issue_type = self.issue_type_to_label(issue_type)
        self.meta['issue_type'] = issue_type

        #################################################
        # FINAL LOGIC LOOP
        #################################################

        if maintainer_waiting_on:
            self.issue.add_desired_label('waiting_on_maintainer')
            if len(self.issue.current_comments) == 0:
                if issue_type:
                    self.issue.add_desired_comment('issue_' + issue_type)
            elif maintainer_to_ping:
                self.issue.add_desired_comment("issue_notify_maintainer")
            elif maintainer_to_reping:
                self.issue.add_desired_comment("issue_renotify_maintainer")

        elif submitter_waiting_on:

            if 'waiting_on_maintainer' in self.issue.desired_labels:
                self.issue.desired_labels.remove('waiting_on_maintainer')

            if needsinfo_add:
                self.issue.add_desired_label('needs_info')

            if submitter_to_ping or submitter_to_reping:
                self.issue.add_desired_comment("issue_needs_info")
            

