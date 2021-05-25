import copy
import shutil
import tempfile
import unittest

from collections import namedtuple

import pytest

from tests.utils.issue_mock import IssueMock
from tests.utils.helpers import get_issue
from ansibullbot.triagers.plugins.component_matching import get_component_match_facts
from ansibullbot.triagers.plugins.shipit import get_automerge_facts
from ansibullbot.triagers.plugins.shipit import get_review_facts
from ansibullbot.triagers.plugins.shipit import get_shipit_facts
from ansibullbot.triagers.plugins.shipit import is_approval
from ansibullbot.wrappers.issuewrapper import IssueWrapper


class ComponentMatcherMock:

    strategies = []
    expected_results = []

    def match(self, issuewrapper):
        return self.expected_results


class HistoryWrapperMock:
    history = None
    def __init__(self):
        self.history = []


class IssueWrapperMock:
    _is_pullrequest = False
    _pr_files = []
    pr_files = []
    _wip = False
    _history = None
    _submitter = 'bob'

    def __init__(self, org, repo, number):
        self._history = HistoryWrapperMock()
        self.org = org
        self.repo = repo
        self.number = number

    def is_pullrequest(self):
        return self._is_pullrequest

    def add_comment(self, user, body):
        payload = {'actor': user, 'event': 'commented', 'body': body}
        self.history.history.append(payload)

    def add_file(self, filename, content):
        mf = MockFile(filename, content=content)
        self._pr_files.append(mf)

    @property
    def wip(self):
        return self._wip

    @property
    def files(self):
        return [x.filename for x in self._pr_files]

    @property
    def history(self):
        return self._history

    @property
    def submitter(self):
        return self._submitter

    @property
    def html_url(self):
        if self.is_pullrequest():
            return 'https://github.com/%s/%s/pulls/%s' % (self.org, self.repo, self.number)
        else:
            return 'https://github.com/%s/%s/issues/%s' % (self.org, self.repo, self.number)


class GitRepoWrapperMock:
    files = []

    def existed(self, filename):
        return True


class MockFile:
    def __init__(self, name, content=''):
        self.filename = name
        self.content = content
        self.additions = 0
        self.deletions = 0
        self.status = None


class MockRepo:
    def __init__(self, repo_path):
        self.repo_path = repo_path

    def get_pullrequest(self, issueid):
        return namedtuple('PullRequest', ['draft', 'get_reviews'])(draft=False, get_reviews=lambda: [])


class GithubWrapperMock:
    def get_request(self, url):
        return []


