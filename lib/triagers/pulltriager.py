#!/usr/bin/env python

import sys

from lib.wrappers.ghapiwrapper import GithubWrapper
from lib.wrappers.issuewrapper import IssueWrapper
from lib.wrappers.pullrequestwrapper import PullrequestWrapper
from lib.triagers.defaulttriager import DefaultTriager


class TriagePullRequests(DefaultTriager):

    VALID_ISSUE_TYPES = ['bugfix pull request' , 'feature pull request', 'docs pull request', 
                         'new module pull request', 'test pull request']

    MUTUALLY_EXCLUSIVE_LABELS = [x.replace(' ', '_') for x in VALID_ISSUE_TYPES]

    def run(self, useapiwrapper=True):
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

        # make a list of valid assignees
        print('Getting valid assignees')
        self.valid_assignees = [x.login for x in self.repo.get_assignees()]

        # extend the ignored labels by repo
        if hasattr(self, 'IGNORE_LABELS_ADD'):
            self.IGNORE_LABELS.extend(self.IGNORE_LABELS_ADD)

        if self.number:

            # get the issue
            issue = self.repo.get_issue(int(self.number))
            self.issue = IssueWrapper(repo=self.repo, issue=issue, cachedir=self.cachedir)
            self.issue.MUTUALLY_EXCLUSIVE_LABELS = self.MUTUALLY_EXCLUSIVE_LABELS
            self.issue.valid_assignees = self.valid_assignees
            self.issue.get_events()
            self.issue.get_comments()

            # get the PR and it's properties
            self.issue.pullrequest = self.repo.get_pullrequest(int(self.number))
            self.issue.get_commits()
            self.issue.get_files()
            self.issue.get_review_comments()

            # do the work
            self.process()

        else:

            # need to get the PRs
            print('Getting ALL pullrequests')
            pullrequests = self.repo.get_pullrequests(since=None)

            # iterate
            for idp,pr in enumerate(pullrequests):
                # get the issue and make a wrapper             
                issue = self.repo.get_issue(int(pr.number))
                self.issue = IssueWrapper(repo=self.repo, issue=issue, cachedir=self.cachedir)
                self.issue.MUTUALLY_EXCLUSIVE_LABELS = self.MUTUALLY_EXCLUSIVE_LABELS
                self.issue.valid_assignees = self.valid_assignees
                self.issue.get_events()
                self.issue.get_comments()

                # get the PR and it's properties
                self.issue.pullrequest = pr
                self.issue.get_commits()
                self.issue.get_files()
                self.issue.get_review_comments()

                # do the work
                self.process()
