#!/usr/bin/env python

import datetime
import logging
import os
import re

from Levenshtein import jaro_winkler

from ansibullbot.parsers.botmetadata import BotMetadataParser
from ansibullbot.utils.extractors import ModuleExtractor
from ansibullbot.utils.git_tools import GitRepoWrapper
from ansibullbot.utils.systemtools import run_command


class AnsibleComponentMatcher(object):

    BOTMETA = {}
    INDEX = {}
    REPO = 'https://github.com/ansible/ansible'
    STOPWORDS = ['ansible', 'core', 'plugin']
    STOPCHARS = ['"', "'", '(', ')', '?', '*', '`', ',', ':', '?', '-']
    BLACKLIST = ['new module', 'new modules']
    FILE_NAMES = []
    MODULES = {}
    MODULE_NAMES = []
    MODULE_NAMESPACE_DIRECTORIES = []

    # FIXME: THESE NEED TO GO INTO BOTMETA
    # ALSO SEE search_by_regex_generic ...
    KEYWORDS = {
        'all': None,
        'ansiballz': 'lib/ansible/executor/module_common.py',
        'ansible-console': 'lib/ansible/cli/console.py',
        'ansible-galaxy': 'lib/ansible/galaxy',
        'ansible-inventory': 'lib/ansible/cli/inventory.py',
        'ansible-playbook': 'lib/ansible/playbook',
        'ansible playbook': 'lib/ansible/playbook',
        'ansible playbooks': 'lib/ansible/playbook',
        'ansible-pull': 'lib/ansible/cli/pull.py',
        'ansible-vault': 'lib/ansible/parsing/vault',
        'ansible-vault edit': 'lib/ansible/parsing/vault',
        'ansible-vault show': 'lib/ansible/parsing/vault',
        'ansible-vault decrypt': 'lib/ansible/parsing/vault',
        'ansible-vault encrypt': 'lib/ansible/parsing/vault',
        'async': 'lib/ansible/modules/utilities/logic/async_wrapper.py',
        'become': 'lib/ansible/playbook/become.py',
        'block': 'lib/ansible/playbook/block.py',
        'blocks': 'lib/ansible/playbook/block.py',
        'callback plugin': 'lib/ansible/plugins/callback',
        'callback plugins': 'lib/ansible/plugins/callback',
        'conditional': 'lib/ansible/playbook/conditional.py',
        'docs': 'docs',
        'delegate_to': 'lib/ansible/playbook/task.py',
        'facts': 'lib/ansible/module_utils/facts',
        'galaxy': 'lib/ansible/galaxy',
        'groupvars': 'lib/ansible/vars/hostvars.py',
        'group vars': 'lib/ansible/vars/hostvars.py',
        'handlers': 'lib/ansible/playbook/handler.py',
        'hostvars': 'lib/ansible/vars/hostvars.py',
        'host vars': 'lib/ansible/vars/hostvars.py',
        'integration tests': 'test/integration',
        'inventory script': 'contrib/inventory',
        'jinja2 template system': 'lib/ansible/template',
        'module_utils': 'lib/ansible/module_utils',
        'multiple modules': None,
        'new module(s) request': None,
        'new modules request': None,
        'new module request': None,
        'new module': None,
        'network_cli': 'lib/ansible/plugins/connection/network_cli.py',
        'network_cli.py': 'lib/ansible/plugins/connection/network_cli.py',
        'network modules': 'lib/ansible/modules/network',
        'paramiko': 'lib/ansible/plugins/connection/paramiko_ssh.py',
        'role': 'lib/ansible/playbook/role',
        'roles': 'lib/ansible/playbook/role',
        'ssh': 'lib/ansible/plugins/connection/ssh.py',
        'ssh authentication': 'lib/ansible/plugins/connection/ssh.py',
        'setup / facts': 'lib/ansible/modules/system/setup.py',
        'setup': 'lib/ansible/modules/system/setup.py',
        'task executor': 'lib/ansible/executor/task_executor.py',
        'testing': 'test/',
        'validate-modules': 'test/sanity/validate-modules',
        'vault': 'lib/ansible/parsing/vault',
        'vault edit': 'lib/ansible/parsing/vault',
        'vault documentation': 'lib/ansible/parsing/vault',
        'with_items': 'lib/ansible/playbook/loop_control.py',
        'windows modules': 'lib/ansible/modules/windows',
        'winrm': 'lib/ansible/plugins/connection/winrm.py'
    }

    def __init__(self, gitrepo=None, botmetafile=None, cachedir=None, module_indexer=None, email_cache=None):
        self.cachedir = cachedir
        self.botmetafile = botmetafile
        self.email_cache = email_cache

        if gitrepo:
            self.gitrepo = gitrepo
        else:
            self.gitrepo = GitRepoWrapper(cachedir=self.cachedir, repo=self.REPO)

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
            mname = mname.replace('.py', '').replace('.ps1', '')
            if mname.startswith('__'):
                continue
            mdata = {
                'name': mname,
                'repo_filename': fn,
                'filename': fn
            }
            if fn not in self.MODULES:
                self.MODULES[fn] = mdata.copy()
            else:
                self.MODULES[fn].update(mdata)

        self.MODULE_NAMESPACE_DIRECTORIES = [os.path.dirname(x) for x in self.gitrepo.module_files]
        self.MODULE_NAMESPACE_DIRECTORIES = sorted(set(self.MODULE_NAMESPACE_DIRECTORIES))

        # make a list of names by enumerating the files
        self.MODULE_NAMES = [os.path.basename(x) for x in self.gitrepo.module_files]
        self.MODULE_NAMES = [x for x in self.MODULE_NAMES if x.endswith('.py') or x.endswith('.ps1')]
        self.MODULE_NAMES = [x.replace('.ps1', '').replace('.py', '') for x in self.MODULE_NAMES]
        self.MODULE_NAMES = [x for x in self.MODULE_NAMES if not x.startswith('__')]
        self.MODULE_NAMES = sorted(set(self.MODULE_NAMES))

        # make a list of names by calling ansible-doc
        checkoutdir = self.gitrepo.checkoutdir
        checkoutdir = os.path.abspath(checkoutdir)
        cmd = 'source {}/hacking/env-setup; ansible-doc -t module -F'.format(checkoutdir)
        logging.debug(cmd)
        (rc, so, se) = run_command(cmd)
        lines = so.split('\n')
        for line in lines:

            parts = line.split()
            parts = [x.strip() for x in parts]

            if len(parts) != 2 or checkoutdir not in line:
                continue

            mname = parts[0]
            if mname not in self.MODULE_NAMES:
                self.MODULE_NAMES.append(mname)

            fpath = parts[1]
            fpath = fpath.replace(checkoutdir + '/', '')

            if fpath not in self.MODULES:
                self.MODULES[fpath] = {
                    'name': mname,
                    'repo_filename': fpath,
                    'filename': fpath
                }

        _modules = self.MODULES.copy()
        for k, v in _modules.items():
            kparts = os.path.splitext(k)
            if kparts[-1] == '.ps1':
                _k = kparts[0] + '.py'
                checkpath = os.path.join(checkoutdir, _k)
                if not os.path.isfile(checkpath):
                    _k = k
            else:
                _k = k
            ME = ModuleExtractor(os.path.join(checkoutdir, _k), email_cache=self.email_cache)
            if k not in self.BOTMETA['files']:
                self.BOTMETA['files'][k] = {
                    'deprecated': os.path.basename(k).startswith('_'),
                    'labels': os.path.dirname(k).split('/'),
                    'authors': ME.authors,
                    'maintainers': ME.authors,
                    'maintainers_keys': [],
                    'notify': ME.authors,
                    'ignored': [],
                    'support': ME.metadata.get('supported_by', 'community'),
                    'metadata': ME.metadata.copy()
                }
            else:
                bmeta = self.BOTMETA['files'][k].copy()
                bmeta['metadata'] = ME.metadata.copy()
                if 'notify' not in bmeta:
                    bmeta['notify'] = []
                if 'maintainers' not in bmeta:
                    bmeta['maintainers'] = []
                if not bmeta.get('supported_by'):
                    bmeta['supported_by'] = ME.metadata.get('supported_by', 'community')
                if 'authors' not in bmeta:
                    bmeta['authors'] = []
                for x in ME.authors:
                    if x not in bmeta['authors']:
                        bmeta['authors'].append(x)
                    if x not in bmeta['maintainers']:
                        bmeta['maintainers'].append(x)
                    if x not in bmeta['notify']:
                        bmeta['notify'].append(x)
                if not bmeta.get('labels'):
                    bmeta['labels'] = os.path.dirname(k).split('/')
                bmeta['deprecated'] = os.path.basename(k).startswith('_')
                self.BOTMETA['files'][k].update(bmeta)

            # clean out the ignorees
            if 'ignored' in self.BOTMETA['files'][k]:
                for ignoree in self.BOTMETA['files'][k]['ignored']:
                    for thiskey in ['maintainers', 'notify']:
                        while ignoree in self.BOTMETA['files'][k][thiskey]:
                            self.BOTMETA['files'][k][thiskey].remove(ignoree)

            # write back to the modules
            self.MODULES[k].update(self.BOTMETA['files'][k])

    def load_meta(self):
        if self.botmetafile is not None:
            with open(self.botmetafile, 'rb') as f:
                rdata = f.read()
        else:
            fp = '.github/BOTMETA.yml'
            rdata = self.gitrepo.get_file_content(fp)
        self.BOTMETA = BotMetadataParser.parse_yaml(rdata)

    def cache_keywords(self):
        for k, v in self.BOTMETA['files'].items():
            if not v.get('keywords'):
                continue
            for kw in v['keywords']:
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
                body = body.replace(SC, '')
                body = body.strip()
        body = body.strip()
        return body

    def match(self, issuewrapper):
        iw = issuewrapper
        matchdata = self.match_components(
            iw.title,
            iw.body,
            iw.template_data.get('component_raw'),
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

            component = component.encode('ascii', 'ignore')
            logging.debug('match "{}"'.format(component))

            delimiters = ['\n', ',', ' + ', ' & ']
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
        if 'module_util' in title.lower() or 'module_util' in component.lower():
            context = 'lib/ansible/module_utils'
        elif 'module util' in title.lower() or 'module util' in component.lower():
            context = 'lib/ansible/module_utils'
        elif 'module' in title.lower() or 'module' in component.lower():
            context = 'lib/ansible/modules'
        elif 'dynamic inventory' in title.lower() or 'dynamic inventory' in component.lower():
            context = 'contrib/inventory'
        elif 'inventory script' in title.lower() or 'inventory script' in component.lower():
            context = 'contrib/inventory'
        elif 'inventory plugin' in title.lower() or 'inventory plugin' in component.lower():
            context = 'lib/ansible/plugins/inventory'
        else:
            context = None

        if not component:
            return []

        if component not in self.STOPWORDS and component not in self.STOPCHARS:

            if not matched_filenames:
                matched_filenames += self.search_by_keywords(component, exact=True)
                if matched_filenames:
                    self.strategy = 'search_by_keywords'

            if not matched_filenames:
                matched_filenames += self.search_by_module_name(component)
                if matched_filenames:
                    self.strategy = 'search_by_module_name'

            if not matched_filenames:
                matched_filenames += self.search_by_regex_module_globs(component)
                if matched_filenames:
                    self.strategy = 'search_by_regex_module_globs'

            if not matched_filenames:
                matched_filenames += self.search_by_regex_modules(component)
                if matched_filenames:
                    self.strategy = 'search_by_regex_modules'

            if not matched_filenames:
                matched_filenames += self.search_by_regex_generic(component)
                if matched_filenames:
                    self.strategy = 'search_by_regex_generic'

            if not matched_filenames:
                matched_filenames += self.search_by_regex_urls(component)
                if matched_filenames:
                    self.strategy = 'search_by_regex_urls'

            if not matched_filenames:
                matched_filenames += self.search_by_tracebacks(component)
                if matched_filenames:
                    self.strategy = 'search_by_tracebacks'

            if not matched_filenames:
                matched_filenames += self.search_by_filepath(component, context=context)
                if matched_filenames:
                    self.strategy = 'search_by_filepath'
                if not matched_filenames:
                    matched_filenames += self.search_by_filepath(component, partial=True)
                    if matched_filenames:
                        self.strategy = 'search_by_filepath[partial]'

            if not matched_filenames:
                matched_filenames += self.search_by_keywords(component, exact=False)
                if matched_filenames:
                    self.strategy = 'search_by_keywords!exact'

            if matched_filenames:
                matched_filenames += self.include_modules_from_test_targets(matched_filenames)

        return matched_filenames

    def search_by_module_name(self, component):
        matches = []

        component = self.clean_body(component)

        # docker-container vs. docker_container
        if component not in self.MODULE_NAMES:
            component = component.replace('-', '_')

        if component in self.MODULE_NAMES:
            mmatch = self.find_module_match(component)
            if mmatch:
                if isinstance(mmatch, list):
                    for x in mmatch:
                        matches.append(x['repo_filename'])
                else:
                    matches.append(mmatch['repo_filename'])

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
                if ' ' + k + ' ' in component or ' ' + k + ' ' in component.lower():
                    logging.debug('keyword match: {}'.format(k))
                    matches.append(v)
                elif ' ' + k + ':' in component or ' ' + k + ':' in component:
                    logging.debug('keyword match: {}'.format(k))
                    matches.append(v)
                elif component.endswith(' ' + k) or component.lower().endswith(' ' + k):
                    logging.debug('keyword match: {}'.format(k))
                    matches.append(v)

                elif (k in component or k in component.lower()) and k in self.BLACKLIST:
                    logging.debug('blacklist  match: {}'.format(k))
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
            'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
            body
        )
        if urls:
            for url in urls:
                url = url.rstrip(')')
                if '/blob' in url and url.endswith('.py'):
                    parts = url.split('/')
                    bindex = parts.index('blob')
                    fn = '/'.join(parts[bindex+2:])
                    matches.append(fn)
                elif '_module.html' in url:
                    parts = url.split('/')
                    fn = parts[-1].replace('_module.html', '')
                    choices = [x for x in self.gitrepo.files if '/' + fn in x or '/_' + fn in x]
                    choices = [x for x in choices if 'lib/ansible/modules' in x]

                    if len(choices) > 1:
                        choices = [x for x in choices if '/' + fn + '.py' in x or '/' + fn + '.ps1' in x or '/_' + fn + '.py' in x]

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
        logging.debug('attempt regex match on: {}'.format(body))

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

        logging.debug('check patterns against: {}'.format(body))

        for pattern in patterns:
            mobj = re.match(pattern, body, re.M | re.I)

            if mobj:
                logging.debug('pattern {} matched on "{}"'.format(pattern, body))

                for x in range(0, mobj.lastindex+1):
                    try:
                        mname = mobj.group(x)
                        logging.debug('mname: {}'.format(mname))
                        if mname == body:
                            continue
                        mname = self.clean_body(mname)
                        if not mname.strip():
                            continue
                        mname = mname.strip().lower()
                        if ' ' in mname:
                            continue
                        if '/' in mname:
                            continue

                        mname = mname.replace('.py', '').replace('.ps1', '')
                        logging.debug('--> {}'.format(mname))

                        # attempt to match a module
                        module_match = self.find_module_match(mname)

                        if not module_match:
                            pass
                        elif isinstance(module_match, list):
                            for m in module_match:
                                matches.append(m['repo_filename'])
                        elif isinstance(module_match, dict):
                            matches.append(module_match['repo_filename'])
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
        logging.debug('try globs on: {}'.format(body))

        keymap = {
            'all': None,
            'ec2': 'lib/ansible/modules/cloud/amazon',
            'ec2_*': 'lib/ansible/modules/cloud/amazon',
            'aws': 'lib/ansible/modules/cloud/amazon',
            'amazon': 'lib/ansible/modules/cloud/amazon',
            'google': 'lib/ansible/modules/cloud/google',
            'gce': 'lib/ansible/modules/cloud/google',
            'gcp': 'lib/ansible/modules/cloud/google',
            'bigip': 'lib/ansible/modules/network/f5',
            'nxos': 'lib/ansible/modules/network/nxos',
            'azure': 'lib/ansible/modules/cloud/azure',
            'azurerm': 'lib/ansible/modules/cloud/azure',
            'openstack': 'lib/ansible/modules/cloud/openstack',
            'ios': 'lib/ansible/modules/network/ios',
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
                logging.debug('matched glob: {}'.format(x))
                break

        if not mobj:
            logging.debug('no glob matches')

        if mobj:
            keyword = mobj.group(1)
            if not keyword.strip():
                pass
            elif keyword in keymap:
                if keymap[keyword]:
                    matches.append(keymap[keyword])
            else:

                if '*' in keyword:
                    keyword = keyword.replace('*', '')

                # check for directories first
                fns = [x for x in self.MODULE_NAMESPACE_DIRECTORIES if keyword in x]

                # check for files second
                if not fns:
                    fns = [x for x in self.gitrepo.module_files if 'lib/ansible/modules' in x and keyword in x]

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
            [r'(.*) action plugin', 'lib/ansible/plugins/action'],
            [r'(.*) inventory plugin', 'lib/ansible/plugins/inventory'],
            [r'(.*) dynamic inventory', 'contrib/inventory'],
            [r'(.*) dynamic inventory (script|file)', 'contrib/inventory'],
            [r'(.*) inventory script', 'contrib/inventory'],
            [r'(.*) filter', 'lib/ansible/plugins/filter'],
            [r'(.*) jinja filter', 'lib/ansible/plugins/filter'],
            [r'(.*) jinja2 filter', 'lib/ansible/plugins/filter'],
            [r'(.*) template filter', 'lib/ansible/plugins/filter'],
            [r'(.*) fact caching plugin', 'lib/ansible/plugins/cache'],
            [r'(.*) fact caching module', 'lib/ansible/plugins/cache'],
            [r'(.*) lookup plugin', 'lib/ansible/plugins/lookup'],
            [r'(.*) lookup', 'lib/ansible/plugins/lookup'],
            [r'(.*) callback plugin', 'lib/ansible/plugins/callback'],
            [r'(.*)\.py callback', 'lib/ansible/plugins/callback'],
            [r'callback plugin (.*)', 'lib/ansible/plugins/callback'],
            [r'(.*) stdout callback', 'lib/ansible/plugins/callback'],
            [r'stdout callback (.*)', 'lib/ansible/plugins/callback'],
            [r'stdout_callback (.*)', 'lib/ansible/plugins/callback'],
            [r'(.*) callback plugin', 'lib/ansible/plugins/callback'],
            [r'(.*) connection plugin', 'lib/ansible/plugins/connection'],
            [r'(.*) connection type', 'lib/ansible/plugins/connection'],
            [r'(.*) connection', 'lib/ansible/plugins/connection'],
            [r'(.*) transport', 'lib/ansible/plugins/connection'],
            [r'connection=(.*)', 'lib/ansible/plugins/connection'],
            [r'connection: (.*)', 'lib/ansible/plugins/connection'],
            [r'connection (.*)', 'lib/ansible/plugins/connection'],
            [r'strategy (.*)', 'lib/ansible/plugins/strategy'],
            [r'(.*) strategy plugin', 'lib/ansible/plugins/strategy'],
            [r'(.*) module util', 'lib/ansible/module_utils'],
            [r'ansible-galaxy (.*)', 'lib/ansible/galaxy'],
            [r'ansible-playbook (.*)', 'lib/ansible/playbook'],
            [r'ansible/module_utils/(.*)', 'lib/ansible/module_utils'],
            [r'module_utils/(.*)', 'lib/ansible/module_utils'],
            [r'lib/ansible/module_utils/(.*)', 'lib/ansible/module_utils'],
            [r'(\S+) documentation fragment', 'lib/ansible/utils/module_docs_fragments'],
        ]

        body = self.clean_body(body)

        matches = []

        for pattern in patterns:
            mobj = re.match(pattern[0], body, re.M | re.I)

            if mobj:
                logging.debug('pattern hit: {}'.format(pattern))
                fname = mobj.group(1)
                fname = fname.lower()

                fpath = os.path.join(pattern[1], fname)

                if fpath in self.gitrepo.files:
                    matches.append(fpath)
                elif os.path.join(pattern[1], fname + '.py') in self.gitrepo.files:
                    fname = os.path.join(pattern[1], fname + '.py')
                    matches.append(fname)
                else:
                    # fallback to the directory
                    matches.append(pattern[1])

        return matches

    def search_by_tracebacks(self, body):

        matches = []

        if 'Traceback (most recent call last)' in body:
            lines = body.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('DistributionNotFound'):
                    matches = ['setup.py']
                    break
                elif line.startswith('File'):
                    fn = line.split()[1]
                    for SC in self.STOPCHARS:
                        fn = fn.replace(SC, '')
                    if 'ansible_module_' in fn:
                        fn = os.path.basename(fn)
                        fn = fn.replace('ansible_module_', '')
                        matches = [fn]
                    elif 'cli/playbook.py' in fn:
                        fn = 'lib/ansible/cli/playbook.py'
                    elif 'module_utils' in fn:
                        idx = fn.find('module_utils/')
                        fn = 'lib/ansible/' + fn[idx:]
                    elif 'ansible/' in fn:
                        idx = fn.find('ansible/')
                        fn1 = fn[idx:]

                        if 'bin/' in fn1:
                            if not fn1.startswith('bin'):

                                idx = fn1.find('bin/')
                                fn1 = fn1[idx:]

                                if fn1.endswith('.py'):
                                    fn1 = fn1.rstrip('.py')

                        elif 'cli/' in fn1:
                            idx = fn1.find('cli/')
                            fn1 = fn1[idx:]
                            fn1 = 'lib/ansible/' + fn1

                        elif 'lib' not in fn1:
                            fn1 = 'lib/' + fn1

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
        if partial and ' ' in body:
            body = body.replace(' ', '/')

        if 'site-packages' in body:
            res = re.match('(.*)/site-packages/(.*)', body)
            body = res.group(2)
        if 'modules/core/' in body:
            body = body.replace('modules/core/', 'modules/')
        if 'modules/extras/' in body:
            body = body.replace('modules/extras/', 'modules/')
        if 'ansible-modules-core/' in body:
            body = body.replace('ansible-modules-core/', '/')
        if 'ansible-modules-extras/' in body:
            body = body.replace('ansible-modules-extras/', '/')
        if body.startswith('ansible/lib/ansible'):
            body = body.replace('ansible/lib', 'lib')
        if body.startswith('ansible/') and not body.startswith('ansible/modules'):
            body = body.replace('ansible/', '', 1)
        if 'module/' in body:
            body = body.replace('module/', 'modules/')

        logging.debug('search filepath [{}] [{}]: {}'.format(context, partial, body))

        if len(body) < 2:
            return []

        if '/' in body:
            body_paths = body.split('/')
        elif ' ' in body:
            body_paths = body.split()
            body_paths = [x.strip() for x in body_paths if x.strip()]
        else:
            body_paths = [body]

        if 'networking' in body_paths:
            ix = body_paths.index('networking')
            body_paths[ix] = 'network'
        if 'plugin' in body_paths:
            ix = body_paths.index('plugin')
            body_paths[ix] = 'plugins'

        if not context or 'lib/ansible/modules' in context:
            mmatch = self.find_module_match(body)
            if mmatch:
                if isinstance(mmatch, list) and len(mmatch) > 1:

                    # only allow for exact prefix globbing here ...
                    if [x for x in mmatch if x['repo_filename'].startswith(body)]:
                        return [x['repo_filename'] for x in mmatch]

                elif isinstance(mmatch, list):
                    return [x['repo_filename'] for x in mmatch]
                else:
                    return [mmatch['repo_filename']]

        if body in self.gitrepo.files:
            matches = [body]
        else:
            for fn in self.gitrepo.files:

                # limit the search set if a context is given
                if context is not None and not fn.startswith(context):
                    continue

                if fn.endswith(body) or fn.endswith(body + '.py') or fn.endswith(body + '.ps1'):
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
                    fn_paths = fn.split('/')
                    fn_paths.append(fn_paths[-1].replace('.py', '').replace('.ps1', ''))

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
                    if len(m) < match and match.startswith(m):
                        tr.append(m)

            for r in tr:
                if r in matches:
                    logging.debug('trimming {}'.format(r))
                    matches.remove(r)

        matches = sorted(set(matches))
        logging.debug('return: {}'.format(matches))

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
                    if len(m) < match and match.startswith(m) or match.endswith(m):
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
            if 'test/integration/targets' in match:
                paths = match.split('/')
                tindex = paths.index('targets')
                mname = paths[tindex+1]
                mrs = self.find_module_match(mname, exact=True)
                if mrs:
                    if not isinstance(mrs, list):
                        mrs = [mrs]
                    for mr in mrs:
                        new_matches.append(mr['repo_filename'])
        return new_matches

    def get_meta_for_file(self, filename):
        meta = {
            'repo_filename': filename,
            'name': os.path.basename(filename).split('.')[0],
            'notify': [],
            'assign': [],
            'authors': [],
            'committers': [],
            'maintainers': [],
            'labels': [],
            'ignore': [],
            'support': None,
            'supported_by': None,
            'deprecated': False,
            'topic': None,
            'subtopic': None,
            'namespace': None,
            'namespace_maintainers': []
        }

        populated = False
        _filename = filename
        _filename = os.path.splitext(filename)[0]

        if filename in self.BOTMETA['files'] or _filename in self.BOTMETA['files']:

            if filename in self.BOTMETA['files']:
                fdata = self.BOTMETA['files'][filename].copy()
            elif _filename in self.BOTMETA['files']:
                fdata = self.BOTMETA['files'][_filename].copy()

            # powershell meta is in the python file
            if filename.endswith('.ps1'):
                pyfile = filename.replace('.ps1', '.py')
                if pyfile in self.BOTMETA['files']:
                    fdata.update(self.BOTMETA['files'][pyfile])

            if 'authors' in fdata:
                meta['authors'] = fdata['authors']
            if 'maintainers' in fdata:
                meta['notify'] += fdata['maintainers']
                meta['assign'] += fdata['maintainers']
                meta['maintainers'] += fdata['maintainers']
            if 'notify' in fdata:
                meta['notify'] += fdata['notify']
            if 'labels' in fdata:
                meta['labels'] += fdata['labels']
            if 'ignore' in fdata:
                meta['ignore'] += fdata['ignore']
            if 'ignored' in fdata:
                meta['ignore'] += fdata['ignored']
            if 'support' in fdata:
                if isinstance(fdata['support'], list):
                    meta['support'] = fdata['support'][0]
                else:
                    meta['support'] = fdata['support']
            elif 'supported_by' in fdata:
                    if isinstance(fdata['supported_by'], list):
                        meta['support'] = fdata['supported_by'][0]
                    else:
                        meta['support'] = fdata['supported_by']

            if 'deprecated' in fdata:
                meta['deprecated'] = fdata['deprecated']

            populated = True

        # walk up the tree for more meta
        paths = filename.split('/')
        for idx, x in enumerate(paths):
            thispath = '/'.join(paths[:(0-idx)])
            if thispath in self.BOTMETA['files']:
                fdata = self.BOTMETA['files'][thispath].copy()
                if 'support' in fdata and not meta['support']:
                    if isinstance(fdata['support'], list):
                        meta['support'] = fdata['support'][0]
                    else:
                        meta['support'] = fdata['support']
                if 'labels' in fdata:
                    meta['labels'] += fdata['labels']
                if 'maintainers' in fdata:
                    meta['notify'] += fdata['maintainers']
                    meta['assign'] += fdata['maintainers']
                    meta['maintainers'] += fdata['maintainers']
                if 'ignore' in fdata:
                    meta['ignore'] += fdata['ignore']
                if 'notify' in fdata:
                    meta['notify'] += fdata['notify']

        if 'lib/ansible/modules' in filename:
            topics = [x for x in paths if x not in ['lib', 'ansible', 'modules']]
            topics = [x for x in topics if x != os.path.basename(filename)]
            if len(topics) == 2:
                meta['topic'] = topics[0]
                meta['subtopic'] = topics[1]
            elif len(topics) == 1:
                meta['topic'] = topics[0]

            meta['namespace'] = '/'.join(topics)

        # set namespace maintainers (skip !modules for now)
        if filename.startswith('lib/ansible/modules'):
            ns = meta.get('namespace')
            keys = self.BOTMETA['files'].keys()
            keys = [x for x in keys if x.startswith(os.path.join('lib/ansible/modules', ns))]
            ignored = []

            for key in keys:
                meta['namespace_maintainers'] += self.BOTMETA['files'][key].get('maintainers', [])
                ignored += self.BOTMETA['files'][key].get('ignored', [])

            for ignoree in ignored:
                while ignoree in meta['namespace_maintainers']:
                    meta['namespace_maintainers'].remove(ignoree)

        # new modules should default to "community" support
        if filename.startswith('lib/ansible/modules') and filename not in self.gitrepo.files:
            meta['support'] = 'community'
            meta['supported_by'] = 'community'

        # test targets for modules should inherit from their modules
        if filename.startswith('test/integration/targets') and filename not in self.BOTMETA['files']:
            whitelist = [
                'labels',
                'ignore',
                'deprecated',
                'authors',
                'assign',
                'maintainers',
                'notify',
                'topic',
                'subtopic',
                'support'
            ]

            paths = filename.split('/')
            tindex = paths.index('targets')
            mname = paths[tindex+1]
            mmatch = self._find_module_match(mname, exact=True)
            if mmatch:
                mmeta = self.get_meta_for_file(mmatch[0]['repo_filename'])
                for k, v in mmeta.items():
                    if k in whitelist and v:
                        if isinstance(meta[k], list):
                            meta[k] = sorted(set(meta[k] + v))
                        elif not meta[k]:
                            meta[k] = v

            # make new test targets community by default
            if not meta['support'] and not meta['supported_by']:
                meta['support'] = 'community'

        # it's okay to remove things from legacy-files.txt
        if filename == 'test/sanity/pep8/legacy-files.txt' and not meta['support']:
            meta['support'] = 'community'

        # fallback to core support
        if not meta['support']:
            meta['support'] = 'core'

        # align support and supported_by
        if meta['support'] != meta['supported_by']:
            if meta['support'] and not meta['supported_by']:
                meta['supported_by'] = meta['support']
            elif not meta['support'] and meta['supported_by']:
                meta['support'] = meta['supported_by']

        # clean up the result
        _meta = meta.copy()
        for k, v in _meta.items():
            if isinstance(v, list):
                meta[k] = sorted(set(v))

        # walk up the botmeta tree looking for ignores to include
        if meta.get('repo_filename'):
            namespace_paths = os.path.dirname(meta['repo_filename'])
            namespace_paths = namespace_paths.split('/')
            for x in reversed(range(0, len(namespace_paths) + 1)):
                this_ns_path = '/'.join(namespace_paths[:x])
                if not this_ns_path:
                    continue
                print('check {}'.format(this_ns_path))
                if this_ns_path in self.BOTMETA['files']:
                    this_ignore = self.BOTMETA['files'][this_ns_path].get('ignore') or \
                        self.BOTMETA['files'][this_ns_path].get('ignored') or \
                        self.BOTMETA['files'][this_ns_path].get('ignores')
                    print('ignored: {}'.format(this_ignore))
                    if this_ignore:
                        for username in this_ignore:
                            if username not in meta['ignore']:
                                meta['ignore'].append(username)

        # process ignores AGAIN.
        if meta.get('ignore'):
            for k, v in meta.items():
                if k == 'ignore':
                    continue
                if not isinstance(v, list):
                    continue
                for ignoree in meta['ignore']:
                    if ignoree in v:
                        meta[k].remove(ignoree)

        return meta

    def find_module_match(self, pattern, exact=False):
        '''Exact module name matching'''

        logging.debug('find_module_match for "{}"'.format(pattern))
        candidate = None

        BLACKLIST = [
            'module_utils',
            'callback',
            'network modules',
            'networking modules'
            'windows modules'
        ]

        if not pattern or pattern is None:
            return None

        # https://github.com/ansible/ansible/issues/19755
        if pattern == 'setup':
            pattern = 'lib/ansible/modules/system/setup.py'

        if '/facts.py' in pattern or ' facts.py' in pattern:
            pattern = 'lib/ansible/modules/system/setup.py'

        # https://github.com/ansible/ansible/issues/18527
        #   docker-container -> docker_container
        if '-' in pattern:
            pattern = pattern.replace('-', '_')

        if 'module_utils' in pattern:
            # https://github.com/ansible/ansible/issues/20368
            return None
        elif 'callback' in pattern:
            return None
        elif 'lookup' in pattern:
            return None
        elif 'contrib' in pattern and 'inventory' in pattern:
            return None
        elif pattern.lower() in BLACKLIST:
            return None

        candidate = self._find_module_match(pattern, exact=exact)

        if not candidate:
            candidate = self._find_module_match(os.path.basename(pattern))

        if not candidate and '/' in pattern and not pattern.startswith('lib/'):
            ppy = None
            ps1 = None
            if not pattern.endswith('.py') and not pattern.endswith('.ps1'):
                ppy = pattern + '.py'
            if not pattern.endswith('.py') and not pattern.endswith('.ps1'):
                ps1 = pattern + '.ps1'
            for mf in self.gitrepo.module_files:
                if pattern in mf:
                    if mf.endswith(pattern) or mf.endswith(ppy) or mf.endswith(ps1):
                        candidate = mf
                        break

        return candidate

    def _find_module_match(self, pattern, exact=False):

        logging.debug('matching on {}'.format(pattern))

        matches = []

        if isinstance(pattern, unicode):
            pattern = pattern.encode('ascii', 'ignore')

        logging.debug('_find_module_match: {}'.format(pattern))

        noext = pattern.replace('.py', '').replace('.ps1', '')

        # exact is looking for a very precise name such as "vmware_guest"
        if exact:
            candidates = [pattern]
        else:
            candidates = [pattern, '_' + pattern, noext, '_' + noext]

        for k, v in self.MODULES.items():
            if v['name'] in candidates:
                logging.debug('match {} on name: {}'.format(k, v['name']))
                matches = [v]
                break

        if not matches:
            # search by key ... aka the filepath
            for k, v in self.MODULES.items():
                if k == pattern:
                    logging.debug('match {} on key: {}'.format(k, k))
                    matches = [v]
                    break

        # spellcheck
        if not exact and not matches and '/' not in pattern:
            _pattern = pattern
            if not isinstance(_pattern, unicode):
                _pattern = _pattern.decode('utf-8')
            candidates = []
            for k, v in self.MODULES.items():
                vname = v['name']
                if not isinstance(vname, unicode):
                    vname = vname.decode('utf-8')
                jw = jaro_winkler(vname, _pattern)
                if jw > .9:
                    candidates.append((jw, k))
            for candidate in candidates:
                matches.append(self.MODULES[candidate[1]])

        return matches