class TestSuperShipit(unittest.TestCase):

    def test_supershipit_shipit_facts(self):
        # a supershipit should count from a supershipiteer
        IW = IssueWrapperMock('ansible', 'ansible', 1)
        IW.pr_files = [
            MockFile('foo'),
        ]
        IW._is_pullrequest = True
        IW.add_comment('jane', 'shipit')
        meta = {
            'is_module_util': False,
            'is_new_module': False,
            'is_needs_rebase': False,
            'is_needs_revision': False,
            'component_matches': [
                {'repo_filename': 'foo', 'supershipit': ['jane', 'doe']}
            ]
        }
        sfacts = get_shipit_facts(IW, meta, {})
        assert sfacts['shipit']
        assert sfacts['supershipit']
        assert sfacts['shipit_actors'] == []
        assert sfacts['shipit_actors_other'] == ['jane']

    def test_supershipit_shipit_on_all_files(self):
        # count all the supershipits
        IW = IssueWrapperMock('ansible', 'ansible', 1)
        IW.pr_files = [
            MockFile('foo'),
            MockFile('bar'),
        ]
        IW._is_pullrequest = True
        IW.add_comment('jane', 'shipit')
        IW.add_comment('doe', 'shipit')
        meta = {
            'is_module_util': False,
            'is_new_module': False,
            'is_needs_rebase': False,
            'is_needs_revision': False,
            'component_matches': [
                {'repo_filename': 'foo', 'supershipit': ['jane']},
                {'repo_filename': 'bar', 'supershipit': ['doe']}
            ]
        }
        sfacts = get_shipit_facts(IW, meta, {})
        assert sfacts['shipit']
        assert sfacts['supershipit']
        assert sfacts['shipit_actors'] == []
        assert sfacts['shipit_actors_other'] == ['jane', 'doe']

    def test_supershipit_shipit_not_all_files(self):
        # make sure there is supershipit for all files
        IW = IssueWrapperMock('ansible', 'ansible', 1)
        IW.pr_files = [
            MockFile('foo'),
            MockFile('bar'),
        ]
        IW._is_pullrequest = True
        IW.add_comment('jane', 'shipit')
        meta = {
            'is_module_util': False,
            'is_new_module': False,
            'is_needs_rebase': False,
            'is_needs_revision': False,
            'component_matches': [
                {'repo_filename': 'foo', 'supershipit': ['jane']},
                {'repo_filename': 'bar', 'supershipit': ['doe']}
            ]
        }
        sfacts = get_shipit_facts(IW, meta, {})
        assert not sfacts['shipit']
        assert not sfacts['supershipit']
        assert sfacts['shipit_actors_other'] == ['jane']
        assert not sfacts['shipit_actors']

    def test_maintainer_is_not_supershipit(self):
        # a maintainer should not be auto-added as a shipiteer
        IW = IssueWrapperMock('ansible', 'ansible', 1)
        IW.pr_files = [
            MockFile('foo'),
        ]
        IW._is_pullrequest = True
        IW.add_comment('janetainer', 'shipit')
        meta = {
            'is_module_util': False,
            'is_new_module': False,
            'is_needs_rebase': False,
            'is_needs_revision': False,
            'component_maintainers': ['janetainer'],
            'component_matches': [
                {'repo_filename': 'foo', 'maintainers': ['janetainer']}
            ]
        }
        sfacts = get_shipit_facts(IW, meta, {})
        assert not sfacts['shipit']
        assert not sfacts['supershipit']
        assert sfacts['shipit_actors'] == ['janetainer']
        assert not sfacts['shipit_actors_other']
        assert sfacts['shipit_count_maintainer'] == 1
        assert sfacts['shipit_actors'] == ['janetainer']

    def test_core_is_not_supershipit(self):
        # a core team member should not be auto-added as a shipiteer
        IW = IssueWrapperMock('ansible', 'ansible', 1)
        IW.pr_files = [
            MockFile('foo'),
        ]
        IW._is_pullrequest = True
        IW.add_comment('coreperson', 'shipit')
        meta = {
            'is_module_util': False,
            'is_new_module': False,
            'is_needs_rebase': False,
            'is_needs_revision': False,
            'component_matches': [
                {'repo_filename': 'foo', 'supershipit': ['jane', 'doe']}
            ]
        }
        sfacts = get_shipit_facts(IW, meta, {}, core_team=['coreperson'])
        assert not sfacts['supershipit']
        assert not sfacts['shipit']
        assert not sfacts['supershipit']
        assert not sfacts['shipit_actors_other']
        assert sfacts['shipit_actors'] == ['coreperson']

    def test_automerge_community_only(self):
        # automerge should only be allowed if the support is 100% community
        IW = IssueWrapperMock('ansible', 'ansible', 1)
        IW.pr_files = [
            MockFile('foo'),
        ]
        IW._is_pullrequest = True
        meta1 = {
            'is_module_util': False,
            'is_new_module': False,
            'is_needs_rebase': False,
            'is_needs_revision': False,
            'component_support': ['core', 'community'],
            'is_backport': False,
            'merge_commits': False,
            'has_commit_mention': False,
            'is_needs_info': False,
            'has_ci': True,
            'mergeable': True,
            'ci_stale': False,
            'ci_state': 'success',
            'shipit': True,
            'supershipit': True,
            'component_matches': [
                {'repo_filename': 'bar', 'supershipit': ['jane', 'doe'], 'support': 'core'},
                {'repo_filename': 'foo', 'supershipit': ['jane', 'doe'], 'support': 'community'},
            ]
        }
        meta2 = copy.deepcopy(meta1)
        meta2['component_support'] = ['community', 'community']
        meta2['component_matches'][0]['support'] = 'community'

        afacts1 = get_automerge_facts(IW, meta1.copy())
        afacts2 = get_automerge_facts(IW, meta2.copy())

        assert afacts1['automerge'] == False
        assert afacts2['automerge'] == True

    def test_supershipit_changelogs(self):
        # a supershipit should count from a supershipiteer
        # https://github.com/ansible/ansibullbot/issues/1147
        IW = IssueWrapperMock('ansible', 'ansible', 1)
        IW.pr_files = [
            MockFile('foo'),
            MockFile('changelogs/fragments/000-foo-change.yml'),
        ]
        IW._is_pullrequest = True
        IW.add_comment('jane', 'shipit')
        meta = {
            'is_module_util': False,
            'is_new_module': False,
            'is_needs_rebase': False,
            'is_needs_revision': False,
            'component_matches': [
                {'repo_filename': 'foo', 'supershipit': ['jane', 'doe']},
                {'repo_filename': 'changelogs/fragments/000-foo-change.yml'}
            ]
        }
        sfacts = get_shipit_facts(IW, meta, {})

        # don't let the plugin modify the meta
        assert len(meta['component_matches']) == 2

        assert sfacts['shipit']
        assert sfacts['supershipit']
        assert sfacts['shipit_actors'] == []
        assert sfacts['shipit_actors_other'] == ['jane']

    def test_supershipit_deletion_from_sanity_ignore(self):
        '''supershipit should work when lines are deleted from ignore files'''
        IW = IssueWrapperMock('ansible', 'ansible', 1)
        IW.pr_files = [
            MockFile('foo'),
            MockFile('changelogs/fragments/000-foo-change.yml'),
            MockFile('test/sanity/validate-modules/ignore.txt'),
        ]
        IW.pr_files[-1].additions = 0
        IW.pr_files[-1].deletions = 1
        IW._is_pullrequest = True
        IW.add_comment('jane', 'shipit')
        meta = {
            'is_module_util': False,
            'is_new_module': False,
            'is_needs_rebase': False,
            'is_needs_revision': False,
            'component_matches': [
                {'repo_filename': 'foo', 'supershipit': ['jane', 'doe']},
                {'repo_filename': 'changelogs/fragments/000-foo-change.yml'},
                {'repo_filename': 'test/sanity/validate-modules/ignore.txt'}
            ]
        }
        sfacts = get_shipit_facts(IW, meta, {})

        # don't let the plugin modify the meta
        assert len(meta['component_matches']) == 3

        assert sfacts['shipit']
        assert sfacts['supershipit']
        assert sfacts['shipit_actors'] == []
        assert sfacts['shipit_actors_other'] == ['jane']

    def test_supershipit_addition_to_sanity_ignore(self):
        '''supershipit should work when lines are deleted from ignore files'''
        IW = IssueWrapperMock('ansible', 'ansible', 1)
        IW.pr_files = [
            MockFile('foo'),
            MockFile('changelogs/fragments/000-foo-change.yml'),
            MockFile('test/sanity/validate-modules/ignore.txt'),
        ]
        IW.pr_files[-1].additions = 1
        IW.pr_files[-1].deletions = 0
        IW._is_pullrequest = True
        IW.add_comment('jane', 'shipit')
        meta = {
            'is_module_util': False,
            'is_new_module': False,
            'is_needs_rebase': False,
            'is_needs_revision': False,
            'component_matches': [
                {'repo_filename': 'foo', 'supershipit': ['jane', 'doe']},
                {'repo_filename': 'changelogs/fragments/000-foo-change.yml'},
                {'repo_filename': 'test/sanity/validate-modules/ignore.txt'}
            ]
        }
        sfacts = get_shipit_facts(IW, meta, {})

        # don't let the plugin modify the meta
        assert len(meta['component_matches']) == 3

        assert not sfacts['shipit']
        assert not sfacts['supershipit']


