#!/usr/bin/env python

import copy
import os
import six
import textwrap
from unittest import TestCase

six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock

from ansibullbot.utils.moduletools import ModuleIndexer


def run(BOTMETA, filepaths):
    """Create and test ModuleIndexer

    1. parse BOTMETA metadata
    2. list source code paths (filepaths keys)
    3. fetch authors from source code content (filepaths values)

    filepaths = {
        'lib/ansible/modules/foo/bar/baz.py': None, # no author in source code
        'lib/ansible/modules/foo2/bar2/baz.py': ['author1', 'author2'],
    }
    """

    def set_modules(self):
        '''list modules from filesystem'''
        for filepath in filepaths.keys():
            m = copy.deepcopy(ModuleIndexer.EMPTY_MODULE)
            m['filename'] = os.path.basename(filepath)
            m['filepath'] = filepath
            self.modules[filepath] = m

    def set_authors(self, mfile):
        '''set authors from module source code: 'author' field in DOCUMENTATION metadata'''
        for (filepath, authors) in filepaths.items():
            if mfile.endswith(filepath):
                if not authors:
                    return []
                else:
                    return authors
        assert False

    @mock.patch.object(ModuleIndexer, 'update')
    @mock.patch.object(ModuleIndexer, 'get_module_authors', side_effect=set_authors, autospec=True)
    @mock.patch.object(ModuleIndexer, 'get_ansible_modules', side_effect=set_modules, autospec=True)
    @mock.patch.object(ModuleIndexer, 'get_file_content', return_value=BOTMETA)
    def indexer(m_update, m_authors, m_modules, m_content):
        indexer = ModuleIndexer()
        indexer.parse_metadata()
        indexer.set_maintainers()
        return indexer

    return indexer()


