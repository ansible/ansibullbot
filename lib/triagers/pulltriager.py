#!/usr/bin/env python

import sys

from lib.wrappers.ghapiwrapper import GithubWrapper
from lib.wrappers.issuewrapper import IssueWrapper
from lib.wrappers.pullrequestwrapper import PullrequestWrapper
from lib.triagers.defaulttriager import DefaultTriager


class TriagePullRequests(DefaultTriager):

    VALID_ISSUE_TYPES = ['bugfix pull request' , 'feature pull request', 'docs pull request', 'new module pull request']

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

        # extend the ignored labels by repo
        if hasattr(self, 'IGNORE_LABELS_ADD'):
            self.IGNORE_LABELS.extend(self.IGNORE_LABELS_ADD)


        if self.number:

            # get the issue
            issue = self.repo.get_issue(int(self.number))
            self.issue = IssueWrapper(repo=self.repo, issue=issue, cachedir=self.cachedir)
            self.issue.get_events()
            self.issue.get_comments()

            # get the PR
            self.issue.pullrequest = self.repo.get_pullrequest(int(self.number))
            self.issue.get_commits()
            self.issue.get_files()
            self.issue.get_review_comments()

            # get files/patches?
            import epdb; epdb.st()

            self.process()

        else:
                
            print('not implemented yet')
            sys.exit(1)