class TestShipitRebuildMerge(unittest.TestCase):

    def test_shipit_with_core_rebuild_merge(self):
        # a rebuild_merge should also be a shipit
        IW = IssueWrapperMock('ansible', 'ansible', 1)
        IW._is_pullrequest = True
        IW.add_file('foo', '')
        IW.add_comment('jane', 'shipit')
        IW.add_comment('x', 'rebuild_merge')
        meta = {
            'is_module_util': False,
            'is_new_module': False,
            'is_needs_rebase': False,
            'is_needs_revision': False,
            'component_maintainers': ['jane', 'doe'],
            'component_matches': [
                {'repo_filename': 'foo', 'maintainers': ['jane', 'doe']}
            ]
        }
        core_team = ['x']
        sfacts = get_shipit_facts(IW, meta, {}, core_team=core_team)

        assert sfacts['shipit']
        assert not sfacts['supershipit']
        assert not sfacts['supershipit_actors']
        assert sfacts['shipit_actors'] == ['jane', 'x']
        assert not sfacts['shipit_actors_other']
        assert sfacts['shipit_count_ansible'] == 1
        assert sfacts['shipit_count_maintainer'] == 1
        assert sfacts['shipit_count_other'] == 0
        assert sfacts['shipit_count_vtotal'] == 2

    def test_shipit_with_noncore_rebuild_merge(self):
        # a !core rebuild_merge should not be a shipit?
        IW = IssueWrapperMock('ansible', 'ansible', 1)
        IW._is_pullrequest = True
        IW.add_file('foo', '')
        IW.add_comment('jane', 'shipit')
        IW.add_comment('z', 'rebuild_merge')
        meta = {
            'is_module_util': False,
            'is_new_module': False,
            'is_needs_rebase': False,
            'is_needs_revision': False,
            'component_maintainers': ['jane', 'doe'],
            'component_matches': [
                {'repo_filename': 'foo', 'maintainers': ['jane', 'doe']}
            ]
        }
        core_team = ['x']
        sfacts = get_shipit_facts(IW, meta, {}, core_team=core_team)

        assert not sfacts['shipit']
        assert not sfacts['supershipit']
        assert not sfacts['supershipit_actors']
        assert sfacts['shipit_actors'] == ['jane']
        assert sfacts['shipit_actors_other'] == ['z']
        assert sfacts['shipit_count_ansible'] == 0
        assert sfacts['shipit_count_maintainer'] == 1
        assert sfacts['shipit_count_other'] == 1
        assert sfacts['shipit_count_vtotal'] == 2


