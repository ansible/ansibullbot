import datetime
import tempfile

import pytest

from ansibullbot.historywrapper import HistoryWrapper


def test_get_component_commands():
    events = [
        {
            'id': 1,
            'actor': 'jimi-c',
            'body': '!component =lib/ansible/unicorns',
            'event': 'commented',
            'created_at': datetime.datetime.utcnow(),
        }
    ]

    cachedir = tempfile.mkdtemp()
    hw = HistoryWrapper(events, [], datetime.datetime.utcnow(), cachedir=cachedir, usecache=False)
    hw.BOTNAMES = []

    events = hw._find_events_by_actor('commented', None)
    ccommands = hw.get_component_commands()

    assert len(events) > 0
    assert len(ccommands) > 0


def test_get_no_component_commands():
    events = [
        {
            'id': 1,
            'actor': 'jimi-c',
            'body': 'unicorns are awesome',
            'event': 'commented',
            'created_at': datetime.datetime.utcnow(),
        }
    ]

    cachedir = tempfile.mkdtemp()
    hw = HistoryWrapper(events, [], datetime.datetime.utcnow(), cachedir=cachedir, usecache=False)
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
        {'event': 'labeled', 'created_at': datetime.datetime.utcnow(), 'actor': 'bcoca', 'label': 'needs_info'},
        {'event': 'labeled', 'created_at': datetime.datetime.utcnow(), 'actor': 'bcoca', 'label': 'needs_info'},

        {'event': 'comment', 'created_at': datetime.datetime.utcnow(), 'actor': 'ansibot', 'body': 'foobar\n<!--- boilerplate: needs_info --->'},
        {'event': 'comment', 'actor': 'ansibot', 'body': 'foobar\n<!--- boilerplate: needs_info --->'},
        {'event': 'labeled', 'created_at': datetime.datetime.utcnow(), 'actor': 'ansibot', 'label': 'needs_info'},
        {'event': 'labeled', 'actor': 'ansibot', 'label': 'needs_info'},
        {'event': 'comment', 'created_at': datetime.datetime.utcnow(), 'actor': 'jimi-c', 'body': 'unicorns are awesome'},
        {'event': 'comment', 'actor': 'jimi-c', 'body': 'unicorns are awesome'},
        {'event': 'unlabeled', 'created_at': datetime.datetime.utcnow(), 'actor': 'ansibot', 'label': 'needs_info'},
        {'event': 'unlabeled', 'actor': 'ansibot', 'label': 'needs_info'},
    ]

    cachedir = tempfile.mkdtemp()
    hw = HistoryWrapper(events, [], datetime.datetime.utcnow(), cachedir=cachedir, usecache=False)
    hw.BOTNAMES = ['ansibot']

    res = []
    res.append(hw.label_last_applied('needs_info'))
    res.append(hw.label_last_removed('needs_info'))
    res.append(hw.last_date_for_boilerplate('needs_info'))
    res.append(hw.was_labeled('needs_info'))
    res.append(hw.was_unlabeled('needs_info'))

    assert not [x for x in res if x is None]