class TestModuleIndexer(TestCase):
    BOTMETA = """
    ---
    macros:
        team_green:
          - larry
          - cow
        modules: lib/ansible/modules
    files:
        # Simplest test
        $modules/foo/bar: jim
        $modules/foo/bar/baz.py: bob

        # Check path normalization
        $modules/foo2/bar2/: jim
        $modules/foo2/bar2/baz.py: bob

        # Check that only full paths match
        $modules/bar/foo: csim
        $modules/bar/foofoo.py: uolip

        # Check with two parent directories
        $modules/baz:
            maintainers: [ZaZa, Loulou]
        $modules/baz/test: jim
        $modules/baz/test/code.py: bob
    """

    def test_maintainers(self):
        """maintainers don't get mix up

        - author is defined in 'author' field of 'DOCUMENTATION' module metadata ('Hubert')
        - module path not in BOTMETA ('lib/ansible/modules/packaging/apt.py')
        - one another directory with one maintainer in BOTMETA, directory name
          is included in module path but is unrelated ('packaging/')
        """

        BOTMETA = """
        ---
        macros:
            team_green:
              - larry
              - cow
            modules: lib/ansible/modules
        files:
            packaging/:
              maintainers: csim
        """
        expected = {
            'packaging': {
                'maintainers': ['csim'],
                'maintainers_keys': ['packaging'],
                'labels': ['packaging'],
            }
        }

        filepath = 'lib/ansible/modules/packaging/apt.py'
        filepaths = {filepath: ['Hubert']}
        indexer = run(textwrap.dedent(BOTMETA), filepaths)

        self.assertEqual(indexer.botmeta['files'], expected)

        self.assertEqual(len(indexer.modules), 1)  # ensure only fake data are loaded
        self.assertEqual(indexer.modules[filepath]['maintainers'], ['Hubert'])
        self.assertFalse(indexer.modules[filepath]['maintainers_keys'])

    def test_module_authors_inherit_from_directory_maintainers(self):
        """Check maintainers

        Authors defined in 'author' field of 'DOCUMENTATION' module metadata inherit from
        directory maintainers specified in BOTMETA.

        - author is defined in 'author' field of 'DOCUMENTATION' module metadata ('bob')
        - module path not in BOTMETA ('lib/ansible/modules/foo/bar/baz.py')
        - one parent directory in BOTMETA with one maintainer ('lib/ansible/modules/foo/bar')
        """
        BOTMETA = """
        ---
        macros:
            team_green:
              - larry
              - cow
            modules: lib/ansible/modules
        files:
            $modules/foo/bar: jim
        """

        expected = {
            'lib/ansible/modules/foo/bar': {
                'labels': sorted(['lib', 'ansible', 'modules', 'foo', 'bar']),
                'maintainers': ['jim'],
                'maintainers_keys': ['lib/ansible/modules/foo/bar'],
            }
        }

        filepath = 'lib/ansible/modules/foo/bar/baz.py'
        filepaths = {filepath: ['bob']}
        indexer = run(textwrap.dedent(BOTMETA), filepaths)

        self.assertEqual(indexer.botmeta['files'], expected)

        self.assertEqual(len(indexer.modules), 1)  # ensure only fake data are loaded
        self.assertEqual(set(indexer.modules[filepath]['maintainers']), set(['bob', 'jim']))  # both
        self.assertEqual(indexer.modules[filepath]['maintainers_keys'], ['lib/ansible/modules/foo/bar'])

    def test_maintainers_inherit_from_directory_maintainers(self):
        """Check maintainers inheritance

        No author defined in 'author' field of 'DOCUMENTATION' module metadata.
        """

        filepaths = {
            'lib/ansible/modules/foo/bar/baz.py': None,
            'lib/ansible/modules/foo2/bar2/baz.py': None,
            'lib/ansible/modules/bar/foofoo.py': None,
            'lib/ansible/modules/baz/test/code.py': None,
        }

        expected = {}
        key = 'lib/ansible/modules/foo/bar'
        expected[key] = {
            'maintainers': ['jim'],
            'maintainers_keys': [key],
        }
        key = 'lib/ansible/modules/foo/bar/baz.py'
        expected[key] = {
            'maintainers': ['bob', 'jim'],
            'maintainers_keys': ['lib/ansible/modules/foo/bar', key],
        }
        key = 'lib/ansible/modules/foo2/bar2'
        expected[key] = {
            'maintainers': ['jim'],
            'maintainers_keys': [key],
        }
        key = 'lib/ansible/modules/foo2/bar2/baz.py'
        expected[key] = {
            'maintainers': ['bob', 'jim'],
            'maintainers_keys': ['lib/ansible/modules/foo2/bar2', key],
        }
        key = 'lib/ansible/modules/bar/foo'
        expected[key] = {
            'maintainers': ['csim'],
            'maintainers_keys': [key],
        }

        key = 'lib/ansible/modules/bar/foofoo.py'
        expected[key] = {
            'maintainers': ['uolip'],
            'maintainers_keys': [key],
        }

        key = 'lib/ansible/modules/baz'
        expected[key] = {
            'maintainers': ['Loulou', 'ZaZa'],
            'maintainers_keys': [key],
        }

        key = 'lib/ansible/modules/baz/test'
        expected[key] = {
            'maintainers': ['Loulou', 'jim', 'ZaZa'],
            'maintainers_keys': ['lib/ansible/modules/baz', key],
        }

        key = 'lib/ansible/modules/baz/test/code.py'
        expected[key] = {
            'maintainers': ['Loulou', 'bob', 'jim', 'ZaZa'],
            'maintainers_keys': ['lib/ansible/modules/baz', 'lib/ansible/modules/baz/test', key],
        }

        indexer = run(textwrap.dedent(self.BOTMETA), filepaths)

        self.assertEqual(len(indexer.modules), len(filepaths))  # ensure only fake data are loaded

        for k in expected:
            # BOTMETA and modules have identical maintainers since there is no authors
            # defined in source code
            self.assertEqual(sorted(indexer.botmeta['files'][k]['maintainers_keys']),sorted(expected[k]['maintainers_keys']))
            self.assertEqual(sorted(indexer.botmeta['files'][k]['maintainers']), sorted(expected[k]['maintainers']))

        for k in filepaths:
            self.assertEqual(sorted(indexer.modules[k]['maintainers_keys']),sorted(expected[k]['maintainers_keys']))
            self.assertEqual(sorted(indexer.modules[k]['maintainers']), sorted(expected[k]['maintainers']))

    def test_authors_not_omitted_if_entry_in_BOTMETA(self):
        """Check that authors aren't omitted when metadata are overidden in BOTMETA

        Ensure that authors defined in 'author' field of 'DOCUMENTATION' module
        metadata aren't omitted when there is a matching entry in BOTMETA.yml.

        Same BOTMETA.yml, but now authors are defined in 'author' field of
        'DOCUMENTATION' module metadata.
        """

        filepaths = {
            'lib/ansible/modules/baz/test/code.py': ['Louise'],
        }

        expected_maintainers = sorted(['Loulou', 'bob', 'jim', 'ZaZa', 'Louise'])

        indexer = run(textwrap.dedent(self.BOTMETA), filepaths)

        self.assertEqual(len(indexer.modules), len(filepaths))  # ensure only fake data are loaded
        self.assertEqual(sorted(indexer.modules['lib/ansible/modules/baz/test/code.py']['maintainers']), expected_maintainers)

    def test_ignored_author(self):
        """Check that author ignored in BOTMETA are removed"""
        BOTMETA = """
        ---
        macros:
            modules: lib/ansible/modules
        files:
            $modules/baz/test/code.py:
                maintainers: bob
                ignored: Oliver
        """

        filepaths = {
            'lib/ansible/modules/baz/test/code.py': ['Louise', 'Oliver'],
        }

        expected_maintainers = sorted(['bob', 'Louise'])  # not Oliver

        indexer = run(textwrap.dedent(BOTMETA), filepaths)

        self.assertEqual(len(indexer.modules), len(filepaths))  # ensure only fake data are loaded
        self.assertEqual(sorted(indexer.modules['lib/ansible/modules/baz/test/code.py']['maintainers']), expected_maintainers)

    def test_ignored_maintainer_in_parent_dir(self):
        """Check that maintainer defined in BOTMETA but ignored in a child entry are ignored.

        No author defined in 'author' field of 'DOCUMENTATION' module metadata.
        """
        BOTMETA = """
        ---
        macros:
            modules: lib/ansible/modules
        files:
            # Check with two parent directories
            $modules/baz/test:
                maintainers: ElsA Oliver
            $modules/baz/test/code1.py:
                ignored: Oliver
        """

        filepaths = {
            'lib/ansible/modules/baz/test/code1.py': None,
            'lib/ansible/modules/baz/test/code2.py': None,
            'lib/ansible/modules/baz/test/code3.py': None,
            'lib/ansible/modules/baz/test/code4.py': None,
        }

        indexer = run(textwrap.dedent(BOTMETA), filepaths)

        self.assertEqual(len(indexer.modules), len(filepaths))  # ensure only fake data are loaded
        self.assertEqual(sorted(indexer.modules['lib/ansible/modules/baz/test/code1.py']['maintainers']), ['ElsA'])
        self.assertEqual(sorted(indexer.modules['lib/ansible/modules/baz/test/code2.py']['maintainers']), sorted(['ElsA', 'Oliver']))
        self.assertEqual(sorted(indexer.modules['lib/ansible/modules/baz/test/code3.py']['maintainers']), sorted(['ElsA', 'Oliver']))
        self.assertEqual(sorted(indexer.modules['lib/ansible/modules/baz/test/code4.py']['maintainers']), sorted(['ElsA', 'Oliver']))

    def test_ignored_author_in_parent_dir(self):
        """Check that author ignored in BOTMETA in a parent directory are not removed

        Some authors defined in 'author' field of 'DOCUMENTATION' module
        metadata but ignored in a parent directory entry in BOTMETA.
        """
        BOTMETA = """
        ---
        macros:
            modules: lib/ansible/modules
        files:
            # Check with two parent directories
            $modules/baz/test:
                maintainers: ElsA
                ignored: Oliver
            $modules/baz/test/code.py:
                maintainers: bob
        """

        filepaths = {
            'lib/ansible/modules/baz/test/code.py': ['Louise', 'Oliver'],
        }

        expected_maintainers = sorted(['ElsA', 'bob', 'Louise', 'Oliver'])  # Oliver here

        indexer = run(textwrap.dedent(BOTMETA), filepaths)

        self.assertEqual(len(indexer.modules), len(filepaths))  # ensure only fake data are loaded
        self.assertEqual(sorted(indexer.modules['lib/ansible/modules/baz/test/code.py']['maintainers']), expected_maintainers)
