import datetime
import six
import unittest

six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock

from ansibullbot.triagers.plugins import needs_info
from tests.utils.helpers import get_issue


class TestNeedsInfoTimeoutFacts(unittest.TestCase):

    def setUp(self):
        self.meta = {
            'is_needs_info': True,
        }
        self.statusfile = 'tests/fixtures/needs_info/0_prstatus.json'
        datetime_patcher = mock.patch.object(needs_info.datetime,
                                             'datetime',
                                             mock.Mock(wraps=datetime.datetime))
        mocked_datetime = datetime_patcher.start()
        mocked_datetime.now.return_value = datetime.datetime(2018, 3, 14, 12, 18, 49, 666470)
        self.addCleanup(datetime_patcher.stop)

    def test_warn(self):
        datafile = 'tests/fixtures/needs_info/0_warn.yml'
        with get_issue(datafile, self.statusfile) as iw:
            facts = needs_info.needs_info_timeout_facts(iw, self.meta)

            self.assertEquals(facts['needs_info_action'], 'warn')

    def test_close(self):
        datafile = 'tests/fixtures/needs_info/0_close.yml'
        with get_issue(datafile, self.statusfile) as iw:
            facts = needs_info.needs_info_timeout_facts(iw, self.meta)

            self.assertEquals(facts['needs_info_action'], 'close')

    def test_no_action(self):
        datafile = 'tests/fixtures/needs_info/0_no_action.yml'
        with get_issue(datafile, self.statusfile) as iw:
            facts = needs_info.needs_info_timeout_facts(iw, self.meta)

            self.assertEquals(facts['needs_info_action'], None)

    def test_close_1(self):
        datafile = 'tests/fixtures/needs_info/1_close.yml'
        with get_issue(datafile, self.statusfile) as iw:
            facts = needs_info.needs_info_timeout_facts(iw, self.meta)

            self.assertEquals(facts['needs_info_action'], 'close')
