import pytest

from ansibullbot.triagers.plugins.notifications import get_notification_facts
from tests.utils.helpers import get_issue
from tests.utils.repo_mock import RepoMock


@pytest.fixture
def meta():
    return {
        'component_maintainers': ['target_user'],
        'component_notifiers': ['another_user'],
    }


@pytest.fixture
def statusfile():
    return 'tests/fixtures/needs_contributor/0_prstatus.json'


@pytest.fixture
def iw(meta, statusfile):
    datafile = 'tests/fixtures/needs_contributor/0_issue.yml'
    with get_issue(datafile, statusfile) as iw:
        iw._assignees = []
        iw._merge_commits = []
        iw.repo = RepoMock(meta['component_maintainers'] + meta['component_notifiers'])
        return iw


def test_notify_authors(iw, meta):
    facts = get_notification_facts(iw, meta)

    expected_assign_users = ['target_user']
    expected_notify_users = ['another_user']  # , u'target_user']
    assert sorted(facts['to_assign']) == expected_assign_users
    assert sorted(facts['to_notify']) == expected_notify_users
