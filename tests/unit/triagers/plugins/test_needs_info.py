import datetime
import tempfile
import unittest

from unittest import mock

from ansibullbot.historywrapper import HistoryWrapper
from ansibullbot.plugins import needs_info


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
        mocked_datetime.now.return_value = datetime.datetime(2018, 3, 14, 12, 18, 49, 666470, tzinfo=datetime.timezone.utc)
        self.addCleanup(datetime_patcher.stop)
        self.cachedir = tempfile.mkdtemp(prefix='ansibot_tests_')

    def test_warn(self):
        events = [{
            'actor': 'mkrizek',
            'created_at': datetime.datetime(2018, 2, 10, 17, 24, 2, tzinfo=datetime.timezone.utc),
            'event': 'labeled',
            'label': 'needs_info',
        }]
        history = HistoryWrapper(events, ['needs_info'], datetime.datetime.now(), cachedir=self.cachedir, usecache=False)
        facts = needs_info.needs_info_timeout_facts(history, self.meta)
        assert facts['needs_info_action'] == 'warn'

    def test_close(self):
        events = [
            {
                'actor': 'mkrizek',
                'created_at': datetime.datetime(2017, 12, 10, 17, 24, 2, tzinfo=datetime.timezone.utc),
                'event': 'labeled',
                'label': 'needs_info',
            },
            {
                'actor': 'ansibot',
                'body': '<!--- boilerplate: needs_info_base --->\n',
                'created_at': datetime.datetime(2018, 1, 10, 17, 24, 1, tzinfo=datetime.timezone.utc),
                'event': 'commented',
            },
        ]
        history = HistoryWrapper(events, ['needs_info'], datetime.datetime.now(), cachedir=self.cachedir, usecache=False)
        facts = needs_info.needs_info_timeout_facts(history, self.meta)
        assert facts['needs_info_action'] == 'close'

    def test_no_action(self):
        events = [
            {
                'actor': 'mkrizek',
                'created_at': datetime.datetime(2018, 2, 10, 17, 24, 2, tzinfo=datetime.timezone.utc),
                'event': 'labeled',
                'label': 'bug',
            }
        ]
        history = HistoryWrapper(events, ['bug'], datetime.datetime.now(), cachedir=self.cachedir, usecache=False)
        facts = needs_info.needs_info_timeout_facts(history, self.meta)
        assert facts['needs_info_action'] is None

    def test_close_1(self):
        events = [
            {
                'actor': 'mkrizek',
                'created_at': datetime.datetime(2017, 8, 16, 17, 24, 2, tzinfo=datetime.timezone.utc),
                'event': 'labeled',
                'label': 'needs_info',
            },
            {
                'actor': 'ansibot',
                'body': '<!--- boilerplate: needs_info_base --->\n',
                'created_at': datetime.datetime(2018, 1, 31, 17, 24, 1, tzinfo=datetime.timezone.utc),
                'event': 'commented',
            },
        ]
        history = HistoryWrapper(events, ['needs_info'], datetime.datetime.now(), cachedir=self.cachedir, usecache=False)
        facts = needs_info.needs_info_timeout_facts(history, self.meta)
        assert facts['needs_info_action'] == 'close'

    def test_too_quick_close(self):
        events = [
            {
                'actor': 'ansibot',
                'body': '<!--- boilerplate: needs_info_base --->\n',
                'created_at': datetime.datetime(2016, 2, 18, 18, 45, 1, tzinfo=datetime.timezone.utc),
                'event': 'commented',
            },
            {
                'actor': 'ansibot',
                'body': '<!--- boilerplate: needs_info_base --->\n',
                'created_at': datetime.datetime(2016, 2, 18, 18, 48, 1, tzinfo=datetime.timezone.utc),
                'event': 'commented',
            },
        ]
        history = HistoryWrapper(events, [], datetime.datetime.now(), cachedir=self.cachedir, usecache=False)
        facts = needs_info.needs_info_timeout_facts(history, self.meta)
        assert facts['needs_info_action'] is None

    def test_too_quick_close2(self):
        events = [
            {
                'actor': 'ansibot',
                'body': '<!--- boilerplate: needs_info_base --->\n',
                'created_at': datetime.datetime(2017, 3, 21, 18, 45, 1, tzinfo=datetime.timezone.utc),
                'event': 'commented',
            },
            {
                'actor': 'mkrizek',
                'body': 'Information provided.\n',
                'created_at': datetime.datetime(2017, 3, 22, 18, 45, 1, tzinfo=datetime.timezone.utc),
                'event': 'commented',
            },
            {
                'actor': 'ansibot',
                'created_at': datetime.datetime(2017, 3, 22, 18, 46, 1, tzinfo=datetime.timezone.utc),
                'event': 'unlabeled',
                'label': 'needs_info',
            },
            {
                'actor': 'debugger',
                'body': 'More info needed.\n',
                'created_at': datetime.datetime(2017, 3, 23, 18, 45, 1, tzinfo=datetime.timezone.utc),
                'event': 'commented',
            },
            {
                'actor': 'ansibot',
                'created_at': datetime.datetime(2017, 3, 23, 18, 46, 1, tzinfo=datetime.timezone.utc),
                'event': 'labeled',
                'label': 'needs_info',
            },
        ]
        history = HistoryWrapper(events, ['needs_info'], datetime.datetime.now(), cachedir=self.cachedir, usecache=False)
        facts = needs_info.needs_info_timeout_facts(history, self.meta)
        assert facts['needs_info_action'] == 'warn'

    def test_warn_template(self):
        events = [
            {
                'actor': 'ansibot',
                'created_at': datetime.datetime(2018, 2, 10, 17, 24, 2, tzinfo=datetime.timezone.utc),
                'event': 'labeled',
                'label': 'needs_info',
            },
            {
                'actor': 'ansibot',
                'created_at': datetime.datetime(2018, 2, 10, 17, 24, 2, tzinfo=datetime.timezone.utc),
                'event': 'labeled',
                'label': 'needs_template',
            },
            {
                'actor': 'ansibot',
                'body': '<!--- boilerplate: issue_missing_data --->\n',
                'created_at': datetime.datetime(2018, 1, 10, 17, 24, 1, tzinfo=datetime.timezone.utc),
                'event': 'commented',
            },
        ]
        history = HistoryWrapper(events, ['needs_info', 'needs_template'], datetime.datetime.now(), cachedir=self.cachedir, usecache=False)
        facts = needs_info.needs_info_timeout_facts(history, self.meta)
        assert facts['needs_info_action'] == 'warn'
