#!/usr/bin/env python

import json
import logging
import os

from fuzzywuzzy import fuzz as fw_fuzz
from textblob import TextBlob

from ansibullbot.utils.systemtools import run_command
from ansibullbot.utils.moduletools import ModuleIndexer


class FileIndexer(ModuleIndexer):

    files = []

    def __init__(self, checkoutdir=None, cmap=None):

        if not os.path.isfile(cmap):
            import ansibullbot.triagers.ansible as at
            basedir = os.path.dirname(at.__file__)
            basedir = os.path.dirname(basedir)
            basedir = os.path.dirname(basedir)
            cmap = os.path.join(basedir, cmap)

        self.checkoutdir = checkoutdir
        self.CMAP = {}
        if cmap:
            with open(cmap, 'rb') as f:
                self.CMAP = json.load(f)

        self.get_files()
        self.match_cache = {}

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

    def get_file_content(self, filepath):
        fpath = os.path.join(self.checkoutdir, filepath)
        if not os.path.isfile(fpath):
            return None
        with open(fpath, 'rb') as f:
            data = f.read()
        return data

    def get_component_labels(self, valid_labels, files):
        '''Matches a filepath to the relevant c: labels'''
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
                    if cl in tmp_clabels:
                        tmp_clabels.remove(cl)
        if tmp_clabels != clabels:
            clabels = [x for x in tmp_clabels]
            clabels = sorted(set(clabels))

        return clabels

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
                            #import epdb; epdb.st()
                            pass
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

        for ng_size in reversed(xrange(2,wordcount)):
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

        logging.info('%s --> %s' % (craws, sorted(set(matches))))
        self.match_cache[craws.lower()] = matches
        return matches