class TestShipitFacts(unittest.TestCase):

    def setUp(self):
        self.meta = {
            'is_new_module': False,
            'module_match': {
                'namespace': 'system',
                'maintainers': ['abulimov'],
            },
            'is_needs_revision': False,  # always set by needs_revision plugin (get_needs_revision_facts)
            'is_needs_rebase': False,
            'is_module_util': False,
        }

    def test_submitter_is_maintainer(self):
        """
        Submitter is a namespace maintainer: approval must be automatically
        added
        """
        datafile = 'tests/fixtures/shipit/0_issue.yml'
        statusfile = 'tests/fixtures/shipit/0_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            _meta = self.meta.copy()
            _meta['component_maintainers'] = []
            _meta['component_namespace_maintainers'] = ['LinusU', 'mscherer']

            facts = get_shipit_facts(iw, _meta, {}, core_team=['bcoca'], botnames=['ansibot'])

            self.assertEqual(iw.submitter, 'mscherer')
            self.assertEqual(['LinusU', 'mscherer'], facts['community_usernames'])
            self.assertEqual(['mscherer'], facts['shipit_actors'])
            self.assertEqual(facts['shipit_count_ansible'], 0)     # bcoca
            self.assertEqual(facts['shipit_count_maintainer'], 0)  # abulimov
            self.assertEqual(facts['shipit_count_community'], 1)   # LinusU, mscherer
            self.assertFalse(facts['shipit'])

    def test_submitter_is_core_team_and_maintainer(self):
        """
        Submitter is a namespace maintainer *and* a core team member: approval
        must be automatically added
        https://github.com/ansible/ansible/pull/21620
        """
        datafile = 'tests/fixtures/shipit/1_issue.yml'
        statusfile = 'tests/fixtures/shipit/1_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            _meta = self.meta.copy()
            _meta['component_maintainers'] = []
            _meta['component_namespace_maintainers'] = ['LinusU']

            facts = get_shipit_facts(iw, _meta, {}, core_team=['bcoca', 'mscherer'], botnames=['ansibot'])

            self.assertEqual(iw.submitter, 'mscherer')
            self.assertEqual(['LinusU'], facts['community_usernames'])
            self.assertEqual(['LinusU', 'mscherer'], facts['shipit_actors'])
            self.assertEqual(facts['shipit_count_ansible'], 1)     # bcoca, mscherer
            self.assertEqual(facts['shipit_count_maintainer'], 0)  # abulimov
            self.assertEqual(facts['shipit_count_community'], 1)   # LinusU
            self.assertTrue(facts['shipit'])

    def needs_rebase_or_revision_prevent_shipit(self, meta):
        datafile = 'tests/fixtures/shipit/1_issue.yml'
        statusfile = 'tests/fixtures/shipit/1_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            facts = get_shipit_facts(iw, meta, {}, core_team=['bcoca', 'mscherer'], botnames=['ansibot'])

            self.assertEqual(iw.submitter, 'mscherer')
            self.assertFalse(facts['community_usernames'])
            self.assertFalse(facts['shipit_actors'])
            self.assertEqual(facts['shipit_count_ansible'], 0)
            self.assertEqual(facts['shipit_count_maintainer'], 0)
            self.assertEqual(facts['shipit_count_community'], 0)
            self.assertFalse(facts['shipit'])

    def test_needs_rebase_prevent_shipit(self):
        """
        needs_rebase label prevents shipit label to be added
        """
        meta = copy.deepcopy(self.meta)
        meta['is_needs_rebase'] = True
        self.needs_rebase_or_revision_prevent_shipit(meta)

    def test_needs_revision_prevent_shipit(self):
        """
        needs_revision label prevents shipit label to be added
        """
        meta = copy.deepcopy(self.meta)
        meta['is_needs_revision'] = True
        self.needs_rebase_or_revision_prevent_shipit(meta)


