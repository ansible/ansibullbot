#!/usr/bin/env python

import unittest
from datetime import datetime

from lib.wrappers.issuewrapper import IssueWrapper

from tests.utils.issue_mock import IssueMock
from tests.utils.issuetriager_mock import TriageIssuesMock

class TestIssueTriage(unittest.TestCase):

    def _get_triager_for_datafile(self, datafile):
        im = IssueMock(datafile)
        iw = IssueWrapper(repo=None, issue=im)
        triage = TriageIssuesMock(verbose=True)

        triage.issue = iw
        triage.issue.get_events()
        triage.issue.get_comments()

        # add additional mock data from fixture
        triage.force = True
        triage._now = im.ydata.get('_now', datetime.now())
        triage.number = im.ydata.get('number', 1)
        triage.github_repo = im.ydata.get('github_repo', 'core')
        triage.match = im.ydata.get('_match')
        triage.module_indexer.match = im.ydata.get('_match')
        triage._module = triage.match['name']
        triage._ansible_members = im.ydata.get('_ansible_members', [])
        triage._module_maintainers = im.ydata.get('_module_maintainers', [])

        return triage

    def test_basic_step_0(self):
        """New issue with all the data, just needs label and intro comment"""
        # load it ...
        triage = self._get_triager_for_datafile('tests/fixtures/000.yml')
        # let it rip ...
        triage.process(usecache=False)

        assert triage.actions['close'] == False
        assert triage.actions['newlabel'] == ['bug_report', 'cloud', 'waiting_on_maintainer']
        assert triage.actions['unlabel'] == []
        assert len(triage.actions['comments']) == 1
        assert triage.actions['comments'][0].endswith('<!--- boilerplate: issue_notify_maintainer --->')
        for maintainer in triage._module_maintainers:
            assert maintainer in triage.actions['comments'][0]


    def test_basic_step_1(self):
        """Issue was previously triaged and awaits maintainer"""
        # load it ...
        triage = self._get_triager_for_datafile('tests/fixtures/000_1.yml')
        # let it rip ...
        triage.process(usecache=False)

        assert triage.actions['close'] == False
        assert triage.actions['newlabel'] == []
        assert triage.actions['unlabel'] == []
        assert len(triage.actions['comments']) == 0


