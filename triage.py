#!/usr/bin/env python
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

import argparse
import os
import sys
import time
from datetime import datetime

# remember to pip install PyGithub, kids!
from github import Github

from jinja2 import Environment, FileSystemLoader

from lib.triagers.triagev3 import TriageV3
from lib.triagers.issuetriager import TriageIssues
from lib.triagers.ansible_ansible_issuetriager import AnsibleAnsibleTriageIssues
from lib.triagers.ansible_ansible_pulltriager import AnsibleAnsibleTriagePullRequests

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
        'shipit_owner_pr',
        'shipit_by_ansible_member'
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
    'cloud/openstack': "openstack",
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

# Static labels, may be added manually
IGNORE_LABELS = [
    "feature_pull_request",
    "bugfix_pull_request",
    "in progress",
    "docs_pull_request",
    "needs_rebase",
    "easyfix",
    "pending_action",
    "gce",
    "python3",
    "bot_broken",
    "owner_pr",
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


class PullRequest:

    def __init__(self, repo, pr_number=None, pr=None):
        self.repo = repo

        if not pr:
            self.instance = self.repo.get_pull(pr_number)
        else:
            self.instance = pr

        self.pr_number = self.instance.number

        self.issue = None
        self.pr_filenames = []
        self.current_pr_labels = []
        self.desired_pr_labels = []

        self.current_comments = []
        self.desired_comments = []

    def get_pr_filenames(self):
        """Returns all files related to this PR"""
        if not self.pr_filenames:
            for pr_file in self.instance.get_files():
                self.pr_filenames.append(pr_file.filename)
        return self.pr_filenames

    def get_last_commit(self):
        """Returns last commit"""
        commits = self.instance.get_commits().reversed
        for commit in commits:
            return commit

    def get_build_status(self):
        """Return build status object"""
        last_commit = self.get_last_commit()
        if last_commit:
            build_statuses = last_commit.get_statuses()
            for build_status in build_statuses:
                return build_status
        return None

    def get_pr_submitter(self):
        """Returns the PR submitter"""
        return self.instance.user.login

    def pr_contains_new_file(self):
        """Return True if PR contains new files"""
        for pr_file in self.instance.get_files():
            if pr_file.status == "added":
                return True
        return False

    def is_labeled_for_interaction(self):
        """Returns True if PR is labeled for interaction"""
        for current_pr_label in self.get_current_labels():
            if current_pr_label in MANUAL_INTERACTION_LABELS:
                return True
        return False

    def is_mergeable(self):
        """Return True if PR is mergeable"""
        while self.instance.mergeable_state == "unknown":
            print("Mergeable state is unknown, trying again...")
            time.sleep(1)
            self.instance = self.repo.get_pull(self.pr_number)
            time.sleep(1)
        return self.instance.mergeable_state != "dirty"

    def is_a_wip(self):
        """Return True if PR start with [WIP] in title"""
        return (self.instance.title.startswith("[WIP]")
                or self.instance.title.startswith("WIP:")
                or self.instance.title.startswith("WIP "))

    def get_base_ref(self):
        """Returns base ref of PR"""
        return self.instance.base.ref

    def get_issue(self):
        """Gets the issue from the GitHub API"""
        if not self.issue:
            self.issue = self.repo.get_issue(self.pr_number)
        return self.issue

    def get_current_labels(self):
        """Pull the list of labels on this PR and shove them into
        pr_labels.
        """
        if not self.current_pr_labels:
            labels = self.get_issue().labels
            for label in labels:
                self.current_pr_labels.append(label.name)
        return self.current_pr_labels

    def get_comments(self):
        """Returns all current comments of the PR"""
        if not self.current_comments:
            self.current_comments = self.instance.get_issue_comments().reversed
        return self.current_comments

    def resolve_desired_pr_labels(self, desired_pr_label):
        """Resolves boilerplate the key labels to labels using an
        alias dict
        """
        for resolved_desired_pr_label, aliases in ALIAS_LABELS.iteritems():
            if desired_pr_label in aliases:
                return resolved_desired_pr_label
        return desired_pr_label

    def process_mutually_exclusive_labels(self, name=None):
        resolved_name = self.resolve_desired_pr_labels(name)
        if resolved_name in MUTUALLY_EXCLUSIVE_LABELS:
            for label in self.desired_pr_labels:
                resolved_label = self.resolve_desired_pr_labels(label)
                if resolved_label in MUTUALLY_EXCLUSIVE_LABELS:
                    self.desired_pr_labels.remove(label)

    def add_desired_label(self, name=None):
        """Adds a label to the desired labels list"""
        if name and name not in self.desired_pr_labels:
            self.process_mutually_exclusive_labels(name=name)
            self.desired_pr_labels.append(name)

    def add_desired_comment(self, boilerplate=None):
        """Adds a boilerplate key to the desired comments list"""
        if boilerplate and boilerplate not in self.desired_comments:
            self.desired_comments.append(boilerplate)

    def add_label(self, label=None):
        """Adds a label to the PR using the GitHub API"""
        self.get_issue().add_to_labels(label)

    def remove_label(self, label=None):
        """Removes a label from the PR using the GitHub API"""
        self.get_issue().remove_from_labels(label)

    def add_comment(self, comment=None):
        """ Adds a comment to the PR using the GitHub API"""
        self.get_issue().create_comment(comment)


class TriagePullRequests:
    def __init__(self, verbose=None, github_user=None, github_pass=None,
                 github_token=None, github_repo=None, pr_number=None,
                 start_at_pr=None, always_pause=False, force=False, dry_run=False):
        self.verbose = verbose
        self.github_user = github_user
        self.github_pass = github_pass
        self.github_token = github_token
        self.github_repo = github_repo
        self.pr_number = pr_number
        self.start_at_pr = start_at_pr
        self.always_pause = always_pause
        self.force = force
        self.dry_run = dry_run

        self.pull_request = None
        self.maintainers = {}
        self.module_maintainers = []
        self.actions = {
            'newlabel': [],
            'unlabel':  [],
            'comments': [],
        }

    def _connect(self):
        """Connects to GitHub's API"""
        return Github(login_or_token=self.github_token or self.github_user,
                      password=self.github_pass)

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
        """Returns the dict of maintainers using the key as owner namespace"""
        if self.module_maintainers:
            return self.module_maintainers

        for owner_space, maintainers in self._get_maintainers().iteritems():
            for filename in self.pull_request.get_pr_filenames():
                if owner_space in filename:
                    for maintainer in maintainers:
                        if maintainer not in self.module_maintainers:
                            self.module_maintainers.extend(maintainers)
        return self.module_maintainers

    def keep_current_main_labels(self):
        current_labels = self.pull_request.get_current_labels()
        for current_label in current_labels:
            if current_label in MUTUALLY_EXCLUSIVE_LABELS:
                self.pull_request.add_desired_label(name=current_label)

    def is_ansible_member(self, login):
        user = self._connect().get_user(login)
        return self._connect().get_organization("ansible").has_in_members(user)

    def add_desired_labels_for_not_mergeable(self):
        """Adds labels for not mergeable conditions"""
        if not self.pull_request.is_mergeable():
            self.debug(msg="PR is not mergeable")
            self.pull_request.add_desired_label(name="needs_revision_not_mergeable")
        else:
            self.debug(msg="PR is mergeable")

    def add_desired_labels_by_namespace(self):
        """Adds labels regarding module namespaces"""
        for pr_filename in self.pull_request.get_pr_filenames():
            namespace = pr_filename.split('/')[0]
            for key, value in MODULE_NAMESPACE_LABELS.iteritems():
                if key == namespace:
                    self.pull_request.add_desired_label(value)

    def add_labels_by_issue_type(self):
        """Adds labels by issue type"""
        body = self.pull_request.instance.body

        if not body:
            self.debug(msg="PR has no description")
            return

        if ("New Module Pull Request" in body
            or "new_plugin" in self.pull_request.desired_pr_labels):
            self.debug(msg="New Module Pull Request")
            return

        if "Bugfix Pull Request" in body:
            self.debug(msg="Bugfix Pull Request")
            self.pull_request.add_desired_label(name="bugfix_pull_request")

        if "Docs Pull Request" in body:
            self.debug(msg="Docs Pull Request")
            self.pull_request.add_desired_label(name="docs_pull_request")

        if "Feature Pull Request" in body:
            self.debug(msg="Feature Pull Request")
            self.pull_request.add_desired_label(name="feature_pull_request")

    def add_desired_labels_by_gitref(self):
        """Adds labels regarding gitref"""
        if "stable" in self.pull_request.get_base_ref():
            self.debug(msg="backport requested")
            self.pull_request.add_desired_label(name="core_review")
            self.pull_request.add_desired_label(name="backport")

    def add_desired_label_by_build_state(self):
        """Adds label regarding build state of last commit"""
        build_status = self.pull_request.get_build_status()
        if build_status:
            self.debug(msg="Build state is %s" % build_status.state)
            if build_status.state == "failure":
                self.pull_request.add_desired_label(name="needs_revision")
        else:
            self.debug(msg="No build state")

    def add_desired_labels_by_maintainers(self):
        """Adds labels regarding maintainer infos"""
        module_maintainers = self.get_module_maintainers()
        pr_contains_new_file = self.pull_request.pr_contains_new_file()

        if pr_contains_new_file:
            self.debug(msg="plugin is new")
            self.pull_request.add_desired_label(name="new_plugin")

        if "shipit" in self.pull_request.get_current_labels():
            self.debug(msg="shipit labeled, skipping maintainer")
            return

        if "needs_info" in self.pull_request.get_current_labels():
            self.debug(msg="needs info labeled, skipping maintainer")
            return

        if "needs_revision" in self.pull_request.get_current_labels():
            self.debug(msg="needs revision labeled, skipping maintainer")
            return

        if "core_review" in self.pull_request.get_current_labels():
            self.debug(msg="Forced core review, skipping maintainer")
            return

        if "ansible" in module_maintainers:
            self.debug(msg="ansible in module maintainers")
            self.pull_request.add_desired_label(name="core_review_existing")
            return

        if (self.pull_request.get_pr_submitter() in module_maintainers
            or self.pull_request.get_pr_submitter().lower() in module_maintainers):
            self.debug(msg="plugin by owner, community review as owner_pr")
            self.pull_request.add_desired_label(name="owner_pr")
            self.pull_request.add_desired_label(name="community_review_owner_pr")
            return

        if not module_maintainers and not pr_contains_new_file:
            self.debug(msg="unknown maintainer.")
            self.pull_request.add_desired_label(name="pending_maintainer_unknown")
            return

        if not module_maintainers and pr_contains_new_file:
            self.debug(msg="New plugin, no module maintainer yet")
            self.pull_request.add_desired_label(name="community_review_new")
        else:
            self.debug(msg="existing plugin modified, module maintainer "
                           "should review")
            self.pull_request.add_desired_label(
                name="community_review_existing"
            )

    def process_comments(self):
        """ Processes PR comments for matching criteria for adding labels"""
        module_maintainers = self.get_module_maintainers()
        comments = self.pull_request.get_comments()

        self.debug(msg="--- START Processing Comments:")

        last_commit_date = self.pull_request.get_build_status().updated_at

        for comment in comments:

            # Is the last useful comment from a bot user?  Then we've got a
            # potential timeout case. Let's explore!
            if comment.user.login in BOTLIST:

                self.debug(msg="%s is in botlist: " % comment.user.login)

                if last_commit_date > comment.updated_at:
                    self.debug(msg="Newer commits then last comment of %s, continuing" %
                               comment.user.login)
                    continue

                today = datetime.today()
                time_delta = today - comment.created_at
                comment_days_old = time_delta.days

                self.debug(msg="Days since last bot comment: %s" %
                           comment_days_old)

                if comment_days_old > 14:
                    pr_labels = self.pull_request.desired_pr_labels

                    if "core_review" in pr_labels:
                        self.debug(msg="has core_review")
                        break

                    if "pending" not in comment.body:
                        if self.pull_request.is_labeled_for_interaction():
                            self.pull_request.add_desired_comment(
                                boilerplate="submitter_first_warning"
                            )
                            self.debug(msg="submitter_first_warning")
                            break
                        if ("community_review" in pr_labels and not
                                self.pull_request.pr_contains_new_file()):
                            self.debug(msg="maintainer_first_warning")
                            self.pull_request.add_desired_comment(
                                boilerplate="maintainer_first_warning"
                            )
                            break

                    # pending in comment.body
                    else:
                        if self.pull_request.is_labeled_for_interaction():
                            self.debug(msg="submitter_second_warning")
                            self.pull_request.add_desired_comment(
                                boilerplate="submitter_second_warning"
                            )
                            self.pull_request.add_desired_label(
                                name="pending_action"
                            )
                            break
                        if ("community_review" in pr_labels and
                                "new_plugin" not in pr_labels):
                            self.debug(msg="maintainer_second_warning")
                            self.pull_request.add_desired_comment(
                                boilerplate="maintainer_second_warning"
                            )
                            self.pull_request.add_desired_label(
                                name="pending_action"
                            )
                            break
                self.debug(msg="STATUS: no useful state change since last pass"
                           "( %s )" % comment.user.login)
                break

            if (comment.user.login in module_maintainers
                or comment.user.login.lower() in module_maintainers):
                self.debug(msg="%s is module maintainer commented on %s." %
                           (comment.user.login, comment.created_at))

                if "bot_broken" in comment.body:
                    self.debug(msg="...said bot_broken!")
                    self.pull_request.add_desired_label(name="bot_broken")

                if ("shipit" in comment.body or "+1" in comment.body
                    or "LGTM" in comment.body):
                    self.debug(msg="...said shipit!")
                    # if maintainer was the submitter:
                    if comment.user.login == self.pull_request.get_pr_submitter():
                        self.pull_request.add_desired_label(name="shipit_owner_pr")
                    elif last_commit_date > comment.updated_at:
                        self.debug(msg="...but we have newer commits. Ignoring!")
                        self.pull_request.add_desired_label(
                            name="community_review_existing"
                        )
                    else:
                        self.pull_request.add_desired_label(name="shipit")
                    break

                elif "needs_revision" in comment.body:
                    self.debug(msg="...said needs_revision!")
                    if last_commit_date > comment.updated_at:
                        self.debug(msg="...but we have newer commits. Ignoring!")
                        self.pull_request.add_desired_label(
                            name="community_review_existing"
                        )
                    else:
                        self.pull_request.add_desired_label(name="needs_revision")
                    break

                elif "needs_info" in comment.body:
                    self.debug(msg="...said needs_info!")
                    self.pull_request.add_desired_label(name="needs_info")

                elif "close_me" in comment.body:
                    self.debug(msg="...said close_me!")
                    self.pull_request.add_desired_label(name="pending_action_close_me")
                    break

            if comment.user.login == self.pull_request.get_pr_submitter():
                self.debug(msg="%s is PR submitter commented on %s." %
                           (comment.user.login, comment.created_at))

                if "bot_broken" in comment.body:
                    self.debug(msg="...said bot_broken!")
                    self.pull_request.add_desired_label(name="bot_broken")

                if "ready_for_review" in comment.body:
                    self.debug(msg="...ready for review!")
                    if "ansible" in module_maintainers:
                        self.debug(msg="core does the review!")
                        self.pull_request.add_desired_label(
                            name="core_review_existing"
                        )
                    elif not module_maintainers:
                        self.debug(msg="community does the review!")
                        self.pull_request.add_desired_label(
                            name="community_review_new"
                        )
                    else:
                        self.debug(msg="community does the review but has "
                                   "maintainer")
                        self.pull_request.add_desired_label(
                            name="community_review_existing"
                        )
                    break

            if (comment.user.login not in BOTLIST
                and self.is_ansible_member(comment.user.login)):

                self.debug(msg="%s is a ansible member" % comment.user.login)

                if "bot_broken" in comment.body:
                    self.debug(msg="...said bot_broken!")
                    self.pull_request.add_desired_label(name="bot_broken")

                if ("shipit" in comment.body or "+1" in comment.body
                    or "LGTM" in comment.body):
                    self.debug(msg="...said shipit!")
                    self.pull_request.add_desired_label(name="shipit_by_ansible_member")
                    break

                elif "needs_revision" in comment.body:
                    self.debug(msg="...said needs_revision!")
                    self.pull_request.add_desired_label(name="needs_revision")
                    break

                elif "needs_info" in comment.body:
                    self.debug(msg="...said needs_info!")
                    self.pull_request.add_desired_label(name="needs_info")
                    break

        self.debug(msg="--- END Processing Comments")

    def render_comment(self, boilerplate=None):
        """Renders templates into comments using the boilerplate as filename"""
        maintainers = self.module_maintainers
        if not maintainers:
            maintainers = ['ansible/core']

        submitter = self.pull_request.get_pr_submitter()

        template = environment.get_template('%s.j2' % boilerplate)
        comment = template.render(maintainer=maintainers, submitter=submitter)
        return comment

    def create_actions(self):
        """Creates actions from the desired label, unlabel and comment actions
        lists"""

        # create new label and comments action
        resolved_desired_pr_labels = []
        for desired_pr_label in self.pull_request.desired_pr_labels:

            # Most of the comments are only going to be added if we also add a
            # new label. So they are coupled. That is why we use the
            # boilerplate dict key as label and use an alias table containing
            # the real labels. This allows us to either use a real new label
            # without a comment or an label coupled with a comment. We check
            # if the label is a boilerplate dict key and get the real label
            # back or alternatively the label we gave as input
            # e.g. label: community_review_existing -> community_review
            # e.g. label: community_review -> community_review
            resolved_desired_pr_label = self.pull_request.resolve_desired_pr_labels(
                desired_pr_label
            )

            # If we didn't get back the same, it means we must also add a
            # comment for this label
            if desired_pr_label != resolved_desired_pr_label:

                # we cache for later use in unlabeling actions
                resolved_desired_pr_labels.append(resolved_desired_pr_label)

                # We only add actions (newlabel, comments) if the label is
                # not already set
                if (resolved_desired_pr_label not in
                        self.pull_request.get_current_labels()):
                    # Use the previous label as key for the boilerplate dict
                    self.pull_request.add_desired_comment(desired_pr_label)
                    self.actions['newlabel'].append(resolved_desired_pr_label)
            # it is a real label
            else:
                resolved_desired_pr_labels.append(desired_pr_label)
                if (desired_pr_label not in
                        self.pull_request.get_current_labels()):
                    self.actions['newlabel'].append(desired_pr_label)
                    # how about a boilerplate with that label name?
                    if os.path.exists("templates/" + desired_pr_label + ".j2"):
                        self.pull_request.add_desired_comment(desired_pr_label)

        # unlabel action
        for current_pr_label in self.pull_request.get_current_labels():

            # some labels we just ignore
            if current_pr_label in IGNORE_LABELS:
                continue

            # now check if we need to unlabel
            if current_pr_label not in resolved_desired_pr_labels:
                self.actions['unlabel'].append(current_pr_label)

        for boilerplate in self.pull_request.desired_comments:
            comment = self.render_comment(boilerplate=boilerplate)
            self.debug(msg=comment)
            self.actions['comments'].append(comment)

    def process(self):
        """Processes the PR"""
        # clear all actions
        self.actions = {
            'newlabel': [],
            'unlabel':  [],
            'comments': [],
        }
        # clear module maintainers
        self.module_maintainers = []
        # print some general infos about the PR to be processed
        print("\nPR #%s: %s" % (self.pull_request.pr_number,
                                (self.pull_request.instance.title).encode('ascii','ignore')))
        print("Created at %s" % self.pull_request.instance.created_at)
        print("Updated at %s" % self.pull_request.instance.updated_at)

        if "bot_broken" in self.pull_request.get_current_labels():
            print("bot_broken labeled, skipping. Needs to be removed manually.")
            return

        self.keep_current_main_labels()
        self.add_desired_labels_by_namespace()

        if self.pull_request.is_a_wip():
            self.debug(msg="PR is a work-in-progress")
            self.pull_request.add_desired_label(name="work_in_progress")
        else:
            self.add_desired_labels_by_maintainers()
            self.add_desired_labels_by_gitref()
            # process comments after labels
            self.process_comments()
            self.add_desired_labels_for_not_mergeable()
            self.add_desired_label_by_build_state()
            self.add_labels_by_issue_type()

        self.create_actions()

        # Print the things we processed
        print("Submitter: %s" % self.pull_request.get_pr_submitter())
        print("Maintainers: %s" % ', '.join(self.get_module_maintainers()))
        print("Current Labels: %s" %
              ', '.join(self.pull_request.current_pr_labels))
        print("Actions: %s" % self.actions)

        if (self.actions['newlabel'] or self.actions['unlabel'] or
                self.actions['comments']):
            if self.dry_run:
                print("Dry-run specified, skipping execution of actions")
            else:
                if self.force:
                    print("Running actions non-interactive as you forced.")
                    self.execute_actions()
                    return
                cont = raw_input("Take recommended actions (y/N/a)? ")
                if cont in ('a', 'A'):
                    sys.exit(0)
                if cont in ('Y', 'y'):
                    self.execute_actions()
        elif self.always_pause:
            print("Skipping, but pause.")
            cont = raw_input("Continue (Y/n/a)? ")
            if cont in ('a', 'A', 'n', 'N'):
                sys.exit(0)
        else:
            print("Skipping.")

    def execute_actions(self):
        """Turns the actions into API calls"""
        for unlabel in self.actions['unlabel']:
            self.debug(msg="API Call unlabel: " + unlabel)
            self.pull_request.remove_label(label=unlabel)
        for newlabel in self.actions['newlabel']:
            self.debug(msg="API Call newlabel: " + newlabel)
            self.pull_request.add_label(label=newlabel)
        for comment in self.actions['comments']:
            self.debug(msg="API Call comment: " + comment)
            self.pull_request.add_comment(comment=comment)

    def run(self):
        """Starts a triage run"""
        repo = self._connect().get_repo("ansible/ansible-modules-%s" %
                                        self.github_repo)

        if self.pr_number:
            self.pull_request = PullRequest(repo=repo,
                                            pr_number=self.pr_number)
            self.process()
        else:
            pulls = repo.get_pulls()
            for pull in pulls:
                if self.start_at_pr and pull.number > self.start_at_pr:
                    continue
                self.pull_request = PullRequest(repo=repo, pr=pull)
                self.process()

def main3():
    parser = argparse.ArgumentParser(
        description="Triage various issue+PR queues "
                    "for Ansible. (NOTE: only "
                    "useful if you have commit "
                    "access to the repo in "
                    "question.)"
    )

    parser.add_argument("--skip-no-update", action="store_true",
                        help="skip processing if updated_at hasn't changed")

    parser.add_argument("--collect_only", action="store_true",
                        help="stop after caching issues")

    parser.add_argument("--skip_module_repos", action="store_true",
                        help="ignore the module repos")
    parser.add_argument("--module_repos_only", action="store_true",
                        help="only process the module repos")

    parser.add_argument("--force_rate_limit", action="store_true",
                        help="debug: force the rate limit")

    parser.add_argument("--sort", default='desc', choices=['asc', 'desc'],
                        help="Direction to sort issues [desc=9-0 asc=0-9]")

    parser.add_argument("--logfile", type=str, default='/var/log/ansibullbot.log',
                        help="Send logging to this file")
    parser.add_argument("--daemonize", action="store_true",
                        help="run in a continuos loop")
    parser.add_argument("--daemonize_interval", type=int, default=(30 * 60),
                        help="seconds to sleep between loop iterations")

    parser.add_argument("--skiprepo", action='append',
                        help="Github repo to skip triaging")

    parser.add_argument("--repo", "-r", type=str,
                        help="Github repo to triage (defaults to all)")
    parser.add_argument("--gh-user", "-u", type=str,
                        help="Github username or token of triager")
    parser.add_argument("--gh-pass", "-P", type=str,
                        help="Github password of triager")
    parser.add_argument("--gh-token", "-T", type=str,
                        help="Github token of triager")
    parser.add_argument("--dryrun", "-n", action="store_true",
                        help="Do not apply any changes.")

    parser.add_argument("--only_prs", action="store_true",
                        help="Triage pullrequests only")
    parser.add_argument("--only_issues", action="store_true",
                        help="Triage issues only")

    parser.add_argument("--only_open", action="store_true",
                        help="Triage open issues|prs only")
    parser.add_argument("--only_closed", action="store_true",
                        help="Triage closed issues|prs only")

    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")
    parser.add_argument("--dry-run", action="store_true",
                        help="Ignore all actions")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Do not ask questions")
    parser.add_argument("--safe_force", action="store_true",
                        help="Prompt only when the workflow doesn't meet specific criteria")
    parser.add_argument("--debug", "-d", action="store_true",
                        help="Debug output")
    parser.add_argument("--pause", "-p", action="store_true",
                        help="Always pause between prs|issues")
    parser.add_argument("--pr", "--id", type=int,
                        help="Triage only the specified pr|issue")

    parser.add_argument("--start-at", "--resume_id", type=int,
                        help="Start triage at the specified pr|issue")
    parser.add_argument("--no_since", action="store_true",
                        help="Do not use the since keyword to fetch issues")
    args = parser.parse_args()

    # Run the triager ...
    TriageV3(args)


def main():

    ANSIBULLBOT_VERSION = int(os.environ.get('ANSIBULLBOT_VERSION', 1))
    ANSIBULLBOT_ALLOW_PRS = os.environ.get('ANSIBULLBOT_ALLOW_PRS', False)

    print('VERSION: %s' % ANSIBULLBOT_VERSION)
    if ANSIBULLBOT_VERSION == 3:
        main3()
    sys.exit(0)

    parser = argparse.ArgumentParser(description="Triage various PR queues "
                                                 "for Ansible. (NOTE: only "
                                                 "useful if you have commit "
                                                 "access to the repo in "
                                                 "question.)")
    parser.add_argument("repo", type=str, choices=['core', 'extras', 'ansible'],
                        help="Repo to be triaged")
    parser.add_argument("--gh-user", "-u", type=str,
                        help="Github username or token of triager")
    parser.add_argument("--gh-pass", "-P", type=str,
                        help="Github password of triager")
    parser.add_argument("--gh-token", "-T", type=str,
                        help="Github token of triager")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Do not apply any changes.")

    parser.add_argument("--only_prs", action="store_true",
                        help="Triage pullrequests only")
    parser.add_argument("--only_issues", action="store_true",
                        help="Triage issues only")

    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Do not ask questions")
    parser.add_argument("--safe_force", action="store_true",
                        help="Ask questions only if a precise match not made.")
    parser.add_argument("--debug", "-d", action="store_true",
                        help="Debug output")
    parser.add_argument("--pause", "-p", action="store_true",
                        help="Always pause between PRs")
    parser.add_argument("--pr", "--id", type=int,
                        help="Triage only the specified pr|issue")
    parser.add_argument("--start-at", type=int,
                        help="Start triage at the specified pr|issue")
    parser.add_argument("--no_since", action="store_true",
                        help="Do not use the since keyword to fetch issues")
    args = parser.parse_args()

    if args.pr and args.start_at:
        print("Error: Mutually exclusive: --start-at and --pr",
              file=sys.stderr)
        sys.exit(1)

    if args.force and args.pause:
        print("Error: Mutually exclusive: --force and --pause",
              file=sys.stderr)
        sys.exit(1)

    if args.force and args.safe_force:
        print("Error: Mutually exclusive: --force and --safe_force",
              file=sys.stderr)
        sys.exit(1)

    if args.only_prs and args.only_issues:
        print("Error: Mutually exclusive: --only_issues and --only_prs",
              file=sys.stderr)
        sys.exit(1)

    # THIS IS TO FORCE THE OLD BEHAVIOR BY DEFAULT
    if not ANSIBULLBOT_VERSION == 2 and not ANSIBULLBOT_ALLOW_PRS:
        args.only_prs = True
        args.only_issues = False

    if args.only_prs or not args.only_issues:
        triage = None
        kwargs = dict(
                verbose=args.verbose,
                github_user=args.gh_user,
                github_pass=args.gh_pass,
                github_token=args.gh_token,
                github_repo=args.repo,
                pr_number=args.pr,
                start_at_pr=args.start_at,
                always_pause=args.pause,
                force=args.force,
                dry_run=args.dry_run,
        )

        if ANSIBULLBOT_VERSION == 1:
            triage = TriagePullRequests(**kwargs)

        elif ANSIBULLBOT_VERSION == 2:

            kwargs['safe_force'] = args.safe_force
            kwargs['no_since'] = args.no_since
            kwargs['number'] = kwargs['pr_number']
            kwargs.pop('pr_number', None)
            kwargs['start_at'] = kwargs['start_at_pr']
            kwargs.pop('start_at_pr', None)

            if args.repo == 'ansible':
                triage = AnsibleAnsibleTriagePullRequests(**kwargs)
            else:
                print('Version 2 PR triage for %s repo not yet implemented' % args.repo)
                sys.exit(1)

        if not triage:
            print('No triager for %s version %s' % (args.repo, ANSIBULLBOT_VERSION))
            sys.exit(1)

        triage.run()

    elif args.only_issues or not args.only_prs:
        kwargs = dict(
                    verbose=args.verbose,
                    github_user=args.gh_user,
                    github_pass=args.gh_pass,
                    github_token=args.gh_token,
                    github_repo=args.repo,
                    number=args.pr,
                    start_at=args.start_at,
                    always_pause=args.pause,
                    force=args.force,
                    safe_force=args.safe_force,
                    dry_run=args.dry_run,
                    no_since=args.no_since
                )
        if args.repo == 'ansible':
            triage = AnsibleAnsibleTriageIssues(**kwargs)
        else:
            triage = TriageIssues(**kwargs)
        triage.run()

if __name__ == "__main__":
    main()
