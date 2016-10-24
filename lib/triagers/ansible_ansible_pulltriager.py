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

    VALID_COMMANDS = ['needs_info', '!needs_info', 'notabug', 
                      'bot_broken', 'bot_skip',
                      'wontfix', 'bug_resolved', 'resolved_by_pr', 
                      'needs_contributor', 'duplicate_of']


