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

from lib.wrappers.ghapiwrapper import ratecheck
from lib.wrappers.ghapiwrapper import GithubWrapper
from lib.wrappers.ghapiwrapper import RepoWrapper
from lib.wrappers.issuewrapper import IssueWrapper
from lib.wrappers.historywrapper import HistoryWrapper
from lib.utils.moduletools import ModuleIndexer
from lib.utils.extractors import extract_pr_number_from_comment
from lib.utils.extractors import extract_template_data
from lib.utils.descriptionfixer import DescriptionFixer

from defaulttriager import DefaultTriager

loader = FileSystemLoader(os.path.join(os.path.dirname(__file__), 'templates'))
environment = Environment(loader=loader, trim_blocks=True)


class TriageIssues(DefaultTriager):

    VALID_COMMANDS = ['needs_info', '!needs_info', 'notabug', 
                      'bot_broken', 'bot_skip',
                      'wontfix', 'bug_resolved', 'resolved_by_pr', 
                      'needs_contributor', 'duplicate_of']

    CLOSURE_COMMANDS = [
        'notabug',
        'wontfix',
        'bug_resolved',
        'resolved_by_pr',
        'duplicate_of'
    ]

    # re-notify interval for maintainers
    RENOTIFY_INTERVAL = 14

    # max limit for needs_info notifications
    RENOTIFY_EXPIRE = 56

    # re-notify interval by this number for features
    FEATURE_RENOTIFY_INTERVAL = 60

    # the max comments per week before ansibot becomes a "spammer"
    MAX_BOT_COMMENTS_PER_WEEK = 5

    def run(self, useapiwrapper=True):
        """Starts a triage run"""

        # how many issues have been processed
        self.icount = 0

        # Create the api connection
        if not useapiwrapper:
            # use the default non-caching connection
            self.repo = self._connect().get_repo(self._get_repo_path())
        else:
            # make use of the special caching wrapper for the api
            self.gh = self._connect()
            self.ghw = GithubWrapper(self.gh)
            self.repo = self.ghw.get_repo(self._get_repo_path())

        # extend the ignored labels by repo
        if hasattr(self, 'IGNORE_LABELS_ADD'):
            self.IGNORE_LABELS.extend(self.IGNORE_LABELS_ADD)

        if self.number:
            issue = self.repo.get_issue(int(self.number))
            self.issue = IssueWrapper(repo=self.repo, issue=issue, cachedir=self.cachedir)
            self.issue.get_events()
            self.issue.get_comments()
            self.process()
        else:

            last_run = None
            now = self.get_current_time()
            last_run_file = '~/.ansibullbot/cache'
            if self.github_repo == 'ansible':
                last_run_file += '/ansible/ansible/'
            else:
                last_run_file += '/ansible/ansible-modules-%s/' % self.github_repo
            last_run_file += 'issues/last_run.pickle'
            last_run_file = os.path.expanduser(last_run_file)
            if os.path.isfile(last_run_file):
                try:
                    with open(last_run_file, 'rb') as f:
                        last_run = pickle.load(f)
                except Exception as e:
                    print(e)

            if last_run and not self.no_since:
                self.debug('Getting issues updated/created since %s' % last_run)
                issues = self.repo.get_issues(since=last_run)
            else:
                self.debug('Getting ALL issues')
                issues = self.repo.get_issues()

            for issue in issues:
                self.icount += 1
                if self.start_at and issue.number > self.start_at:
                    continue
                if self.is_pr(issue):
                    continue
                self.issue = IssueWrapper(repo=self.repo, issue=issue, cachedir=self.cachedir)
                self.issue.get_events()
                self.issue.get_comments()
                action_res = self.process()
                if action_res:
                    while action_res['REDO']:
                        issue = self.repo.get_issue(int(issue.number))
                        self.issue = IssueWrapper(repo=self.repo, issue=issue, cachedir=self.cachedir)
                        self.issue.get_events()
                        self.issue.get_comments()
                        action_res = self.process()
                        if not action_res:
                            action_res = {'REDO': False}

            # save this run time
            with open(last_run_file, 'wb') as f:
                pickle.dump(now, f)


    def print_comment_list(self):
        """Print comment creators and the commands they used"""
        for x in self.issue.current_comments:
            command = None
            if x.user.login != 'ansibot':
                command = [y for y in self.VALID_COMMANDS if y in x.body \
                           and not '!' + y in x.body]
                command = ', '.join(command)
            else:
                # What template did ansibot use?
                try:
                    command = x.body.split('\n')[-1].split()[-2]
                except:
                    pass

            if command:
                print("\t%s %s (%s)" % (x.created_at.isoformat(),
                      x.user.login, command))
            else:
                print("\t%s %s" % (x.created_at.isoformat(), x.user.login))

    @ratecheck()
    def process(self, usecache=True):
        """Processes the Issue"""

        # basic processing
        self._process()

        # who maintains this?
        maintainers = []

        if self.meta.get('component_valid', False):
            correct_repo = self.match.get('repository')
            if correct_repo != self.github_repo:
                self.meta['correct_repo'] = False
            else:
                self.meta['correct_repo'] = True
                maintainers = self.get_module_maintainers()
                if not maintainers:
                    #issue_module_no_maintainer
                    #import epdb; epdb.st()
                    pass

        '''
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
        '''

        ###########################################################
        #                   Enumerate Actions
        ###########################################################

        self.keep_current_main_labels()
        self.debug(msg='desired_comments: %s' % self.issue.desired_comments)

        self.process_history(usecache=usecache)
        self.debug(msg='desired_comments: %s' % self.issue.desired_comments)
        
        self.create_actions()
        self.debug(msg='desired_comments: %s' % self.issue.desired_comments)

        print("Module: %s" % self.module)
        if self.match:
            print("MModule: %s" % self.match['name'])
        else:
            print("MModule: %s" % self.match)
        print("Maintainer(s): %s" \
            % ', '.join(self.get_module_maintainers(expand=False)))
        print("Submitter: %s" % self.issue.get_submitter())
        print("Total Comments: %s" % len(self.issue.current_comments))
        self.print_comment_list()
        print("Current Labels: %s" % ', '.join(sorted(self.issue.current_labels)))

        # invoke the wizard
        import pprint; pprint.pprint(self.actions)
        action_meta = self.apply_actions()
        return action_meta


    def create_actions(self):
        """Create actions from the desired label/unlabel/comment actions"""

        # do nothing for bot_skip
        if self.meta['bot_skip']:
            return

        if 'bot_broken' in self.issue.desired_labels:
            # If the bot is broken, do nothing other than set the broken label
            self.actions['comments'] = []
            self.actions['newlabel'] = []
            self.actions['unlabel'] = []
            self.actions['close'] = False
            if not 'bot_broken' in self.issue.current_labels:
                self.actions['newlabel'] = ['bot_broken']                
            return

        # add the version labels
        self.create_label_version_actions()

        if self.issue.desired_state != self.issue.instance.state:
            if self.issue.desired_state == 'closed':
                # close the issue ...
                self.actions['close'] = True

                # We only want up to 1 comment when an issue is closed
                if 'issue_closure' in self.issue.desired_comments:
                    self.issue.desired_comments = ['issue_closure']
                elif 'issue_deprecated_module' in self.issue.desired_comments:
                    self.issue.desired_comments = ['issue_deprecated_module']
                else:
                    self.issue.desired_comments = []

                if self.issue.desired_comments:
                    comment = self.render_comment(
                                boilerplate=self.issue.desired_comments[0]
                              )
                    self.actions['comments'].append(comment)
                return

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
                resolved_desired_labels.append(desired_label)
                if desired_label not in self.issue.get_current_labels():
                    self.actions['newlabel'].append(desired_label)
                    '''
                    if os.path.exists("templates/" + 'issue_' + desired_label + ".j2"):
                        self.issue.add_desired_comment('issue_' + desired_label)
                    '''

        for current_label in self.issue.get_current_labels():
            if current_label in self.IGNORE_LABELS:
                continue
            if current_label not in resolved_desired_labels:
                self.actions['unlabel'].append(current_label)

        # should only make one comment at a time
        if len(self.issue.desired_comments) > 1:
            if 'issue_wrong_repo' in self.issue.desired_comments:
                self.issue.desired_comments = ['issue_wrong_repo']
            elif 'issue_invalid_module' in self.issue.desired_comments:
                self.issue.desired_comments = ['issue_invalid_module']
            elif 'issue_module_no_maintainer' in self.issue.desired_comments:
                self.issue.desired_comments = ['issue_module_no_maintainer']
            elif 'issue_needs_info' in self.issue.desired_comments \
                and 'needs_info' in self.issue.desired_labels:
                self.issue.desired_comments = ['issue_needs_info']
            elif 'issue_needs_info' in self.issue.desired_comments \
                and 'needs_info' not in self.issue.desired_labels:
                self.issue.desired_comments.remove('issue_needs_info')
            else:
                import epdb; epdb.st()        

        # Do not comment needs_info if it's not a label
        if 'issue_needs_info' in self.issue.desired_comments \
            and not 'needs_info' in self.issue.desired_labels:
            self.issue.desired_comments.remove('issue_needs_info')    

        # render the comments
        for boilerplate in self.issue.desired_comments:
            comment = self.render_comment(boilerplate=boilerplate)
            self.debug(msg=boilerplate)
            self.actions['comments'].append(comment)

        # do not re-comment
        for idx,comment in enumerate(self.actions['comments']):
            if self.issue.current_comments:
                if self.issue.current_comments[-1].body == comment:
                    self.debug(msg="Removing repeat comment from actions")
                    self.actions['comments'].remove(comment)
        #import epdb; epdb.st()


    def create_label_version_actions(self):
        if not self.ansible_label_version:
            return
        expected = 'affects_%s' % self.ansible_label_version
        if expected not in self.valid_labels:
            print("NEED NEW LABEL: %s" % expected)
            import epdb; epdb.st()

        candidates = [x for x in self.issue.current_labels]
        candidates = [x for x in candidates if x.startswith('affects_')]
        candidates = [x for x in candidates if x != expected]
        if len(candidates) > 0:
            #for cand in candidates:
            #    self.issue.pop_desired_label(name=cand)
            #return
            pass
        else:
            if expected not in self.issue.current_labels \
                or expected not in self.issue.desired_labels:
                self.issue.add_desired_label(name=expected)
        #import epdb; epdb.st()


    def create_commment_actions(self):
        '''Render desired comment templates'''

        # should only make one comment at a time
        if len(self.issue.desired_comments) > 1:
            if 'issue_wrong_repo' in self.issue.desired_comments:
                self.issue.desired_comments = ['issue_wrong_repo']
            elif 'issue_invalid_module' in self.issue.desired_comments:
                self.issue.desired_comments = ['issue_invalid_module']
            elif 'issue_module_no_maintainer' in self.issue.desired_comments:
                self.issue.desired_comments = ['issue_module_no_maintainer']
            elif 'issue_needs_info' in self.issue.desired_comments \
                and 'needs_info' in self.issue.desired_labels:
                self.issue.desired_comments = ['issue_needs_info']
            elif 'issue_needs_info' in self.issue.desired_comments \
                and 'needs_info' not in self.issue.desired_labels:
                self.issue.desired_comments.remove('issue_needs_info')
            else:
                import epdb; epdb.st()        

        # Do not comment needs_info if it's not a label
        if 'issue_needs_info' in self.issue.desired_comments \
            and not 'needs_info' in self.issue.desired_labels:
            self.issue.desired_comments.remove('issue_needs_info')    

        # render the comments
        for boilerplate in self.issue.desired_comments:
            comment = self.render_comment(boilerplate=boilerplate)
            self.debug(msg=boilerplate)
            self.actions['comments'].append(comment)

        # do not re-comment
        for idx,comment in enumerate(self.actions['comments']):
            if self.issue.current_comments:
                if self.issue.current_comments[-1].body == comment:
                    self.debug(msg="Removing repeat comment from actions")
                    self.actions['comments'].remove(comment)


    def create_label_actions(self):
        """Create actions from the desired label/unlabel/comment actions"""

        if 'bot_broken' in self.issue.desired_labels:
            # If the bot is broken, do nothing other than set the broken label
            self.actions['comments'] = []
            self.actions['newlabel'] = []
            self.actions['unlabel'] = []
            self.actions['close'] = False
            if not 'bot_broken' in self.issue.current_labels:
                self.actions['newlabel'] = ['bot_broken']                
            return

        if self.meta['bot_skip']:
            return

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
                resolved_desired_labels.append(desired_label)
                if desired_label not in self.issue.get_current_labels():
                    self.actions['newlabel'].append(desired_label)

        for current_label in self.issue.get_current_labels():
            if current_label in self.IGNORE_LABELS:
                continue
            if current_label not in resolved_desired_labels:
                self.actions['unlabel'].append(current_label)



    def process_history(self, usecache=True):
        '''Steps through all known meta about the issue and decides what to do'''

        self.meta.update(self.get_facts())
        self.add_desired_labels_by_issue_type()
        self.add_desired_labels_by_ansible_version()
        self.add_desired_labels_by_namespace()

        #################################################
        # FINAL LOGIC LOOP
        #################################################

        if self.meta['bot_broken']:
            self.debug(msg='broken bot stanza')
            self.issue.add_desired_label('bot_broken')

        elif self.meta['bot_skip']:

            self.debug(msg='bot skip stanza')

            # clear out all actions and do nothing
            for k,v in self.actions.iteritems():
                if type(v) == list:
                    self.actions[k] = []
            self.actions['close'] = False

        elif self.meta['bot_spam']:

            self.debug(msg='bot spam stanza')

            # clear out all actions and do nothing
            for k,v in self.actions.iteritems():
                if type(v) == list:
                    self.actions[k] = []
            self.actions['close'] = False

            # do we mark this somehow?
            self.issue.add_desired_label('bot_broken')


        elif self.match and self.match.get('deprecated', False) \
            and 'feature_idea' in self.issue.desired_labels:

            self.debug(msg='deprecated module stanza')

            # Make the deprecated comment
            self.issue.desired_comments = ['issue_deprecated_module']

            # Close the issue ...
            self.issue.set_desired_state('closed')

        elif not self.meta['maintainers_known'] and self.meta['valid_module']:

            self.debug(msg='unknown maintainer stanza') 
            self.issue.desired_comments = ['issue_module_no_maintainer']

        elif self.meta['maintainer_closure']:

            self.debug(msg='maintainer closure stanza')

            # Need to close the issue ...
            self.issue.set_desired_state('closed')

        elif self.meta['new_module_request']:

            self.debug(msg='new module request stanza')
            self.issue.desired_comments = []
            for label in self.issue.current_labels:
                if not label in self.issue.desired_labels:
                    self.issue.desired_labels.append(label)

        elif not self.meta['correct_repo']:

            self.debug(msg='wrong repo stanza')
            self.issue.desired_comments = ['issue_wrong_repo']
            self.actions['close'] = True

        elif not self.meta['valid_module'] and \
            not self.meta['maintainer_command_needsinfo']:

            self.debug(msg='invalid module stanza')

            self.issue.add_desired_label('needs_info')
            if 'issue_invalid_module' not in self.issue.current_bot_comments \
                and not 'issue_needs_info' in self.issue.current_bot_comments:
                self.issue.desired_comments = ['issue_invalid_module']

        elif not self.meta['notification_maintainers'] and \
            not self.meta['maintainer_command_needsinfo']:

            self.debug(msg='no maintainer stanza')

            self.issue.add_desired_label('waiting_on_maintainer')
            self.issue.add_desired_comment("issue_module_no_maintainer")

        elif self.meta['maintainer_command'] == 'needs_contributor':

            # maintainer can't or won't fix this, but would like someone else to
            self.debug(msg='maintainer needs contributor stanza')
            self.issue.add_desired_label('waiting_on_contributor')

        elif self.meta['maintainer_waiting_on']:

            self.debug(msg='maintainer wait stanza')

            self.issue.add_desired_label('waiting_on_maintainer')
            if len(self.issue.current_comments) == 0:
                # new issue
                if self.meta['issue_type']:
                    if self.meta['submitter'] not in self.meta['notification_maintainers']:
                        # ping the maintainer
                        self.issue.add_desired_comment('issue_new')
                    else:
                        # do not send intial ping to maintainer if also submitter
                        if 'issue_new' in self.issue.desired_comments:
                            self.issue.desired_comments.remove('issue_new')
            else:
                # old issue -- renotify
                if not self.match['deprecated'] and self.meta['notification_maintainers']:
                    if self.meta['maintainer_to_ping']:
                        self.issue.add_desired_comment("issue_notify_maintainer")
                    elif self.meta['maintainer_to_reping']:
                        self.issue.add_desired_comment("issue_renotify_maintainer")

        elif self.meta['submitter_waiting_on']:

            self.debug(msg='submitter wait stanza')

            if 'waiting_on_maintainer' in self.issue.desired_labels:
                self.issue.desired_labels.remove('waiting_on_maintainer')

            if (self.meta['needsinfo_add'] or self.meta['missing_sections']) \
                or (not self.meta['needsinfo_remove'] and self.meta['missing_sections']) \
                or (self.meta['needsinfo_add'] and not self.meta['missing_sections']): 


                #import epdb; epdb.st()
                self.issue.add_desired_label('needs_info')
                if len(self.issue.current_comments) == 0 or \
                    not self.meta['maintainer_commented']:

                    if self.issue.current_bot_comments:
                        if 'issue_needs_info' not in self.issue.current_bot_comments:
                            self.issue.add_desired_comment("issue_needs_info")
                    else:
                        self.issue.add_desired_comment("issue_needs_info")

                # needs_info: warn if stale, close if expired
                elif self.meta['needsinfo_expired']:
                    self.issue.add_desired_comment("issue_closure")
                    self.issue.set_desired_state('closed')
                elif self.meta['needsinfo_stale'] \
                    and (self.meta['submitter_to_ping'] or self.meta['submitter_to_reping']):
                    self.issue.add_desired_comment("issue_pending_closure")


    def get_history_facts(self, usecache=True):
        return self.get_facts(usecache=usecache)

    def get_facts(self, usecache=True):
        '''Only used by the ansible/ansible triager at the moment'''
        hfacts = {}
        today = self.get_current_time()
        
        self.history = HistoryWrapper(
                        self.issue, 
                        usecache=usecache, 
                        cachedir=self.cachedir
                       )

        # what was the last commment?
        bot_broken = False
        if self.issue.current_comments:
            for comment in self.issue.current_comments:
                if 'bot_broken' in comment.body:
                    bot_broken = True

        # did someone from ansible want this issue skipped?
        bot_skip = False
        if self.issue.current_comments:
            for comment in self.issue.current_comments:
                if 'bot_skip' in comment.body and comment.user.login in self.ansible_members:
                    bot_skip = True


        # Has the bot been overzealous with comments?
        hfacts['bot_spam'] = False
        bcg = self.history.get_user_comments_groupby('ansibot', groupby='w')
        for k,v in bcg.iteritems():
            if v >= self.MAX_BOT_COMMENTS_PER_WEEK:
                hfacts['bot_spam'] = True

        # Is this a new module?
        hfacts['new_module_request'] = False
        if 'feature_idea' in self.issue.desired_labels:
            if self.template_data['component name'] == 'new':
                hfacts['new_module_request'] = True

        # who made this and when did they last comment?
        submitter = self.issue.get_submitter()
        submitter_last_commented = self.history.last_commented_at(submitter)
        if not submitter_last_commented:
            submitter_last_commented = self.issue.instance.created_at
            #import epdb; epdb.st()
        submitter_last_comment = self.history.last_comment(submitter)
        submitter_last_notified = self.history.last_notified(submitter)

        # what did they not provide?
        missing_sections = self.issue.get_missing_sections()

        # Is this a valid module?
        if self.match:
            self.meta['valid_module'] = True
        else:
            self.meta['valid_module'] = False

        # Filed in the right place?
        if self.meta['valid_module']:
            if self.match['repository'] != self.github_repo:
                hfacts['correct_repo'] = False
            else:
                hfacts['correct_repo'] = True
        else:
            hfacts['correct_repo'] = True

        # DEBUG + FIXME - speeds up bulk triage
        if 'component name' in missing_sections \
            and (self.match or self.github_repo == 'ansible'):
            missing_sections.remove('component name')
        #import epdb; epdb.st()

        # Who are the maintainers?
        maintainers = [x for x in self.get_module_maintainers()]
        #hfacts['maintainers'] = maintainers
        #import epdb; epdb.st()

        # Set a fact to indicate that we know the maintainer
        self.meta['maintainers_known'] = False
        if maintainers:
            self.meta['maintainers_known'] = True

        if 'ansible' in maintainers:
            maintainers.remove('ansible')
        maintainers.extend(self.ansible_members)
        if 'ansibot' in maintainers:
            maintainers.remove('ansibot')
        if submitter in maintainers:
            maintainers.remove(submitter)
        maintainers = sorted(set(maintainers))

        # Has maintainer been notified? When?
        notification_maintainers = [x for x in self.get_module_maintainers()]
        if 'ansible' in notification_maintainers:
            notification_maintainers.extend(self.ansible_members)
        if 'ansibot' in notification_maintainers:
            notification_maintainers.remove('ansibot')
        hfacts['notification_maintainers'] = notification_maintainers
        maintainer_last_notified = self.history.\
                    last_notified(notification_maintainers)

        # Has maintainer viewed issue?
        maintainer_viewed = self.history.has_viewed(maintainers)
        maintainer_last_viewed = self.history.last_viewed_at(maintainers)
        #import epdb; epdb.st()

        # Has maintainer been mentioned?
        maintainer_mentioned = self.history.is_mentioned(maintainers)

        # Has maintainer viewed issue?
        maintainer_viewed = self.history.has_viewed(maintainers)

        # Has the maintainer ever responded?
        maintainer_commented = self.history.has_commented(maintainers)
        maintainer_last_commented = self.history.last_commented_at(maintainers)
        maintainer_last_comment = self.history.last_comment(maintainers)
        maintainer_comments = self.history.get_user_comments(maintainers)
        #import epdb; epdb.st()

        # Was the maintainer the last commentor?
        last_commentor_ismaintainer = False
        last_commentor_issubmitter = False
        last_commentor = self.history.last_commentor()
        if last_commentor in maintainers and last_commentor != self.github_user:
            last_commentor_ismaintainer = True
        elif last_commentor == submitter:
            last_commentor_issubmitter = True

        # Did the maintainer issue a command?
        maintainer_commands = self.history.get_commands(maintainers, 
                                                        self.VALID_COMMANDS)

        # Keep all commands
        hfacts['maintainer_commands'] = maintainer_commands
        # Set a bit for the last command given
        if hfacts['maintainer_commands']:
            hfacts['maintainer_command'] = hfacts['maintainer_commands'][-1]
        else:
            hfacts['maintainer_command'] = None

        # Is the last command a closure command?
        if hfacts['maintainer_command'] in self.CLOSURE_COMMANDS:
            hfacts['maintainer_closure'] = True
        else:
            hfacts['maintainer_closure'] = False

        # handle resolved_by_pr ...
        if 'resolved_by_pr' in maintainer_commands:
            pr_number = extract_pr_number_from_comment(maintainer_last_comment)
            hfacts['resolved_by_pr'] = {
                'number': pr_number,
                'merged': self.is_pr_merged(pr_number),
            }            
            if not hfacts['resolved_by_pr']['merged']:
                hfacts['maintainer_closure'] = False

        # needs_info toggles
        ni_commands = [x for x in maintainer_commands if 'needs_info' in x]

        # Has the maintainer ever subscribed?
        maintainer_subscribed = self.history.has_subscribed(maintainers)
        
        # Was it ever needs_info?
        was_needs_info = self.history.was_labeled(label='needs_info')
        needsinfo_last_applied = self.history.label_last_applied('needs_info')
        needsinfo_last_removed = self.history.label_last_removed('needs_info')

        # Still needs_info?
        needsinfo_add = False
        needsinfo_remove = False
        
        if 'needs_info' in self.issue.current_labels:
            if not needsinfo_last_applied or not submitter_last_commented:
                import epdb; epdb.st()
            if submitter_last_commented > needsinfo_last_applied:
                needsinfo_add = False
                needsinfo_remove = True

        #if 'needs_info' in maintainer_commands and maintainer_last_commented:
        if ni_commands and maintainer_last_commented:
            if ni_commands[-1] == 'needs_info':            
                #import epdb; epdb.st()
                if submitter_last_commented and maintainer_last_commented:
                    if submitter_last_commented > maintainer_last_commented:
                        needsinfo_add = False
                        needsinfo_remove = True
                else:
                    needsinfo_add = True
                    needsinfo_remove = False
            else:
                needsinfo_add = False
                needsinfo_remove = True

        # Save existing needs_info if not time to remove ...        
        if 'needs_info' in self.issue.current_labels \
            and not needsinfo_add \
            and not needsinfo_remove:
            needsinfo_add = True

        if ni_commands and maintainer_last_commented:
            if maintainer_last_commented > submitter_last_commented:
                if ni_commands[-1] == 'needs_info':
                    needsinfo_add = True
                    needsinfo_remove = False
                else:
                    needsinfo_add = False
                    needsinfo_remove = True
        #import epdb; epdb.st()

        # Is needs_info stale or expired?
        needsinfo_age = None
        needsinfo_stale = False
        needsinfo_expired = False
        if 'needs_info' in self.issue.current_labels: 
            time_delta = today - needsinfo_last_applied
            needsinfo_age = time_delta.days
            if needsinfo_age > self.RENOTIFY_INTERVAL:
                needsinfo_stale = True
            if needsinfo_age > self.RENOTIFY_EXPIRE:
                needsinfo_expired = True

        # Should we be in waiting_on_maintainer mode?
        maintainer_waiting_on = False
        if (needsinfo_remove or not needsinfo_add) \
            or not was_needs_info \
            and not missing_sections:
            maintainer_waiting_on = True

        # Should we [re]notify the submitter?
        submitter_waiting_on = False
        submitter_to_ping = False
        submitter_to_reping = False
        if not maintainer_waiting_on:
            submitter_waiting_on = True

        if missing_sections:
            submitter_waiting_on = True
            maintainer_waiting_on = False

        # use [!]needs_info to set final state
        if ni_commands:
            if ni_commands[-1] == '!needs_info':
                submitter_waiting_on = False
                maintainer_waiting_on = True
            elif ni_commands[-1] == 'needs_info':
                submitter_waiting_on = True
                maintainer_waiting_on = False

        # Time to [re]ping maintainer?
        maintainer_to_ping = False
        maintainer_to_reping = False
        if maintainer_waiting_on:

            # if feature idea, extend the notification interval
            interval = self.RENOTIFY_INTERVAL
            if self.meta.get('issue_type', None) == 'feature idea':
                interval = self.FEATURE_RENOTIFY_INTERVAL

            if maintainer_viewed and not maintainer_last_notified:
                time_delta = today - maintainer_last_viewed
                view_age = time_delta.days
                if view_age > interval:
                    maintainer_to_reping = True
            elif maintainer_last_notified:
                time_delta = today - maintainer_last_notified
                ping_age = time_delta.days
                if ping_age > interval:
                    maintainer_to_reping = True
            else:
                maintainer_to_ping = True

        # Time to [re]ping the submitter?
        if submitter_waiting_on:
            if submitter_last_notified:
                time_delta = today - submitter_last_notified
                notification_age = time_delta.days
                if notification_age > self.RENOTIFY_INTERVAL:
                    submitter_to_reping = True
                else:
                    submitter_to_reping = False
                submitter_to_ping = False
            else:
                submitter_to_ping = True
                submitter_to_reping = False

        hfacts['bot_broken'] = bot_broken
        hfacts['bot_skip'] = bot_skip
        hfacts['missing_sections'] = missing_sections
        hfacts['was_needsinfo'] = was_needs_info
        hfacts['needsinfo_age'] = needsinfo_age
        hfacts['needsinfo_stale'] = needsinfo_stale
        hfacts['needsinfo_expired'] = needsinfo_expired
        hfacts['needsinfo_add'] = needsinfo_add
        hfacts['needsinfo_remove'] = needsinfo_remove
        hfacts['notification_maintainers'] = self.get_module_maintainers() or 'ansible'
        hfacts['maintainer_last_notified'] = maintainer_last_notified
        hfacts['maintainer_commented'] = maintainer_commented
        hfacts['maintainer_viewed'] = maintainer_viewed
        hfacts['maintainer_subscribed'] = maintainer_subscribed
        hfacts['maintainer_command_needsinfo'] = 'needs_info' in maintainer_commands
        hfacts['maintainer_command_not_needsinfo'] = '!needs_info' in maintainer_commands
        hfacts['maintainer_waiting_on'] = maintainer_waiting_on
        hfacts['maintainer_to_ping'] = maintainer_to_ping
        hfacts['maintainer_to_reping'] = maintainer_to_reping
        hfacts['submitter'] = submitter
        hfacts['submitter_waiting_on'] = submitter_waiting_on
        hfacts['submitter_to_ping'] = submitter_to_ping
        hfacts['submitter_to_reping'] = submitter_to_reping

        hfacts['last_commentor_ismaintainer'] = last_commentor_ismaintainer
        hfacts['last_commentor_issubmitter'] = last_commentor_issubmitter
        hfacts['last_commentor'] = last_commentor

        return hfacts
