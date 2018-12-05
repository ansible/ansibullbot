#! /usr/bin/env python

import textwrap

import pytest

from ansibullbot.triagers.plugins.notifications import get_notification_facts
from tests.utils.helpers import get_issue
from tests.utils.repo_mock import RepoMock


@pytest.fixture
def meta():
    return {
        u'component_maintainers': [u'target_user'],
        u'component_notifiers': [u'another_user'],
    }


@pytest.fixture
def statusfile():
    return u'tests/fixtures/needs_contributor/0_prstatus.json'


@pytest.fixture
def iw(meta, statusfile):
    datafile = u'tests/fixtures/needs_contributor/0_issue.yml'
    with get_issue(datafile, statusfile) as iw:
        iw.get_assignees = lambda: []
        iw.repo = RepoMock(meta[u'component_maintainers'] + meta[u'component_notifiers'])
        return iw


def test_notify_authors(iw, meta):
    facts = get_notification_facts(iw, meta)

    expected_assign_users = [u'target_user']
    expected_notify_users = [u'another_user']  # , u'target_user']
    assert sorted(facts[u'to_assign']) == expected_assign_users
    assert sorted(facts[u'to_notify']) == expected_notify_users
