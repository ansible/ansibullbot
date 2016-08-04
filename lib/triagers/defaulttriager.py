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
import pytz
from datetime import datetime

# remember to pip install PyGithub, kids!
from github import Github

from jinja2 import Environment, FileSystemLoader

from lib.wrappers.issuewrapper import IssueWrapper
from lib.utils.moduletools import ModuleIndexer
from lib.utils.extractors import extract_template_data
from lib.utils.descriptionfixer import DescriptionFixer

basepath = os.path.dirname(__file__).split('/')
libindex = basepath.index('lib')
basepath = '/'.join(basepath[0:libindex])
loader = FileSystemLoader(os.path.join(basepath, 'templates'))
environment = Environment(loader=loader, trim_blocks=True)

# A dict of alias labels. It is used for coupling a template (comment) with a
# label.

MAINTAINERS_FILES = {
    'core': "MAINTAINERS-CORE.txt",
    'extras': "MAINTAINERS-EXTRAS.txt",
}


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


class DefaultTriager(object):

    BOTLIST = ['gregdek', 'robynbergeron', 'ansibot']
    VALID_ISSUE_TYPES = ['bug report', 'feature idea', 'documentation report']
    IGNORE_LABELS = [
        "feature_pull_request",
        "feature_idea",
        "bugfix_pull_request",
        "bug_report",
        "docs_pull_request",
        "docs_report",
        "in progress",
        "docs_pull_request",
        "easyfix",
        "pending_action",
        "gce",
        "python3",
        "P1","P2","P3","P4",
    ]


    def __init__(self, verbose=None, github_user=None, github_pass=None,
                 github_token=None, github_repo=None, number=None,
                 start_at=None, always_pause=False, force=False, safe_force=False, dry_run=False):

        self.verbose = verbose
        self.github_user = github_user
        self.github_pass = github_pass
        self.github_token = github_token
        self.github_repo = github_repo
        self.number = number
        self.start_at = start_at
        self.always_pause = always_pause
        self.force = force
        self.safe_force = safe_force
        self.dry_run = dry_run

        self.issue = None
        self.maintainers = {}
        self.module_maintainers = []
        self.actions = {
            'newlabel': [],
            'unlabel':  [],
            'comments': [],
            'close': False,
        }

        self.module_indexer = ModuleIndexer()
        self.module_indexer.get_ansible_modules()
        self.ansible_members = self.get_ansible_members()
        self.valid_labels = self.get_valid_labels()

        # processed metadata
        self.meta = {}

    def _connect(self):
        """Connects to GitHub's API"""
        return Github(login_or_token=self.github_token or self.github_user,
                      password=self.github_pass)

    def is_pr(self, issue):
        if '/pull/' in issue.html_url:
            return True
        else:
            return False

    def is_issue(self, issue):
        return not self.is_pr(issue)

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

    def _get_maintainers(self, usecache=True):
        """Reads all known maintainers from files and their owner namespace"""
        if not self.maintainers or not usecache:
            for repo in ['core', 'extras']:
                f = open(MAINTAINERS_FILES[repo])
                for line in f:
                    owner_space = (line.split(': ')[0]).strip()
                    maintainers_string = (line.split(': ')[-1]).strip()
                    self.maintainers[owner_space] = maintainers_string.split(' ')
                f.close()
            # meta is special
            self.maintainers['meta'] = ['ansible']
        return self.maintainers

    def debug(self, msg=""):
        """Prints debug message if verbosity is given"""
        if self.verbose:
            print("Debug: " + msg)

    def get_module_maintainers(self, expand=True):
        """Returns the list of maintainers for the current module"""
        # expand=False means don't use cache and don't expand the 'ansible' group

        if self.module_maintainers and expand:
            return self.module_maintainers
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

        # get cached or non-cached maintainers list
        if not expand:
            maintainers = self._get_maintainers(usecache=False)
        else:
            maintainers = self._get_maintainers()

        if mdata['repo_filename'] in maintainers:
            self.module_maintainers = maintainers[mdata['repo_filename']]
        elif (mdata['deprecated_filename']) in maintainers:
            self.module_maintainers = maintainers[mdata['deprecated_filename']]
        elif mdata['namespaced_module'] in maintainers:
            self.module_maintainers = maintainers[mdata['namespaced_module']]
        elif mdata['fulltopic'] in maintainers:
            self.module_maintainers = maintainers[mdata['fulltopic']]
        elif (mdata['topic'] + '/') in maintainers:
            self.module_maintainers = maintainers[mdata['topic'] + '/']
        else:
            pass

        if not self.module_maintainers and self.match:
            if self.match['authors']:
                self.module_maintainers = self.match['authors']

        return self.module_maintainers

    def get_current_labels(self):
        """Pull the list of labels on this Issue"""
        if not self.current_labels:
            labels = self.issue.instance.labels
            for label in labels:
                self.current_labels.append(label.name)
        return self.current_labels

    def run(self):
        pass

    def create_actions(self):
        pass

    def component_from_comments(self):
        """Extracts a component name from special comments"""
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
        """Has the maintainer -ever- commented on the issue?"""
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

    def is_maintainer_mentioned(self):
        mentioned = False
        if self.module_maintainers:
            for comment in self.issue.current_comments:
                # "ansible" is special ...
                if 'ansible' in self.module_maintainers:
                    for x in self.ansible_members:
                        if ('@%s' % x) in comment.body:
                            mentioned = True
                            break
                else:
                    for x in self.module_maintainers:
                        if ('@%s' % x) in comment.body:
                            mentioned = True
                            break
        return mentioned
       

    def get_current_time(self):
        now = datetime.now()
        #now = datetime.now(pytz.timezone('US/Pacific'))
        #import epdb; epdb.st()
        return now

    def age_of_last_maintainer_comment(self):
        """How long ago did the maintainer comment?"""
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
            now = self.get_current_time()
            diff = now - last_comment.created_at
            age = diff.days
            return age

    def is_waiting_on_maintainer(self):
        """Is the issue waiting on the maintainer to comment?"""
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

        return waiting                
            

    def keep_current_main_labels(self):
        current_labels = self.issue.get_current_labels()
        for current_label in current_labels:
            if current_label in self.issue.MUTUALLY_EXCLUSIVE_LABELS:
                self.issue.add_desired_label(name=current_label)

    def add_desired_labels_by_issue_type(self):
        """Adds labels by defined issue type"""
        issue_type = self.template_data.get('issue type', False)

        if issue_type is False:
            self.issue.add_desired_label('needs_info')
            #self.issue.add_desired_comment(
            #    boilerplate="issue_missing_data"
            #)            
            return

        if not issue_type.lower() in self.VALID_ISSUE_TYPES:
            self.issue.add_desired_label('needs_info')
            #self.issue.add_desired_comment(
            #    boilerplate="issue_missing_data"
            #)            
            return

        desired_label = issue_type.replace(' ', '_')        
        desired_label = desired_label.lower()
        desired_label = desired_label.replace('documentation', 'docs')
        if desired_label not in self.issue.get_current_labels():
            self.issue.add_desired_label(name=desired_label)
        if len(self.issue.current_comments) == 0:
            # only set this if no other comments
            #self.issue.add_desired_comment(boilerplate='issue_%s' % desired_label)
            self.issue.add_desired_comment(boilerplate='issue_new')

    def add_desired_labels_by_ansible_version(self):
        if not 'ansible version' in self.template_data:
            self.debug(msg="no ansible version section")
            self.issue.add_desired_label(name="needs_info")
            #self.issue.add_desired_comment(
            #    boilerplate="issue_missing_data"
            #)            
            return
        if not self.template_data['ansible version']:
            self.debug(msg="no ansible version defined")
            self.issue.add_desired_label(name="needs_info")
            #self.issue.add_desired_comment(
            #    boilerplate="issue_missing_data"
            #)            
            return

    def add_desired_labels_by_namespace(self):
        """Adds labels regarding module namespaces"""

        SKIPTOPICS = ['network/basics/']

        if not self.match:
            return False        

        '''
        if 'component name' in self.template_data and self.match:
            if self.match['repository'] != self.github_repo:
                self.issue.add_desired_comment(boilerplate='issue_wrong_repo')
        '''

        for key in ['topic', 'subtopic']:            
            # ignore networking/basics
            if self.match[key] and not self.match['fulltopic'] in SKIPTOPICS:
                thislabel = self.issue.TOPIC_MAP.\
                                get(self.match[key], self.match[key])
                if thislabel in self.valid_labels:
                    self.issue.add_desired_label(thislabel)

    def render_comment(self, boilerplate=None):
        """Renders templates into comments using the boilerplate as filename"""
        #maintainers = self.module_maintainers
        maintainers = self.get_module_maintainers(expand=False)
        #import epdb; epdb.st()
        if not maintainers:
            maintainers = ['NO_MAINTAINER_FOUND'] #FIXME - why?
        submitter = self.issue.get_submitter()
        missing_sections = [x for x in self.issue.REQUIRED_SECTIONS \
                            if not x in self.template_data \
                            or not self.template_data.get(x)]

        issue_type = self.template_data.get('issue type', None)
        if issue_type:
            issue_type = issue_type.lower()

        correct_repo = self.match.get('repository', None)

        template = environment.get_template('%s.j2' % boilerplate)
        comment = template.render(maintainers=maintainers, 
                                  submitter=submitter, 
                                  issue_type=issue_type,
                                  correct_repo=correct_repo,
                                  component_name=self.template_data.get('component name', 'NULL'),
                                  missing_sections=missing_sections)
        #import epdb; epdb.st()
        return comment


    def process_comments(self):
        """ Processes ISSUE comments for matching criteria to add labels"""
        if not self.github_user in self.BOTLIST:
            self.BOTLIST.append(self.github_user)
        module_maintainers = self.get_module_maintainers()
        comments = self.issue.get_comments()
        today = datetime.today()

        self.debug(msg="--- START Processing Comments:")

        for idc,comment in enumerate(comments):

            if comment.user.login in self.BOTLIST:
                self.debug(msg="%s is in botlist: " % comment.user.login)
                time_delta = today - comment.created_at
                comment_days_old = time_delta.days

                self.debug(msg="Days since last bot comment: %s" % comment_days_old)
                if comment_days_old > 14:
                    labels = self.issue.desired_labels

                    if 'pending' not in comment.body:

                        if self.issue.is_labeled_for_interaction():
                            self.debug(msg="submitter_first_warning")
                            self.issue.add_desired_comment(
                                boilerplate="submitter_first_warning"
                            )
                            break

                        if "maintainer_review" not in labels:
                            self.debug(msg="maintainer_first_warning")
                            self.issue.add_desired_comment(
                                boilerplate="maintainer_first_warning"
                            )
                            break

                    # pending in comment.body                           
                    else:
                        if self.issue.is_labeled_for_interaction():
                            self.debug(msg="submitter_second_warning")
                            self.issue.add_desired_comment(
                                boilerplate="submitter_second_warning"
                            )
                            break

                        if "maintainer_review" in labels:
                            self.debug(msg="maintainer_second_warning")
                            self.issue.add_desired_comment(
                                boilerplate="maintainer_second_warning"
                            )
                            break

                self.debug(msg="STATUS: no useful state change since last pass"
                            "( %s )" % comment.user.login)
                break

            if comment.user.login in module_maintainers \
                or comment.user.login.lower() in module_maintainers\
                or ('ansible' in module_maintainers and comment.user.login in self.ansible_members):

                self.debug(msg="%s is module maintainer commented on %s." % (comment.user.login, comment.created_at))
                if 'needs_info' in comment.body:
                    self.debug(msg="...said needs_info!")
                    self.issue.add_desired_label(name="needs_info")
                elif "close_me" in comment.body:
                    self.debug(msg="...said close_me!")
                    self.issue.add_desired_label(name="pending_action_close_me")
                    break

            if comment.user.login == self.issue.get_submitter():
                self.debug(msg="submitter %s, commented on %s." % (comment.user.login, comment.created_at))

            if comment.user.login not in self.BOTLIST and comment.user.login in self.ansible_members:
                self.debug(msg="%s is a ansible member" % comment.user.login)

        self.debug(msg="--- END Processing Comments")


    def issue_type_to_label(self, issue_type):
        if issue_type:
            issue_type = issue_type.lower()
            issue_type = issue_type.replace(' ', '_')
            issue_type = issue_type.replace('documentation', 'docs')
        return issue_type


    def check_safe_match(self):
        """ Turn force on or off depending on match characteristics """

        if self.action_count() == 0:
            self.force = True
        else:
            safe_match = False
            if self.module:
                if self.module in self.issue.instance.title.lower():
                    safe_match = True
            if safe_match:
                self.force = True
            else:
                self.force = False

    def action_count(self):
        """ Return the number of actions that are to be performed """
        count = 0
        for k,v in self.actions.iteritems():
            if k == 'close' and v:
                count += 1
            elif k != 'close':
                count += len(v)
        return count

    def apply_actions(self):

        action_meta = {'REDO': False}

        if self.safe_force:
            self.check_safe_match()

        if self.action_count() > 0:
            if self.dry_run:
                print("Dry-run specified, skipping execution of actions")
            else:
                if self.force:
                    print("Running actions non-interactive as you forced.")
                    self.execute_actions()
                    return
                cont = raw_input("Take recommended actions (y/N/a/R/T)? ")
                if cont in ('a', 'A'):
                    sys.exit(0)
                if cont in ('Y', 'y'):
                    self.execute_actions()
                if cont == 'T':
                    self.template_wizard()
                    action_meta['REDO'] = True
                if cont == 'r' or cont == 'R':
                    action_meta['REDO'] = True
                if cont == 'DEBUG':
                    import epdb; epdb.st()
        elif self.always_pause:
            print("Skipping, but pause.")
            cont = raw_input("Continue (Y/n/a/R/T)? ")
            if cont in ('a', 'A', 'n', 'N'):
                sys.exit(0)
            if cont == 'T':
                self.template_wizard()
                action_meta['REDO'] = True
            elif cont == 'REDO':
                action_meta['REDO'] = True
            elif cont == 'DEBUG':
                import epdb; epdb.st()
                action_meta['REDO'] = True
        else:
            print("Skipping.")
    
        # let the upper level code redo this issue
        return action_meta

    def template_wizard(self):
        print('################################################')
        print(self.issue.new_description)
        print('################################################')
        cont = raw_input("Apply this new description? (Y/N)")
        if cont == 'Y':
            self.issue.set_description(self.issue.new_description)
        #import epdb; epdb.st() 


    def execute_actions(self):
        """Turns the actions into API calls"""
        #time.sleep(1)
        for comment in self.actions['comments']:
            self.debug(msg="API Call comment: " + comment)
            self.issue.add_comment(comment=comment)
        if self.actions['close']:
            # https://github.com/PyGithub/PyGithub/blob/master/github/Issue.py#L263
            self.issue.instance.edit(state='closed')
            return
        for unlabel in self.actions['unlabel']:
            self.debug(msg="API Call unlabel: " + unlabel)
            self.issue.remove_label(label=unlabel)
        for newlabel in self.actions['newlabel']:
            self.debug(msg="API Call newlabel: " + newlabel)
            self.issue.add_label(label=newlabel)


    def smart_match_module(self):
        match = None
        known_modules = []
        #if not self.module_indexer.modules:
        #    import epdb; epdb.st()
        for k,v in self.module_indexer.modules.iteritems():
            known_modules.append(v['name'])

        title = self.issue.instance.title.lower()
        title = title.replace(':', '')
        title_matches = [x for x in known_modules if x + ' module' in title]
        if not title_matches:
            title_matches = [x for x in known_modules if title.startswith(x + ' ')]
            if not title_matches:
                title_matches = [x for x in known_modules if  ' ' + x + ' ' in title]
            

        cmatches = None
        if self.template_data.get('component name'):        
            component = self.template_data.get('component name')
            cmatches = [x for x in known_modules if x in component]
            cmatches = [x for x in cmatches if not '_' + x in component]

            # use title ... ?
            if title_matches:
                cmatches = [x for x in cmatches if x in title_matches]

            if cmatches:
                if len(cmatches) >= 1:
                    match = cmatches[0]
                if not match:
                    if 'docs.ansible.com' in component:
                        #import epdb; epdb.st()
                        pass
                    else:
                        #import epdb; epdb.st()
                        pass

        if not match:
            if len(title_matches) == 1:
                match = title_matches[0]
            else:
                print("TITLE MATCHES: %s" % title_matches)
                print("COMPONENT MATCHES: %s" % cmatches)
                #import epdb; epdb.st()

        #import epdb; epdb.st()
        return match
