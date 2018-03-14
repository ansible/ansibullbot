import datetime
import six
import unittest

six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock

from ansibullbot.triagers.plugins.needs_info import needs_info_timeout_facts
from tests.utils.helpers import get_issue


class MockNow(datetime.datetime):
    @classmethod
    def now(cls):
        return cls(2018, 3, 14, 12, 18, 49, 666470)


class TestNeedsInfoTimeoutFacts(unittest.TestCase):

    def setUp(self):
        self.meta = {
            'is_needs_info': True,
        }
        self.statusfile = 'tests/fixtures/needs_info/0_prstatus.json'

    def test_warn(self):
        datafile = 'tests/fixtures/needs_info/0_warn.yml'
        with get_issue(datafile, self.statusfile) as iw:
            facts = needs_info_timeout_facts(iw, self.meta)

            self.assertEquals(facts['needs_info_action'], 'warn')

    def test_close(self):
        datafile = 'tests/fixtures/needs_info/0_close.yml'
        with get_issue(datafile, self.statusfile) as iw:
            facts = needs_info_timeout_facts(iw, self.meta)

            self.assertEquals(facts['needs_info_action'], 'close')

    def test_no_action(self):
        datafile = 'tests/fixtures/needs_info/0_no_action.yml'
        with get_issue(datafile, self.statusfile) as iw:
            facts = needs_info_timeout_facts(iw, self.meta)

            self.assertEquals(facts['needs_info_action'], None)

    def test_close_1(self):
        datafile = 'tests/fixtures/needs_info/1_close.yml'
        with get_issue(datafile, self.statusfile) as iw:

            datetime.datetime = MockNow

            facts = needs_info_timeout_facts(iw, self.meta)

            self.assertEquals(facts['needs_info_action'], 'close')
