import pytest

from ansibullbot.triagers.plugins.ci_rebuild import get_rebuild_command_facts

from tests.utils.helpers import get_issue


@pytest.mark.skip(reason="With shippable support removed, ci/azp.py needs a mock")
def test_rebuild_command():
    """Test ran and failed. /rebuild command issued."""
    datafile = 'tests/fixtures/rebuild/0_issue.yml'
    statusfile = 'tests/fixtures/rebuild/0_prstatus.json'
    with get_issue(datafile, statusfile) as iw:
        meta = {
            'is_pullrequest': True,
            'is_needs_revision': False,
            'is_needs_rebase': False,
            'needs_rebuild': False,
            'ci_run_number': 0,
        }
        rbfacts = get_rebuild_command_facts(iw, meta, None)
        assert rbfacts['needs_rebuild']
        assert rbfacts['needs_rebuild_all']
        assert not rbfacts['needs_rebuild_failed']


@pytest.mark.skip(reason="With shippable support removed, ci/azp.py needs a mock")
def test_rebuild_failed_command():
    """Test ran and failed. /rebuild_failed command issued."""
    datafile = 'tests/fixtures/rebuild/1_issue.yml'
    statusfile = 'tests/fixtures/rebuild/1_prstatus.json'
    with get_issue(datafile, statusfile) as iw:
        meta = {
            'is_pullrequest': True,
            'is_needs_revision': False,
            'is_needs_rebase': False,
            'needs_rebuild': False,
            'ci_run_number': 0,
        }
        rbfacts = get_rebuild_command_facts(iw, meta, None)
        assert rbfacts['needs_rebuild']
        assert rbfacts['needs_rebuild_failed']
        assert not rbfacts['needs_rebuild_all']


@pytest.mark.skip(reason="With shippable support removed, ci/azp.py needs a mock")
def test_rebuild_and_rebuild_failed_commands():
    """Test ran and failed. /rebuild and /rebuild_failed commands issued, in that order."""
    datafile = 'tests/fixtures/rebuild/2_issue.yml'
    statusfile = 'tests/fixtures/rebuild/2_prstatus.json'
    with get_issue(datafile, statusfile) as iw:
        meta = {
            'is_pullrequest': True,
            'is_needs_revision': False,
            'is_needs_rebase': False,
            'needs_rebuild': False,
            'ci_run_number': 0,
        }
        rbfacts = get_rebuild_command_facts(iw, meta, None)
        assert rbfacts['needs_rebuild']
        assert rbfacts['needs_rebuild_failed']
        assert not rbfacts['needs_rebuild_all']


@pytest.mark.skip(reason="With shippable support removed, ci/azp.py needs a mock")
def test_rebuild_failed_and_rebuild_commands():
    """Test ran and failed. /rebuild_failed and /rebuild commands issued, in that order."""
    datafile = 'tests/fixtures/rebuild/3_issue.yml'
    statusfile = 'tests/fixtures/rebuild/3_prstatus.json'
    with get_issue(datafile, statusfile) as iw:
        meta = {
            'is_pullrequest': True,
            'is_needs_revision': False,
            'is_needs_rebase': False,
            'needs_rebuild': False,
            'ci_run_number': 0,
        }
        rbfacts = get_rebuild_command_facts(iw, meta, None)
        assert rbfacts['needs_rebuild']
        assert rbfacts['needs_rebuild_all']
        assert not rbfacts['needs_rebuild_failed']
