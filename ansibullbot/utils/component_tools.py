#!/usr/bin/env python

import copy
import datetime
import json
import logging
import os
import re

from collections import OrderedDict

from Levenshtein import jaro_winkler

from ansibullbot._text_compat import to_bytes, to_text
from ansibullbot.utils.extractors import ModuleExtractor
from ansibullbot.utils.git_tools import GitRepoWrapper
from ansibullbot.utils.systemtools import run_command

from ansibullbot.utils.galaxy import GalaxyQueryTool


MODULES_FLATTEN_MAP = {
    'lib/ansible/modules/inventory/add_host.py': 'lib/ansible/modules/add_host.py',
    'lib/ansible/modules/packaging/os/apt.py': 'lib/ansible/modules/apt.py',
    'lib/ansible/modules/packaging/os/apt_key.py': 'lib/ansible/modules/apt_key.py',
    'lib/ansible/modules/packaging/os/apt_repository.py': 'lib/ansible/modules/apt_repository.py',
    'lib/ansible/modules/files/assemble.py': 'lib/ansible/modules/assemble.py',
    'lib/ansible/modules/utilities/logic/assert.py': 'lib/ansible/modules/assert.py',
    'lib/ansible/modules/utilities/logic/async_status.py': 'lib/ansible/modules/async_status.py',
    'lib/ansible/modules/utilities/logic/async_wrapper.py': 'lib/ansible/modules/async_wrapper.py',
    'lib/ansible/modules/files/blockinfile.py': 'lib/ansible/modules/blockinfile.py',
    'lib/ansible/modules/commands/command.py': 'lib/ansible/modules/command.py',
    'lib/ansible/modules/files/copy.py': 'lib/ansible/modules/copy.py',
    'lib/ansible/modules/system/cron.py': 'lib/ansible/modules/cron.py',
    'lib/ansible/modules/system/debconf.py': 'lib/ansible/modules/debconf.py',
    'lib/ansible/modules/utilities/logic/debug.py': 'lib/ansible/modules/debug.py',
    'lib/ansible/modules/packaging/os/dnf.py': 'lib/ansible/modules/dnf.py',
    'lib/ansible/modules/packaging/os/dpkg_selections.py': 'lib/ansible/modules/dpkg_selections.py',
    'lib/ansible/modules/commands/expect.py': 'lib/ansible/modules/expect.py',
    'lib/ansible/modules/utilities/logic/fail.py': 'lib/ansible/modules/fail.py',
    'lib/ansible/modules/files/fetch.py': 'lib/ansible/modules/fetch.py',
    'lib/ansible/modules/files/file.py': 'lib/ansible/modules/file.py',
    'lib/ansible/modules/files/find.py': 'lib/ansible/modules/find.py',
    'lib/ansible/modules/system/gather_facts.py': 'lib/ansible/modules/gather_facts.py',
    'lib/ansible/modules/net_tools/basics/get_url.py': 'lib/ansible/modules/get_url.py',
    'lib/ansible/modules/system/getent.py': 'lib/ansible/modules/getent.py',
    'lib/ansible/modules/source_control/git.py': 'lib/ansible/modules/git.py',
    'lib/ansible/modules/system/group.py': 'lib/ansible/modules/group.py',
    'lib/ansible/modules/inventory/group_by.py': 'lib/ansible/modules/group_by.py',
    'lib/ansible/modules/system/hostname.py': 'lib/ansible/modules/hostname.py',
    'lib/ansible/modules/utilities/logic/import_playbook.py': 'lib/ansible/modules/import_playbook.py',
    'lib/ansible/modules/utilities/logic/import_role.py': 'lib/ansible/modules/import_role.py',
    'lib/ansible/modules/utilities/logic/import_tasks.py': 'lib/ansible/modules/import_tasks.py',
    'lib/ansible/modules/utilities/logic/include.py': 'lib/ansible/modules/include.py',
    'lib/ansible/modules/utilities/logic/include_role.py': 'lib/ansible/modules/include_role.py',
    'lib/ansible/modules/utilities/logic/include_tasks.py': 'lib/ansible/modules/include_tasks.py',
    'lib/ansible/modules/utilities/logic/include_vars.py': 'lib/ansible/modules/include_vars.py',
    'lib/ansible/modules/system/iptables.py': 'lib/ansible/modules/iptables.py',
    'lib/ansible/modules/system/known_hosts.py': 'lib/ansible/modules/known_hosts.py',
    'lib/ansible/modules/files/lineinfile.py': 'lib/ansible/modules/lineinfile.py',
    'lib/ansible/modules/utilities/helper/meta.py': 'lib/ansible/modules/meta.py',
    'lib/ansible/modules/packaging/os/package.py': 'lib/ansible/modules/package.py',
    'lib/ansible/modules/packaging/os/package_facts.py': 'lib/ansible/modules/package_facts.py',
    'lib/ansible/modules/utilities/logic/pause.py': 'lib/ansible/modules/pause.py',
    'lib/ansible/modules/system/ping.py': 'lib/ansible/modules/ping.py',
    'lib/ansible/modules/packaging/language/pip.py': 'lib/ansible/modules/pip.py',
    'lib/ansible/modules/commands/raw.py': 'lib/ansible/modules/raw.py',
    'lib/ansible/modules/system/reboot.py': 'lib/ansible/modules/reboot.py',
    'lib/ansible/modules/files/replace.py': 'lib/ansible/modules/replace.py',
    'lib/ansible/modules/packaging/os/rpm_key.py': 'lib/ansible/modules/rpm_key.py',
    'lib/ansible/modules/commands/script.py': 'lib/ansible/modules/script.py',
    'lib/ansible/modules/system/service.py': 'lib/ansible/modules/service.py',
    'lib/ansible/modules/system/service_facts.py': 'lib/ansible/modules/service_facts.py',
    'lib/ansible/modules/utilities/logic/set_fact.py': 'lib/ansible/modules/set_fact.py',
    'lib/ansible/modules/utilities/logic/set_stats.py': 'lib/ansible/modules/set_stats.py',
    'lib/ansible/modules/system/setup.py': 'lib/ansible/modules/setup.py',
    'lib/ansible/modules/commands/shell.py': 'lib/ansible/modules/shell.py',
    'lib/ansible/modules/net_tools/basics/slurp.py': 'lib/ansible/modules/slurp.py',
    'lib/ansible/modules/files/stat.py': 'lib/ansible/modules/stat.py',
    'lib/ansible/modules/source_control/subversion.py': 'lib/ansible/modules/subversion.py',
    'lib/ansible/modules/system/systemd.py': 'lib/ansible/modules/systemd.py',
    'lib/ansible/modules/system/sysvinit.py': 'lib/ansible/modules/sysvinit.py',
    'lib/ansible/modules/files/tempfile.py': 'lib/ansible/modules/tempfile.py',
    'lib/ansible/modules/files/template.py': 'lib/ansible/modules/template.py',
    'lib/ansible/modules/files/unarchive.py': 'lib/ansible/modules/unarchive.py',
    'lib/ansible/modules/net_tools/basics/uri.py': 'lib/ansible/modules/uri.py',
    'lib/ansible/modules/system/user.py': 'lib/ansible/modules/user.py',
    'lib/ansible/modules/utilities/logic/wait_for.py': 'lib/ansible/modules/wait_for.py',
    'lib/ansible/modules/utilities/logic/wait_for_connection.py': 'lib/ansible/modules/wait_for_connection.py',
    'lib/ansible/modules/packaging/os/yum.py': 'lib/ansible/modules/yum.py',
    'lib/ansible/modules/packaging/os/yum_repository.py': 'lib/ansible/modules/yum_repository.py',
}