class TestIsApproval(unittest.TestCase):

    def test_is_approval(self):
        self.assertTrue(is_approval('shipit'))
        self.assertTrue(is_approval('+1'))
        self.assertTrue(is_approval('LGTM'))

        self.assertTrue(is_approval(' shipit '))
        self.assertTrue(is_approval("\tshipit\t"))
        self.assertTrue(is_approval("\tshipit\n"))
        self.assertTrue(is_approval('Hey, LGTM !'))

        self.assertFalse(is_approval(':+1:'))
        self.assertFalse(is_approval('lgtm'))
        self.assertFalse(is_approval('Shipit'))
        self.assertFalse(is_approval('shipit!'))

        self.assertFalse(is_approval('shipits'))
        self.assertFalse(is_approval('LGTM.'))
        self.assertFalse(is_approval('Looks good to me'))


class TestOwnerPR(unittest.TestCase):

    def setUp(self):
        self.meta = {
            'is_needs_revision': False,  # always set by needs_revision plugin (get_needs_revision_facts)
            'is_needs_rebase': False,
        }

    def test_owner_pr_submitter_is_maintainer_one_module_utils_file_updated(self):
        """
        Submitter is a maintainer: ensure owner_pr is set (only one file below module_utils updated)
        """
        botmeta_files = {'lib/ansible/module_utils/foo/bar.py': {'maintainers': ['ElsA', 'Oliver']}}
        datafile = 'tests/fixtures/shipit/2_issue.yml'
        statusfile = 'tests/fixtures/shipit/2_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            iw._pr_files = [MockFile('lib/ansible/module_utils/foo/bar.py')]
            # need to give the wrapper a list of known files to compare against
            iw.gitrepo = GitRepoWrapperMock()
            iw.gitrepo.files.append('lib/ansible/modules/foo/bar.py')

            # predefine what the matcher is going to return
            CM = ComponentMatcherMock()
            CM.expected_results = [
                {
                    'repo_filename': 'lib/ansible/module_utils/foo/bar.py',
                    'labels': [],
                    'support': None,
                    'maintainers': ['ElsA', 'Oliver'],
                    'notify': ['ElsA', 'Oliver'],
                    'ignore': [],
                }
            ]

            meta = self.meta.copy()
            iw._commits = []
            meta.update(get_component_match_facts(iw, CM, []))
            facts = get_shipit_facts(iw, meta, botmeta_files, core_team=['bcoca', 'mscherer'], botnames=['ansibot'])

            self.assertEqual(iw.submitter, 'ElsA')
            self.assertTrue(facts['owner_pr'])

    def test_owner_pr_submitter_is_maintainer_one_modules_file_updated(self):
        """
        Submitter is a maintainer: ensure owner_pr is set (only one file below modules updated)
        """
        botmeta_files = {'lib/ansible/modules/foo/bar.py': {'maintainers': ['ElsA', 'mscherer']}}
        CM = ComponentMatcherMock()
        CM.expected_results = [
            {
                'repo_filename': 'lib/ansible/modules/foo/bar.py',
                'labels': [],
                'support': None,
                'maintainers': ['ElsA', 'mscherer'],
                'notify': ['ElsA', 'mscherer'],
                'ignore': [],
            }
        ]

        meta = self.meta.copy()

        datafile = 'tests/fixtures/shipit/0_issue.yml'
        statusfile = 'tests/fixtures/shipit/0_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            iw._pr_files = [MockFile('lib/ansible/modules/foo/bar.py')]
            iw.gitrepo = GitRepoWrapperMock()
            iw.gitrepo.files.append('lib/ansible/modules/foo/bar.py')

            meta.update(get_component_match_facts(iw, CM, []))
            facts = get_shipit_facts(iw, meta, botmeta_files, core_team=['bcoca'], botnames=['ansibot'])

        self.assertEqual(iw.submitter, 'mscherer')
        self.assertTrue(facts['owner_pr'])

    @pytest.mark.skip(reason="FIXME")
    def test_owner_pr_submitter_is_maintainer_new_module(self):
        """
        Submitter is a maintainer: pull request adds a new module: ensure owner_pr is False
        """
        botmeta_files = {'lib/ansible/modules/foo/bar.py': {'maintainers': ['ElsA', 'mscherer']}}
        CM = ComponentMatcherMock()
        CM.expected_results = [
            {
                'repo_filename': 'lib/ansible/modules/foo/bar.py',
                'labels': [],
                'support': None,
                'maintainers': ['ElsA', 'mscherer'],
                'notify': ['ElsA', 'mscherer'],
                'ignore': [],
            }
        ]

        meta = self.meta.copy()

        datafile = 'tests/fixtures/shipit/0_issue.yml'
        statusfile = 'tests/fixtures/shipit/0_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            iw.pr_files = [MockFile('lib/ansible/modules/foo/bar.py')]
            iw.gitrepo = GitRepoWrapperMock()

            meta.update(get_component_match_facts(iw, CM, []))
            facts = get_shipit_facts(iw, meta, botmeta_files, core_team=['bcoca'], botnames=['ansibot'])

        self.assertEqual(iw.submitter, 'mscherer')
        self.assertFalse(facts['owner_pr'])

    def test_owner_pr_submitter_is_not_maintainer_of_all_updated_files(self):
        """
        PR updates 2 files below module_utils, submitter is a maintainer from only one: ensure owner_pr isn't set
        """
        botmeta_files = {
            'lib/ansible/module_utils/foo/bar.py': {'maintainers': ['ElsA', 'Oliver']},
            'lib/ansible/module_utils/baz/bar.py': {'maintainers': ['TiTi', 'ZaZa']},
        }
        CM = ComponentMatcherMock()
        CM.expected_results = [
            {
                'repo_filename': 'lib/ansible/module_utils/foo/bar.py',
                'labels': [],
                'support': None,
                'maintainers': ['ElsA', 'Oliver'],
                'notify': ['ElsA', 'Oliver'],
                'ignore': [],
            },
            {
                'repo_filename': 'lib/ansible/modules/baz/bar.py',
                'labels': [],
                'support': None,
                'maintainers': ['TiTi', 'ZaZa'],
                'notify': ['TiTi', 'ZaZa'],
                'ignore': [],
            }
        ]

        issue = IssueMock('/dev/null')
        issue.user.login = 'ElsA'
        issue.html_url = 'https://github.com/ansible/ansible/pull/123'
        cachedir = tempfile.mkdtemp()
        gh = GithubWrapperMock()
        iw = IssueWrapper(cachedir=cachedir, issue=issue, github=gh)
        iw._pr_files = [
            MockFile('lib/ansible/module_utils/foo/bar.py'),
            MockFile('lib/ansible/module_utils/baz/bar.py')
        ]
        iw.gitrepo = GitRepoWrapperMock()
        iw.repo = MockRepo(repo_path='ansible/ansible')

        meta = self.meta.copy()
        iw._commits = []
        meta.update(get_component_match_facts(iw, CM, []))
        facts = get_shipit_facts(iw, meta, botmeta_files, core_team=['bcoca', 'mscherer'], botnames=['ansibot'])
        shutil.rmtree(cachedir)

        self.assertEqual(iw.submitter, 'ElsA')
        self.assertFalse(facts['owner_pr'])

    def test_owner_pr_module_utils_and_modules_updated_submitter_maintainer_1(self):
        """
        PR updates 2 files (one below modules, the other below module_utils),
        submitter is a maintainer from both, check that owner_pr is set.
        Submitter is maintainer from module file.
        """
        botmeta_files = {
            'lib/ansible/modules/foo/bar.py': {'maintainers': ['ElsA', 'mscherer']},
            'lib/ansible/module_utils/baz/bar.py': {'maintainers': ['TiTi', 'ZaZa']},
        }
        CM = ComponentMatcherMock()
        CM.expected_results = [
            {
                'repo_filename': 'lib/ansible/module_utils/foo/bar.py',
                'labels': [],
                'support': None,
                'maintainers': ['ElsA', 'mscherer'],
                'notify': ['ElsA', 'mscherer'],
                'ignore': [],
            },
            {
                'repo_filename': 'lib/ansible/modules/baz/bar.py',
                'labels': [],
                'support': None,
                'maintainers': ['TiTi', 'ZaZa'],
                'notify': ['TiTi', 'ZaZa'],
                'ignore': [],
            }
        ]

        meta = self.meta.copy()

        datafile = 'tests/fixtures/shipit/0_issue.yml'
        statusfile = 'tests/fixtures/shipit/0_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            iw._pr_files = [
                MockFile('lib/ansible/modules/foo/bar.py'),
                MockFile('lib/ansible/module_utils/baz/bar.py')
            ]
            iw.gitrepo = GitRepoWrapperMock()
            iw.gitrepo.files = ['lib/ansible/modules/foo/bar.py', 'lib/ansible/module_utils/baz/bar.py']

            iw._commits = []
            meta.update(get_component_match_facts(iw, CM, []))
            facts = get_shipit_facts(iw, meta, botmeta_files, core_team=['bcoca', 'mscherer'], botnames=['ansibot'])

        self.assertEqual(iw.submitter, 'mscherer')
        self.assertFalse(facts['owner_pr'])

    @pytest.mark.skip(reason="FIXME")
    def test_owner_pr_module_utils_and_modules_updated_submitter_maintainer_2(self):
        """
        PR updates 2 files (one below modules, the other below module_utils),
        submitter is a maintainer from both, check that owner_pr is set.
        Submitter is maintainer from module_utils file.
        """
        botmeta_files = {
            'lib/ansible/modules/foo/bar.py': {'maintainers': ['ElsA', 'ZaZa']},
            'lib/ansible/module_utils/baz/bar.py': {'maintainers': ['TiTi', 'mscherer']},
        }
        CM = ComponentMatcherMock()
        CM.expected_results = [
            {
                'repo_filename': 'lib/ansible/module_utils/foo/bar.py',
                'labels': [],
                'support': None,
                'maintainers': ['ElsA', 'mscherer'],
                'notify': ['ElsA', 'mscherer'],
                'ignore': [],
            },
            {
                'repo_filename': 'lib/ansible/modules/baz/bar.py',
                'labels': [],
                'support': None,
                'maintainers': ['TiTi', 'ZaZa'],
                'notify': ['TiTi', 'ZaZa'],
                'ignore': [],
            }
        ]

        meta = self.meta.copy()

        datafile = 'tests/fixtures/shipit/0_issue.yml'
        statusfile = 'tests/fixtures/shipit/0_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            iw.pr_files = [
                MockFile('lib/ansible/modules/foo/bar.py'),
                MockFile('lib/ansible/module_utils/baz/bar.py')
            ]
            meta.update(get_component_match_facts(iw, CM, []))
            facts = get_shipit_facts(iw, meta, botmeta_files, core_team=['bcoca'], botnames=['ansibot'])

        self.assertEqual(iw.submitter, 'mscherer')
        self.assertFalse(facts['owner_pr'])

    def test_owner_pr_submitter_is_maintainer_one_module_file_updated_changelog(self):
        """
        Submitter is a maintainer: ensure owner_pr is set even if changelog fragment is present
        """
        botmeta_files = {'lib/ansible/modules/foo/bar.py': {'maintainers': ['ElsA', 'Oliver']}}
        datafile = 'tests/fixtures/shipit/2_issue.yml'
        statusfile = 'tests/fixtures/shipit/2_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            iw._pr_files = [
                MockFile('lib/ansible/modules/foo/bar.py'),
                MockFile('changelogs/fragments/00000-fragment.yaml')
            ]
            # need to give the wrapper a list of known files to compare against
            iw.gitrepo = GitRepoWrapperMock()
            iw.gitrepo.files.append('lib/ansible/modules/foo/bar.py')

            # predefine what the matcher is going to return
            CM = ComponentMatcherMock()
            CM.expected_results = [
                {
                    'repo_filename': 'lib/ansible/modules/foo/bar.py',
                    'labels': [],
                    'support': None,
                    'maintainers': ['ElsA', 'Oliver'],
                    'notify': ['ElsA', 'Oliver'],
                    'ignore': [],
                }
            ]

            meta = self.meta.copy()
            iw._commits = []
            meta.update(get_component_match_facts(iw, CM, []))
            facts = get_shipit_facts(iw, meta, botmeta_files, core_team=['bcoca', 'mscherer'], botnames=['ansibot'])

            self.assertEqual(iw.submitter, 'ElsA')
            self.assertTrue(facts['owner_pr'])


