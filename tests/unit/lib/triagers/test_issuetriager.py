#!/usr/bin/env python

import unittest
from datetime import datetime

from tests.utils.loaders import  get_triagermock_for_datafile

class TestIssueTriageWorkflow1(unittest.TestCase):


    def test_basic_step_0(self):
        """New issue with all the data, just needs label and intro comment"""
        # load it ...
        triage = get_triagermock_for_datafile('tests/fixtures/000.yml')
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
        triage = get_triagermock_for_datafile('tests/fixtures/000_1.yml')
        # let it rip ...
        triage.process(usecache=False)

        assert triage.actions['close'] == False
        assert triage.actions['newlabel'] == []
        assert triage.actions['unlabel'] == []
        assert len(triage.actions['comments']) == 0

    def test_basic_step_2(self):
        """Issue was previously triaged and maintainer response timeout"""
        # load it ...
        triage = get_triagermock_for_datafile('tests/fixtures/000_2.yml')
        # let it rip ...
        triage.process(usecache=False)

        assert triage.actions['close'] == False
        assert triage.actions['newlabel'] == []
        assert triage.actions['unlabel'] == []
        assert len(triage.actions['comments']) == 1

    def test_basic_step_3(self):
        """Maintainer has finally responded with needs_info"""
        # load it ...
        triage = get_triagermock_for_datafile('tests/fixtures/000_3.yml')
        # let it rip ...
        triage.process(usecache=False)

        assert triage.actions['close'] == False
        assert triage.actions['newlabel'] == ['needs_info']
        assert triage.actions['unlabel'] == ['waiting_on_maintainer']
        assert len(triage.actions['comments']) == 0

    def test_basic_step_4(self):
        """needs_info still but not timeout"""
        # load it ...
        triage = get_triagermock_for_datafile('tests/fixtures/000_4.yml')
        # let it rip ...
        triage.process(usecache=False)

        assert triage.actions['close'] == False
        assert triage.actions['newlabel'] == []
        assert triage.actions['unlabel'] == []
        assert len(triage.actions['comments']) == 0

    def test_basic_step_5(self):
        """needs_info still and TIMEOUT 1"""
        # load it ...
        triage = get_triagermock_for_datafile('tests/fixtures/000_5.yml')
        # let it rip ...
        triage.process(usecache=False)

        assert triage.actions['close'] == False
        assert triage.actions['newlabel'] == []
        assert triage.actions['unlabel'] == []
        assert len(triage.actions['comments']) == 1
        assert triage.actions['comments'][0].endswith('<!--- boilerplate: issue_closure --->')
        submitter = triage.issue.get_submitter()
        submitter = '@' + submitter
        assert submitter in triage.actions['comments'][0]

    def test_basic_step_6(self):
        """needs_info still and TIMEOUT 2 + CLOSE!"""
        # load it ...
        triage = get_triagermock_for_datafile('tests/fixtures/000_6.yml')
        # let it rip ...
        triage.process(usecache=False)

        assert triage.actions['close'] == True
        assert triage.actions['newlabel'] == []
        assert triage.actions['unlabel'] == []
        assert len(triage.actions['comments']) == 1
        assert triage.actions['comments'][0].endswith('<!--- boilerplate: issue_closure --->')
        submitter = triage.issue.get_submitter()
        submitter = '@' + submitter
        assert submitter in triage.actions['comments'][0]


class TestIssueTriageBadUsers(unittest.TestCase):

    """Assert that bad submitters are handled appropriately"""

    def test_issue_no_template(self):
        """New issue with no data"""
        # load it ...
        triage = get_triagermock_for_datafile('tests/fixtures/001_bad_template.yml')
        # let it rip ...
        triage.process(usecache=False)

        assert triage.actions['close'] == False
        assert triage.actions['newlabel'] == ['needs_info']
        assert triage.actions['unlabel'] == []
        assert len(triage.actions['comments']) == 1
        assert triage.actions['comments'][0].endswith('<!--- boilerplate: issue_invalid_module --->')
        submitter = triage.issue.get_submitter()
        submitter = '@' + submitter
        assert submitter in triage.actions['comments'][0]

    def test_issue_no_ansible_version(self):
        """New issue with no data"""
        # load it ...
        triage = get_triagermock_for_datafile('tests/fixtures/001_no_ansible_version.yml')
        # let it rip ...
        triage.process(usecache=False)

        assert triage.actions['close'] == False
        assert triage.actions['newlabel'] == ['bug_report', 'needs_info', 'cloud']
        assert triage.actions['unlabel'] == []
        assert len(triage.actions['comments']) == 1
        assert triage.actions['comments'][0].endswith('<!--- boilerplate: issue_needs_info --->')
        submitter = triage.issue.get_submitter()
        submitter = '@' + submitter
        assert submitter in triage.actions['comments'][0]