def make_prefixes(filename):
    # make a byte by byte list of prefixes for this fp
    indexes = range(0, len(filename) + 1)
    indexes = [1-x for x in indexes]
    indexes = [x for x in indexes if x < 0]
    indexes = [None] + indexes
    prefixes = [filename[:x] for x in indexes]
    return prefixes


class AnsibleComponentMatcher:

    botmeta = {}
    GALAXY_FILES = {}
    GALAXY_MANIFESTS = {}
    REPO = 'https://github.com/ansible/ansible'
    STOPWORDS = ['ansible', 'core', 'plugin']
    STOPCHARS = ['"', "'", '(', ')', '?', '*', '`', ',', ':', '?', '-']
    BLACKLIST = ['new module', 'new modules']
    MODULES = OrderedDict()
    MODULE_NAMES = []
    MODULE_NAMESPACE_DIRECTORIES = []

    # FIXME: THESE NEED TO GO INTO botmeta
    # ALSO SEE search_by_regex_generic ...
    KEYWORDS = {
        'N/A': 'lib/ansible/cli/__init__.py',
        'n/a': 'lib/ansible/cli/__init__.py',
        'all': 'lib/ansible/cli/__init__.py',
        'ansiballz': 'lib/ansible/executor/module_common.py',
        'ansible-console': 'lib/ansible/cli/console.py',
        'ansible-galaxy': 'lib/ansible/galaxy',
        'ansible-inventory': 'lib/ansible/cli/inventory.py',
        'ansible logging': 'lib/ansible/plugins/callback/default.py',
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
        'bot': 'docs/docsite/rst/community/development_process.rst',
        'callback plugin': 'lib/ansible/plugins/callback',
        'callback plugins': 'lib/ansible/plugins/callback',
        'callbacks': 'lib/ansible/plugins/callback/__init__.py',
        'cli': 'lib/ansible/cli/__init__.py',
        'conditional': 'lib/ansible/playbook/conditional.py',
        'core': 'lib/ansible/cli/__init__.py',
        'docs': 'docs/docsite/README.md',
        'docs.ansible.com': 'docs/docsite/README.md',
        'delegate_to': 'lib/ansible/playbook/task.py',
        'ec2.py dynamic inventory script': 'contrib/inventory/ec2.py',
        'ec2 dynamic inventory script': 'contrib/inventory/ec2.py',
        'ec2 inventory script': 'contrib/inventory/ec2.py',
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
        'logging': 'lib/ansible/plugins/callback/default.py',
        'module_utils': 'lib/ansible/module_utils',
        'multiple modules': None,
        'new module(s) request': None,
        'new modules request': None,
        'new module request': None,
        'new module': None,
        'network_cli': 'lib/ansible/plugins/connection/network_cli.py',
        'network_cli.py': 'lib/ansible/plugins/connection/network_cli.py',
        'network modules': 'lib/ansible/modules/network',
        'nxos': 'lib/ansible/modules/network/nxos/__init__.py',
        'paramiko': 'lib/ansible/plugins/connection/paramiko_ssh.py',
        'redis fact caching': 'lib/ansible/plugins/cache/redis.py',
        'role': 'lib/ansible/playbook/role',
        'roles': 'lib/ansible/playbook/role',
        'ssh': 'lib/ansible/plugins/connection/ssh.py',
        'ssh authentication': 'lib/ansible/plugins/connection/ssh.py',
        'setup / facts': 'lib/ansible/modules/system/setup.py',
        'setup': 'lib/ansible/modules/system/setup.py',
        'task executor': 'lib/ansible/executor/task_executor.py',
        'testing': 'test/',
        #u'validate-modules': u'test/sanity/validate-modules',
        'validate-modules': 'test/sanity/code-smell',
        'vault': 'lib/ansible/parsing/vault',
        'vault edit': 'lib/ansible/parsing/vault',
        'vault documentation': 'lib/ansible/parsing/vault',
        'with_items': 'lib/ansible/playbook/loop_control.py',
        'windows modules': 'lib/ansible/modules/windows',
        'winrm': 'lib/ansible/plugins/connection/winrm.py'
    }

    def __init__(self, gitrepo=None, botmeta=None, usecache=False, cachedir=None, commit=None, email_cache=None, use_galaxy=False):
        self.usecache = usecache
        self.cachedir = cachedir
        self.use_galaxy = use_galaxy
        self.botmeta = botmeta if botmeta else {'files': {}}
        self.email_cache = email_cache
        self.commit = commit

        if gitrepo:
            self.gitrepo = gitrepo
        else:
            self.gitrepo = GitRepoWrapper(cachedir=cachedir, repo=self.REPO, commit=self.commit)

        # we need to query galaxy for a few things ...
        if not use_galaxy:
            self.GQT = None
        else:
            self.GQT = GalaxyQueryTool(cachedir=self.cachedir)

        self.strategy = None
        self.strategies = []

        self.updated_at = None
        self.update()

    def update(self, email_cache=None, usecache=False, use_galaxy=True, botmeta=None):
        if botmeta is not None:
            self.botmeta = botmeta
        if self.GQT is not None and use_galaxy:
            self.GQT.update()
        if email_cache:
            self.email_cache = email_cache
        self.index_files()
        self.cache_keywords()
        self.updated_at = datetime.datetime.now()

    def get_module_meta(self, checkoutdir, filename):

        if self.cachedir:
            cdir = os.path.join(self.cachedir, 'module_extractor_cache')
        else:
            cdir = '/tmp/ansibot_module_extractor_cache'
        if not os.path.exists(cdir) and self.usecache:
            os.makedirs(cdir)
        cfile = os.path.join(cdir, '%s.json' % os.path.basename(filename))

        bmeta = None
        if not os.path.exists(cfile) or not self.usecache:
            bmeta = {}
            efile = os.path.join(checkoutdir, filename)
            if not os.path.exists(efile):
                fdata = self.gitrepo.get_file_content(filename, follow=True)
                ME = ModuleExtractor(None, filedata=fdata, email_cache=self.email_cache)
            else:
                ME = ModuleExtractor(os.path.join(checkoutdir, filename), email_cache=self.email_cache)
            if filename not in self.botmeta['files']:
                bmeta = {
                    'deprecated': os.path.basename(filename).startswith('_'),
                    'labels': os.path.dirname(filename).split('/'),
                    'authors': ME.authors,
                    'maintainers': ME.authors,
                    'maintainers_keys': [],
                    'notified': ME.authors,
                    'ignored': [],
                    'support': 'core' if os.path.exists(efile) else 'community',
                }
            else:
                bmeta = self.botmeta['files'][filename].copy()
                if 'notified' not in bmeta:
                    bmeta['notified'] = []
                if 'maintainers' not in bmeta:
                    bmeta['maintainers'] = []
                if not bmeta.get('supported_by'):
                    bmeta['supported_by'] = 'community'
                if 'authors' not in bmeta:
                    bmeta['authors'] = []
                for x in ME.authors:
                    if x not in bmeta['authors']:
                        bmeta['authors'].append(x)
                    if x not in bmeta['maintainers']:
                        bmeta['maintainers'].append(x)
                    if x not in bmeta['notified']:
                        bmeta['notified'].append(x)
                if not bmeta.get('labels'):
                    bmeta['labels'] = os.path.dirname(filename).split('/')
                bmeta['deprecated'] = os.path.basename(filename).startswith('_')

            # clean out the ignorees
            if 'ignored' in bmeta:
                for ignoree in bmeta['ignored']:
                    for thiskey in ['maintainers', 'notified']:
                        while ignoree in bmeta[thiskey]:
                            bmeta[thiskey].remove(ignoree)

            if self.usecache:
                with open(cfile, 'w') as f:
                    f.write(json.dumps(bmeta))

        if bmeta is None and self.usecache:
            with open(cfile) as f:
                bmeta = json.loads(f.read())

        return bmeta

    def index_files(self):
        self.MODULES = OrderedDict()
        self.MODULE_NAMES = []
        self.MODULE_NAMESPACE_DIRECTORIES = []

        for fn in self.gitrepo.module_files:
            if self.gitrepo.isdir(fn):
                continue
            if not self.gitrepo.exists(fn):
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

        self.MODULE_NAMESPACE_DIRECTORIES = (os.path.dirname(x) for x in self.gitrepo.module_files)
        self.MODULE_NAMESPACE_DIRECTORIES = sorted(set(self.MODULE_NAMESPACE_DIRECTORIES))

        # make a list of names by enumerating the files
        self.MODULE_NAMES = (os.path.basename(x) for x in self.gitrepo.module_files)
        self.MODULE_NAMES = (x for x in self.MODULE_NAMES if x.endswith(('.py', '.ps1')))
        self.MODULE_NAMES = (x.replace('.ps1', '').replace('.py', '') for x in self.MODULE_NAMES)
        self.MODULE_NAMES = (x for x in self.MODULE_NAMES if not x.startswith('__'))
        self.MODULE_NAMES = sorted(set(self.MODULE_NAMES))

        # append module names from botmeta
        bmodules = [x for x in self.botmeta['files'] if x.startswith('lib/ansible/modules')]
        bmodules = [x for x in bmodules if x.endswith('.py') or x.endswith('.ps1')]
        bmodules = [x for x in bmodules if '__init__' not in x]
        for bmodule in bmodules:
            mn = os.path.basename(bmodule).replace('.py', '').replace('.ps1', '')
            mn = mn.lstrip('_')
            if mn not in self.MODULE_NAMES:
                self.MODULE_NAMES.append(mn)
            if bmodule not in self.MODULES:
                self.MODULES[bmodule] = {
                    'filename': bmodule,
                    'repo_filename': bmodule,
                    'name': mn
                }

        # make a list of names by calling ansible-doc
        checkoutdir = self.gitrepo.checkoutdir
        checkoutdir = os.path.abspath(checkoutdir)
        cmd = f'. {checkoutdir}/hacking/env-setup; ansible-doc -t module -F'
        logging.debug(cmd)
        (rc, so, se) = run_command(cmd, cwd=checkoutdir)
        if rc != 0:
            raise Exception("'ansible-doc' command failed (%s, %s %s)" % (rc, so, se))
        lines = to_text(so).split('\n')
        for line in lines:

            # compat for macos tmpdirs
            if ' /private' in line:
                line = line.replace(' /private', '', 1)

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
            logging.debug('extract %s' % k)
            # FIXME fmeta = self.get_module_meta(checkoutdir, k, _k)
            fmeta = self.get_module_meta(checkoutdir, k)
            if k in self.botmeta['files']:
                self.botmeta['files'][k].update(fmeta)
            else:
                self.botmeta['files'][k] = copy.deepcopy(fmeta)
            self.MODULES[k].update(fmeta)

    def cache_keywords(self):
        for k, v in self.botmeta['files'].items():
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
        matched_filenames = None

        #import epdb; epdb.st()

        # No matching necessary for PRs, but should provide consistent api
        if files:
            matched_filenames = files[:]
        elif not component or component is None:
            return []
        elif ' ' not in component and '\n' not in component and component.startswith('lib/') and self.gitrepo.existed(component):
            matched_filenames = [component]
        else:
            matched_filenames = []
            if component is None:
                return matched_filenames

            logging.debug(f'match "{component}"')

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

        # mitigate flattening of the modules directory
        if matched_filenames:
            matched_filenames = [MODULES_FLATTEN_MAP.get(fn, fn) for fn in matched_filenames]

        # create metadata for each matched file
        component_matches = []
        matched_filenames = sorted(set(matched_filenames))
        for fn in matched_filenames:
            component_matches.append(self.get_meta_for_file(fn))
            if self.gitrepo.exists(fn):
                component_matches[-1]['exists'] = True
                component_matches[-1]['existed'] = True
            elif self.gitrepo.existed(fn):
                component_matches[-1]['exists'] = False
                component_matches[-1]['existed'] = True
            else:
                component_matches[-1]['exists'] = False
                component_matches[-1]['existed'] = False

        return component_matches

    def search_ecosystem(self, component):

        # never search collections for files that still exist
        if self.gitrepo.exists(component):
            return []

        if component.endswith('/') and self.gitrepo.exists(component.rstrip('/')):
            return []

        matched_filenames = []

        '''
        # botmeta -should- be the source of truth, but it's proven not to be ...
        if not matched_filenames:
            matched_filenames += self.search_by_botmeta_migrated_to(component)
        '''

        if self.GQT is not None:
            # see what is actually in galaxy ...
            matched_filenames += self.GQT.search_galaxy(component)

            # fallback to searching for migrated directories ...
            if not matched_filenames and component.startswith('lib/ansible/modules'):
                matched_filenames += self.GQT.fuzzy_search_galaxy(component)

        return matched_filenames

    def _match_component(self, title, body, component):
        """Find matches for a single line"""

        if not component:
            return []

        matched_filenames = []

        # sometimes we get urls ...
        #   https://github.com/ansible/ansible/issues/68553
        #   https//github.com/ansible/ansible/blob/devel/docs/docsite/rst/user_guide...
        if component.startswith('http'):
            if '/blob/' in component:
                # chop off the branch+path
                component = component.split('/blob/')[-1]
                # chop off the path
                component = component.split('/', 1)[-1]

        # don't neeed to match if it's a known file ...
        if self.gitrepo.exists(component.strip()):
            return [component.strip()]

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
        elif 'integration test' in title.lower() or 'integration test' in component.lower():
            context = 'test/integration/targets'
            component = component.replace('integration test', '').strip()
        else:
            context = None

        if component not in self.STOPWORDS and component not in self.STOPCHARS:

            '''
            if not matched_filenames:
                matched_filenames += self.search_by_botmeta_migrated_to(component)
                if matched_filenames:
                    self.strategy = u'search_by_botmeta_migrated_to'

            if not matched_filenames:
                matched_filenames += self.search_by_galaxy(component)
                if matched_filenames:
                    self.strategy = u'search_by_galaxy'
            '''

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

    def search_by_botmeta_migrated_to(self, component):
        '''Is this a file belonging to a collection?'''

        matches = []

        # narrow searching to modules/utils/plugins
        if component.startswith('lib/ansible') and not (
                component.startswith('lib/ansible/plugins') or not
                component.startswith('lib/ansible/module')):
            return matches

        if os.path.basename(component) == '__init__.py':
            return matches

        if component.startswith('test/lib'):
            return matches

        # check for matches in botmeta first in case there's a migrated_to key ...
        botmeta_candidates = []
        for bmkey in self.botmeta['files'].keys():
            # skip tests because we dont want false positives
            if not bmkey.startswith('lib/ansible'):
                continue
            if not self.botmeta['files'][bmkey].get('migrated_to'):
                continue

            if 'modules/' in component and 'modules/' not in bmkey:
                continue
            if 'lookup' in component and 'lookup' not in bmkey:
                continue
            if 'filter' in component and 'filter' not in bmkey:
                continue
            if 'inventory' in component and 'inventory' not in bmkey:
                continue

            if bmkey == component or os.path.basename(bmkey).replace('.py', '') == os.path.basename(component).replace('.py', ''):
                mt = self.botmeta['files'][bmkey].get('migrated_to')[0]
                for fn,gcollections in self.GALAXY_FILES.items():
                    if mt not in gcollections:
                        continue
                    if os.path.basename(fn).replace('.py', '') != os.path.basename(component).replace('.py', ''):
                        continue
                    if 'modules/' in component and 'modules/' not in fn:
                        continue
                    if 'lookup' in component and 'lookup' not in fn:
                        continue
                    if 'filter' in component and 'filter' not in fn:
                        continue
                    if 'inventory' in component and 'inventory' not in fn:
                        continue
                    botmeta_candidates.append('collection:%s:%s' % (mt, fn))
                    logging.info('matched %s to %s to %s:%s' % (component, bmkey, mt, fn))

        if botmeta_candidates:
            return botmeta_candidates

        return matches

    """
    def search_by_galaxy(self, component):
        '''Is this a file belonging to a collection?'''

        matches = []

        # narrow searching to modules/utils/plugins
        if component.startswith('lib/ansible') and not (
                component.startswith('lib/ansible/plugins') or not
                component.startswith('lib/ansible/module')):
            return matches

        if os.path.basename(component) == '__init__.py':
            return matches

        if component.startswith('test/lib'):
            return matches

        candidates = []
        for key in self.GALAXY_FILES.keys():
            if not (component in key or key == component):
                continue
            if not key.startswith('plugins'):
                continue
            keybn = os.path.basename(key).replace('.py', '')
            if keybn != component:
                continue

            logging.info(u'matched %s to %s:%s' % (component, key, self.GALAXY_FILES[key]))
            candidates.append(key)

        if candidates:
            for cn in candidates:
                for fqcn in self.GALAXY_FILES[cn]:
                    if fqcn.startswith('testing.'):
                        continue
                    matches.append('collection:%s:%s' % (fqcn, cn))
            matches = sorted(set(matches))

        #import epdb; epdb.st()

        return matches
    """

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
                    logging.debug(f'keyword match: {k}')
                    matches.append(v)
                elif ' ' + k + ':' in component or ' ' + k + ':' in component:
                    logging.debug(f'keyword match: {k}')
                    matches.append(v)
                elif component.endswith(' ' + k) or component.lower().endswith(' ' + k):
                    logging.debug(f'keyword match: {k}')
                    matches.append(v)

                elif (k in component or k in component.lower()) and k in self.BLACKLIST:
                    logging.debug(f'blacklist  match: {k}')
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
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
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
        logging.debug(f'attempt regex match on: {body}')

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

        logging.debug(f'check patterns against: {body}')

        for pattern in patterns:
            mobj = re.match(pattern, body, re.M | re.I)

            if mobj:
                logging.debug(f'pattern {pattern} matched on "{body}"')

                for x in range(0, mobj.lastindex+1):
                    try:
                        mname = mobj.group(x)
                        logging.debug(f'mname: {mname}')
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
                        logging.debug(f'--> {mname}')

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
        logging.debug(f'try globs on: {body}')

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
                logging.debug(f'matched glob: {x}')
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
                    fns = [x for x in self.gitrepo.module_files
                           if 'lib/ansible/modules' in x
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
                logging.debug(f'pattern hit: {pattern}')
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
            if res:
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

        logging.debug(f'search filepath [{context}] [{partial}]: {body}')

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
                    # another modules dir flattening mitigation
                    if len(mmatch) == 2:
                        if MODULES_FLATTEN_MAP.get(mmatch[1]['repo_filename'], '') == mmatch[0]['repo_filename']:
                            return [mmatch[0]['repo_filename']]

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

                if fn.endswith((body, body + '.py', body + '.ps1')):
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
                    if len(m) < len(match) and match.startswith(m):
                        tr.append(m)

            for r in tr:
                if r in matches:
                    logging.debug(f'trimming {r}')
                    matches.remove(r)

        matches = sorted(set(matches))
        logging.debug(f'return: {matches}')

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

    def _filenames_to_keys(self, filenames):
        '''Match filenames to the keys in botmeta'''
        ckeys = set()
        for filen in filenames:
            if filen in self.botmeta['files']:
                ckeys.add(filen)
            for key in self.botmeta['files'].keys():
                if filen.startswith(key):
                    ckeys.add(key)
        return list(ckeys)

    def get_labels_for_files(self, files):
        labels = []
        for fn in files:
            for label in self.get_meta_for_file(fn).get('labels', []):
                if label not in ['ansible', 'lib'] and label not in labels:
                    labels.append(label)
        return labels

    def get_meta_for_file(self, filename):
        meta = {
            'collection': None,
            'collection_scm': None,
            'repo_filename': filename,
            'repo_link': None,
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
            'supershipit': [],
            'namespace': None,
            'namespace_maintainers': [],
            'metadata': {},
            'migrated_to': None,
            'keywords': [],
        }

        if self.gitrepo.exists(filename):
            meta['repo_link'] = '%s/blob/devel/%s' % (self.gitrepo.repo, filename)

        if filename.startswith('collection:'):
            fqcn = filename.split(':')[1]
            manifest = self.GALAXY_MANIFESTS.get(fqcn)
            if manifest:
                manifest = manifest['manifest']['collection_info']
            meta['collection'] = fqcn
            meta['migrated_to'] = fqcn
            meta['support'] = 'community'
            manifest = self.GALAXY_MANIFESTS.get(fqcn)
            if manifest:
                manifest = manifest['manifest']['collection_info']
                if manifest.get('repository'):
                    meta['collection_scm'] = manifest['repository']
                elif manifest.get('issues'):
                    meta['collection_scm'] = manifest['issues']
            return meta

        filenames = [filename, os.path.splitext(filename)[0]]

        # powershell meta is in the python file
        if filename.endswith('.ps1'):
            pyfile = filename.replace('.ps1', '.py')
            if pyfile in self.botmeta['files']:
                filenames.append(pyfile)

        botmeta_entries = self._filenames_to_keys(filenames)
        for bme in botmeta_entries:
            logging.debug('matched botmeta entry: %s' % bme)

        # Modules contain metadata in docstrings and that should
        # be factored in ...
        #   https://github.com/ansible/ansibullbot/issues/1042
        #   https://github.com/ansible/ansibullbot/issues/1053
        if 'lib/ansible/modules' in filename:
            mmatch = self.find_module_match(filename)
            if mmatch and len(mmatch) == 1 and mmatch[0]['filename'] == filename:
                for k in 'authors', 'maintainers':
                    meta[k] += mmatch[0][k]
                meta['notify'] += mmatch[0]['notified']

        # reconcile the delta between a child and it's parents
        support_levels = {}

        for entry in botmeta_entries:
            fdata = self.botmeta['files'][entry].copy()

            if 'authors' in fdata:
                meta['notify'] += fdata['authors']
                meta['authors'] += fdata['authors']
            if 'maintainers' in fdata:
                meta['notify'] += fdata['maintainers']
                meta['assign'] += fdata['maintainers']
                meta['maintainers'] += fdata['maintainers']
            if 'notified' in fdata:
                meta['notify'] += fdata['notified']
            if 'labels' in fdata:
                meta['labels'] += fdata['labels']
            if 'ignore' in fdata:
                meta['ignore'] += fdata['ignore']
            if 'ignored' in fdata:
                meta['ignore'] += fdata['ignored']
            if 'migrated_to' in fdata and meta['migrated_to'] is None:
                meta['migrated_to'] = fdata['migrated_to']
            if 'keywords' in fdata:
                meta['keywords'] += fdata['keywords']

            if 'support' in fdata:
                if isinstance(fdata['support'], list):
                    support_levels[entry] = fdata['support'][0]
                else:
                    support_levels[entry] = fdata['support']
            elif 'supported_by' in fdata:
                if isinstance(fdata['supported_by'], list):
                    support_levels[entry] = fdata['supported_by'][0]
                else:
                    support_levels[entry] = fdata['supported_by']

            # only "deprecate" exact matches
            if 'deprecated' in fdata and entry == filename:
                meta['deprecated'] = fdata['deprecated']

        # walk up the tree for more meta
        paths = filename.split('/')
        for idx, x in enumerate(paths):
            thispath = '/'.join(paths[:(0-idx)])
            if thispath in self.botmeta['files']:
                fdata = self.botmeta['files'][thispath].copy()
                if 'support' in fdata:
                    if isinstance(fdata['support'], list):
                        support_levels[thispath] = fdata['support'][0]
                    else:
                        support_levels[thispath] = fdata['support']
                elif 'supported_by' in fdata:
                    if isinstance(fdata['supported_by'], list):
                        support_levels[thispath] = fdata['supported_by'][0]
                    else:
                        support_levels[thispath] = fdata['supported_by']
                if 'labels' in fdata:
                    meta['labels'] += fdata['labels']
                if 'maintainers' in fdata:
                    meta['notify'] += fdata['maintainers']
                    meta['assign'] += fdata['maintainers']
                    meta['maintainers'] += fdata['maintainers']
                if 'ignore' in fdata:
                    meta['ignore'] += fdata['ignore']
                if 'notified' in fdata:
                    meta['notify'] += fdata['notified']

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
            keys = self.botmeta['files'].keys()
            keys = [x for x in keys if x.startswith(os.path.join('lib/ansible/modules', ns))]
            ignored = []

            for key in keys:
                meta['namespace_maintainers'] += self.botmeta['files'][key].get('maintainers', [])
                ignored += self.botmeta['files'][key].get('ignored', [])

            for ignoree in ignored:
                while ignoree in meta['namespace_maintainers']:
                    meta['namespace_maintainers'].remove(ignoree)

        # reconcile support levels
        if filename in support_levels:
            # exact match
            meta['support'] = support_levels[filename]
            meta['supported_by'] = support_levels[filename]
            logging.debug('%s support == %s' % (filename, meta['supported_by']))
        else:
            # pick the closest match
            keys = support_levels.keys()
            keys = sorted(keys, key=len, reverse=True)
            if keys:
                meta['support'] = support_levels[keys[0]]
                meta['supported_by'] = support_levels[keys[0]]
                logging.debug('%s support == %s' % (keys[0], meta['supported_by']))

        '''
        # new modules should default to "community" support
        if filename.startswith(u'lib/ansible/modules') and filename not in self.gitrepo.files and not meta.get('migrated_to'):
            meta[u'support'] = u'community'
            meta[u'supported_by'] = u'community'
        '''

        # test targets for modules should inherit from their modules
        if filename.startswith('test/integration/targets') and filename not in self.botmeta['files']:
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
                #import epdb; epdb.st()
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

        def get_prefix_paths(repo_filename, files):
            """Emit all prefix paths matching the given file list."""
            if not repo_filename:
                return

            prefix_paths = make_prefixes(repo_filename)

            for prefix_path in prefix_paths:
                if prefix_path in files:
                    logging.debug(f'found botmeta prefix: {prefix_path}')
                    yield prefix_path

        # walk up the botmeta tree looking for meta to include
        for this_prefix in get_prefix_paths(
            meta.get('repo_filename'), self.botmeta['files'],
        ):

            this_ignore = (
                self.botmeta['files'][this_prefix].get('ignore') or
                self.botmeta['files'][this_prefix].get('ignored') or
                self.botmeta['files'][this_prefix].get('ignores') or
                []
            )

            for username in this_ignore:
                if username not in meta['ignore']:
                    logging.info(f'ignored: {this_ignore}')
                    meta['ignore'].append(username)
                if username in meta['notify']:
                    logging.info('remove %s notify by %s rule' % \
                        (username, this_prefix))
                    meta['notify'].remove(username)
                if username in meta['assign']:
                    logging.info('remove %s assignment by %s rule' % \
                        (username, this_prefix))
                    meta['assign'].remove(username)
                if username in meta['maintainers']:
                    logging.info('remove %s maintainer by %s rule' % \
                        (username, this_prefix))
                    meta['maintainers'].remove(username)

            this_supershipit = self.botmeta['files'][this_prefix].get(
                'supershipit', [],
            )

            for username in this_supershipit:
                if username not in meta['supershipit']:
                    logging.info(f'supershipiteer: {this_prefix}')
                    meta['supershipit'].append(username)

        return meta

    def find_module_match(self, pattern, exact=False):
        '''Exact module name matching'''

        logging.debug(f'find_module_match for "{pattern}"')
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
                    if mf.endswith((pattern, ppy, ps1)):
                        candidate = mf
                        break

        return candidate

    def _find_module_match(self, pattern, exact=False):

        logging.debug(f'matching on {pattern}')

        matches = []

        if isinstance(pattern, str):
            pattern = to_text(to_bytes(pattern, 'ascii', 'ignore'), 'ascii')

        logging.debug(f'_find_module_match: {pattern}')

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
                    logging.debug(f'match {k} on key: {k}')
                    matches = [v]
                    break

        # spellcheck
        if not exact and not matches and '/' not in pattern:
            _pattern = pattern
            if not isinstance(_pattern, str):
                _pattern = to_text(_pattern)
            candidates = []
            for k, v in self.MODULES.items():
                vname = v['name']
                if not isinstance(vname, str):
                    vname = to_text(vname)
                jw = jaro_winkler(vname, _pattern)
                if jw > .9:
                    candidates.append((jw, k))
            for candidate in candidates:
                matches.append(self.MODULES[candidate[1]])

        return matches
