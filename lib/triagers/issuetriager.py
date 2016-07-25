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

# remember to pip install PyGithub, kids!
from github import Github

from jinja2 import Environment, FileSystemLoader

from lib.wrappers.issuewrapper import IssueWrapper
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
            self.issue = Issue(repo=self.repo, number=self.number)
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
        self.add_desired_labels_by_issue_type()
        self.add_desired_labels_by_ansible_version()
        self.add_desired_labels_by_namespace()
        self.add_desired_labels_by_maintainers()
        self.process_comments()
        self.create_actions()

        '''
        self.actions = [] #hackaround
        if not issue_type_defined:
            self.actions.append('ENOTEMPLATE: please use template')        
        elif not issue_type_valid:
            self.actions.append('ENOISSUETYPE: please use valid issue type')        
        elif issue_type_valid:
            thislabel = issue_type.lower().replace(' ', '_')
            thislabel = thislabel.replace('documentation', 'docs')
            if thislabel in self.valid_labels \
                and thislabel not in self.issue.current_labels:
                self.actions.append("ALABEL: add %s" % thislabel)
            elif thislabel not in self.valid_labels:
                print('%s NOT VALID!' % thislabel)
                import epdb; epdb.st()

        if not component_defined:
            self.actions.append('ENOTEMPLATE: please use template')        
        elif not component_isvalid:
            self.actions.append('ENOMODULE: please specify a valid module name')        
        if component_isvalid and not this_repo:
            self.actions.append('EWRONGREPO: please file under %s' % correct_repo)

        if component_isvalid and this_repo and not maintainers:
            self.actions.append('ENOMAINTAINER: module has no maintainer')

        if component_isvalid:
            if maintainers and not 'needs_info' in self.issue.current_labels:
                if not maintainer_commented:
                    self.actions.append("WOM: ping maintainer(s)")
                if maintainer_commented \
                    and waiting_on_maintainer \
                    and maintainer_last_comment_age > 14:
                    self.actions.append("WOM: -remind- maintainer(s)")
            if maintainers \
                and 'needs_info' in self.issue.current_labels \
                and not waiting_on_maintainer:
                    self.actions.append("RLABEL: remove needs_info")

            for key in ['topic', 'subtopic']:            
                if self.match[key]:

                    thislabel = self.issue.TOPIC_MAP.get(self.match[key], self.match[key])

                    if thislabel not in self.issue.current_labels \
                        and thislabel in self.valid_labels:
                        self.actions.append("ALABEL: add %s" % thislabel)
            #import epdb; epdb.st()
        '''

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
        print("Maintainer(s) Have Commented: %s" % maintainer_commented)
        print("Maintainer(s) Comment Age: %s days" % maintainer_last_comment_age)
        print("Waiting on Maintainer(s): %s" % waiting_on_maintainer)
        print("Current Labels: %s" % ', '.join(self.issue.current_labels))
        print("Actions: %s" % self.actions)

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


