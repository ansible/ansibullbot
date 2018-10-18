#!/usr/bin/env python

import copy
import textwrap
import unittest

import six
six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock

from tests.utils.issue_mock import IssueMock
from tests.utils.helpers import get_issue
from tests.utils.module_indexer_mock import create_indexer
from ansibullbot.triagers.plugins.component_matching import get_component_match_facts
from ansibullbot.triagers.plugins.shipit import get_review_facts, get_shipit_facts, is_approval
from ansibullbot.wrappers.issuewrapper import IssueWrapper


class ComponentMatcherMock(object):

    strategies = []
    expected_results = []

    def match(self, issuewrapper):
        return self.expected_results


class ModuleIndexerMock(object):

    def __init__(self, namespace_maintainers):
        self.namespace_maintainers = namespace_maintainers

    def get_maintainers_for_namespace(self, namespace):
        return self.namespace_maintainers


class FileIndexerMock(object):

    files = []

    def find_component_matches_by_file(self, filenames):
        return []

    def isnewdir(self, path):
        return False

    def get_component_labels(self, files, valid_labels=None):
        return []


class MockFile(object):
    def __init__(self, name):
        self.filename = name


class MockRepo(object):
    def __init__(self, repo_path):
        self.repo_path = repo_path


class TestShipitFacts(unittest.TestCase):

    def setUp(self):
        self.meta = {
            u'is_new_module': False,
            u'module_match': {
                u'namespace': u'system',
                u'maintainers': [u'abulimov'],
            },
            u'is_needs_revision': False,  # always set by needs_revision plugin (get_needs_revision_facts)
            u'is_needs_rebase': False,
            u'is_module_util': False,
        }

    def test_submitter_is_maintainer(self):
        """
        Submitter is a namespace maintainer: approval must be automatically
        added
        """
        datafile = u'tests/fixtures/shipit/0_issue.yml'
        statusfile = u'tests/fixtures/shipit/0_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            namespace_maintainers = [u'LinusU', u'mscherer']

            _meta = self.meta.copy()
            _meta[u'component_maintainers'] = []
            _meta[u'component_namespace_maintainers'] = namespace_maintainers[:]

            facts = get_shipit_facts(iw, _meta, ModuleIndexerMock(namespace_maintainers), core_team=[u'bcoca'], botnames=[u'ansibot'])

            self.assertEqual(iw.submitter, u'mscherer')
            self.assertEqual([u'LinusU', u'mscherer'], facts[u'community_usernames'])
            self.assertEqual([u'mscherer'], facts[u'shipit_actors'])
            self.assertEqual(facts[u'shipit_count_ansible'], 0)     # bcoca
            self.assertEqual(facts[u'shipit_count_maintainer'], 0)  # abulimov
            self.assertEqual(facts[u'shipit_count_community'], 1)   # LinusU, mscherer
            self.assertFalse(facts[u'shipit'])

    def test_submitter_is_core_team_and_maintainer(self):
        """
        Submitter is a namespace maintainer *and* a core team member: approval
        must be automatically added
        https://github.com/ansible/ansible/pull/21620
        """
        datafile = u'tests/fixtures/shipit/1_issue.yml'
        statusfile = u'tests/fixtures/shipit/1_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            namespace_maintainers = [u'LinusU']

            _meta = self.meta.copy()
            _meta[u'component_maintainers'] = []
            _meta[u'component_namespace_maintainers'] = namespace_maintainers[:]

            facts = get_shipit_facts(iw, _meta, ModuleIndexerMock(namespace_maintainers), core_team=[u'bcoca', u'mscherer'], botnames=[u'ansibot'])

            self.assertEqual(iw.submitter, u'mscherer')
            self.assertEqual([u'LinusU'], facts[u'community_usernames'])
            self.assertEqual([u'LinusU', u'mscherer'], facts[u'shipit_actors'])
            self.assertEqual(facts[u'shipit_count_ansible'], 1)     # bcoca, mscherer
            self.assertEqual(facts[u'shipit_count_maintainer'], 0)  # abulimov
            self.assertEqual(facts[u'shipit_count_community'], 1)   # LinusU
            self.assertTrue(facts[u'shipit'])

    def needs_rebase_or_revision_prevent_shipit(self, meta):
        datafile = u'tests/fixtures/shipit/1_issue.yml'
        statusfile = u'tests/fixtures/shipit/1_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            namespace_maintainers = [u'LinusU']

            facts = get_shipit_facts(iw, meta, ModuleIndexerMock(namespace_maintainers), core_team=[u'bcoca', u'mscherer'], botnames=[u'ansibot'])

            self.assertEqual(iw.submitter, u'mscherer')
            self.assertFalse(facts[u'community_usernames'])
            self.assertFalse(facts[u'shipit_actors'])
            self.assertEqual(facts[u'shipit_count_ansible'], 0)
            self.assertEqual(facts[u'shipit_count_maintainer'], 0)
            self.assertEqual(facts[u'shipit_count_community'], 0)
            self.assertFalse(facts[u'shipit'])

    def test_needs_rebase_prevent_shipit(self):
        """
        needs_rebase label prevents shipit label to be added
        """
        meta = copy.deepcopy(self.meta)
        meta[u'is_needs_rebase'] = True
        self.needs_rebase_or_revision_prevent_shipit(meta)

    def test_needs_revision_prevent_shipit(self):
        """
        needs_revision label prevents shipit label to be added
        """
        meta = copy.deepcopy(self.meta)
        meta[u'is_needs_revision'] = True
        self.needs_rebase_or_revision_prevent_shipit(meta)


