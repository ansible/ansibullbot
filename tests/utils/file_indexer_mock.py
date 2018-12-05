import six

from ansibullbot.utils.file_tools import FileIndexer


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
    class FileIndexerMock(FileIndexer):
        def update(self, force=False):
            '''noop'''

        def get_file_content(self, filepath):
            return BOTMETA

        def get_ansible_modules(self):
            '''list modules from filesystem'''
            self.populate_modules(filepaths.keys())

        def get_module_authors(self, mfile):
            '''set authors from module source code: 'author' field in DOCUMENTATION metadata'''
            for (filepath, authors) in filepaths.items():
                if mfile.endswith(filepath):
                    if not authors:
                        return []
                    else:
                        return authors
            assert False

        def get_files(self):
            self.files = list(filepaths.keys())
            self.modules = filepaths

    file_indexer = FileIndexerMock()
    #file_indexer.parse_metadata()
    #file_indexer.get_ansible_modules()
    #file_indexer.set_maintainers()

    return file_indexer
