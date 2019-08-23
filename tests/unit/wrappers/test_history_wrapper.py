#!/usr/bin/env python

import datetime
import pytz

from backports import tempfile

from ansibullbot.wrappers.historywrapper import HistoryWrapper



class UserMock(object):
    def __init__(self, login):
        self.login = login

class LabelEventMock(object):
    def __init__(self, event, login, label=None):
        self.id = 1
        self.actor = UserMock(login)
        self._created_at = datetime.datetime.now()
        self._event = event
        self._label = label

    @property
    def raw_data(self):
        created_at = self.created_at
        if isinstance(created_at, datetime.datetime):
            created_at = self.created_at.isoformat()
        return {
            'actor': {'login': self.actor.login},
            'event': self._event,
            'created_at': created_at,
            'label': {'name': self._label}
        }

    @property
    def event(self):
        return self._event

    @property
    def created_at(self):
        return self._created_at


class CommentMock(object):
    def __init__(self, login, body):
        self.id = 1
        self.user = UserMock(login)
        self.body = body
        self.created_at = datetime.datetime.now()


class RepoMock(object):
    repo_path = 'ansible/ansible'


class IssueMock(object):
    number = 1


class IssueWrapperMock(object):

    _events = []
    _comments = []
    _reactions = []

    def __init__(self):
        self.instance = IssueMock()
        self.repo = RepoMock()

    @property
    def events(self):
        return self._events

    @property
    def comments(self):
        return self._comments

    @property
    def reactions(self):
        return self._reactions


def test_get_component_commands():
    iw = IssueWrapperMock()

    iw._comments = [
        CommentMock('jimi-c', '!component =lib/ansible/unicorns')
    ]

    cachedir = tempfile.mkdtemp()
    hw = HistoryWrapper(iw, cachedir=cachedir, usecache=False)

    events = hw._find_events_by_actor('commented', None)
    ccommands = hw.get_component_commands(botnames=[])

    assert len(events) > 0
    assert len(ccommands) > 0


def test_get_no_component_commands():
    iw = IssueWrapperMock()

    iw._comments = [
        CommentMock('jimi-c', 'unicorns are awesome')
    ]

    cachedir = tempfile.mkdtemp()
    hw = HistoryWrapper(iw, cachedir=cachedir, usecache=False)

    events = hw._find_events_by_actor('commented', None)
    ccommands = hw.get_component_commands(botnames=[])

    assert len(events) == 1
    assert len(ccommands) == 0


def test_ignore_events_without_dates_on_last_methods():

    # With the addition of timeline events, we have a lot
    # of missing keys that we would normally get from the 
    # events endpoint. This test asserts that the historywrapper
    # filters those timeline events out when the necessary
    # keys are missing

    # iw.history.label_last_applied(u'needs_info')
    # iw.history.label_last_removed(u'needs_info')
    # iw.history.last_date_for_boilerplate(u'needs_info_base')
    # iw.history.last_date_for_boilerplate(u'issue_missing_data')

    events = [
        [u'labeled', True, u'bcoca', u'needs_info'],
        [u'labeled', None, u'bcoca', u'needs_info'],
        [u'comment', True, u'ansibot', u'foobar\n<!--- boilerplate: needs_info --->'],
        [u'comment', None, u'ansibot', u'foobar\n<!--- boilerplate: needs_info --->'],
        [u'labeled', True, u'ansibot', u'needs_info'],
        [u'labeled', None, u'ansibot', u'needs_info'],
        [u'comment', True, u'jimi-c', u'unicorns are awesome'],
        [u'comment', None, u'jimi-c', u'unicorns are awesome'],
        [u'unlabeled', True, u'ansibot', u'needs_info'],
        [u'unlabeled', None, u'ansibot', u'needs_info'],
    ]

    iw = IssueWrapperMock()
    for event in events:
        if event[0] in [u'labeled', u'unlabeled']:
            levent = LabelEventMock(event[0], event[2], label=event[3])
            if event[1] is None:
                levent._created_at = None
            iw._events.append(levent)

        if event[0] == u'comment':
            thiscomment = CommentMock(event[2], event[3])
            if event[1] is None:
                thiscomment.date = None
            iw._comments.append(thiscomment)

    cachedir = tempfile.mkdtemp()
    hw = HistoryWrapper(iw, cachedir=cachedir, usecache=False)

    res = []
    res.append(hw.label_last_applied(u'needs_info'))
    res.append(hw.label_last_removed(u'needs_info'))
    res.append(hw.last_date_for_boilerplate(u'needs_info'))
    res.append(hw.was_labeled(u'needs_info'))
    res.append(hw.was_unlabeled(u'needs_info'))

    assert not [x for x in res if x is None]


def test__fix_history_tz():

    with tempfile.TemporaryDirectory() as cachedir:

        iw = IssueWrapperMock()
        cachedir = tempfile.mkdtemp()
        hw = HistoryWrapper(iw, cachedir=cachedir, usecache=False)

        events = [
            {'created_at': datetime.datetime.now()},
            {'created_at': pytz.utc.localize(datetime.datetime.now())},
            {'created_at': '2019-08-01T19:00:00'},
            {'created_at': '2019-08-01T19:00:00Z'},
            {'created_at': '2019-08-01T19:00:00+00:00'},
        ]

        fixed = hw._fix_history_tz(events)
        for event in fixed:
            assert hasattr(event['created_at'], 'tzinfo')
            assert event['created_at'].tzinfo is not None
