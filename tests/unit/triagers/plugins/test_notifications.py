#! /usr/bin/env python

import textwrap

import pytest

from ansibullbot.triagers.plugins.notifications import get_notification_facts
from tests.utils.helpers import get_issue
from tests.utils.file_indexer_mock import create_indexer
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
def botmeta():
    return textwrap.dedent(u"""
        ---
        macros:
            modules: lib/ansible/modules
            module_utils: lib/ansible/module_utils
        files:
            $modules/foo/bar.py:
                maintainers: ElsA ZaZa
            $module_utils/baz/bar.py:
                maintainers: TiTi mscherer
    """)


@pytest.fixture
def module_indexer(botmeta):
    modules = {u'lib/ansible/modules/foo/bar.py': None}
    module_indexer = create_indexer(botmeta, modules)


@pytest.fixture
def iw(meta, statusfile):
    datafile = u'tests/fixtures/needs_contributor/0_issue.yml'
    with get_issue(datafile, statusfile) as iw:
        iw.get_assignees = lambda: []
        iw.repo = RepoMock(meta[u'component_maintainers'] + meta[u'component_notifiers'])
        return iw


def test_notify_authors(iw, meta, module_indexer):
    facts = get_notification_facts(iw, meta, module_indexer)

    expected_assign_users = [u'target_user']
    expected_notify_users = [u'another_user', u'target_user']
    assert sorted(facts[u'to_assign']) == expected_assign_users
    assert sorted(facts[u'to_notify']) == expected_notify_users
