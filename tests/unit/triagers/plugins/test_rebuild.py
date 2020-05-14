from ansibullbot.triagers.plugins.ci_rebuild import get_rebuild_command_facts
from tests.utils.helpers import get_issue


def test_rebuild_command():
    """Test ran and failed. /rebuild command issued."""
    datafile = u'tests/fixtures/rebuild/0_issue.yml'
    statusfile = u'tests/fixtures/rebuild/0_prstatus.json'
    with get_issue(datafile, statusfile) as iw:
        meta = {
            u'is_pullrequest': True,
            u'is_needs_revision': False,
            u'is_needs_rebase': False,
            u'needs_rebuild': False,
            u'ci_run_number': 0,
        }
        rbfacts = get_rebuild_command_facts(iw, meta)
        assert rbfacts[u'needs_rebuild']
        assert rbfacts[u'needs_rebuild_all']
        assert not rbfacts[u'needs_rebuild_failed']


def test_rebuild_failed_command():
    """Test ran and failed. /rebuild_failed command issued."""
    datafile = u'tests/fixtures/rebuild/1_issue.yml'
    statusfile = u'tests/fixtures/rebuild/1_prstatus.json'
    with get_issue(datafile, statusfile) as iw:
        meta = {
            u'is_pullrequest': True,
            u'is_needs_revision': False,
            u'is_needs_rebase': False,
            u'needs_rebuild': False,
            u'ci_run_number': 0,
        }
        rbfacts = get_rebuild_command_facts(iw, meta)
        assert rbfacts[u'needs_rebuild']
        assert rbfacts[u'needs_rebuild_failed']
        assert not rbfacts[u'needs_rebuild_all']


def test_rebuild_and_rebuild_failed_commands():
    """Test ran and failed. /rebuild and /rebuild_failed commands issued, in that order."""
    datafile = u'tests/fixtures/rebuild/2_issue.yml'
    statusfile = u'tests/fixtures/rebuild/2_prstatus.json'
    with get_issue(datafile, statusfile) as iw:
        meta = {
            u'is_pullrequest': True,
            u'is_needs_revision': False,
            u'is_needs_rebase': False,
            u'needs_rebuild': False,
            u'ci_run_number': 0,
        }
        rbfacts = get_rebuild_command_facts(iw, meta)
        assert rbfacts[u'needs_rebuild']
        assert rbfacts[u'needs_rebuild_failed']
        assert not rbfacts[u'needs_rebuild_all']


def test_rebuild_failed_and_rebuild_commands():
    """Test ran and failed. /rebuild_failed and /rebuild commands issued, in that order."""
    datafile = u'tests/fixtures/rebuild/3_issue.yml'
    statusfile = u'tests/fixtures/rebuild/3_prstatus.json'
    with get_issue(datafile, statusfile) as iw:
        meta = {
            u'is_pullrequest': True,
            u'is_needs_revision': False,
            u'is_needs_rebase': False,
            u'needs_rebuild': False,
            u'ci_run_number': 0,
        }
        rbfacts = get_rebuild_command_facts(iw, meta)
        assert rbfacts[u'needs_rebuild']
        assert rbfacts[u'needs_rebuild_all']
        assert not rbfacts[u'needs_rebuild_failed']