class TestIsApproval(unittest.TestCase):

    def test_is_approval(self):
        self.assertTrue(is_approval(u'shipit'))
        self.assertTrue(is_approval(u'+1'))
        self.assertTrue(is_approval(u'LGTM'))

        self.assertTrue(is_approval(u' shipit '))
        self.assertTrue(is_approval(u"\tshipit\t"))
        self.assertTrue(is_approval(u"\tshipit\n"))
        self.assertTrue(is_approval(u'Hey, LGTM !'))

        self.assertFalse(is_approval(u':+1:'))
        self.assertFalse(is_approval(u'lgtm'))
        self.assertFalse(is_approval(u'Shipit'))
        self.assertFalse(is_approval(u'shipit!'))

        self.assertFalse(is_approval(u'shipits'))
        self.assertFalse(is_approval(u'LGTM.'))
        self.assertFalse(is_approval(u'Looks good to me'))


class TestOwnerPR(unittest.TestCase):

    def setUp(self):
        self.meta = {
            u'is_needs_revision': False,  # always set by needs_revision plugin (get_needs_revision_facts)
            u'is_needs_rebase': False,
        }

    def test_owner_pr_submitter_is_maintainer_one_module_utils_file_updated(self):
        """
        Submitter is a maintainer: ensure owner_pr is set (only one file below module_utils updated)
        """
        BOTMETA = u"""
        ---
        macros:
            modules: lib/ansible/modules
            module_utils: lib/ansible/module_utils
        files:
            $module_utils/foo/bar.py:
                maintainers: ElsA Oliver
        """

        modules = {u'lib/ansible/module_utils/foo/bar.py': None}
        module_indexer = create_indexer(textwrap.dedent(BOTMETA), modules)

        self.assertEqual(len(module_indexer.modules), 2)  # ensure only fake data are loaded
        self.assertEqual(sorted(module_indexer.botmeta[u'files'][u'lib/ansible/module_utils/foo/bar.py'][u'maintainers']), [u'ElsA', u'Oliver'])


        datafile = u'tests/fixtures/shipit/2_issue.yml'
        statusfile = u'tests/fixtures/shipit/2_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            iw.pr_files = [MockFile(u'lib/ansible/module_utils/foo/bar.py')]
            # need to give the wrapper a list of known files to compare against
            iw.file_indexer = FileIndexerMock()
            iw.file_indexer.files.append(u'lib/ansible/modules/foo/bar.py')

            # predefine what the matcher is going to return
            CM = ComponentMatcherMock()
            CM.expected_results = [
                {
                    u'repo_filename': u'lib/ansible/module_utils/foo/bar.py',
                    u'labels': [],
                    u'support': None,
                    u'maintainers': [u'ElsA', u'Oliver'],
                    u'notify': [u'ElsA', u'Oliver'],
                    u'ignore': [],
                }
            ]

            meta = self.meta.copy()
            iw._commits = []
            meta.update(get_component_match_facts(iw, CM, []))
            facts = get_shipit_facts(iw, meta, module_indexer, core_team=[u'bcoca', u'mscherer'], botnames=[u'ansibot'])

            self.assertEqual(iw.submitter, u'ElsA')
            self.assertTrue(facts[u'owner_pr'])

    def test_owner_pr_submitter_is_maintainer_one_modules_file_updated(self):
        """
        Submitter is a maintainer: ensure owner_pr is set (only one file below modules updated)
        """
        BOTMETA = u"""
        ---
        macros:
            modules: lib/ansible/modules
            module_utils: lib/ansible/module_utils
        files:
            $modules/foo/bar.py:
                maintainers: ElsA mscherer
        """

        modules = {u'lib/ansible/modules/foo/bar.py': None}
        module_indexer = create_indexer(textwrap.dedent(BOTMETA), modules)

        self.assertEqual(len(module_indexer.modules), 2)  # ensure only fake data are loaded
        self.assertEqual(sorted(module_indexer.botmeta[u'files'][u'lib/ansible/modules/foo/bar.py'][u'maintainers']), [u'ElsA', u'mscherer'])

        CM = ComponentMatcherMock()
        CM.expected_results = [
            {
                u'repo_filename': u'lib/ansible/modules/foo/bar.py',
                u'labels': [],
                u'support': None,
                u'maintainers': [u'ElsA', u'mscherer'],
                u'notify': [u'ElsA', u'mscherer'],
                u'ignore': [],
            }
        ]

        meta = self.meta.copy()

        datafile = u'tests/fixtures/shipit/0_issue.yml'
        statusfile = u'tests/fixtures/shipit/0_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            iw.pr_files = [MockFile(u'lib/ansible/modules/foo/bar.py')]
            iw.file_indexer = FileIndexerMock()
            iw.file_indexer.files.append(u'lib/ansible/modules/foo/bar.py')

            meta.update(get_component_match_facts(iw, CM, []))
            facts = get_shipit_facts(iw, meta, module_indexer, core_team=[u'bcoca'], botnames=[u'ansibot'])

        self.assertEqual(iw.submitter, u'mscherer')
        self.assertTrue(facts[u'owner_pr'])

    def test_owner_pr_submitter_is_maintainer_new_module(self):
        """
        Submitter is a maintainer: pull request adds a new module: ensure owner_pr is False
        """
        BOTMETA = u"""
        ---
        macros:
            modules: lib/ansible/modules
            module_utils: lib/ansible/module_utils
        files:
            $modules/foo/bar.py:
                maintainers: ElsA mscherer
        """

        modules = {}  # new module
        module_indexer = create_indexer(textwrap.dedent(BOTMETA), modules)

        self.assertEqual(len(module_indexer.modules), 1)  # ensure only fake data are loaded
        # Ensure that BOTMETA.yml updates doesn't interfere
        self.assertEqual(sorted(module_indexer.botmeta[u'files'][u'lib/ansible/modules/foo/bar.py'][u'maintainers']), [u'ElsA', u'mscherer'])

        CM = ComponentMatcherMock()
        CM.expected_results = [
            {
                u'repo_filename': u'lib/ansible/modules/foo/bar.py',
                u'labels': [],
                u'support': None,
                u'maintainers': [u'ElsA', u'mscherer'],
                u'notify': [u'ElsA', u'mscherer'],
                u'ignore': [],
            }
        ]

        meta = self.meta.copy()

        datafile = u'tests/fixtures/shipit/0_issue.yml'
        statusfile = u'tests/fixtures/shipit/0_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            iw.pr_files = [MockFile(u'lib/ansible/modules/foo/bar.py')]
            iw.file_indexer = FileIndexerMock()

            meta.update(get_component_match_facts(iw, CM, []))
            facts = get_shipit_facts(iw, meta, module_indexer, core_team=[u'bcoca'], botnames=[u'ansibot'])

        self.assertEqual(iw.submitter, u'mscherer')
        self.assertFalse(facts[u'owner_pr'])

    #@unittest.skip('disabled')
    def test_owner_pr_submitter_is_not_maintainer_of_all_updated_files(self):
        """
        PR updates 2 files below module_utils, submitter is a maintainer from only one: ensure owner_pr isn't set
        """
        BOTMETA = u"""
        ---
        macros:
            modules: lib/ansible/modules
            module_utils: lib/ansible/module_utils
        files:
            $module_utils/foo/bar.py:
                maintainers: ElsA Oliver
            $module_utils/baz/bar.py:
                maintainers: TiTi ZaZa
        """

        module_indexer = create_indexer(textwrap.dedent(BOTMETA), {})

        self.assertEqual(len(module_indexer.modules), 1)  # ensure only fake data are loaded
        self.assertEqual(sorted(module_indexer.botmeta[u'files'][u'lib/ansible/module_utils/foo/bar.py'][u'maintainers']), [u'ElsA', u'Oliver'])
        self.assertEqual(sorted(module_indexer.botmeta[u'files'][u'lib/ansible/module_utils/baz/bar.py'][u'maintainers']), [u'TiTi', u'ZaZa'])

        CM = ComponentMatcherMock()
        CM.expected_results = [
            {
                u'repo_filename': u'lib/ansible/module_utils/foo/bar.py',
                u'labels': [],
                u'support': None,
                u'maintainers': [u'ElsA', u'Oliver'],
                u'notify': [u'ElsA', u'Oliver'],
                u'ignore': [],
            },
            {
                u'repo_filename': u'lib/ansible/modules/baz/bar.py',
                u'labels': [],
                u'support': None,
                u'maintainers': [u'TiTi', u'ZaZa'],
                u'notify': [u'TiTi', u'ZaZa'],
                u'ignore': [],
            }
        ]

        issue = IssueMock(u'/dev/null')
        issue.user.login = u'ElsA'
        issue.html_url = u'https://github.com/ansible/ansible/pull/123'
        iw = IssueWrapper(cachedir="", issue=issue)
        iw.pr_files = [
            MockFile(u'lib/ansible/module_utils/foo/bar.py'),
            MockFile(u'lib/ansible/module_utils/baz/bar.py')
        ]
        iw.file_indexer = FileIndexerMock()
        iw.repo = MockRepo(repo_path='ansible/ansible')

        meta = self.meta.copy()
        iw._commits = []
        meta.update(get_component_match_facts(iw, CM, []))
        facts = get_shipit_facts(iw, meta, module_indexer, core_team=[u'bcoca', u'mscherer'], botnames=[u'ansibot'])

        self.assertEqual(iw.submitter, u'ElsA')
        self.assertFalse(facts[u'owner_pr'])

    def test_owner_pr_module_utils_and_modules_updated_submitter_maintainer_1(self):
        """
        PR updates 2 files (one below modules, the other below module_utils),
        submitter is a maintainer from both, check that owner_pr is set.
        Submitter is maintainer from module file.
        """
        BOTMETA = u"""
        ---
        macros:
            modules: lib/ansible/modules
            module_utils: lib/ansible/module_utils
        files:
            $modules/foo/bar.py:
                maintainers: ElsA mscherer
            $module_utils/baz/bar.py:
                maintainers: TiTi ZaZa
        """

        modules = {u'lib/ansible/modules/foo/bar.py': None}
        module_indexer = create_indexer(textwrap.dedent(BOTMETA), modules)

        self.assertEqual(len(module_indexer.modules), 2)  # ensure only fake data are loaded
        self.assertEqual(sorted(module_indexer.botmeta[u'files'][u'lib/ansible/modules/foo/bar.py'][u'maintainers']), [u'ElsA', u'mscherer'])
        self.assertEqual(sorted(module_indexer.botmeta[u'files'][u'lib/ansible/module_utils/baz/bar.py'][u'maintainers']), [u'TiTi', u'ZaZa'])

        CM = ComponentMatcherMock()
        CM.expected_results = [
            {
                u'repo_filename': u'lib/ansible/module_utils/foo/bar.py',
                u'labels': [],
                u'support': None,
                u'maintainers': [u'ElsA', u'mscherer'],
                u'notify': [u'ElsA', u'mscherer'],
                u'ignore': [],
            },
            {
                u'repo_filename': u'lib/ansible/modules/baz/bar.py',
                u'labels': [],
                u'support': None,
                u'maintainers': [u'TiTi', u'ZaZa'],
                u'notify': [u'TiTi', u'ZaZa'],
                u'ignore': [],
            }
        ]

        meta = self.meta.copy()

        datafile = u'tests/fixtures/shipit/0_issue.yml'
        statusfile = u'tests/fixtures/shipit/0_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            iw.pr_files = [
                MockFile(u'lib/ansible/modules/foo/bar.py'),
                MockFile(u'lib/ansible/module_utils/baz/bar.py')
            ]
            iw.file_indexer = FileIndexerMock()

            iw._commits = []
            meta.update(get_component_match_facts(iw, CM, []))
            facts = get_shipit_facts(iw, meta, module_indexer, core_team=[u'bcoca', u'mscherer'], botnames=[u'ansibot'])

        self.assertEqual(iw.submitter, u'mscherer')
        self.assertFalse(facts[u'owner_pr'])

    def test_owner_pr_module_utils_and_modules_updated_submitter_maintainer_2(self):
        """
        PR updates 2 files (one below modules, the other below module_utils),
        submitter is a maintainer from both, check that owner_pr is set.
        Submitter is maintainer from module_utils file.
        """
        BOTMETA = u"""
        ---
        macros:
            modules: lib/ansible/modules
            module_utils: lib/ansible/module_utils
        files:
            $modules/foo/bar.py:
                maintainers: ElsA ZaZa
            $module_utils/baz/bar.py:
                maintainers: TiTi mscherer
        """

        modules = {u'lib/ansible/modules/foo/bar.py': None}
        module_indexer = create_indexer(textwrap.dedent(BOTMETA), modules)

        self.assertEqual(len(module_indexer.modules), 2)  # ensure only fake data are loaded
        self.assertEqual(sorted(module_indexer.botmeta[u'files'][u'lib/ansible/modules/foo/bar.py'][u'maintainers']), [u'ElsA', u'ZaZa'])
        self.assertEqual(sorted(module_indexer.botmeta[u'files'][u'lib/ansible/module_utils/baz/bar.py'][u'maintainers']), [u'TiTi', u'mscherer'])

        CM = ComponentMatcherMock()
        CM.expected_results = [
            {
                u'repo_filename': u'lib/ansible/module_utils/foo/bar.py',
                u'labels': [],
                u'support': None,
                u'maintainers': [u'ElsA', u'mscherer'],
                u'notify': [u'ElsA', u'mscherer'],
                u'ignore': [],
            },
            {
                u'repo_filename': u'lib/ansible/modules/baz/bar.py',
                u'labels': [],
                u'support': None,
                u'maintainers': [u'TiTi', u'ZaZa'],
                u'notify': [u'TiTi', u'ZaZa'],
                u'ignore': [],
            }
        ]

        meta = self.meta.copy()

        datafile = u'tests/fixtures/shipit/0_issue.yml'
        statusfile = u'tests/fixtures/shipit/0_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            iw.pr_files = [
                MockFile(u'lib/ansible/modules/foo/bar.py'),
                MockFile(u'lib/ansible/module_utils/baz/bar.py')
            ]
            iw.file_indexer = FileIndexerMock()
            meta.update(get_component_match_facts(iw, CM, []))
            facts = get_shipit_facts(iw, meta, module_indexer, core_team=[u'bcoca'], botnames=[u'ansibot'])

        self.assertEqual(iw.submitter, u'mscherer')
        self.assertFalse(facts[u'owner_pr'])


