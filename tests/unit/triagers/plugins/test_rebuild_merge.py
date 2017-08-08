#!/usr/bin/env python

import json
import logging
import tempfile
import unittest

from test.utils.issue_mock import IssueMock
from test.utils.repo_mock import RepoMock
from ansibullbot.triagers.plugins.ci_rebuild import get_rebuild_merge_facts
from ansibullbot.wrappers.issuewrapper import IssueWrapper
from ansibullbot.wrappers.historywrapper import HistoryWrapper

'''
logging.level = logging.DEBUG
consoleHandler = logging.StreamHandler()
logFormatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
consoleHandler.setFormatter(logFormatter)
rootLogger = logging.getLogger()
rootLogger.addHandler(consoleHandler)
'''


def load_update_fetch(datatype):
    logging.debug(datatype)
    return []


class TestRebuildMergeFacts(unittest.TestCase):

    def get_issue(self, datafile, statusfile):
        #datafile = 'test/fixtures/rebuild_merge/0_issue.yml'
        #statusfile = 'test/fixtures/rebuild_merge/0_prstatus.json'

        issue = IssueMock(datafile)
        tmpdir = tempfile.mkdtemp()
        repo = RepoMock()
        repo.repo_path = 'ansible/ansible'

        iw = IssueWrapper(repo=repo, cachedir=tmpdir, issue=issue)

        # disable this completely
        iw.load_update_fetch = load_update_fetch
        # hook in here to avoid github api calls
        iw._comments = issue.comments
        iw._events = issue.events
        iw._reactions = issue.reactions

        # pre-load status to avoid github api calls
        with open(statusfile, 'rb') as f:
            iw._pr_status = json.loads(f.read())

        # pre-create history to avoid github api calls
        history = HistoryWrapper(iw, cachedir=tmpdir, usecache=False)
        iw._history = history

        # merge_commits(self, commits)
        if issue.commits:
            iw._history.merge_commits(issue.commits)

        return iw

    def test0(self):
        # command issued, test ran, time to merge
        datafile = 'test/fixtures/rebuild_merge/0_issue.yml'
        statusfile = 'test/fixtures/rebuild_merge/0_prstatus.json'
        iw = self.get_issue(datafile, statusfile)

        meta = {
            'needs_revision': False,
            'needs_rebase': False,
            'needs_rebuild': False
        }
        rbfacts = get_rebuild_merge_facts(iw, meta, ['superman'])
        assert rbfacts['needs_rebuild'] == False
        assert rbfacts['admin_merge'] == True

    def test1(self):
        # new test is in progress, do not rebuild and do not merge
        datafile = 'test/fixtures/rebuild_merge/1_issue.yml'
        statusfile = 'test/fixtures/rebuild_merge/1_prstatus.json'
        iw = self.get_issue(datafile, statusfile)

        meta = {
            'needs_revision': False,
            'needs_rebase': False,
            'needs_rebuild': False
        }
        rbfacts = get_rebuild_merge_facts(iw, meta, ['superman'])
        assert rbfacts['needs_rebuild'] == False
        assert rbfacts['admin_merge'] == False

    def test2(self):
        # command given, time to rebuild but not merge
        datafile = 'test/fixtures/rebuild_merge/2_issue.yml'
        statusfile = 'test/fixtures/rebuild_merge/2_prstatus.json'
        iw = self.get_issue(datafile, statusfile)

        meta = {
            'needs_revision': False,
            'needs_rebase': False,
            'needs_rebuild': False
        }
        rbfacts = get_rebuild_merge_facts(iw, meta, ['superman'])
        assert rbfacts['needs_rebuild'] == True
        assert rbfacts['admin_merge'] == False

    def test3(self):
        # command given, new commit created, do not rebuild or merge
        datafile = 'test/fixtures/rebuild_merge/3_issue.yml'
        statusfile = 'test/fixtures/rebuild_merge/3_prstatus.json'
        iw = self.get_issue(datafile, statusfile)

        meta = {
            'needs_revision': False,
            'needs_rebase': False,
            'needs_rebuild': False
        }
        rbfacts = get_rebuild_merge_facts(iw, meta, ['superman'])
        assert rbfacts['needs_rebuild'] == False
        assert rbfacts['admin_merge'] == False
