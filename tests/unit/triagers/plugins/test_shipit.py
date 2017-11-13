#!/usr/bin/env python

import copy
import json
import logging
import os
import shutil
import tempfile
import textwrap
import unittest

import six
six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock

from tests.utils.issue_mock import IssueMock
from tests.utils.helpers import get_issue
from tests.utils.module_indexer_mock import create_indexer
from ansibullbot.triagers.plugins.component_matching import get_component_match_facts
from ansibullbot.triagers.plugins.shipit import get_shipit_facts
from ansibullbot.wrappers.issuewrapper import IssueWrapper


class ModuleIndexerMock(object):

    def __init__(self, namespace_maintainers):
        self.namespace_maintainers = namespace_maintainers

    def get_maintainers_for_namespace(self, namespace):
        return self.namespace_maintainers


class FileIndexerMock(object):
    def find_component_matches_by_file(self, filenames):
        return []

    def isnewdir(self, path):
        return False

    def get_component_labels(self, files, valid_labels=None):
        return []


class MockFile(object):
    def __init__(self, name):
        self.filename = name


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

    @unittest.skip('disabled')
    def test_submitter_is_maintainer(self):
        """
        Submitter is a namespace maintainer: approval must be automatically
        added
        """
        datafile = 'tests/fixtures/shipit/0_issue.yml'
        statusfile = 'tests/fixtures/shipit/0_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            namespace_maintainers = ['LinusU', 'mscherer']
            facts = get_shipit_facts(iw, self.meta, ModuleIndexerMock(namespace_maintainers), core_team=['bcoca'], botnames=['ansibot'])

            self.assertEqual(iw.submitter, 'mscherer')
            self.assertEqual(['LinusU', 'mscherer'], facts['community_usernames'])
            self.assertEqual(['mscherer'], facts['shipit_actors'])
            self.assertEqual(facts['shipit_count_ansible'], 0)     # bcoca
            self.assertEqual(facts['shipit_count_maintainer'], 0)  # abulimov
            self.assertEqual(facts['shipit_count_community'], 1)   # LinusU, mscherer
            self.assertFalse(facts['shipit'])

    @unittest.skip('disabled')
    def test_submitter_is_core_team_and_maintainer(self):
        """
        Submitter is a namespace maintainer *and* a core team member: approval
        must be automatically added
        https://github.com/ansible/ansible/pull/21620
        """
        datafile = 'tests/fixtures/shipit/1_issue.yml'
        statusfile = 'tests/fixtures/shipit/1_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            namespace_maintainers = ['LinusU']
            facts = get_shipit_facts(iw, self.meta, ModuleIndexerMock(namespace_maintainers), core_team=['bcoca', 'mscherer'], botnames=['ansibot'])

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
            namespace_maintainers = ['LinusU']

            facts = get_shipit_facts(iw, meta, ModuleIndexerMock(namespace_maintainers), core_team=['bcoca', 'mscherer'], botnames=['ansibot'])

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


