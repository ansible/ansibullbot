from ansibullbot.triagers.plugins.ci_rebuild import get_rebuild_merge_facts
from ansibullbot.utils.shippable_api import ShippableCI
from tests.utils.helpers import get_issue


def test0():
    """command issued, test ran, time to merge"""
    datafile = u'tests/fixtures/rebuild_merge/0_issue.yml'
    statusfile = u'tests/fixtures/rebuild_merge/0_prstatus.json'
    with get_issue(datafile, statusfile) as iw:
        meta = {
            u'is_pullrequest': True,
            u'is_needs_revision': False,
            u'is_needs_rebase': False,
            u'needs_rebuild': False,
            u'ci_run_number': 0,
        }
        rbfacts = get_rebuild_merge_facts(iw, meta, [u'superman'], ShippableCI)
        assert not rbfacts[u'needs_rebuild']
        assert not rbfacts[u'needs_rebuild_all']
        assert rbfacts[u'admin_merge']


def test1():
    """new test is in progress, do not rebuild and do not merge"""
    datafile = u'tests/fixtures/rebuild_merge/1_issue.yml'
    statusfile = u'tests/fixtures/rebuild_merge/1_prstatus.json'
    with get_issue(datafile, statusfile) as iw:
        meta = {
            u'is_pullrequest': True,
            u'is_needs_revision': False,
            u'is_needs_rebase': False,
            u'needs_rebuild': False,
            u'ci_run_number': 0
        }
        rbfacts = get_rebuild_merge_facts(iw, meta, [u'superman'], ShippableCI)
        assert not rbfacts[u'needs_rebuild']
        assert not rbfacts[u'needs_rebuild_all']
        assert not rbfacts[u'admin_merge']


def test2():
    """command given, time to rebuild but not merge"""
    datafile = u'tests/fixtures/rebuild_merge/2_issue.yml'
    statusfile = u'tests/fixtures/rebuild_merge/2_prstatus.json'
    with get_issue(datafile, statusfile) as iw:
        meta = {
            u'is_pullrequest': True,
            u'is_needs_revision': False,
            u'is_needs_rebase': False,
            u'needs_rebuild': False,
            u'ci_run_number': 0
        }
        rbfacts = get_rebuild_merge_facts(iw, meta, [u'superman'], ShippableCI)
        assert rbfacts[u'needs_rebuild']
        assert rbfacts[u'needs_rebuild_all']
        assert not rbfacts[u'admin_merge']


def test3():
    """command given, new commit created, do not rebuild or merge"""
    datafile = u'tests/fixtures/rebuild_merge/3_issue.yml'
    statusfile = u'tests/fixtures/rebuild_merge/3_prstatus.json'
    with get_issue(datafile, statusfile) as iw:
        meta = {
            u'is_pullrequest': True,
            u'is_needs_revision': False,
            u'is_needs_rebase': False,
            u'needs_rebuild': False,
            u'ci_run_number': 0
        }
        rbfacts = get_rebuild_merge_facts(iw, meta, [u'superman'], ShippableCI)
        assert not rbfacts[u'needs_rebuild']
        assert not rbfacts[u'needs_rebuild_all']
        assert not rbfacts[u'admin_merge']
