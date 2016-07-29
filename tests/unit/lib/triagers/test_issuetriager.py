#!/usr/bin/env python

import unittest

from lib.wrappers.issuewrapper import IssueWrapper

from tests.utils.issue_mock import IssueMock
from tests.utils.issuetriager_mock import TriageIssuesMock

class TestIssueTriage(unittest.TestCase):

    def test_noop(self):
        im = IssueMock('tests/fixtures/000.yml')
        iw = IssueWrapper(repo=None, issue=im)
        triage = TriageIssuesMock(verbose=True)

        triage.issue = iw
        triage.issue.get_events()
        triage.issue.get_comments()

        # add additional mock data from fixture
        triage.force = True
        triage.number = im.ydata.get('number', 1)
        triage.github_repo = im.ydata.get('github_repo', 'core')
        triage.match = im.ydata.get('_match')
        triage.module_indexer.match = im.ydata.get('_match')
        triage._module = triage.match['name']
        triage._ansible_members = im.ydata.get('_ansible_members', [])
        triage._module_maintainers = im.ydata.get('_module_maintainers', [])

        # let it rip ...
        triage.process()

        assert triage.actons['close'] == False
        assert triage.actons['newlabel'] == ['bug_report', 'cloud', 'waiting_on_maintainer']
        assert triage.actons['unlabel'] == []
        assert len(triage.actons['comments']) == 1
        #import epdb; epdb.st()
