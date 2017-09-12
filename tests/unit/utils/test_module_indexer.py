#!/usr/bin/env python

import copy
import os
import six
import textwrap
from unittest import TestCase

six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock

from ansibullbot.utils.moduletools import ModuleIndexer


def run(BOTMETA, authors, filepath):

    def set_modules(self):
        '''list modules from filesystem'''
        m = copy.deepcopy(ModuleIndexer.EMPTY_MODULE)
        m['filename'] = os.path.basename(filepath)
        m['filepath'] = filepath
        self.modules[m['filepath']] = m

    def set_authors(self, mfile):
        '''set authors from module source code: 'author' field in DOCUMENTATION metadata'''
        if mfile.endswith(filepath):
            return authors
        else:
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

        filepath = 'lib/ansible/modules/packaging/apt.py'
        indexer = run(textwrap.dedent(BOTMETA), ['Hubert'], filepath)
        self.assertEqual(len(indexer.modules), 1)  # ensure only fake data are loaded
        self.assertEqual(indexer.modules[filepath]['maintainers'], ['Hubert'])
        self.assertEqual(indexer.modules[filepath]['maintainers_key'], None)

    def test_module_authors_inherit_from_directory_maintainers(self):
        """ authors defined in module metadata inherit from directory maintainers specified in BOTMETA

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

        filepath = 'lib/ansible/modules/foo/bar/baz.py'
        indexer = run(textwrap.dedent(BOTMETA), ['bob'], filepath)
        self.assertEqual(len(indexer.modules), 1)  # ensure only fake data are loaded
        self.assertEqual(set(indexer.modules[filepath]['maintainers']), set(['bob', 'jim']))  # both
        self.assertEqual(indexer.modules[filepath]['maintainers_key'], 'lib/ansible/modules/foo/bar')

    def test_maintainers_dont_inherit_from_directory_maintainers(self):
        """module maintainers don't inherit from parent directory maintainers (both defined in BOTMETA)

        - author isn't defined in 'author' field of 'DOCUMENTATION' module metadata
        - module path in BOTMETA ('lib/ansible/modules/foo/bar/baz.py')
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
            $modules/foo/bar/baz.py: bob
        """

        filepath = 'lib/ansible/modules/foo/bar/baz.py'
        indexer = run(textwrap.dedent(BOTMETA), [], filepath)
        self.assertEqual(len(indexer.modules), 1)  # ensure only fake data are loaded
        self.assertEqual(set(indexer.modules[filepath]['maintainers']), set(['bob']))  # only bob, not jim
        self.assertEqual(indexer.modules[filepath]['maintainers_key'], 'lib/ansible/modules/foo/bar/baz.py')
