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

import json
import os
import sys
import time
from datetime import datetime

# remember to pip install PyGithub, kids!
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

    def __init__(self, repo=None, issue=None):
        self.repo = repo
        self.instance = issue
        self.number = self.instance.number
        self.current_labels = self.get_current_labels()
        self.template_data = {}
        self.desired_labels = []
        self.current_events = []
        self.current_comments = []
        self.current_bot_comments = []
        self.current_reactions = []
        self.desired_comments = []
        self.current_state = 'open'
        self.desired_state = 'open'

    def get_comments(self):
        """Returns all current comments of the PR"""
        if not self.current_comments:
            self.current_comments = [x for x in self.instance.get_comments()]
            self.current_comments.reverse()
            #print("GOT %s COMMENTS" % len(self.current_comments))
            for x in self.current_comments:
                body = x.body
                lines = body.split('\n')
                if lines[-1].startswith('<!---') \
                    and lines[-1].endswith('--->') \
                    and 'boilerplate:' in lines[-1]:
                    parts = lines[-1].split()
                    boilerplate = parts[2]
                    self.current_bot_comments.append(boilerplate)
                else:
                    self.current_bot_comments.append('')
        return self.current_comments

    def get_events(self):
        if not self.current_events:
            self.current_events = \
                [x for x in self.instance.get_events()]
        return self.current_events

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
        if not self.template_data:
            self.template_data = \
                extract_template_data(self.instance.body, issue_number=self.number)
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

    def add_desired_label(self, name=None):
        """Adds a label to the desired labels list"""
        if name and name not in self.desired_labels:
            self.process_mutually_exclusive_labels(name=name)
            self.desired_labels.append(name)

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

