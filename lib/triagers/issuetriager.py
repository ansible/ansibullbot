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

from lib.utils.moduletools import ModuleIndexer
from lib.utils.extractors import extract_template_data

loader = FileSystemLoader(os.path.join(os.path.dirname(__file__), 'templates'))
environment = Environment(loader=loader, trim_blocks=True)

# A dict of alias labels. It is used for coupling a template (comment) with a
# label.
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

MAINTAINERS_FILES = {
    'core': "MAINTAINERS-CORE.txt",
    'extras': "MAINTAINERS-EXTRAS.txt",
}

# modules having files starting like the key, will get the value label
MODULE_NAMESPACE_LABELS = {
    'cloud': "cloud",
    'cloud/google': "gce",
    'cloud/amazon': "aws",
    'cloud/azure': "azure",
    'cloud/digital_ocean': "digital_ocean",
    'windows': "windows",
    'network': "networking"
}

# We don't remove any of these labels unless forced
MUTUALLY_EXCLUSIVE_LABELS = [
    "shipit",
    "needs_revision",
    "needs_info",
    "community_review",
    "core_review",
]

# Static labels, manually added
IGNORE_LABELS = [
    "feature_pull_request",
    "bugfix_pull_request",
    "in progress",
    "docs_pull_request",
    "easyfix",
    "pending_action",
    "gce",
    "python3",
]

# We warn for human interaction
MANUAL_INTERACTION_LABELS = [
    "needs_revision",
    "needs_info",
]

BOTLIST = [
    'gregdek',
    'robynbergeron',
]


class IssueWrapper(object):

    def __init__(self, repo=None, issue=None):
        self.repo = repo
        self.instance = issue
        self.number = self.instance.number
        self.current_labels = self.get_current_labels()
        self.desired_labels = []
        self.current_comments = []
        self.desired_comments = []

    def get_comments(self):
        """Returns all current comments of the PR"""
        if not self.current_comments:
            #self.current_comments = self.instance.get_comments().reversed
            self.current_comments = \
                [x for x in self.instance.get_comments().reversed]
        return self.current_comments

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
        tdict = extract_template_data(self.instance.body)
        return tdict

    def resolve_desired_labels(self, desired_label):
        for resolved_label, aliases in ALIAS_LABELS.iteritems():
            if desired_label in aliases:
                return resolve_label
        return desired_label

    def process_mutually_exclusive_labels(self, name=None):
        resolved_name = self.resolve_desired_labels(name)
        if resolved_name in MUTUALLY_EXCLUSIVE_LABELS:
            for label in self.desired_labels:
                resolved_label = self.resolve_desired_labels(label)
                if resolved_label in MUTUALLY_EXCLUSIVE_LABELS:
                    self.desired_labels.remove(label)        

    def add_desired_label(self, name=None):
        """Adds a label to the desired labels list"""
        if name and name not in self.desired_labels:
            self.process_mutually_exclusive_labels(name=name)
            self.desired_labels.append(name)


