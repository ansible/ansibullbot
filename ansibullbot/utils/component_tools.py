#!/usr/bin/env python

import logging
import os
import re

from pprint import pprint

STOPWORDS = ['ansible', 'core', 'plugin']
STOPCHARS = ['"', "'", '(', ')', '?', '*', '`', ',']
BLACKLIST = STOPWORDS + ['new module', 'new modules']


class ComponentMatcher(object):

    KEYWORDS = {}

    def __init__(self, cachedir=None, file_indexer=None, module_indexer=None):
        self.cachedir = cachedir
        self.file_indexer = file_indexer
        self.module_indexer = module_indexer

        self.cache_keywords()

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

        for kw in BLACKLIST:
            self.KEYWORDS[kw] = None

    def match_components(self, title, body, component):
        """Make a list of matching files with metadata"""

        component = component.encode('ascii', 'ignore')
        logging.debug('match "{}"'.format(component))

        matched_filenames = []

        if component:
            matched_filenames += self.search_by_keywords(component)

        if not matched_filenames:
            matched_filenames += self.search_by_regex_urls(component)

        if not matched_filenames:
            matched_filenames += self.search_by_tracebacks(component)

        if not matched_filenames:
            matched_filenames += self.search_by_filepath(component)
            if not matched_filenames:
                matched_filenames += self.search_by_filepath(component, partial=True)

        if matched_filenames:
            matched_filenames += self.include_modules_from_test_targets(matched_filenames)

        # bypass for blacklist
        if None in matched_filenames:
            return []

        component_matches = []
        matched_filenames = sorted(set(matched_filenames))
        for fn in matched_filenames:
            component_matches.append(self.get_meta_for_file(fn))

        return component_matches

    def search_by_keywords(self, component):
        """Simple keyword search"""
        component = component.lower()
        matches = []
        if component in self.KEYWORDS:
            matches = [self.KEYWORDS[component]]
        else:
            for k,v in self.KEYWORDS.items():
                if ' ' + k + ' ' in component:
                    matches.append(v)
                elif ' ' + k + ':' in component:
                    matches.append(v)
                elif component.endswith(' ' + k):
                    matches.append(v)
                elif k + ' module' in component:
                    matches.append(v)

                elif k in component and k in BLACKLIST:
                    matches.append(None)

        return matches

    def search_by_regex_urls(self, body):
        # http://docs.ansible.com/ansible/latest/copy_module.html
        # http://docs.ansible.com/ansible/latest/dev_guide/developing_modules.html
        # http://docs.ansible.com/ansible/latest/postgresql_db_module.html
        # [helm module](https//docs.ansible.com/ansible/2.4/helm_module.html)
        # Windows module: win_robocopy\nhttp://docs.ansible.com/ansible/latest/win_robocopy_module.html
        # Examples:\n* archive (https://docs.ansible.com/ansible/archive_module.html)\n* s3_sync (https://docs.ansible.com/ansible/s3_sync_module.html)

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
                        choices = [x for x in choices if fn + '.py' in x]

                    if len(choices) == 1:
                        matches.append(choices[0])
                    else:
                        import epdb; epdb.st()
                else:
                    pass

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
                    for SC in STOPCHARS:
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

        if matches:
            import epdb; epdb.st()
        return matches

    def search_by_filepath(self, body, partial=False):
        """Find known filepaths in body"""
        matches = []
        body_paths = body.split('/')
        if not body_paths[-1].endswith('.py') and not body_paths[-1].endswith('.ps1'):
            body_paths[-1] = body_paths[-1] + '.py'

        for fn in self.file_indexer.files:

            if fn in body:
                matches.append(fn)

            if partial:

                '''
                for word in body.split():
                    if word in fn:
                        matches.append(fn)

                    if word == 'cloud/docker_container' and 'docker_container' in fn:
                        print(fn)
                        import epdb; epdb.st()
                '''

                # if all subpaths are in this filepath, it is a match
                bp_total = 0
                fn_paths = fn.split('/')
                for bp in body_paths:
                    if bp in fn_paths:
                        bp_total += 1
                if bp_total == len(body_paths):
                    matches.append(fn)

        #if body == 'cloud/docker_container':
        #    import epdb; epdb.st()

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




