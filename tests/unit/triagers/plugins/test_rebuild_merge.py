import pytest

from ansibullbot.triagers.plugins.ci_rebuild import get_rebuild_merge_facts
from tests.utils.helpers import get_issue


@pytest.mark.xfail(reason="With shippable support removed, ci/azp.py needs a mock")
def test0():
    """command issued, test ran, time to merge"""
    datafile = 'tests/fixtures/rebuild_merge/0_issue.yml'
    statusfile = 'tests/fixtures/rebuild_merge/0_prstatus.json'
    with get_issue(datafile, statusfile) as iw:
        meta = {
            'is_pullrequest': True,
            'is_needs_revision': False,
            'is_needs_rebase': False,
            'needs_rebuild': False,
            'ci_run_number': 0,
        }
        rbfacts = get_rebuild_merge_facts(iw, meta, ['superman'], None)
        assert not rbfacts['needs_rebuild']
        assert not rbfacts['needs_rebuild_all']
        assert rbfacts['admin_merge']


@pytest.mark.xfail(reason="With shippable support removed, ci/azp.py needs a mock")
def test1():
    """new test is in progress, do not rebuild and do not merge"""
    datafile = 'tests/fixtures/rebuild_merge/1_issue.yml'
    statusfile = 'tests/fixtures/rebuild_merge/1_prstatus.json'
    with get_issue(datafile, statusfile) as iw:
        meta = {
            'is_pullrequest': True,
            'is_needs_revision': False,
            'is_needs_rebase': False,
            'needs_rebuild': False,
            'ci_run_number': 0
        }
        rbfacts = get_rebuild_merge_facts(iw, meta, ['superman'], None)
        assert not rbfacts['needs_rebuild']
        assert not rbfacts['needs_rebuild_all']
        assert not rbfacts['admin_merge']


@pytest.mark.xfail(reason="With shippable support removed, ci/azp.py needs a mock")
def test2():
    """command given, time to rebuild but not merge"""
    datafile = 'tests/fixtures/rebuild_merge/2_issue.yml'
    statusfile = 'tests/fixtures/rebuild_merge/2_prstatus.json'
    with get_issue(datafile, statusfile) as iw:
        meta = {
            'is_pullrequest': True,
            'is_needs_revision': False,
            'is_needs_rebase': False,
            'needs_rebuild': False,
            'ci_run_number': 0
        }
        rbfacts = get_rebuild_merge_facts(iw, meta, ['superman'], None)
        assert rbfacts['needs_rebuild']
        assert rbfacts['needs_rebuild_all']
        assert not rbfacts['admin_merge']


def test3():
    """command given, new commit created, do not rebuild or merge"""
    datafile = 'tests/fixtures/rebuild_merge/3_issue.yml'
    statusfile = 'tests/fixtures/rebuild_merge/3_prstatus.json'
    with get_issue(datafile, statusfile) as iw:
        meta = {
            'is_pullrequest': True,
            'is_needs_revision': False,
            'is_needs_rebase': False,
            'needs_rebuild': False,
            'ci_run_number': 0
        }
        rbfacts = get_rebuild_merge_facts(iw, meta, ['superman'], None)
        assert not rbfacts['needs_rebuild']
        assert not rbfacts['needs_rebuild_all']
        assert not rbfacts['admin_merge']
