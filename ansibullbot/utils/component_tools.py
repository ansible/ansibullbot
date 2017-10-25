#!/usr/bin/env python

import logging
import os
import re

from pprint import pprint


class ComponentMatcher(object):

    STOPWORDS = ['ansible', 'core', 'plugin']
    STOPCHARS = ['"', "'", '(', ')', '?', '*', '`', ',', ':', '?', '-']
    BLACKLIST = ['new module', 'new modules']
    FILE_NAMES = []
    MODULE_NAMES = []
    MODULE_NAMESPACE_DIRECTORIES = []

    # FIXME: THESE NEED TO GO INTO BOTMETA
    # ALSO SEE search_by_regex_generic ...
    KEYWORDS = {
        'ansiballz': 'lib/ansible/executor/module_common.py',
        'ansible-console': 'lib/ansible/cli/console.py',
        'ansible-galaxy': 'lib/ansible/galaxy',
        'ansible-playbook': 'lib/ansible/playbook',
        'ansible playbook': 'lib/ansible/playbook',
        'ansible playbooks': 'lib/ansible/playbook',
        'ansible-pull': 'lib/ansible/cli/pull.py',
        'ansible-vault': 'lib/ansible/parsing/vault',
        'ansible-vault edit': 'lib/ansible/parsing/vault',
        'ansible-vault show': 'lib/ansible/parsing/vault',
        'ansible-vault decrypt': 'lib/ansible/parsing/vault',
        'ansible-vault encrypt': 'lib/ansible/parsing/vault',
        'become': 'lib/ansible/playbook/become.py',
        'block': 'lib/ansible/playbook/block.py',
        'blocks': 'lib/ansible/playbook/block.py',
        'callback plugin': 'lib/ansible/plugins/callback',
        'callback plugins': 'lib/ansible/plugins/callback',
        'conditional': 'lib/ansible/playbook/conditional.py',
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
        #'playbook role': 'lib/ansible/playbook/role',
        #'playbook roles': 'lib/ansible/playbook/role',
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
    }

    def __init__(self, cachedir=None, file_indexer=None, module_indexer=None):
        self.cachedir = cachedir
        self.file_indexer = file_indexer
        self.FILE_NAMES = sorted(self.file_indexer.files)
        self.module_indexer = module_indexer
        self.MODULE_NAMES = [x['name'] for x in self.module_indexer.modules.values()]

        self.MODULE_NAMESPACE_DIRECTORIES = [os.path.dirname(x) for x in self.FILE_NAMES if x.startswith('lib/ansible/modules/')]
        self.MODULE_NAMESPACE_DIRECTORIES = sorted(set(self.MODULE_NAMESPACE_DIRECTORIES))

        self.cache_keywords()
        self.strategy = None
        self.strategies = []

    def cache_keywords(self):
        """Make a map of keywords and module names"""
        for k,v in self.file_indexer.botmeta['files'].items():
            if not v.get('keywords'):
                continue
            for kw in v['keywords']:
                if kw not in self.KEYWORDS:
                    self.KEYWORDS[kw] = k

        for k,v in self.module_indexer.modules.items():
            if not v.get('name'):
                continue
            if v['name'] not in self.KEYWORDS:
                self.KEYWORDS[v['name']] = v['repo_filename']
            if v['name'].startswith('_'):
                vname = v['name'].replace('_', '', 1)
                if vname not in self.KEYWORDS:
                    self.KEYWORDS[vname] = v['repo_filename']

        for k,v in self.file_indexer.CMAP.items():
            if k not in self.KEYWORDS:
                self.KEYWORDS[k] = v

        for kw in self.BLACKLIST:
            self.KEYWORDS[kw] = None

    def match_components(self, title, body, component):
        """Make a list of matching files with metadata"""

        self.strategy = None
        self.strategies = []

        component = component.encode('ascii', 'ignore')
        logging.debug('match "{}"'.format(component))

        matched_filenames = []

        delimiters = ['\n', ',', ' + ', ' & ', ': ']
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

        '''
        # bypass for blacklist
        if None in matched_filenames:
            return []
        '''

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

        component = component.strip()
        for SC in self.STOPCHARS:
            if component.startswith(SC):
                component = component.lstrip(SC)
                component = component.strip()
            if component.endswith(SC):
                component = component.rstrip(SC)
                component = component.strip()

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

    def search_by_fileindexer(self, title, body, component):
        """Use the fileindexers component matching algo"""
        matches = []
        template_data = {'component name': component, 'component_raw': component}
        ckeys = self.file_indexer.find_component_match(title, body, template_data)
        if ckeys:
            components = self.file_indexer.find_component_matches_by_file(ckeys)
            import epdb; epdb.st()
        return matches

    def search_by_module_name(self, component):
        matches = []

        _component = component

        for SC in self.STOPCHARS:
            component = component.replace(SC, '')
        component = component.strip()

        # docker-container vs. docker_container
        if component not in self.MODULE_NAMES:
            component = component.replace('-', '_')

        if component in self.MODULE_NAMES:
            mmatch = self.module_indexer.find_match(component, exact=True)
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
            for k,v in self.KEYWORDS.items():
                if ' ' + k + ' ' in component or ' ' + k + ' ' in component.lower():
                    logging.debug('keyword match: {}'.format(k))
                    matches.append(v)
                elif ' ' + k + ':' in component or ' ' + k + ':' in component:
                    logging.debug('keyword match: {}'.format(k))
                    matches.append(v)
                elif component.endswith(' ' + k) or component.lower().endswith(' ' + k):
                    logging.debug('keyword match: {}'.format(k))
                    matches.append(v)

                #elif k + ' module' in component:
                #    logging.debug('keyword match: {}'.format(k))
                #    matches.append(v)

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
                    choices = [x for x in self.file_indexer.files if '/' + fn in x or '/_' + fn in x]
                    choices = [x for x in choices if 'lib/ansible/modules' in x]

                    if len(choices) > 1:
                        #choices = [x for x in choices if fn + '.py' in x or fn + '.ps1' in x]
                        choices = [x for x in choices if '/' + fn + '.py' in x or '/' + fn + '.ps1' in x or '/_' + fn + '.py' in x]

                    if not choices:
                        pass
                    elif len(choices) == 1:
                        matches.append(choices[0])
                    else:
                        #import epdb; epdb.st()
                        pass
                else:
                    pass

        #if 's3_module' in body and not matches:
        #    import epdb; epdb.st()

        return matches

    def search_by_regex_modules(self, body):
        # foo module
        # foo and bar modules
        # foo* modules
        # foo* module

        _body = body
        body = body.lower()
        for SC in self.STOPCHARS:
            if SC in body:
                body = body.replace(SC, '')
        body = body.strip()

        # https://www.tutorialspoint.com/python/python_reg_expressions.htm
        patterns = [
            r'(.*)-module',
            r'modules/(.*)',
            r'module\: (.*)',
            r'module (.*)',
            r'new (.*) module',
            r'the (.*) module',
            r'(.*) module',
            r'(.*) core module',
            r'(.*) extras module',
            r'\`(.*)\` module',
            r'(.*)\* modules',
            r'(.*) and (.*)',
            r'(.*) or (.*)',
            r'(.*) \+ (.*)',
            r'(.*) \& (.*)',
            r'(.*) and (.*) modules',
            r'(.*) or (.*) module',
            r'(.*)_module',
            r'action: (.*)',
            r'action (.*)',
            r'ansible_module_(.*)\.py',
            r'(.*) task',
        ]

        matches = []

        logging.debug('check patterns against: {}'.format(body))

        for pattern in patterns:
            logging.debug('test pattern: {}'.format(pattern))
            mobj = re.match(pattern, body, re.M | re.I)
            if mobj:
                for x in range(0,3):
                    try:
                        mname = mobj.group(x)
                        if mname == body:
                            continue
                        mname = mname.strip().lower()
                        mname = mname.replace('.py', '').replace('.ps1', '')

                        module = None
                        if mname in self.MODULE_NAMES:
                            module = self.module_indexer.find_match(mname, exact=True)

                        if not module:
                            pass
                        elif isinstance(module, list):
                            for m in module:
                                #logging.debug('matched {}'.format(m['name']))
                                matches.append(m['repo_filename'])
                        elif isinstance(module, dict):
                            #logging.debug('matched {}'.format(module['name']))
                            matches.append(module['repo_filename'])
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
        body = body.lower()

        #print('')
        #print('BODY: {}'.format(body))

        keymap = {
            'ec2': 'lib/ansible/modules/cloud/amazon',
            'ec2_*': 'lib/ansible/modules/cloud/amazon',
            'aws': 'lib/ansible/modules/cloud/amazon',
            'amazon': 'lib/ansible/modules/cloud/amazon',
            'google': 'lib/ansible/modules/cloud/google',
            'gce': 'lib/ansible/modules/cloud/google',
            'bigip': 'lib/ansible/modules/network/f5',
            'nxos': 'lib/ansible/modules/network/nxos',
            'azure': 'lib/ansible/modules/cloud/azure',
            'azurerm': 'lib/ansible/modules/cloud/azure',
            'openstack': 'lib/ansible/modules/cloud/openstack',
        }

        regexes = [
            r'all (\S+) based modules',
            r'all (\S+) modules',
            r'(\S+) modules',
            r'(\S+\*) modules'
        ]

        mobj = None
        for x in regexes:
            mobj = re.match(x, body)
            if mobj:
                break

        if mobj:
            keyword = mobj.group(1)
            if keyword in keymap:
                matches.append(keymap[keyword])
            else:

                if '*' in keyword:
                    print(keyword)
                    import epdb; epdb.st()

                # check for directories first
                fns = [x for x in self.MODULE_NAMESPACE_DIRECTORIES if keyword in x]

                # check for files second
                if not fns:
                    fns = [x for x in self.FILE_NAMES if 'lib/ansible/modules' in x and keyword in x]

                if fns:
                    matches += fns

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
        ]

        _body = body
        for SC in self.STOPCHARS:
            if SC in body:
                body = body.replace(SC, '')
        body = body.strip()

        matches = []

        for pattern in patterns:
            #logging.debug('test pattern: {}'.format(pattern))
            mobj = re.match(pattern[0], body, re.M | re.I)

            if mobj:
                logging.debug('pattern hit: {}'.format(pattern))
                fname = mobj.group(1)
                fname = fname.lower()

                '''
                if not fname.endswith('.py'):
                    fpath = os.path.join(pattern[1], fname + '.py')
                else:
                    fpath = os.path.join(pattern[1], fname)
                '''
                fpath = os.path.join(pattern[1], fname)

                if fpath in self.file_indexer.files:
                    matches.append(fpath)
                elif os.path.join(pattern[1], fname + '.py') in self.file_indexer.files:
                    fname = os.path.join(pattern[1], fname + '.py')
                    matches.append(fname)
                else:
                    # fallback to the directory
                    matches.append(pattern[1])

        #if 'module_utils/ec2.py' in body:
        #    import epdb; epdb.st()

        #if body == 'lib/ansible/module_utils/facts':
        #    import epdb; epdb.st()

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

        #if '/' not in body and '.' not in body:
        #    return matches

        body = body.strip()
        for SC in self.STOPCHARS:
            if body.startswith(SC):
                body = body.lstrip(SC)
                body = body.strip()
            if body.endswith(SC):
                body = body.rstrip(SC)
                body = body.strip()

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

        #print('FINAL BODY: {}'.format(body))

        body_paths = body.split('/')
        #if not body_paths[-1].endswith('.py') and not body_paths[-1].endswith('.ps1'):
        #    body_paths[-1] = body_paths[-1] + '.py'

        if body in self.file_indexer.files:
            matches = [body]
        else:
            for fn in self.FILE_NAMES:

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

                    # if all subpaths are in this filepath, it is a match
                    bp_total = 0
                    fn_paths = fn.split('/')
                    for bp in body_paths:
                        if bp in fn_paths:
                            bp_total += 1
                    if bp_total == len(body_paths):
                        if fn not in matches:
                            matches.append(fn)
                    #elif bp_total > 3:
                    #    print('{}/{} match on {}'.format(bp_total, len(body_paths), fn))
                    #    print(body_paths)
                    #    if 'rhn_register' in fn:
                    #        import epdb; epdb.st()

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
                    matches.remove(r)

        matches = sorted(set(matches))
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
                mrs = self.module_indexer.find_match(mname, exact=True)
                if mrs:
                    if not isinstance(mrs, list):
                        mrs = [mrs]
                    for mr in mrs:
                        new_matches.append(mr['repo_filename'])
                #import epdb; epdb.st()
        return new_matches

    def get_meta_for_file(self, filename):
        """Compile metadata for a matched filename"""

        meta = {
            'repo_filename': filename
        }

        meta['labels'] = self.file_indexer.get_filemap_labels_for_files([filename])
        (to_notify, to_assign) = self.file_indexer.get_filemap_users_for_files([filename])
        meta['notify'] = to_notify
        meta['assign'] = to_assign

        if 'lib/ansible/modules' in filename:
            mmeta = self.module_indexer.find_match(filename, exact=True)
            if not mmeta:
                pass
            elif mmeta and len(mmeta) == 1:
                meta.update(mmeta[0])
            else:
                import epdb; epdb.st()

        #import epdb; epdb.st()
        return meta
