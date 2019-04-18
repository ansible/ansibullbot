#!/usr/bin/env python

import datetime
import tempfile

from ansibullbot.wrappers.historywrapper import HistoryWrapper



class UserMock(object):
    def __init__(self, login):
        self.login = login


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
