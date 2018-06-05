#!/usr/bin/env python

import copy
import logging
import os
import re

from fuzzywuzzy import fuzz as fw_fuzz
from textblob import TextBlob

from ansibullbot.parsers.botmetadata import BotMetadataParser
from ansibullbot.utils.systemtools import run_command
from ansibullbot.utils.moduletools import ModuleIndexer


class FileIndexer(ModuleIndexer):

    REPO = 'https://github.com/ansible/ansible'

    DEFAULT_COMPONENT_MATCH = {
        'supported_by': 'core',
        'filename': None,
        'labels': [],
        'owners': [],
        'notify': []
    }

    files = []

    def __init__(self, botmetafile=None, checkoutdir=None, repo=None):

        if checkoutdir is None:
            self.checkoutdir = '~/.ansibullbot/cache/ansible.files.checkout'
        else:
            self.checkoutdir = os.path.join(checkoutdir, 'ansible.files.checkout')
        self.checkoutdir = os.path.expanduser(self.checkoutdir)

        if repo:
            self.REPO = 'https://github.com/{}'.format(repo)

        self.botmetafile = botmetafile
        self.botmeta = {}
        self.CMAP = {}
        self.FILEMAP = {}
        self.match_cache = {}
        self.update(force=True)
        self.email_commits = {}

    def parse_metadata(self):

        if self.botmetafile is not None:
            with open(self.botmetafile, 'rb') as f:
                rdata = f.read()
        else:
            fp = '.github/BOTMETA.yml'
            rdata = self.get_file_content(fp)
        if rdata:
            self.botmeta = BotMetadataParser.parse_yaml(rdata)
        else:
            self.botmeta = {}

        # reshape meta into old format
        self.CMAP = {}
        for k,v in self.botmeta.get('files', {}).items():
            if not v:
                continue
            if 'keywords' not in v:
                continue
            for keyword in v['keywords']:
                if keyword not in self.CMAP:
                    self.CMAP[keyword] = []
                if k not in self.CMAP[keyword]:
                    self.CMAP[keyword].append(k)

        # update the data
        self.get_files()
        self.get_filemap()

    def get_files(self):

        cmd = 'find %s' % self.checkoutdir
        (rc, so, se) = run_command(cmd)
        files = so.split('\n')
        files = [x.strip() for x in files if x.strip()]
        files = [x.replace(self.checkoutdir + '/', '') for x in files]
        files = [x for x in files if not x.startswith('.git')]
        self.files = files

    def get_component_labels(self, files, valid_labels=[]):
        '''Matches a filepath to the relevant c: labels'''
        labels = [x for x in valid_labels if x.startswith('c:')]

        clabels = []
        for cl in labels:
            cl = cl.replace('c:', '', 1)
            al = os.path.join('lib/ansible', cl)
            if al.endswith('/'):
                al = al.rstrip('/')
            for f in files:
                if not f:
                    continue
                if f.startswith(cl) or f.startswith(al):
                    clabels.append(cl)

        # use the more specific labels
        clabels = sorted(set(clabels))
        tmp_clabels = [x for x in clabels]
        for cl in clabels:
            for x in tmp_clabels:
                if cl != x and x.startswith(cl):
                    if cl in tmp_clabels:
                        tmp_clabels.remove(cl)
        if tmp_clabels != clabels:
            clabels = [x for x in tmp_clabels]
            clabels = sorted(set(clabels))

        # Use botmeta
        ckeys = self._filenames_to_keys(files)
        for ckey in ckeys:
            if not self.botmeta['files'].get(ckey):
                continue
            ckey_labels = self.botmeta['files'][ckey].get('labels', [])
            for cklabel in ckey_labels:
                if cklabel in valid_labels and cklabel not in clabels:
                    clabels.append(cklabel)

        return clabels

    def _filenames_to_keys(self, filenames):
        '''Match filenames to the keys in botmeta'''
        ckeys = []
        for filen in filenames:
            # Use botmeta
            if filen in self.botmeta['files']:
                if filen not in ckeys:
                    ckeys.append(filen)
            else:
                for key in self.botmeta['files'].keys():
                    if filen.startswith(key):
                        ckeys.append(key)
        return ckeys

    def _string_to_cmap_key(self, text):
        text = text.lower()
        matches = []
        if text.endswith('.'):
            text = text.rstrip('.')
        if text in self.CMAP:
            matches += self.CMAP[text]
            return matches
        elif (text + 's') in self.CMAP:
            matches += self.CMAP[text + 's']
            return matches
        elif text.rstrip('s') in self.CMAP:
            matches += self.CMAP[text.rstrip('s')]
            return matches
        return matches

    def get_keywords_for_file(self, filename):
        keywords = []
        for k, v in self.CMAP.items():
            toadd = False
            for x in v:
                if x == filename:
                    toadd = True
            if toadd:
                keywords.append(k)
        return keywords

    def find_component_matches_by_file(self, filenames):
        '''Make a list of component matches based on filenames'''

        matches = []
        for filen in filenames:
            match = copy.deepcopy(self.DEFAULT_COMPONENT_MATCH)
            match['filename'] = filen

            ckeys = self._filenames_to_keys([filen])
            ckeys = sorted(set(ckeys))

            for ckey in ckeys:
                cdata = self.botmeta['files'].get(ckey)
                if not cdata:
                    continue

                if 'labels' in cdata:
                    for label in cdata['labels']:
                        if label not in match['labels']:
                            match['labels'].append(label)

                if 'support' in cdata:
                    match['supported_by'] = cdata['support'][0]

                if 'maintainers' in cdata:
                    for user in cdata['maintainers']:
                        if user not in match['owners']:
                            match['owners'].append(user)

                if 'notify' in cdata:
                    for user in cdata['notify']:
                        if user not in match['notify']:
                            match['notify'].append(user)

            matches.append(match)

        return matches

    def find_component_match(self, title, body, template_data):
        '''Make a list of matching files for arbitrary text in an issue'''

        # DistributionNotFound: The 'jinja2<2.9' distribution was not found and
        #   is required by ansible
        # File
        # "/usr/lib/python2.7/site-packages/ansible/plugins/callback/foreman.py",
        #   line 30, in <module>

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
                            if C.DEFAULT_BREAKPOINTS:
                                logging.error('breakpoint!')
                                import epdb; epdb.st()
            if matches:
                return matches

        craws = template_data.get('component_raw')
        if craws is None:
            return matches

        # compare to component mapping
        matches = self._string_to_cmap_key(craws)
        if matches:
            return matches

        # do not re-process the same strings over and over again
        if craws.lower() in self.match_cache:
            return self.match_cache[craws.lower()]

        # make ngrams from largest to smallest and recheck
        blob = TextBlob(craws.lower())
        wordcount = len(blob.tokens) + 1

        for ng_size in reversed(xrange(2, wordcount)):
            ngrams = [' '.join(x) for x in blob.ngrams(ng_size)]
            for ng in ngrams:

                matches = self._string_to_cmap_key(ng)
                if matches:
                    self.match_cache[craws.lower()] = matches
                    return matches

        # https://pypi.python.org/pypi/fuzzywuzzy
        matches = []
        for cr in craws.lower().split('\n'):
            ratios = []
            for k in self.CMAP.keys():
                ratio = fw_fuzz.ratio(cr, k)
                ratios.append((ratio, k))
            ratios = sorted(ratios, key=lambda tup: tup[0])
            if ratios[-1][0] >= 90:
                cnames = self.CMAP[ratios[-1][1]]
                matches += cnames
        if matches:
            self.match_cache[craws.lower()] = matches
            return matches

        # try to match to repo files
        if craws:
            clines = craws.split('\n')
            for craw in clines:
                cparts = craw.replace('-', ' ')
                cparts = cparts.split()

                for idx, x in enumerate(cparts):
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

        logging.info('%s --> %s' % (craws, sorted(set(matches))))
        self.match_cache[craws.lower()] = matches
        return matches

    def get_filemap(self):
        '''Read filemap and make re matchers'''

        self.FILEMAP = {}
        bfiles = self.botmeta.get('files', {})
        for k, v in bfiles.items():
            self.FILEMAP[k] = {}
            reg = k
            if reg.endswith('/'):
                reg += '*'
            self.FILEMAP[k] = {
                #'inclusive': False,
                'inclusive': True,
                'exclusive': False,
                'assign': [],
                'notify': [],
                'labels': []
            }
            self.FILEMAP[k]['regex'] = re.compile(reg)
            if not v:
                continue

            if 'maintainers' in v:
                self.FILEMAP[k]['maintainers'] = v['maintainers']
            if 'assign' in v or 'maintainers' in v:
                if 'assign' in v:
                    self.FILEMAP[k]['assign'] = v['assign']
                if 'maintainers' in v:
                    self.FILEMAP[k]['assign'] += v['maintainers']
                    self.FILEMAP[k]['assign'] = sorted(set(self.FILEMAP[k]['assign']))
            if 'notify' in v or 'maintainers' in v:
                if 'notify' in v:
                    self.FILEMAP[k]['notify'] = v['notify']
                if 'maintainers' in v:
                    self.FILEMAP[k]['notify'] += v['maintainers']
                    self.FILEMAP[k]['notify'] = sorted(set(self.FILEMAP[k]['notify']))
            if 'labels' in v:
                labels = v['labels']
                labels = [x for x in labels if x not in ['lib', 'ansible']]
                self.FILEMAP[k]['labels'] = labels

    def get_filemap_labels_for_files(self, files):
        '''Get expected labels from the filemap'''
        labels = []

        exclusive = False
        for f in files:

            if f is None:
                continue

            # only one match
            if exclusive:
                continue

            for k, v in self.FILEMAP.iteritems():
                if not v['inclusive'] and v['regex'].match(f):
                    labels = v['labels']
                    exclusive = True
                    break

                if 'labels' not in v:
                    continue

                if v['regex'].match(f):
                    for label in v['labels']:
                        if label not in labels:
                            labels.append(label)

        return labels

    def get_filemap_users_for_files(self, files):
        '''Get expected notifiees from the filemap'''
        to_notify = []
        to_assign = []

        exclusive = False
        for f in files:

            if f is None:
                continue

            # only one match
            if exclusive:
                continue

            for k, v in self.FILEMAP.iteritems():
                if not v['inclusive'] and v['regex'].match(f):
                    to_notify = v['notify']
                    to_assign = v['assign']
                    exclusive = True
                    break

                if 'notify' not in v and 'assign' not in v:
                    continue

                if v['regex'].match(f):
                    for user in v['notify']:
                        if user not in to_notify:
                            to_notify.append(user)
                    for user in v['assign']:
                        if user not in to_assign:
                            to_assign.append(user)

        return to_notify, to_assign

    def isnewdir(self, path):
        if path in self.files:
            return False
        else:
            return True

    def commits_by_email(self, email):
        if not isinstance(email, (list, tuple)):
            email = [email]

        if not self.email_commits:
            cmd = 'cd {}; git log --format="%H %ae"'.format(self.checkoutdir)
            (rc, so, se) = run_command(cmd)
            commits = [x.split(None, 1)[::-1] for x in so.split('\n') if x]
            for x in commits:
                if x[0] not in self.email_commits:
                    self.email_commits[x[0]] = []
                self.email_commits[x[0]].append(x[1])

        commits = []
        for x in email:
            commits += self.email_commits.get(x, [])

        return commits