class TestOwnerPR(unittest.TestCase):

    def setUp(self):
        self.meta = {
            'is_needs_revision': False,  # always set by needs_revision plugin (get_needs_revision_facts)
            'is_needs_rebase': False,
        }

    @unittest.skip('disabled')
    def test_owner_pr_submitter_is_maintainer_one_module_utils_file_updated(self):
        """
        Submitter is a maintainer: ensure owner_pr is set (only one file below module_utils updated)
        """
        BOTMETA = """
        ---
        macros:
            modules: lib/ansible/modules
            module_utils: lib/ansible/module_utils
        files:
            $module_utils/foo/bar.py:
                maintainers: ElsA Oliver
        """

        modules = {'lib/ansible/module_utils/foo/bar.py': None}
        module_indexer = create_indexer(textwrap.dedent(BOTMETA), modules)

        self.assertEqual(len(module_indexer.modules), 2)  # ensure only fake data are loaded
        self.assertEqual(sorted(module_indexer.botmeta['files']['lib/ansible/module_utils/foo/bar.py']['maintainers']), ['ElsA', 'Oliver'])

        issue = IssueMock('/dev/null')
        issue.user.login = 'ElsA'
        issue.html_url = 'https://github.com/ansible/ansible/pull/123'
        iw = IssueWrapper(cachedir="", issue=issue)
        iw.pr_files = [MockFile('lib/ansible/module_utils/foo/bar.py')]

        meta = self.meta.copy()
        meta.update(get_component_match_facts(iw, None, FileIndexerMock(), module_indexer, []))
        facts = get_shipit_facts(iw, meta, module_indexer, core_team=['bcoca', 'mscherer'], botnames=['ansibot'])

        self.assertEqual(iw.submitter, 'ElsA')
        self.assertTrue(facts['owner_pr'])

    @unittest.skip('disabled')
    def test_owner_pr_submitter_is_maintainer_one_modules_file_updated(self):
        """
        Submitter is a maintainer: ensure owner_pr is set (only one file below modules updated)
        """
        BOTMETA = """
        ---
        macros:
            modules: lib/ansible/modules
            module_utils: lib/ansible/module_utils
        files:
            $modules/foo/bar.py:
                maintainers: ElsA mscherer
        """

        modules = {'lib/ansible/modules/foo/bar.py': None}
        module_indexer = create_indexer(textwrap.dedent(BOTMETA), modules)

        self.assertEqual(len(module_indexer.modules), 2)  # ensure only fake data are loaded
        self.assertEqual(sorted(module_indexer.botmeta['files']['lib/ansible/modules/foo/bar.py']['maintainers']), ['ElsA', 'mscherer'])

        meta = self.meta.copy()

        datafile = 'tests/fixtures/shipit/0_issue.yml'
        statusfile = 'tests/fixtures/shipit/0_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            iw.pr_files = [MockFile('lib/ansible/modules/foo/bar.py')]

            meta.update(get_component_match_facts(iw, {}, FileIndexerMock(), module_indexer, []))
            facts = get_shipit_facts(iw, meta, module_indexer, core_team=['bcoca'], botnames=['ansibot'])

        self.assertEqual(iw.submitter, 'mscherer')
        self.assertTrue(facts['owner_pr'])

    @unittest.skip('disabled')
    def test_owner_pr_submitter_is_maintainer_new_module(self):
        """
        Submitter is a maintainer: pull request adds a new module: ensure owner_pr is False
        """
        BOTMETA = """
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
        self.assertEqual(sorted(module_indexer.botmeta['files']['lib/ansible/modules/foo/bar.py']['maintainers']), ['ElsA', 'mscherer'])

        meta = self.meta.copy()

        datafile = 'tests/fixtures/shipit/0_issue.yml'
        statusfile = 'tests/fixtures/shipit/0_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            iw.pr_files = [MockFile('lib/ansible/modules/foo/bar.py')]

            meta.update(get_component_match_facts(iw, {}, FileIndexerMock(), module_indexer, []))
            facts = get_shipit_facts(iw, meta, module_indexer, core_team=['bcoca'], botnames=['ansibot'])

        self.assertEqual(iw.submitter, 'mscherer')
        self.assertFalse(facts['owner_pr'])

    @unittest.skip('disabled')
    def test_owner_pr_submitter_is_not_maintainer_of_all_updated_files(self):
        """
        PR updates 2 files below module_utils, submitter is a maintainer from only one: ensure owner_pr isn't set
        """
        BOTMETA = """
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
        self.assertEqual(sorted(module_indexer.botmeta['files']['lib/ansible/module_utils/foo/bar.py']['maintainers']), ['ElsA', 'Oliver'])
        self.assertEqual(sorted(module_indexer.botmeta['files']['lib/ansible/module_utils/baz/bar.py']['maintainers']), ['TiTi', 'ZaZa'])

        issue = IssueMock('/dev/null')
        issue.user.login = 'ElsA'
        issue.html_url = 'https://github.com/ansible/ansible/pull/123'
        iw = IssueWrapper(cachedir="", issue=issue)
        iw.pr_files = [
            MockFile('lib/ansible/module_utils/foo/bar.py'),
            MockFile('lib/ansible/module_utils/baz/bar.py')
        ]

        meta = self.meta.copy()
        meta.update(get_component_match_facts(iw, {}, FileIndexerMock(), module_indexer, []))
        facts = get_shipit_facts(iw, meta, module_indexer, core_team=['bcoca', 'mscherer'], botnames=['ansibot'])

        self.assertEqual(iw.submitter, 'ElsA')
        self.assertFalse(facts['owner_pr'])

    @unittest.skip('disabled')
    def test_owner_pr_module_utils_and_modules_updated_submitter_maintainer_1(self):
        """
        PR updates 2 files (one below modules, the other below module_utils),
        submitter is a maintainer from both, check that owner_pr is set.
        Submitter is maintainer from module file.
        """
        BOTMETA = """
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

        modules = {'lib/ansible/modules/foo/bar.py': None}
        module_indexer = create_indexer(textwrap.dedent(BOTMETA), modules)

        self.assertEqual(len(module_indexer.modules), 2)  # ensure only fake data are loaded
        self.assertEqual(sorted(module_indexer.botmeta['files']['lib/ansible/modules/foo/bar.py']['maintainers']), ['ElsA', 'mscherer'])
        self.assertEqual(sorted(module_indexer.botmeta['files']['lib/ansible/module_utils/baz/bar.py']['maintainers']), ['TiTi', 'ZaZa'])

        meta = self.meta.copy()

        datafile = 'tests/fixtures/shipit/0_issue.yml'
        statusfile = 'tests/fixtures/shipit/0_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            iw.pr_files = [
                MockFile('lib/ansible/modules/foo/bar.py'),
                MockFile('lib/ansible/module_utils/baz/bar.py')
            ]
            meta.update(get_component_match_facts(iw, {}, FileIndexerMock(), module_indexer, []))
            facts = get_shipit_facts(iw, meta, module_indexer, core_team=['bcoca', 'mscherer'], botnames=['ansibot'])

        self.assertEqual(iw.submitter, 'mscherer')
        self.assertFalse(facts['owner_pr'])

    @unittest.skip('disabled')
    def test_owner_pr_module_utils_and_modules_updated_submitter_maintainer_2(self):
        """
        PR updates 2 files (one below modules, the other below module_utils),
        submitter is a maintainer from both, check that owner_pr is set.
        Submitter is maintainer from module_utils file.
        """
        BOTMETA = """
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

        modules = {'lib/ansible/modules/foo/bar.py': None}
        module_indexer = create_indexer(textwrap.dedent(BOTMETA), modules)

        self.assertEqual(len(module_indexer.modules), 2)  # ensure only fake data are loaded
        self.assertEqual(sorted(module_indexer.botmeta['files']['lib/ansible/modules/foo/bar.py']['maintainers']), ['ElsA', 'ZaZa'])
        self.assertEqual(sorted(module_indexer.botmeta['files']['lib/ansible/module_utils/baz/bar.py']['maintainers']), ['TiTi', 'mscherer'])

        meta = self.meta.copy()

        datafile = 'tests/fixtures/shipit/0_issue.yml'
        statusfile = 'tests/fixtures/shipit/0_prstatus.json'
        with get_issue(datafile, statusfile) as iw:
            iw.pr_files = [
                MockFile('lib/ansible/modules/foo/bar.py'),
                MockFile('lib/ansible/module_utils/baz/bar.py')
            ]
            meta.update(get_component_match_facts(iw, {}, FileIndexerMock(), module_indexer, []))
            facts = get_shipit_facts(iw, meta, module_indexer, core_team=['bcoca'], botnames=['ansibot'])

        self.assertEqual(iw.submitter, 'mscherer')
        self.assertFalse(facts['owner_pr'])
