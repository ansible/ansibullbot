#!/usr/bin/env python

import logging
import os
import re

from pprint import pprint


class ComponentMatcher(object):

    STOPWORDS = ['ansible', 'core', 'plugin']
    STOPCHARS = ['"', "'", '(', ')', '?', '*', '`', ',']
    BLACKLIST = ['new module', 'new modules']
    MODULE_NAMES = []

    # FIXME: THESE NEED TO GO INTO BOTMETA
    # ALSO SEE search_by_regex_generic ...
    KEYWORDS = {
        'ansiballz': 'lib/ansible/executor/module_common.py',
        'ansible-galaxy': 'lib/ansible/galaxy',
        'ansible-playbook': 'lib/ansible/playbook',
        'ansible playbook': 'lib/ansible/playbook',
        'ansible playbooks': 'lib/ansible/playbook',
        'ansible-pull': 'lib/ansible/cli/pull.py',
        'ansible-vault': 'lib/ansible/parsing/vault',
        'become': 'lib/ansible/playbook/become.py',
        'block': 'lib/ansible/playbook/block.py',
        'callback plugin': 'lib/ansible/plugins/callback',
        'callback plugins': 'lib/ansible/plugins/callback',
        'handlers': 'lib/ansible/playbook/handler.py',
        'hostvars': 'lib/ansible/vars/hostvars.py',
        'jinja2 template system': 'lib/ansible/template',
        'module_utils': 'lib/ansible/module_utils',
        'new module(s) request': None,
        'new modules request': None,
        'new module request': None,
        'new module': None,
        #'playbook role': 'lib/ansible/playbook/role',
        #'playbook roles': 'lib/ansible/playbook/role',
        'role': 'lib/ansible/playbook/role',
        'roles': 'lib/ansible/playbook/role',
        'setup / facts': 'lib/ansible/modules/system/setup.py',
        'vault': 'lib/ansible/parsing/vault',
        'vault edit': 'lib/ansible/parsing/vault',
        'vault documentation': 'lib/ansible/parsing/vault',
    }

    def __init__(self, cachedir=None, file_indexer=None, module_indexer=None):
        self.cachedir = cachedir
        self.file_indexer = file_indexer
        self.module_indexer = module_indexer
        self.MODULE_NAMES = [x['name'] for x in self.module_indexer.modules.values()]
        #import epdb; epdb.st()

        self.cache_keywords()
        self.strategy = None

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
                self.KEYWORDS[vname] = v['repo_filename']

        for k,v in self.file_indexer.CMAP.items():
            if k not in self.KEYWORDS:
                self.KEYWORDS[k] = v

        for kw in self.BLACKLIST:
            self.KEYWORDS[kw] = None

    def match_components(self, title, body, component):
        """Make a list of matching files with metadata"""

        self.strategy = None
        component = component.encode('ascii', 'ignore')
        logging.debug('match "{}"'.format(component))

        matched_filenames = []

        #if '\n' in component:
        #    components = component.split('\n')
        #    for _component in components:
        #        matched_filenames += self.match_components(title, body, _component)


        if component not in self.STOPWORDS:

            if not matched_filenames:
                matched_filenames += self.search_by_module_name(component)
                if matched_filenames:
                    self.strategy = 'search_by_module_name'

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
                matched_filenames += self.search_by_filepath(component)
                if matched_filenames:
                    self.strategy = 'search_by_filepath'
                if not matched_filenames:
                    matched_filenames += self.search_by_filepath(component, partial=True)
                    if matched_filenames:
                        self.strategy = 'search_by_filepath[partial]'

            if matched_filenames:
                matched_filenames += self.include_modules_from_test_targets(matched_filenames)

            if not matched_filenames:
                matched_filenames += self.search_by_keywords(component)

            if matched_filenames:
                matched_filenames += self.include_modules_from_test_targets(matched_filenames)

        # reduce subpaths
        if matched_filenames:
            matched_filenames = self.reduce_filepaths(matched_filenames)

        # bypass for blacklist
        if None in matched_filenames:
            return []

        component_matches = []
        matched_filenames = sorted(set(matched_filenames))
        for fn in matched_filenames:
            component_matches.append(self.get_meta_for_file(fn))

        return component_matches

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

    def search_by_keywords(self, component):
        """Simple keyword search"""

        component = component.lower()
        matches = []
        if component in self.STOPWORDS:
            matches = [None]
        elif component in self.KEYWORDS:
            matches = [self.KEYWORDS[component]]
        else:
            for k,v in self.KEYWORDS.items():
                if ' ' + k + ' ' in component:
                    logging.debug('keyword match: {}'.format(k))
                    matches.append(v)
                elif ' ' + k + ':' in component:
                    logging.debug('keyword match: {}'.format(k))
                    matches.append(v)
                elif component.endswith(' ' + k):
                    logging.debug('keyword match: {}'.format(k))
                    matches.append(v)

                #elif k + ' module' in component:
                #    logging.debug('keyword match: {}'.format(k))
                #    matches.append(v)

                elif k in component and k in self.BLACKLIST:
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
                    choices = [x for x in self.file_indexer.files if '/' + fn in x]
                    choices = [x for x in choices if 'lib/ansible/modules' in x]

                    if len(choices) > 1:
                        #choices = [x for x in choices if fn + '.py' in x or fn + '.ps1' in x]
                        choices = [x for x in choices if fn + '.py' in x or fn + '.ps1' in x]

                    if not choices:
                        pass
                    elif len(choices) == 1:
                        matches.append(choices[0])
                    else:
                        #import epdb; epdb.st()
                        pass
                else:
                    pass

        return matches

    def search_by_regex_modules(self, body):
        # foo module
        # foo and bar modules
        # foo* modules
        # foo* module

        # https://www.tutorialspoint.com/python/python_reg_expressions.htm
        patterns = [
            r'new (.*) module',
            r'(.*) module',
            r'\`(.*)\` module',
            r'(.*)\* modules',
            r'(.*) and (.*) modules',
            r'(.*)_module',
            r'action: (.*)',
        ]

        matches = []

        for pattern in patterns:
            logging.debug('test pattern: {}'.format(pattern))
            mobj = re.match(pattern, body, re.M | re.I)
            if mobj:
                for x in range(0,3):
                    try:
                        mname = mobj.group(x)
                        mname = mname.strip().lower()
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

        #if body == 'user module':
        #if body == 'lineinfile module':
        #if body == 'service  module':
        #    import epdb; epdb.st()

        #if ' and ' in body and 'module' in body:
        #    import epdb; epdb.st()

        return matches

    def search_by_regex_generic(self, body):
        # foo dynamic inventory script
        # foo filter

        # https://www.tutorialspoint.com/python/python_reg_expressions.htm
        patterns = [
            [r'(.*) action plugin', 'lib/ansible/plugins/action'],
            [r'(.*) dynamic inventory script', 'contrib/inventory'],
            [r'(.*) inventory script', 'contrib/inventory'],
            [r'(.*) filter', 'lib/ansible/plugins/filter'],
            [r'(.*) fact caching plugin', 'lib/ansible/plugins/cache'],
            [r'(.*) lookup plugin', 'lib/ansible/plugins/lookup'],
            [r'(.*) lookup', 'lib/ansible/plugins/lookup'],
            [r'(.*) callback plugin', 'lib/ansible/plugins/callback'],
            [r'callback plugin (.*)', 'lib/ansible/plugins/callback'],
            [r'(.*) connection plugin', 'lib/ansible/plugins/connection'],
            [r'(.*) connection type', 'lib/ansible/plugins/connection'],
            [r'(.*) connection', 'lib/ansible/plugins/connection'],
            [r'connection (.*)', 'lib/ansible/plugins/connection'],
            [r'(.*) strategy plugin', 'lib/ansible/plugins/strategy'],
            [r'(.*) module util', 'lib/ansible/module_utils'],
            [r'ansible-galaxy (.*)', 'lib/ansible/galaxy'],
            [r'ansible-playbook (.*)', 'lib/ansible/playbook'],
        ]

        matches = []

        for pattern in patterns:
            logging.debug('test pattern: {}'.format(pattern))
            mobj = re.match(pattern[0], body, re.M | re.I)
            if mobj:
                fname = mobj.group(1)
                if not fname.endswith('.py'):
                    fpath = os.path.join(pattern[1], fname + '.py')
                else:
                    fpath = os.path.join(pattern[1], fname)
                if fpath in self.file_indexer.files:
                    matches.append(fpath)
                else:
                    # fallback to the directory
                    matches.append(pattern[1])

        #if 'module_utils/ec2.py' in body:
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

    def search_by_filepath(self, body, partial=False):
        """Find known filepaths in body"""
        matches = []

        _body = body[:]
        if '/' not in body and '.' not in body:
            return matches

        if 'modules/core/' in body:
            body = body.replace('modules/core/', 'modules/')
        if 'modules/extras/' in body:
            body = body.replace('modules/extras/', 'modules/')

        body_paths = body.split('/')
        if not body_paths[-1].endswith('.py') and not body_paths[-1].endswith('.ps1'):
            body_paths[-1] = body_paths[-1] + '.py'

        for fn in self.file_indexer.files:

            # narrow the context if possible
            if 'module' in body and 'module' not in fn:
                continue

            if fn in body or fn.endswith(body):
                matches.append(fn)

            if partial:

                # if all subpaths are in this filepath, it is a match
                bp_total = 0
                fn_paths = fn.split('/')
                for bp in body_paths:
                    if bp in fn_paths:
                        bp_total += 1
                if bp_total == len(body_paths):
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
                    matches.remove(r)


        #if _body == 'modules/core/system/setup.py':
        #    import epdb; epdb.st()

        return matches

    def reduce_filepaths(self, matches):
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
