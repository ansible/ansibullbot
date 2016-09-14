#!/usr/bin/env python

import yaml
from lib.utils.systemtools import *

class ModuleIndexer(object):

    def __init__(self):
        self.modules = {}
        self.checkoutdir = '/tmp/ansible.modules.checkout'

    def create_checkout(self):
        """checkout ansible"""
        cmd = "git clone http://github.com/ansible/ansible --recursive %s" % self.checkoutdir
        (rc, so, se) = run_command(cmd)
        print str(so) + str(se)

    def update_checkout(self):
        """rebase + pull + update the checkout"""
        cmd = "cd %s ; git pull --rebase" % self.checkoutdir
        (rc, so, se) = run_command(cmd)
        print str(so) + str(se)
        cmd = "cd %s ; git submodule update --recursive" % self.checkoutdir
        (rc, so, se) = run_command(cmd)
        print str(so) + str(se)

    def _find_match(self, pattern, exact=False):

        match = None
        for k,v in self.modules.iteritems():
            if v['name'] == pattern:
                match = v
                break
        if not match:
            # search by key ... aka the filepath
            for k,v in self.modules.iteritems():
                if k == pattern:
                    match = v
                    break
        if not match and not exact:
            # search by properties
            for k,v in self.modules.iteritems():
                for subkey in v.keys():
                    if v[subkey] == pattern:
                        match = v
                        break
                if match:
                    break
        return match

    def find_match(self, pattern, exact=False):
        '''Exact module name matching'''
        if not pattern:
            return None
        match = self._find_match(pattern, exact=exact)
        if not match and not exact:
            # check for just the basename
            #   2617: ansible-s-extras/network/cloudflare_dns.py
            bname = os.path.basename(pattern)
            match = self._find_match(bname)

            if not match:
                # check for deprecated name
                #   _fireball -> fireball
                match = self._find_match('_' + bname)

        return match

    def is_valid(self, mname):
        match = self.find_match(mname)
        if match:
            return True
        else:
            return False

    def get_repository_for_module(self, mname):
        match = self.find_match(mname)
        if match:
            return match['repository']
        else:
            return None

    def get_ansible_modules(self):
        """Make a list of known modules"""

        # manage the checkout
        if not os.path.isdir(self.checkoutdir):
            self.create_checkout()
        else:
            self.update_checkout()

        #(Epdb) pp module
        #u'wait_for'
        #(Epdb) pp self.module_indexer.is_valid(module)
        #False        

        matches = []
        module_dir = os.path.join(self.checkoutdir, 'lib/ansible/modules')
        module_dir = os.path.expanduser(module_dir)
        for root, dirnames, filenames in os.walk(module_dir):
            for filename in filenames:
                if 'lib/ansible/modules' in root \
                    and not filename == '__init__.py' \
                    and (filename.endswith('.py') or filename.endswith('.ps1')):
                    matches.append(os.path.join(root, filename))    

        matches = sorted(set(matches))

        # figure out the names
        for match in matches:
            mdict = {}
            mdict['authors'] = []

            mdict['filename'] = os.path.basename(match)

            dirpath = os.path.dirname(match)
            dirpath = dirpath.replace(self.checkoutdir + '/', '')
            mdict['dirpath'] = dirpath

            filepath = match.replace(self.checkoutdir + '/', '')
            mdict['filepath'] = filepath

            subpath = dirpath.replace('lib/ansible/modules/', '')
            path_parts = subpath.split('/')
            mdict['repository'] = path_parts[0]
            mdict['topic'] = path_parts[1]
            if len(path_parts) > 2:
                mdict['subtopic'] = path_parts[2]
                mdict['fulltopic'] = '/'.join(path_parts[1:3]) + '/'
            else:
                mdict['subtopic'] = None
                mdict['fulltopic'] = path_parts[1] +'/'

            mdict['repo_filename'] = mdict['filepath']\
                .replace('lib/ansible/modules/%s/' % mdict['repository'], '')

            # clustering/consul
            mdict['namespaced_module'] = mdict['repo_filename']
            mdict['namespaced_module'] = mdict['namespaced_module']\
                                            .replace('.py', '')
            mdict['namespaced_module'] = mdict['namespaced_module']\
                                            .replace('.ps1', '')

            mname = os.path.basename(match)
            mname = mname.replace('.py', '')
            mname = mname.replace('.ps1', '')
            mdict['name'] = mname

            # deprecated modules
            if mname.startswith('_'):
                deprecated_filename = \
                    os.path.dirname(mdict['namespaced_module'])
                deprecated_filename = \
                    os.path.join(deprecated_filename, mname[1:] + '.py')
                mdict['deprecated_filename'] = deprecated_filename
            else:
                mdict['deprecated_filename'] = mdict['repo_filename']


            mkey = mdict['filepath']
            self.modules[mkey] = mdict

        # grep the authors:
        for k,v in self.modules.iteritems():
            mfile = os.path.join(self.checkoutdir, v['filepath'])
            authors = self.get_module_authors(mfile)
            self.modules[k]['authors'] = authors

        # meta is a special module
        self.modules['meta'] = {}
        self.modules['meta']['authors'] = []
        self.modules['meta']['name'] = 'meta'
        self.modules['meta']['namespaced_module'] = None
        self.modules['meta']['deprecated_filename'] = None
        self.modules['meta']['dirpath'] = None
        self.modules['meta']['filename'] = None
        self.modules['meta']['filepath'] = None
        self.modules['meta']['fulltopic'] = None
        self.modules['meta']['repo_filename'] = 'meta'
        self.modules['meta']['repository'] = 'core'
        self.modules['meta']['subtopic'] = None
        self.modules['meta']['topic'] = None
        self.modules['meta']['authors'] = []

        # deprecated modules are annoying
        newitems = []
        for k,v in self.modules.iteritems():
            if v['name'].startswith('_'):
                dkey = os.path.dirname(v['filepath'])
                dkey = os.path.join(dkey, v['filename'].replace('_', '', 1))
                if not dkey in self.modules:
                    nd = v.copy()
                    nd['name'] = nd['name'].replace('_', '', 1)
                    newitems.append((dkey, nd))
        for ni in newitems:
            self.modules[ni[0]] = ni[1]

        return self.modules


    def get_module_authors(self, module_file):
        """Grep the authors out of the module docstrings"""

        authors = []
        if not os.path.exists(module_file):
            return authors

        documentation = ''
        inphase = False

        with open(module_file, 'rb') as f:
            for line in f:
                if 'DOCUMENTATION' in line:
                    inphase = True 
                    continue                
                if line.strip().endswith("'''") or line.strip().endswith('"""'):
                    phase = None
                    break 
                if inphase:
                    documentation += line

        if not documentation:
            return authors

        # clean out any other yaml besides author to save time
        inphase = False
        author_lines = ''
        doc_lines = documentation.split('\n')
        for idx,x in enumerate(doc_lines):
            if x.startswith('author'):
                #print("START ON %s" % x)
                inphase = True
                #continue
            if inphase and not x.strip().startswith('-') and not x.strip().startswith('author'):
                #print("BREAK ON %s" % x)
                inphase = False
                break
            if inphase:
                author_lines += x + '\n'

        if not author_lines:
            return authors            

        ydata = {}
        try:
            ydata = yaml.load(author_lines)
        except Exception as e:
            print e
            #import epdb; epdb.st()
            return authors

        if not ydata:
            return authors

        if not 'author' in ydata:
            return authors

        if type(ydata['author']) != list:
            ydata['author'] = [ydata['author']]

        for author in ydata['author']:
            if '@' in author:
                words = author.split()
                for word in words:
                    if '@' in word and '(' in word and ')' in word:
                        if '(' in word:
                            word = word.split('(')[-1]
                        if ')' in word:
                            word = word.split(')')[0]
                        word = word.strip()
                        if word.startswith('@'):
                            word = word.replace('@', '', 1)
                            authors.append(word)
        return authors


    def fuzzy_match(self, repo=None, title=None, component=None):
        '''Fuzzy matching for modules'''

        match = None
        known_modules = []

        for k,v in self.modules.iteritems():
            known_modules.append(v['name'])

        title = title.lower()
        title = title.replace(':', '')
        title_matches = [x for x in known_modules if x + ' module' in title]

        if not title_matches:
            title_matches = [x for x in known_modules if title.startswith(x + ' ')]
            if not title_matches:
                title_matches = [x for x in known_modules if  ' ' + x + ' ' in title]

        # don't do singular word matching in title for ansible/ansible
        cmatches = None
        if component:        
            cmatches = [x for x in known_modules if x in component]
            cmatches = [x for x in cmatches if not '_' + x in component]

            # use title ... ?
            if title_matches:
                cmatches = [x for x in cmatches if x in title_matches]

            if cmatches:
                if len(cmatches) >= 1:
                    match = cmatches[0]
                if not match:
                    if 'docs.ansible.com' in component:
                        pass
                    else:
                        pass
                print("module - component matches: %s" % cmatches)

        if not match:
            if len(title_matches) == 1:
                match = title_matches[0]
            else:
                print("module - title matches: %s" % title_matches)

        #import epdb; epdb.st()
        return match
