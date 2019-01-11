#!/usr/bin/env python

import datetime
import logging
import os
import re

import six

from Levenshtein import jaro_winkler

from ansibullbot._text_compat import to_bytes, to_text
from ansibullbot.parsers.botmetadata import BotMetadataParser
from ansibullbot.utils.extractors import ModuleExtractor
from ansibullbot.utils.file_tools import FileIndexer
from ansibullbot.utils.git_tools import GitRepoWrapper
from ansibullbot.utils.systemtools import run_command


class AnsibleComponentMatcher(object):

    BOTMETA = {}
    INDEX = {}
    REPO = u'https://github.com/ansible/ansible'
    STOPWORDS = [u'ansible', u'core', u'plugin']
    STOPCHARS = [u'"', "'", u'(', u')', u'?', u'*', u'`', u',', u':', u'?', u'-']
    BLACKLIST = [u'new module', u'new modules']
    FILE_NAMES = []
    MODULES = {}
    MODULE_NAMES = []
    MODULE_NAMESPACE_DIRECTORIES = []

    # FIXME: THESE NEED TO GO INTO BOTMETA
    # ALSO SEE search_by_regex_generic ...
    KEYWORDS = {
        u'all': None,
        u'ansiballz': u'lib/ansible/executor/module_common.py',
        u'ansible-console': u'lib/ansible/cli/console.py',
        u'ansible-galaxy': u'lib/ansible/galaxy',
        u'ansible-inventory': u'lib/ansible/cli/inventory.py',
        u'ansible-playbook': u'lib/ansible/playbook',
        u'ansible playbook': u'lib/ansible/playbook',
        u'ansible playbooks': u'lib/ansible/playbook',
        u'ansible-pull': u'lib/ansible/cli/pull.py',
        u'ansible-vault': u'lib/ansible/parsing/vault',
        u'ansible-vault edit': u'lib/ansible/parsing/vault',
        u'ansible-vault show': u'lib/ansible/parsing/vault',
        u'ansible-vault decrypt': u'lib/ansible/parsing/vault',
        u'ansible-vault encrypt': u'lib/ansible/parsing/vault',
        u'async': u'lib/ansible/modules/utilities/logic/async_wrapper.py',
        u'become': u'lib/ansible/playbook/become.py',
        u'block': u'lib/ansible/playbook/block.py',
        u'blocks': u'lib/ansible/playbook/block.py',
        u'callback plugin': u'lib/ansible/plugins/callback',
        u'callback plugins': u'lib/ansible/plugins/callback',
        u'conditional': u'lib/ansible/playbook/conditional.py',
        u'docs': u'docs',
        u'delegate_to': u'lib/ansible/playbook/task.py',
        u'facts': u'lib/ansible/module_utils/facts',
        u'galaxy': u'lib/ansible/galaxy',
        u'groupvars': u'lib/ansible/vars/hostvars.py',
        u'group vars': u'lib/ansible/vars/hostvars.py',
        u'handlers': u'lib/ansible/playbook/handler.py',
        u'hostvars': u'lib/ansible/vars/hostvars.py',
        u'host vars': u'lib/ansible/vars/hostvars.py',
        u'integration tests': u'test/integration',
        u'inventory script': u'contrib/inventory',
        u'jinja2 template system': u'lib/ansible/template',
        u'module_utils': u'lib/ansible/module_utils',
        u'multiple modules': None,
        u'new module(s) request': None,
        u'new modules request': None,
        u'new module request': None,
        u'new module': None,
        u'network_cli': u'lib/ansible/plugins/connection/network_cli.py',
        u'network_cli.py': u'lib/ansible/plugins/connection/network_cli.py',
        u'network modules': u'lib/ansible/modules/network',
        u'paramiko': u'lib/ansible/plugins/connection/paramiko_ssh.py',
        u'role': u'lib/ansible/playbook/role',
        u'roles': u'lib/ansible/playbook/role',
        u'ssh': u'lib/ansible/plugins/connection/ssh.py',
        u'ssh authentication': u'lib/ansible/plugins/connection/ssh.py',
        u'setup / facts': u'lib/ansible/modules/system/setup.py',
        u'setup': u'lib/ansible/modules/system/setup.py',
        u'task executor': u'lib/ansible/executor/task_executor.py',
        u'testing': u'test/',
        u'validate-modules': u'test/sanity/validate-modules',
        u'vault': u'lib/ansible/parsing/vault',
        u'vault edit': u'lib/ansible/parsing/vault',
        u'vault documentation': u'lib/ansible/parsing/vault',
        u'with_items': u'lib/ansible/playbook/loop_control.py',
        u'windows modules': u'lib/ansible/modules/windows',
        u'winrm': u'lib/ansible/plugins/connection/winrm.py'
    }

    def __init__(self, gitrepo=None, botmetafile=None, cachedir=None, email_cache=None, file_indexer=None):
        self.botmetafile = botmetafile
        self.email_cache = email_cache

        if gitrepo:
            self.gitrepo = gitrepo
        else:
            self.gitrepo = GitRepoWrapper(cachedir=cachedir, repo=self.REPO)

        if file_indexer:
            self.file_indexer = file_indexer
        else:
            self.file_indexer = FileIndexer(
                botmetafile=self.botmetafile,
                gitrepo=self.gitrepo
            )

        self.strategy = None
        self.strategies = []

        self.indexed_at = False
        self.updated_at = None
        self.update()

    def update(self, email_cache=None):
        if email_cache:
            self.email_cache = email_cache
        self.gitrepo.update()
        self.index_files()
        self.indexed_at = datetime.datetime.now()
        self.cache_keywords()
        self.updated_at = datetime.datetime.now()

    def index_files(self):

        self.BOTMETA = {}
        self.MODULES = {}
        self.MODULE_NAMES = []
        self.MODULE_NAMESPACE_DIRECTORIES = []

        self.load_meta()

        for fn in self.gitrepo.module_files:
            if os.path.isdir(fn):
                continue
            mname = os.path.basename(fn)
            mname = mname.replace(u'.py', u'').replace(u'.ps1', u'')
            if mname.startswith(u'__'):
                continue
            mdata = {
                u'name': mname,
                u'repo_filename': fn,
                u'filename': fn
            }
            if fn not in self.MODULES:
                self.MODULES[fn] = mdata.copy()
            else:
                self.MODULES[fn].update(mdata)

        self.MODULE_NAMESPACE_DIRECTORIES = (os.path.dirname(x) for x in self.gitrepo.module_files)
        self.MODULE_NAMESPACE_DIRECTORIES = sorted(set(self.MODULE_NAMESPACE_DIRECTORIES))

        # make a list of names by enumerating the files
        self.MODULE_NAMES = (os.path.basename(x) for x in self.gitrepo.module_files)
        self.MODULE_NAMES = (x for x in self.MODULE_NAMES if x.endswith((u'.py', u'.ps1')))
        self.MODULE_NAMES = (x.replace(u'.ps1', u'').replace(u'.py', u'') for x in self.MODULE_NAMES)
        self.MODULE_NAMES = (x for x in self.MODULE_NAMES if not x.startswith(u'__'))
        self.MODULE_NAMES = sorted(set(self.MODULE_NAMES))

        # make a list of names by calling ansible-doc
        checkoutdir = self.gitrepo.checkoutdir
        checkoutdir = os.path.abspath(checkoutdir)
        cmd = u'. {}/hacking/env-setup; ansible-doc -t module -F'.format(checkoutdir)
        logging.debug(cmd)
        (rc, so, se) = run_command(cmd, cwd=checkoutdir)
        if rc:
            raise Exception("'ansible-doc' command failed (%s, %s %s)" % (rc, so, se))
        lines = to_text(so).split(u'\n')
        for line in lines:

            # compat for macos tmpdirs
            if u' /private' in line:
                line = line.replace(u' /private', u'', 1)

            parts = line.split()
            parts = [x.strip() for x in parts]

            if len(parts) != 2 or checkoutdir not in line:
                continue

            mname = parts[0]
            if mname not in self.MODULE_NAMES:
                self.MODULE_NAMES.append(mname)

            fpath = parts[1]
            fpath = fpath.replace(checkoutdir + u'/', u'')

            if fpath not in self.MODULES:
                self.MODULES[fpath] = {
                    u'name': mname,
                    u'repo_filename': fpath,
                    u'filename': fpath
                }

        _modules = self.MODULES.copy()
        for k, v in _modules.items():
            kparts = os.path.splitext(k)
            if kparts[-1] == u'.ps1':
                _k = kparts[0] + u'.py'
                checkpath = os.path.join(checkoutdir, _k)
                if not os.path.isfile(checkpath):
                    _k = k
            else:
                _k = k
            ME = ModuleExtractor(os.path.join(checkoutdir, _k), email_cache=self.email_cache)
            if k not in self.BOTMETA[u'files']:
                self.BOTMETA[u'files'][k] = {
                    u'deprecated': os.path.basename(k).startswith(u'_'),
                    u'labels': os.path.dirname(k).split(u'/'),
                    u'authors': ME.authors,
                    u'maintainers': ME.authors,
                    u'maintainers_keys': [],
                    u'notified': ME.authors,
                    u'ignored': [],
                    u'support': ME.metadata.get(u'supported_by', u'community'),
                    u'metadata': ME.metadata.copy()
                }
            else:
                bmeta = self.BOTMETA[u'files'][k].copy()
                bmeta[u'metadata'] = ME.metadata.copy()
                if u'notified' not in bmeta:
                    bmeta[u'notified'] = []
                if u'maintainers' not in bmeta:
                    bmeta[u'maintainers'] = []
                if not bmeta.get(u'supported_by'):
                    bmeta[u'supported_by'] = ME.metadata.get(u'supported_by', u'community')
                if u'authors' not in bmeta:
                    bmeta[u'authors'] = []
                for x in ME.authors:
                    if x not in bmeta[u'authors']:
                        bmeta[u'authors'].append(x)
                    if x not in bmeta[u'maintainers']:
                        bmeta[u'maintainers'].append(x)
                    if x not in bmeta[u'notified']:
                        bmeta[u'notified'].append(x)
                if not bmeta.get(u'labels'):
                    bmeta[u'labels'] = os.path.dirname(k).split(u'/')
                bmeta[u'deprecated'] = os.path.basename(k).startswith(u'_')
                self.BOTMETA[u'files'][k].update(bmeta)

            # clean out the ignorees
            if u'ignored' in self.BOTMETA[u'files'][k]:
                for ignoree in self.BOTMETA[u'files'][k][u'ignored']:
                    for thiskey in [u'maintainers', u'notified']:
                        while ignoree in self.BOTMETA[u'files'][k][thiskey]:
                            self.BOTMETA[u'files'][k][thiskey].remove(ignoree)

            # write back to the modules
            self.MODULES[k].update(self.BOTMETA[u'files'][k])

    def load_meta(self):
        if self.botmetafile is not None:
            with open(self.botmetafile, 'rb') as f:
                rdata = f.read()
        else:
            fp = u'.github/BOTMETA.yml'
            rdata = self.gitrepo.get_file_content(fp)
        self.BOTMETA = BotMetadataParser.parse_yaml(rdata)

    def cache_keywords(self):
        for k, v in self.BOTMETA[u'files'].items():
            if not v.get(u'keywords'):
                continue
            for kw in v[u'keywords']:
                if kw not in self.KEYWORDS:
                    self.KEYWORDS[kw] = k

    def clean_body(self, body, internal=False):
        body = body.lower()
        body = body.strip()
        for SC in self.STOPCHARS:
            if body.startswith(SC):
                body = body.lstrip(SC)
                body = body.strip()
            if body.endswith(SC):
                body = body.rstrip(SC)
                body = body.strip()
            if internal and SC in body:
                body = body.replace(SC, u'')
                body = body.strip()
        body = body.strip()
        return body

    def match(self, issuewrapper):
        iw = issuewrapper
        matchdata = self.match_components(
            iw.title,
            iw.body,
            iw.template_data.get(u'component_raw'),
            files=iw.files
        )
        return matchdata

    def match_components(self, title, body, component, files=None):
        """Make a list of matching files with metadata"""

        self.strategy = None
        self.strategies = []

        # No matching necessary for PRs, but should provide consistent api
        if files:
            matched_filenames = files[:]
        else:
            matched_filenames = []
            if component is None:
                return matched_filenames

            logging.debug(u'match "{}"'.format(component))

            delimiters = [u'\n', u',', u' + ', u' & ']
            delimited = False
            for delimiter in delimiters:
                if delimiter in component:
                    delimited = True
                    components = component.split(delimiter)
                    for _component in components:
                        _matches = self._match_component(title, body, _component)
                        self.strategies.append(self.strategy)

                        # bypass for blacklist
                        if None in _matches:
                            _matches = []

                        matched_filenames += _matches

                    # do not process any more delimiters
                    break

            if not delimited:
                matched_filenames += self._match_component(title, body, component)
                self.strategies.append(self.strategy)

                # bypass for blacklist
                if None in matched_filenames:
                    return []

            # reduce subpaths
            if matched_filenames:
                matched_filenames = self.reduce_filepaths(matched_filenames)

        # create metadata for each matched file
        component_matches = []
        matched_filenames = sorted(set(matched_filenames))
        for fn in matched_filenames:
            component_matches.append(self.get_meta_for_file(fn))

        return component_matches

    def _match_component(self, title, body, component):
        """Find matches for a single line"""
        matched_filenames = []

        # context sets the path prefix to narrow the search window
        if u'module_util' in title.lower() or u'module_util' in component.lower():
            context = u'lib/ansible/module_utils'
        elif u'module util' in title.lower() or u'module util' in component.lower():
            context = u'lib/ansible/module_utils'
        elif u'module' in title.lower() or u'module' in component.lower():
            context = u'lib/ansible/modules'
        elif u'dynamic inventory' in title.lower() or u'dynamic inventory' in component.lower():
            context = u'contrib/inventory'
        elif u'inventory script' in title.lower() or u'inventory script' in component.lower():
            context = u'contrib/inventory'
        elif u'inventory plugin' in title.lower() or u'inventory plugin' in component.lower():
            context = u'lib/ansible/plugins/inventory'
        else:
            context = None

        if not component:
            return []

        if component not in self.STOPWORDS and component not in self.STOPCHARS:

            if not matched_filenames:
                matched_filenames += self.search_by_keywords(component, exact=True)
                if matched_filenames:
                    self.strategy = u'search_by_keywords'

            if not matched_filenames:
                matched_filenames += self.search_by_module_name(component)
                if matched_filenames:
                    self.strategy = u'search_by_module_name'

            if not matched_filenames:
                matched_filenames += self.search_by_regex_module_globs(component)
                if matched_filenames:
                    self.strategy = u'search_by_regex_module_globs'

            if not matched_filenames:
                matched_filenames += self.search_by_regex_modules(component)
                if matched_filenames:
                    self.strategy = u'search_by_regex_modules'

            if not matched_filenames:
                matched_filenames += self.search_by_regex_generic(component)
                if matched_filenames:
                    self.strategy = u'search_by_regex_generic'

            if not matched_filenames:
                matched_filenames += self.search_by_regex_urls(component)
                if matched_filenames:
                    self.strategy = u'search_by_regex_urls'

            if not matched_filenames:
                matched_filenames += self.search_by_tracebacks(component)
                if matched_filenames:
                    self.strategy = u'search_by_tracebacks'

            if not matched_filenames:
                matched_filenames += self.search_by_filepath(component, context=context)
                if matched_filenames:
                    self.strategy = u'search_by_filepath'
                if not matched_filenames:
                    matched_filenames += self.search_by_filepath(component, partial=True)
                    if matched_filenames:
                        self.strategy = u'search_by_filepath[partial]'

            if not matched_filenames:
                matched_filenames += self.search_by_keywords(component, exact=False)
                if matched_filenames:
                    self.strategy = u'search_by_keywords!exact'

            if matched_filenames:
                matched_filenames += self.include_modules_from_test_targets(matched_filenames)

        return matched_filenames

    def search_by_module_name(self, component):
        matches = []

        component = self.clean_body(component)

        # docker-container vs. docker_container
        if component not in self.MODULE_NAMES:
            component = component.replace(u'-', u'_')

        if component in self.MODULE_NAMES:
            mmatch = self.find_module_match(component)
            if mmatch:
                if isinstance(mmatch, list):
                    for x in mmatch:
                        matches.append(x[u'repo_filename'])
                else:
                    matches.append(mmatch[u'repo_filename'])

        return matches

    def search_by_keywords(self, component, exact=True):
        """Simple keyword search"""

        component = component.lower()
        matches = []
        if component in self.STOPWORDS:
            matches = [None]
        elif component in self.KEYWORDS:
            matches = [self.KEYWORDS[component]]
        elif not exact:
            for k, v in self.KEYWORDS.items():
                if u' ' + k + u' ' in component or u' ' + k + u' ' in component.lower():
                    logging.debug(u'keyword match: {}'.format(k))
                    matches.append(v)
                elif u' ' + k + u':' in component or u' ' + k + u':' in component:
                    logging.debug(u'keyword match: {}'.format(k))
                    matches.append(v)
                elif component.endswith(u' ' + k) or component.lower().endswith(u' ' + k):
                    logging.debug(u'keyword match: {}'.format(k))
                    matches.append(v)

                elif (k in component or k in component.lower()) and k in self.BLACKLIST:
                    logging.debug(u'blacklist  match: {}'.format(k))
                    matches.append(None)

        return matches

    def search_by_regex_urls(self, body):
        # http://docs.ansible.com/ansible/latest/copy_module.html
        # http://docs.ansible.com/ansible/latest/dev_guide/developing_modules.html
        # http://docs.ansible.com/ansible/latest/postgresql_db_module.html
        # [helm module](https//docs.ansible.com/ansible/2.4/helm_module.html)
        # Windows module: win_robocopy\nhttp://docs.ansible.com/ansible/latest/win_robocopy_module.html
        # Examples:\n* archive (https://docs.ansible.com/ansible/archive_module.html)\n* s3_sync (https://docs.ansible.com/ansible/s3_sync_module.html)
        # https//github.com/ansible/ansible/blob/devel/lib/ansible/modules/windows/win_dsc.ps1L228

        matches = []

        urls = re.findall(
            u'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
            body
        )
        if urls:
            for url in urls:
                url = url.rstrip(u')')
                if u'/blob' in url and url.endswith(u'.py'):
                    parts = url.split(u'/')
                    bindex = parts.index(u'blob')
                    fn = u'/'.join(parts[bindex+2:])
                    matches.append(fn)
                elif u'_module.html' in url:
                    parts = url.split(u'/')
                    fn = parts[-1].replace(u'_module.html', u'')
                    choices = [x for x in self.gitrepo.files if u'/' + fn in x or u'/_' + fn in x]
                    choices = [x for x in choices if u'lib/ansible/modules' in x]

                    if len(choices) > 1:
                        choices = [x for x in choices if u'/' + fn + u'.py' in x or u'/' + fn + u'.ps1' in x or u'/_' + fn + u'.py' in x]

                    if not choices:
                        pass
                    elif len(choices) == 1:
                        matches.append(choices[0])
                    else:
                        pass
                else:
                    pass

        return matches

    def search_by_regex_modules(self, body):
        # foo module
        # foo and bar modules
        # foo* modules
        # foo* module

        body = body.lower()
        logging.debug(u'attempt regex match on: {}'.format(body))

        # https://www.tutorialspoint.com/python/python_reg_expressions.htm
        patterns = [
            r'\:\n(\S+)\.py',
            r'(\S+)\.py',
            r'\-(\s+)(\S+)(\s+)module',
            r'\`ansible_module_(\S+)\.py\`',
            r'module(\s+)\-(\s+)(\S+)',
            r'module(\s+)(\S+)',
            r'\`(\S+)\`(\s+)module',
            r'(\S+)(\s+)module',
            r'the (\S+) command',
            r'(\S+) \(.*\)',
            r'(\S+)\-module',
            r'modules/(\S+)',
            r'module\:(\s+)\`(\S+)\`',
            r'module\: (\S+)',
            r'module (\S+)',
            r'module `(\S+)`',
            r'module: (\S+)',
            r'new (\S+) module',
            r'the (\S+) module',
            r'the \"(\S+)\" module',
            r':\n(\S+) module',
            r'(\S+) module',
            r'(\S+) core module',
            r'(\S+) extras module',
            r':\n\`(\S+)\` module',
            r'\`(\S+)\` module',
            r'`(\S+)` module',
            r'(\S+)\* modules',
            r'(\S+) and (\S+)',
            r'(\S+) or (\S+)',
            r'(\S+) \+ (\S+)',
            r'(\S+) \& (\S)',
            r'(\S+) and (\S+) modules',
            r'(\S+) or (\S+) module',
            r'(\S+)_module',
            r'action: (\S+)',
            r'action (\S+)',
            r'ansible_module_(\S+)\.py',
            r'ansible_module_(\S+)',
            r'ansible_modules_(\S+)\.py',
            r'ansible_modules_(\S+)',
            r'(\S+) task',
            r'(\s+)\((\S+)\)',
            r'(\S+)(\s+)(\S+)(\s+)modules',
            r'(\S+)(\s+)module\:(\s+)(\S+)',
            r'\-(\s+)(\S+)(\s+)module',
            r'\:(\s+)(\S+)(\s+)module',
            r'\-(\s+)ansible(\s+)(\S+)(\s+)(\S+)(\s+)module',
            r'.*(\s+)(\S+)(\s+)module.*'
        ]

        matches = []

        logging.debug(u'check patterns against: {}'.format(body))

        for pattern in patterns:
            mobj = re.match(pattern, body, re.M | re.I)

            if mobj:
                logging.debug(u'pattern {} matched on "{}"'.format(pattern, body))

                for x in range(0, mobj.lastindex+1):
                    try:
                        mname = mobj.group(x)
                        logging.debug(u'mname: {}'.format(mname))
                        if mname == body:
                            continue
                        mname = self.clean_body(mname)
                        if not mname.strip():
                            continue
                        mname = mname.strip().lower()
                        if u' ' in mname:
                            continue
                        if u'/' in mname:
                            continue

                        mname = mname.replace(u'.py', u'').replace(u'.ps1', u'')
                        logging.debug(u'--> {}'.format(mname))

                        # attempt to match a module
                        module_match = self.find_module_match(mname)

                        if not module_match:
                            pass
                        elif isinstance(module_match, list):
                            for m in module_match:
                                matches.append(m[u'repo_filename'])
                        elif isinstance(module_match, dict):
                            matches.append(module_match[u'repo_filename'])
                    except Exception as e:
                        logging.error(e)

                if matches:
                    break

        return matches

    def search_by_regex_module_globs(self, body):
        # All AWS modules
        # BigIP modules
        # NXOS modules
        # azurerm modules

        matches = []
        body = self.clean_body(body)
        logging.debug(u'try globs on: {}'.format(body))

        keymap = {
            u'all': None,
            u'ec2': u'lib/ansible/modules/cloud/amazon',
            u'ec2_*': u'lib/ansible/modules/cloud/amazon',
            u'aws': u'lib/ansible/modules/cloud/amazon',
            u'amazon': u'lib/ansible/modules/cloud/amazon',
            u'google': u'lib/ansible/modules/cloud/google',
            u'gce': u'lib/ansible/modules/cloud/google',
            u'gcp': u'lib/ansible/modules/cloud/google',
            u'bigip': u'lib/ansible/modules/network/f5',
            u'nxos': u'lib/ansible/modules/network/nxos',
            u'azure': u'lib/ansible/modules/cloud/azure',
            u'azurerm': u'lib/ansible/modules/cloud/azure',
            u'openstack': u'lib/ansible/modules/cloud/openstack',
            u'ios': u'lib/ansible/modules/network/ios',
        }

        regexes = [
            r'(\S+) ansible modules',
            r'all (\S+) based modules',
            r'all (\S+) modules',
            r'.* all (\S+) modules.*',
            r'(\S+) modules',
            r'(\S+\*) modules',
            r'all cisco (\S+\*) modules',
        ]

        mobj = None
        for x in regexes:
            mobj = re.match(x, body)
            if mobj:
                logging.debug(u'matched glob: {}'.format(x))
                break

        if not mobj:
            logging.debug(u'no glob matches')

        if mobj:
            keyword = mobj.group(1)
            if not keyword.strip():
                pass
            elif keyword in keymap:
                if keymap[keyword]:
                    matches.append(keymap[keyword])
            else:

                if u'*' in keyword:
                    keyword = keyword.replace(u'*', u'')

                # check for directories first
                fns = [x for x in self.MODULE_NAMESPACE_DIRECTORIES if keyword in x]

                # check for files second
                if not fns:
                    fns = [x for x in self.gitrepo.module_files
                           if u'lib/ansible/modules' in x
                           and keyword in x]

                if fns:
                    matches += fns

        if matches:
            matches = sorted(set(matches))

        return matches

    def search_by_regex_generic(self, body):
        # foo dynamic inventory script
        # foo filter

        # https://www.tutorialspoint.com/python/python_reg_expressions.htm
        patterns = [
            [r'(.*) action plugin', u'lib/ansible/plugins/action'],
            [r'(.*) inventory plugin', u'lib/ansible/plugins/inventory'],
            [r'(.*) dynamic inventory', u'contrib/inventory'],
            [r'(.*) dynamic inventory (script|file)', u'contrib/inventory'],
            [r'(.*) inventory script', u'contrib/inventory'],
            [r'(.*) filter', u'lib/ansible/plugins/filter'],
            [r'(.*) jinja filter', u'lib/ansible/plugins/filter'],
            [r'(.*) jinja2 filter', u'lib/ansible/plugins/filter'],
            [r'(.*) template filter', u'lib/ansible/plugins/filter'],
            [r'(.*) fact caching plugin', u'lib/ansible/plugins/cache'],
            [r'(.*) fact caching module', u'lib/ansible/plugins/cache'],
            [r'(.*) lookup plugin', u'lib/ansible/plugins/lookup'],
            [r'(.*) lookup', u'lib/ansible/plugins/lookup'],
            [r'(.*) callback plugin', u'lib/ansible/plugins/callback'],
            [r'(.*)\.py callback', u'lib/ansible/plugins/callback'],
            [r'callback plugin (.*)', u'lib/ansible/plugins/callback'],
            [r'(.*) stdout callback', u'lib/ansible/plugins/callback'],
            [r'stdout callback (.*)', u'lib/ansible/plugins/callback'],
            [r'stdout_callback (.*)', u'lib/ansible/plugins/callback'],
            [r'(.*) callback plugin', u'lib/ansible/plugins/callback'],
            [r'(.*) connection plugin', u'lib/ansible/plugins/connection'],
            [r'(.*) connection type', u'lib/ansible/plugins/connection'],
            [r'(.*) connection', u'lib/ansible/plugins/connection'],
            [r'(.*) transport', u'lib/ansible/plugins/connection'],
            [r'connection=(.*)', u'lib/ansible/plugins/connection'],
            [r'connection: (.*)', u'lib/ansible/plugins/connection'],
            [r'connection (.*)', u'lib/ansible/plugins/connection'],
            [r'strategy (.*)', u'lib/ansible/plugins/strategy'],
            [r'(.*) strategy plugin', u'lib/ansible/plugins/strategy'],
            [r'(.*) module util', u'lib/ansible/module_utils'],
            [r'ansible-galaxy (.*)', u'lib/ansible/galaxy'],
            [r'ansible-playbook (.*)', u'lib/ansible/playbook'],
            [r'ansible/module_utils/(.*)', u'lib/ansible/module_utils'],
            [r'module_utils/(.*)', u'lib/ansible/module_utils'],
            [r'lib/ansible/module_utils/(.*)', u'lib/ansible/module_utils'],
            [r'(\S+) documentation fragment', u'lib/ansible/utils/module_docs_fragments'],
        ]

        body = self.clean_body(body)

        matches = []

        for pattern in patterns:
            mobj = re.match(pattern[0], body, re.M | re.I)

            if mobj:
                logging.debug(u'pattern hit: {}'.format(pattern))
                fname = mobj.group(1)
                fname = fname.lower()

                fpath = os.path.join(pattern[1], fname)

                if fpath in self.gitrepo.files:
                    matches.append(fpath)
                elif os.path.join(pattern[1], fname + u'.py') in self.gitrepo.files:
                    fname = os.path.join(pattern[1], fname + u'.py')
                    matches.append(fname)
                else:
                    # fallback to the directory
                    matches.append(pattern[1])

        return matches

    def search_by_tracebacks(self, body):

        matches = []

        if u'Traceback (most recent call last)' in body:
            lines = body.split(u'\n')
            for line in lines:
                line = line.strip()
                if line.startswith(u'DistributionNotFound'):
                    matches = [u'setup.py']
                    break
                elif line.startswith(u'File'):
                    fn = line.split()[1]
                    for SC in self.STOPCHARS:
                        fn = fn.replace(SC, u'')
                    if u'ansible_module_' in fn:
                        fn = os.path.basename(fn)
                        fn = fn.replace(u'ansible_module_', u'')
                        matches = [fn]
                    elif u'cli/playbook.py' in fn:
                        fn = u'lib/ansible/cli/playbook.py'
                    elif u'module_utils' in fn:
                        idx = fn.find(u'module_utils/')
                        fn = u'lib/ansible/' + fn[idx:]
                    elif u'ansible/' in fn:
                        idx = fn.find(u'ansible/')
                        fn1 = fn[idx:]

                        if u'bin/' in fn1:
                            if not fn1.startswith(u'bin'):

                                idx = fn1.find(u'bin/')
                                fn1 = fn1[idx:]

                                if fn1.endswith(u'.py'):
                                    fn1 = fn1.rstrip(u'.py')

                        elif u'cli/' in fn1:
                            idx = fn1.find(u'cli/')
                            fn1 = fn1[idx:]
                            fn1 = u'lib/ansible/' + fn1

                        elif u'lib' not in fn1:
                            fn1 = u'lib/' + fn1

                        if fn1 not in self.files:
                            pass

        return matches

    def search_by_filepath(self, body, partial=False, context=None):
        """Find known filepaths in body"""

        matches = []
        body = self.clean_body(body)

        if not body:
            return []
        if body.lower() in self.STOPCHARS:
            return []
        if body.lower() in self.STOPWORDS:
            return []

        # 'inventory manager' vs. 'inventory/manager'
        if partial and u' ' in body:
            body = body.replace(u' ', u'/')

        if u'site-packages' in body:
            res = re.match(u'(.*)/site-packages/(.*)', body)
            body = res.group(2)
        if u'modules/core/' in body:
            body = body.replace(u'modules/core/', u'modules/')
        if u'modules/extras/' in body:
            body = body.replace(u'modules/extras/', u'modules/')
        if u'ansible-modules-core/' in body:
            body = body.replace(u'ansible-modules-core/', u'/')
        if u'ansible-modules-extras/' in body:
            body = body.replace(u'ansible-modules-extras/', u'/')
        if body.startswith(u'ansible/lib/ansible'):
            body = body.replace(u'ansible/lib', u'lib')
        if body.startswith(u'ansible/') and not body.startswith(u'ansible/modules'):
            body = body.replace(u'ansible/', u'', 1)
        if u'module/' in body:
            body = body.replace(u'module/', u'modules/')

        logging.debug(u'search filepath [{}] [{}]: {}'.format(context, partial, body))

        if len(body) < 2:
            return []

        if u'/' in body:
            body_paths = body.split(u'/')
        elif u' ' in body:
            body_paths = body.split()
            body_paths = [x.strip() for x in body_paths if x.strip()]
        else:
            body_paths = [body]

        if u'networking' in body_paths:
            ix = body_paths.index(u'networking')
            body_paths[ix] = u'network'
        if u'plugin' in body_paths:
            ix = body_paths.index(u'plugin')
            body_paths[ix] = u'plugins'

        if not context or u'lib/ansible/modules' in context:
            mmatch = self.find_module_match(body)
            if mmatch:
                if isinstance(mmatch, list) and len(mmatch) > 1:

                    # only allow for exact prefix globbing here ...
                    if [x for x in mmatch if x[u'repo_filename'].startswith(body)]:
                        return [x[u'repo_filename'] for x in mmatch]

                elif isinstance(mmatch, list):
                    return [x[u'repo_filename'] for x in mmatch]
                else:
                    return [mmatch[u'repo_filename']]

        if body in self.gitrepo.files:
            matches = [body]
        else:
            for fn in self.gitrepo.files:

                # limit the search set if a context is given
                if context is not None and not fn.startswith(context):
                    continue

                if fn.endswith((body, body + u'.py', body + u'.ps1')):
                    # ios_config.py -> test_ios_config.py vs. ios_config.py
                    bn1 = os.path.basename(body)
                    bn2 = os.path.basename(fn)
                    if bn2.startswith(bn1):
                        matches = [fn]
                        break

                if partial:

                    # netapp_e_storagepool storage module
                    # lib/ansible/modules/storage/netapp/netapp_e_storagepool.py

                    # if all subpaths are in this filepath, it is a match
                    bp_total = 0
                    fn_paths = fn.split(u'/')
                    fn_paths.append(fn_paths[-1].replace(u'.py', u'').replace(u'.ps1', u''))

                    for bp in body_paths:
                        if bp in fn_paths:
                            bp_total += 1

                    if bp_total == len(body_paths):
                        matches = [fn]
                        break

                    elif bp_total > 1:

                        if (float(bp_total) / float(len(body_paths))) >= (2.0 / 3.0):
                            if fn not in matches:
                                matches.append(fn)

        if matches:
            tr = []
            for match in matches[:]:
                # reduce to longest path
                for m in matches:
                    if match == m:
                        continue
                    if len(m) < len(match) and match.startswith(m):
                        tr.append(m)

            for r in tr:
                if r in matches:
                    logging.debug(u'trimming {}'.format(r))
                    matches.remove(r)

        matches = sorted(set(matches))
        logging.debug(u'return: {}'.format(matches))

        return matches

    def reduce_filepaths(self, matches):

        # unique
        _matches = []
        for _match in matches:
            if _match not in _matches:
                _matches.append(_match)
        matches = _matches[:]

        # squash to longest path
        if matches:
            tr = []
            for match in matches[:]:
                # reduce to longest path
                for m in matches:
                    if match == m:
                        continue
                    if m is None or match is None:
                        continue
                    if len(m) < len(match) and match.startswith(m) or match.endswith(m):
                        tr.append(m)

            for r in tr:
                if r in matches:
                    matches.remove(r)
        return matches

    def include_modules_from_test_targets(self, matches):
        """Map test targets to the module files"""
        new_matches = []
        for match in matches:
            if not match:
                continue
            # include modules from test targets
            if u'test/integration/targets' in match:
                paths = match.split(u'/')
                tindex = paths.index(u'targets')
                mname = paths[tindex+1]
                mrs = self.find_module_match(mname, exact=True)
                if mrs:
                    if not isinstance(mrs, list):
                        mrs = [mrs]
                    for mr in mrs:
                        new_matches.append(mr[u'repo_filename'])
        return new_matches

    def get_meta_for_file(self, filename):
        meta = {
            u'repo_filename': filename,
            u'name': os.path.basename(filename).split(u'.')[0],
            u'notify': [],
            u'assign': [],
            u'authors': [],
            u'committers': [],
            u'maintainers': [],
            u'labels': [],
            u'ignore': [],
            u'support': None,
            u'supported_by': None,
            u'deprecated': False,
            u'topic': None,
            u'subtopic': None,
            u'supershipit': [],
            u'namespace': None,
            u'namespace_maintainers': [],
            u'metadata': {},
        }

        populated = False
        filenames = [filename, os.path.splitext(filename)[0]]

        # powershell meta is in the python file
        if filename.endswith(u'.ps1'):
            pyfile = filename.replace(u'.ps1', u'.py')
            if pyfile in self.BOTMETA[u'files']:
                filenames.append(pyfile)

        botmeta_entries = self.file_indexer._filenames_to_keys(filenames)
        for bme in botmeta_entries:
            logging.debug(u'matched botmeta entry: %s' % bme)

        # Modules contain metadata in docstrings and that should
        # be factored in ...
        #   https://github.com/ansible/ansibullbot/issues/1042
        #   https://github.com/ansible/ansibullbot/issues/1053
        if u'lib/ansible/modules' in filename:
            mmatch = self.find_module_match(filename)
            if len(mmatch) == 1 and mmatch[0][u'filename'] == filename:
                meta[u'metadata'].update(mmatch[0][u'metadata'])
                for k in u'authors', u'maintainers':
                    meta[k] += mmatch[0][k]
                meta[u'notify'] += mmatch[0][u'notified']

            if meta[u'metadata']:
                if meta[u'metadata'][u'supported_by']:
                    meta[u'support'] = meta[u'metadata'][u'supported_by']

        # reconcile the delta between a child and it's parents
        support_levels = {}

        for entry in botmeta_entries:
            fdata = self.BOTMETA[u'files'][entry].copy()

            if u'authors' in fdata:
                meta[u'notify'] += fdata[u'authors']
                meta[u'authors'] += fdata[u'authors']
            if u'maintainers' in fdata:
                meta[u'notify'] += fdata[u'maintainers']
                meta[u'assign'] += fdata[u'maintainers']
                meta[u'maintainers'] += fdata[u'maintainers']
            if u'notified' in fdata:
                meta[u'notify'] += fdata[u'notified']
            if u'labels' in fdata:
                meta[u'labels'] += fdata[u'labels']
            if u'ignore' in fdata:
                meta[u'ignore'] += fdata[u'ignore']
            if u'ignored' in fdata:
                meta[u'ignore'] += fdata[u'ignored']

            if u'support' in fdata:
                if isinstance(fdata[u'support'], list):
                    support_levels[entry] = fdata[u'support'][0]
                else:
                    support_levels[entry] = fdata[u'support']
            elif u'supported_by' in fdata:
                if isinstance(fdata[u'supported_by'], list):
                    support_levels[entry] = fdata[u'supported_by'][0]
                else:
                    support_levels[entry] = fdata[u'supported_by']

            # only "deprecate" exact matches
            if u'deprecated' in fdata and entry == filename:
                meta[u'deprecated'] = fdata[u'deprecated']

            populated = True

        # walk up the tree for more meta
        paths = filename.split(u'/')
        for idx, x in enumerate(paths):
            thispath = u'/'.join(paths[:(0-idx)])
            if thispath in self.BOTMETA[u'files']:
                fdata = self.BOTMETA[u'files'][thispath].copy()
                if u'support' in fdata:
                    if isinstance(fdata[u'support'], list):
                        support_levels[thispath] = fdata[u'support'][0]
                    else:
                        support_levels[thispath] = fdata[u'support']
                elif u'supported_by' in fdata:
                    if isinstance(fdata[u'supported_by'], list):
                        support_levels[thispath] = fdata[u'supported_by'][0]
                    else:
                        support_levels[thispath] = fdata[u'supported_by']
                if u'labels' in fdata:
                    meta[u'labels'] += fdata[u'labels']
                if u'maintainers' in fdata:
                    meta[u'notify'] += fdata[u'maintainers']
                    meta[u'assign'] += fdata[u'maintainers']
                    meta[u'maintainers'] += fdata[u'maintainers']
                if u'ignore' in fdata:
                    meta[u'ignore'] += fdata[u'ignore']
                if u'notified' in fdata:
                    meta[u'notify'] += fdata[u'notified']

        if u'lib/ansible/modules' in filename:
            topics = [x for x in paths if x not in [u'lib', u'ansible', u'modules']]
            topics = [x for x in topics if x != os.path.basename(filename)]
            if len(topics) == 2:
                meta[u'topic'] = topics[0]
                meta[u'subtopic'] = topics[1]
            elif len(topics) == 1:
                meta[u'topic'] = topics[0]

            meta[u'namespace'] = u'/'.join(topics)

        # set namespace maintainers (skip !modules for now)
        if filename.startswith(u'lib/ansible/modules'):
            ns = meta.get(u'namespace')
            keys = self.BOTMETA[u'files'].keys()
            keys = [x for x in keys if x.startswith(os.path.join(u'lib/ansible/modules', ns))]
            ignored = []

            for key in keys:
                meta[u'namespace_maintainers'] += self.BOTMETA[u'files'][key].get(u'maintainers', [])
                ignored += self.BOTMETA[u'files'][key].get(u'ignored', [])

            for ignoree in ignored:
                while ignoree in meta[u'namespace_maintainers']:
                    meta[u'namespace_maintainers'].remove(ignoree)

        # reconcile support levels
        if filename in support_levels:
            # exact match
            meta[u'support'] = support_levels[filename]
            meta[u'supported_by'] = support_levels[filename]
            logging.debug(u'%s support == %s' % (filename, meta[u'supported_by']))
        else:
            # pick the closest match
            keys = support_levels.keys()
            keys = sorted(keys, key=len, reverse=True)
            if keys:
                meta[u'support'] = support_levels[keys[0]]
                meta[u'supported_by'] = support_levels[keys[0]]
                logging.debug(u'%s support == %s' % (keys[0], meta[u'supported_by']))

        # new modules should default to "community" support
        if filename.startswith(u'lib/ansible/modules') and filename not in self.gitrepo.files:
            meta[u'support'] = u'community'
            meta[u'supported_by'] = u'community'

        # test targets for modules should inherit from their modules
        if filename.startswith(u'test/integration/targets') and filename not in self.BOTMETA[u'files']:
            whitelist = [
                u'labels',
                u'ignore',
                u'deprecated',
                u'authors',
                u'assign',
                u'maintainers',
                u'notify',
                u'topic',
                u'subtopic',
                u'support'
            ]

            paths = filename.split(u'/')
            tindex = paths.index(u'targets')
            mname = paths[tindex+1]
            mmatch = self._find_module_match(mname, exact=True)
            if mmatch:
                mmeta = self.get_meta_for_file(mmatch[0][u'repo_filename'])
                for k, v in mmeta.items():
                    if k in whitelist and v:
                        if isinstance(meta[k], list):
                            meta[k] = sorted(set(meta[k] + v))
                        elif not meta[k]:
                            meta[k] = v

            # make new test targets community by default
            if not meta[u'support'] and not meta[u'supported_by']:
                meta[u'support'] = u'community'

        # it's okay to remove things from legacy-files.txt
        if filename == u'test/sanity/pep8/legacy-files.txt' and not meta[u'support']:
            meta[u'support'] = u'community'

        # fallback to core support
        if not meta[u'support']:
            meta[u'support'] = u'core'

        # align support and supported_by
        if meta[u'support'] != meta[u'supported_by']:
            if meta[u'support'] and not meta[u'supported_by']:
                meta[u'supported_by'] = meta[u'support']
            elif not meta[u'support'] and meta[u'supported_by']:
                meta[u'support'] = meta[u'supported_by']

        # clean up the result
        _meta = meta.copy()
        for k, v in _meta.items():
            if isinstance(v, list):
                meta[k] = sorted(set(v))

        def get_ns_paths(repo_filename, files):
            """Emit all subpaths matching the given file list."""
            if not repo_filename:
                return

            namespace_paths = os.path.dirname(repo_filename)
            namespace_paths = namespace_paths.split(u'/')

            for x in reversed(range(0, len(namespace_paths) + 1)):
                this_ns_path = u'/'.join(namespace_paths[:x])
                if not this_ns_path:
                    continue
                print(u'check {}'.format(this_ns_path))
                if this_ns_path in files:
                    yield this_ns_path

        # walk up the botmeta tree looking for ignores to include
        for this_ns_path in get_ns_paths(
            meta.get(u'repo_filename'), self.BOTMETA[u'files'],
        ):
            this_ignore = (
                self.BOTMETA[u'files'][this_ns_path].get(u'ignore') or
                self.BOTMETA[u'files'][this_ns_path].get(u'ignored') or
                self.BOTMETA[u'files'][this_ns_path].get(u'ignores') or
                []
            )
            print(u'ignored: {}'.format(this_ignore))
            for username in this_ignore:
                if username not in meta[u'ignore']:
                    meta[u'ignore'].append(username)

        # process ignores AGAIN.
        if meta.get(u'ignore'):
            for k, v in meta.items():
                if k == u'ignore':
                    continue
                if not isinstance(v, list):
                    continue
                for ignoree in meta[u'ignore']:
                    if ignoree in v:
                        meta[k].remove(ignoree)

        # get supershipits
        if filename in self.BOTMETA[u'files']:
            if u'supershipit' in self.BOTMETA[u'files'][filename]:
                for username in self.BOTMETA[u'files'][filename][u'supershipit']:
                    if username not in meta[u'supershipit']:
                        meta[u'supershipit'].append(username)

        for this_ns_path in get_ns_paths(
            meta.get(u'repo_filename'), self.BOTMETA[u'files'],
        ):
            this_supershipit = self.BOTMETA[u'files'][this_ns_path].get(
                u'supershipit', [],
            )
            for username in this_supershipit:
                if username not in meta[u'supershipit']:
                    meta[u'supershipit'].append(username)

        return meta

    def find_module_match(self, pattern, exact=False):
        '''Exact module name matching'''

        logging.debug(u'find_module_match for "{}"'.format(pattern))
        candidate = None

        BLACKLIST = [
            u'module_utils',
            u'callback',
            u'network modules',
            u'networking modules'
            u'windows modules'
        ]

        if not pattern or pattern is None:
            return None

        # https://github.com/ansible/ansible/issues/19755
        if pattern == u'setup':
            pattern = u'lib/ansible/modules/system/setup.py'

        if u'/facts.py' in pattern or u' facts.py' in pattern:
            pattern = u'lib/ansible/modules/system/setup.py'

        # https://github.com/ansible/ansible/issues/18527
        #   docker-container -> docker_container
        if u'-' in pattern:
            pattern = pattern.replace(u'-', u'_')

        if u'module_utils' in pattern:
            # https://github.com/ansible/ansible/issues/20368
            return None
        elif u'callback' in pattern:
            return None
        elif u'lookup' in pattern:
            return None
        elif u'contrib' in pattern and u'inventory' in pattern:
            return None
        elif pattern.lower() in BLACKLIST:
            return None

        candidate = self._find_module_match(pattern, exact=exact)

        if not candidate:
            candidate = self._find_module_match(os.path.basename(pattern))

        if not candidate and u'/' in pattern and not pattern.startswith(u'lib/'):
            ppy = None
            ps1 = None
            if not pattern.endswith(u'.py') and not pattern.endswith(u'.ps1'):
                ppy = pattern + u'.py'
            if not pattern.endswith(u'.py') and not pattern.endswith(u'.ps1'):
                ps1 = pattern + u'.ps1'
            for mf in self.gitrepo.module_files:
                if pattern in mf:
                    if mf.endswith((pattern, ppy, ps1)):
                        candidate = mf
                        break

        return candidate

    def _find_module_match(self, pattern, exact=False):

        logging.debug(u'matching on {}'.format(pattern))

        matches = []

        if isinstance(pattern, six.text_type):
            pattern = to_text(to_bytes(pattern, 'ascii', 'ignore'), 'ascii')

        logging.debug(u'_find_module_match: {}'.format(pattern))

        noext = pattern.replace(u'.py', u'').replace(u'.ps1', u'')

        # exact is looking for a very precise name such as "vmware_guest"
        if exact:
            candidates = [pattern]
        else:
            candidates = [pattern, u'_' + pattern, noext, u'_' + noext]

        for k, v in self.MODULES.items():
            if v[u'name'] in candidates:
                logging.debug(u'match {} on name: {}'.format(k, v[u'name']))
                matches = [v]
                break

        if not matches:
            # search by key ... aka the filepath
            for k, v in self.MODULES.items():
                if k == pattern:
                    logging.debug(u'match {} on key: {}'.format(k, k))
                    matches = [v]
                    break

        # spellcheck
        if not exact and not matches and u'/' not in pattern:
            _pattern = pattern
            if not isinstance(_pattern, six.text_type):
                _pattern = to_text(_pattern)
            candidates = []
            for k, v in self.MODULES.items():
                vname = v[u'name']
                if not isinstance(vname, six.text_type):
                    vname = to_text(vname)
                jw = jaro_winkler(vname, _pattern)
                if jw > .9:
                    candidates.append((jw, k))
            for candidate in candidates:
                matches.append(self.MODULES[candidate[1]])

        return matches
