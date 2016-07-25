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

    MUTUALLY_EXCLUSIVE_LABELS = [
	"shipit",
	"needs_revision",
	"needs_info",
	"community_review",
	"core_review",
    ]

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
        for resolved_label, aliases in self.ALIAS_LABELS.iteritems():
            if desired_label in aliases:
                return resolve_label
        return desired_label

    def process_mutually_exclusive_labels(self, name=None):
        resolved_name = self.resolve_desired_labels(name)
        if resolved_name in self.MUTUALLY_EXCLUSIVE_LABELS:
            for label in self.desired_labels:
                resolved_label = self.resolve_desired_labels(label)
                if resolved_label in MUTUALLY_EXCLUSIVE_LABELS:
                    self.desired_labels.remove(label)        

    def add_desired_label(self, name=None):
        """Adds a label to the desired labels list"""
        if name and name not in self.desired_labels:
            self.process_mutually_exclusive_labels(name=name)
            self.desired_labels.append(name)



