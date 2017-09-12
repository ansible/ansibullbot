#!/usr/bin/env python

import copy
import six
from unittest import TestCase

six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock

from ansibullbot.utils.moduletools import ModuleIndexer

METADATA = """
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

def set_modules(self):
    mdict = copy.deepcopy(ModuleIndexer.EMPTY_MODULE)
    mdict['filename'] = 'apt.py'
    mdict['filepath'] = 'lib/ansible/modules/packaging/apt.py'
    self.modules[mdict['filepath']] = mdict

def set_authors(self, mfile):
    assert mfile.endswith('lib/ansible/modules/packaging/apt.py')
    return ['Hubert']

class TestModuleIndexer(TestCase):
    @mock.patch.object(ModuleIndexer, 'update')
    @mock.patch.object(ModuleIndexer, 'get_module_authors', side_effect=set_authors, autospec=True)
    @mock.patch.object(ModuleIndexer, 'get_ansible_modules', side_effect=set_modules, autospec=True)
    @mock.patch.object(ModuleIndexer, 'get_file_content', return_value=METADATA)
    def test_maintainers(self, m_update, m_authors, m_modules, m_content):
        indexer = ModuleIndexer()
        indexer.parse_metadata()
        indexer.set_maintainers()
        self.assertEqual(len(indexer.modules), 1)
        mfile = 'lib/ansible/modules/packaging/apt.py'
        self.assertEqual(indexer.modules[mfile]['maintainers_key'], None)
        self.assertEqual(indexer.modules[mfile]['maintainers'], ['Hubert'])
