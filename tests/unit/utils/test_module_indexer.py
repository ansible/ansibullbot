#!/usr/bin/env python

import textwrap
from unittest import TestCase

from tests.utils.module_indexer_mock import create_indexer


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
            u'packaging': {
                u'maintainers': [u'csim'],
                u'maintainers_keys': [u'packaging'],
                u'labels': [u'packaging'],
            }
        }

        filepath = u'lib/ansible/modules/packaging/apt.py'
        filepaths = {filepath: [u'Hubert']}
        indexer = create_indexer(textwrap.dedent(BOTMETA), filepaths)

        self.assertEqual(indexer.botmeta[u'files'], expected)

        self.assertEqual(len(indexer.modules), 2)  # ensure only fake data are loaded
        self.assertEqual(indexer.modules[filepath][u'maintainers'], [u'Hubert'])
        self.assertFalse(indexer.modules[filepath][u'maintainers_keys'])

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
            u'lib/ansible/modules/foo/bar': {
                u'labels': sorted([u'lib', u'ansible', u'modules', u'foo', u'bar']),
                u'maintainers': [u'jim'],
                u'maintainers_keys': [u'lib/ansible/modules/foo/bar'],
            }
        }

        filepath = u'lib/ansible/modules/foo/bar/baz.py'
        filepaths = {filepath: [u'bob']}
        indexer = create_indexer(textwrap.dedent(BOTMETA), filepaths)

        self.assertEqual(indexer.botmeta[u'files'], expected)

        self.assertEqual(len(indexer.modules), 2)  # ensure only fake data are loaded
        self.assertEqual(set(indexer.modules[filepath][u'maintainers']), set([u'bob', u'jim']))  # both
        self.assertEqual(indexer.modules[filepath][u'maintainers_keys'], [u'lib/ansible/modules/foo/bar'])

    def test_maintainers_inherit_from_directory_maintainers(self):
        """Check maintainers inheritance

        No author defined in 'author' field of 'DOCUMENTATION' module metadata.
        """

        filepaths = {
            u'lib/ansible/modules/foo/bar/baz.py': None,
            u'lib/ansible/modules/foo2/bar2/baz.py': None,
            u'lib/ansible/modules/bar/foofoo.py': None,
            u'lib/ansible/modules/baz/test/code.py': None,
        }

        expected = {}
        key = u'lib/ansible/modules/foo/bar'
        expected[key] = {
            u'maintainers': [u'jim'],
            u'maintainers_keys': [key],
        }
        key = u'lib/ansible/modules/foo/bar/baz.py'
        expected[key] = {
            u'maintainers': [u'bob', u'jim'],
            u'maintainers_keys': [u'lib/ansible/modules/foo/bar', key],
        }
        key = u'lib/ansible/modules/foo2/bar2'
        expected[key] = {
            u'maintainers': [u'jim'],
            u'maintainers_keys': [key],
        }
        key = u'lib/ansible/modules/foo2/bar2/baz.py'
        expected[key] = {
            u'maintainers': [u'bob', u'jim'],
            u'maintainers_keys': [u'lib/ansible/modules/foo2/bar2', key],
        }
        key = u'lib/ansible/modules/bar/foo'
        expected[key] = {
            u'maintainers': [u'csim'],
            u'maintainers_keys': [key],
        }

        key = u'lib/ansible/modules/bar/foofoo.py'
        expected[key] = {
            u'maintainers': [u'uolip'],
            u'maintainers_keys': [key],
        }

        key = u'lib/ansible/modules/baz'
        expected[key] = {
            u'maintainers': [u'Loulou', u'ZaZa'],
            u'maintainers_keys': [key],
        }

        key = u'lib/ansible/modules/baz/test'
        expected[key] = {
            u'maintainers': [u'Loulou', u'jim', u'ZaZa'],
            u'maintainers_keys': [u'lib/ansible/modules/baz', key],
        }

        key = u'lib/ansible/modules/baz/test/code.py'
        expected[key] = {
            u'maintainers': [u'Loulou', u'bob', u'jim', u'ZaZa'],
            u'maintainers_keys': [u'lib/ansible/modules/baz', u'lib/ansible/modules/baz/test', key],
        }

        indexer = create_indexer(textwrap.dedent(self.BOTMETA), filepaths)

        self.assertEqual(len(indexer.modules) - 1, len(filepaths))  # ensure only fake data are loaded

        for k in expected:
            # BOTMETA and modules have identical maintainers since there is no authors
            # defined in source code
            self.assertEqual(sorted(indexer.botmeta[u'files'][k][u'maintainers_keys']),sorted(expected[k][u'maintainers_keys']))
            self.assertEqual(sorted(indexer.botmeta[u'files'][k][u'maintainers']), sorted(expected[k][u'maintainers']))

        for k in filepaths:
            self.assertEqual(sorted(indexer.modules[k][u'maintainers_keys']),sorted(expected[k][u'maintainers_keys']))
            self.assertEqual(sorted(indexer.modules[k][u'maintainers']), sorted(expected[k][u'maintainers']))

    def test_authors_not_omitted_if_entry_in_BOTMETA(self):
        """Check that authors aren't omitted when metadata are overidden in BOTMETA

        Ensure that authors defined in 'author' field of 'DOCUMENTATION' module
        metadata aren't omitted when there is a matching entry in BOTMETA.yml.

        Same BOTMETA.yml, but now authors are defined in 'author' field of
        'DOCUMENTATION' module metadata.
        """

        filepaths = {
            u'lib/ansible/modules/baz/test/code.py': [u'Louise'],
        }

        expected_maintainers = sorted([u'Loulou', u'bob', u'jim', u'ZaZa', u'Louise'])

        indexer = create_indexer(textwrap.dedent(self.BOTMETA), filepaths)

        self.assertEqual(len(indexer.modules) - 1, len(filepaths))  # ensure only fake data are loaded
        self.assertEqual(sorted(indexer.modules[u'lib/ansible/modules/baz/test/code.py'][u'maintainers']), expected_maintainers)

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
            u'lib/ansible/modules/baz/test/code.py': [u'Louise', u'Oliver'],
        }

        expected_maintainers = sorted([u'bob', u'Louise'])  # not Oliver

        indexer = create_indexer(textwrap.dedent(BOTMETA), filepaths)

        self.assertEqual(len(indexer.modules) - 1, len(filepaths))  # ensure only fake data are loaded
        self.assertEqual(sorted(indexer.modules[u'lib/ansible/modules/baz/test/code.py'][u'maintainers']), expected_maintainers)

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
            u'lib/ansible/modules/baz/test/code1.py': None,
            u'lib/ansible/modules/baz/test/code2.py': None,
            u'lib/ansible/modules/baz/test/code3.py': None,
            u'lib/ansible/modules/baz/test/code4.py': None,
        }

        indexer = create_indexer(textwrap.dedent(BOTMETA), filepaths)

        self.assertEqual(len(indexer.modules) - 1, len(filepaths))  # ensure only fake data are loaded
        self.assertEqual(sorted(indexer.modules[u'lib/ansible/modules/baz/test/code1.py'][u'maintainers']), [u'ElsA'])
        self.assertEqual(sorted(indexer.modules[u'lib/ansible/modules/baz/test/code2.py'][u'maintainers']), sorted([u'ElsA', u'Oliver']))
        self.assertEqual(sorted(indexer.modules[u'lib/ansible/modules/baz/test/code3.py'][u'maintainers']), sorted([u'ElsA', u'Oliver']))
        self.assertEqual(sorted(indexer.modules[u'lib/ansible/modules/baz/test/code4.py'][u'maintainers']), sorted([u'ElsA', u'Oliver']))

    def test_ignored_author_in_parent_dir(self):
        """Check that author ignored in BOTMETA in a parent directory are removed

        Some authors are defined in 'author' field of 'DOCUMENTATION' module
        metadata and ignored in a parent directory entry in BOTMETA: ignored
        authors aren't maintainers.
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
            u'lib/ansible/modules/baz/test/code.py': [u'Louise', u'Oliver'],
        }

        expected_maintainers = sorted([u'ElsA', u'bob', u'Louise'])  # Oliver not here

        indexer = create_indexer(textwrap.dedent(BOTMETA), filepaths)

        self.assertEqual(len(indexer.modules) - 1, len(filepaths))  # ensure only fake data are loaded
        self.assertEqual(sorted(indexer.modules[u'lib/ansible/modules/baz/test/code.py'][u'maintainers']), expected_maintainers)
