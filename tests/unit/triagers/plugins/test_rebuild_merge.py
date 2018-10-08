#!/usr/bin/env python

import json
import logging
import tempfile
import unittest

from tests.utils.issue_mock import IssueMock
from tests.utils.repo_mock import RepoMock
from tests.utils.helpers import get_issue
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

    def test0(self):
        # command issued, test ran, time to merge
        datafile = u'tests/fixtures/rebuild_merge/0_issue.yml'
        statusfile = u'tests/fixtures/rebuild_merge/0_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            meta = {
                u'is_pullrequest': True,
                u'is_needs_revision': False,
                u'is_needs_rebase': False,
                u'needs_rebuild': False,
                u'ci_run_number': 0,
            }
            rbfacts = get_rebuild_merge_facts(iw, meta, [u'superman'])
            assert rbfacts[u'needs_rebuild'] == False
            assert rbfacts[u'admin_merge'] == True

    def test1(self):
        # new test is in progress, do not rebuild and do not merge
        datafile = u'tests/fixtures/rebuild_merge/1_issue.yml'
        statusfile = u'tests/fixtures/rebuild_merge/1_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            meta = {
                u'is_pullrequest': True,
                u'is_needs_revision': False,
                u'is_needs_rebase': False,
                u'needs_rebuild': False,
                u'ci_run_number': 0
            }
            rbfacts = get_rebuild_merge_facts(iw, meta, [u'superman'])
            assert rbfacts[u'needs_rebuild'] == False
            assert rbfacts[u'admin_merge'] == False

    def test2(self):
        # command given, time to rebuild but not merge
        datafile = u'tests/fixtures/rebuild_merge/2_issue.yml'
        statusfile = u'tests/fixtures/rebuild_merge/2_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            meta = {
                u'is_pullrequest': True,
                u'is_needs_revision': False,
                u'is_needs_rebase': False,
                u'needs_rebuild': False,
                u'ci_run_number': 0
            }
            rbfacts = get_rebuild_merge_facts(iw, meta, [u'superman'])
            assert rbfacts[u'needs_rebuild'] == True
            assert rbfacts[u'admin_merge'] == False

    def test3(self):
        # command given, new commit created, do not rebuild or merge
        datafile = u'tests/fixtures/rebuild_merge/3_issue.yml'
        statusfile = u'tests/fixtures/rebuild_merge/3_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            meta = {
                u'is_pullrequest': True,
                u'is_needs_revision': False,
                u'is_needs_rebase': False,
                u'needs_rebuild': False,
                u'ci_run_number': 0
            }
            rbfacts = get_rebuild_merge_facts(iw, meta, [u'superman'])
            assert rbfacts[u'needs_rebuild'] == False
            assert rbfacts[u'admin_merge'] == False
