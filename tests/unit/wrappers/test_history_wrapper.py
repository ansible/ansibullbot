import datetime

import pytest

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
        {
            u'id': 1,
            u'actor': u'jimi-c',
            u'body': '!component =lib/ansible/unicorns',
            u'event': u'commented',
            u'created_at': datetime.datetime.utcnow(),
        }
    ]
    iw._events = iw._comments

    cachedir = tempfile.mkdtemp()
    hw = HistoryWrapper(iw, cachedir=cachedir, usecache=False)
    hw.BOTNAMES = []

    events = hw._find_events_by_actor('commented', None)
    ccommands = hw.get_component_commands()

    assert len(events) > 0
    assert len(ccommands) > 0


def test_get_no_component_commands():
    iw = IssueWrapperMock()

    iw._comments = [
        {
            u'id': 1,
            u'actor': u'jimi-c',
            u'body': u'unicorns are awesome',
            u'event': u'commented',
            u'created_at': datetime.datetime.utcnow(),
        }
    ]
    iw._events = iw._comments

    cachedir = tempfile.mkdtemp()
    hw = HistoryWrapper(iw, cachedir=cachedir, usecache=False)
    hw.BOTNAMES = []

    events = hw._find_events_by_actor('commented', None)
    ccommands = hw.get_component_commands()

    assert len(events) == 1
    assert len(ccommands) == 0


@pytest.mark.skip(reason="FIXME")
def test_ignore_events_without_dates_on_last_methods():
    """With the addition of timeline events, we have a lot
    of missing keys that we would normally get from the 
    events endpoint. This test asserts that the historywrapper
    filters those timeline events out when the necessary
    keys are missing."""

    events = [
        {u'event': u'labeled', u'created_at': datetime.datetime.utcnow(), u'actor': u'bcoca', u'label': u'needs_info'},
        {u'event': u'labeled', u'created_at': datetime.datetime.utcnow(), u'actor': u'bcoca', u'label': u'needs_info'},

        {u'event': u'comment', u'created_at': datetime.datetime.utcnow(), u'actor': u'ansibot', u'body': u'foobar\n<!--- boilerplate: needs_info --->'},
        {u'event': u'comment', u'actor': u'ansibot', u'body': u'foobar\n<!--- boilerplate: needs_info --->'},
        {u'event': u'labeled', u'created_at': datetime.datetime.utcnow(), u'actor': u'ansibot', u'label': u'needs_info'},
        {u'event': u'labeled', u'actor': u'ansibot', u'label': u'needs_info'},
        {u'event': u'comment', u'created_at': datetime.datetime.utcnow(), u'actor': u'jimi-c', u'body': u'unicorns are awesome'},
        {u'event': u'comment', u'actor': u'jimi-c', u'body': u'unicorns are awesome'},
        {u'event': u'unlabeled', u'created_at': datetime.datetime.utcnow(), u'actor': u'ansibot', u'label': u'needs_info'},
        {u'event': u'unlabeled', u'actor': u'ansibot', u'label': u'needs_info'},
    ]

    iw = IssueWrapperMock()
    for event in events:
        if event[u'event'] == u'comment':
            iw._comments.append(event)
        iw._events.append(event)

    cachedir = tempfile.mkdtemp()
    hw = HistoryWrapper(iw, cachedir=cachedir, usecache=False)
    hw.BOTNAMES = ['ansibot']

    res = []
    res.append(hw.label_last_applied(u'needs_info'))
    res.append(hw.label_last_removed(u'needs_info'))
    res.append(hw.last_date_for_boilerplate(u'needs_info'))
    res.append(hw.was_labeled(u'needs_info'))
    res.append(hw.was_unlabeled(u'needs_info'))

    assert not [x for x in res if x is None]