class TestReviewFacts(unittest.TestCase):

    def setUp(self):
        self.meta = {
            u'is_needs_revision': False,  # always set by needs_revision plugin (get_needs_revision_facts)
            u'is_needs_rebase': False,
            u'is_needs_info': False,  # set by needs_info_template_facts
        }

    def test_review_facts_are_defined_module_utils(self):
        BOTMETA = u"""
        ---
        macros:
            modules: lib/ansible/modules
            module_utils: lib/ansible/module_utils
        files:
            $module_utils:
              support: community
            $modules/foo/bar.py:
                maintainers: ElsA ZaZa
            $module_utils/baz/bar.py:
                maintainers: TiTi mscherer
        """

        modules = {u'lib/ansible/modules/foo/bar.py': None}
        module_indexer = create_indexer(textwrap.dedent(BOTMETA), modules)

        self.assertEqual(len(module_indexer.modules), 2)  # ensure only fake data are loaded
        self.assertEqual(sorted(module_indexer.botmeta[u'files'][u'lib/ansible/modules/foo/bar.py'][u'maintainers']),[u'ElsA', u'ZaZa'])
        self.assertEqual(sorted(module_indexer.botmeta[u'files'][u'lib/ansible/module_utils/baz/bar.py'][u'maintainers']),[u'TiTi', u'mscherer'])

        datafile = u'tests/fixtures/shipit/2_issue.yml'
        statusfile = u'tests/fixtures/shipit/2_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            iw.pr_files = [MockFile(u'lib/ansible/module_utils/foo/bar.py')]
            # need to give the wrapper a list of known files to compare against
            iw.file_indexer = FileIndexerMock()
            iw.file_indexer.files.append(u'lib/ansible/modules/foo/bar.py')

            # predefine what the matcher is going to return
            CM = ComponentMatcherMock()
            CM.expected_results = [
                {
                    u'repo_filename': u'lib/ansible/module_utils/foo/bar.py',
                    u'labels': [],
                    u'support': None,
                    u'maintainers': [u'ElsA', u'Oliver'],
                    u'notify': [u'ElsA', u'Oliver'],
                    u'ignore': [],
                }
            ]

            meta = self.meta.copy()
            iw._commits = []
            meta.update(get_component_match_facts(iw, CM, []))
            meta.update(get_shipit_facts(iw, meta, module_indexer, core_team=[u'bcoca'], botnames=[u'ansibot']))
            facts = get_review_facts(iw, meta)

        self.assertTrue(facts[u'community_review'])
        self.assertFalse(facts[u'core_review'])
        self.assertFalse(facts[u'committer_review'])
