import unittest

from ansibullbot.triagers.plugins.needs_contributor import get_needs_contributor_facts
from tests.utils.helpers import get_issue


class AnsibleTriageMock:
    BOTNAMES = ['ansibot']


class TestNeedsContributorFacts(unittest.TestCase):

    def setUp(self):
        self.statusfile = 'tests/fixtures/needs_contributor/0_prstatus.json'

    def test_needs_contributor_command(self):
        datafile = 'tests/fixtures/needs_contributor/0_issue.yml'
        with get_issue(datafile, self.statusfile) as iw:
            facts = get_needs_contributor_facts(AnsibleTriageMock(), iw)
            self.assertTrue(facts['is_needs_contributor'])

    def test_not_needs_contributor_command(self):
        datafile = 'tests/fixtures/needs_contributor/1_issue.yml'
        with get_issue(datafile, self.statusfile) as iw:
            facts = get_needs_contributor_facts(AnsibleTriageMock(), iw)
            self.assertFalse(facts['is_needs_contributor'])

    def test_waiting_on_contributor_label(self):
        datafile = 'tests/fixtures/needs_contributor/2_issue.yml'
        with get_issue(datafile, self.statusfile) as iw:
            facts = get_needs_contributor_facts(AnsibleTriageMock(), iw)
            self.assertTrue(facts['is_needs_contributor'])