class TestReviewFacts(unittest.TestCase):

    def setUp(self):
        self.meta = {
            'is_needs_revision': False,  # always set by needs_revision plugin (get_needs_revision_facts)
            'is_needs_rebase': False,
            'is_needs_info': False,  # set by needs_info_template_facts
        }

    def test_review_facts_are_defined_module_utils(self):
        botmeta_files = {
            'lib/ansible/module_utils': {'support': 'community'},
            'lib/ansible/modules/foo/bar.py': {'maintainers': ['ElsA', 'ZaZa']},
            'lib/ansible/module_utils/baz/bar.py': {'maintainers': ['TiTi', 'mscherer']},
        }
        datafile = 'tests/fixtures/shipit/2_issue.yml'
        statusfile = 'tests/fixtures/shipit/2_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            iw._pr_files = [MockFile('lib/ansible/module_utils/foo/bar.py')]
            # need to give the wrapper a list of known files to compare against
            iw.gitrepo = GitRepoWrapperMock()
            iw.gitrepo.files.append('lib/ansible/modules/foo/bar.py')

            # predefine what the matcher is going to return
            CM = ComponentMatcherMock()
            CM.expected_results = [
                {
                    'repo_filename': 'lib/ansible/module_utils/foo/bar.py',
                    'labels': [],
                    'support': None,
                    'maintainers': ['ElsA', 'Oliver'],
                    'notify': ['ElsA', 'Oliver'],
                    'ignore': [],
                }
            ]

            meta = self.meta.copy()
            iw._commits = []
            meta.update(get_component_match_facts(iw, CM, []))
            meta.update(get_shipit_facts(iw, meta, botmeta_files, core_team=['bcoca'], botnames=['ansibot']))
            facts = get_review_facts(iw, meta)

        self.assertTrue(facts['community_review'])
        self.assertFalse(facts['core_review'])
        self.assertFalse(facts['committer_review'])


