import six
from ansibullbot.utils.moduletools import ModuleIndexer

six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock


def create_indexer(BOTMETA, filepaths):
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
        self.populate_modules(filepaths.keys())

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
        module_indexer = ModuleIndexer()
        module_indexer.parse_metadata()
        module_indexer.set_maintainers()
        return module_indexer

    return indexer()