class TriageIssues:

    def __init__(self, verbose=None, github_user=None, github_pass=None,
                 github_token=None, github_repo=None, number=None,
                 start_at=None, always_pause=False, force=False, dry_run=False):

        self.valid_issue_types = ['bug report', 'feature idea', 'documentation report']
        self.topic_map = {'amazon': 'aws',
                          'google': 'gce',
                          'network': 'networking'}

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

        self.issue = None
        self.maintainers = {}
        self.module_maintainers = []
        self.actions = {
            'newlabel': [],
            'unlabel':  [],
            'comments': [],
        }

        self.module_indexer = ModuleIndexer()
        self.module_indexer.get_ansible_modules()
        self.ansible_members = self.get_ansible_members()
        self.valid_labels = self.get_valid_labels()

    def _connect(self):
        """Connects to GitHub's API"""
        return Github(login_or_token=self.github_token or self.github_user,
                      password=self.github_pass)

    def is_pr(self, issue):
        if '/pull/' in issue.html_url:
            return True
        else:
            return False

    def get_ansible_members(self):
        ansible_members = []
        org = self._connect().get_organization("ansible")
        members = org.get_members()
        ansible_members = [x.login for x in members]
        #import epdb; epdb.st()
        return ansible_members

    def get_valid_labels(self):
        vlabels = []
        self.repo = self._connect().get_repo("ansible/ansible-modules-%s" %
                                        self.github_repo)
        for vl in self.repo.get_labels():
            vlabels.append(vl.name)
        return vlabels

    def _get_maintainers(self):
        """Reads all known maintainers from files and their owner namespace"""
        if not self.maintainers:
            f = open(MAINTAINERS_FILES[self.github_repo])
            for line in f:
                owner_space = (line.split(': ')[0]).strip()
                maintainers_string = (line.split(': ')[-1]).strip()
                self.maintainers[owner_space] = maintainers_string.split(' ')
            f.close()
        return self.maintainers

    def debug(self, msg=""):
        """Prints debug message if verbosity is given"""
        if self.verbose:
            print("Debug: " + msg)

    def get_module_maintainers(self):
        """Returns the list of maintainers for the current module"""
        if self.module_maintainers:
            return self.module_maintainers
        #module = self.template_data.get('component name', None)
        module = self.module
        if not module:
            self.module_maintainers = []
            return self.module_maintainers

        if not self.module_indexer.is_valid(module):
            self.module_maintainers = []
            return self.module_maintainers

        mdata = self.module_indexer.find_match(module)
        if mdata['repository'] != self.github_repo:
            # this was detected and handled in the process loop
            pass

        maintainers = self._get_maintainers()
        if mdata['repo_filename'] in maintainers:
            self.module_maintainers = maintainers[mdata['repo_filename']]
        elif mdata['namespaced_module'] in maintainers:
            self.module_maintainers = maintainers[mdata['namespaced_module']]
        elif mdata['fulltopic'] in maintainers:
            self.module_maintainers = maintainers[mdata['fulltopic']]
        elif (mdata['topic'] + '/') in maintainers:
            self.module_maintainers = maintainers[mdata['topic'] + '/']
        else:
            #import pprint; pprint.pprint(mdata)
            #import epdb; epdb.st()
            pass

        return self.module_maintainers

    def get_current_labels(self):
        """Pull the list of labels on this Issue"""
        if not self.current_labels:
            labels = self.issue.instance.labels
            for label in labels:
                self.current_labels.append(label.name)
        return self.current_labels

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
            if issue_type.lower() in self.valid_issue_types:
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

                    thislabel = self.topic_map.get(self.match[key], self.match[key])

                    if thislabel not in self.issue.current_labels \
                        and thislabel in self.valid_labels:
                        self.actions.append("ALABEL: add %s" % thislabel)
            #import epdb; epdb.st()


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

        if waiting_on_maintainer and maintainer_commented:
            import epdb; epdb.st()


    def component_from_comments(self):
        # https://github.com/ansible/ansible-modules/core/issues/2618
        # comments like: [module: packaging/os/zypper.py] ... ?
        component = None
        for idx, x in enumerate(self.issue.current_comments):
            if '[' in x.body and ']' in x.body and ('module' in x.body or 'component' in x.body or 'plugin' in x.body):
                if x.user.login in BOTLIST:
                    component = x.body.split()[-1]
                    component = component.replace('[', '')
        return component

    def has_maintainer_commented(self):
        commented = False
        if self.module_maintainers:
                
            for comment in self.issue.current_comments:
                # ignore comments from submitter
                if comment.user.login == self.issue.get_submitter():
                    continue

                # "ansible" is special ...
                if 'ansible' in self.module_maintainers \
                    and comment.user.login in self.ansible_members:
                    commented = True
                elif comment.user.login in self.module_maintainers:
                    commented = True

        return commented

    def age_of_last_maintainer_comment(self):
        last_comment = None
        if self.module_maintainers:
            for idx,comment in enumerate(self.issue.current_comments):
                # "ansible" is special ...
                is_maintainer = False
                if 'ansible' in self.module_maintainers \
                    and comment.user.login in self.ansible_members:
                    is_maintainer = True
                elif comment.user.login in self.module_maintainers:
                    is_maintainer = True

                if is_maintainer:
                    last_comment = comment
                    break

        if not last_comment:
            return -1
        else:
            now = datetime.now()
            diff = now - last_comment.created_at
            age = diff.days
            return age

    def is_waiting_on_maintainer(self):
        waiting = False
        if self.module_maintainers:
            if not self.issue.current_comments:
                return True            

            creator_last_index = -1
            maintainer_last_index = -1
            for idx,comment in enumerate(self.issue.current_comments):
                if comment.user.login == self.issue.get_submitter():
                    if creator_last_index == -1 or idx < creator_last_index:
                        creator_last_index = idx

                # "ansible" is special ...
                is_maintainer = False
                if 'ansible' in self.module_maintainers \
                    and comment.user.login in self.ansible_members:
                    is_maintainer = True
                elif comment.user.login in self.module_maintainers:
                    is_maintainer = True

                if is_maintainer and \
                    (maintainer_last_index == -1 or idx < maintainer_last_index):
                    maintainer_last_index = idx

            if creator_last_index == -1 and maintainer_last_index == -1:
                waiting = True
            elif creator_last_index == -1 and maintainer_last_index > -1:
                waiting = False
            elif creator_last_index < maintainer_last_index:
                waiting = True

        #if self.issue.instance.number == 4200:
        #    import epdb; epdb.st()
        return waiting                
            

    def keep_current_main_labels(self):
        current_labels = self.issue.get_current_labels()
        for current_label in current_labels:
            if current_label in MUTUALLY_EXCLUSIVE_LABELS:
                self.issue.add_desired_label(name=current_label)