class TestAutomergeFacts(unittest.TestCase):

    def test_automerge_changelog_fragment(self):
        iw = IssueWrapperMock('ansible', 'ansible', 1)
        iw._is_pullrequest = True
        iw.pr_files = [
            MockFile('lib/ansible/modules/foo/bar.py'),
            MockFile('changelogs/fragments/00000-fragment.yaml')
        ]
        meta = {
            'is_module_util': False,
            'is_new_module': False,
            'is_needs_rebase': False,
            'is_needs_revision': False,
            'component_support': ['community'],
            'is_backport': False,
            'merge_commits': False,
            'has_commit_mention': False,
            'is_needs_info': False,
            'has_ci': True,
            'mergeable': True,
            'ci_stale': False,
            'ci_state': 'success',
            'shipit': True,
            'supershipit': False,
            'is_new_directory': False,
            'is_module': True,
            'module_match': {
                'namespace': 'foo',
                'maintainers': ['ghuser1'],
            },
        }

        afacts = get_automerge_facts(iw, meta)

        self.assertTrue(afacts['automerge'])

    def test_automerge_deletion_from_ignore(self):
        iw = IssueWrapperMock('ansible', 'ansible', 1)
        iw._is_pullrequest = True
        mfile = MockFile('test/sanity/validate-modules/ignore.txt')
        mfile.deletions = 1
        iw.pr_files = [mfile]
        meta = {
            'is_module_util': False,
            'is_new_module': False,
            'is_needs_rebase': False,
            'is_needs_revision': False,
            'component_support': ['community'],
            'is_backport': False,
            'merge_commits': False,
            'has_commit_mention': False,
            'is_needs_info': False,
            'has_ci': True,
            'mergeable': True,
            'ci_stale': False,
            'ci_state': 'success',
            'shipit': True,
            'supershipit': False,
            'is_new_directory': False,
            'is_module': True,
            'module_match': {
                'namespace': 'foo',
                'maintainers': ['ghuser1'],
            },
        }

        afacts = get_automerge_facts(iw, meta)

        self.assertTrue(afacts['automerge'])

    def test_automerge_addition_to_ignore(self):
        iw = IssueWrapperMock('ansible', 'ansible', 1)
        iw._is_pullrequest = True
        mfile = MockFile('test/sanity/validate-modules/ignore.txt')
        mfile.additions = 1
        mfile.status = 'added'
        iw.pr_files = [mfile]
        meta = {
            'is_module_util': False,
            'is_new_module': False,
            'is_needs_rebase': False,
            'is_needs_revision': False,
            'component_support': ['community'],
            'is_backport': False,
            'merge_commits': False,
            'has_commit_mention': False,
            'is_needs_info': False,
            'has_ci': True,
            'mergeable': True,
            'ci_stale': False,
            'ci_state': 'success',
            'shipit': True,
            'supershipit': False,
            'is_new_directory': False,
            'is_module': True,
            'module_match': {
                'namespace': 'foo',
                'maintainers': ['ghuser1'],
            },
            'component_matches': [
                {
                    'repo_filename': 'test/sanity/validate-modules/ignore.txt',
                    'support': 'core'
                }
            ]
        }

        afacts = get_automerge_facts(iw, meta)

        self.assertFalse(afacts['automerge'])
