#!/usr/bin/env python

import os

from fuzzywuzzy import fuzz as fw_fuzz
from fuzzywuzzy import process as fw_process

from lib.utils.systemtools import run_command
from lib.utils.moduletools import ModuleIndexer


class FileIndexer(ModuleIndexer):

    files = []

    def get_files(self):
        # manage the checkout
        if not os.path.isdir(self.checkoutdir):
            self.create_checkout()
        else:
            self.update_checkout()

        cmd = 'find %s' % self.checkoutdir
        (rc, so, se) = run_command(cmd)
        files = so.split('\n')
        files = [x.strip() for x in files if x.strip()]
        files = [x.replace(self.checkoutdir + '/', '') for x in files]
        files = [x for x in files if not x.startswith('.git')]
        self.files = files

    def get_component_labels(self, valid_labels, files):
        labels = [x for x in valid_labels if x.startswith('c:')]

        clabels = []
        for cl in labels:
            l = cl.replace('c:', '', 1)
            al = os.path.join('lib/ansible', l)
            if al.endswith('/'):
                al = al.rstrip('/')
            for f in files:
                if not f:
                    continue
                if f.startswith(l) or f.startswith(al):
                    clabels.append(cl)

        # use the more specific labels
        clabels = sorted(set(clabels))
        tmp_clabels = [x for x in clabels]
        for cl in clabels:
            for x in tmp_clabels:
                if cl != x and x.startswith(cl):
                    tmp_clabels.remove(cl)
        if tmp_clabels != clabels:
            clabels = [x for x in tmp_clabels]
            clabels = sorted(set(clabels))

        return clabels

    def find_component_match(self, title, body, template_data):

        # DistributionNotFound: The 'jinja2<2.9' distribution was not found and
        #   is required by ansible
        # File
        # "/usr/lib/python2.7/site-packages/ansible/plugins/callback/foreman.py",
        #   line 30, in <module>

        CMAP = {
            'action plugin': [],
            'ansible-console': ['bin/ansible-console'],
            'ansible-doc': ['bin/ansible-doc'],
            'ansible-galaxy': [],
            'ansible-playbook': [],
            'ansible-playbook command': ['bin/ansible-playbook'],
            'ansible-pull': ['bin/ansible-pull'],
            'ansible-vault': ['bin/ansible-vault'],
            'ansible-test': [],
            'ansible command': ['bin/ansible'],
            'ansible console': ['bin/ansible-console'],
            'ansible core': [None],
            'ansible galaxy': [],
            'ansible logging': [],
            'ansible pull': [],
            'async': ['lib/ansible/plugins/action/async.py'],
            'async task': ['lib/ansible/plugins/action/async.py'],
            'asynchronus task': ['lib/ansible/plugins/action/async.py'],
            'block': ['lib/ansible/playbook/block.py'],
            'callback plugin': ['lib/ansible/plugins/callback'],
            'connection plugin': ['lib/ansible/plugins/connection'],
            'connection local': ['lib/ansible/plugins/connection/local.py'],
            'core': [None],
            'core inventory': ['lib/ansible/inventory'],
            'dynamic inventory': ['contrib/inventory'],
            'dynamic inventory script': ['contrib/inventory'],
            'delegate_to': [],
            'facts': ['lib/ansible/module_utils/facts.py'],
            'facts.py': ['lib/ansible/module_utils/facts.py'],
            'gather_facts': ['lib/ansible/module_utils/facts.py'],
            'handlers': ['lib/ansible/playbook/handler.py'],
            'host_vars': ['lib/ansible/vars/hostvars.py'],
            'include_role': ['lib/ansible/playbook/role/include.py'],
            'include role': ['lib/ansible/playbook/role/include.py'],
            'inventory': ['lib/ansible/inventory'],
            'inventory parsing': ['lib/ansible/inventory'],
            'inventory script': ['contrib/inventory'],
            'jinja': ['lib/ansible/template'],
            'jinja2': ['lib/ansible/template'],
            'local connection': ['lib/ansible/plugins/connection/local.py'],
            'n/a': [None],
            'na': [None],
            'openstack dynamic inventory script':
                ['contrib/inventory/openstack.py'],
            'paramiko': ['lib/ansible/plugins/connection/paramiko_ssh.py'],
            'role': ['lib/ansible/playbook/role'],
            'roles_path': ['lib/ansible/playbook/role'],
            'role path': ['lib/ansible/playbook/role'],
            'roles path': ['lib/ansible/playbook/role'],
            'role include': ['lib/ansible/playbook/role/include.py'],
            'role dep': ['lib/ansible/playbook/role/requirement.py'],
            'role dependencies': ['lib/ansible/playbook/role/requirement.py'],
            'role dependency': ['lib/ansible/playbook/role/requirement.py'],
            'runner': [None],
            'ssh connection plugin': ['lib/ansible/plugins/connection/ssh.py'],
            'ssh connection': ['lib/ansible/plugins/connection/ssh.py'],
            'ssh plugin': ['lib/ansible/plugins/connection/ssh.py'],
            'templates': [],
            'with_fileglob': ['lib/ansible/plugins/lookup/fileglob.py'],
            'with_items': ['lib/ansible/plugins/lookup/__init__.py'],
            'validate-modules': ['test/sanity/validate-modules'],
            'vars-prompt': [],
            'vault': ['lib/ansible/parsing/vault'],
            'vault cat': ['lib/ansible/parsing/vault'],
            'vault decrypt': ['lib/ansible/parsing/vault'],
            'vault edit': ['lib/ansible/parsing/vault'],
            'vault encrypt': ['lib/ansible/parsing/vault'],
        }

        STOPWORDS = ['ansible', 'core', 'plugin']
        STOPCHARS = ['"', "'", '(', ')', '?', '*', '`', ',']
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
                            #import epdb; epdb.st()
                            pass
            if matches:
                return matches

        craws = template_data.get('component_raw')

        # compare to component mapping
        rawl = craws.lower()
        if rawl.endswith('.'):
            rawl = rawl.rstrip('.')
        if rawl in CMAP:
            matches += CMAP[rawl]
            return matches
        elif (rawl + 's') in CMAP:
            matches += CMAP[rawl + 's']
            return matches
        elif rawl.rstrip('s') in CMAP:
            matches += CMAP[rawl.rstrip('s')]
            return matches

        # https://pypi.python.org/pypi/fuzzywuzzy
        matches = []
        for cr in craws.lower().split('\n'):
            ratios = []
            for k in CMAP.keys():
                ratio = fw_fuzz.ratio(cr, k)
                ratios.append((ratio, k))
            ratios = sorted(ratios, key=lambda tup: tup[0])
            if ratios[-1][0] >= 90:
                cnames = CMAP[ratios[-1][1]]
                matches += cnames


        #if matches:
        #    import epdb; epdb.st()

        if title == 'includes wrapped in a block statement drop environment variables':
            import epdb; epdb.st()

        # try to match to repo files
        if craws:
            clines = craws.split('\n')
            for craw in clines:
                cparts = craw.replace('-', ' ')
                cparts = cparts.split()

                for idx,x in enumerate(cparts):
                    for SC in STOPCHARS:
                        if SC in x:
                            x = x.replace(SC, '')
                    for SW in STOPWORDS:
                        if x == SW:
                            x = ''
                    if x and '/' not in x:
                        x = '/' + x
                    cparts[idx] = x

                cparts = [x.strip() for x in cparts if x.strip()]

                for x in cparts:
                    for f in self.files:
                        if '/modules/' in f:
                            continue
                        if 'test/' in f and 'test' not in craw:
                            continue
                        if 'galaxy' in f and 'galaxy' not in body:
                            continue
                        if 'dynamic inv' in body.lower() and 'contrib' not in f:
                            continue
                        if 'inventory' in f and 'inventory' not in body.lower():
                            continue
                        if 'contrib' in f and 'inventory' not in body.lower():
                            continue

                        try:
                            f.endswith(x)
                        except UnicodeDecodeError:
                            continue

                        fname = os.path.basename(f).split('.')[0]

                        if f.endswith(x):
                            if fname.lower() in body.lower():
                                matches.append(f)
                                break
                        if f.endswith(x + '.py'):
                            if fname.lower() in body.lower():
                                matches.append(f)
                                break
                        if f.endswith(x + '.ps1'):
                            if fname.lower() in body.lower():
                                matches.append(f)
                                break
                        if os.path.dirname(f).endswith(x):
                            if fname.lower() in body.lower():
                                matches.append(f)
                                break

        print('%s --> %s' % (craws, sorted(set(matches))))
        return matches
